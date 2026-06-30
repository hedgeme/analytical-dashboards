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
CMC_KEY          = os.getenv("CMC_API_KEY", "")

CG_BASE  = "https://api.coingecko.com/api/v3"
CDC_BASE = "https://api.crypto.com/exchange/v1/public"
CQ_BASE  = "https://api.cryptoquant.com/v1"
CMC_BASE = "https://pro-api.coinmarketcap.com"

CG_HEADERS  = {"x-cg-demo-api-key": COINGECKO_KEY} if COINGECKO_KEY else {}
CQ_HEADERS  = {"Authorization": f"Bearer {CRYPTOQUANT_KEY}"} if CRYPTOQUANT_KEY else {}
CMC_HEADERS = {"X-CMC_PRO_API_KEY": CMC_KEY, "Accept": "application/json"} if CMC_KEY else {}
UA_HEADERS  = {"User-Agent": "Mozilla/5.0 (ETH-Dashboard/1.0)"}

HTX_BASE = "https://api.hbdm.com"

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


# ── ultrasound.money public API (no key, no auth) ────────────────────────────
USM_BASE = "https://ultrasound.money"

async def fetch_usm_burn_rates(s):
    """Burn rate in ETH/min across time frames (m5, h1, d1, d7, d30)."""
    return await get(s, f"{USM_BASE}/api/v2/fees/burn-rates")


async def fetch_usm_gauge_rates(s):
    """Annual issuance rate, annual burn rate, supply growth rate — key for §10 signal."""
    return await get(s, f"{USM_BASE}/api/v2/fees/gauge-rates")


async def fetch_usm_supply_parts(s):
    """Current ETH supply broken down: beacon balances, execution layer, deposits."""
    return await get(s, f"{USM_BASE}/api/v2/fees/supply-parts")


async def fetch_usm_scarcity(s):
    """Scarcity metrics: total ETH staked, burned, locked with amounts and start dates."""
    return await get(s, f"{USM_BASE}/api/fees/scarcity")


async def fetch_defillama_cexs(s):
    """DefiLlama CEX overview — public, no key. 90 exchanges with 24h/1w/1m net inflows."""
    return await get(s, "https://api.llama.fi/cexs")


# ── TradingView scanner (no key, public) ──────────────────────────────────────
TV_SCANNER = "https://scanner.tradingview.com/america/scan"
TV_ETH_TICKERS = ["NASDAQ:ETHA", "CBOE:FETH", "CBOE:ETHV", "AMEX:ETHE",
                   "AMEX:ETH",   "AMEX:ETHW", "CBOE:TETH", "CBOE:QETH"]
TV_BTC_TICKERS = ["NASDAQ:IBIT", "CBOE:FBTC",  "AMEX:GBTC", "AMEX:BTC",
                   "CBOE:BTCO",  "CBOE:BTCW"]
TV_COLS = ["name", "description", "close", "volume", "change",
           "average_volume_10d_calc", "average_volume_30d_calc", "relative_volume_10d_calc"]

async def fetch_tv_etfs(s):
    """TradingView scanner: price, volume, rel-vol for major ETH + BTC spot ETFs. No key."""
    payload = {
        "symbols": {"tickers": TV_ETH_TICKERS + TV_BTC_TICKERS},
        "columns": TV_COLS,
    }
    async with s.post(TV_SCANNER, json=payload,
                      headers={**UA_HEADERS, "Content-Type": "application/json"},
                      timeout=TIMEOUT) as r:
        r.raise_for_status()
        return await r.json(content_type=None)


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


SOSO_BASE    = "https://openapi.sosovalue.com/openapi/v1"
SOSO_HEADERS = {"x-soso-api-key": SOSOVALUE_KEY, **UA_HEADERS} if SOSOVALUE_KEY else {}

async def fetch_sosovalue_etf(s):
    """ETH spot ETF aggregate daily/weekly/monthly net flows from SoSoValue.
    Returns summary-history with 3 rows per date (daily, weekly, monthly windows)."""
    if not SOSOVALUE_KEY:
        return None
    return await get(s, f"{SOSO_BASE}/etfs/summary-history",
                     params={"symbol": "ETH", "country_code": "US", "limit": "3"},
                     headers=SOSO_HEADERS)


async def fetch_eth_supply(s):
    """Etherscan ethsupply2: circulating supply, total burned, beacon deposits (all in Wei)."""
    if not ETHERSCAN_KEY:
        return None
    return await get(s, "https://api.etherscan.io/v2/api", params={
        "chainid": "1", "module": "stats", "action": "ethsupply2", "apikey": ETHERSCAN_KEY,
    })


async def fetch_btc_history_30d(s):
    """BTC 30-day daily price history — used for ETH/BTC correlation and beta."""
    return await get(s, f"{CG_BASE}/coins/bitcoin/market_chart", headers=CG_HEADERS,
                     params={"vs_currency": "usd", "days": "30", "interval": "daily"})


# ── CoinMarketCap API (Free/Basic tier) ───────────────────────────────────────

async def fetch_cmc_fng(s):
    """CMC Fear & Greed Index — current value + 7-day history. More authoritative than alternative.me."""
    if not CMC_KEY:
        return None
    latest = await get(s, f"{CMC_BASE}/v3/fear-and-greed/latest", headers=CMC_HEADERS)
    hist   = await get(s, f"{CMC_BASE}/v3/fear-and-greed/historical",
                       headers=CMC_HEADERS, params={"limit": "7"})
    return {"latest": latest, "historical": hist}


async def fetch_cmc_global(s):
    """CMC global metrics: market cap, BTC/ETH dominance, DeFi vol, stablecoin cap, derivatives vol."""
    if not CMC_KEY:
        return None
    return await get(s, f"{CMC_BASE}/v1/global-metrics/quotes/latest", headers=CMC_HEADERS)


async def fetch_cmc_quotes(s):
    """CMC ETH+BTC quotes with CEX/DEX volume split and percent changes across all timeframes."""
    if not CMC_KEY:
        return None
    return await get(s, f"{CMC_BASE}/v1/cryptocurrency/quotes/latest",
                     headers=CMC_HEADERS, params={"symbol": "ETH,BTC", "convert": "USD"})


# ── HTX USDT-M Linear Swap (public, no key) ───────────────────────────────────

async def fetch_htx_funding(s):
    """ETH-USDT USDT-M perpetual funding rate from HTX (v1 — v3 does not exist)."""
    return await get(s, f"{HTX_BASE}/linear-swap-api/v1/swap_funding_rate",
                     params={"contract_code": "ETH-USDT"})

async def fetch_htx_oi(s):
    """Current open interest for ETH-USDT linear swap (USDT-denominated)."""
    return await get(s, f"{HTX_BASE}/linear-swap-api/v1/swap_open_interest",
                     params={"contract_code": "ETH-USDT"})

async def fetch_htx_ls(s):
    """Elite account long/short ratio for ETH-USDT linear swap."""
    return await get(s, f"{HTX_BASE}/linear-swap-api/v1/swap_elite_account_ratio",
                     params={"contract_code": "ETH-USDT", "period": "5min"})

async def fetch_htx_oi_history(s):
    """25 hourly OI snapshots in USDT — used for 24h OI trend calculation."""
    return await get(s, f"{HTX_BASE}/linear-swap-api/v1/swap_his_open_interest",
                     params={"contract_code": "ETH-USDT", "period": "60min",
                             "size": "25", "amount_type": "1"})

async def fetch_htx_liquidations(s):
    """Last 24h ETH-USDT liquidation orders from HTX (2 pages = up to 100 orders)."""
    p1, p2 = await asyncio.gather(
        safe(get(s, f"{HTX_BASE}/linear-swap-api/v1/swap_liquidation_orders",
                 params={"contract_code": "ETH-USDT", "trade_type": "0",
                         "create_date": "1", "page_index": "1", "page_size": "50"})),
        safe(get(s, f"{HTX_BASE}/linear-swap-api/v1/swap_liquidation_orders",
                 params={"contract_code": "ETH-USDT", "trade_type": "0",
                         "create_date": "1", "page_index": "2", "page_size": "50"})),
    )
    orders = []
    for page in (p1, p2):
        orders.extend((_safe_get(page, "data", "orders") or []))
    return orders

async def fetch_okx_liquidations(s):
    """OKX ETH-USDT-SWAP filled liquidation orders (most recent 100)."""
    return await get(s, f"{OKX_BASE}/public/liquidation-orders",
                     params={"instType": "SWAP", "uly": "ETH-USDT",
                             "state": "filled", "limit": "100"})


# ── Beacon chain staking delta (public RPC + Etherscan) ───────────────────────
ETH_PUBLIC_RPC    = "https://eth.drpc.org"
DEPOSIT_CONTRACT  = "0x00000000219ab540356cBB839Cbe05303d7705Fa"
DEPOSIT_TOPIC     = "0x649bbc62d0e31342afea4e5cd82d4049e7e1ee912fc0889aa790803be39038c5"
RPC_HEADERS       = {**UA_HEADERS, "Content-Type": "application/json"}

async def _rpc(s, method, params=None):
    payload = {"jsonrpc": "2.0", "method": method, "params": params or [], "id": 1}
    async with s.post(ETH_PUBLIC_RPC, json=payload, headers=RPC_HEADERS, timeout=TIMEOUT) as r:
        d = await r.json(content_type=None)
        return d.get("result")

async def fetch_beacon_deposits_24h(s):
    """Count ETH2 DepositEvent logs in the last ~7200 blocks (24h). Each event = 32 ETH staked."""
    if not ETHERSCAN_KEY:
        return None
    curr = await _rpc(s, "eth_blockNumber")
    if not curr:
        return None
    from_block = int(curr, 16) - 7200
    p1, p2 = await asyncio.gather(
        safe(get(s, "https://api.etherscan.io/v2/api", params={
            "chainid": "1", "module": "logs", "action": "getLogs",
            "address": DEPOSIT_CONTRACT, "fromBlock": str(from_block), "toBlock": "latest",
            "topic0": DEPOSIT_TOPIC, "page": "1", "offset": "1000", "apikey": ETHERSCAN_KEY,
        })),
        safe(get(s, "https://api.etherscan.io/v2/api", params={
            "chainid": "1", "module": "logs", "action": "getLogs",
            "address": DEPOSIT_CONTRACT, "fromBlock": str(from_block), "toBlock": "latest",
            "topic0": DEPOSIT_TOPIC, "page": "2", "offset": "1000", "apikey": ETHERSCAN_KEY,
        })),
    )
    count = len((p1 or {}).get("result") or []) + len((p2 or {}).get("result") or [])
    return {"deposits_24h": count, "eth_staked_24h": count * 32}

async def fetch_beacon_withdrawal_sample(s):
    """Sample 6 blocks spread over 24h via public ETH RPC to estimate daily withdrawal rate."""
    curr = await _rpc(s, "eth_blockNumber")
    if not curr:
        return None
    curr_num = int(curr, 16)
    sample_blocks = [curr_num - i * 1200 for i in range(6)]  # one sample every 4h

    async def _block_withdrawals(blk_num):
        result = await _rpc(s, "eth_getBlockByNumber", [hex(blk_num), False])
        if not isinstance(result, dict):
            return None
        ws = result.get("withdrawals", [])
        return sum(int(w["amount"], 16) / 1e9 for w in ws)

    samples = await asyncio.gather(*[safe(_block_withdrawals(b)) for b in sample_blocks])
    valid = [v for v in samples if v is not None]
    if not valid:
        return None
    avg = sum(valid) / len(valid)
    return {
        "avg_eth_per_block": round(avg, 4),
        "eth_unstaked_24h_est": round(avg * 7200),
        "sample_count": len(valid),
    }


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
            cq_flows, cq_funding, cq_oi, cq_ls, cq_liq,
            etf, btc_30d,
            usm_burn, usm_gauge, usm_supply, usm_scarcity,
            cex_flows, tv_etfs,
            cmc_fng, cmc_global, cmc_quotes,
            htx_funding, htx_oi, htx_ls, htx_oi_hist, htx_liqs, okx_liqs,
            beacon_deps, beacon_ws,
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
            safe(fetch_cq(s, "/eth/exchange-flows/inflow")),   # requires CryptoQuant Professional
            safe(fetch_funding_rate(s)),
            safe(fetch_open_interest(s)),
            safe(fetch_long_short_ratio(s)),
            safe(fetch_cq(s, "/eth/derivatives/liquidation")), # requires CryptoQuant Professional
            safe(fetch_sosovalue_etf(s)),                      # SoSoValue openapi.sosovalue.com
            safe(fetch_btc_history_30d(s)),
            safe(fetch_usm_burn_rates(s)),
            safe(fetch_usm_gauge_rates(s)),
            safe(fetch_usm_supply_parts(s)),
            safe(fetch_usm_scarcity(s)),
            safe(fetch_defillama_cexs(s)),
            safe(fetch_tv_etfs(s)),
            safe(fetch_cmc_fng(s)),
            safe(fetch_cmc_global(s)),
            safe(fetch_cmc_quotes(s)),
            safe(fetch_htx_funding(s)),
            safe(fetch_htx_oi(s)),
            safe(fetch_htx_ls(s)),
            safe(fetch_htx_oi_history(s)),
            safe(fetch_htx_liquidations(s)),
            safe(fetch_okx_liquidations(s)),
            safe(fetch_beacon_deposits_24h(s)),
            safe(fetch_beacon_withdrawal_sample(s)),
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

    # ── parse F&G ────────────────────────────────────────────────────────────
    fng_latest  = _safe_get(fng,     "data", 0, "value")
    fng_7d      = [d.get("value") for d in (_safe_get(fng, "data") or [])]
    eth_fng_val = _safe_get(eth_fng, "value")

    # ── parse OKX derivatives ─────────────────────────────────────────────────
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

    # ── parse HTX derivatives ─────────────────────────────────────────────────
    htx_der  = _parse_htx_derivatives(htx_funding, htx_oi, htx_ls, htx_oi_hist)

    # ── parse combined liquidations (OKX + HTX) ───────────────────────────────
    liq_data = _parse_liquidations(htx_liqs, okx_liqs)

    # ── parse §10 supply/burn (Etherscan ethsupply2) ─────────────────────────
    supply_data = _parse_supply(eth_supply)

    # ── parse §11 staking (DefiLlama + beacon chain) ─────────────────────────
    staking = _parse_staking(lido, lst)

    # ── parse 24h staking delta (Etherscan deposits + drpc.org withdrawals) ───
    staked_24h   = (beacon_deps or {}).get("eth_staked_24h")
    deposits_24h = (beacon_deps or {}).get("deposits_24h")
    unstaked_24h = (beacon_ws  or {}).get("eth_unstaked_24h_est")
    net_stake_24h = (round(staked_24h - unstaked_24h)
                     if staked_24h is not None and unstaked_24h is not None else None)
    staking["staked_24h_eth"]      = staked_24h
    staking["validators_entered_24h"] = deposits_24h
    staking["unstaked_24h_eth_est"] = unstaked_24h
    staking["net_stake_change_24h"] = net_stake_24h

    # ── parse §10 ultrasound.money supply/burn ────────────────────────────────
    usm_data = _parse_usm(usm_burn, usm_gauge, usm_supply, usm_scarcity)

    # ── parse §16 exchange flows (DefiLlama CEX) ──────────────────────────────
    cex_data = _parse_cex_flows(cex_flows)

    # ── parse §6 ETF flows (SoSoValue — real daily net inflows) ─────────────────
    soso_etf = _parse_soso_etf(etf)         # `etf` variable = fetch_sosovalue_etf result
    etf_tv   = _parse_tv_etfs(tv_etfs)      # TradingView volume proxy (kept as supplement)

    # ── parse CMC data ─────────────────────────────────────────────────────────
    cmc_data = _parse_cmc(cmc_fng, cmc_global, cmc_quotes)

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
    # CMC quotes supplement CoinGecko with CEX/DEX volume split and multi-timeframe % changes
    cmc_eth = cmc_data.get("eth", {})
    cmc_btc = cmc_data.get("btc", {})

    return {
        "timestamp": int(time.time()),
        "eth": {
            "price":          _safe_get(eth_cg,  "market_data", "current_price", "usd"),
            "price_24h_high": _safe_get(eth_cg,  "market_data", "high_24h", "usd"),
            "price_24h_low":  _safe_get(eth_cg,  "market_data", "low_24h",  "usd"),
            "change_24h":     _safe_get(eth_cg,  "market_data", "price_change_percentage_24h"),
            "change_7d":      cmc_eth.get("change_7d"),
            "change_30d":     cmc_eth.get("change_30d"),
            "volume_24h":     _safe_get(eth_cg,  "market_data", "total_volume", "usd"),
            "cex_volume_24h": cmc_eth.get("cex_volume_24h"),
            "dex_volume_24h": cmc_eth.get("dex_volume_24h"),
            "market_cap":     _safe_get(eth_cg,  "market_data", "market_cap", "usd"),
            "cdc_last":       _safe_get(eth_cdc, "result", "data", "a"),
        },
        "btc": {
            "price":           _safe_get(btc_cg,  "market_data", "current_price", "usd"),
            "change_24h":      _safe_get(btc_cg,  "market_data", "price_change_percentage_24h"),
            "change_7d":       cmc_btc.get("change_7d"),
            "change_30d":      cmc_btc.get("change_30d"),
            "dominance":       cmc_data.get("btc_dominance") or _safe_get(global_cg, "data", "market_cap_percentage", "btc"),
            "cdc_last":        _safe_get(btc_cdc, "result", "data", "a"),
            "correlation_30d": corr_30d,
            "beta_30d":        beta_30d,
        },
        "market": {
            "total_market_cap_usd":    cmc_data.get("total_market_cap_usd"),
            "total_volume_24h_usd":    cmc_data.get("total_volume_24h_usd"),
            "btc_dominance":           cmc_data.get("btc_dominance"),
            "eth_dominance":           cmc_data.get("eth_dominance"),
            "defi_volume_24h_usd":     cmc_data.get("defi_volume_24h_usd"),
            "stablecoin_market_cap":   cmc_data.get("stablecoin_market_cap"),
            "derivatives_volume_24h":  cmc_data.get("derivatives_volume_24h"),
            "active_cryptocurrencies": cmc_data.get("active_cryptocurrencies"),
            "source": "CoinMarketCap",
        },
        "weekly_range": {
            "high": max((p for p in cg_7d_prices), default=None),
            "low":  min((p for p in cg_7d_prices), default=None),
            "avg":  (sum(cg_7d_prices) / len(cg_7d_prices)) if cg_7d_prices else None,
        },
        "fear_greed": {
            # CMC F&G is primary; alternative.me is fallback
            "value":          cmc_data.get("fng_value") or (int(fng_latest) if fng_latest else None),
            "classification": cmc_data.get("fng_classification") or _safe_get(fng, "data", 0, "value_classification"),
            "7d_trend":       cmc_data.get("fng_7d_trend") or fng_7d,
            "source":         "CoinMarketCap" if cmc_data.get("fng_value") else "alternative.me",
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
        "supply": {**supply_data, **usm_data},
        "staking": staking,
        "derivatives": {
            "okx": {
                "funding_rate":      round(okx_funding, 4) if okx_funding is not None else None,
                "open_interest_usd": round(okx_oi_usd, 0)  if okx_oi_usd  is not None else None,
                "long_short_ratio":  round(okx_ls, 3)       if okx_ls       is not None else None,
            },
            "htx": htx_der,
            "liquidations": liq_data,
        },
        "etf_flows": {**soso_etf, "tv_proxy": etf_tv},
        "exchange_flows": cex_data,
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


def _parse_soso_etf(raw) -> dict:
    """Parse SoSoValue ETH ETF summary-history.
    The API returns 3 rows per date: smallest |net_inflow| = daily, next = weekly, largest = monthly."""
    try:
        entries = (raw or {}).get("data") or []
        if not entries:
            return {}
        latest_date = entries[0]["date"]
        day_rows = [e for e in entries if e["date"] == latest_date]
        # Sort ascending by absolute value so daily < weekly < monthly
        day_rows = sorted(day_rows, key=lambda e: abs(e.get("total_net_inflow") or 0))
        daily   = day_rows[0] if len(day_rows) > 0 else {}
        weekly  = day_rows[1] if len(day_rows) > 1 else {}
        monthly = day_rows[2] if len(day_rows) > 2 else {}
        return {
            "source":               "SoSoValue",
            "date":                 latest_date,
            "daily_net_inflow_usd":   daily.get("total_net_inflow"),
            "weekly_net_inflow_usd":  weekly.get("total_net_inflow"),
            "monthly_net_inflow_usd": monthly.get("total_net_inflow"),
            "total_aum_usd":          daily.get("total_net_assets"),
            "cum_net_inflow_usd":     daily.get("cum_net_inflow"),
            "total_volume_usd":       daily.get("total_value_traded"),
        }
    except Exception as e:
        print(f"[data] soso etf parse: {e}")
        return {}


def _parse_tv_etfs(raw) -> dict:
    """
    Parse TradingView scanner ETF data into §8-scoreable signals.
    Net dollar flows unavailable (paywalled everywhere); we use volume × price
    and relative volume as institutional sentiment proxy.
    """
    ETH_SET = {t.split(":")[1] for t in TV_ETH_TICKERS}
    BTC_SET = {t.split(":")[1] for t in TV_BTC_TICKERS}

    eth_etfs, btc_etfs = [], []
    try:
        for row in (raw or {}).get("data", []):
            ticker = row["s"].split(":")[1]
            cols   = TV_COLS
            vals   = row["d"]
            d = dict(zip(cols, vals))
            entry = {
                "ticker":      ticker,
                "name":        d.get("description"),
                "price":       d.get("close"),
                "volume":      d.get("volume"),
                "change_pct":  round(d["change"], 2) if d.get("change") is not None else None,
                "rel_vol_10d": round(d["relative_volume_10d_calc"], 2) if d.get("relative_volume_10d_calc") else None,
                "avg_vol_30d": d.get("average_volume_30d_calc"),
                "dollar_vol":  round(d["close"] * d["volume"] / 1e6, 1) if d.get("close") and d.get("volume") else None,
            }
            if ticker in ETH_SET:
                eth_etfs.append(entry)
            elif ticker in BTC_SET:
                btc_etfs.append(entry)

        def _summarise(etfs):
            valid = [e for e in etfs if e["change_pct"] is not None]
            if not valid:
                return {}
            avg_chg   = round(sum(e["change_pct"] for e in valid) / len(valid), 2)
            total_dvol = round(sum(e["dollar_vol"] or 0 for e in valid), 1)
            # Biggest ETF by dollar volume drives the signal
            lead  = max(valid, key=lambda e: e["dollar_vol"] or 0)
            rv    = lead.get("rel_vol_10d")
            # Sentiment: price up + rel_vol > 1 = inflow signal; price down + rel_vol > 1 = outflow
            if avg_chg > 0.5 and (rv or 1) >= 1.0:
                sentiment = "BULLISH"
            elif avg_chg < -0.5 and (rv or 1) >= 1.0:
                sentiment = "BEARISH"
            else:
                sentiment = "NEUTRAL"
            return {
                "avg_change_pct":    avg_chg,
                "total_dollar_vol_m": total_dvol,
                "lead_etf":          lead["ticker"],
                "lead_etf_name":     lead["name"],
                "lead_rel_vol":      rv,
                "sentiment":         sentiment,
                "etfs":              valid,
            }

        return {
            "source": "TradingView (volume proxy — net flows require paid API)",
            "eth":    _summarise(eth_etfs),
            "btc":    _summarise(btc_etfs),
        }
    except Exception as e:
        print(f"[data] tv_etf parse: {e}")
        return {"source": "TradingView", "error": str(e)}


def _parse_htx_derivatives(funding_raw, oi_raw, ls_raw, oi_hist_raw) -> dict:
    """Parse HTX USDT-M ETH-USDT linear swap derivatives into clean fields."""
    result = {}
    try:
        d = (funding_raw or {}).get("data", {})
        if isinstance(d, list):
            d = d[0] if d else {}
        fr = d.get("funding_rate")
        if fr is not None:
            result["funding_rate"] = round(float(fr) * 100, 4)
    except Exception as e:
        print(f"[data] htx funding: {e}")

    try:
        oi_list = (oi_raw or {}).get("data") or []
        if oi_list:
            val = oi_list[0].get("value")
            if val is not None:
                result["open_interest_usd"] = float(val)
    except Exception as e:
        print(f"[data] htx oi: {e}")

    try:
        ls_list = ((ls_raw or {}).get("data") or {}).get("list") or []
        if ls_list:
            buy  = float(ls_list[0].get("buy_ratio",  0) or 0)
            sell = float(ls_list[0].get("sell_ratio", 0) or 0)
            if sell > 0:
                result["long_short_ratio"] = round(buy / sell, 3)
    except Exception as e:
        print(f"[data] htx ls: {e}")

    try:
        ticks = (oi_hist_raw or {}).get("data", {}).get("tick") or []
        if len(ticks) >= 2:
            ticks_sorted = sorted(ticks, key=lambda x: x.get("ts", 0))
            oi_vals = [float(t["volume"]) for t in ticks_sorted if t.get("volume")]
            if len(oi_vals) >= 2:
                first, last = oi_vals[0], oi_vals[-1]
                pct = round((last - first) / first * 100, 2) if first != 0 else 0.0
                result["oi_24h_change_pct"] = pct
                result["oi_trend"] = "rising" if pct > 2 else "falling" if pct < -2 else "flat"
                result["oi_6h_snap_b"] = [round(v / 1e9, 2) for v in oi_vals[-7:]]
    except Exception as e:
        print(f"[data] htx oi_hist: {e}")

    return result


def _parse_liquidations(htx_liqs_raw, okx_liqs_raw) -> dict:
    """Aggregate raw liquidation orders from HTX + OKX into time-bucketed USD totals."""
    now_ms = time.time() * 1000
    cutoffs = {
        "1h":  now_ms - 3_600_000,
        "4h":  now_ms - 14_400_000,
        "12h": now_ms - 43_200_000,
        "24h": now_ms - 86_400_000,
    }
    long_usd  = {k: 0.0 for k in cutoffs}
    short_usd = {k: 0.0 for k in cutoffs}

    # HTX: direction="sell" = long was closed (liquidated long)
    #       direction="buy"  = short was closed (liquidated short)
    for order in (htx_liqs_raw or []):
        try:
            ts  = float(order.get("created_at", 0))
            px  = float(order.get("price",  0) or 0)
            vol = float(order.get("volume", 0) or 0)
            usd = vol * px  # contracts × price (ETH-USDT: 1 contract ≈ 0.01 ETH, directional signal is correct)
            bucket = long_usd if order.get("direction") == "sell" else short_usd
            for period, cutoff in cutoffs.items():
                if ts >= cutoff:
                    bucket[period] += usd
        except Exception:
            pass

    # OKX: data[].details[]; side="sell" = long liquidated, side="buy" = short liquidated
    for item in ((okx_liqs_raw or {}).get("data") or []):
        for detail in (item.get("details") or []):
            try:
                ts   = float(detail.get("ts",   0) or 0)
                sz   = float(detail.get("sz",   0) or 0)
                bkpx = float(detail.get("bkPx", 0) or 0)
                usd  = sz * bkpx  # OKX ETH-USDT-SWAP: 1 contract = 1 ETH
                bucket = long_usd if detail.get("side") == "sell" else short_usd
                for period, cutoff in cutoffs.items():
                    if ts >= cutoff:
                        bucket[period] += usd
            except Exception:
                pass

    result = {}
    for period in cutoffs:
        l, s = long_usd[period], short_usd[period]
        if l > 0 or s > 0:
            total = l + s
            result[period] = {
                "long_usd_m":  round(l / 1e6, 2),
                "short_usd_m": round(s / 1e6, 2),
                "total_usd_m": round(total / 1e6, 2),
                "bias": ("long_heavy" if l > s * 1.5
                         else "short_heavy" if s > l * 1.5
                         else "balanced"),
            }
    return result


def _parse_cmc(fng_raw, global_raw, quotes_raw) -> dict:
    """Parse CoinMarketCap Free-tier responses into dashboard-ready fields."""
    result = {}

    # Fear & Greed (primary)
    try:
        latest = (fng_raw or {}).get("latest", {}).get("data", {})
        if isinstance(latest, list):
            latest = latest[0] if latest else {}
        result["fng_value"]          = int(latest["value"]) if latest.get("value") else None
        result["fng_classification"] = latest.get("value_classification")
        # CMC historical F&G — try both known response shapes
        hist_raw  = (fng_raw or {}).get("historical", {})
        hist_data = (hist_raw.get("data") or {})
        if isinstance(hist_data, list):
            entries = hist_data
        elif isinstance(hist_data, dict):
            entries = hist_data.get("data_list") or []
        else:
            entries = []
        result["fng_7d_trend"] = [int(d["value"]) for d in entries if d.get("value")]
    except Exception as e:
        print(f"[data] cmc fng parse: {e}")

    # Global metrics
    try:
        q = (global_raw or {}).get("data", {}).get("quote", {}).get("USD", {})
        d = (global_raw or {}).get("data", {})
        result["total_market_cap_usd"]   = q.get("total_market_cap")
        result["total_volume_24h_usd"]   = q.get("total_volume_24h")
        result["btc_dominance"]          = d.get("btc_dominance")
        result["eth_dominance"]          = d.get("eth_dominance")
        result["active_cryptocurrencies"] = d.get("active_cryptocurrencies")
        result["defi_volume_24h_usd"]    = q.get("defi_volume_24h")
        result["stablecoin_market_cap"]  = q.get("stablecoin_market_cap")
        result["derivatives_volume_24h"] = q.get("derivatives_volume_24h")
    except Exception as e:
        print(f"[data] cmc global parse: {e}")

    # ETH + BTC quotes (CEX/DEX volume split, multi-timeframe changes)
    try:
        coins = (quotes_raw or {}).get("data", {})
        for symbol, key in [("ETH", "eth"), ("BTC", "btc")]:
            coin_list = coins.get(symbol)
            coin = coin_list[0] if isinstance(coin_list, list) else coin_list
            if not coin:
                continue
            q = coin.get("quote", {}).get("USD", {})
            result[key] = {
                "change_7d":      q.get("percent_change_7d"),
                "change_30d":     q.get("percent_change_30d"),
                "cex_volume_24h": q.get("cex_volume_24h"),
                "dex_volume_24h": q.get("dex_volume_24h"),
            }
    except Exception as e:
        print(f"[data] cmc quotes parse: {e}")

    return result


def _parse_cex_flows(raw) -> dict:
    """Parse DefiLlama CEX flows. Negative inflow = net outflow = accumulation (bullish)."""
    MAJOR = {"Binance", "OKX", "HTX", "Bybit", "Kraken", "Bitfinex", "KuCoin"}
    # Coinbase excluded — no public on-chain flow API
    try:
        cexs = (raw or {}).get("cexs", [])
        major = [x for x in cexs if x.get("name") in MAJOR]
        all_cexs = [x for x in cexs if x.get("inflows_24h") is not None]

        def _sum(lst, key):
            vals = [x.get(key) for x in lst if x.get(key) is not None]
            return round(sum(vals) / 1e6, 1) if vals else None  # convert to $M

        total_24h = _sum(all_cexs, "inflows_24h")
        total_1w   = _sum(all_cexs, "inflows_1w")

        breakdown = {
            x["name"]: {
                "inflow_24h_usd_m": round(x["inflows_24h"] / 1e6, 1) if x.get("inflows_24h") is not None else None,
                "inflow_1w_usd_m":  round(x["inflows_1w"]  / 1e6, 1) if x.get("inflows_1w")  is not None else None,
                "tvl_usd_b":        round(x["currentTvl"]  / 1e9, 2) if x.get("currentTvl")  is not None else None,
            }
            for x in major
        }

        # Signal: net negative = outflows = accumulation = bullish (+1 if < -$100M)
        direction = "outflow" if (total_24h or 0) < 0 else "inflow"
        return {
            "source": "DefiLlama",
            "total_24h_usd_m": total_24h,
            "total_1w_usd_m":  total_1w,
            "direction_24h":   direction,
            "exchanges":       breakdown,
        }
    except Exception as e:
        print(f"[data] cex flows parse: {e}")
        return {"source": "DefiLlama", "error": str(e)}


def _parse_usm(burn_raw, gauge_raw, supply_raw, scarcity_raw) -> dict:
    """Parse ultrasound.money API responses into clean supply/burn metrics."""
    result = {}
    try:
        # Burn rate: d1 window gives best daily signal
        d1_burn = (burn_raw or {}).get("d1", {}).get("rate", {})
        result["burn_rate_eth_per_min"] = d1_burn.get("eth_per_minute")
        result["burn_rate_eth_per_day"] = (
            round(d1_burn["eth_per_minute"] * 60 * 24, 2)
            if d1_burn.get("eth_per_minute") else None
        )
    except Exception:
        pass

    try:
        # Gauge rates: annual issuance, annual burn, net supply growth
        d1_gauge = (gauge_raw or {}).get("d1", {})
        result["issuance_rate_eth_per_year"]  = d1_gauge.get("issuance_rate_yearly", {}).get("eth")
        result["burn_rate_eth_per_year"]       = d1_gauge.get("burn_rate_yearly", {}).get("eth")
        result["supply_growth_rate_yearly"]    = d1_gauge.get("supply_growth_rate_yearly")
        # Positive growth_rate = inflationary; negative = deflationary
        sgr = d1_gauge.get("supply_growth_rate_yearly")
        if sgr is not None:
            result["is_deflationary"] = sgr < 0
        issuance = d1_gauge.get("issuance_rate_yearly", {}).get("eth")
        burn      = d1_gauge.get("burn_rate_yearly", {}).get("eth")
        if issuance and burn:
            issuance_day = float(issuance) / 365
            burn_day_yr  = float(burn) / 365
            result["issuance_eth_per_day"] = round(issuance_day, 2)
            # net_daily_eth > 0 means burn > issuance = supply decreasing = deflationary
            result["net_daily_eth"]        = round(burn_day_yr - issuance_day, 2)
            # supply_change_24h: negative = supply shrinking (deflationary)
            result["supply_change_24h"]    = round(issuance_day - burn_day_yr, 2)
    except Exception:
        pass

    try:
        # Supply parts: execution layer + beacon balances
        sp = supply_raw or {}
        # executionBalancesSum is in Wei (huge int-as-string), beacon values in Gwei
        exec_wei = sp.get("executionBalancesSum")
        beacon_gwei = sp.get("beaconBalancesSum")
        if exec_wei:
            result["execution_layer_eth"] = round(int(str(exec_wei).rstrip("n")) / 1e18)
        if beacon_gwei:
            result["beacon_layer_eth"] = round(int(str(beacon_gwei).rstrip("n")) / 1e9)
    except Exception:
        pass

    try:
        # Scarcity: total ETH staked (the canonical live figure from ultrasound.money)
        engines = (scarcity_raw or {}).get("engines", {})
        staked = engines.get("staked", {})
        if staked.get("amount"):
            result["total_eth_staked_usm"] = round(int(str(staked["amount"]).rstrip("n")) / 1e18)
    except Exception:
        pass

    return result


def _parse_supply(raw) -> dict:
    """Parse Etherscan ethsupply2. Values are in Wei — convert to whole ETH."""
    try:
        r = (raw or {}).get("result", {})
        def _wei(key):
            v = r.get(key)
            return round(int(v) / 1e18) if v else None
        return {
            "circulating_eth":        _wei("EthSupply"),
            "total_burned_eth":       _wei("BurntFees"),
            "beacon_net_deposits_eth": _wei("Eth2Staking"),   # cumulative deposits, NOT total staked
            "beacon_withdrawn_eth":   _wei("WithdrawnTotal"),
        }
    except Exception as e:
        print(f"[data] supply parse: {e}")
        return {}


def _parse_staking(lido_raw, lst_raw=None) -> dict:
    result = {}

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

    # Total ETH staked — requires CryptoQuant Pro or beaconcha.in paid key
    result["total_eth_staked_note"] = "~34M ETH estimated — live data requires CryptoQuant Professional"

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


# ─── 5-minute TTL cache (file-backed so restarts don't cold-start) ────────────

import json as _json

_CACHE_FILE    = "/tmp/eth-dashboard-data.json"
DATA_CACHE_TTL = 5 * 60  # seconds


def _load_disk_cache() -> dict:
    try:
        with open(_CACHE_FILE) as f:
            d = _json.load(f)
        if time.time() - d.get("ts", 0) < DATA_CACHE_TTL:
            print("[data] loaded cache from disk")
            return d
    except Exception:
        pass
    return {}


def _save_disk_cache(ts: float, data: dict) -> None:
    try:
        tmp = _CACHE_FILE + ".tmp"
        with open(tmp, "w") as f:
            _json.dump({"ts": ts, "data": data}, f)
        os.replace(tmp, _CACHE_FILE)
    except Exception as e:
        print(f"[data] cache write error: {e}")


_data_cache: dict = _load_disk_cache()


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
    _save_disk_cache(now, result)
    return jsonify(result)
