# TQQQ Dynamic DCA & 90/10 Rebalance Bot

An automated trading bot designed for long-term TQQQ (3x Leveraged Nasdaq-100) investing. This bot executes a disciplined, emotion-free strategy using **Weekly DCA**, **Dynamic Dip Buying**, and **Automatic Profit Harvesting**.

## 📈 The Strategy
This bot automates a "Self-Refilling" 90/10 portfolio:
* **Target Allocation:** 90% TQQQ / 10% Cash reserve.
* **Weekly DCA:** Invests **$1,250 every Tuesday** at 11:00 AM EST (1.5 hours after market open to avoid morning volatility).
* **Dynamic Dip Buying:** If TQQQ drops below its **200-day Moving Average (SMA200)**, the bot automatically doubles the weekly buy to **$2,500**.
* **Profit Harvesting:** If TQQQ exceeds 92% of the portfolio or nears its 52-week high, the bot sells the excess to refill the 10% cash reserve for future dips.

## 🛠 Tech Stack
* **Language:** Python 3.10+
* **Broker API:** [Alpaca Markets](https://alpaca.markets/) (Supports fractional shares)
* **Alerts:** [Twilio WhatsApp API](https://www.twilio.com/en-us/messaging/whatsapp) (Optional)
* **Automation:** GitHub Actions (Runs for free in the cloud)

## 📁 Project Structure
```text
.
├── .github/workflows/
│   └── tuesday_trade.yml    # GitHub Actions Schedule (Tuesday 11:00 AM EST)
├── tqqq_dynamic_bot.py      # Core Trading Logic
├── requirements.txt         # Required Python Libraries
└── README.md                # Project Documentation

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```