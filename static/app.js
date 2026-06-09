// ============================================================
// Dashboard Cuantitativo - app.js
// Compatible con Lightweight Charts v5
// ============================================================

const priceContainer = document.getElementById('priceChartContainer');
const rsiContainer = document.getElementById('rsiChartContainer');

// --- Gráfico Principal (Velas + EMA) ---
const mainChart = LightweightCharts.createChart(priceContainer, {
    layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#94a3b8' },
    grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.05)' }
    },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    timeScale: { timeVisible: true, secondsVisible: false },
    rightPriceScale: { borderColor: 'rgba(255, 255, 255, 0.1)' }
});

// API v5: addSeries(TipoSerie, opciones)
const candleSeries = mainChart.addSeries(LightweightCharts.CandlestickSeries, {
    upColor: '#00ff88',
    downColor: '#ff0055',
    borderDownColor: '#ff0055',
    borderUpColor: '#00ff88',
    wickDownColor: '#ff0055',
    wickUpColor: '#00ff88',
});

const emaSeries = mainChart.addSeries(LightweightCharts.LineSeries, {
    color: '#3b82f6',
    lineWidth: 2,
    crosshairMarkerVisible: false,
    lastValueVisible: false,
    priceLineVisible: false,
});

// --- Gráfico RSI ---
const rsiChart = LightweightCharts.createChart(rsiContainer, {
    layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#94a3b8' },
    grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.05)' }
    },
    timeScale: { timeVisible: true },
    rightPriceScale: { borderColor: 'rgba(255, 255, 255, 0.1)' }
});

const rsiSeries = rsiChart.addSeries(LightweightCharts.LineSeries, {
    color: '#a855f7',
    lineWidth: 2,
});

// Líneas de sobrecompra/sobreventa
rsiSeries.createPriceLine({
    price: 70, color: '#ff0055', lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed,
    axisLabelVisible: true, title: 'Sobrecompra'
});
rsiSeries.createPriceLine({
    price: 30, color: '#00ff88', lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed,
    axisLabelVisible: true, title: 'Sobreventa'
});

// Sincronizar escalas de tiempo entre ambos gráficos
mainChart.timeScale().subscribeVisibleTimeRangeChange(range => {
    if (range) rsiChart.timeScale().setVisibleRange(range);
});
rsiChart.timeScale().subscribeVisibleTimeRangeChange(range => {
    if (range) mainChart.timeScale().setVisibleRange(range);
});

// Responsividad
function resizeCharts() {
    mainChart.applyOptions({ width: priceContainer.clientWidth, height: priceContainer.clientHeight });
    rsiChart.applyOptions({ width: rsiContainer.clientWidth, height: rsiContainer.clientHeight });
}
window.addEventListener('resize', resizeCharts);
setTimeout(resizeCharts, 150);

// ============================================================
// Lógica de Consumo de API
// ============================================================
async function fetchMarketData() {
    const symbol = document.getElementById('symbolSelect').value;
    const interval = document.getElementById('intervalSelect').value;

    try {
        const res = await fetch('/api/market?symbol=' + symbol + '&interval=' + interval + '&limit=150');
        const result = await res.json();

        if (result.success) {
            const d = result.data;
            candleSeries.setData(d.candles);
            emaSeries.setData(d.ema);
            rsiSeries.setData(d.rsi);
        } else {
            console.error('Error API:', result.error);
        }
    } catch (err) {
        console.error('fetchMarketData error:', err);
    }
}

async function fetchPortfolio() {
    const list = document.getElementById('portfolioList');
    try {
        const res = await fetch('/api/portfolio');
        const result = await res.json();
        if (result.success) {
            list.innerHTML = '';
            if (result.balances.length === 0) {
                list.innerHTML = '<li>Sin fondos</li>';
                return;
            }
            result.balances.forEach(b => {
                const li = document.createElement('li');
                li.innerHTML = '<span>' + b.asset + '</span><span style="color:#00ff88">' + parseFloat(b.free).toFixed(4) + '</span>';
                list.appendChild(li);
            });
        } else {
            list.innerHTML = '<li style="color:#ff0055">Error: ' + result.error + '</li>';
        }
    } catch (e) {
        list.innerHTML = '<li style="color:#ff0055">Sin conexión</li>';
        console.error('fetchPortfolio error:', e);
    }
}

// Global array to store Grid Price Lines so we can remove/update them
let gridLines = [];

async function fetchGridState() {
    try {
        const res = await fetch('/api/grid_state');
        const result = await res.json();
        const btn = document.getElementById('toggleBotBtn');
        const boughtCountEl = document.getElementById('gridBoughtCount');
        const profitEl = document.getElementById('gridProfit');
        
        if (result.success) {
            const state = result.state;
            
            const basePriceEl = document.getElementById('basePrice');
            if (basePriceEl && state.base_price) {
                basePriceEl.style.color = '#f8fafc';
                basePriceEl.style.fontSize = '2rem';
                basePriceEl.innerText = '$ ' + state.base_price.toLocaleString('en-US', { minimumFractionDigits: 2 });
            }
            
            if (state.is_running) {
                btn.innerText = 'Apagar Bot';
                btn.style.background = '#ff0055';
            } else {
                btn.innerText = 'Encender Bot';
                btn.style.background = '#3b82f6';
            }
            
            let boughtCount = 0;
            let totalInvested = 0.0;
            if (state.hold_position) {
                totalInvested += state.hold_position.usdt_allocated || 0;
            }
            
            // Limpiar líneas anteriores
            gridLines.forEach(line => candleSeries.removePriceLine(line));
            gridLines = [];
            
            const openOrdersList = document.getElementById('openOrdersList');
            if(openOrdersList) openOrdersList.innerHTML = '';

            state.grids.forEach(g => {
                let li = document.createElement('li');
                li.style.marginBottom = '2px';
                if (g.status === "WAITING_SELL") {
                    boughtCount++;
                    totalInvested += g.alloc_usdt || (g.btc_qty * g.buy_price) || 11.8;
                    // Línea de Take Profit
                    const line = candleSeries.createPriceLine({
                        price: g.sell_price, color: '#00ff88', lineWidth: 1,
                        lineStyle: LightweightCharts.LineStyle.Dotted,
                        axisLabelVisible: true
                    });
                    gridLines.push(line);
                    li.innerHTML = `<span style="color:#00ff88">VENTA</span> en $${g.sell_price.toFixed(2)}`;
                } else {
                    // Línea de Compra
                    const line = candleSeries.createPriceLine({
                        price: g.buy_price, color: '#3b82f6', lineWidth: 1,
                        lineStyle: LightweightCharts.LineStyle.Dotted,
                        axisLabelVisible: true
                    });
                    gridLines.push(line);
                    li.innerHTML = `<span style="color:#3b82f6">COMPRA</span> en $${g.buy_price.toFixed(2)}`;
                }
                if(openOrdersList) openOrdersList.appendChild(li);
            });
            
            boughtCountEl.innerText = boughtCount;
            const investedEl = document.getElementById('gridInvested');
            if (investedEl) investedEl.innerText = '$ ' + totalInvested.toFixed(2);
            profitEl.innerText = '$ ' + state.total_profit.toFixed(2);
            
            // Render History
            const historyList = document.getElementById('tradeHistoryList');
            if (state.history && state.history.length > 0) {
                historyList.innerHTML = '';
                state.history.forEach(trade => {
                    const li = document.createElement('li');
                    li.style.marginBottom = '5px';
                    li.style.borderBottom = '1px solid rgba(255,255,255,0.05)';
                    li.style.paddingBottom = '3px';
                    
                    const timeSpan = `<span style="color:#64748b">${trade.time}</span>`;
                    const typeSpan = trade.type.includes('COMPRA') ? `<span style="color:#3b82f6">COMPRA</span>` : `<span style="color:#a855f7">VENTA</span>`;
                    const priceSpan = `<span>$${trade.price.toFixed(2)}</span>`;
                    const profitSpan = trade.profit > 0 ? `<br><span style="color:#00ff88">Beneficio: +$${trade.profit.toFixed(3)}</span>` : '';
                    const buySpan = trade.buy_price > 0 ? `<br><span style="color:#64748b">Comprado en: $${trade.buy_price.toFixed(2)}</span>` : '';
                    
                    li.innerHTML = `${timeSpan} ${typeSpan} @ ${priceSpan} ${buySpan} ${profitSpan}`;
                    historyList.appendChild(li);
                });
            } else {
                historyList.innerHTML = '<li>Sin operaciones recientes</li>';
            }
        }
    } catch (e) {
        console.error('fetchGridState error:', e);
    }
}

document.getElementById('toggleBotBtn').addEventListener('click', async () => {
    try {
        await fetch('/api/toggle_bot', {method: 'POST'});
        fetchGridState();
    } catch (e) {
        console.error('toggleBot error:', e);
    }
});

// Eventos de cambio de moneda / temporalidad
document.getElementById('symbolSelect').addEventListener('change', fetchMarketData);
document.getElementById('intervalSelect').addEventListener('change', fetchMarketData);

// Arrancar todo
fetchMarketData();
fetchPortfolio();
fetchGridState();
setInterval(fetchMarketData, 5000);
setInterval(fetchPortfolio, 10000);
setInterval(fetchGridState, 3000);
