from typing import Dict, Any, Optional
from services.indicator_engine import extension_pct


# ---------------------------------------------------------------------------
# Sub-score functions (each returns its component's maximum points)
# ---------------------------------------------------------------------------

def _score_btc_rs(btc_rs: Optional[float]) -> float:
    """0–25 pts based on 20-day return differential vs BTC."""
    if btc_rs is None:
        return 10.0  # neutral when unavailable
    if btc_rs > 0.20:
        return 25.0
    if btc_rs > 0.12:
        return 22.0
    if btc_rs > 0.05:
        return 18.0
    if btc_rs > 0.01:
        return 13.0
    if btc_rs > -0.02:
        return 10.0
    if btc_rs > -0.08:
        return 5.0
    return 0.0


def _score_trend(trend: str) -> float:
    """0–25 pts based on trend quality."""
    return {"Strong": 25.0, "Neutral": 12.0, "Weak": 0.0}.get(trend, 0.0)


def _score_entry_quality(ind: Dict[str, Any]) -> float:
    """
    0–20 pts.  Rewards setups where price is near (but above) EMA21 —
    i.e. not chasing a vertical move.
    """
    ext = extension_pct(ind)
    close = ind["close"]
    sma50 = ind["sma50"]
    above_sma50 = close > sma50

    base: float
    if ext < 2:
        base = 20.0
    elif ext < 6:
        base = 17.0
    elif ext < 12:
        base = 12.0
    elif ext < 20:
        base = 6.0
    elif ext < 30:
        base = 2.0
    else:
        base = 0.0

    # Bonus for price staying above SMA50 (stronger base)
    if above_sma50 and ext < 20:
        base = min(base + 2, 20.0)

    return base


def _score_volume(ind: Dict[str, Any]) -> float:
    """
    0–15 pts.  Compares 5-day avg volume to 50-day avg volume.
    Rising volume is constructive.
    """
    avg50 = ind.get("vol_avg_50d", 0)
    avg5  = ind.get("vol_avg_5d",  0)

    if not avg50 or not avg5:
        return 7.0  # neutral when data missing

    ratio = avg5 / avg50
    if ratio > 1.6:
        return 15.0
    if ratio > 1.2:
        return 12.0
    if ratio > 0.85:
        return 9.0
    if ratio > 0.55:
        return 5.0
    return 2.0


def _score_extension_risk(ind: Dict[str, Any]) -> float:
    """
    0–15 pts.  Higher score = lower extension risk (better entry timing).
    Penalises coins that are far above SMA50.
    """
    close = ind["close"]
    sma50 = ind["sma50"]
    ext   = extension_pct(ind)

    if sma50 > 0:
        dist_sma50_pct = (close - sma50) / sma50 * 100
    else:
        dist_sma50_pct = 0.0

    if ext < 3 and dist_sma50_pct < 15:
        return 15.0
    if ext < 8:
        return 12.0
    if ext < 15:
        return 8.0
    if ext < 25:
        return 4.0
    return 0.0


# ---------------------------------------------------------------------------
# BTC regime
# ---------------------------------------------------------------------------

def get_btc_regime(btc_ind: Optional[Dict[str, Any]]) -> str:
    """Risk-On | Neutral | Risk-Off based on BTC trend structure."""
    if btc_ind is None:
        return "Neutral"

    close        = btc_ind["close"]
    sma50        = btc_ind["sma50"]
    ema21        = btc_ind["ema21"]

    if close > sma50 and ema21 > sma50:
        return "Risk-On"
    if close < sma50:
        return "Risk-Off"
    return "Neutral"


def _regime_multiplier(regime: str, is_btc: bool) -> float:
    """Altcoins are penalised in weak BTC regimes; BTC itself is not."""
    if is_btc:
        return 1.0
    return {"Risk-On": 1.0, "Neutral": 0.90, "Risk-Off": 0.75}.get(regime, 1.0)


# ---------------------------------------------------------------------------
# Master score
# ---------------------------------------------------------------------------

def compute_score(
    ind: Dict[str, Any],
    trend: str,
    btc_rs: Optional[float],
    btc_regime: str,
    is_btc: bool = False,
) -> float:
    """Return a 0–100 momentum score."""
    raw = (
        _score_btc_rs(btc_rs)
        + _score_trend(trend)
        + _score_entry_quality(ind)
        + _score_volume(ind)
        + _score_extension_risk(ind)
    )

    adjusted = raw * _regime_multiplier(btc_regime, is_btc)
    return round(min(max(adjusted, 0.0), 100.0), 1)
