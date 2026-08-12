"""
Mock MetaTrader5 module for Linux environments.
Provides stub functions to allow Engine_1.py to initialize without the Windows-only MT5 library.
"""

# Constants
TRADE_ACTION_DEAL = 5
ORDER_TYPE_BUY = 0
ORDER_TYPE_SELL = 1
ORDER_FILLING_IOC = 1

def initialize(*args, **kwargs):
    print("[MT5 Mock] initialize() called - returning True (dry run)")
    return True

def shutdown():
    print("[MT5 Mock] shutdown() called")
    return True

def account_info():
    class AccountInfo:
        balance = 10000.0
        equity = 10000.0
        margin = 0.0
        margin_free = 10000.0
        margin_level = 0.0
        profit = 0.0
        currency = "USD"
        server = "MockServer"
        login = 12345678
        name = "Mock Account"
    return AccountInfo()

def symbol_info(symbol):
    class SymbolInfo:
        point = 0.00001
        digits = 5
        trade_contract_size = 100000
        volume_min = 0.01
        volume_max = 100.0
        volume_step = 0.01
    return SymbolInfo()

def symbol_info_tick(symbol):
    class Tick:
        bid = 1.0
        ask = 1.0001
        last = 1.0
        time = 0
    return Tick()

def order_send(request):
    class OrderResult:
        retcode = 10009  # TRADE_RETCODE_DONE
        deal = 12345
        order = 67890
        comment = "Mock order"
    print(f"[MT5 Mock] order_send() called - returning mock result")
    return OrderResult()

def positions_get(*args, **kwargs):
    return []

def orders_get(*args, **kwargs):
    return []

def history_deals_get(*args, **kwargs):
    return []

def copy_rates_from_pos(symbol, timeframe, start_pos, count):
    import numpy as np
    # Return mock OHLCV data
    return np.zeros(count, dtype=[
        ('time', 'i8'), ('open', 'f8'), ('high', 'f8'), 
        ('low', 'f8'), ('close', 'f8'), ('tick_volume', 'i8'),
        ('spread', 'i4'), ('real_volume', 'i8')
    ])
