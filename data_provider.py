import pandas as pd
from binance.client import Client
from config import get_public_mainnet_client

def get_latest_klines(symbol: str, interval: str, limit: int = 100) -> pd.DataFrame:
    """
    Obtiene las últimas velas (klines) reales de la Mainnet de Binance.
    """
    # Usamos el cliente público de MAINNET para ver el mercado real
    client = get_public_mainnet_client()
    
    try:
        if limit > 1000:
            if interval == '1m': start_str = "2000 minutes ago"
            elif interval == '5m': start_str = "10000 minutes ago"
            elif interval == '15m': start_str = "30000 minutes ago"
            elif interval == '1h': start_str = "5000 hours ago"
            elif interval == '4h': start_str = "20000 hours ago"
            else: start_str = "1 Jan, 2017"
            
            klines = client.get_historical_klines(symbol, interval, start_str)
        else:
            klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
            
        df = pd.DataFrame(klines, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
            
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
        
        return df
    except Exception as e:
        print(f"Error obteniendo datos históricos reales para {symbol}: {e}")
        raise e
