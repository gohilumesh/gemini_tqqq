import os
import argparse
import alpaca_trade_api as tradeapi
from twilio.rest import Client
import yfinance as yf
import datetime
import pandas as pd

parser = argparse.ArgumentParser(description='TQQQ Dynamic DCA bot')
parser.add_argument('--dry-run', action='store_true', help='Simulate only: no orders, no WhatsApp')
parser.add_argument('--day', choices=('tue', 'fri'), help='Simulate as Tuesday or Friday')
parser.add_argument('--test', action='store_true', help='Test Alpaca connection + send one WhatsApp message')
args = parser.parse_args()
DRY_RUN = args.dry_run
SIMULATE_DAY = args.day
TEST_MODE = args.test

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
        if not DRY_RUN:
            print("Error: No API keys found in Environment or config.py")
# --- SETTINGS ---
MY_PHONE = 'whatsapp:+14802891477'  # <--- UPDATE THIS
TW_SENDER = 'whatsapp:+14155238886' # Default Twilio Sandbox No.

# --- LOAD SECRETS ---
ALPACA_URL = 'https://paper-api.alpaca.markets' # Use 'https://api.alpaca.markets' for live

TW_SID = os.getenv('TWILIO_SID')
TW_TOKEN = os.getenv('TWILIO_TOKEN')
if not TW_SID or not TW_TOKEN:
    try:
        import config
        TW_SID = getattr(config, 'TWILIO_SID', None) or TW_SID
        TW_TOKEN = getattr(config, 'TWILIO_TOKEN', None) or TW_TOKEN
    except ImportError:
        pass
DYNAMIC_RALLY_THRESHOLD = 0.15      # 15% limit
# --- HELPERS ---
# alpaca-trade-api reads APCA_* env vars; set them so the library finds credentials (e.g. in GitHub Actions)
if API_KEY and SECRET_KEY:
    os.environ['APCA_API_KEY_ID'] = API_KEY
    os.environ['APCA_API_SECRET_KEY'] = SECRET_KEY
    os.environ['APCA_API_BASE_URL'] = ALPACA_URL
api = tradeapi.REST(API_KEY, SECRET_KEY, ALPACA_URL) if (API_KEY and SECRET_KEY) else None

def send_alert(message):
    print(f"STDOUT: {message}")
    if DRY_RUN:
        return
    if TW_SID and TW_TOKEN:
        try:
            client = Client(TW_SID, TW_TOKEN)
            client.messages.create(body=message, from_=TW_SENDER, to=MY_PHONE)
        except Exception as e: print(f"WhatsApp Error: {e}")

def get_last_buy_info():
    """Finds the date and QQQ price of the last TQQQ buy order."""
    if not api:
        return None, None
    orders = api.list_orders(status='filled', limit=10, symbols=['TQQQ'], side='buy')
    if not orders:
        return None, None
    
    # Get date of last buy
    last_buy_date = orders[0].filled_at.date()
    
    # Get QQQ price on that specific date
    qqq_data = yf.download("QQQ", start=last_buy_date, end=last_buy_date + datetime.timedelta(days=1), progress=False)
    if qqq_data.empty:
        return last_buy_date, None
    return last_buy_date, float(pd.Series(qqq_data['Close'].iloc[0]).squeeze())

def run_strategy():
    # Simulated day for local testing (--day tue | --day fri)
    if SIMULATE_DAY == 'tue':
        effective_weekday = 1
    elif SIMULATE_DAY == 'fri':
        effective_weekday = 4
    else:
        effective_weekday = datetime.datetime.today().weekday()

    if DRY_RUN:
        day_name = {1: 'Tuesday', 4: 'Friday'}.get(effective_weekday, 'other')
        print("\n=== DRY RUN (no orders, no WhatsApp) ===\n"
              f"Simulated day: {day_name} (weekday={effective_weekday})\n")

    # 1. Get Market Data (squeeze to scalar if yfinance returns Series)
    tqqq_data = yf.download("TQQQ", period="1y", interval="1d", progress=False)
    if tqqq_data.columns.nlevels > 1:
        tqqq_data.columns = tqqq_data.columns.get_level_values(0)
    curr_tqqq = float(tqqq_data['Close'].iloc[-1])
    sma200 = float(tqqq_data['Close'].rolling(window=200).mean().iloc[-1])
    print(f"TQQQ: ${curr_tqqq:.2f}  |  SMA200: ${sma200:.2f}  |  Below SMA200: {curr_tqqq < sma200}")

    # 2. Check Rally Guard (QQQ Change from Last Buy)
    last_date, last_qqq_price = get_last_buy_info()
    qqq_1d = yf.download("QQQ", period="1d", progress=False)
    if qqq_1d.columns.nlevels > 1:
        qqq_1d.columns = qqq_1d.columns.get_level_values(0)
    curr_qqq = float(qqq_1d['Close'].iloc[-1])
    if last_date:
        print(f"Last TQQQ buy: {last_date}  |  QQQ then: ${last_qqq_price:.2f}  |  QQQ now: ${curr_qqq:.2f}")

    rally_triggered = False
    if last_qqq_price:
        perc_change = (curr_qqq - last_qqq_price) / last_qqq_price
        if perc_change > DYNAMIC_RALLY_THRESHOLD:
            rally_triggered = True
            send_alert(f"⚠️ RALLY GUARD: QQQ is {perc_change:.1%} higher since last buy. Skipping DCA.")
            print(f"Rally guard: QQQ +{perc_change:.1%} since last buy → skip DCA")
    if not rally_triggered and last_qqq_price:
        print(f"Rally guard: QQQ +{(curr_qqq - last_qqq_price) / last_qqq_price:.1%} (under {DYNAMIC_RALLY_THRESHOLD:.0%}) → DCA allowed")

    # 3. Execution (Tuesday Only)
    if effective_weekday == 1 and not rally_triggered:
        amount = 2500 if curr_tqqq < sma200 else 1250
        if curr_tqqq < sma200:
            send_alert(f"🔥 DIP BUY: TQQQ below SMA200. Buying ${amount}.")
            if DRY_RUN:
                print(f"[DRY RUN] Would DIP BUY: ${amount} TQQQ (below SMA200)")
        else:
            send_alert(f"✅ TUESDAY DCA: Buying ${amount} TQQQ.")
            if DRY_RUN:
                print(f"[DRY RUN] Would DCA BUY: ${amount} TQQQ")
        if not DRY_RUN and api:
            api.submit_order(symbol='TQQQ', notional=amount, side='buy', type='market', time_in_force='day')
        elif DRY_RUN:
            print(f"  → Order NOT sent (dry run)\n")
    elif effective_weekday == 1 and rally_triggered:
        print("Tuesday: Rally guard active — no buy.\n")
    elif effective_weekday != 1:
        print(f"Not Tuesday (weekday={effective_weekday}) — no DCA buy.\n")

    # 4. Rebalance (90/10) — Friday only, and only when market is green (TQQQ up for the day)
    try:
        is_friday = effective_weekday == 4
        recent = yf.download("TQQQ", period="5d", interval="1d", progress=False)
        if len(recent) and recent.columns.nlevels > 1:
            recent.columns = recent.columns.get_level_values(0)
        market_green = (float(recent['Close'].iloc[-1]) > float(recent['Open'].iloc[-1])) if len(recent) else False
        print(f"Friday: {is_friday}  |  Market green (TQQQ close > open): {market_green}")

        if is_friday and market_green and api:
            acct = api.get_account()
            total_val = float(acct.portfolio_value)
            pos = api.get_position('TQQQ')
            tqqq_pct = float(pos.market_value) / total_val if total_val else 0
            if tqqq_pct > 0.92:
                sell_amt = float(pos.market_value) - (total_val * 0.90)
                send_alert(f"💰 HARVEST: Sold ${sell_amt:.2f} to refill cash (Friday, green day).")
                if DRY_RUN:
                    print(f"[DRY RUN] Would HARVEST: sell ${sell_amt:.2f} TQQQ (portfolio {tqqq_pct:.1%} > 92%)")
                    print("  → Order NOT sent (dry run)\n")
                else:
                    api.submit_order(symbol='TQQQ', notional=sell_amt, side='sell', type='market', time_in_force='day')
            else:
                print(f"TQQQ at {tqqq_pct:.1%} of portfolio (≤92%) — no harvest.\n")
        elif is_friday and market_green and not api:
            print("[DRY RUN] Would run harvest check (Friday, green). No API — cannot show portfolio.\n")
        elif is_friday and not market_green:
            send_alert("📅 FRIDAY: Market red — skipping harvest. Will try next Friday.")
            print("Friday but market red — skipping harvest.\n")
        elif not is_friday:
            print("Not Friday — no harvest check.\n")
    except Exception as e:
        print(f"Rebalance check: {e}")

    if DRY_RUN:
        print("=== END DRY RUN ===\n")

def run_test():
    """Verify Alpaca connection and send one WhatsApp message."""
    print("Testing Alpaca + WhatsApp...\n")
    # 1. Alpaca
    if not api:
        print("ALPACA: No API keys (set ALPACA_API_KEY / ALPACA_SECRET_KEY or config.py).")
    else:
        try:
            acct = api.get_account()
            clock = api.get_clock()
            print(f"ALPACA: Connected (paper trading). Account status: {acct.status}")
            print(f"  Portfolio value: ${float(acct.portfolio_value):,.2f}")
            print(f"  Market open: {clock.is_open}\n")
        except Exception as e:
            print(f"ALPACA: Error — {e}\n")
    # 2. WhatsApp
    if not TW_SID or not TW_TOKEN:
        print("WHATSAPP: No Twilio credentials (set TWILIO_SID / TWILIO_TOKEN or in config.py).")
        return
    try:
        client = Client(TW_SID, TW_TOKEN)
        msg = "TQQQ bot test: Alpaca connected. WhatsApp works."
        client.messages.create(body=msg, from_=TW_SENDER, to=MY_PHONE)
        print("WHATSAPP: One test message sent to", MY_PHONE)
    except Exception as e:
        print(f"WHATSAPP: Error — {e}")

if __name__ == "__main__":
    if TEST_MODE:
        run_test()
    else:
        run_strategy()
    