import pandas as pd
from binance.client import Client
from config import get_public_mainnet_client

def test_rsi_mean_reversion():
    client = get_public_mainnet_client()
    klines = client.get_historical_klines("BTCUSDT", Client.KLINE_INTERVAL_15MINUTE, "30 days ago UTC")
    df = pd.DataFrame(klines, columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
        
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    usdt_balance = 120.0
    btc_balance = 0.0
    in_position = False
    entry_price = 0.0
    
    for i in range(50, len(df)):
        row = df.iloc[i]
        
        if not in_position:
            if row['rsi'] < 25:
                entry_price = row['close']
                position_usdt = usdt_balance * 0.99
                btc_bought = position_usdt / entry_price
                btc_balance = btc_bought * 0.999
                usdt_balance -= position_usdt
                in_position = True
        else:
            tp = entry_price * 1.005 # 0.5% ganancia
            sl = entry_price * 0.98  # 2.0% perdida
            
            if row['high'] >= tp:
                usdt_gained = btc_balance * tp
                usdt_balance += usdt_gained * 0.999
                btc_balance = 0.0
                in_position = False
            elif row['low'] <= sl:
                usdt_gained = btc_balance * sl
                usdt_balance += usdt_gained * 0.999
                btc_balance = 0.0
                in_position = False
                
    if in_position:
        usdt_balance += btc_balance * df.iloc[-1]['close'] * 0.999
        
    print(f"Final Balance 15m RSI Mean Reversion: {usdt_balance}")

if __name__ == "__main__":
    test_rsi_mean_reversion()
