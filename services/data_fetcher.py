import ccxt
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

CACHE_DIR = Path("./data/crypto")
TIMEFRAME = "1d"
INITIAL_CANDLE_LIMIT = 400

# Exchanges available in the UI selector
EXCHANGE_OPTIONS = {
    "Binance (Global)":  "binance",
    "BinanceUS (USA)":   "binanceus",
    "Bybit":             "bybit",
    "OKX":               "okx",
    "KuCoin":            "kucoin",
}


def get_exchange(exchange_id: str = "binance") -> ccxt.Exchange:
    """Return a configured CCXT exchange instance."""
    cfg = {"enableRateLimit": True, "timeout": 15000}
    cls = getattr(ccxt, exchange_id, None)
    if cls is None:
        raise ValueError(f"Unknown exchange: {exchange_id}")
    return cls(cfg)


def _today_midnight_ms() -> int:
    """Timestamp (ms) for today 00:00 UTC — open of the still-incomplete daily candle."""
    now = datetime.now(timezone.utc)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(midnight.timestamp() * 1000)


def _csv_path(pair: str, exchange_id: str) -> Path:
    """One CSV file per pair + exchange so caches don't mix."""
    name = pair.replace("/", "_") + f"_{TIMEFRAME}_{exchange_id}.csv"
    return CACHE_DIR / name


def _load_cache(pair: str, exchange_id: str) -> Optional[pd.DataFrame]:
    path = _csv_path(pair, exchange_id)
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
        df["timestamp"] = pd.to_numeric(df["timestamp"])
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
        return df
    except Exception:
        return None


def _save_cache(df: pd.DataFrame, pair: str, exchange_id: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _csv_path(pair, exchange_id)
    df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    df.to_csv(path, index=False)


def _ohlcv_to_df(raw: list) -> pd.DataFrame:
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df


def _fetch_from_exchange(
    exchange: ccxt.Exchange,
    pair: str,
    since: Optional[int] = None,
    limit: int = INITIAL_CANDLE_LIMIT,
) -> Optional[pd.DataFrame]:
    try:
        kwargs: dict = {"limit": limit}
        if since is not None:
            kwargs["since"] = since
        raw = exchange.fetch_ohlcv(pair, TIMEFRAME, **kwargs)
        if not raw:
            return None
        return _ohlcv_to_df(raw)
    except Exception:
        return None


def get_data(
    pair: str,
    exchange: Optional[ccxt.Exchange] = None,
    exchange_id: str = "binance",
) -> Tuple[Optional[pd.DataFrame], str]:
    """
    Return (df, status) where status is 'ok' | 'stale_cache' | 'unavailable'.

    Cache strategy:
      1. Load cached CSV (keyed by pair + exchange_id).
      2. If cache has yesterday's candle, return immediately.
      3. Otherwise fetch only the missing candles, merge, re-save.
      4. On any fetch failure fall back to stale cache or mark unavailable.
    """
    if exchange is None:
        exchange = get_exchange(exchange_id)

    today_ms     = _today_midnight_ms()
    yesterday_ms = today_ms - 86_400_000

    cached = _load_cache(pair, exchange_id)

    if cached is not None and not cached.empty:
        latest_ts = int(cached["timestamp"].max())

        if latest_ts >= yesterday_ms:
            completed = cached[cached["timestamp"] < today_ms].copy()
            return completed, "ok"

        # Incremental update
        since  = latest_ts + 1
        new_df = _fetch_from_exchange(exchange, pair, since=since)

        if new_df is not None and not new_df.empty:
            combined = (
                pd.concat([cached, new_df], ignore_index=True)
                .sort_values("timestamp")
                .drop_duplicates("timestamp")
                .reset_index(drop=True)
            )
            completed = combined[combined["timestamp"] < today_ms].copy()
            _save_cache(completed, pair, exchange_id)
            return completed, "ok"

        completed = cached[cached["timestamp"] < today_ms].copy()
        return completed, "stale_cache"

    # No cache — full initial fetch
    df = _fetch_from_exchange(exchange, pair, limit=INITIAL_CANDLE_LIMIT)
    if df is not None and not df.empty:
        completed = df[df["timestamp"] < today_ms].copy()
        _save_cache(completed, pair, exchange_id)
        return completed, "ok"

    return None, "unavailable"
