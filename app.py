import os
import json
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from data_provider import get_latest_klines
from strategy import generate_signals
from config import get_binance_client
import traceback
from binance.client import Client

app = Flask(__name__, static_folder='static', static_url_path='/static')
CORS(app)

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/api/portfolio', methods=['GET'])
def portfolio():
    try:
        # La billetera sí usa el cliente privado (Testnet o Mainnet según el .env)
        client = get_binance_client()
        account = client.get_account()
        # Mostrar únicamente USDT y BTC para evitar ruido de Testnet
        balances = [b for b in account['balances'] if b['asset'] in ['USDT', 'BTC'] and (float(b['free']) > 0 or float(b['locked']) > 0)]
        return jsonify({'success': True, 'balances': balances})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/grid_state', methods=['GET'])
def grid_state():
    try:
        if os.path.exists("grid_state.json"):
            with open("grid_state.json", "r") as f:
                state = json.load(f)
            return jsonify({'success': True, 'state': state})
        return jsonify({'success': False, 'error': 'Grid no inicializado'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/toggle_bot', methods=['POST'])
def toggle_bot():
    try:
        if os.path.exists("grid_state.json"):
            with open("grid_state.json", "r") as f:
                state = json.load(f)
            
            state["is_running"] = not state.get("is_running", True)
            
            with open("grid_state.json", "w") as f:
                json.dump(state, f, indent=4)
                
            return jsonify({'success': True, 'is_running': state["is_running"]})
        return jsonify({'success': False, 'error': 'Grid no inicializado'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/market', methods=['GET'])
def market_data():
    symbol = request.args.get('symbol', 'BTCUSDT')
    interval = request.args.get('interval', '1m')
    
    if interval in ['1m', '15m']:
        limit = 2000 
    elif interval in ['1h', '4h']:
        limit = 5000
    else:
        limit = 10000

    try:
        df = get_latest_klines(symbol, interval, limit=limit)
        
        # Calcular EMA 20 y RSI 14 locales para el visualizador
        df['ema'] = df['close'].ewm(span=20, adjust=False).mean()
        
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        rs = avg_gain / avg_loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        df = df.dropna(subset=['ema', 'rsi', 'close'])
        df['time'] = (df['open_time'].astype('int64') // 10**9).astype(int)
        
        candles = df[['time', 'open', 'high', 'low', 'close']].to_dict(orient='records')
        ema = df[['time', 'ema']].rename(columns={'ema': 'value'}).to_dict(orient='records')
        rsi = df[['time', 'rsi']].rename(columns={'rsi': 'value'}).to_dict(orient='records')
        
        # Como ya no usamos señales direccionales puras en el visualizador base, omitimos los markers
        # Las lineas de Grid ya se envian desde /api/grid_state al frontend.
        markers = []
                
        candles = sorted(candles, key=lambda x: x['time'])
        ema = sorted(ema, key=lambda x: x['time'])
        rsi = sorted(rsi, key=lambda x: x['time'])
                
        return jsonify({
            'success': True,
            'data': {
                'candles': candles,
                'ema': ema,
                'rsi': rsi,
                'markers': markers,
                'current_price': candles[-1]['close'] if candles else 0
            }
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    print("Iniciando Dashboard Híbrido (Precios Reales / Dinero Falso) en http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
