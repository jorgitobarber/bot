import time
import json
import os
from binance.client import Client
from config import get_binance_client
from execution import round_step, get_symbol_filters
from strategy import generate_signals
from data_provider import get_latest_klines
from risk_manager import calculate_auto_compounding_size

STATE_FILE = "grid_state.json"

class HybridBot:
    def __init__(self, symbol="BTCUSDT"):
        self.symbol = symbol
        self.client = get_binance_client()
        self.grid_spacing_pct = 0.005 # 0.5% Scalping
        self.num_grids = 4
        self.state = self.load_state()

    def load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
            except:
                return None
        return None

    def save_state(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.state, f, indent=4)

    def initialize_state(self, current_price):
        self.state = {
            "symbol": self.symbol,
            "base_price": current_price,
            "is_running": True,
            "hold_position": None, # La bolsa para la ganancia grande (Trailing Stop)
            "grids": [],           # La metralleta para ganancias pequeñas (Scalping)
            "total_profit": 0.0,
            "history": []
        }
        self.save_state()

    def get_current_price(self):
        ticker = self.client.get_symbol_ticker(symbol=self.symbol)
        return float(ticker["price"])

    def execute_market_order(self, side, quantity):
        try:
            step_size, _, min_qty = get_symbol_filters(self.client, self.symbol)
            qty = round_step(quantity, step_size)
            if qty < min_qty: return None
            order = self.client.create_order(
                symbol=self.symbol,
                side=side,
                type=Client.ORDER_TYPE_MARKET,
                quantity=qty
            )
            print(f"[{side}] Ejecutada: {qty} {self.symbol}")
            return order
        except Exception as e:
            print(f"[ERROR] Ejecutando orden {side}: {e}")
            return None

    def log_trade(self, trade_type, price, profit=0.0):
        self.state.setdefault("history", []).insert(0, {
            "time": time.strftime("%H:%M:%S"),
            "type": trade_type,
            "price": price,
            "profit": profit
        })
        self.state["history"] = self.state["history"][:50]

    def deploy_hybrid_system(self, current_price, atr):
        # Solicitamos el 5% del capital total
        total_qty, sl_price, total_usdt_alloc = calculate_auto_compounding_size(
            self.client, self.symbol, current_price, allocation_percentage=0.05
        )
        if total_qty <= 0: return False

        print(f"🚀 INICIANDO MOTOR HÍBRIDO. Capital asignado: {total_usdt_alloc:.2f} USDT")
        
        # DIVIDIR CAPITAL: 50% para Hold (Ganancia Grande), 50% para Scalping (Metralleta)
        hold_usdt = total_usdt_alloc * 0.50
        scalp_usdt = total_usdt_alloc * 0.50

        # --- 1. COMPRAR BOLSA HOLD ---
        hold_qty_raw = hold_usdt / current_price
        order = self.execute_market_order(Client.SIDE_BUY, hold_qty_raw)
        if order:
            self.state["hold_position"] = {
                "entry_price": current_price,
                "qty": float(order['executedQty']),
                "highest_price": current_price,
                "atr_at_entry": atr,
                "usdt_allocated": hold_usdt
            }
            self.log_trade("COMPRA_HOLD", current_price, 0.0)

        # --- 2. DESPLEGAR GRID SCALPING ---
        # Usamos el scalp_usdt divido en balas (niveles de grid hacia abajo)
        bullet_usdt = scalp_usdt / self.num_grids
        grids = []
        for i in range(1, self.num_grids + 1):
            buy_p = current_price * (1 - (i * self.grid_spacing_pct))
            sell_p = buy_p * (1 + self.grid_spacing_pct)
            grids.append({
                "level": i,
                "buy_price": buy_p,
                "sell_price": sell_p,
                "status": "WAITING_BUY",
                "alloc_usdt": bullet_usdt,
                "btc_qty": 0.0
            })
        self.state["grids"] = grids
        self.state["base_price"] = current_price
        return True

    def panic_sell_everything(self, current_price):
        print("🚨 SEÑAL DE EMERGENCIA (-1). Cerrando todas las posiciones híbridas para proteger capital.")
        # Vender bolsa Hold
        if self.state.get("hold_position"):
            pos = self.state["hold_position"]
            order = self.execute_market_order(Client.SIDE_SELL, pos["qty"])
            if order:
                c_quote = float(order.get('cummulativeQuoteQty', 0))
                profit = c_quote - pos["usdt_allocated"] if c_quote > 0 else 0.0
                self.state["total_profit"] += profit
                self.log_trade("VENTA_HOLD_PANIC", current_price, profit)
            self.state["hold_position"] = None
        
        # Vender posiciones abiertas del Grid
        for grid in self.state.get("grids", []):
            if grid["status"] == "WAITING_SELL" and grid["btc_qty"] > 0:
                order = self.execute_market_order(Client.SIDE_SELL, grid["btc_qty"])
                if order:
                    c_quote = float(order.get('cummulativeQuoteQty', 0))
                    profit = c_quote - grid["alloc_usdt"] if c_quote > 0 else 0.0
                    self.state["total_profit"] += profit
                    self.log_trade(f"VENTA_GRID_PANIC_L{grid['level']}", current_price, profit)
        
        # Borrar el grid
        self.state["grids"] = []
        self.save_state()

    def tick(self):
        self.state = self.load_state()
        try:
            current_price = self.get_current_price()
        except: return

        if not self.state: self.initialize_state(current_price)
        if not self.state.get("is_running", True): return

        print(f"[{time.strftime('%H:%M:%S')}] {self.symbol} | Precio: {current_price:.2f} | Beneficio: {self.state.get('total_profit', 0.0):.2f} USDT")

        # 1. Analizar el Cerebro Institucional
        try:
            df = get_latest_klines(self.symbol, interval='15m', limit=100)
            # Aplicamos los parámetros optimizados por fuerza bruta
            df_signals = generate_signals(df, ema_window=50, rsi_window=21, rsi_min=60, rsi_max=70)
            last_signal_row = df_signals.iloc[-1]
            signal = last_signal_row['signal']
            atr = last_signal_row['atr']
        except Exception as e:
            print(f"Error analizando datos: {e}")
            return

        state_changed = False

        # --- CONTROL DE LA BOLSA HOLD (La ganancia grande) ---
        hold_pos = self.state.get("hold_position")
        
        if hold_pos is None and len(self.state.get("grids", [])) == 0:
            if signal == 1:
                # Luz verde: Desplegar todo el sistema Híbrido
                if self.deploy_hybrid_system(current_price, atr):
                    state_changed = True
        elif hold_pos is not None:
            # Trailing Stop de la bolsa Hold
            if current_price > hold_pos["highest_price"]:
                hold_pos["highest_price"] = current_price
                state_changed = True
                
            trailing_stop = hold_pos["highest_price"] - (atr * 2)
            hard_stop = hold_pos["entry_price"] * 0.98
            activation_price = max(hard_stop, trailing_stop)
            
            # Si el Cerebro dice -1 (Cambio de tendencia brutal) o toca el Stop
            if signal == -1 or current_price <= activation_price:
                self.panic_sell_everything(current_price)
                return # Salir del tick

        # --- CONTROL DEL GRID (El Scalping de ganancias pequeñas) ---
        grids = self.state.get("grids", [])
        for grid in grids:
            # Comprar scalping
            if grid["status"] == "WAITING_BUY" and current_price <= grid["buy_price"]:
                print(f"[GRID L{grid['level']}] Precio cruzó {grid['buy_price']:.2f}. Haciendo micro-compra...")
                qty_raw = grid["alloc_usdt"] / current_price
                order = self.execute_market_order(Client.SIDE_BUY, qty_raw)
                if order:
                    grid["btc_qty"] = float(order['executedQty'])
                    grid["status"] = "WAITING_SELL"
                    self.log_trade(f"COMPRA_GRID_L{grid['level']}", current_price, 0.0)
                    state_changed = True
                    
            # Vender scalping (Tomar pequeña ganancia)
            elif grid["status"] == "WAITING_SELL" and current_price >= grid["sell_price"]:
                print(f"[GRID L{grid['level']}] Precio cruzó {grid['sell_price']:.2f}. Cobrando micro-ganancia...")
                order = self.execute_market_order(Client.SIDE_SELL, grid["btc_qty"])
                if order:
                    c_quote = float(order.get('cummulativeQuoteQty', 0))
                    profit = c_quote - grid["alloc_usdt"] if c_quote > 0 else 0.0
                    self.state["total_profit"] += profit
                    grid["btc_qty"] = 0.0
                    grid["status"] = "WAITING_BUY"
                    self.log_trade(f"VENTA_GRID_L{grid['level']}", current_price, profit)
                    state_changed = True

        if state_changed:
            self.save_state()

def run_trading_bot():
    print("===============================================================")
    print("Iniciando Motor HÍBRIDO (Francotirador Hold + Metralleta Scalp)")
    print("===============================================================")
    bot = HybridBot(symbol="BTCUSDT")
    while True:
        try: bot.tick()
        except Exception as e: print(f"Error: {e}")
        time.sleep(15)

if __name__ == "__main__":
    run_trading_bot()
