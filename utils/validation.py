import re
from typing import Tuple, List


def parse_symbols(input_str: str, max_symbols: int = 20) -> Tuple[List[str], List[str]]:
    """Parse comma-separated symbols. Returns (valid_symbols, invalid_symbols)."""
    if not input_str or not input_str.strip():
        return [], []

    parts = [s.strip().upper() for s in input_str.split(",")]
    parts = [s for s in parts if s]

    seen: set = set()
    deduped: List[str] = []
    for s in parts:
        if s not in seen:
            seen.add(s)
            deduped.append(s)

    valid: List[str] = []
    invalid: List[str] = []
    for sym in deduped:
        if re.match(r"^[A-Z0-9]{2,10}$", sym):
            valid.append(sym)
        else:
            invalid.append(sym)

    if len(valid) > max_symbols:
        invalid.extend(valid[max_symbols:])
        valid = valid[:max_symbols]

    return valid, invalid


def symbol_to_pair(symbol: str) -> str:
    return f"{symbol}/USDT"


def pair_to_csv_name(pair: str, timeframe: str) -> str:
    return pair.replace("/", "_") + f"_{timeframe}.csv"
