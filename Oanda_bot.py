import os
import pandas as pd
import pandas_ta as ta
from oandapyV20 import API
from oandapyV20.endpoints.pricing import PricingStream
from oandapyV20.endpoints.accounts import AccountDetails
from oandapyV20.endpoints.orders import OrderCreate
from oandapyV20.endpoints.positions import PositionDetails, PositionClose
from oandapyV20.exceptions import V20Error
import time

# --- CONFIGURATION ---
OANDA_ACCESS_TOKEN = "bb44e33b0520c7d68d7e8feb713abebf-f2dcfa5e713109fb29dbed4065f4df17"
OANDA_ACCOUNT_ID = "001-004-9227373-001"
# Use 'practice' for a demo account or 'live' for a real account
OANDA_ENVIRONMENT = "live" 

# Strategy Settings
INSTRUMENT = "EUR_USD"
TIMEFRAME = "M5"  # 5-minute candles
TRADE_SIZE = 1000 # Number of units to trade

# --- OANDA API INITIALIZATION ---
api = API(access_token=OANDA_ACCESS_TOKEN, environment=OANDA_ENVIRONMENT)

# --- INDICATOR & PATTERN LOGIC ---
def get_latest_data(count=100):
    """Fetches the latest candle data from OANDA."""
    params = {"count": count, "granularity": TIMEFRAME}
    r = oandapyV20.endpoints.instruments.InstrumentsCandles(instrument=INSTRUMENT, params=params)
    api.request(r)
    
    data = []
    for candle in r.response['candles']:
        data.append([candle['time'], candle['mid']['o'], candle['mid']['h'], candle['mid']['l'], candle['mid']['c'], candle['volume']])
    
    df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
    df['time'] = pd.to_datetime(df['time'])
    return df

def calculate_indicators(df):
    """Calculates all necessary indicators and adds them to the DataFrame."""
    df.ta.sma(length=20, append=True)
    df.ta.sma(length=50, append=True)
    df.ta.rsi(length=14, append=True)
    df.ta.atr(length=14, append=True)
    # Candlestick Pattern Detection (simplified)
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
        # No position exists
        if e.code == 404:
            return False
    return False

def execute_trade(side):
    """Executes a trade with Stop Loss and Take Profit."""
    df = get_latest_data(count=2)
    atr = ta.atr(df['high'], df['low'], df['close'], length=14).iloc[-1]
    
    stop_loss_pips = (atr * 1.5) / 0.0001 # Convert ATR to pips for EUR_USD
    take_profit_pips = stop_loss_pips * 2

    current_price = df['close'].iloc[-1]

    if side == 'BUY':
        sl_price = current_price - (stop_loss_pips * 0.0001)
        tp_price = current_price + (take_profit_pips * 0.0001)
        units = TRADE_SIZE
    else: # SELL
        sl_price = current_price + (stop_loss_pips * 0.0001)
        tp_price = current_price - (take_profit_pips * 0.0001)
        units = -TRADE_SIZE

    order_data = {
        "order": {
            "units": str(units),
            "instrument": INSTRUMENT,
            "marketIfTouchedOrderType": "MARKET",
            "timeInForce": "FOK",
            "positionFill": "DEFAULT",
            "takeProfitOnFill": {
                "price": f"{tp_price:.5f}"
            },
            "stopLossOnFill": {
                "price": f"{sl_price:.5f}"
            }
        }
    }
    r = OrderCreate(accountID=OANDA_ACCOUNT_ID, data=order_data)
    api.request(r)
    print(f"--- Trade Placed: {side} {INSTRUMENT} ---")

# --- MAIN TRADING LOGIC ---
def run_bot():
    print(f"Running bot check at {time.ctime()}...")
    
    if check_for_open_position():
        print("Position already open. Skipping check.")
        return

    df = get_latest_data()
    df = calculate_indicators(df)
    
    # Get the latest completed candle's data
    last = df.iloc[-2]

    # --- CHECKING TRADE CONDITIONS ---
    is_bull_engulfing = last['CDL_ENGULFING'] > 0
    is_bear_engulfing = last['CDL_ENGULFING'] < 0
    
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
