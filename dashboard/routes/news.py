"""
GET /dashboard/api/news
Free real-time news from SoSoValue (no Anthropic tokens used).
  - category 1 : crypto articles (PANews, Cointelegraph, Odaily, Benzinga, ForesightNews, …)
  - category 13: macro articles (WSJ, Barron's, Reuters, AP, Business Today, …)
Runs two fetches in parallel, classifies BULLISH/BEARISH/NEUTRAL via keyword scoring,
then splits into top-3 macro + top-3 crypto headlines.
Cache: 30-minute TTL.
"""

import json
import os
import re
import time
import urllib.request
import urllib.parse
import concurrent.futures
from flask import Blueprint, jsonify

news_bp = Blueprint("news", __name__)

SOSOVALUE_KEY = os.getenv("SOSOVALUE_API_KEY", "")
SOSO_NEWS_URL = "https://openapi.sosovalue.com/openapi/v1/news"
SOSO_HDRS = {
    "x-soso-api-key": SOSOVALUE_KEY,
    "User-Agent":     "Mozilla/5.0 (ETH-Dashboard/1.0)",
    "Accept":         "application/json",
}

CACHE_TTL = 30 * 60   # seconds

# ─── keyword sets ─────────────────────────────────────────────────────────────

_BULLISH = {
    "surge", "surges", "surged", "rally", "rallied", "rallies", "soars", "soared",
    "inflow", "inflows", "approval", "approved", "approves", "record", "bullish",
    "upgrade", "upgrades", "partnership", "launch", "launches", "launched",
    "gains", "gained", "higher", "rises", "rose", "recovery", "recovered",
    "breakthrough", "adoption", "positive", "upside", "climbs", "climbed",
    "jumps", "jumped", "outperform", "support", "backed", "milestone",
    "all-time high", "ath", "breakout",
}

_BEARISH = {
    "crash", "crashes", "crashed", "hack", "hacked", "exploit", "exploited",
    "ban", "banned", "outflow", "outflows", "dump", "dumped", "liquidation",
    "liquidations", "arrest", "arrested", "fraud", "penalty", "fined", "fine",
    "scam", "falls", "fell", "fallen", "dropped", "drop", "decline", "declining",
    "bearish", "warning", "risk", "concern", "rejected", "delay", "delayed",
    "loses", "loss", "losses", "violated", "violation", "lawsuit", "charges",
    "selloff", "sell-off", "plunges", "plunged", "slump", "slumps", "slumped",
    "vulnerability", "breach", "breached", "stolen", "theft", "downgrade",
    "seized", "jailed", "indicted", "investigation",
}

_MACRO_TERMS = {
    "federal reserve", "fomc", " cpi ", "pce", "inflation", "interest rate",
    "yield curve", "treasury yield", "nasdaq", "dow jones", "s&p 500",
    "dxy", "dollar index", "nonfarm payroll", "gdp", "recession",
    "rate cut", "rate hike", "powell", "ecb ", "boe ", "wall street surges",
    "wall street falls", "stocks rose", "stocks fell", "equities",
    "oil prices", "gold prices", "tariff", "trade war", "geopolit",
    "wsj", "barron's", "marketwatch",
}

_CRYPTO_TERMS = {
    "ethereum", "eth etf", " eth ", "bitcoin", " btc ", "defi", "nft",
    "spot etf", "sec ", "binance", "coinbase", "okx", "kraken",
    "staking", "layer 2", "layer2", "arbitrum", "base chain",
    "solana", "crypto", "blockchain", "validator", "whale alert",
    "on-chain", "smart contract", "liquidation", "stablecoin",
    "usdt", "usdc", "grayscale", "blackrock eth", "fidelity eth",
    "bitwise", "vaneck", "inflow", "outflow", "hack", "exploit",
    "token", "airdrop", "protocol", "dex", "cex",
}

# ETH-specific — boosts an article's priority within the crypto bucket
_ETH_TERMS = {
    "ethereum", "eth etf", " eth ", "eth2", "etha", "feth", "ethe",
    "ethw", "vitalik", "beacon chain", "proof of stake", "withdrawals",
    "eth staking", "eth burn", "eip-", "dencun", "pectra",
}


# ─── helpers ──────────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").strip()


def _classify(text: str) -> str:
    t = text.lower()
    bull = sum(1 for w in _BULLISH if w in t)
    bear = sum(1 for w in _BEARISH if w in t)
    if bear > bull:
        return "BEARISH"
    if bull > bear:
        return "BULLISH"
    return "NEUTRAL"


def _is_macro(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in _MACRO_TERMS)


def _is_crypto(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in _CRYPTO_TERMS)


def _eth_score(text: str) -> int:
    """Higher = more ETH-specific. Used to sort crypto bucket by relevance."""
    t = text.lower()
    return sum(1 for w in _ETH_TERMS if w in t)


# ─── fetchers ─────────────────────────────────────────────────────────────────

def _fetch_soso(category: str, page_size: int = 25) -> list:
    """Blocking HTTP call — runs in thread pool."""
    params = urllib.parse.urlencode({"category": category, "page_size": page_size})
    url    = f"{SOSO_NEWS_URL}?{params}"
    req    = urllib.request.Request(url, headers=SOSO_HDRS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode())
            return (d.get("data") or {}).get("list") or []
    except Exception as e:
        print(f"[news] soso category={category}: {e}")
        return []


_STOP = {"the", "a", "an", "in", "on", "at", "to", "of", "for", "and",
         "or", "is", "was", "are", "were", "as", "with", "by", "its", "it"}


def _sig_words(title: str) -> frozenset:
    """Extract significant words (skip stopwords, keep numbers and proper nouns)."""
    words = re.sub(r"[^a-z0-9 ]", "", title.lower()).split()
    return frozenset(w for w in words if len(w) > 3 and w not in _STOP)


def _is_duplicate(sig_a: frozenset, seen_sigs: list, threshold: float = 0.6) -> bool:
    """Return True if sig_a overlaps ≥ threshold with any previously seen sig set."""
    for sig_b in seen_sigs:
        union = sig_a | sig_b
        if not union:
            continue
        jaccard = len(sig_a & sig_b) / len(union)
        if jaccard >= threshold:
            return True
    return False


def _parse(raw_list: list) -> list:
    """Convert SoSoValue news items to dashboard format.
    Deduplicates by exact title AND by Jaccard similarity of significant words."""
    out       = []
    seen_sigs = []

    for item in raw_list:
        raw_title   = item.get("title") or ""
        raw_content = item.get("content") or ""
        title = _strip_html(raw_title or raw_content)[:200]
        if not title:
            continue
        sig = _sig_words(title)
        if _is_duplicate(sig, seen_sigs):
            continue
        seen_sigs.append(sig)

        source  = item.get("nick_name") or item.get("author") or "Unknown"
        tags    = item.get("tags") or []
        detail  = _strip_html(raw_content)[:120] if raw_content else title[:120]
        full    = f"{title} {detail} {' '.join(tags)}"

        out.append({
            "title":  title,
            "impact": _classify(full),
            "detail": detail,
            "source": source,
            "_text":  full.lower(),
        })
    return out


def _clean(items: list) -> list:
    """Remove internal _text field before returning to client."""
    return [
        {k: v for k, v in a.items() if k != "_text"}
        for a in items
    ]


# ─── main fetch ───────────────────────────────────────────────────────────────

def fetch_news() -> dict:
    """Fetch crypto articles, macro, and CT/Twitter posts in parallel.
    category 1  = crypto articles (PANews, Cointelegraph, Odaily, Benzinga, …)
    category 13 = macro articles (WSJ, Barron's, Reuters, AP, …)
    category 4  = verified crypto Twitter/X posts (@whale_alert, @Cointelegraph CT, …)
    Returns top-3 macro + top-3 crypto + top-5 social (CT) posts."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        fut_crypto = pool.submit(_fetch_soso, "1",  50)   # broad crypto/finance article pool
        fut_macro  = pool.submit(_fetch_soso, "13", 25)   # dedicated macro/markets bucket
        fut_social = pool.submit(_fetch_soso, "4",  30)   # verified CT / Twitter posts
        crypto_raw = fut_crypto.result()
        macro_raw  = fut_macro.result()
        social_raw = fut_social.result()

    # Parse each pool separately to avoid cross-contamination
    parsed_macro   = _parse(macro_raw)
    parsed_crypto  = _parse(crypto_raw)
    parsed_social  = _parse(social_raw)
    parsed_all     = _parse(crypto_raw + macro_raw)     # deduped combined article pool

    # Macro: prefer items from macro bucket, fall back to keyword scan of combined pool
    macro_items = [a for a in parsed_macro if _is_macro(a["_text"])]
    if len(macro_items) < 3:
        extras = [a for a in parsed_all
                  if _is_macro(a["_text"]) and a["title"] not in {x["title"] for x in macro_items}]
        macro_items.extend(extras)

    # Crypto articles: keyword-matched, NOT in macro, ETH-first sort
    macro_titles = {a["title"] for a in macro_items}
    crypto_candidates = [a for a in parsed_all
                         if _is_crypto(a["_text"]) and a["title"] not in macro_titles]
    crypto_candidates.sort(key=lambda a: -_eth_score(a["_text"]))

    # Social/CT: all parsed cat-4 posts, ETH-relevant first
    social_candidates = list(parsed_social)
    social_candidates.sort(key=lambda a: -_eth_score(a["_text"]))

    # Fallbacks
    if not macro_items:
        macro_items = [a for a in parsed_all if not _is_crypto(a["_text"])]
    if not crypto_candidates:
        crypto_candidates = [a for a in parsed_all if a["title"] not in macro_titles]

    return {
        "source": "SoSoValue",
        "macro":  _clean(macro_items[:3]),
        "crypto": _clean(crypto_candidates[:3]),
        "social": _clean(social_candidates[:5]),
    }


# ─── 30-minute cache (file-backed so restarts don't cold-start) ───────────────

_CACHE_FILE = "/tmp/eth-dashboard-news.json"


def _load_disk_cache() -> dict:
    try:
        with open(_CACHE_FILE) as f:
            d = json.load(f)
        if time.time() - d.get("ts", 0) < CACHE_TTL:
            print("[news] loaded cache from disk")
            return d
    except Exception:
        pass
    return {}


def _save_disk_cache(ts: float, data: dict) -> None:
    try:
        tmp = _CACHE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"ts": ts, "data": data}, f)
        os.replace(tmp, _CACHE_FILE)
    except Exception as e:
        print(f"[news] cache write error: {e}")


_cache: dict = _load_disk_cache()


def _cached_fetch() -> dict:
    now = time.time()
    if _cache.get("ts") and (now - _cache["ts"]) < CACHE_TTL:
        print("[news] serving from cache")
        return _cache["data"]
    data = fetch_news()
    _cache["ts"]   = now
    _cache["data"] = data
    _save_disk_cache(now, data)
    return data


@news_bp.route("/news")
def get_news():
    return jsonify(_cached_fetch())
