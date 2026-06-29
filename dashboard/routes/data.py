"""
GET /dashboard/api/data
Fires ~15 external API calls concurrently via aiohttp and returns a single JSON payload
containing all data needed for the dashboard.
"""

import asyncio
import math
import os
import re
import time
from typing import Any, Dict, List, Optional

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
    """Parse ETH F&G from ethereumfear.com Next.js data blob: pageProps.index"""
    try:
        async with s.get("https://ethereumfear.com/", headers=UA_HEADERS, timeout=TIMEOUT) as r:
            html = await r.text()
        # Value lives in __NEXT_DATA__ JSON as {"props":{"pageProps":{"index":"21",...}}}
        patterns = [
            r'"pageProps"\s*:\s*\{[^}]*"index"\s*:\s*"(\d+)"',
            r'"index"\s*:\s*"(\d+)"',   # fallback — first numeric "index" field
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
    # V2 API (V1 deprecated June 2025)
    return await get(s, "https://api.etherscan.io/v2/api", params={
        "chainid": "1", "module": "gastracker", "action": "gasoracle", "apikey": ETHERSCAN_KEY,
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


# ── OKX public API (no key — replaces CryptoQuant derivatives) ───────────────
# Binance is geo-restricted on this server; OKX is accessible.

OKX_BASE = "https://www.okx.com/api/v5"

async def fetch_funding_rate(s):
    """ETH-USDT-SWAP funding rate from OKX — free, no key."""
    return await get(s, f"{OKX_BASE}/public/funding-rate",
                     params={"instId": "ETH-USDT-SWAP"})


async def fetch_open_interest(s):
    """ETH-USDT-SWAP open interest from OKX — free, no key."""
    return await get(s, f"{OKX_BASE}/public/open-interest",
                     params={"instId": "ETH-USDT-SWAP"})


async def fetch_long_short_ratio(s):
    """ETH long/short account ratio from OKX — free, no key."""
    return await get(s, f"{OKX_BASE}/rubik/stat/contracts/long-short-account-ratio-contract",
                     params={"instId": "ETH-USDT-SWAP", "period": "1H"})


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


async def fetch_eth_supply(s):
    """Etherscan ethsupply2: circulating supply, total burned, ETH2 staking (all in Wei)."""
    if not ETHERSCAN_KEY:
        return None
    return await get(s, "https://api.etherscan.io/v2/api", params={
        "chainid": "1", "module": "stats", "action": "ethsupply2", "apikey": ETHERSCAN_KEY,
    })


async def fetch_beaconchain(s):
    """beaconcha.in latest epoch: validator count → total ETH staked."""
    return await get(s, "https://beaconcha.in/api/v1/epoch/latest", headers=UA_HEADERS)


async def fetch_btc_history_30d(s):
    """BTC 30-day daily price history — used for ETH/BTC correlation and beta."""
    return await get(s, f"{CG_BASE}/coins/bitcoin/market_chart", headers=CG_HEADERS,
                     params={"vs_currency": "usd", "days": "30", "interval": "daily"})


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
            gas, eth_supply,
            lido, lst,
            reddit_eth, reddit_cc,
            cq_flows, cq_funding, cq_oi, cq_ls, cq_liq,
            etf, beaconchain, btc_30d,
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
            safe(fetch_eth_supply(s)),
            safe(fetch_defillama_lido(s)),
            safe(fetch_defillama_lst(s)),
            safe(fetch_reddit(s, "ethereum")),
            safe(fetch_reddit(s, "CryptoCurrency")),
            safe(fetch_cq(s, "/eth/exchange-flows/inflow")),   # requires Professional — returns None on Basic
            safe(fetch_funding_rate(s)),
            safe(fetch_open_interest(s)),
            safe(fetch_long_short_ratio(s)),
            safe(fetch_cq(s, "/eth/derivatives/liquidation")), # requires Professional — returns None on Basic
            safe(fetch_sosovalue_etf(s)),
            safe(fetch_beaconchain(s)),
            safe(fetch_btc_history_30d(s)),
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

    # ── parse OKX derivatives ─────────────────────────────────────────────────
    # cq_funding → OKX funding-rate:  {"data": [{"fundingRate": "-0.000029"}]}
    # cq_oi      → OKX open-interest: {"data": [{"oi": "7464177", "oiUsd": "1173741988"}]}
    # cq_ls      → OKX LS ratio:      {"data": [["timestamp", "2.941"]]}
    okx_funding = None
    okx_oi_usd  = None
    okx_ls      = None
    try:
        okx_funding = float(cq_funding["data"][0]["fundingRate"]) * 100 if cq_funding else None
    except Exception: pass
    try:
        okx_oi_usd = float(cq_oi["data"][0]["oiUsd"]) if cq_oi else None
    except Exception: pass
    try:
        okx_ls = float(cq_ls["data"][0][1]) if cq_ls else None
    except Exception: pass

    cq_data = {
        "exchange_inflow":    _cq_last(cq_flows, "inflow_mean"),  # None on CryptoQuant Basic
        "funding_rate":       round(okx_funding, 4) if okx_funding is not None else None,
        "open_interest_usd":  round(okx_oi_usd, 0) if okx_oi_usd is not None else None,
        "long_short_ratio":   round(okx_ls, 3) if okx_ls is not None else None,
        "liquidations_long":  _cq_last(cq_liq, "liquidations_long"),
        "liquidations_short": _cq_last(cq_liq, "liquidations_short"),
        "source": "OKX (funding/OI/LS)",
    }

    # ── parse §10 supply/burn (Etherscan ethsupply2) ─────────────────────────
    supply_data = _parse_supply(eth_supply)

    # ── parse §11 staking (beaconcha.in + DefiLlama) ──────────────────────────
    staking = _parse_staking(lido, lst, beaconchain)

    # ── parse §18 BTC/ETH correlation ─────────────────────────────────────────
    btc_30d_prices = _parse_cg_prices(btc_30d)
    eth_prices_for_corr = cg_200d_prices[-31:] if len(cg_200d_prices) >= 31 else cg_200d_prices
    corr_30d = None
    beta_30d  = None
    if len(btc_30d_prices) >= 2 and len(eth_prices_for_corr) >= 2:
        eth_rets = _daily_returns(eth_prices_for_corr)
        btc_rets = _daily_returns(btc_30d_prices)
        n = min(len(eth_rets), len(btc_rets))
        if n >= 2:
            corr_30d = _pearson(eth_rets[-n:], btc_rets[-n:])
            beta_30d = _beta_calc(eth_rets[-n:], btc_rets[-n:])

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
            "price":         _safe_get(btc_cg,  "market_data", "current_price", "usd"),
            "change_24h":    _safe_get(btc_cg,  "market_data", "price_change_percentage_24h"),
            "dominance":     _safe_get(global_cg, "data", "market_cap_percentage", "btc"),
            "cdc_last":      _safe_get(btc_cdc, "result", "data", "a"),
            "correlation_30d": corr_30d,
            "beta_30d":      beta_30d,
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
        "supply": supply_data,
        "staking": staking,
        "derivatives": cq_data,
        "etf_flows": etf,
        "exchange_flows": {
            "net_inflow_eth": cq_data.get("exchange_inflow"),
            "source": "CryptoQuant" if cq_data.get("exchange_inflow") is not None else "unavailable — CryptoQuant Professional required",
        },
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


def _parse_supply(raw) -> dict:
    """Parse Etherscan ethsupply2. Values are in Wei — convert to whole ETH."""
    try:
        r = (raw or {}).get("result", {})
        def _wei(key):
            v = r.get(key)
            return round(int(v) / 1e18) if v else None
        circulating = _wei("EthSupply")
        burned       = _wei("BurntFees")
        staked_eth2  = _wei("Eth2Staking")
        rewards      = _wei("ValidatorRewards")
        return {
            "circulating_eth":   circulating,
            "total_burned_eth":  burned,
            "eth2_staking_eth":  staked_eth2,
            "validator_rewards": rewards,
        }
    except Exception as e:
        print(f"[data] supply parse: {e}")
        return {}


def _parse_staking(lido_raw, lst_raw=None, beacon_raw=None) -> dict:
    result = {}

    # Total ETH staked + validator count from beaconcha.in
    try:
        d = (beacon_raw or {}).get("data", {})
        validators = d.get("validatorscount") or d.get("activevalidators")
        if validators:
            result["total_validators"]  = int(validators)
            result["total_eth_staked"]  = int(validators) * 32
    except Exception:
        pass

    # Staking APR from DefiLlama LST pools (stETH / wstETH)
    try:
        pools = (lst_raw or {}).get("data", lst_raw) if isinstance(lst_raw, dict) else (lst_raw or [])
        if isinstance(pools, list):
            steth_pools = [
                p for p in pools
                if isinstance(p, dict)
                and p.get("symbol", "").lower() in ("steth", "wsteth")
                and p.get("chain", "").lower() == "ethereum"
            ]
            if steth_pools:
                apy = max(p.get("apy", 0) or 0 for p in steth_pools)
                result["staking_apr_pct"] = round(float(apy), 2)
    except Exception:
        pass

    # Lido TVL from DefiLlama protocol endpoint
    try:
        tvl = (lido_raw or {}).get("tvl", [])
        if tvl:
            result["lido_tvl_usd"] = tvl[-1]["totalLiquidityUSD"]
    except Exception:
        pass

    return result


def _daily_returns(prices: List[float]) -> List[float]:
    if len(prices) < 2:
        return []
    return [(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]


def _pearson(x: List[float], y: List[float]) -> Optional[float]:
    n = len(x)
    if n < 2:
        return None
    mx, my = sum(x) / n, sum(y) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    sx  = math.sqrt(sum((xi - mx) ** 2 for xi in x))
    sy  = math.sqrt(sum((yi - my) ** 2 for yi in y))
    if sx == 0 or sy == 0:
        return None
    return round(cov / (sx * sy), 3)


def _beta_calc(eth_rets: List[float], btc_rets: List[float]) -> Optional[float]:
    n = len(eth_rets)
    if n < 2:
        return None
    mb = sum(btc_rets) / n
    me = sum(eth_rets) / n
    cov = sum((e - me) * (b - mb) for e, b in zip(eth_rets, btc_rets)) / n
    var = sum((b - mb) ** 2 for b in btc_rets) / n
    if var == 0:
        return None
    return round(cov / var, 3)


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


# ─── 5-minute TTL cache ───────────────────────────────────────────────────────

_data_cache: dict = {}
DATA_CACHE_TTL = 5 * 60  # seconds


# ─── Flask route ──────────────────────────────────────────────────────────────

@data_bp.route("/data")
def get_data():
    now = time.time()
    if _data_cache.get("ts") and (now - _data_cache["ts"]) < DATA_CACHE_TTL:
        print("[data] serving from cache")
        return jsonify(_data_cache["data"])
    result = asyncio.run(fetch_all_data())
    _data_cache["ts"]   = now
    _data_cache["data"] = result
    return jsonify(result)
