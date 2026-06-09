import time
import json
import os
from binance.client import Client
from binance.exceptions import BinanceAPIException
from config import get_binance_client
from execution import round_step, get_symbol_filters, execute_limit_order, cancel_all_open_orders
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
            "hold_position": None,
            "grids": [],
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
            print(f"[{side}] Ejecutada MERCADO: {qty} {self.symbol}")
            return order
        except Exception as e:
            print(f"[ERROR] Ejecutando orden {side}: {e}")
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

    def deploy_hybrid_system(self, current_price, atr):
        total_qty, sl_price, total_usdt_alloc = calculate_auto_compounding_size(
            self.client, self.symbol, current_price, allocation_percentage=0.05
        )
        if total_qty <= 0: return False

        print(f"[INICIO] MOTOR HÍBRIDO. Capital asignado: {total_usdt_alloc:.2f} USDT")
        
        hold_usdt = total_usdt_alloc * 0.50
        scalp_usdt = total_usdt_alloc * 0.50

        # --- 1. COMPRAR BOLSA HOLD (Market) ---
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

        # --- 2. DESPLEGAR GRID SCALPING (LIMIT BUY ORDERS) ---
        bullet_usdt = scalp_usdt / self.num_grids
        grids = []
        for i in range(1, self.num_grids + 1):
            buy_p = current_price * (1 - (i * self.grid_spacing_pct))
            sell_p = buy_p * (1 + self.grid_spacing_pct)
            qty_raw = bullet_usdt / buy_p
            
            # Anclar orden en Binance
            limit_order = execute_limit_order(self.client, self.symbol, Client.SIDE_BUY, qty_raw, buy_p)
            if limit_order:
                grids.append({
                    "level": i,
                    "buy_price": buy_p,
                    "sell_price": sell_p,
                    "status": "WAITING_BUY",
                    "alloc_usdt": bullet_usdt,
                    "btc_qty": 0.0,
                    "order_id": limit_order['orderId']
                })
        self.state["grids"] = grids
        self.state["base_price"] = current_price
        return True

    def panic_sell_everything(self, current_price):
        print("[EMERGENCIA] SEÑAL DE EMERGENCIA (-1). Abortando sistema híbrido.")
        # Primero cancelar todas las órdenes Límite puestas en Binance
        cancel_all_open_orders(self.client, self.symbol)

        # Vender bolsa Hold a precio de mercado
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
            if grid["status"] == "WAITING_SELL" and grid.get("btc_qty", 0) > 0:
                order = self.execute_market_order(Client.SIDE_SELL, grid["btc_qty"])
                if order:
                    c_quote = float(order.get('cummulativeQuoteQty', 0))
                    alloc = grid.get("alloc_usdt", grid.get("btc_qty", 0) * grid.get("buy_price", 0))
                    profit = c_quote - alloc if c_quote > 0 else 0.0
                    self.state["total_profit"] += profit
                    self.log_trade(f"VENTA_GRID_PANIC_L{grid['level']}", current_price, profit)
        
        self.state["grids"] = []
        self.save_state()

    def check_limit_orders(self):
        """Verifica en Binance el estado de las órdenes límite puestas por el Grid."""
        state_changed = False
        grids = self.state.get("grids", [])
        for grid in grids:
            # === Migración de compras atrapadas antiguas ===
            if grid["status"] == "WAITING_SELL" and "order_id" not in grid:
                print(f"[MIGRACIÓN] Anclando Venta Límite nivel {grid['level']} en {grid['sell_price']}")
                limit_order = execute_limit_order(self.client, self.symbol, Client.SIDE_SELL, grid.get("btc_qty",0), grid["sell_price"])
                if limit_order:
                    grid["order_id"] = limit_order['orderId']
                    state_changed = True
                continue
            
            # === Recuperar órdenes canceladas manualmente y crear nuevas ===
            if grid["status"] == "WAITING_BUY" and "order_id" not in grid:
                qty_raw = grid.get("alloc_usdt", 11.8) / grid["buy_price"]
                limit_order = execute_limit_order(self.client, self.symbol, Client.SIDE_BUY, qty_raw, grid["buy_price"])
                if limit_order:
                    grid["order_id"] = limit_order['orderId']
                    state_changed = True
                continue

            if "order_id" not in grid: continue
            
            try:
                order_info = self.client.get_order(symbol=self.symbol, orderId=grid["order_id"])
            except BinanceAPIException as e:
                continue

            if order_info['status'] == 'FILLED':
                print(f"[EXITO] ¡ORDEN LÍMITE EJECUTADA INSTANTÁNEAMENTE! (Nivel {grid['level']})")
                executed_qty = float(order_info['executedQty'])
                executed_price = float(order_info['price']) if float(order_info['price']) > 0 else float(order_info['cummulativeQuoteQty'])/executed_qty
                
                if grid["status"] == "WAITING_BUY":
                    grid["btc_qty"] = executed_qty
                    grid["status"] = "WAITING_SELL"
                    self.log_trade(f"COMPRA_GRID_L{grid['level']}", executed_price, 0.0)
                    
                    sell_limit = execute_limit_order(self.client, self.symbol, Client.SIDE_SELL, executed_qty, grid["sell_price"])
                    if sell_limit:
                        grid["order_id"] = sell_limit['orderId']
                    else:
                        grid.pop("order_id", None)
                    state_changed = True

                elif grid["status"] == "WAITING_SELL":
                    c_quote = float(order_info['cummulativeQuoteQty'])
                    alloc = grid.get("alloc_usdt", grid.get("btc_qty", 0) * grid.get("buy_price", 0))
                    profit = c_quote - alloc if c_quote > 0 else 0.0
                    self.state["total_profit"] += profit
                    grid["btc_qty"] = 0.0
                    grid["status"] = "WAITING_BUY"
                    self.log_trade(f"VENTA_GRID_L{grid['level']}", executed_price, profit, buy_price=grid["buy_price"])
                    
                    qty_raw = grid.get("alloc_usdt", 10.0) / grid["buy_price"]
                    buy_limit = execute_limit_order(self.client, self.symbol, Client.SIDE_BUY, qty_raw, grid["buy_price"])
                    if buy_limit:
                        grid["order_id"] = buy_limit['orderId']
                    else:
                        grid.pop("order_id", None)
                    state_changed = True

            elif order_info['status'] in ['CANCELED', 'REJECTED']:
                grid.pop("order_id", None) 
                state_changed = True

        return state_changed

    def tick(self):
        self.state = self.load_state()
        try: current_price = self.get_current_price()
        except: return

        if not self.state: self.initialize_state(current_price)
        if not self.state.get("is_running", True): return

        print(f"[{time.strftime('%H:%M:%S')}] {self.symbol} | Spot: {current_price:.2f} | Beneficio: {self.state.get('total_profit', 0.0):.2f} USDT")

        state_changed = self.check_limit_orders()

        try:
            df = get_latest_klines(self.symbol, interval='15m', limit=100)
            df_signals = generate_signals(df, ema_window=50, rsi_window=21, rsi_min=60, rsi_max=70)
            last_signal_row = df_signals.iloc[-1]
            signal = last_signal_row['signal']
            atr = last_signal_row['atr']
        except Exception as e:
            print(f"Error analizando datos: {e}")
            if state_changed: self.save_state()
            return

        hold_pos = self.state.get("hold_position")
        
        if hold_pos is None and len(self.state.get("grids", [])) == 0:
            if signal == 1:
                if self.deploy_hybrid_system(current_price, atr):
                    state_changed = True
        elif hold_pos is not None:
            if current_price > hold_pos["highest_price"]:
                hold_pos["highest_price"] = current_price
                state_changed = True
                
            trailing_stop = hold_pos["highest_price"] - (atr * 2)
            hard_stop = hold_pos["entry_price"] * 0.98
            activation_price = max(hard_stop, trailing_stop)
            
            if signal == -1 or current_price <= activation_price:
                self.panic_sell_everything(current_price)
                return

        if state_changed:
            self.save_state()

def run_trading_bot():
    print("===============================================================")
    print("Iniciando Motor HÍBRIDO PRO (Órdenes Límite Directo a Binance)")
    print("===============================================================")
    bot = HybridBot(symbol="BTCUSDT")
    while True:
        try: bot.tick()
        except Exception as e: print(f"Error: {e}")
        time.sleep(15)

if __name__ == "__main__":
    run_trading_bot()
