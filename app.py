"""
Crypto Momentum Entry & Exit Analyzer
--------------------------------------
Local-first Streamlit app for 3–6 month swing-trading momentum analysis.
Data source: Binance OHLCV via CCXT  |  Cache: ./data/crypto/*.csv
"""

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from services.data_fetcher import EXCHANGE_OPTIONS, get_data, get_exchange
from services.indicator_engine import (
    compute_btc_rs,
    compute_indicators,
    get_latest_indicators,
)
from services.scoring_engine import compute_score, get_btc_regime
from services.signal_engine import classify_action, classify_trend, compute_price_levels
from utils.validation import parse_symbols, symbol_to_pair

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REFRESH_MIN_SECONDS = 15 * 60  # 15-minute minimum between refreshes

# ---------------------------------------------------------------------------
# Streamlit page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Crypto Momentum Analyzer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    /* Table font size */
    .stDataFrame { font-size: 13px; }
    /* Metric label */
    [data-testid="stMetricLabel"] { font-size: 13px; }
    /* Tighten padding */
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

for key, default in {
    "last_refresh": None,
    "results": None,
    "raw_data": {},
    "btc_regime": "Neutral",
    "exchange_label": "BinanceUS (USA)",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📈 About")
    st.markdown(
        """
        **What this tool does:**
        - Ranks cryptos by 3–6 month momentum
        - Entry, re-entry, trim & exit levels
        - BTC-relative strength (20-day)
        - Momentum score 0–100

        **What this is NOT:**
        - AI prediction engine
        - Automated trading bot
        - Financial advice

        ---
        **Timeframe:** 1D candles (UTC)
        **Cache:** `./data/crypto/`
        """
    )

    st.divider()
    st.subheader("🌐 Data Source")
    exchange_label = st.selectbox(
        "Exchange",
        options=list(EXCHANGE_OPTIONS.keys()),
        index=list(EXCHANGE_OPTIONS.keys()).index(st.session_state.exchange_label)
            if st.session_state.exchange_label in EXCHANGE_OPTIONS else 0,
        help=(
            "Binance.com is geo-blocked in the US and some other countries (HTTP 451). "
            "US users: choose BinanceUS. Global alternative: Bybit or OKX."
        ),
    )
    st.session_state.exchange_label = exchange_label
    exchange_id = EXCHANGE_OPTIONS[exchange_label]
    st.caption(f"CCXT id: `{exchange_id}`")

    st.divider()
    st.subheader("⏱ Refresh Policy")
    if st.session_state.last_refresh:
        elapsed = (datetime.now(timezone.utc) - st.session_state.last_refresh).total_seconds()
        remaining = max(0.0, REFRESH_MIN_SECONDS - elapsed)
        if remaining > 0:
            st.warning(
                f"Next refresh in **{int(remaining // 60)}m {int(remaining % 60)}s**"
            )
        else:
            st.success("Ready to refresh")
        st.caption(
            f"Last run: {st.session_state.last_refresh.strftime('%Y-%m-%d %H:%M UTC')}"
        )
    else:
        st.info("No data fetched yet.")

    st.divider()
    st.subheader("🎨 Legend")
    st.markdown(
        """
        **Trend**
        🟢 Strong · 🟡 Neutral · 🔴 Weak

        **Action**
        🟢 BUY · 🟡 WAIT · 🔵 HOLD · 🔴 AVOID

        **BTC RS** (20-day return vs BTC)
        Positive · Neutral · Weak

        **Score**
        75–100 excellent · 50–74 good · <50 avoid
        """
    )

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("📈 Crypto Momentum Entry & Exit Analyzer")
st.caption(
    f"3–6 month swing trading momentum | {st.session_state.exchange_label} OHLCV 1D candles (UTC) | Local cache only"
)

# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

col_input, col_btn = st.columns([5, 2])

with col_input:
    symbol_input = st.text_input(
        "Enter crypto symbols (comma-separated, max 20):",
        placeholder="BTC, ETH, SOL, SUI, LINK",
        help="Coin base symbols only — USDT pairs are used automatically.",
    )

with col_btn:
    st.write("")
    st.write("")
    analyze_btn = st.button(
        "🔍 Analyze Crypto Momentum",
        type="primary",
        use_container_width=True,
    )


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def _format_close(price: float) -> str:
    if price >= 10_000:
        return f"${price:,.2f}"
    if price >= 1_000:
        return f"${price:,.2f}"
    if price >= 100:
        return f"${price:.2f}"
    if price >= 10:
        return f"${price:.3f}"
    if price >= 1:
        return f"${price:.4f}"
    if price >= 0.01:
        return f"${price:.5f}"
    return f"${price:.6f}"


def _btc_rs_label(btc_rs: Optional[float]) -> str:
    if btc_rs is None:
        return "N/A"
    if btc_rs > 0.03:
        return "Positive"
    if btc_rs < -0.03:
        return "Weak"
    return "Neutral"


def run_analysis(
    symbols: List[str],
    exchange,
    exchange_id: str = "binance",
    progress_callback=None,
) -> Tuple[List[dict], Dict, List[str], List[str], str]:
    """
    Returns (results, raw_data, stale_symbols, unavailable_symbols, btc_regime).
    """
    results: List[dict] = []
    stale_symbols: List[str] = []
    unavailable_symbols: List[str] = []
    raw_data: Dict = {}

    total = len(symbols) + 1  # +1 for BTC benchmark
    step = 0

    # --- BTC benchmark ---
    if progress_callback:
        progress_callback(step / total, "Fetching BTC benchmark…")
    btc_df, btc_status = get_data("BTC/USDT", exchange, exchange_id)
    raw_data["BTC/USDT"] = btc_df
    btc_ind = get_latest_indicators(btc_df) if btc_df is not None else None
    btc_regime = get_btc_regime(btc_ind)
    step += 1

    # --- Per-symbol analysis ---
    for symbol in symbols:
        pair = symbol_to_pair(symbol)

        if progress_callback:
            progress_callback(step / total, f"Analyzing {symbol}…")

        df, status = get_data(pair, exchange, exchange_id)
        raw_data[pair] = df

        if status == "unavailable" or df is None or df.empty:
            unavailable_symbols.append(symbol)
            step += 1
            continue

        if status == "stale_cache":
            stale_symbols.append(symbol)

        ind = get_latest_indicators(df)
        if ind is None:
            unavailable_symbols.append(symbol)
            step += 1
            continue

        btc_rs_val = compute_btc_rs(ind, btc_ind)
        trend      = classify_trend(ind)
        action     = classify_action(ind, trend, btc_rs_val)
        entry, re_entry, trim, exit_lvl = compute_price_levels(ind)
        score      = compute_score(ind, trend, btc_rs_val, btc_regime, is_btc=(symbol == "BTC"))

        stale_flag = " ⚠️" if status == "stale_cache" else ""

        results.append(
            {
                "Crypto":      symbol + stale_flag,
                "Pair":        pair,
                "Last Close":  _format_close(ind["close"]),
                "Trend":       trend,
                "Action":      action,
                "Entry":       entry,
                "Re-Entry":    re_entry,
                "Trim":        trim,
                "Exit":        exit_lvl,
                "BTC RS":      _btc_rs_label(btc_rs_val),
                "Score":       score,
                # private fields for charts
                "_symbol":     symbol,
                "_pair":       pair,
                "_close_raw":  ind["close"],
            }
        )
        step += 1

    # Sort by score descending, assign ranks
    results.sort(key=lambda r: r["Score"], reverse=True)
    for i, r in enumerate(results, 1):
        r["Rank"] = i

    if progress_callback:
        progress_callback(1.0, "Complete!")

    return results, raw_data, stale_symbols, unavailable_symbols, btc_regime


# ---------------------------------------------------------------------------
# Trigger analysis on button press
# ---------------------------------------------------------------------------

if analyze_btn:
    if not symbol_input or not symbol_input.strip():
        st.error("Please enter at least one crypto symbol.")
    else:
        valid_symbols, invalid_symbols = parse_symbols(symbol_input)

        if invalid_symbols:
            st.warning(
                f"Invalid or unavailable symbols skipped: **{', '.join(invalid_symbols)}**"
            )

        if not valid_symbols:
            st.error("No valid symbols to analyze.")
        else:
            # Enforce refresh interval (advisory — still runs with stale cache)
            if st.session_state.last_refresh:
                elapsed = (
                    datetime.now(timezone.utc) - st.session_state.last_refresh
                ).total_seconds()
                if elapsed < REFRESH_MIN_SECONDS:
                    remaining = REFRESH_MIN_SECONDS - elapsed
                    st.info(
                        f"ℹ️ {int(remaining // 60)}m {int(remaining % 60)}s until next "
                        "recommended refresh — serving from cache where possible."
                    )

            exchange = get_exchange(exchange_id)
            progress_bar = st.progress(0, text="Starting…")

            def _update_progress(pct: float, text: str) -> None:
                progress_bar.progress(min(pct, 1.0), text=text)

            try:
                (
                    st.session_state.results,
                    st.session_state.raw_data,
                    stale_list,
                    unavail_list,
                    st.session_state.btc_regime,
                ) = run_analysis(valid_symbols, exchange, exchange_id, _update_progress)

                time.sleep(0.2)
                progress_bar.empty()
                st.session_state.last_refresh = datetime.now(timezone.utc)

                if unavail_list:
                    st.warning(
                        f"⚠️ Symbols unavailable / insufficient history: **{', '.join(unavail_list)}**"
                    )
                if stale_list:
                    st.info(
                        f"ℹ️ Stale cache used for: **{', '.join(stale_list)}** — data may be outdated (⚠️)"
                    )

            except Exception as exc:
                progress_bar.empty()
                st.error(f"Analysis failed: {exc}")


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

if st.session_state.results:
    results    = st.session_state.results
    raw_data   = st.session_state.raw_data
    btc_regime = st.session_state.btc_regime

    st.divider()

    # KPI row
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    regime_icon = {"Risk-On": "🟢", "Neutral": "🟡", "Risk-Off": "🔴"}.get(btc_regime, "🟡")
    kpi1.metric("BTC Regime", f"{regime_icon} {btc_regime}")
    kpi2.metric("Symbols Analyzed", len(results))
    buy_count = sum(1 for r in results if r["Action"] == "BUY")
    kpi3.metric("BUY Setups", buy_count)
    top_score = results[0]["Score"] if results else 0
    kpi4.metric("Top Score", f"{top_score}/100")

    st.divider()

    # --- Build display DataFrame ---
    DISPLAY_COLS = [
        "Rank", "Crypto", "Pair", "Last Close",
        "Trend", "Action", "Entry", "Re-Entry", "Trim", "Exit",
        "BTC RS", "Score",
    ]
    df_display = pd.DataFrame(results)[DISPLAY_COLS].copy()

    # Pandas Styler for colour coding
    def _style_trend(val: str) -> str:
        if val == "Strong":
            return "color:#00cc66;font-weight:bold"
        if val == "Neutral":
            return "color:#ffaa00"
        if val == "Weak":
            return "color:#ff5555"
        return ""

    def _style_action(val: str) -> str:
        mapping = {
            "BUY":   "background-color:#0d3d1f;color:#00ee77;font-weight:bold",
            "WAIT":  "background-color:#3d2d00;color:#ffcc00",
            "HOLD":  "background-color:#0a1f3d;color:#66aaff",
            "AVOID": "background-color:#3d0a0a;color:#ff6666",
        }
        return mapping.get(val, "")

    def _style_btc_rs(val: str) -> str:
        if val == "Positive":
            return "color:#00cc66"
        if val == "Weak":
            return "color:#ff5555"
        if val == "Neutral":
            return "color:#ffaa00"
        return ""

    def _style_score(val) -> str:
        try:
            s = float(val)
        except (TypeError, ValueError):
            return ""
        if s >= 75:
            return "color:#00cc66;font-weight:bold"
        if s >= 50:
            return "color:#ffaa00"
        return "color:#ff5555"

    styled_df = (
        df_display.style
        .map(_style_trend,  subset=["Trend"])
        .map(_style_action, subset=["Action"])
        .map(_style_btc_rs, subset=["BTC RS"])
        .map(_style_score,  subset=["Score"])
    )

    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    # --- Methodology expander ---
    with st.expander("📖 Methodology & Score Breakdown"):
        m1, m2 = st.columns(2)
        with m1:
            st.markdown(
                """
                **Trend Classification:**
                - **Strong** — close > SMA50, EMA21 > SMA50, SMA50 rising
                - **Neutral** — mixed signals around SMA50
                - **Weak** — close < SMA50, EMA21 < SMA50

                **Action:**
                - **BUY** — Strong trend, ≤20% above EMA21, positive BTC RS
                - **WAIT** — Strong trend but extended (>20% above EMA21)
                - **HOLD** — Trend intact, not ideal entry conditions
                - **AVOID** — Weak trend / below SMA50

                **Price Levels:**
                - **Entry** — pullback zone around EMA10/EMA21
                - **Re-Entry** — breakout above 20-day high
                - **Trim** — 12–20% above EMA21
                - **Exit** — daily close below SMA50 (momentum invalidation)
                """
            )
        with m2:
            st.markdown(
                """
                **Momentum Score (0–100):**
                | Component | Max |
                |-----------|-----|
                | BTC Relative Strength (20d) | 25 |
                | Trend Quality | 25 |
                | Entry Quality (not extended) | 20 |
                | Volume Quality (5d vs 50d avg) | 15 |
                | Extension Risk | 15 |

                **BTC Regime Adjustment:**
                - Risk-On → no penalty
                - Neutral → ×0.90
                - Risk-Off → ×0.75 (altcoins only)

                **BTC RS Labels:**
                - Positive — outperforming BTC by >3% over 20 days
                - Neutral — within ±3% of BTC
                - Weak — underperforming BTC by >3%
                """
            )

    # ---------------------------------------------------------------------------
    # Optional price charts
    # ---------------------------------------------------------------------------

    st.divider()
    st.subheader("📊 Price Charts")
    st.caption("Expand a symbol to view its price chart with EMA10, EMA21, and SMA50.")

    for row in results:
        symbol = row["_symbol"]
        pair   = row["_pair"]
        df     = raw_data.get(pair)

        if df is None or df.empty:
            continue

        label = (
            f"📈 {symbol}/USDT  ·  {row['Trend']}  ·  {row['Action']}  ·  Score {row['Score']}"
        )

        with st.expander(label):
            ind_df = compute_indicators(df).tail(150).copy()

            fig = go.Figure()

            fig.add_trace(go.Scatter(
                x=ind_df["datetime"], y=ind_df["close"],
                name="Close", line=dict(color="#ffffff", width=2),
            ))
            fig.add_trace(go.Scatter(
                x=ind_df["datetime"], y=ind_df["ema10"],
                name="EMA 10", line=dict(color="#00ccff", width=1, dash="dot"),
            ))
            fig.add_trace(go.Scatter(
                x=ind_df["datetime"], y=ind_df["ema21"],
                name="EMA 21", line=dict(color="#ff9900", width=1.5),
            ))
            fig.add_trace(go.Scatter(
                x=ind_df["datetime"], y=ind_df["sma50"],
                name="SMA 50", line=dict(color="#ffff44", width=1.5),
            ))

            fig.update_layout(
                template="plotly_dark",
                title=f"{symbol}/USDT — Last {len(ind_df)} Days",
                xaxis_title="Date",
                yaxis_title="Price (USDT)",
                height=420,
                legend=dict(
                    orientation="h",
                    yanchor="bottom", y=1.02,
                    xanchor="right", x=1,
                ),
                margin=dict(l=40, r=20, t=60, b=40),
            )

            st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------

elif not analyze_btn:
    st.info(
        "👆 Enter crypto symbols above and click **Analyze Crypto Momentum** to get started.\n\n"
        "Example: `BTC, ETH, SOL, SUI, LINK, AVAX, DOT`"
    )
