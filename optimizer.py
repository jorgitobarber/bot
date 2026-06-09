import itertools
from data_provider import get_latest_klines
from strategy import generate_signals

def simulate_hybrid(df, grid_spacing_pct=0.005, num_grids=4):
    initial_balance = 1000.0
    balance = initial_balance
    hold_position = None
    grids = []
    
    trades_hold = 0
    trades_scalp = 0
    win_hold = 0
    win_scalp = 0

    for i in range(100, len(df)): # Empezar en 100 para asegurar que la EMA100 tenga datos
        row = df.iloc[i]
        current_price = row['close']
        signal = row['signal']
        atr = row['atr']
        
        # --- ENTRADA (Cerebro) ---
        if hold_position is None and len(grids) == 0:
            if signal == 1:
                total_alloc = balance * 0.05
                hold_usdt = total_alloc * 0.5
                scalp_usdt = total_alloc * 0.5
                
                # 1. Comprar Hold
                hold_qty = (hold_usdt / current_price) * 0.999
                balance -= hold_usdt
                hold_position = {
                    "entry_price": current_price,
                    "qty": hold_qty,
                    "highest_price": current_price,
                    "usdt_allocated": hold_usdt,
                    "atr": atr
                }
                
                # 2. Desplegar Grids
                bullet_usdt = scalp_usdt / num_grids
                grids = []
                for g in range(1, num_grids + 1):
                    buy_p = current_price * (1 - (g * grid_spacing_pct))
                    sell_p = buy_p * (1 + grid_spacing_pct)
                    grids.append({
                        "level": g,
                        "buy_price": buy_p,
                        "sell_price": sell_p,
                        "status": "WAITING_BUY",
                        "alloc_usdt": bullet_usdt,
                        "btc_qty": 0.0
                    })
                    
        # --- GESTIÓN DE POSICIONES ABIERTAS ---
        elif hold_position is not None:
            if current_price > hold_position["highest_price"]:
                hold_position["highest_price"] = current_price
                
            atr_val = hold_position["atr"]
            trailing_stop = hold_position["highest_price"] - (atr_val * 2)
            hard_stop = hold_position["entry_price"] * 0.98
            activation_price = max(hard_stop, trailing_stop)
            
            # PÁNICO / SALIDA
            if signal == -1 or current_price <= activation_price:
                # 1. Vender Hold
                gross_hold = hold_position["qty"] * current_price
                net_hold = gross_hold * 0.999
                profit_hold = net_hold - hold_position["usdt_allocated"]
                balance += net_hold
                
                trades_hold += 1
                if profit_hold > 0: win_hold += 1
                
                # 2. Vender Grids
                for grid in grids:
                    if grid["status"] == "WAITING_SELL":
                        gross_g = grid["btc_qty"] * current_price
                        net_g = gross_g * 0.999
                        profit_g = net_g - grid["alloc_usdt"]
                        balance += net_g
                        trades_scalp += 1
                        if profit_g > 0: win_scalp += 1
                
                hold_position = None
                grids = []
                continue
            
            # --- SCALPING CONTINUO ---
            for grid in grids:
                if grid["status"] == "WAITING_BUY" and current_price <= grid["buy_price"]:
                    qty = (grid["alloc_usdt"] / current_price) * 0.999
                    balance -= grid["alloc_usdt"]
                    grid["btc_qty"] = qty
                    grid["status"] = "WAITING_SELL"
                    
                elif grid["status"] == "WAITING_SELL" and current_price >= grid["sell_price"]:
                    gross = grid["btc_qty"] * current_price
                    net = gross * 0.999
                    profit = net - grid["alloc_usdt"]
                    balance += net
                    
                    trades_scalp += 1
                    if profit > 0: win_scalp += 1
                    
                    grid["btc_qty"] = 0.0
                    grid["status"] = "WAITING_BUY"

    # Liquidación Final
    if hold_position is not None:
        balance += hold_position["qty"] * current_price * 0.999
        for grid in grids:
            if grid["status"] == "WAITING_SELL":
                balance += grid["btc_qty"] * current_price * 0.999

    return balance - initial_balance

def run_optimizer():
    print("Descargando historial del mercado (5000 velas de 15m)...")
    df_raw = get_latest_klines("BTCUSDT", "15m", 5000)
    
    emas = [10, 20, 30, 50, 100]
    rsis = [7, 10, 14, 21]
    rsi_mins = [40, 50, 60]
    rsi_maxs = [70, 80, 90]
    
    best_profit = -9999
    best_params = None
    
    print("Iniciando fuerza bruta sobre miles de combinaciones...")
    
    combinations = list(itertools.product(emas, rsis, rsi_mins, rsi_maxs))
    
    for ema, rsi, rmin, rmax in combinations:
        if rmin >= rmax: continue
        
        df = df_raw.copy()
        df = generate_signals(df, ema_window=ema, rsi_window=rsi, rsi_min=rmin, rsi_max=rmax)
        
        profit = simulate_hybrid(df)
        
        if profit > best_profit:
            best_profit = profit
            best_params = (ema, rsi, rmin, rmax)
            print(f"Nuevo Campeón! EMA:{ema} RSI:{rsi} Rango:[{rmin}-{rmax}] -> Ganancia Neta: {profit:.2f} USDT")

    print("\n================= OPTIMIZACIÓN COMPLETADA =================")
    print(f"Mejor Configuración Encontrada:")
    print(f"EMA Window: {best_params[0]}")
    print(f"RSI Window: {best_params[1]}")
    print(f"RSI Mínimo: {best_params[2]}")
    print(f"RSI Máximo: {best_params[3]}")
    print(f"Ganancia Neta Simulada: {best_profit:.2f} USDT")
    print("===========================================================")

if __name__ == "__main__":
    run_optimizer()
