"""
GET /dashboard/api/news
Runs two Anthropic web searches in parallel:
  1. Macro economics headlines (Fed, CPI, DXY, Nasdaq, PCE)
  2. Crypto / ETH headlines (ETF flows, hacks, regulatory, protocol)
Returns top 3 macro + top 3 crypto headlines with impact tags.
Cost: ~2 web-search tool uses on claude-sonnet-4-6 (~$0.006)
"""

import os
import json
import asyncio
import concurrent.futures
from flask import Blueprint, jsonify

import anthropic

news_bp = Blueprint("news", __name__)

MODEL   = "claude-sonnet-4-6"
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


def _search(prompt: str, label: str) -> dict:
    """Run a single web-search-enabled Anthropic call (blocking)."""
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOK,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
        # Extract text from the final assistant turn
        text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                text += block.text

        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text[text.find("{"):text.rfind("}") + 1]

        return json.loads(text)
    except json.JSONDecodeError:
        return {"headlines": [], "raw": text if "text" in dir() else ""}
    except Exception as e:
        print(f"[news] {label} search error: {e}")
        return {"headlines": [], "error": str(e)}


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
    return jsonify(fetch_news())
