import os
import pandas as pd
import pandas_ta as ta
from oandapyV20 import API
from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.endpoints.orders import OrderCreate
from oandapyV20.endpoints.positions import PositionDetails
from oandapyV20.exceptions import V20Error
import time

# --- CONFIGURATION ---
OANDA_ACCESS_TOKEN = os.environ.get('OANDA_ACCESS_TOKEN')
OANDA_ACCOUNT_ID = os.environ.get('OANDA_ACCOUNT_ID')
OANDA_ENVIRONMENT = "live"

INSTRUMENT = "EUR_USD"
TIMEFRAME = "M5"
TRADE_SIZE = 600

# --- OANDA API INITIALIZATION ---
api = API(access_token=OANDA_ACCESS_TOKEN, environment=OANDA_ENVIRONMENT)

# --- INDICATOR & PATTERN LOGIC ---
def get_latest_data(count=100):
    """Fetches the latest candle data from OANDA."""
    params = {"count": count, "granularity": TIMEFRAME}
    r = InstrumentsCandles(instrument=INSTRUMENT, params=params)
    api.request(r)
    
    data = []
    for candle in r.response['candles']:
        data.append([candle['time'], float(candle['mid']['o']), float(candle['mid']['h']), float(candle['mid']['l']), float(candle['mid']['c']), candle['volume']])
    
    df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
    df['time'] = pd.to_datetime(df['time'])
    return df

def calculate_indicators(df):
    """Calculates all necessary indicators and adds them to the DataFrame."""
    df.ta.sma(length=20, append=True, col_names=('SMA_20',))
    df.ta.sma(length=50, append=True, col_names=('SMA_50',))
    df.ta.rsi(length=14, append=True, col_names=('RSI_14',))
    df.ta.atr(length=14, append=True, col_names=('ATR_14',))
    
    # DEFINITIVE FIX: Use the direct, correct function name
    df['engulfing'] = ta.cdl_engulfing(df['open'], df['high'], df['low'], df['close'])
        
    return df

# --- TRADE MANAGEMENT ---
def check_for_open_position():
    """Checks if there is an open position for the instrument."""
    r = PositionDetails(accountID=OANDA_ACCOUNT_ID, instrument=INSTRUMENT)
    try:
        api.request(r)
        if int(r.response['position']['long']['units']) != 0 or int(r.response['position']['short']['units']) != 0:
            return True
    except V20Error as e:
        if "404" in str(e): # No position exists for the instrument
            return False
    return False

def execute_trade(side):
    """Executes a trade with Stop Loss and Take Profit."""
    df = get_latest_data(count=15)
    atr = df.ta.atr(length=14).iloc[-1]
    
    stop_loss_distance = atr * 1.5
    take_profit_distance = stop_loss_distance * 2
    current_price = df['close'].iloc[-1]

    if side == 'BUY':
        sl_price = current_price - stop_loss_distance
        tp_price = current_price + take_profit_distance
        units = TRADE_SIZE
    else: # SELL
        sl_price = current_price + stop_loss_distance
        tp_price = current_price - take_profit_distance
        units = -TRADE_SIZE

    order_data = {
        "order": {
            "units": str(units),
            "instrument": INSTRUMENT,
            "type": "MARKET",
            "timeInForce": "FOK", # Fill Or Kill
            "positionFill": "DEFAULT",
            "takeProfitOnFill": {"price": f"{tp_price:.5f}"},
            "stopLossOnFill": {"price": f"{sl_price:.5f}"}
        }
    }
    r = OrderCreate(accountID=OANDA_ACCOUNT_ID, data=order_data)
    try:
        api.request(r)
        print(f"--- Trade Placed: {side} {INSTRUMENT} ---")
        print(f"Response: {r.response}")
    except V20Error as e:
        print(f"!!! Error placing trade: {e} !!!")
        print(f"Response details: {e.msg}")

# --- MAIN TRADING LOGIC ---
def run_bot():
    print(f"[{time.ctime()}] Running bot check...")
    
    if OANDA_ACCESS_TOKEN is None or OANDA_ACCOUNT_ID is None:
        print("!!! ERROR: OANDA credentials are not set in GitHub Secrets. Exiting. !!!")
        return

    if check_for_open_position():
        print("Position already open. Skipping check.")
        return

    df = get_latest_data()
    df = calculate_indicators(df)
    
    last = df.iloc[-2]

    is_bull_engulfing = last['engulfing'] > 0
    is_bear_engulfing = last['engulfing'] < 0
    
    buy_signal = last['SMA_20'] > last['SMA_50'] and last['RSI_14'] > 50 and is_bull_engulfing
    sell_signal = last['SMA_20'] < last['SMA_50'] and last['RSI_14'] < 50 and is_bear_engulfing
    
    if buy_signal:
        execute_trade('BUY')
    elif sell_signal:
        execute_trade('SELL')
    else:
        print("No signal found.")

# --- RUN THE BOT ---
if __name__ == "__main__":
    run_bot()
