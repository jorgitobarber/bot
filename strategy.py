import pandas as pd
import numpy as np

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calcula el Average True Range (ATR) para medir la volatilidad absoluta.
    Esencial para nuestro Trailing Stop dinámico.
    """
    high = df['high']
    low = df['low']
    prev_close = df['close'].shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean().fillna(0)

def calculate_ema(df: pd.DataFrame, period: int = 50) -> pd.Series:
    """
    Calcula la Media Móvil Exponencial (EMA) para determinar la tendencia principal.
    Filtro Direccional: Solo operaremos a favor de esta línea.
    """
    return df['close'].ewm(span=period, adjust=False).mean()

def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calcula el Relative Strength Index (RSI) para medir el momentum.
    Ayuda a evitar comprar en "la cima" cuando el mercado está sobrecomprado.
    """
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50) # Neutro si no hay suficientes datos

def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calcula el Average Directional Index (ADX) para medir la fuerza de la tendencia.
    ADX > 25 indica tendencia fuerte. ADX < 25 indica mercado lateral.
    """
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    up_move = high - high.shift(1)
    down_move = low.shift(1) - low
    
    pos_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    neg_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    smoothed_tr = tr.ewm(alpha=1/period, adjust=False).mean()
    smoothed_pos_dm = pd.Series(pos_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean()
    smoothed_neg_dm = pd.Series(neg_dm, index=df.index).ewm(alpha=1/period, adjust=False).mean()
    
    pos_di = 100 * (smoothed_pos_dm / smoothed_tr)
    neg_di = 100 * (smoothed_neg_dm / smoothed_tr)
    
    dx = 100 * (abs(pos_di - neg_di) / (pos_di + neg_di))
    adx = dx.ewm(alpha=1/period, adjust=False).mean()
    
    return adx.fillna(0)

def generate_signals(df: pd.DataFrame, ema_window: int = 50, rsi_window: int = 14) -> pd.DataFrame:
    """
    Cerebro Institucional Opción C: Market Maker con Freno de Emergencia.
    Calcula volatilidad para el Grid Dinámico y detecta colapsos estructurales.
    """
    df = df.copy()
    
    # 1. Calculamos la volatilidad absoluta (ATR)
    df['atr'] = calculate_atr(df, 14)
    
    # 2. Grid Dinámico: Espaciado basado en Volatilidad (ATR / Precio)
    # Multiplicamos por 0.5 para que las trampas estén a media vela de distancia en promedio
    raw_grid_pct = (df['atr'] / df['close']) * 0.5
    # Limitamos mínimo 0.5% (garantiza ganancia tras Binance) y máximo 1.5%
    df['dynamic_grid_pct'] = raw_grid_pct.clip(lower=0.005, upper=0.015)
    
    # 3. Calculamos los indicadores de tendencia y régimen
    df['ema_50'] = calculate_ema(df, ema_window)
    df['rsi_14'] = calculate_rsi(df, rsi_window)
    df['adx_14'] = calculate_adx(df, 14)
    
    df['signal'] = 0
    
    # Iteramos a partir del periodo 50 para tener datos válidos
    for i in range(max(ema_window, rsi_window), len(df)):
        current_close = df.loc[i, 'close']
        current_ema = df.loc[i, 'ema_50']
        current_rsi = df.loc[i, 'rsi_14']
        current_adx = df.loc[i, 'adx_14']
        
        # --- LÓGICA DE RÉGIMEN HÍBRIDO ---
        # Freno con Histéresis: Solo aborta si cae un 0.3% por debajo de la EMA (Colchón) o RSI < 25
        if current_close < (current_ema * 0.997) or current_rsi < 25:
            df.loc[i, 'signal'] = -1  # ABORTAR / FRENO
            
        # Si estamos sobre la EMA (Tendencia alcista confirmada)
        elif current_close >= current_ema:
            if current_adx < 25:
                # Mercado Lateral o tendencia débil: MODO GRID
                df.loc[i, 'signal'] = 1
            else:
                # Tendencia Fuerte detectada: MODO TREND FOLLOWER
                df.loc[i, 'signal'] = 2
            
    return df

if __name__ == "__main__":
    print("Probando Cerebro de Tendencia (EMA + RSI)...")
    np.random.seed(42)
    precios = 100 + np.cumsum(np.random.normal(0.0, 1.0, 300))
    data = {
        "open_time": pd.date_range(start="2026-06-01", periods=300, freq="1H"),
        "open": precios - 0.5,
        "high": precios + 1.0,
        "low": precios - 1.0,
        "close": precios,
        "volume": np.random.uniform(10, 100, 300)
    }
    df_test = pd.DataFrame(data)
    df_signals = generate_signals(df_test)
    print(df_signals[["open_time", "close", "ema_50", "rsi_14", "atr", "signal"]].tail(10))
