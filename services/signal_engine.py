from typing import Dict, Any, Optional, Tuple
from services.indicator_engine import extension_pct


# ---------------------------------------------------------------------------
# Trend classification
# ---------------------------------------------------------------------------

def classify_trend(ind: Dict[str, Any]) -> str:
    close       = ind["close"]
    ema21       = ind["ema21"]
    sma50       = ind["sma50"]
    sma50_rising = ind.get("sma50_rising", False)

    above_sma50  = close > sma50
    ema21_above  = ema21 > sma50

    if above_sma50 and ema21_above and sma50_rising:
        return "Strong"
    if not above_sma50 and not ema21_above:
        return "Weak"
    return "Neutral"


# ---------------------------------------------------------------------------
# Action classification
# ---------------------------------------------------------------------------

def classify_action(
    ind: Dict[str, Any],
    trend: str,
    btc_rs: Optional[float],
) -> str:
    if trend == "Weak":
        return "AVOID"

    ext = extension_pct(ind)
    rs_positive = btc_rs is not None and btc_rs > 0.0

    if trend == "Strong":
        if ext > 20:
            return "WAIT"       # extended — wait for pullback
        if rs_positive:
            return "BUY"
        return "HOLD"

    # Neutral
    if ext > 15:
        return "WAIT"
    return "HOLD"


# ---------------------------------------------------------------------------
# Price level computation
# ---------------------------------------------------------------------------

def _fmt(v: float) -> str:
    """Human-readable price formatting."""
    if v >= 10_000:
        return f"{v:,.0f}"
    if v >= 1_000:
        return f"{v:,.1f}"
    if v >= 100:
        return f"{v:.2f}"
    if v >= 10:
        return f"{v:.3f}"
    if v >= 1:
        return f"{v:.4f}"
    if v >= 0.01:
        return f"{v:.5f}"
    return f"{v:.6f}"


def compute_price_levels(ind: Dict[str, Any]) -> Tuple[str, str, str, str]:
    """
    Return (entry, re_entry, trim, exit_str) as display strings.

    entry     — pullback buy zone around EMA10/EMA21
    re_entry  — breakout above 20-day high
    trim      — 12–20% above EMA21
    exit_str  — invalidation: close below SMA50
    """
    close    = ind["close"]
    ema10    = ind["ema10"]
    ema21    = ind["ema21"]
    sma50    = ind["sma50"]
    high_20d = ind["high_20d"]

    # --- Entry: pullback zone anchored on EMA10/EMA21 ---
    anchor_low  = min(ema10, ema21)
    anchor_high = max(ema10, ema21)

    entry_low  = anchor_low  * 0.97
    entry_high = anchor_high * 1.005

    # Never suggest buying above current price
    if entry_high > close:
        entry_high = close * 0.995
    if entry_low > entry_high:
        entry_low = entry_high * 0.97

    entry = f"{_fmt(entry_low)}–{_fmt(entry_high)}"

    # --- Re-entry: breakout above 20-day high ---
    re_entry_level = high_20d * 1.005
    # If close is already above 20-day high, add one more ATR-like buffer
    if close >= high_20d:
        re_entry_level = close * 1.02
    re_entry = f"above {_fmt(re_entry_level)} breakout"

    # --- Trim: 12–20% above EMA21 ---
    trim_low  = ema21 * 1.12
    trim_high = ema21 * 1.20
    trim = f"{_fmt(trim_low)}–{_fmt(trim_high)}"

    # --- Exit: daily close below SMA50 ---
    exit_str = f"close below {_fmt(sma50)}"

    return entry, re_entry, trim, exit_str
