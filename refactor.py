import re

with open('main.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Remove STATE_FILE
code = re.sub(r'STATE_FILE = "grid_state\.json"\n+', '', code)

# 2. Update __init__
init_old = """    def __init__(self, symbol="BTCUSDT"):
        self.symbol = symbol
        self.client = get_public_mainnet_client()
        self.num_grids = 5
        self.state = self.load_state()"""

init_new = """    def __init__(self, symbol="BTCUSDT", initial_balance=39.33):
        self.symbol = symbol
        self.initial_balance = initial_balance
        self.state_file = f"grid_state_{symbol}.json"
        self.client = get_public_mainnet_client()
        self.num_grids = 5
        self.state = self.load_state()"""

if init_old in code:
    code = code.replace(init_old, init_new)
else:
    print("WARNING: init_old not found!")

# 3. Update load_state and save_state
code = code.replace('STATE_FILE', 'self.state_file')

# 4. Replace 118.0 with self.initial_balance
code = re.sub(r'118\.0', 'self.initial_balance', code)

# 5. Update run_trading_bot
run_old = """def run_trading_bot():
    print("===============================================================")
    print("Iniciando Motor GRID DINÁMICO (Opción C - Frecuencia 3s)")
    print("===============================================================")
    bot = HybridBot(symbol="BTCUSDT")
    while True:
        try: bot.tick()
        except Exception as e: print(f"Error: {e}")
        time.sleep(3)"""

run_new = """def run_trading_bot():
    print("===============================================================")
    print("Iniciando Motor Multi-Cripto (Fase 3) - Frecuencia 3s")
    print("===============================================================")
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    bots = [HybridBot(symbol=sym, initial_balance=39.33) for sym in symbols]
    while True:
        for bot in bots:
            try: bot.tick()
            except Exception as e: print(f"Error en {bot.symbol}: {e}")
        time.sleep(3)"""

if run_old in code:
    code = code.replace(run_old, run_new)
else:
    print("WARNING: run_old not found!")

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Refactor done.')
