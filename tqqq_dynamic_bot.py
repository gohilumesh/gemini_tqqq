import os
import alpaca_trade_api as tradeapi
from twilio.rest import Client
import yfinance as yf
import datetime
import pandas as pd


# 1. Try to get keys from GitHub Cloud first
API_KEY = os.getenv('ALPACA_API_KEY')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')

# 2. If not in the cloud (running locally), try to load from config.py
if not API_KEY:
    try:
        import config
        API_KEY = config.API_KEY
        SECRET_KEY = config.SECRET_KEY
    except ImportError:
        print("Error: No API keys found in Environment or config.py")
# --- SETTINGS ---
MY_PHONE = 'whatsapp:+14802891477'  # <--- UPDATE THIS
TW_SENDER = 'whatsapp:+14155238886' # Default Twilio Sandbox No.

# --- LOAD SECRETS ---
ALPACA_URL = 'https://paper-api.alpaca.markets' # Use 'https://api.alpaca.markets' for live

TW_SID = os.getenv('TWILIO_SID')
TW_TOKEN = os.getenv('TWILIO_TOKEN')
DYNAMIC_RALLY_THRESHOLD = 0.15      # 15% limit
# --- HELPERS ---
api = tradeapi.REST(API_KEY, SECRET_KEY, ALPACA_URL)

def send_alert(message):
    print(f"STDOUT: {message}")
    if TW_SID and TW_TOKEN:
        try:
            client = Client(TW_SID, TW_TOKEN)
            client.messages.create(body=message, from_=TW_SENDER, to=MY_PHONE)
        except Exception as e: print(f"WhatsApp Error: {e}")

def get_last_buy_info():
    """Finds the date and QQQ price of the last TQQQ buy order."""
    orders = api.list_orders(status='filled', limit=10, symbols=['TQQQ'], side='buy')
    if not orders:
        return None, None
    
    # Get date of last buy
    last_buy_date = orders[0].filled_at.date()
    
    # Get QQQ price on that specific date
    qqq_data = yf.download("QQQ", start=last_buy_date, end=last_buy_date + datetime.timedelta(days=1))
    if qqq_data.empty:
        return last_buy_date, None
    
    return last_buy_date, qqq_data['Close'].iloc[0]

def run_strategy():
    # 1. Get Market Data
    tqqq_data = yf.download("TQQQ", period="1y", interval="1d")
    curr_tqqq = tqqq_data['Close'].iloc[-1]
    sma200 = tqqq_data['Close'].rolling(window=200).mean().iloc[-1]
    
    # 2. Check Rally Guard (QQQ Change from Last Buy)
    last_date, last_qqq_price = get_last_buy_info()
    curr_qqq = yf.download("QQQ", period="1d")['Close'].iloc[-1]
    
    rally_triggered = False
    if last_qqq_price:
        perc_change = (curr_qqq - last_qqq_price) / last_qqq_price
        if perc_change > DYNAMIC_RALLY_THRESHOLD:
            rally_triggered = True
            send_alert(f"⚠️ RALLY GUARD: QQQ is {perc_change:.1%} higher since last buy. Skipping DCA.")

    # 3. Execution (Tuesday Only)
    if datetime.datetime.today().weekday() == 1 and not rally_triggered:
        amount = 1250
        if curr_tqqq < sma200:
            amount = 2500
            send_alert(f"🔥 DIP BUY: TQQQ below SMA200. Buying ${amount}.")
        else:
            send_alert(f"✅ TUESDAY DCA: Buying ${amount} TQQQ.")
        
        api.submit_order(symbol='TQQQ', notional=amount, side='buy', type='market', time_in_force='day')

    # 4. Rebalance (90/10) — Friday only, and only when market is green (TQQQ up for the day)
    try:
        today = datetime.datetime.today()
        is_friday = today.weekday() == 4
        # Green = most recent trading day closed higher than it opened
        recent = yf.download("TQQQ", period="5d", interval="1d", progress=False)
        market_green = recent['Close'].iloc[-1] > recent['Open'].iloc[-1] if len(recent) else False

        if is_friday and market_green:
            acct = api.get_account()
            total_val = float(acct.portfolio_value)
            pos = api.get_position('TQQQ')
            if float(pos.market_value) / total_val > 0.92:
                sell_amt = float(pos.market_value) - (total_val * 0.90)
                api.submit_order(symbol='TQQQ', notional=sell_amt, side='sell', type='market', time_in_force='day')
                send_alert(f"💰 HARVEST: Sold ${sell_amt:.2f} to refill cash (Friday, green day).")
        elif is_friday and not market_green:
            send_alert("📅 FRIDAY: Market red — skipping harvest. Will try next Friday.")
    except Exception as e:
        print(f"Rebalance check: {e}")

if __name__ == "__main__":
    run_strategy()
    