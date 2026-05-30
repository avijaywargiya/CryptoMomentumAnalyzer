import pandas as pd
import numpy as np
from typing import Optional, Dict, Any


# ---------------------------------------------------------------------------
# Core indicator functions
# ---------------------------------------------------------------------------

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, prev_close = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=period).mean()


# ---------------------------------------------------------------------------
# Full indicator computation on a DataFrame
# ---------------------------------------------------------------------------

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all technical indicator columns to a copy of df."""
    df = df.copy()
    close = df["close"]

    df["ema10"] = _ema(close, 10)
    df["ema21"] = _ema(close, 21)
    df["sma50"] = _sma(close, 50)
    df["sma200"] = _sma(close, 200)
    df["atr14"] = _atr(df, 14)

    df["high_20d"] = df["high"].rolling(20).max()
    df["low_20d"] = df["low"].rolling(20).min()
    df["vol_avg_50d"] = df["volume"].rolling(50).mean()
    df["vol_avg_5d"] = df["volume"].rolling(5).mean()

    # SMA50 direction: compare to value 5 bars ago
    df["sma50_prev5"] = df["sma50"].shift(5)
    df["sma50_rising"] = df["sma50"] > df["sma50_prev5"]

    return df


# ---------------------------------------------------------------------------
# Extract latest indicator snapshot
# ---------------------------------------------------------------------------

MIN_CANDLES = 55  # need at least this many for SMA50 + a few lookback bars


def get_latest_indicators(df: Optional[pd.DataFrame]) -> Optional[Dict[str, Any]]:
    """Return a dict of current indicator values, or None if insufficient data."""
    if df is None or df.empty or len(df) < MIN_CANDLES:
        return None

    df = compute_indicators(df)
    last = df.iloc[-1]

    # 20-bar-ago close for relative-strength calc (needs index offset of 20)
    close_20d_ago: Optional[float] = None
    if len(df) >= 21:
        close_20d_ago = float(df["close"].iloc[-21])

    return {
        "close":         float(last["close"]),
        "ema10":         float(last["ema10"]),
        "ema21":         float(last["ema21"]),
        "sma50":         float(last["sma50"]),
        "sma200":        float(last["sma200"]) if pd.notna(last["sma200"]) else None,
        "atr14":         float(last["atr14"]) if pd.notna(last["atr14"]) else 0.0,
        "high_20d":      float(last["high_20d"]),
        "low_20d":       float(last["low_20d"]),
        "vol_avg_50d":   float(last["vol_avg_50d"]) if pd.notna(last["vol_avg_50d"]) else 0.0,
        "vol_avg_5d":    float(last["vol_avg_5d"])  if pd.notna(last["vol_avg_5d"])  else 0.0,
        "sma50_rising":  bool(last["sma50_rising"]) if pd.notna(last["sma50_rising"]) else False,
        "close_20d_ago": close_20d_ago,
        "datetime":      last["datetime"],
    }


# ---------------------------------------------------------------------------
# Derived helpers (used by signal & scoring engines)
# ---------------------------------------------------------------------------

def extension_pct(ind: Dict[str, Any]) -> float:
    """Percentage distance of close above EMA21 (negative = below)."""
    ema21 = ind.get("ema21", 0)
    if not ema21:
        return 0.0
    return (ind["close"] - ema21) / ema21 * 100.0


def compute_btc_rs(
    ind: Dict[str, Any],
    btc_ind: Optional[Dict[str, Any]],
) -> Optional[float]:
    """
    20-day return of coin minus 20-day return of BTC.
    Positive = coin outperforming BTC.
    """
    c     = ind.get("close")
    c20   = ind.get("close_20d_ago")
    btc_c = btc_ind.get("close")       if btc_ind else None
    btc20 = btc_ind.get("close_20d_ago") if btc_ind else None

    if any(v is None for v in [c, c20, btc_c, btc20]):
        return None
    if c20 == 0 or btc20 == 0:
        return None

    return (c / c20 - 1) - (btc_c / btc20 - 1)
