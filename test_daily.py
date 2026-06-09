import pandas as pd
from binance.client import Client
from config import get_public_mainnet_client

def test_daily_strategy():
    client = get_public_mainnet_client()
    klines = client.get_historical_klines("BTCUSDT", Client.KLINE_INTERVAL_1DAY, "1000 days ago UTC")
    df = pd.DataFrame(klines, columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['close'] = df['close'].astype(float)
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    
    balance = 120.0
    btc = 0.0
    in_pos = False
    
    for i in range(50, len(df)):
        if not in_pos and df['ema_20'].iloc[i] > df['ema_50'].iloc[i] and df['ema_20'].iloc[i-1] <= df['ema_50'].iloc[i-1]:
            btc = balance / df['close'].iloc[i] * 0.999
            balance = 0
            in_pos = True
        elif in_pos and df['ema_20'].iloc[i] < df['ema_50'].iloc[i] and df['ema_20'].iloc[i-1] >= df['ema_50'].iloc[i-1]:
            balance = btc * df['close'].iloc[i] * 0.999
            btc = 0
            in_pos = False
            
    if in_pos:
        balance = btc * df['close'].iloc[-1] * 0.999
    print(f"Final Balance: {balance}")

if __name__ == "__main__":
    test_daily_strategy()
