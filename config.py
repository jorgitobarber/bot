import os
from dotenv import load_dotenv
from binance.client import Client

# Carga las variables desde el archivo .env a la memoria del sistema
load_dotenv()

def get_binance_client() -> Client:
    """
    Cliente PRIVADO para Ejecución y Billetera.
    Decide a qué red conectarse (Testnet o Mainnet) para operar.
    """
    use_real_money_str = os.getenv("USE_REAL_MONEY", "False")
    use_real_money = use_real_money_str.strip().lower() == "true"
    
    if use_real_money:
        # MODO DINERO REAL (MAINNET)
        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_SECRET_KEY")
        if not api_key or not api_secret or api_key == "tu_api_key_real_aqui":
            raise ValueError("ERROR DE SEGURIDAD: Faltan las claves reales en .env")
        print("[!!!] ATENCION: CONECTADO A BINANCE MAINNET (EJECUCION REAL) [!!!]")
        return Client(api_key, api_secret, testnet=False)
    else:
        # MODO SIMULACION (TESTNET)
        api_key = os.getenv("BINANCE_TESTNET_API_KEY")
        api_secret = os.getenv("BINANCE_TESTNET_SECRET_KEY")
        print("[i] Conectado a Binance Testnet (Ejecucion Simulada)")
        return Client(api_key, api_secret, testnet=True)

def get_public_mainnet_client() -> Client:
    """
    Cliente PUBLICO exclusivo para Lectura de Datos.
    Siempre se conecta a la Mainnet de Binance para obtener los precios
    y la historia REAL del mercado, sin requerir claves de API.
    """
    return Client(testnet=False)
