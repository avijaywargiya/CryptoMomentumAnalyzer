# Crypto Momentum Entry & Exit Analyzer

Local-first Streamlit app for 3–6 month swing trading momentum analysis.  
Fetches Binance OHLCV data, caches it locally, and ranks up to 20 crypto symbols by momentum setup quality.

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open your browser at **http://localhost:8501**

## Features

- Enter up to 20 symbols (e.g. `BTC, ETH, SOL, SUI, LINK`)
- Binance USDT pairs fetched via CCXT
- **Local CSV cache** in `./data/crypto/` — incremental updates only
- **15-minute minimum refresh interval** (API-safe)
- Ranked output table: Trend · Action · Entry · Re-Entry · Trim · Exit · BTC RS · Score
- Optional per-symbol price charts (Close, EMA10, EMA21, SMA50)
- Invalid or unavailable symbols are skipped gracefully

## Output Columns

| Column | Description |
|--------|-------------|
| Rank | Best momentum setup = #1 |
| Last Close | Last completed 1D UTC candle close |
| Trend | Strong / Neutral / Weak (SMA50 + EMA21 structure) |
| Action | BUY / WAIT / HOLD / AVOID |
| Entry | Pullback buy zone (EMA10/EMA21 area) |
| Re-Entry | Breakout above 20-day high |
| Trim | Partial-profit zone (12–20% above EMA21) |
| Exit | Momentum invalidation (close below SMA50) |
| BTC RS | 20-day return vs BTC: Positive / Neutral / Weak |
| Score | 0–100 composite momentum score |

## Score Weights

| Component | Max Pts |
|-----------|---------|
| BTC Relative Strength (20d) | 25 |
| Trend Quality | 25 |
| Entry Quality (distance from EMA21) | 20 |
| Volume Quality (5d vs 50d avg) | 15 |
| Extension Risk | 15 |

BTC regime adjustment: Risk-Off penalises altcoin scores by 25%.

## Project Structure

```
app.py                      Main Streamlit application
services/
  data_fetcher.py           CCXT + CSV cache management
  indicator_engine.py       EMA, SMA, ATR, indicators
  signal_engine.py          Trend / Action / price levels
  scoring_engine.py         0-100 momentum score
utils/
  validation.py             Symbol parsing and validation
data/crypto/                CSV cache (auto-created)
requirements.txt
```

## Cache Files

One CSV per symbol per timeframe: `./data/crypto/BTC_USDT_1d.csv`

Columns: `timestamp, open, high, low, close, volume, datetime`

The app never refetches full history — only missing candles are appended on each run.

## Notes

- This is **not** financial advice.
- This is **not** an AI prediction engine or automated trading bot.
- All data is fetched from Binance public endpoints — no API key required.
- Only completed 1D UTC candles are used (live intraday candle is excluded).
