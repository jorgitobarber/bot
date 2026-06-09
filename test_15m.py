import pandas as pd
from binance.client import Client
from config import get_public_mainnet_client
from strategy import generate_signals

def test_15m_breakout():
    client = get_public_mainnet_client()
    klines = client.get_historical_klines("BTCUSDT", Client.KLINE_INTERVAL_15MINUTE, "30 days ago UTC")
    df = pd.DataFrame(klines, columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
        
    df = generate_signals(df)
    
    usdt_balance = 120.0
    btc_balance = 0.0
    in_position = False
    entry_price = 0.0
    highest_price_in_trade = 0.0
    trailing_stop_price = 0.0
    
    for i in range(50, len(df)):
        row = df.iloc[i]
        
        if not in_position:
            if row['signal'] == 1:
                entry_price = row['close']
                highest_price_in_trade = entry_price
                trailing_stop_price = entry_price - (row['atr'] * 1.5)
                
                position_usdt = usdt_balance * 0.99
                btc_bought = position_usdt / entry_price
                btc_balance = btc_bought * 0.999
                usdt_balance -= position_usdt
                in_position = True
        else:
            if row['high'] > highest_price_in_trade:
                highest_price_in_trade = row['high']
                new_ts = highest_price_in_trade - (row['atr'] * 1.5)
                if new_ts > trailing_stop_price:
                    trailing_stop_price = new_ts
                    
            if row['low'] <= trailing_stop_price:
                usdt_gained = btc_balance * trailing_stop_price
                usdt_balance += usdt_gained * 0.999
                btc_balance = 0.0
                in_position = False
            elif row['signal'] == -1:
                usdt_gained = btc_balance * row['close']
                usdt_balance += usdt_gained * 0.999
                btc_balance = 0.0
                in_position = False
                
    if in_position:
        usdt_balance += btc_balance * df.iloc[-1]['close'] * 0.999
        
    print(f"Final Balance 15m Breakout: {usdt_balance}")

if __name__ == "__main__":
    test_15m_breakout()
