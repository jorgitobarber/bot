import time
import json
import os
from binance.client import Client
from config import get_public_mainnet_client
from strategy import generate_signals
from data_provider import get_latest_klines

class MomentumBot:
    def __init__(self, symbol="BTCUSDT", initial_balance=118.0):
        self.symbol = symbol
        self.initial_balance = initial_balance
        self.state_file = f"state_{symbol}_momentum.json"
        self.client = get_public_mainnet_client()
        self.max_bullets = 2
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
            "is_running": True,
            "positions": [],
            "total_profit": 0.0,
            "virtual_balance": self.initial_balance,
            "history": []
        }
        self.save_state()

    def get_invested_usdt(self):
        invested = 0.0
        for pos in self.state.get("positions", []):
            invested += pos["qty"] * pos["buy_price"]
        return invested

    def get_free_balance(self):
        return self.state.get("virtual_balance", self.initial_balance) - self.get_invested_usdt()

    def get_virtual_balance(self):
        return self.state.get("virtual_balance", self.initial_balance)

    def get_current_price(self):
        ticker = self.client.get_symbol_ticker(symbol=self.symbol)
        return float(ticker["price"])

    def log_trade(self, trade_type, price, profit=0.0, buy_price=0.0):
        self.state.setdefault("history", []).insert(0, {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "type": trade_type,
            "price": price,
            "profit": profit,
            "buy_price": buy_price
        })
        self.state["history"] = self.state["history"][:50]

    def check_positions_and_stops(self, current_price, current_atr):
        # Usamos vela de 1m para detectar mechas reales (Wick Hunter)
        try:
            klines = self.client.get_klines(symbol=self.symbol, interval='1m', limit=1)
            current_low = float(klines[0][3])
        except:
            current_low = current_price

        state_changed = False
        positions = self.state.get("positions", [])
        active_positions = []

        for pos in positions:
            # 1. Actualizar Trailing Stop si el precio subió
            if current_price > pos["highest_price"]:
                pos["highest_price"] = current_price
                new_sl = current_price - (2.5 * current_atr)
                if new_sl > pos["stop_loss_price"]:
                    print(f"[TRAILING STOP] Ajustando SL de {pos['stop_loss_price']:.2f} a {new_sl:.2f}")
                    pos["stop_loss_price"] = new_sl
                    state_changed = True

            # 2. Comprobar si la mecha tocó el Stop Loss
            if current_low <= pos["stop_loss_price"]:
                fee = (pos["qty"] * pos["stop_loss_price"]) * 0.001
                c_quote = pos["qty"] * pos["stop_loss_price"]
                profit = (c_quote - (pos["qty"] * pos["buy_price"])) - fee
                
                self.state["total_profit"] += profit
                self.state["virtual_balance"] += profit
                self.log_trade("VENTA_STOP_MARKET", pos["stop_loss_price"], profit, buy_price=pos["buy_price"])
                print(f"[EXITO MAINNET] Posición Cerrada por Trailing Stop @ {pos['stop_loss_price']:.2f} | Ganancia: {profit:.2f}")
                state_changed = True
            else:
                active_positions.append(pos)

        if len(self.state["positions"]) != len(active_positions):
            self.state["positions"] = active_positions
            state_changed = True

        return state_changed

    def tick(self):
        self.state = self.load_state()
        try: current_price = self.get_current_price()
        except: return

        if not self.state: self.initialize_state(current_price)
        if not self.state.get("is_running", True): return

        # 1. Obtener la tendencia macro en velas de 1H
        try:
            df = get_latest_klines(self.symbol, interval='1h', limit=150)
            df_signals = generate_signals(df, ema_window=50, rsi_window=14)
            last_signal_row = df_signals.iloc[-1]
            signal = last_signal_row['signal']
            current_atr = last_signal_row['atr']
        except Exception as e:
            print(f"Error analizando datos de 1H: {e}")
            return

        print(f"[{time.strftime('%H:%M:%S')}] {self.symbol} (SIMULADOR MAINNET 1H) | Spot: {current_price:.2f} | Balas activas: {len(self.state.get('positions', []))}/{self.max_bullets} | Profit: {self.state.get('total_profit', 0.0):.2f}")

        # 2. Revisar Trailing Stops y Wick Hunter
        state_changed = self.check_positions_and_stops(current_price, current_atr)

        # 3. Disparar nuevas "Heavy Bullets" si hay señal y cupo
        positions = self.state.get("positions", [])
        if signal == 1 and len(positions) < self.max_bullets:
            free_balance = self.get_free_balance()
            # Si es la primera bala, usa el 50%. Si es la segunda, usa el resto.
            allocation = free_balance * 0.5 if len(positions) == 0 else free_balance * 0.95
            
            if allocation > 20.0:  # Validar que supere holgadamente el min notional
                qty = allocation / current_price
                fee = (qty * current_price) * 0.001
                sl_price = current_price - (2.5 * current_atr)
                
                self.state["virtual_balance"] -= fee
                self.state["total_profit"] -= fee
                
                new_pos = {
                    "buy_price": current_price,
                    "qty": qty,
                    "highest_price": current_price,
                    "stop_loss_price": sl_price
                }
                self.state["positions"].append(new_pos)
                self.log_trade("COMPRA_HEAVY_BULLET", current_price, -fee)
                print(f"[HEAVY BULLET] Disparando bala de {allocation:.2f} USDT @ {current_price:.2f} | Stop Inicial: {sl_price:.2f}")
                state_changed = True

        if state_changed:
            self.save_state()

def run_trading_bot():
    print("===============================================================")
    print("Iniciando Arquitectura Momentum 1H - Heavy Bullets (Simulador Realista)")
    print("===============================================================")
    symbols = ["SOLUSDT"]
    bots = [MomentumBot(symbol=sym, initial_balance=118.0) for sym in symbols]
    while True:
        for bot in bots:
            try: bot.tick()
            except Exception as e: print(f"Error en {bot.symbol}: {e}")
        time.sleep(3)

if __name__ == "__main__":
    run_trading_bot()
