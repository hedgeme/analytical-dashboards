"""
GET /dashboard/api/news
Runs two Anthropic web searches in parallel:
  1. Macro economics headlines (Fed, CPI, DXY, Nasdaq, PCE)
  2. Crypto / ETH headlines (ETF flows, hacks, regulatory, protocol)
Returns top 3 macro + top 3 crypto headlines with impact tags.
Cost: ~2 web-search tool uses on claude-haiku-4-5-20251001 (~$0.001)
Cache: 30-minute TTL to prevent duplicate API calls on rapid retries.
"""

import os
import re
import json
import time
import concurrent.futures
from flask import Blueprint, jsonify

import anthropic

news_bp = Blueprint("news", __name__)

MODEL   = "claude-haiku-4-5-20251001"
MAX_TOK = 1024

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

MACRO_PROMPT = """Search for the top 3 macro economic news events from the last 24 hours that
affect crypto markets. Focus on: Fed statements, CPI/PCE prints, Nasdaq moves >1%, DXY moves,
Treasury yields, geopolitical risk events.

Return ONLY valid JSON in this exact format (no markdown, no explanation):
{
  "headlines": [
    {"title": "...", "impact": "BEARISH|BULLISH|NEUTRAL", "detail": "one sentence"}
  ]
}"""

CRYPTO_PROMPT = """Search for the top 3 most important crypto news events from the last 24 hours.

Priority sources to check (search each):
- @WatcherGuru — major market-moving alerts
- @cz_binance — Binance and crypto market commentary
- @BitcoinNews / @Bitcoin — BTC news and sentiment
- @VitalikButerin — Ethereum protocol announcements
- @ethereum — official Ethereum Foundation updates
- @PeckShieldAlert / @CertiKAlert — exchange hacks, exploits, smart contract vulnerabilities

Also cover: ETH/BTC price action, ETF flow data, SEC or regulatory actions, protocol upgrades,
large liquidation events.

Flag any security exploits or hacks as BEARISH and mark them HIGH priority.

Return ONLY valid JSON in this exact format (no markdown, no explanation):
{
  "headlines": [
    {"title": "...", "impact": "BEARISH|BULLISH|NEUTRAL", "detail": "one sentence", "source": "@handle or outlet"}
  ]
}"""


def _extract_json(text: str) -> dict:
    """Robustly extract the first complete {...} object from arbitrary text."""
    text = text.strip()
    # Find the first '{' and last '}' in the string
    start = text.find("{")
    end   = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in: {text[:200]!r}")
    return json.loads(text[start:end + 1])


def _search(prompt: str, label: str) -> dict:
    """Run a single web-search-enabled Anthropic call (blocking)."""
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOK,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                text += block.text

        return _extract_json(text)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[news] {label} JSON parse error: {e}")
        return {"headlines": [], "error": str(e)}
    except Exception as e:
        print(f"[news] {label} search error: {e}")
        return {"headlines": [], "error": str(e)}


# ─── 30-minute TTL cache ───────────────────────────────────────────────────────

_cache: dict = {}
CACHE_TTL = 30 * 60  # seconds


def _cached_fetch() -> dict:
    now = time.time()
    if _cache.get("ts") and (now - _cache["ts"]) < CACHE_TTL:
        print("[news] serving from cache")
        return _cache["data"]

    data = fetch_news()
    _cache["ts"]   = now
    _cache["data"] = data
    return data


def fetch_news() -> dict:
    """Run both searches in parallel using a thread pool (Anthropic SDK is sync)."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        macro_fut  = pool.submit(_search, MACRO_PROMPT,  "macro")
        crypto_fut = pool.submit(_search, CRYPTO_PROMPT, "crypto")
        macro_data  = macro_fut.result()
        crypto_data = crypto_fut.result()

    return {
        "macro":  macro_data.get("headlines", []),
        "crypto": crypto_data.get("headlines", []),
    }


@news_bp.route("/news")
def get_news():
    return jsonify(_cached_fetch())
