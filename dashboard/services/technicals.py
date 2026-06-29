"""
Pure-Python technical indicator calculations.
All functions accept a list of floats (closing prices) or OHLCV dicts.
Returns values aligned to the input length where possible.
"""

from __future__ import annotations
import math
from typing import List, Dict, Tuple, Optional


def ema(prices: List[float], period: int) -> List[Optional[float]]:
    """Exponential moving average. Returns None for the first (period-1) values."""
    result: List[Optional[float]] = [None] * len(prices)
    if len(prices) < period:
        return result
    # Seed with SMA of first `period` values
    sma = sum(prices[:period]) / period
    result[period - 1] = sma
    k = 2.0 / (period + 1)
    for i in range(period, len(prices)):
        result[i] = prices[i] * k + result[i - 1] * (1 - k)
    return result


def rsi(prices: List[float], period: int = 14) -> List[Optional[float]]:
    """Wilder's RSI. Returns None for the first `period` values."""
    result: List[Optional[float]] = [None] * len(prices)
    if len(prices) < period + 1:
        return result

    gains, losses = [], []
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def _rsi_value(ag: float, al: float) -> float:
        if al == 0:
            return 100.0
        rs = ag / al
        return 100.0 - (100.0 / (1.0 + rs))

    result[period] = _rsi_value(avg_gain, avg_loss)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        result[i + 1] = _rsi_value(avg_gain, avg_loss)

    return result


def macd(
    prices: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Dict[str, List[Optional[float]]]:
    """Returns dict with keys: macd_line, signal_line, histogram."""
    fast_ema  = ema(prices, fast)
    slow_ema  = ema(prices, slow)

    macd_line: List[Optional[float]] = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(fast_ema, slow_ema)
    ]

    valid_macd = [v for v in macd_line if v is not None]
    first_valid = next((i for i, v in enumerate(macd_line) if v is not None), None)

    if first_valid is None or len(valid_macd) < signal:
        return {
            "macd_line":    macd_line,
            "signal_line":  [None] * len(prices),
            "histogram":    [None] * len(prices),
        }

    sig_ema = ema(valid_macd, signal)
    signal_line: List[Optional[float]] = [None] * len(prices)
    histogram:   List[Optional[float]] = [None] * len(prices)

    for j, v in enumerate(sig_ema):
        if v is not None:
            idx = first_valid + j
            signal_line[idx] = v
            if macd_line[idx] is not None:
                histogram[idx] = macd_line[idx] - v  # type: ignore[operator]

    return {"macd_line": macd_line, "signal_line": signal_line, "histogram": histogram}


def bollinger(
    prices: List[float],
    period: int = 20,
    num_std: float = 2.0,
) -> Dict[str, List[Optional[float]]]:
    """Returns dict with keys: upper, middle, lower."""
    upper:  List[Optional[float]] = [None] * len(prices)
    middle: List[Optional[float]] = [None] * len(prices)
    lower:  List[Optional[float]] = [None] * len(prices)

    for i in range(period - 1, len(prices)):
        window = prices[i - period + 1 : i + 1]
        sma = sum(window) / period
        variance = sum((x - sma) ** 2 for x in window) / period
        std = math.sqrt(variance)
        middle[i] = sma
        upper[i]  = sma + num_std * std
        lower[i]  = sma - num_std * std

    return {"upper": upper, "middle": middle, "lower": lower}


def find_levels(
    candles: List[Dict],
    lookback: int = 50,
    cluster_pct: float = 0.015,
) -> Dict[str, List[float]]:
    """
    Identify support and resistance levels from swing highs/lows.
    candles: list of {open, high, low, close} dicts.
    Returns: {supports: [...], resistances: [...]} sorted closest-to-price first.
    """
    if len(candles) < 5:
        return {"supports": [], "resistances": []}

    data = candles[-lookback:] if len(candles) > lookback else candles
    current_price = data[-1]["close"]

    swing_highs: List[float] = []
    swing_lows:  List[float] = []

    for i in range(2, len(data) - 2):
        h = data[i]["high"]
        l = data[i]["low"]
        if h > data[i-1]["high"] and h > data[i-2]["high"] and h > data[i+1]["high"] and h > data[i+2]["high"]:
            swing_highs.append(h)
        if l < data[i-1]["low"] and l < data[i-2]["low"] and l < data[i+1]["low"] and l < data[i+2]["low"]:
            swing_lows.append(l)

    def cluster(levels: List[float]) -> List[float]:
        if not levels:
            return []
        levels = sorted(levels)
        clustered: List[float] = []
        group: List[float] = [levels[0]]
        for v in levels[1:]:
            if (v - group[0]) / group[0] <= cluster_pct:
                group.append(v)
            else:
                clustered.append(sum(group) / len(group))
                group = [v]
        clustered.append(sum(group) / len(group))
        return clustered

    res_raw = cluster([h for h in swing_highs if h > current_price])
    sup_raw = cluster([l for l in swing_lows  if l < current_price])

    # Sort: resistance ascending (nearest first), support descending (nearest first)
    resistances = sorted(res_raw)[:3]
    supports    = sorted(sup_raw, reverse=True)[:3]

    return {"supports": supports, "resistances": resistances}


def latest(values: List[Optional[float]]) -> Optional[float]:
    """Return the last non-None value in a list."""
    for v in reversed(values):
        if v is not None:
            return v
    return None


def summarize(prices: List[float], candles: List[Dict]) -> Dict:
    """Run all indicators and return a flat summary dict."""
    closes = [c["close"] for c in candles] if candles else prices

    ema20_vals  = ema(closes, 20)
    ema50_vals  = ema(closes, 50)
    ema200_vals = ema(closes, 200)
    rsi_vals    = rsi(closes, 14)
    macd_vals   = macd(closes)
    bb_vals     = bollinger(closes, 20)
    levels      = find_levels(candles) if candles else {"supports": [], "resistances": []}

    return {
        "ema20":       latest(ema20_vals),
        "ema50":       latest(ema50_vals),
        "ema200":      latest(ema200_vals),
        "rsi":         latest(rsi_vals),
        "macd_line":   latest(macd_vals["macd_line"]),
        "macd_signal": latest(macd_vals["signal_line"]),
        "macd_hist":   latest(macd_vals["histogram"]),
        "bb_upper":    latest(bb_vals["upper"]),
        "bb_middle":   latest(bb_vals["middle"]),
        "bb_lower":    latest(bb_vals["lower"]),
        "supports":    levels["supports"],
        "resistances": levels["resistances"],
        # Series for charting (last 100 points)
        "ema20_series":  [v for v in ema20_vals[-100:]],
        "ema50_series":  [v for v in ema50_vals[-100:]],
        "ema200_series": [v for v in ema200_vals[-100:]],
        "rsi_series":    [v for v in rsi_vals[-100:]],
    }
