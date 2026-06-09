import math
from binance.client import Client

def get_symbol_filters(client: Client, symbol: str) -> tuple[float, float, float]:
    """
    Obtiene las reglas de precisión (filtros) impuestas por Binance para el par.
    
    Retorna:
    - step_size: Incremento mínimo permitido para la cantidad (ej. 0.00001).
    - tick_size: Incremento mínimo permitido para el precio (ej. 0.01).
    - min_qty: Cantidad mínima permitida para una orden.
    """
    try:
        info = client.get_symbol_info(symbol)
        
        # 1. Obtener el filtro LOT_SIZE (Tamaño del Lote)
        lot_size_filter = next(f for f in info["filters"] if f["filterType"] == "LOT_SIZE")
        step_size = float(lot_size_filter["stepSize"])
        min_qty = float(lot_size_filter["minQty"])
        
        # 2. Obtener el filtro PRICE_FILTER (Filtro de Precio)
        price_filter = next(f for f in info["filters"] if f["filterType"] == "PRICE_FILTER")
        tick_size = float(price_filter["tickSize"])
        
        return step_size, tick_size, min_qty
    except Exception as e:
        print(f"Error al obtener los filtros del símbolo {symbol}: {e}")
        # Retornar valores por defecto conservadores
        return 0.00001, 0.01, 0.0001

def round_step(value: float, step: float) -> float:
    """
    Ajusta un valor numérico (precio o cantidad) a los decimales y saltos permitidos.
    
    Explicación matemática:
    Si la cantidad calculada de BTC es 0.01234567, pero el step_size de Binance es 0.001,
    intentar enviar 0.01234567 provocará un error de API (Filter LOT_SIZE).
    Esta función calcula los decimales correctos a partir del paso mínimo y redondea hacia abajo
    (para cantidad) o hacia el decimal exacto.
    """
    if step <= 0:
        return value
    # Calculamos el número de decimales mediante el logaritmo en base 10 del inverso del paso
    # Ej: 1 / 0.001 = 1000. log10(1000) = 3 decimales.
    precision = int(round(-math.log10(step)))
    if precision <= 0:
        return int(value)
    
    # Redondeamos al número de decimales calculado
    return round(value, precision)

def execute_buy_order(client: Client, symbol: str, quantity: float) -> dict | None:
    """
    Ejecuta una orden de compra a precio de mercado (MARKET) en la Testnet.
    """
    try:
        step_size, _, min_qty = get_symbol_filters(client, symbol)
        # Redondear la cantidad al formato de lote permitido
        rounded_qty = round_step(quantity, step_size)

        if rounded_qty < min_qty:
            print(f"Cantidad calculada ({rounded_qty}) es inferior al mínimo permitido ({min_qty}).")
            return None

        print(f"Enviando orden de COMPRA MERCADO: {rounded_qty} {symbol}")
        order = client.create_order(
            symbol=symbol,
            side=Client.SIDE_BUY,
            type=Client.ORDER_TYPE_MARKET,
            quantity=rounded_qty
        )
        return order
    except Exception as e:
        print(f"Error al ejecutar orden de compra: {e}")
        return None

def execute_stop_loss_order(
    client: Client,
    symbol: str,
    quantity: float,
    stop_price: float
) -> dict | None:
    """
    Crea una orden de protección de Stop-Loss de tipo STOP_LOSS_LIMIT.
    
    Explicación:
    Una orden STOP_LOSS_LIMIT se mantiene en espera en el libro de órdenes.
    - stopPrice: El precio gatillo. Si el precio de mercado baja a este nivel, la orden se activa.
    - price: El precio límite al que se enviará la orden de venta. 
      Establecemos el precio límite ligeramente inferior (ej. un 0.2% menos) que el stopPrice
      para asegurar que la orden se ejecute completamente aun si hay una caída muy rápida (deslizamiento).
    """
    try:
        step_size, tick_size, _ = get_symbol_filters(client, symbol)
        
        # Redondear cantidad y precios según los filtros de Binance
        rounded_qty = round_step(quantity, step_size)
        rounded_stop_price = round_step(stop_price, tick_size)
        # El precio de venta límite será un 0.2% inferior al de activación para garantizar ejecución
        limit_price = rounded_stop_price * 0.998
        rounded_limit_price = round_step(limit_price, tick_size)

        print(f"Estableciendo STOP_LOSS_LIMIT:")
        print(f"- Cantidad: {rounded_qty}")
        print(f"- Precio Gatillo (Stop): {rounded_stop_price}")
        print(f"- Precio Límite de Venta: {rounded_limit_price}")

        order = client.create_order(
            symbol=symbol,
            side=Client.SIDE_SELL,
            type=Client.ORDER_TYPE_STOP_LOSS_LIMIT,
            timeInForce=Client.TIME_IN_FORCE_GTC, # Good 'Til Cancelled
            quantity=rounded_qty,
            stopPrice=rounded_stop_price,
            price=rounded_limit_price
        )
        return order
    except Exception as e:
        print(f"Error al ejecutar orden de Stop-Loss: {e}")
        return None

def cancel_all_open_orders(client: Client, symbol: str):
    """
    Cancela todas las órdenes abiertas de un símbolo (por ejemplo,
    para limpiar órdenes Stop-Loss previas antes de enviar una nueva).
    """
    try:
        open_orders = client.get_open_orders(symbol=symbol)
        for order in open_orders:
            client.cancel_order(symbol=symbol, orderId=order["orderId"])
            print(f"Orden abierta cancelada: ID {order['orderId']}")
    except Exception as e:
        print(f"Error al cancelar órdenes abiertas: {e}")
