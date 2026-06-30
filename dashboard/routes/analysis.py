"""
POST /dashboard/api/analysis
Body: { "data": <market_data_payload> }

Deterministic rule-based scoring across all 21 signal sections.
Zero Anthropic token usage — all thresholds from SCORING_SPEC.md.
Returns identical JSON structure: scorecard, aggregate, options A/B/C, ranked, flags.

Scoring scale: −1.0 (strong bearish) to +1.0 (strong bullish), 0.5 steps.
Tier multipliers: CRITICAL ×2.0 | HIGH ×1.5 | STANDARD ×1.0 | LOW ×0.5
Max weighted net: ±20.0  (bull max = +20.0, bear max ≈ −20.5)
"""

import json
from flask import Blueprint, request, jsonify

analysis_bp = Blueprint("analysis", __name__)


# ─── tier weights ─────────────────────────────────────────────────────────────

_WEIGHTS = {
    "§1":  0.0,   # CONTEXT — never scored
    "§2":  1.0,   # STANDARD — weekly range vs EMA structure
    "§3":  0.5,   # LOW — Crypto F&G (lagging, overlaps RSI)
    "§4":  0.5,   # LOW — ETH F&G
    "§5":  2.0,   # CRITICAL — EMA50/200 cross (trend regime)
    "§6":  1.5,   # HIGH — RSI (entry timing)
    "§7":  1.5,   # HIGH — S/R reward-risk
    "§8":  2.0,   # CRITICAL — ETF institutional flows
    "§9":  1.5,   # HIGH — price vs EMA stack (current position)
    "§10": 0.5,   # LOW — supply/burn (slow-moving fundamental)
    "§11": 0.5,   # LOW — staking flows (slow-moving)
    "§12": 0.5,   # LOW — social/CT sentiment
    "§13": 1.5,   # HIGH — derivatives (funding + L/S ratio)
    "§14": 2.0,   # CRITICAL — macro risk sentiment
    "§15": 1.0,   # STANDARD — crypto news
    "§16": 1.5,   # HIGH — CEX exchange flows
    "§17": 1.0,   # STANDARD — Bollinger + MACD
    "§18": 2.0,   # CRITICAL — BTC dominance + direction
    "§19": 1.0,   # STANDARD — ETH/BTC cross ratio
    "§20": 0.0,   # PLACEHOLDER — Options IV/skew (pending API)
    "§21": 0.0,   # PLACEHOLDER — Volatility regime (pending API)
}

_TIER_NAMES = {
    "§1":  "CONTEXT",
    "§2":  "STANDARD",
    "§3":  "LOW",
    "§4":  "LOW",
    "§5":  "CRITICAL",
    "§6":  "HIGH",
    "§7":  "HIGH",
    "§8":  "CRITICAL",
    "§9":  "HIGH",
    "§10": "LOW",
    "§11": "LOW",
    "§12": "LOW",
    "§13": "HIGH",
    "§14": "CRITICAL",
    "§15": "STANDARD",
    "§16": "HIGH",
    "§17": "STANDARD",
    "§18": "CRITICAL",
    "§19": "STANDARD",
    "§20": "PLACEHOLDER",
    "§21": "PLACEHOLDER",
}

# Maximum possible weighted bull score — used as confidence denominator
_MAX_WEIGHTED = 20.0


# ─── safe nested getter ───────────────────────────────────────────────────────

def _g(d, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k)
        if d is None:
            return default
    return d


def _fmt_price(v):
    if v is None:
        return "N/A"
    return f"${v:,.0f}"


def _fmt_pct(v, decimals=1):
    if v is None:
        return "N/A"
    return f"{v:+.{decimals}f}%"


def _label(score: float) -> str:
    if score > 0:
        return "BULL"
    if score < 0:
        return "BEAR"
    return "NEUT"


# ─── 21 scoring sections ──────────────────────────────────────────────────────

def _s1(data, _news):
    """§1 — ETH Price + Intraday Range (CONTEXT, weight=0)"""
    price = _g(data, "eth", "price")
    high  = _g(data, "eth", "price_24h_high")
    low   = _g(data, "eth", "price_24h_low")
    chg   = _g(data, "eth", "change_24h")
    if price:
        value = f"{_fmt_price(price)} | 24h {_fmt_pct(chg)} | range {_fmt_price(low)}–{_fmt_price(high)}"
    else:
        value = "N/A"
    return 0, value, "CONTEXT"


def _s2(data, _news):
    """§2 — Weekly Range vs EMA20/50/200 Structure (STANDARD ×1.0)"""
    price  = _g(data, "eth", "price") or 0
    wk_h   = _g(data, "weekly_range", "high") or 0
    wk_l   = _g(data, "weekly_range", "low")  or 0
    ema20  = _g(data, "technicals", "ema20")
    ema50  = _g(data, "technicals", "ema50")
    ema200 = _g(data, "technicals", "ema200")

    if not wk_h or not wk_l or wk_h == wk_l:
        return 0, "N/A", "NEUT"

    pos    = (price - wk_l) / (wk_h - wk_l)
    wk_str = f"Week {_fmt_price(wk_l)}–{_fmt_price(wk_h)}, pos={pos:.0%}"

    ema_parts = []
    if ema200 is not None: ema_parts.append(f"EMA200={_fmt_price(ema200)}")
    if ema50  is not None: ema_parts.append(f"EMA50={_fmt_price(ema50)}")
    if ema20  is not None: ema_parts.append(f"EMA20={_fmt_price(ema20)}")

    if not ema_parts:
        if pos > 0.667: return 0.5, f"Upper third ({wk_str})", "BULL"
        if pos < 0.333: return -0.5, f"Lower third ({wk_str})", "BEAR"
        return 0, f"Mid-range ({wk_str})", "NEUT"

    desc = f"{wk_str} | " + " | ".join(ema_parts)

    # _rel: where does the weekly range sit relative to a given EMA level?
    #   "above"  = range.low > ema  (entire range above the EMA — EMA is below/support)
    #   "below"  = range.high < ema (entire range below the EMA — EMA is above/resistance)
    #   "spans"  = range straddles the EMA
    def _rel(ema_val):
        if ema_val is None: return None
        if wk_l > ema_val:  return "above"
        if wk_h < ema_val:  return "below"
        return "spans"

    r200 = _rel(ema200)
    r50  = _rel(ema50)
    r20  = _rel(ema20)

    active = [r for r in [r200, r50, r20] if r is not None]

    if all(r == "above" for r in active):
        return 1.0, f"Above all EMAs — {desc}", "BULL"
    if r200 == "above" and r50 == "above" and r20 == "spans":
        return 0.75, f"Range touches EMA20, EMA50/200 support intact — {desc}", "BULL"
    if r200 == "above" and r50 == "above" and r20 == "below":
        return 0.5, f"Above EMA200+50, EMA20 above range — {desc}", "BULL"
    if r200 == "above" and r50 == "spans":
        return 0.5, f"Above EMA200, testing EMA50 — {desc}", "BULL"
    if r200 == "above" and r50 == "below":
        return 0.25, f"Above EMA200, below EMA50 — {desc}", "BULL"
    if r200 == "spans":
        return 0.0, f"Range testing EMA200 — {desc}", "NEUT"
    if all(r == "below" for r in active):
        return -1.0, f"Below all EMAs — {desc}", "BEAR"
    if r200 == "below" and r50 == "below":
        return -0.75, f"Below EMA200+EMA50 — {desc}", "BEAR"
    if r200 == "below":
        return -0.25, f"Below EMA200 — {desc}", "BEAR"

    return 0, f"Mixed EMA structure — {desc}", "NEUT"


def _s3(data, _news):
    """§3 — Crypto F&G Index with gradient scoring (LOW ×0.5)"""
    val   = _g(data, "fear_greed", "value")
    label = _g(data, "fear_greed", "classification") or ""
    if val is None:
        return 0, "N/A", "NEUT"
    val = int(val)
    desc = f"F&G={val} ({label})"
    if val < 20:
        return 0.5,   f"{desc} — Extreme Fear (contrarian long)", "BULL"
    if val < 45:
        return 0.25,  f"{desc} — Fear (mild contrarian lean)",    "BULL"
    if val <= 55:
        return 0,     desc, "NEUT"
    if val <= 75:
        return -0.25, f"{desc} — Greed (mild caution)",           "BEAR"
    return -0.5,      f"{desc} — Extreme Greed (contrarian short)", "BEAR"


def _s4(data, _news):
    """§4 — ETH F&G Index with gradient scoring (LOW ×0.5)"""
    val = _g(data, "eth_fear_greed", "value")
    if val is None:
        return 0, "N/A", "NEUT"
    val = int(val)
    desc = f"ETH F&G={val}"
    if val < 20:
        return 0.5,   f"{desc} — Extreme Fear", "BULL"
    if val < 45:
        return 0.25,  f"{desc} — Fear (mild lean)", "BULL"
    if val <= 55:
        return 0,     desc, "NEUT"
    if val <= 75:
        return -0.25, f"{desc} — Greed (mild caution)", "BEAR"
    return -0.5,      f"{desc} — Extreme Greed", "BEAR"


def _s5(data, _news):
    """§5 — EMA50 vs EMA200 Cross / Trend Regime (CRITICAL ×2.0)"""
    ema50  = _g(data, "technicals", "ema50")
    ema200 = _g(data, "technicals", "ema200")
    if ema50 is None or ema200 is None:
        return 0, "N/A", "NEUT"
    diff_pct = (ema50 - ema200) / ema200 * 100
    desc = f"EMA50={_fmt_price(ema50)} vs EMA200={_fmt_price(ema200)} ({diff_pct:+.1f}%)"
    if diff_pct > 0.5:
        return 1, f"Golden cross — {desc}", "BULL"
    if diff_pct < -0.5:
        return -1, f"Death cross — {desc}", "BEAR"
    return 0.5 if diff_pct > 0 else -0.5, f"Converging — {desc}", "BULL" if diff_pct > 0 else "BEAR"


def _s6(data, _news):
    """§6 — RSI Daily 14-period (HIGH ×1.5)"""
    rsi_val = _g(data, "technicals", "rsi")
    rsi_4h  = _g(data, "technicals", "rsi_4h")
    if rsi_val is None:
        return 0, "N/A", "NEUT"
    r = round(float(rsi_val), 1)
    desc = f"RSI(14)={r}" + (f" | RSI(14)4h={round(float(rsi_4h),1)}" if rsi_4h else "")
    if r < 30:
        return 1,    f"{desc} — Oversold", "BULL"
    if r < 45:
        return -0.5, f"{desc} — Weak momentum", "BEAR"
    if r < 55:
        return 0,    f"{desc} — Neutral", "NEUT"
    if r < 70:
        return 0.5,  f"{desc} — Strong momentum", "BULL"
    return -1,       f"{desc} — Overbought", "BEAR"


def _s7(data, _news):
    """§7 — Support/Resistance Reward-to-Risk (HIGH ×1.5)"""
    price       = _g(data, "eth", "price") or 0
    supports    = _g(data, "technicals", "supports")    or []
    resistances = _g(data, "technicals", "resistances") or []
    sups_below  = [s for s in supports    if s < price]
    res_above   = [r for r in resistances if r > price]
    if not sups_below or not res_above:
        return 0, "No clear S/R levels near price", "NEUT"
    nearest_sup = max(sups_below)
    nearest_res = min(res_above)
    upside   = nearest_res - price
    downside = price - nearest_sup
    if downside < 1:
        return 0, "Price near support — R/R undefined", "NEUT"
    rr = upside / downside
    desc = f"R/R={rr:.1f}:1 | sup={_fmt_price(nearest_sup)} | res={_fmt_price(nearest_res)}"
    if rr > 2:
        return 0.5,  f"Favorable long setup — {desc}", "BULL"
    if rr < 1:
        return -0.5, f"Unfavorable long setup — {desc}", "BEAR"
    return 0, desc, "NEUT"


def _s8(data, _news):
    """§8 — ETF Net Flows (CRITICAL ×2.0)"""
    daily = _g(data, "etf_flows", "daily_net_inflow_usd")
    date  = _g(data, "etf_flows", "date") or ""
    if daily is None:
        return 0, "N/A", "NEUT"
    m = float(daily) / 1e6
    desc = f"Daily net {m:+.0f}M USD ({date})"
    if daily > 100e6:
        return 1,    f"Strong inflow — {desc}", "BULL"
    if daily > 50e6:
        return 0.5,  f"Moderate inflow — {desc}", "BULL"
    if daily < -100e6:
        return -1,   f"Strong outflow — {desc}", "BEAR"
    if daily < -50e6:
        return -0.5, f"Moderate outflow — {desc}", "BEAR"
    return 0, f"Neutral — {desc}", "NEUT"


def _s9(data, _news):
    """§9 — Price vs EMA Stack (EMA20/50/200) — current position (HIGH ×1.5)
    Replaced Gas (gwei) — gas near 0 since EIP-4844 / Dencun (March 2024), zero signal value."""
    price  = _g(data, "eth", "price") or 0
    ema20  = _g(data, "technicals", "ema20")
    ema50  = _g(data, "technicals", "ema50")
    ema200 = _g(data, "technicals", "ema200")

    if not price or (ema20 is None and ema50 is None and ema200 is None):
        return 0, "N/A", "NEUT"

    ema_parts = []
    if ema200 is not None: ema_parts.append(f"EMA200={_fmt_price(ema200)}")
    if ema50  is not None: ema_parts.append(f"EMA50={_fmt_price(ema50)}")
    if ema20  is not None: ema_parts.append(f"EMA20={_fmt_price(ema20)}")
    desc = f"ETH={_fmt_price(price)} | " + " | ".join(ema_parts)

    above20  = ema20  is None or price > ema20
    above50  = ema50  is None or price > ema50
    above200 = ema200 is None or price > ema200

    if above20 and above50 and above200:
        return 1.0,   f"Above all EMAs (full bull stack) — {desc}", "BULL"
    if above20 and above50 and not above200:
        return 0.5,   f"Above EMA20+50, below EMA200 — {desc}", "BULL"
    if above20 and not above50:
        return 0.0,   f"Above EMA20 only (short-term bounce) — {desc}", "NEUT"
    if not above20 and above50 and above200:
        return -0.25, f"Below EMA20, EMA50+200 hold — {desc}", "BEAR"
    if not above20 and not above50 and above200:
        return -0.5,  f"Below EMA20+50, above EMA200 — {desc}", "BEAR"
    return -1.0,      f"Below all EMAs (full bear stack) — {desc}", "BEAR"


def _s10(data, _news):
    """§10 — ETH Supply / Burn Deflationary Signal (LOW ×0.5)"""
    is_defl  = _g(data, "supply", "is_deflationary")
    sgr      = _g(data, "supply", "supply_growth_rate_yearly")
    burn_day = _g(data, "supply", "burn_rate_eth_per_day")
    iss_day  = _g(data, "supply", "issuance_eth_per_day")
    if sgr is not None:
        desc = f"Net supply growth={sgr:+.3f}%/yr"
        if burn_day and iss_day:
            desc += f" | burn={burn_day:.0f} ETH/day | issuance={iss_day:.0f} ETH/day"
        if sgr < 0:
            return 0.5,  f"Deflationary — {desc}", "BULL"
        return -0.5, f"Inflationary — {desc}", "BEAR"
    if is_defl is True:
        return 0.5,  "Deflationary (burn > issuance)", "BULL"
    if is_defl is False:
        return -0.5, "Inflationary (issuance > burn)", "BEAR"
    return 0, "N/A", "NEUT"


def _s11(data, _news):
    """§11 — Staking Flows 24h Net (LOW ×0.5)"""
    net_24h    = _g(data, "staking", "net_stake_change_24h")
    unstaked   = _g(data, "staking", "unstaked_24h_eth_est")
    staked     = _g(data, "staking", "staked_24h_eth")
    validators = _g(data, "staking", "validators_entered_24h")
    parts = []
    if staked is not None:
        parts.append(f"staked={staked:,.0f} ETH/24h")
    if unstaked is not None:
        parts.append(f"unstaked≈{unstaked:,.0f} ETH/24h")
    if validators is not None:
        parts.append(f"validators+={validators}")
    desc = " | ".join(parts) or "N/A"
    if unstaked and float(unstaked) > 50000:
        return -1,  f"Large unstaking event — {desc}", "BEAR"
    if net_24h is not None:
        if float(net_24h) > 0:
            return 0.5, f"Net staking inflow — {desc}", "BULL"
        if float(net_24h) < 0:
            return 0,   f"Small net unstaking — {desc}", "NEUT"
    return 0, desc or "N/A", "NEUT"


def _s12(data, news):
    """§12 — Social / CT Sentiment (LOW ×0.5)"""
    social = (news or {}).get("social") or []
    bull   = sum(1 for p in social if p.get("impact") == "BULLISH")
    bear   = sum(1 for p in social if p.get("impact") == "BEARISH")
    total  = len(social) or 1

    alert_kw = {"hack", "exploit", "breach", "scam", "stolen", "fraud", "rug pull", "phishing"}
    has_alert = any(any(k in p.get("title", "").lower() for k in alert_kw) for p in social)
    if has_alert:
        return -1, "Security alert detected in CT posts", "BEAR"

    bull_pct = bull / total * 100
    bear_pct = bear / total * 100
    desc = f"CT: {bull_pct:.0f}% bull / {bear_pct:.0f}% bear ({total} posts)"
    if bull_pct > 60:
        return 0.5,  f"Bullish CT sentiment — {desc}", "BULL"
    if bear_pct > 60:
        return -0.5, f"Bearish CT sentiment — {desc}", "BEAR"
    return 0, desc, "NEUT"


def _s13(data, _news):
    """§13 — Derivatives: Funding Rate + L/S Ratio (HIGH ×1.5)
    L/S > 1.5 scores +0.5 only when RSI < 50 (squeeze setup requires momentum context)."""
    htx = _g(data, "derivatives", "htx") or {}
    okx = _g(data, "derivatives", "okx") or {}
    rsi_val = _g(data, "technicals", "rsi")

    fr  = htx.get("funding_rate") if htx.get("funding_rate") is not None else okx.get("funding_rate")
    ls  = htx.get("long_short_ratio") if htx.get("long_short_ratio") is not None else okx.get("long_short_ratio")
    oi_trend = htx.get("oi_trend")
    oi_chg   = htx.get("oi_24h_change_pct")

    score = 0
    parts = []

    if fr is not None:
        if fr < -0.05:
            score += 0.5
            parts.append(f"FR={fr:.4f}% (shorts crowded→squeeze risk)")
        elif fr > 0.05:
            score -= 0.5
            parts.append(f"FR={fr:.4f}% (longs crowded)")
        else:
            parts.append(f"FR={fr:.4f}%")

    if ls is not None:
        rsi_below_50 = rsi_val is not None and float(rsi_val) < 50
        if ls > 1.5:
            if rsi_below_50:
                score += 0.5
                parts.append(f"L/S={ls:.2f} (squeeze setup, RSI<50 confirms)")
            else:
                parts.append(f"L/S={ls:.2f} (crowded longs, RSI≥50 — no squeeze signal)")
        elif ls < 0.8:
            score -= 0.5
            parts.append(f"L/S={ls:.2f} (longs light)")
        else:
            parts.append(f"L/S={ls:.2f}")

    eth_chg = _g(data, "eth", "change_24h") or 0
    if oi_trend == "rising" and eth_chg < -1:
        score -= 1
        oi_str = f"{oi_chg:+.1f}%" if oi_chg is not None else "rising"
        parts.append(f"OI {oi_str} + ETH down {eth_chg:.1f}% = bearish divergence")
    elif oi_trend:
        parts.append(f"OI trend={oi_trend}")

    score = max(-1.0, min(1.0, score))
    return score, " | ".join(parts) or "N/A", _label(score)


def _s14(data, news):
    """§14 — Macro Risk Sentiment (CRITICAL ×2.0)"""
    macro_news = (news or {}).get("macro") or []
    if not macro_news:
        return 0, "No macro news available", "NEUT"
    bull = sum(1 for n in macro_news if n.get("impact") == "BULLISH")
    bear = sum(1 for n in macro_news if n.get("impact") == "BEARISH")
    titles = " ".join(n.get("title", "") for n in macro_news).lower()
    severe_bear = any(w in titles for w in ["recession", "crisis", "collapse", "crash", "default"])
    if severe_bear and bear > 0:
        return -1,  f"Macro risk-off — severe signals ({bear} bear / {bull} bull)", "BEAR"
    if bear > bull:
        return -0.5, f"Macro cautious ({bear} bear / {bull} bull)", "BEAR"
    if bull > bear:
        return 1,    f"Macro risk-on ({bull} bull / {bear} bear)", "BULL"
    return 0, f"Macro neutral ({bull} bull / {bear} bear)", "NEUT"


def _s15(data, news):
    """§15 — Crypto News Sentiment (STANDARD ×1.0)"""
    crypto_news = (news or {}).get("crypto") or []
    if not crypto_news:
        return 0, "No crypto news available", "NEUT"
    titles = " ".join(n.get("title", "") for n in crypto_news).lower()
    exploit_kw = ["hack", "exploit", "breach", "stolen", "fraud", "rug pull", "phishing"]
    if any(k in titles for k in exploit_kw):
        return -1, "Major security event in crypto news", "BEAR"
    bull = sum(1 for n in crypto_news if n.get("impact") == "BULLISH")
    bear = sum(1 for n in crypto_news if n.get("impact") == "BEARISH")
    if bull > bear:
        return 1,    f"Bullish crypto news ({bull} bull / {bear} bear)", "BULL"
    if bear > bull:
        return -0.5, f"Bearish crypto news ({bear} bear / {bull} bull)", "BEAR"
    return 0, f"Neutral crypto news ({bull} bull / {bear} bear)", "NEUT"


def _s16(data, _news):
    """§16 — CEX Exchange Flows On-Chain Accumulation (HIGH ×1.5)"""
    cex      = _g(data, "exchange_flows") or {}
    total_m  = cex.get("total_24h_usd_m")
    dir_24h  = cex.get("direction_24h") or ""
    total_1w = cex.get("total_1w_usd_m")
    if total_m is None:
        return 0, "N/A", "NEUT"
    desc = f"CEX net {total_m:+.0f}M USD/24h ({dir_24h})"
    if total_1w is not None:
        desc += f" | 1w={total_1w:+.0f}M"
    if total_m < -100:
        return 1,    f"Strong outflow (accumulation) — {desc}", "BULL"
    if total_m < 0:
        return 0.5,  f"Net outflow (accumulation) — {desc}", "BULL"
    if total_m > 100:
        return -1,   f"Strong inflow (selling pressure) — {desc}", "BEAR"
    if total_m > 0:
        return -0.5, f"Net inflow (selling pressure) — {desc}", "BEAR"
    return 0, desc, "NEUT"


def _s17(data, _news):
    """§17 — Bollinger Bands + MACD (STANDARD ×1.0)"""
    price    = _g(data, "eth", "price") or 0
    bb_upper = _g(data, "technicals", "bb_upper")
    bb_lower = _g(data, "technicals", "bb_lower")
    macd_l   = _g(data, "technicals", "macd_line")
    macd_s   = _g(data, "technicals", "macd_signal")
    macd_h   = _g(data, "technicals", "macd_hist")

    score = 0
    parts = []

    if bb_upper and bb_lower and price:
        if price > bb_upper:
            score -= 0.5
            parts.append(f"Above BB upper ({_fmt_price(bb_upper)})")
        elif price < bb_lower:
            score += 0.5
            parts.append(f"Below BB lower ({_fmt_price(bb_lower)})")
        else:
            parts.append(f"Inside BB ({_fmt_price(bb_lower)}–{_fmt_price(bb_upper)})")

    if macd_l is not None and macd_s is not None:
        cross = "bullish" if macd_l > macd_s else "bearish"
        score += 0.5 if macd_l > macd_s else -0.5
        hist_str = f" hist={macd_h:+.2f}" if macd_h is not None else ""
        parts.append(f"MACD {cross} ({macd_l:.2f} vs sig {macd_s:.2f}{hist_str})")

    score = max(-1.0, min(1.0, score))
    return score, " | ".join(parts) or "N/A", _label(score)


def _s18(data, _news):
    """§18 — BTC Influence: Dominance Tiers + 24h Direction (CRITICAL ×2.0)
    Bidirectional: +5% BTC rise in low-dom regime = ETH tailwind; -3% = ETH headwind."""
    dom     = _g(data, "btc", "dominance")
    beta    = _g(data, "btc", "beta_30d")
    corr    = _g(data, "btc", "correlation_30d")
    btc_p   = _g(data, "btc", "price")
    btc_24h = _g(data, "btc", "change_24h")
    parts   = []
    score   = 0

    dom_pct = None
    if dom is not None:
        dom_pct = float(dom) if float(dom) > 1 else float(dom) * 100
        if dom_pct > 58:
            score -= 1.0
            parts.append(f"BTC dom={dom_pct:.1f}% >58% (ETH headwind)")
        elif dom_pct > 55:
            score -= 0.5
            parts.append(f"BTC dom={dom_pct:.1f}% 55–58% (moderate headwind)")
        elif dom_pct > 50:
            parts.append(f"BTC dom={dom_pct:.1f}% neutral")
        else:
            score += 0.25
            parts.append(f"BTC dom={dom_pct:.1f}% <50% (altcoin tailwind)")

    if btc_24h is not None:
        btc_chg = float(btc_24h)
        if btc_chg > 5 and (dom_pct is None or dom_pct < 55):
            score += 0.5
            parts.append(f"BTC +{btc_chg:.1f}% 24h (rising, low dom — ETH tailwind)")
        elif btc_chg < -3:
            score -= 0.5
            parts.append(f"BTC {btc_chg:.1f}% 24h (falling — ETH beta amplifies)")
        else:
            parts.append(f"BTC {btc_chg:+.1f}% 24h")

    if beta is not None:
        parts.append(f"β={float(beta):.2f}x")
    if corr is not None:
        parts.append(f"30d corr={float(corr):.2f}")
    if btc_p is not None:
        parts.append(f"BTC={_fmt_price(btc_p)}")

    score = max(-1.0, min(1.0, score))
    return score, " | ".join(parts) or "N/A", _label(score)


def _s19(data, _news):
    """§19 — ETH/BTC Cross Ratio: relative performance vs BTC (STANDARD ×1.0)"""
    eth_price = _g(data, "eth", "price") or 0
    btc_price = _g(data, "btc", "price") or 0
    eth_24h   = _g(data, "eth", "change_24h")
    btc_24h   = _g(data, "btc", "change_24h")
    eth_7d    = _g(data, "eth", "change_7d")
    btc_7d    = _g(data, "btc", "change_7d")

    if not eth_price or not btc_price:
        return 0, "N/A", "NEUT"

    ratio = eth_price / btc_price
    parts = [f"ETH/BTC={ratio:.5f}"]
    score = 0

    if eth_24h is not None and btc_24h is not None:
        alpha_24h = float(eth_24h) - float(btc_24h)
        parts.append(f"24h alpha={alpha_24h:+.1f}%")
        if alpha_24h > 2:
            score += 0.5
        elif alpha_24h < -2:
            score -= 0.5

    if eth_7d is not None and btc_7d is not None:
        alpha_7d = float(eth_7d) - float(btc_7d)
        parts.append(f"7d alpha={alpha_7d:+.1f}%")
        if alpha_7d > 5:
            score += 0.5
        elif alpha_7d < -5:
            score -= 0.5

    score = max(-1.0, min(1.0, score))
    return score, " | ".join(parts), _label(score)


def _s20(data, _news):
    """§20 — Options IV / Put-Call Skew (PLACEHOLDER — pending paid API)"""
    return 0, "N/A — Options IV/skew (pending paid options data API)", "NEUT"


def _s21(data, _news):
    """§21 — Volatility Regime / Crypto VIX (PLACEHOLDER — pending data)"""
    return 0, "N/A — Volatility regime / crypto VIX (pending data source)", "NEUT"


# ─── scorers registry ────────────────────────────────────────────────────────

_SCORERS = [
    _s1,  _s2,  _s3,  _s4,  _s5,  _s6,  _s7,
    _s8,  _s9,  _s10, _s11, _s12, _s13, _s14,
    _s15, _s16, _s17, _s18, _s19, _s20, _s21,
]


# ─── flag detection ───────────────────────────────────────────────────────────

def _detect_flags(data, news, scorecard) -> list:
    flags = []
    price = _g(data, "eth", "price") or 0
    supports    = _g(data, "technicals", "supports")    or []
    resistances = _g(data, "technicals", "resistances") or []

    sups_below = [s for s in supports    if s < price]
    res_above  = [r for r in resistances if r > price]
    nearest_sup = max(sups_below) if sups_below else None
    nearest_res = min(res_above)  if res_above  else None

    net = scorecard.get("aggregate", {}).get("net_score", 0)

    if nearest_sup and price < nearest_sup * 1.02:
        if net < 0:
            flags.append("RULE VIOLATION: ETH near key support — short entry not advised")

    if nearest_res and price > nearest_res * 0.98:
        if net > 0:
            flags.append("RULE VIOLATION: ETH near key resistance — long entry not advised")

    fng_val = _g(data, "fear_greed", "value")
    rsi_val = _g(data, "technicals", "rsi")
    if fng_val is not None and rsi_val is not None:
        if int(fng_val) < 20 and float(rsi_val) < 30:
            flags.append("CAPITULATION ZONE: F&G <20 + RSI <30 → weight contrarian long")

    if fng_val is not None and rsi_val is not None:
        if int(fng_val) > 80 and float(rsi_val) > 70:
            flags.append("EUPHORIA ZONE: F&G >80 + RSI >70 → weight contrarian short")

    htx_fr = _g(data, "derivatives", "htx", "funding_rate")
    okx_fr = _g(data, "derivatives", "okx", "funding_rate")
    fr = htx_fr if htx_fr is not None else okx_fr
    if fr is not None and float(fr) < -0.05:
        flags.append(f"SQUEEZE RISK: Funding rate {float(fr):.4f}% — crowded shorts")

    return flags


# ─── trade option builder ────────────────────────────────────────────────────

def _build_options(data, news, scores_dict, weighted_net) -> dict:
    price       = _g(data, "eth", "price") or 2000
    btc_price   = _g(data, "btc", "price") or 60000
    supports    = _g(data, "technicals", "supports")    or []
    resistances = _g(data, "technicals", "resistances") or []

    sups_below = sorted([s for s in supports    if s < price], reverse=True)
    res_above  = sorted([r for r in resistances if r > price])

    sup1 = sups_below[0] if sups_below else round(price * 0.97)
    sup2 = sups_below[1] if len(sups_below) > 1 else round(price * 0.94)
    res1 = res_above[0]  if res_above  else round(price * 1.03)
    res2 = res_above[1]  if len(res_above) > 1 else round(price * 1.06)

    btc_sup = round(btc_price * 0.97)
    btc_res = round(btc_price * 1.03)

    is_long = weighted_net >= 0
    conf_a  = min(90, max(40, int(50 + (abs(weighted_net) / _MAX_WEIGHTED) * 40)))
    conf_b  = max(15, min(60, int(50 - (abs(weighted_net) / _MAX_WEIGHTED) * 40)))

    bull_sections = sorted(
        [(k, v) for k, v in scores_dict.items() if v["score"] > 0],
        key=lambda x: -x[1]["score"]
    )
    bear_sections = sorted(
        [(k, v) for k, v in scores_dict.items() if v["score"] < 0],
        key=lambda x: x[1]["score"]
    )

    def _driver_text(sections, n=2):
        return "; ".join(f"{k} ({v['value'][:60]})" for k, v in sections[:n])

    if is_long:
        entry_a   = [round(sup1 * 1.002), round(sup1 * 1.012)]
        target1_a = round(res1)
        target2_a = round(res2)
        stop_a    = round(sup1 * 0.96)
        manual_a  = round(sum(entry_a) / 2 * 1.07)
        cond_a    = f"ETH holds above {_fmt_price(sup1)} AND BTC reclaims {_fmt_price(btc_sup)}"
        thesis_a  = (
            f"Weighted net {weighted_net:+.1f} — bullish bias driven by {_driver_text(bull_sections)}. "
            f"Entry targets {_fmt_price(sup1)} support with {_fmt_price(res1)} as first objective. "
            f"BTC {_fmt_price(btc_price)} must hold {_fmt_price(btc_sup)} for confirmation."
        )
        risks_a   = [
            f"BTC loses {_fmt_price(btc_sup)} → invalidates long setup",
            f"Close below {_fmt_price(sup1)} support triggers stop at {_fmt_price(stop_a)}",
            f"Bear counter: {_driver_text(bear_sections, 1) or 'limited downside catalysts'}",
        ]

        entry_b   = [round(res1 * 0.99), round(res1 * 1.01)]
        target1_b = round(price * 0.96)
        target2_b = round(sup1)
        stop_b    = round(res1 * 1.04)
        manual_b  = round(sum(entry_b) / 2 * 0.97)
        cond_b    = f"ETH rejects {_fmt_price(res1)} resistance AND BTC loses {_fmt_price(btc_res)}"
        thesis_b  = (
            f"Contrarian short: price approaching resistance at {_fmt_price(res1)} "
            f"with bearish signals from {_driver_text(bear_sections)}. "
            f"Only valid on clean rejection — do not front-run."
        )
        risks_b   = [
            f"Breakout above {_fmt_price(res1)} — short squeezed to {_fmt_price(res2)}",
            f"Weighted net is positive ({weighted_net:+.1f}) — primary bias opposes this trade",
        ]
        reason_c  = (
            f"Long setup (A) requires ETH to hold {_fmt_price(sup1)}; short setup (B) requires "
            f"rejection at {_fmt_price(res1)}. Both entries need BTC confirmation."
        )
        watch_a   = f"ETH closes 4h candle above {_fmt_price(sup1)} with volume expansion"
        watch_b   = f"ETH wick rejection at {_fmt_price(res1)} on elevated volume"

    else:
        entry_a   = [round(res1 * 0.99), round(res1 * 1.005)]
        target1_a = round(sup1)
        target2_a = round(sup2)
        stop_a    = round(res1 * 1.04)
        manual_a  = round(sum(entry_a) / 2 * 0.95)
        cond_a    = f"ETH fails to hold {_fmt_price(res1)} resistance AND BTC loses {_fmt_price(btc_sup)}"
        thesis_a  = (
            f"Weighted net {weighted_net:+.1f} — bearish bias driven by {_driver_text(bear_sections)}. "
            f"Short entry near {_fmt_price(res1)} resistance targeting {_fmt_price(sup1)}. "
            f"BTC {_fmt_price(btc_price)} losing {_fmt_price(btc_sup)} is primary catalyst."
        )
        risks_a   = [
            f"BTC reclaims {_fmt_price(btc_res)} → breaks bear thesis",
            f"Close above {_fmt_price(res1)} triggers stop at {_fmt_price(stop_a)}",
            f"Bull counter: {_driver_text(bull_sections, 1) or 'limited upside catalysts'}",
        ]

        entry_b   = [round(sup1 * 1.002), round(sup1 * 1.015)]
        target1_b = round(res1)
        target2_b = round(res2)
        stop_b    = round(sup1 * 0.96)
        manual_b  = round(sum(entry_b) / 2 * 1.05)
        cond_b    = f"ETH bounces from {_fmt_price(sup1)} AND BTC holds {_fmt_price(btc_sup)}"
        thesis_b  = (
            f"Contrarian long: primary bias is bearish but {_driver_text(bull_sections)} "
            f"may support a bounce from {_fmt_price(sup1)}. Only on confirmed support hold."
        )
        risks_b   = [
            f"Support at {_fmt_price(sup1)} fails → flush to {_fmt_price(sup2)}",
            f"Weighted net is negative ({weighted_net:+.1f}) — primary bias opposes this trade",
        ]
        reason_c  = (
            f"Short setup (A) requires rejection at {_fmt_price(res1)}; long setup (B) requires "
            f"confirmed bounce from {_fmt_price(sup1)}. Both need BTC direction first."
        )
        watch_a   = f"ETH 4h close below {_fmt_price(res1)} with BTC failing {_fmt_price(btc_sup)}"
        watch_b   = f"ETH bounces {_fmt_price(sup1)} with strong 4h close above"

    dir_a = "LONG" if is_long else "SHORT"
    dir_b = "SHORT" if is_long else "LONG"

    return {
        "A": {
            "direction":       dir_a,
            "confidence":      conf_a,
            "entry_condition": cond_a,
            "entry_zone":      entry_a,
            "target1":         target1_a,
            "target2":         target2_a,
            "stop":            stop_a,
            "manual_exit":     manual_a,
            "thesis":          thesis_a,
            "risks":           risks_a,
        },
        "B": {
            "direction":       dir_b,
            "confidence":      conf_b,
            "entry_condition": cond_b,
            "entry_zone":      entry_b,
            "target1":         target1_b,
            "target2":         target2_b,
            "stop":            stop_b,
            "manual_exit":     manual_b,
            "thesis":          thesis_b,
            "risks":           risks_b,
        },
        "C": {
            "reason":       reason_c,
            "watch_for_A":  watch_a,
            "watch_for_B":  watch_b,
            "invalidation": (
                f"ETH outside {_fmt_price(sup1)}–{_fmt_price(res1)} range "
                f"without BTC confirmation — reassess entirely"
            ),
        },
    }


# ─── main scoring engine ──────────────────────────────────────────────────────

def run_analysis(data: dict) -> dict:
    """Score all 21 sections, apply tier weights, and return the full structured result."""
    news = data.get("news") or {}

    scorecard = {}
    for i, scorer in enumerate(_SCORERS, 1):
        section = f"§{i}"
        try:
            score, value, lbl = scorer(data, news)
        except Exception as e:
            print(f"[analysis] {section} error: {e}")
            score, value, lbl = 0, "Error", "NEUT"
        weight = _WEIGHTS.get(section, 1.0)
        scorecard[section] = {
            "value":    value,
            "score":    score,
            "label":    lbl,
            "tier":     _TIER_NAMES.get(section, "STANDARD"),
            "weight":   weight,
            "weighted": round(score * weight, 2),
        }

    # Weighted aggregate (§1 context=0, §20/§21 placeholder=0 — auto-excluded)
    weighted_net = round(sum(v["weighted"] for v in scorecard.values()), 2)
    bull_count = sum(1 for k, v in scorecard.items() if v["score"] > 0 and k != "§1")
    bear_count = sum(1 for k, v in scorecard.items() if v["score"] < 0 and k != "§1")
    neut_count = sum(1 for k, v in scorecard.items() if v["score"] == 0 and k != "§1")

    direction  = "LONG" if weighted_net >= 0 else "SHORT"
    confidence = min(90, max(40, round(50 + (weighted_net / _MAX_WEIGHTED) * 40)))

    aggregate = {
        "bullish":    bull_count,
        "bearish":    bear_count,
        "neutral":    float(neut_count),
        "net_score":  weighted_net,
        "confidence": confidence,
        "direction":  direction,
    }

    options = _build_options(data, news, scorecard, weighted_net)
    conf_a  = options["A"]["confidence"]
    conf_b  = options["B"]["confidence"]
    conf_c  = max(0, 100 - conf_a - conf_b)

    ranked = sorted([
        {"rank": 0, "option": "A", "label": "OPTION A",
         "summary": f"{options['A']['direction']} {options['A']['entry_zone'][0]}–{options['A']['entry_zone'][1]} · stop {options['A']['stop']} · T1 {options['A']['target1']}",
         "_conf": conf_a},
        {"rank": 0, "option": "B", "label": "OPTION B",
         "summary": f"{options['B']['direction']} {options['B']['entry_zone'][0]}–{options['B']['entry_zone'][1]} · stop {options['B']['stop']} · T1 {options['B']['target1']}",
         "_conf": conf_b},
        {"rank": 0, "option": "C", "label": "OPTION C",
         "summary": f"Wait — {options['C']['watch_for_A'][:80]}",
         "_conf": conf_c},
    ], key=lambda x: -x["_conf"])
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
        del r["_conf"]

    flags = _detect_flags(data, news, {"aggregate": aggregate})

    return {
        "scorecard": scorecard,
        "aggregate": aggregate,
        "options":   options,
        "ranked":    ranked,
        "flags":     flags,
        "_source":   "deterministic-rules-v2",
    }


# ─── routes ──────────────────────────────────────────────────────────────────

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
