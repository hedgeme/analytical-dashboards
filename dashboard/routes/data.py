"""
GET /dashboard/api/data
Fires ~15 external API calls concurrently via aiohttp and returns a single JSON payload
containing all data needed for the dashboard.
"""

import asyncio
import os
import re
import time
from typing import Any, Dict

import aiohttp
from flask import Blueprint, jsonify

from services.technicals import summarize

data_bp = Blueprint("data", __name__)

# ─── constants ────────────────────────────────────────────────────────────────
COINGECKO_KEY    = os.getenv("COINGECKO_API_KEY", "")
ETHERSCAN_KEY    = os.getenv("ETHERSCAN_API_KEY", "")
SOSOVALUE_KEY    = os.getenv("SOSOVALUE_API_KEY", "")
CRYPTOQUANT_KEY  = os.getenv("CRYPTOQUANT_API_KEY", "")

CG_BASE  = "https://api.coingecko.com/api/v3"
CDC_BASE = "https://api.crypto.com/exchange/v1/public"
CQ_BASE  = "https://api.cryptoquant.com/v1"

CG_HEADERS = {"x-cg-demo-api-key": COINGECKO_KEY} if COINGECKO_KEY else {}
CQ_HEADERS = {"Authorization": f"Bearer {CRYPTOQUANT_KEY}"} if CRYPTOQUANT_KEY else {}
UA_HEADERS = {"User-Agent": "Mozilla/5.0 (ETH-Dashboard/1.0)"}

TIMEOUT = aiohttp.ClientTimeout(total=15)


# ─── individual fetchers ──────────────────────────────────────────────────────

async def safe(coro):
    """Wrap a coroutine so a network failure returns None instead of raising."""
    try:
        return await coro
    except Exception as e:
        print(f"[data] fetch error: {e}")
        return None


async def get(session: aiohttp.ClientSession, url: str, params=None, headers=None) -> Any:
    h = {**UA_HEADERS, **(headers or {})}
    async with session.get(url, params=params, headers=h, timeout=TIMEOUT) as r:
        r.raise_for_status()
        return await r.json(content_type=None)


async def fetch_eth_coingecko(s):
    return await get(s, f"{CG_BASE}/coins/ethereum", headers=CG_HEADERS, params={
        "localization": "false", "tickers": "false",
        "community_data": "false", "developer_data": "false",
    })


async def fetch_btc_coingecko(s):
    return await get(s, f"{CG_BASE}/coins/bitcoin", headers=CG_HEADERS, params={
        "localization": "false", "tickers": "false",
        "community_data": "false", "developer_data": "false",
    })


async def fetch_global_coingecko(s):
    return await get(s, f"{CG_BASE}/global", headers=CG_HEADERS)


async def fetch_eth_history_7d(s):
    return await get(s, f"{CG_BASE}/coins/ethereum/market_chart", headers=CG_HEADERS,
                     params={"vs_currency": "usd", "days": "7", "interval": "daily"})


async def fetch_eth_history_200d(s):
    return await get(s, f"{CG_BASE}/coins/ethereum/market_chart", headers=CG_HEADERS,
                     params={"vs_currency": "usd", "days": "200", "interval": "daily"})


async def fetch_eth_ticker_cdc(s):
    return await get(s, f"{CDC_BASE}/get-ticker", params={"instrument_name": "ETH_USDT"})


async def fetch_btc_ticker_cdc(s):
    return await get(s, f"{CDC_BASE}/get-ticker", params={"instrument_name": "BTC_USDT"})


async def fetch_eth_candles_4h(s):
    return await get(s, f"{CDC_BASE}/get-candlestick",
                     params={"instrument_name": "ETH_USDT", "timeframe": "4h", "count": "100"})


async def fetch_eth_candles_1d(s):
    return await get(s, f"{CDC_BASE}/get-candlestick",
                     params={"instrument_name": "ETH_USDT", "timeframe": "1D", "count": "200"})


async def fetch_fear_greed(s):
    return await get(s, "https://api.alternative.me/fng/", params={"limit": "7"})


async def fetch_eth_fear_greed(s):
    """Parse ETH-specific F&G index from ethereumfear.com HTML."""
    try:
        async with s.get("https://ethereumfear.com/", headers=UA_HEADERS, timeout=TIMEOUT) as r:
            html = await r.text()
        patterns = [
            r'"value":\s*(\d+)',
            r'class="fgi-value[^"]*"[^>]*>(\d+)',
            r'<span[^>]*id="fgi[^"]*"[^>]*>(\d+)',
            r'"fgi"[^:]*:\s*{\s*"value":\s*(\d+)',
            r'>(\d+)<\/[a-z]+>\s*<\/div>\s*<div[^>]*class="[^"]*label',
        ]
        for pat in patterns:
            m = re.search(pat, html)
            if m:
                val = int(m.group(1))
                if 0 <= val <= 100:
                    return {"value": val}
    except Exception as e:
        print(f"[data] eth f&g: {e}")
    return None


async def fetch_gas(s):
    if not ETHERSCAN_KEY:
        return None
    return await get(s, "https://api.etherscan.io/api", params={
        "module": "gastracker", "action": "gasoracle", "apikey": ETHERSCAN_KEY,
    })


async def fetch_defillama_lido(s):
    return await get(s, "https://api.llama.fi/protocol/lido")


async def fetch_defillama_lst(s):
    return await get(s, "https://yields.llama.fi/pools")


async def fetch_reddit(s, subreddit: str):
    return await get(s, f"https://www.reddit.com/r/{subreddit}/hot.json",
                     params={"limit": "25"},
                     headers={"User-Agent": "ETH-Dashboard/1.0 (dashboard)"})


async def fetch_cq(s, path: str, params: dict = None):
    if not CRYPTOQUANT_KEY:
        return None
    return await get(s, f"{CQ_BASE}{path}", headers=CQ_HEADERS,
                     params={"window": "day", "limit": "3", **(params or {})})


async def fetch_sosovalue_etf(s):
    """ETH + BTC spot ETF flows from SoSoValue. Graceful degradation if key absent."""
    if not SOSOVALUE_KEY:
        return None
    try:
        eth = await get(s, "https://sosovalue.com/api/etf/us-eth-spot/daily-net-inflow",
                        headers={"apiKey": SOSOVALUE_KEY})
        btc = await get(s, "https://sosovalue.com/api/etf/us-btc-spot/daily-net-inflow",
                        headers={"apiKey": SOSOVALUE_KEY})
        return {"eth": eth, "btc": btc}
    except Exception as e:
        print(f"[data] sosovalue: {e}")
        return None


# ─── parallel orchestration ───────────────────────────────────────────────────

async def fetch_all_data() -> Dict:
    connector = aiohttp.TCPConnector(limit=20, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as s:
        (
            eth_cg, btc_cg, global_cg,
            eth_7d, eth_200d,
            eth_cdc, btc_cdc,
            eth_4h, eth_1d,
            fng, eth_fng,
            gas,
            lido, lst,
            reddit_eth, reddit_cc,
            cq_flows, cq_funding, cq_oi, cq_ls, cq_liq,
            etf,
        ) = await asyncio.gather(
            safe(fetch_eth_coingecko(s)),
            safe(fetch_btc_coingecko(s)),
            safe(fetch_global_coingecko(s)),
            safe(fetch_eth_history_7d(s)),
            safe(fetch_eth_history_200d(s)),
            safe(fetch_eth_ticker_cdc(s)),
            safe(fetch_btc_ticker_cdc(s)),
            safe(fetch_eth_candles_4h(s)),
            safe(fetch_eth_candles_1d(s)),
            safe(fetch_fear_greed(s)),
            safe(fetch_eth_fear_greed(s)),
            safe(fetch_gas(s)),
            safe(fetch_defillama_lido(s)),
            safe(fetch_defillama_lst(s)),
            safe(fetch_reddit(s, "ethereum")),
            safe(fetch_reddit(s, "CryptoCurrency")),
            safe(fetch_cq(s, "/eth/exchange-flows/inflow")),
            safe(fetch_cq(s, "/eth/derivatives/funding-rates")),
            safe(fetch_cq(s, "/eth/derivatives/open-interest")),
            safe(fetch_cq(s, "/eth/derivatives/long-short-ratio")),
            safe(fetch_cq(s, "/eth/derivatives/liquidation")),
            safe(fetch_sosovalue_etf(s)),
        )

    # ── parse 1D candles for technicals ──────────────────────────────────────
    candles_1d = _parse_cdc_candles(eth_1d)
    candles_4h = _parse_cdc_candles(eth_4h)
    closes_1d  = [c["close"] for c in candles_1d]
    closes_4h  = [c["close"] for c in candles_4h]

    tech_1d = summarize(closes_1d, candles_1d) if closes_1d else {}
    rsi_4h  = None
    if closes_4h:
        from services.technicals import rsi as calc_rsi, latest
        rsi_4h = latest(calc_rsi(closes_4h, 14))

    # ── parse CoinGecko price history ─────────────────────────────────────────
    cg_200d_prices = _parse_cg_prices(eth_200d)
    cg_7d_prices   = _parse_cg_prices(eth_7d)

    # ── parse Reddit sentiment ────────────────────────────────────────────────
    reddit_summary = _parse_reddit(reddit_eth, reddit_cc)

    # ── parse F&G ────────────────────────────────────────────────────────────
    fng_latest  = _safe_get(fng,     "data", 0, "value")
    fng_7d      = [d.get("value") for d in (_safe_get(fng, "data") or [])]
    eth_fng_val = _safe_get(eth_fng, "value")

    # ── parse CryptoQuant ─────────────────────────────────────────────────────
    cq_data = {
        "exchange_inflow": _cq_last(cq_flows,   "inflow_mean"),
        "funding_rate":    _cq_last(cq_funding,  "funding_rate"),
        "open_interest":   _cq_last(cq_oi,       "open_interest"),
        "long_short_ratio":_cq_last(cq_ls,       "long_short_ratio"),
        "liquidations_long":  _cq_last(cq_liq,   "liquidations_long"),
        "liquidations_short": _cq_last(cq_liq,   "liquidations_short"),
    }

    # ── parse staking (DefiLlama) ─────────────────────────────────────────────
    staking = _parse_staking(lido)

    # ── assemble payload ──────────────────────────────────────────────────────
    return {
        "timestamp": int(time.time()),
        "eth": {
            "price":       _safe_get(eth_cg,  "market_data", "current_price", "usd"),
            "price_24h_high": _safe_get(eth_cg, "market_data", "high_24h", "usd"),
            "price_24h_low":  _safe_get(eth_cg, "market_data", "low_24h",  "usd"),
            "change_24h":  _safe_get(eth_cg,  "market_data", "price_change_percentage_24h"),
            "volume_24h":  _safe_get(eth_cg,  "market_data", "total_volume", "usd"),
            "market_cap":  _safe_get(eth_cg,  "market_data", "market_cap",   "usd"),
            "cdc_last":    _safe_get(eth_cdc, "result", "data", "a"),  # ask price
        },
        "btc": {
            "price":       _safe_get(btc_cg,  "market_data", "current_price", "usd"),
            "change_24h":  _safe_get(btc_cg,  "market_data", "price_change_percentage_24h"),
            "dominance":   _safe_get(global_cg, "data", "market_cap_percentage", "btc"),
            "cdc_last":    _safe_get(btc_cdc, "result", "data", "a"),
        },
        "weekly_range": {
            "high": max((p for p in cg_7d_prices), default=None),
            "low":  min((p for p in cg_7d_prices), default=None),
            "avg":  (sum(cg_7d_prices) / len(cg_7d_prices)) if cg_7d_prices else None,
        },
        "fear_greed": {
            "value":          int(fng_latest) if fng_latest else None,
            "classification": _safe_get(fng, "data", 0, "value_classification"),
            "7d_trend":       fng_7d,
        },
        "eth_fear_greed": {
            "value": int(eth_fng_val) if eth_fng_val is not None else None,
        },
        "technicals": {
            **tech_1d,
            "rsi_4h": rsi_4h,
        },
        "gas": {
            "safe":    _safe_get(gas, "result", "SafeGasPrice"),
            "propose": _safe_get(gas, "result", "ProposeGasPrice"),
            "fast":    _safe_get(gas, "result", "FastGasPrice"),
        },
        "staking": staking,
        "derivatives": cq_data,
        "etf_flows": etf,
        "reddit": reddit_summary,
        "candles_1d": candles_1d[-100:],  # last 100 for chart
        "candles_4h": candles_4h[-100:],
        "prices_200d": cg_200d_prices,    # for MA overlay
    }


# ─── parsers ──────────────────────────────────────────────────────────────────

def _parse_cdc_candles(raw) -> list:
    """Convert Crypto.com candlestick response to [{time,open,high,low,close,volume}]."""
    try:
        items = raw["result"]["data"]
        out = []
        for c in items:
            # CDC format: t=timestamp(ms), o, h, l, c, v
            out.append({
                "time":   int(c["t"]) // 1000,
                "open":   float(c["o"]),
                "high":   float(c["h"]),
                "low":    float(c["l"]),
                "close":  float(c["c"]),
                "volume": float(c.get("v", 0)),
            })
        return sorted(out, key=lambda x: x["time"])
    except Exception:
        return []


def _parse_cg_prices(raw) -> list:
    """Extract list of closing prices from CoinGecko market_chart response."""
    try:
        return [p[1] for p in raw["prices"]]
    except Exception:
        return []


def _parse_reddit(eth_raw, cc_raw) -> dict:
    posts = []
    for raw in (eth_raw, cc_raw):
        try:
            children = raw["data"]["children"]
            for c in children[:10]:
                d = c["data"]
                posts.append({
                    "title":       d.get("title", ""),
                    "upvote_ratio": d.get("upvote_ratio", 0),
                    "score":       d.get("score", 0),
                    "subreddit":   d.get("subreddit", ""),
                })
        except Exception:
            pass

    bullish_kw  = ["bull", "pump", "moon", "ath", "breakout", "long", "buy", "accumulate"]
    bearish_kw  = ["bear", "dump", "crash", "short", "sell", "down", "red", "rekt"]
    bull_count  = sum(1 for p in posts if any(k in p["title"].lower() for k in bullish_kw))
    bear_count  = sum(1 for p in posts if any(k in p["title"].lower() for k in bearish_kw))
    total       = max(len(posts), 1)

    return {
        "post_count":    len(posts),
        "bull_pct":      round(bull_count / total * 100, 1),
        "bear_pct":      round(bear_count / total * 100, 1),
        "top_titles":    [p["title"] for p in posts[:5]],
    }


def _parse_staking(lido_raw) -> dict:
    try:
        tvl = lido_raw.get("tvl", [])
        latest_tvl = tvl[-1]["totalLiquidityUSD"] if tvl else None
        return {"lido_tvl_usd": latest_tvl}
    except Exception:
        return {}


def _cq_last(raw, field: str):
    """Extract the last value of a field from a CryptoQuant response."""
    try:
        return raw["result"]["data"][-1][field]
    except Exception:
        return None


def _safe_get(obj, *keys):
    """Safely traverse nested dicts/lists."""
    for k in keys:
        if obj is None:
            return None
        if isinstance(obj, list):
            try:
                obj = obj[int(k)]
            except Exception:
                return None
        elif isinstance(obj, dict):
            obj = obj.get(k)
        else:
            return None
    return obj


# ─── Flask route ──────────────────────────────────────────────────────────────

@data_bp.route("/data")
def get_data():
    result = asyncio.run(fetch_all_data())
    return jsonify(result)
