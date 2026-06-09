from binance.client import Client

def get_available_balance(client: Client, asset: str = "USDT") -> float:
    """
    Consulta la API de Binance para obtener el saldo disponible (libre)
    de un activo específico en la cuenta de la Testnet.
    """
    try:
        balance_info = client.get_asset_balance(asset=asset)
        if balance_info:
            return float(balance_info["free"])
        return 0.0
    except Exception as e:
        print(f"Error al obtener el saldo de {asset}: {e}")
        return 0.0

def calculate_auto_compounding_size(
    client: Client,
    symbol: str,
    entry_price: float,
    allocation_percentage: float = 0.05,
    stop_loss_percentage: float = 0.02
) -> tuple[float, float, float]:
    """
    Interés Compuesto Automático:
    En lugar de invertir siempre una cantidad fija, invierte un porcentaje (ej. 5%) 
    de todo el capital disponible en la cuenta.
    A medida que la cuenta crece, la posición crece exponencialmente.
    
    Retorna:
    - quantity: Cantidad de activo a comprar.
    - stop_loss_price: Precio de Stop Loss de seguridad.
    - position_size_usdt: Monto en USDT asignado a la posición (para registros).
    """
    # 1. Obtener el saldo disponible en USDT
    balance = get_available_balance(client, "USDT")
    if balance <= 0:
        print("Saldo en USDT insuficiente o igual a cero.")
        return 0.0, 0.0, 0.0

    # 2. Asignar el % del capital total para esta operación
    position_size_usdt = balance * allocation_percentage

    # 3. Restricción física: Dejamos un margen del 5% libre para comisiones
    max_allowed_usdt = balance * 0.95
    if position_size_usdt > max_allowed_usdt:
        position_size_usdt = max_allowed_usdt
        
    # Binance exige un mínimo de ~10 USDT para procesar una orden spot. Ponemos un margen de 11 USDT.
    if position_size_usdt < 11.0:
        print(f"[RIESGO] Asignación de {position_size_usdt:.2f} USDT es menor al mínimo de 11 USDT. Ignorando.")
        return 0.0, 0.0, 0.0

    # 4. Calcular la cantidad de tokens a comprar
    quantity = position_size_usdt / entry_price

    # 5. Calcular el precio exacto de Stop-Loss (abajo del precio de entrada por el porcentaje definido)
    stop_loss_price = entry_price * (1 - stop_loss_percentage)

    return quantity, stop_loss_price, position_size_usdt

# Bloque de prueba local
if __name__ == "__main__":
    # Mock de un cliente para pruebas locales sin conexión
    class MockClient:
        def get_asset_balance(self, asset):
            return {"asset": "USDT", "free": "1000.0", "locked": "0.0"}
            
    mock_client = MockClient()
    print("Simulando cálculo de riesgo...")
    qty, sl_price = calculate_position_size(
        client=mock_client,
        symbol="BTCUSDT",
        entry_price=50000.0,
        risk_percentage=0.01,         # 1% de riesgo de la cuenta ($10)
        stop_loss_percentage=0.02     # 2% de Stop-Loss ($1000 por debajo de la entrada)
    )
    
    print(f"Saldo simulación: 1000 USDT")
    print(f"Cantidad a comprar: {qty:.6f} unidades")
    print(f"Costo total estimado: {qty * 50000.0:.2f} USDT")
    print(f"Precio de entrada: 50000.0 USDT")
    print(f"Precio de Stop-Loss calculado (2% abajo): {sl_price:.2f} USDT")
    print(f"Pérdida si toca Stop-Loss: {(50000.0 - sl_price) * qty:.2f} USDT (debe ser aprox. 10.0 USDT)")
