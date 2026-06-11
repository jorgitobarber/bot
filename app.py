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
        # Billetera Virtual (Paper Trading Realista)
        total_equity = 118.0
        invested_usdt = 0.0
        btc_balance = 0.0
        sol_balance = 0.0
        
        for symbol in ["BTCUSDT", "SOLUSDT"]:
            state_file = f"grid_state_{symbol}.json"
            if os.path.exists(state_file):
                with open(state_file, "r") as f:
                    state = json.load(f)
                    
                total_equity += state.get("total_profit", 0.0)
                
                trend = state.get("trend_position")
                if trend:
                    qty = trend.get("qty", 0.0)
                    invested_usdt += qty * trend.get("buy_price", 0.0)
                    if symbol == "BTCUSDT": btc_balance += qty
                    if symbol == "SOLUSDT": sol_balance += qty
                    
                for g in state.get("grids", []):
                    if g.get("status") == "WAITING_SELL":
                        qty = g.get("btc_qty", 0.0)
                        invested_usdt += qty * g.get("buy_price", 0.0)
                        if symbol == "BTCUSDT": btc_balance += qty
                        if symbol == "SOLUSDT": sol_balance += qty
        
        free_usdt = total_equity - invested_usdt
        
        balances = [
            {"asset": "USDT", "free": f"{free_usdt:.2f}"},
            {"asset": "BTC", "free": f"{btc_balance:.4f}"},
            {"asset": "SOL", "free": f"{sol_balance:.4f}"}
        ]
        return jsonify({'success': True, 'balances': balances})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/grid_state', methods=['GET'])
def grid_state():
    try:
        symbol = request.args.get('symbol', 'BTCUSDT')
        state_file = f"grid_state_{symbol}.json"
        if os.path.exists(state_file):
            with open(state_file, "r") as f:
                state = json.load(f)
            return jsonify({'success': True, 'state': state})
        return jsonify({'success': False, 'error': f'Grid no inicializado para {symbol}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/toggle_bot', methods=['POST'])
def toggle_bot():
    try:
        symbol = request.json.get('symbol', 'BTCUSDT') if request.is_json else request.args.get('symbol', 'BTCUSDT')
        state_file = f"grid_state_{symbol}.json"
        if os.path.exists(state_file):
            with open(state_file, "r") as f:
                state = json.load(f)
            
            state["is_running"] = not state.get("is_running", True)
            
            with open(state_file, "w") as f:
                json.dump(state, f, indent=4)
                
            return jsonify({'success': True, 'is_running': state["is_running"]})
        return jsonify({'success': False, 'error': f'Grid no inicializado para {symbol}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/market', methods=['GET'])
def market_data():
    symbol = request.args.get('symbol', 'BTCUSDT')
    interval = request.args.get('interval', '1m')
    
    # Usar el parámetro de límite (por defecto 200 velas, suficientes para la EMA 50)
    # Esto hace que la recarga de la página sea ultra rápida y sin lag
    try:
        limit = int(request.args.get('limit', 200))
    except ValueError:
        limit = 200

    try:
        df = get_latest_klines(symbol, interval, limit=limit)
        
        # Calcular EMA 50 y RSI 14 locales para el visualizador
        df['ema'] = df['close'].ewm(span=50, adjust=False).mean()
        
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
        rs = avg_gain / avg_loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        import numpy as np
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
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
