import time
import json
import os
from binance.client import Client
from binance.exceptions import BinanceAPIException
from config import get_public_mainnet_client
from execution import round_step, get_symbol_filters
from strategy import generate_signals
from data_provider import get_latest_klines
from risk_manager import calculate_auto_compounding_size

class HybridBot:
    def __init__(self, symbol="BTCUSDT", initial_balance=39.33):
        self.symbol = symbol
        self.initial_balance = initial_balance
        self.state_file = f"grid_state_{symbol}.json"
        self.client = get_public_mainnet_client()
        self.num_grids = 5
        self.state = self.load_state()

    def load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except:
                return None
        return None

    def save_state(self):
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=4)

    def initialize_state(self, current_price):
        self.state = {
            "symbol": self.symbol,
            "base_price": current_price,
            "is_running": True,
            "grids": [],
            "total_profit": 0.0,
            "grid_profit": 0.0,
            "trend_profit": 0.0,
            "virtual_balance": self.initial_balance,
            "history": [],
            "grid_spacing_pct": 0.0
        }
        self.save_state()

    def get_current_price(self):
        ticker = self.client.get_symbol_ticker(symbol=self.symbol)
        return float(ticker["price"])

    def execute_market_order(self, side, quantity, current_price):
        try:
            step_size, _, min_qty = get_symbol_filters(self.client, self.symbol)
            qty = round_step(quantity, step_size)
            if qty < min_qty: return None
            # SIMULADOR LOCAL: Ejecución instantánea
            print(f"[{side}] SIMULADOR MERCADO: {qty} {self.symbol} @ {current_price}")
            return {
                "executedQty": str(qty),
                "price": str(current_price),
                "cummulativeQuoteQty": str(qty * current_price)
            }
        except Exception as e:
            print(f"[ERROR] Ejecutando orden VIRTUAL {side}: {e}")
            return None

    def log_trade(self, trade_type, price, profit=0.0, buy_price=0.0):
        self.state.setdefault("history", []).insert(0, {
            "time": time.strftime("%H:%M:%S"),
            "type": trade_type,
            "price": price,
            "profit": profit,
            "buy_price": buy_price
        })
        self.state["history"] = self.state["history"][:50]

    def deploy_grid_system(self, current_price, current_ema, grid_spacing_pct, allocation_pct=0.5):
        v_balance = self.state.get("virtual_balance", self.initial_balance)
        total_qty, sl_price, total_usdt_alloc = calculate_auto_compounding_size(
            self.client, self.symbol, current_price, allocation_percentage=allocation_pct, override_balance=v_balance
        )
        if total_qty <= 0: return False

        min_usd_per_level = 11.5
        bullet_usdt = total_usdt_alloc / self.num_grids
        
        if bullet_usdt < min_usd_per_level:
            actual_grids = int(total_usdt_alloc // min_usd_per_level)
            if actual_grids < 1:
                print(f"[WARNING] Capital insuficiente ({total_usdt_alloc:.2f} USDT) para abrir niveles del Grid.")
                return False
            bullet_usdt = total_usdt_alloc / actual_grids
        else:
            actual_grids = self.num_grids

        print(f"[INICIO] MOTOR GRID DINÁMICO. Anclado: {current_price:.2f} | Sep: {grid_spacing_pct*100:.2f}% | Niveles: {actual_grids} | Asignación: {allocation_pct*100}%")
        
        grids = []
        for i in range(1, actual_grids + 1):
            buy_p = current_price * (1 - (i * grid_spacing_pct))
            sell_p = buy_p * (1 + grid_spacing_pct)
            qty_raw = bullet_usdt / buy_p
            
            # Anclar orden VIRTUAL en el Simulador Local
            grids.append({
                "level": i,
                "buy_price": buy_p,
                "sell_price": sell_p,
                "status": "WAITING_BUY",
                "alloc_usdt": bullet_usdt,
                "btc_qty": qty_raw
            })
        self.state["grids"] = grids
        self.state["base_price"] = current_price
        self.state["grid_spacing_pct"] = grid_spacing_pct
        return True

    def panic_sell_everything(self, current_price):
        print("[EMERGENCIA] SEÑAL DE EMERGENCIA (-1). Abortando sistema.")
        
        # Vender posiciones abiertas del Grid Virtual
        for grid in self.state.get("grids", []):
            if grid["status"] == "WAITING_SELL" and grid.get("btc_qty", 0) > 0:
                order = self.execute_market_order(Client.SIDE_SELL, grid["btc_qty"], current_price)
                if order:
                    c_quote = float(order.get('cummulativeQuoteQty', 0))
                    alloc = grid.get("alloc_usdt", grid.get("btc_qty", 0) * grid.get("buy_price", 0))
                    profit = c_quote - alloc if c_quote > 0 else 0.0
                    self.state["total_profit"] += profit
                    self.state["grid_profit"] = self.state.get("grid_profit", 0.0) + profit
                    self.state["virtual_balance"] = self.state.get("virtual_balance", self.initial_balance) + profit
                    self.log_trade(f"VENTA_GRID_PANIC_L{grid['level']}", current_price, profit)
        
        self.state["grids"] = []
        self.save_state()

    def check_limit_orders(self, current_price):
        """Simula localmente el cruce de precios con las órdenes Límite virtuales."""
        state_changed = False
        grids = self.state.get("grids", [])
        for grid in grids:
            # === Migración de grids antiguos para asegurar cantidad BTC ===
            if "btc_qty" not in grid or grid["btc_qty"] == 0:
                grid["btc_qty"] = grid.get("alloc_usdt", 11.5) / grid["buy_price"]
                grid.pop("order_id", None)
                state_changed = True
                
            if grid["status"] == "WAITING_BUY":
                if current_price <= grid["buy_price"]:
                    print(f"[EXITO VIRTUAL] Compra Límite ejecutada (Nivel {grid['level']}) @ {grid['buy_price']:.2f}")
                    grid["status"] = "WAITING_SELL"
                    self.log_trade(f"COMPRA_GRID_L{grid['level']}", grid["buy_price"], 0.0)
                    state_changed = True

            elif grid["status"] == "WAITING_SELL":
                if current_price >= grid["sell_price"]:
                    print(f"[EXITO VIRTUAL] Venta Límite ejecutada (Nivel {grid['level']}) @ {grid['sell_price']:.2f}")
                    c_quote = grid["btc_qty"] * grid["sell_price"]
                    alloc = grid.get("alloc_usdt", grid["btc_qty"] * grid["buy_price"])
                    profit = c_quote - alloc if c_quote > 0 else 0.0
                    
                    self.state["total_profit"] += profit
                    self.state["grid_profit"] = self.state.get("grid_profit", 0.0) + profit
                    self.state["virtual_balance"] = self.state.get("virtual_balance", self.initial_balance) + profit
                    grid["status"] = "WAITING_BUY"
                    self.log_trade(f"VENTA_GRID_L{grid['level']}", grid["sell_price"], profit, buy_price=grid["buy_price"])
                    state_changed = True

        return state_changed

    def tick(self):
        self.state = self.load_state()
        try: current_price = self.get_current_price()
        except: return

        if not self.state: self.initialize_state(current_price)
        if not self.state.get("is_running", True): return

        print(f"[{time.strftime('%H:%M:%S')}] {self.symbol} (PAPER TRADING) | Spot: {current_price:.2f} | Beneficio: {self.state.get('total_profit', 0.0):.2f} USDT")

        state_changed = self.check_limit_orders(current_price)

        try:
            df = get_latest_klines(self.symbol, interval='5m', limit=100)
            df_signals = generate_signals(df, ema_window=50, rsi_window=14)
            last_signal_row = df_signals.iloc[-1]
            signal = last_signal_row['signal']
            dynamic_grid_pct = last_signal_row['dynamic_grid_pct']
            current_ema = last_signal_row['ema_50']
            current_adx = last_signal_row['adx_14']
        except Exception as e:
            print(f"Error analizando datos: {e}")
            if state_changed: self.save_state()
            return

        grids = self.state.get("grids", [])
        trend_state = self.state.get("trend_position", None)
        
        # --- ASIGNADOR DINÁMICO DE CAPITAL (ADX) ---
        if current_adx < 25:
            # Mercado Lateral -> Grid utiliza el 100% del capital para pescar la volatilidad
            grid_alloc_pct = 1.0
            trend_alloc_pct = 0.0
        else:
            # Tendencia Fuerte -> Doble Núcleo: Francotirador absorbe 75%, Grid residual 25%
            grid_alloc_pct = 0.25
            trend_alloc_pct = 0.75
            
        v_balance_current = self.state.get("virtual_balance", self.initial_balance)
        new_allocations = {
            "grid_pct": grid_alloc_pct,
            "trend_pct": trend_alloc_pct,
            "grid_usdt": v_balance_current * grid_alloc_pct,
            "trend_usdt": v_balance_current * trend_alloc_pct
        }
        
        if self.state.get("allocations") != new_allocations:
            self.state["allocations"] = new_allocations
            state_changed = True

        # --- MOTOR 1: TREND FOLLOWER (Dinámico) ---
        if signal == 2 and trend_alloc_pct > 0:
            if not trend_state:
                v_balance = self.state.get("virtual_balance", self.initial_balance)
                total_qty, sl_price, _ = calculate_auto_compounding_size(
                    self.client, self.symbol, current_price, allocation_percentage=trend_alloc_pct, stop_loss_percentage=0.03, override_balance=v_balance
                )
                if total_qty > 0:
                    print(f"[TREND] ¡TENDENCIA FUERTE DETECTADA (ADX>25)! Desplegando Franco-Tirador VIRTUAL.")
                    order = self.execute_market_order(Client.SIDE_BUY, total_qty, current_price)
                    if order:
                        self.state["trend_position"] = {
                            "buy_price": current_price,
                            "qty": total_qty,
                            "highest_price": current_price,
                            "stop_loss_price": sl_price
                        }
                        self.log_trade("COMPRA_TREND", current_price)
                        state_changed = True
            else:
                # Trailing Stop: Si el precio sube un 1.5% desde el último máximo, subimos el Stop
                if current_price > trend_state["highest_price"] * 1.015:
                    trend_state["highest_price"] = current_price
                    new_sl_price = current_price * (1 - 0.03) # Trailing del 3%
                    if new_sl_price > trend_state["stop_loss_price"]:
                        print(f"[TREND] Actualizando Trailing Stop VIRTUAL hacia arriba: {new_sl_price:.2f}")
                        trend_state["stop_loss_price"] = new_sl_price
                        state_changed = True

        # Revisar si el Stop Loss VIRTUAL se ejecutó
        if trend_state:
            if current_price <= trend_state["stop_loss_price"]:
                c_quote = trend_state["qty"] * trend_state["stop_loss_price"]
                profit = c_quote - (trend_state["qty"] * trend_state["buy_price"])
                self.state["total_profit"] += profit
                self.state["trend_profit"] = self.state.get("trend_profit", 0.0) + profit
                self.state["virtual_balance"] = self.state.get("virtual_balance", self.initial_balance) + profit
                self.log_trade("VENTA_TREND_STOP", trend_state["stop_loss_price"], profit, buy_price=trend_state["buy_price"])
                self.state["trend_position"] = None
                print(f"[TREND] Trailing Stop VIRTUAL Alcanzado. Ola surfeada con éxito. Ganancia: {profit:.2f}")
                state_changed = True

        # --- MOTOR 2: GRID DE ALTA FRECUENCIA ---
        # Trailing Grid: Si todas las redes están vacías y el precio sube más de 0.5% alejándose, las recogemos
        if grids:
            all_waiting_buy = all(g["status"] == "WAITING_BUY" for g in grids)
            if all_waiting_buy:
                highest_buy = max(g["buy_price"] for g in grids)
                if current_price > highest_buy * 1.005:
                    print(f"[GRID RE-ANCHOR] Precio subió demasiado. Recogiendo redes vacías para seguirlo...")
                    self.state["grids"] = []
                    grids = []
                    state_changed = True
                    
        # Solo lo iniciamos si la red no está creada y si el ADX dice que no estamos en tendencia fuerte (señal distinta a -1 o -2).
        if len(grids) == 0 and signal not in [-1, -2] and grid_alloc_pct > 0:
            if self.deploy_grid_system(current_price, current_ema, dynamic_grid_pct, allocation_pct=grid_alloc_pct):
                state_changed = True
                
        # Lógica de Red Dinámica de Arrastre Estructural (Trailing EMA Grid)
        if len(grids) > 0 and signal not in [-1, -2]:
            base_price = self.state.get("base_price", current_ema)
            grid_spacing_pct = self.state.get("grid_spacing_pct", 0.005)
            # Si la EMA sube más de 1 nivel entero por encima de nuestra ancla original
            if current_ema > base_price * (1 + (grid_spacing_pct * 1.0)):
                print(f"[TRAILING ESTRUCTURAL] EMA subió a {current_ema:.2f}. Moviendo red de pesca hacia arriba...")
                # Cancelar órdenes límite actuales del Grid en Binance (VIRTUAL)
                # Vender posiciones atrapadas para liberar capital al nuevo nivel
                for g in grids:
                    if g["status"] == "WAITING_SELL" and g.get("btc_qty", 0) > 0:
                        order = self.execute_market_order(Client.SIDE_SELL, g["btc_qty"], current_price)
                        if order:
                            c_quote = float(order.get('cummulativeQuoteQty', 0))
                            alloc = g.get("alloc_usdt", g.get("btc_qty", 0) * g.get("buy_price", 0))
                            profit = c_quote - alloc if c_quote > 0 else 0.0
                            self.state["total_profit"] += profit
                            self.state["grid_profit"] = self.state.get("grid_profit", 0.0) + profit
                            self.state["virtual_balance"] = self.state.get("virtual_balance", self.initial_balance) + profit
                            self.log_trade(f"VENTA_GRID_RECENTER_L{g['level']}", current_price, profit)
                # Vaciar la red para que se vuelva a desplegar en el próximo tick
                self.state["grids"] = []
                state_changed = True

        # Freno de Emergencia (Capa 3) solo para el Grid
        grids = self.state.get("grids", []) # Recargar por si se vació
        if len(grids) > 0:
            lowest_grid_price = min([g["buy_price"] for g in grids])
            # El Freno Dinámico: Aborta si hay Pánico Extremo (signal = -1) o si perfora 1.5% debajo de la última red.
            if signal == -1 or current_price < (lowest_grid_price * 0.985):
                self.panic_sell_everything(current_price)
                return

        if state_changed:
            self.save_state()

def run_trading_bot():
    print("===============================================================")
    print("Iniciando Experimento de Alta Volatilidad - Frecuencia 3s")
    print("===============================================================")
    # Experimento: Todo el capital a la cripto con mayor volatilidad intradía (Solana)
    symbols = ["SOLUSDT"]
    bots = [HybridBot(symbol=sym, initial_balance=118.0) for sym in symbols]
    while True:
        for bot in bots:
            try: bot.tick()
            except Exception as e: print(f"Error en {bot.symbol}: {e}")
        time.sleep(3)

if __name__ == "__main__":
    run_trading_bot()
