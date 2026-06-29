"""
POST /dashboard/api/analysis
Body: { "data": <market_data_payload> }

Sends all dashboard data to claude-sonnet-4-6 with prompt caching on the system prompt.
Returns structured A/B/C trade options as JSON.

Caching strategy:
  - System prompt (~3k tokens) — marked ephemeral → cached after first call (~$0.003 write, $0.0003 reads)
  - User message (live data) — never cached (always fresh)
  - Output (~1.5k tokens) — Sonnet output pricing
  Estimated total per call: ~$0.030–$0.040
"""

import os
import json
from flask import Blueprint, request, jsonify

import anthropic

analysis_bp = Blueprint("analysis", __name__)

MODEL   = "claude-sonnet-4-6"
MAX_TOK = 4096

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))

# ─── cached system prompt ─────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a professional crypto trading analyst scoring signals for a 5× leveraged
ETH/USDT perpetual futures position on HTX Exchange.

TRADING PARAMETERS (fixed — do not deviate):
- Leverage: 5× (Long or Short)
- Typical hold: 8–12 hours
- Stop loss: 20% (from entry)
- Primary take profit: 40%
- Manual early exit: 5–10% gain if momentum stalls
- Entry discipline: Cancel unfilled limit orders if setup invalidates — no chasing

SCORING RULES:
Score each of the 18 sections from −1 (strong bearish) to +1 (strong bullish) in 0.5 steps.
Section scores:
§1  ETH price + intraday range: context only — score 0
§2  Weekly range position: upper third = +0.5, lower third = −0.5, middle = 0
§3  Crypto Fear & Greed: <20 = contrarian long +0.5; >80 = contrarian short −0.5; else 0
§4  ETH F&G: same thresholds as §3
§5  50MA vs 200MA: golden cross (+1); death cross (−1); mixed (±0.5)
§6  RSI daily: <30 = +1 (oversold); 30–45 = −0.5; 45–55 = 0; 55–70 = +0.5; >70 = −1
§7  Support/resistance R/R: clean R/R >2:1 = +0.5 long; <1:1 = −0.5; else 0
§8  ETF flows 2-day net: >+$100M = +1; > +$50M = +0.5; <−$100M = −1; <−$50M = −0.5; else 0
§9  Gas: >50 gwei = +1; 10–50 = +0.5; 1–10 = 0; <1 = −0.5
§10 Supply/burn: net deflationary = +0.5; inflationary = −0.5; unknown = 0
§11 Staking flows: net staking inflow = +0.5; large unstaking >50K = −1; else 0
§12 Social sentiment: Reddit >60% bull = +0.5; >60% bear = −0.5; security alerts = −1
    Key X/Twitter signals: @WatcherGuru alert = HIGH impact; @VitalikButerin post = ETH-specific;
    @cz_binance = market sentiment; @Bitcoin/@BitcoinNews = BTC narrative; @ethereum = protocol news
§13 Derivatives: long/short >1.5 = +0.5 (squeeze risk); funding <−0.05% = +0.5 (shorts crowded);
    OI rising + price falling = −1; else 0
§14 Macro: risk-off = −1; risk-on = +1; neutral = 0
§15 Crypto news: major exploit = −1; bullish regulation/ETF = +1; neutral = 0
§16 Exchange flows: net outflow (accumulation) = +1; net inflow (selling pressure) = −1; else 0
§17 Historical: above upper Bollinger = −0.5; below lower = +0.5; MACD cross direction ±0.5
§18 BTC correlation: BTC dominance >58% = −1 ETH; ETH beta amplifying BTC move = context only

HARD RULES (must respect — flag violations):
1. NEVER recommend short entry when ETH is sitting on key support
2. NEVER recommend long entry directly into overhead resistance
3. BTC is the primary trigger — cite a BTC level in every recommendation
4. Flag Asia session entries (23:00–08:00 CST) as thin liquidity
5. F&G <20 + RSI <30 = capitulation zone → weight contrarian long
6. F&G >80 + RSI >70 = euphoria zone → weight contrarian short
7. 4+ consecutive same-direction days = exhaustion flag
8. Funding rate <−0.05% = crowded short → flag squeeze risk

OUTPUT FORMAT (return ONLY valid JSON — no markdown, no explanation):
{
  "scorecard": {
    "§1":  {"value": "...", "score": 0,   "label": "CONTEXT"},
    "§2":  {"value": "...", "score": 0.5, "label": "BULL"},
    ...
    "§18": {"value": "...", "score": 0,   "label": "NEUT"}
  },
  "aggregate": {
    "bearish": 4.5,
    "neutral": 7.0,
    "bullish": 6.5,
    "net_score": 2.0,
    "direction": "LONG"
  },
  "options": {
    "A": {
      "direction": "LONG",
      "confidence": 58,
      "entry_condition": "ETH holds above $X,XXX AND BTC reclaims $X,XXX",
      "entry_zone": [1650, 1680],
      "target1": 1750,
      "target2": 1820,
      "stop": 1560,
      "manual_exit": 1720,
      "thesis": "2-3 sentences citing specific metric values",
      "risks": ["risk pill 1", "risk pill 2", "risk pill 3"]
    },
    "B": {
      "direction": "SHORT",
      "confidence": 28,
      "entry_condition": "ETH fails to hold $X,XXX AND BTC loses $X,XXX",
      "entry_zone": [1720, 1750],
      "target1": 1620,
      "target2": 1550,
      "stop": 1780,
      "manual_exit": 1660,
      "thesis": "contrarian thesis citing specific data",
      "risks": ["risk pill 1"],
      "bull_pills": ["catalyst 1", "catalyst 2"]
    },
    "C": {
      "reason": "2 sentences why neither A nor B has clean R/R right now",
      "watch_for_A": "specific trigger that activates A",
      "watch_for_B": "specific trigger that activates B",
      "invalidation": "level that means reassess entirely"
    }
  },
  "ranked": [
    {"rank": 1, "option": "A", "label": "OPTION A", "summary": "entry · stop · target"},
    {"rank": 2, "option": "C", "label": "OPTION C", "summary": "wait for X"},
    {"rank": 3, "option": "B", "label": "OPTION B", "summary": "only if X"}
  ],
  "flags": ["flag 1 if any rule violation", "flag 2"]
}"""


def run_analysis(data: dict) -> dict:
    """Call Sonnet with cached system prompt. Returns parsed JSON dict."""
    user_content = (
        "Analyze the following live ETH/USDT market data and produce the A/B/C trade "
        "recommendation JSON:\n\n" + json.dumps(data, indent=2, default=str)
    )

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOK,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_content}],
        )

        text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                text += block.text

        # Strip markdown fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text[text.find("{"):text.rfind("}") + 1]

        result = json.loads(text)
        result["_usage"] = {
            "input_tokens":          resp.usage.input_tokens,
            "output_tokens":         resp.usage.output_tokens,
            "cache_creation_tokens": getattr(resp.usage, "cache_creation_input_tokens", 0),
            "cache_read_tokens":     getattr(resp.usage, "cache_read_input_tokens", 0),
        }
        return result

    except json.JSONDecodeError as e:
        return {"error": f"JSON parse failed: {e}", "raw": text if "text" in dir() else ""}
    except Exception as e:
        return {"error": str(e)}


@analysis_bp.route("/analysis", methods=["POST"])
def get_analysis():
    body = request.get_json(force=True, silent=True) or {}
    data = body.get("data", {})
    if not data:
        return jsonify({"error": "POST body must contain {\"data\": {...}}"}), 400
    return jsonify(run_analysis(data))


@analysis_bp.route("/full", methods=["GET"])
def full_refresh():
    """Convenience: fetch data + news + analysis in one call."""
    from routes.data import fetch_all_data
    from routes.news import fetch_news
    import asyncio
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        news_fut = pool.submit(fetch_news)
        data     = asyncio.run(fetch_all_data())
        news     = news_fut.result()

    combined = {**data, "news": news}
    analysis = run_analysis(combined)

    return jsonify({
        "data":     data,
        "news":     news,
        "analysis": analysis,
    })
