# ETH/USDT Signal Scoring Specification
**Dashboard: ETH Pre-Trade Analysis Engine**
**Instrument: ETH/USDT Perpetual — HTX Exchange — 5× Leverage**
**Hold target: 4–12 hours**
**Version: 2.1 — Weighted Tier System (21 Sections)**

---

## 1. Purpose and Scope

This document defines the complete signal scoring framework used by the `/analysis` Telegram command. It covers every data source, scoring threshold, tier weight, and the confidence formula.

The system scores 21 signal sections (§1 context, §2–§19 active, §20–§21 placeholders) using live market data fetched from 40+ external APIs. Each scored section produces a raw score from −1.0 to +1.0 in 0.5 steps. A tier multiplier is applied before summation. The result is a weighted net score that drives direction (LONG/SHORT) and confidence (40–90%).

**Delivery:** All output reaches the trader via Telegram bot. No frontend UI. Zero LLM calls — scoring is deterministic Python. `_source: deterministic-rules-v2`

**This is a decision-support framework, not an autonomous trading system.** All trade entries, sizing, and exits remain at the discretion of the trader.

---

## 2. Trading Context — Why These Parameters

| Parameter | Value | Implication for Scoring |
|---|---|---|
| Instrument | ETH/USDT Perpetual | ETH-specific signals weighted higher than general crypto |
| Leverage | 5× | Entry timing is critical — being right on direction but wrong on timing is losing |
| Hold target | 4–12 hours | Intraday signals dominate; multi-day signals provide structure only |
| Exchange | HTX | Derivatives signals sourced from HTX primary, OKX secondary |
| Stop loss | ~20% ETH move | A 20% adverse move on 5× wipes the position — Critical signals that flip bearish mid-trade matter enormously |
| Take profit | ~40% ETH move | Requires a sustained directional move — macro and institutional signals must align |

---

## 3. Four-Tier Architecture

Sections §2–§19 are actively scored (18 sections). §1 is context-only (weight 0). §20–§21 are placeholders (weight 0, always N/A). Each active section falls into one of four tiers. The tier multiplier is applied to the raw section score before adding to the net score.

### CRITICAL — Multiplier ×2.0

**Definition:** Regime-defining signals. When a Critical signal fires at full magnitude (±1.0 raw → ±2.0 weighted), it cannot be offset by anything below Critical tier alone. A death cross at −2.0 weighted requires another Critical signal at +1.0 or higher just to reach neutral.

**Why these sections are Critical:**
- They reflect forces large enough to move ETH 10–20% within the hold window
- Being on the wrong side of them with 5× leverage means maximum loss before other signals resolve
- Historically: Fed rate decisions, BTC trend breaks, and large ETF flow reversals have all preceded 15%+ ETH moves within hours

**Critical sections:** §5 (MA Trend Regime), §8 (ETF Institutional Flows), §14 (Macro Risk Sentiment), §18 (BTC Influence)

> **Quantitative note:** §14 (Macro) and §18 (BTC) are frequently correlated — a risk-on macro event (Fed dovish surprise) typically pushes BTC higher simultaneously. When both fire at +1.0, the combined +4.0 weighted contribution may partially represent the same underlying event. This is acknowledged but accepted: when macro AND BTC both confirm risk-on, the trade conviction should be higher, not lower.

---

### HIGH — Multiplier ×1.5

**Definition:** Entry-timing signals. These determine whether a trade entered NOW has clean structure — clean entry, correct momentum, favorable squeeze/accumulation dynamics. For a 4-hour hold, a poor entry on a good direction thesis still loses.

**Why these sections are High:**
- RSI directly measures whether price is extended — entering a 5× long at RSI 72 is entering into exhaustion regardless of the direction thesis
- Price vs EMA stack tells you where price sits relative to the most-watched levels on any trading desk
- Support/Resistance R/R determines if the setup offers favorable asymmetry
- Derivatives (funding + L/S ratio) can cause involuntary position unwinds via liquidation cascades
- Exchange flows show whether smart money is accumulating or distributing

**High sections:** §6 (RSI Daily), §7 (S/R Reward/Risk), §9 (Price vs EMA Stack), §13 (Derivatives), §16 (Exchange Flows)

---

### STANDARD — Multiplier ×1.0

**Definition:** Supporting signals. Meaningful when aligned with higher-tier signals but not decisive alone. Primarily structural context (where has price been this week, what do technical overlays say) and event-driven news that may or may not resolve within the hold window.

**Standard sections:** §2 (Weekly Range vs EMA Structure), §15 (Crypto News), §17 (Bollinger + MACD)

---

### LOW — Multiplier ×0.5

**Definition:** Context signals. Either too slow-moving for a 4–12h trade, overlapping a higher-weighted section, or currently limited by data quality. These contribute directional color but are intentionally dampened so they cannot swing a close decision.

**Low sections:** §3 (Crypto F&G), §4 (ETH F&G), §10 (Supply/Burn), §11 (Staking Flows), §12 (Social/CT)

> **Why F&G is Low:** Both F&G indexes move slowly and are already partially reflected in §6 (RSI), §5 (MA cross), and §13 (derivatives positioning). Their primary value is identifying capitulation or euphoria extremes, both of which are captured in the flag system (hard rules 5 and 6) independently of the weighted score.

---

## 4. Score Architecture

```
weighted_net = Σ (raw_score_i × tier_multiplier_i)   for i in §2..§19
               (§20, §21 placeholders always = 0, excluded automatically)
direction    = LONG  if weighted_net ≥ 0
               SHORT if weighted_net < 0
confidence   = clamp(50% + (weighted_net / 20.0) × 40%, floor=40%, cap=90%)
```

### Maximum weighted scores by tier

| Tier | Sections | Multiplier | Max Bull | Max Bear | % of Total |
|---|---|---|---|---|---|
| CRITICAL | §5, §8, §14, §18 | ×2.0 | +8.00 | −8.00 | 40% |
| HIGH | §6, §7, §9, §13, §16 | ×1.5 | +6.75 | −6.75 | 34% |
| STANDARD | §2, §15, §17, §19 | ×1.0 | +4.00 | −4.00 | 20% |
| LOW | §3, §4, §10, §11, §12 | ×0.5 | +1.25 | −1.75 | ~6% |
| PLACEHOLDER | §20, §21 | ×0.0 | 0 | 0 | — |
| **Total** | | | **+20.00** | **−20.50** | |

> The Low tier's max bearish (−1.75) exceeds its max bullish (+1.25) because §11 (Staking) and §12 (Social) are asymmetric: they can score −1.0 raw (large unstaking event / security alert) but only +0.5 raw on the upside. §19 (ETH/BTC cross) increases Standard tier max from ±3.00 to ±4.00, raising the total denominator from 19.0 to 20.0.

### Confidence scale

| Weighted Net | % of Max | Confidence | Practical Meaning |
|---|---|---|---|
| 0.0 | 0% | 50% | Coin flip — no edge |
| ±1.5 | 8% | 53% | One Critical signal, slight tilt |
| ±3.0 | 16% | 56% | One Critical + one High aligned |
| ±5.0 | 26% | 61% | Mixed Critical signals, some High |
| ±7.0 | 37% | 65% | Two Critical + High aligned |
| ±9.0 | 47% | 69% | Most sections in agreement |
| ±11.0 | 58% | 73% | Strong multi-tier alignment |
| ±14.0 | 74% | 79% | Near-maximum conviction |
| ±17.0 | 89% | 86% | Almost all signals maxed |

**The 90% cap is intentional.** No combination of signals on a 5× leveraged instrument should project more than 90% confidence — market structure can change faster than any scorecard can update.

---

## 5. Section Reference — All 18 Sections

---

### §1 — ETH Price + Intraday Range
**Tier:** CONTEXT (never scored — always 0)
**Data sources:** CoinGecko (price, 24h high/low, change %), Crypto.com (last trade)
**What it captures:** Current ETH/USDT price and the day's trading range
**Scoring:** Always 0. Displayed in the scorecard header as reference for all other sections.
**Quant note:** The 24h range is used implicitly by §6 (RSI) and §17 (Bollinger). Displaying it explicitly prevents misinterpretation of other scores without price context.

---

### §2 — Weekly Range vs EMA20/50/200
**Tier:** STANDARD (×1.0) | Raw: −1.0 to +1.0 | **Max weighted: ±1.00**
**Data sources:** CoinGecko 7-day price history (weekly high/low), Crypto.com 1D candles → EMA calculations
**What it captures:** Where has price spent the week relative to the three primary moving average levels
**Scoring logic:**

| Condition | Raw Score | Reasoning |
|---|---|---|
| Weekly range entirely above EMA20, EMA50, EMA200 | +1.0 | Full bull structure — price has not revisited any key MA all week |
| Weekly range above EMA50 and EMA200, touching EMA20 | +0.75 | Slight softness at the short-term MA but structure intact |
| Weekly range above EMA200, below EMA50 | +0.5 | Broad support holds, but medium-term trend under pressure |
| Weekly range spanning EMA200 (testing it) | 0 | Decision zone — market is at the key long-term level |
| Weekly range below EMA20, above EMA50 | −0.25 | Short-term trend broken, medium intact |
| Weekly range below EMA20 and EMA50 | −0.75 | Two levels of structure lost |
| Weekly range entirely below EMA20, EMA50, EMA200 | −1.0 | Full bear structure — no MA providing support this week |

**Quant note:** This is a STRUCTURE signal, not a NOW signal. It tells you where the market has been, not where it is this second. Standard tier is appropriate — it contributes color to §9 (Price vs EMA Stack) rather than duplicating it. Together they answer: "where was price this week" (§2) and "where is price right now" (§9).

---

### §3 — Crypto Fear & Greed Index (Contrarian)
**Tier:** LOW (×0.5) | Raw: −0.5 to +0.5 | **Max weighted: ±0.25**
**Data source:** CoinMarketCap `/v3/fear-and-greed/latest` and `/historical` (7-day trend)
**What it captures:** Aggregate crypto market sentiment index (0 = extreme fear, 100 = extreme greed)
**Scoring logic:**

| F&G Value | Raw Score | Label |
|---|---|---|
| < 20 Extreme Fear | +0.5 | Contrarian long signal |
| 20–45 Fear | +0.25 | Mild contrarian lean |
| 45–55 Neutral | 0 | No signal |
| 55–75 Greed | −0.25 | Mild caution |
| > 80 Extreme Greed | −0.5 | Contrarian short signal |

**Quant note:** F&G is a lagging sentiment aggregator — it synthesizes price momentum, volume, social sentiment, surveys, and options data. Most of those inputs are already captured independently by other sections (RSI, volume via technicals, social via §12, derivatives via §13). Low tier prevents double-counting. More critically: F&G at 70–85 ("Greed") can persist for months in bull markets. Contrarian signals from F&G work better as exits than entries, and are most reliable only at the extremes (<15, >85). The flag system independently catches F&G + RSI combined extremes (rules 5 and 6), which is more reliable than the raw score alone.

---

### §4 — ETH Fear & Greed Index (Contrarian)
**Tier:** LOW (×0.5) | Raw: −0.5 to +0.5 | **Max weighted: ±0.25**
**Data source:** ethereumfear.com (Next.js page scrape — ETH-specific F&G)
**What it captures:** ETH-specific sentiment index, isolated from BTC and broader crypto
**Scoring logic:** Identical thresholds to §3
**Quant note:** ETH F&G diverges from Crypto F&G when ETH outperforms or underperforms BTC. When the two indexes diverge significantly (e.g., Crypto F&G = 65, ETH F&G = 30), it signals ETH-specific fear during a broader market grind-up — historically a strong contrarian long signal for ETH specifically. This divergence is not currently captured in the scoring; it is a potential enhancement. Low tier appropriate given overlap with §3.

---

### §5 — EMA50 vs EMA200 Cross (Trend Regime)
**Tier:** CRITICAL (×2.0) | Raw: −1.0 to +1.0 | **Max weighted: ±2.00**
**Data source:** Crypto.com 200-day 1D candles → pure-Python EMA calculation
**What it captures:** The macro trend regime — whether the medium-term trend (EMA50) is above or below the long-term trend (EMA200)
**Scoring logic:**

| Condition | Raw Score | Label |
|---|---|---|
| EMA50 > EMA200 by > 0.5% | +1.0 | Golden cross — bull regime confirmed |
| EMA50 > EMA200 by 0–0.5% | +0.5 | Converging bullish — cross imminent |
| EMA50 < EMA200 by 0–0.5% | −0.5 | Converging bearish — death cross forming |
| EMA50 < EMA200 by > 0.5% | −1.0 | Death cross — bear regime confirmed |

**Quant rationale for Critical tier:** The 50/200 cross is one of the most widely watched technical signals across institutional and retail participants. Its self-fulfilling nature means it triggers actual buy/sell flows at these levels. A 5× leveraged long position entered during a confirmed death cross (−2.0 weighted) faces structural headwinds that no amount of favorable short-term signals should override. This is the single most important reason for Critical classification.

**Limitation:** The cross is a lagging indicator — EMA50 crossing below EMA200 confirms a downtrend that has already been developing. It does not predict reversals. For a 4-hour hold, a death cross rules out aggressive long entries but does not by itself mandate a short.

---

### §6 — RSI Daily (Entry Timing)
**Tier:** HIGH (×1.5) | Raw: −1.0 to +1.0 | **Max weighted: ±1.50**
**Data source:** Crypto.com 1D candles (200-day) + 4h candles → 14-period Wilder's RSI
**What it captures:** Momentum and overbought/oversold conditions on the daily timeframe
**Scoring logic:**

| RSI(14) Daily | Raw Score | Reasoning |
|---|---|---|
| < 30 | +1.0 | Oversold — statistically unusual, strong mean-reversion signal |
| 30–45 | −0.5 | Weakening momentum — market losing ground |
| 45–55 | 0 | Neutral momentum |
| 55–70 | +0.5 | Sustained strength — uptrend intact |
| > 70 | −1.0 | Overbought — dangerous entry zone for 5× long |

**Quant note:** RSI 30–45 scoring −0.5 reflects weakening directional momentum, not necessarily a short signal. In a bull market, RSI 30–45 is often a buying opportunity. However, for a 5× leveraged entry, entering into declining momentum is risky even if the long-term trend is intact — the position may need to endure a further drawdown before recovery, and the stop loss may be hit first.

The 4h RSI (`technicals.rsi_4h`) is shown in the scorecard value string but does not independently adjust the score. It provides a useful divergence signal: if the daily RSI is bearish (35) but the 4h RSI has recovered to 55, the momentum may be turning intraday — a nuance the trader should evaluate manually.

---

### §7 — Support/Resistance Reward-to-Risk
**Tier:** HIGH (×1.5) | Raw: −0.5 to +0.5 | **Max weighted: ±0.75**
**Data source:** Crypto.com 1D candles → pure-Python swing high/low algorithm (50-candle lookback, 1.5% cluster tolerance)
**What it captures:** The ratio of potential upside (distance to nearest resistance) to potential downside (distance to nearest support) from current price
**Scoring logic:**

| R/R Ratio | Raw Score | Label |
|---|---|---|
| > 2:1 | +0.5 | Favorable setup — upside at least 2× the risk |
| 1:1 to 2:1 | 0 | Acceptable but not ideal |
| < 1:1 | −0.5 | Unfavorable — downside exceeds upside |

**Quant note:** This section enforces one of the most fundamental rules of professional trading: only take asymmetric setups. A LONG signal with R/R < 1:1 means the stop is far below while the target is close above — the math doesn't work on a probabilistic basis even with high directional confidence. High tier is justified because a poor R/R score (−0.75 weighted) should be a serious brake on otherwise bullish signals.

**Limitation:** The swing algorithm uses 50 daily candles. S/R levels identified on the daily timeframe may not reflect intraday microstructure levels. For 4-hour entries, the trader should verify the key levels on a 4h chart manually.

---

### §8 — ETF Net Flows (Institutional Direction)
**Tier:** CRITICAL (×2.0) | Raw: −1.0 to +1.0 | **Max weighted: ±2.00**
**Data source:** SoSoValue openapi `/etfs/summary-history?symbol=ETH&country_code=US` — daily/weekly/monthly net inflows
**What it captures:** Net USD flowing into or out of the 8 US spot ETH ETFs (ETHA, FETH, ETHE, ETH, ETHW, TETH, QETH, ETHV)
**Scoring logic:**

| Daily Net Flow | Raw Score | Reasoning |
|---|---|---|
| > +$100M | +1.0 | Strong institutional accumulation |
| +$50M to +$100M | +0.5 | Moderate institutional buying |
| −$50M to +$50M | 0 | Neutral institutional activity |
| −$100M to −$50M | −0.5 | Moderate institutional selling |
| < −$100M | −1.0 | Strong institutional distribution |

**Quant rationale for Critical tier:** The US spot ETH ETFs collectively hold billions in AUM. Net daily flows represent new institutional capital entering or leaving the ETH market — not paper trading, not derivatives, actual spot buying and selling. $100M+ inflows represent significant demand pressure. $100M+ outflows represent significant supply pressure. These flows do not resolve within hours — they reflect multi-day institutional positioning decisions that tend to persist.

**Critical limitation — data lag:** SoSoValue reports the most recent complete trading day. This means the flow data is approximately 20–32 hours old when used in a live analysis. A strong inflow yesterday does not guarantee continued inflow today. The signal is directional guidance, not a same-hour confirmation.

---

### §9 — Price vs EMA Stack (EMA20 / EMA50 / EMA200)
**Tier:** HIGH (×1.5) | Raw: −1.0 to +1.0 | **Max weighted: ±1.50**
**Data source:** Crypto.com 1D candles → pure-Python EMA calculations (20, 50, 200 periods)
**What it captures:** Where is ETH price RIGHT NOW relative to the three most-watched moving averages
**Scoring logic:**

| Price Position | Raw Score | Label |
|---|---|---|
| Above EMA20, EMA50, and EMA200 | +1.0 | Full bull stack — all MAs providing support below |
| Above EMA20 and EMA50, below EMA200 | +0.5 | Recovering — medium-term support intact, long-term resistance above |
| Above EMA20 only | 0 | Short-term bounce — no structural backing |
| Below EMA20 only (recently lost) | −0.25 | Short-term support lost |
| Below EMA20 and EMA50 | −0.5 | Momentum broken — two key levels acting as resistance |
| Below EMA20, EMA50, and EMA200 | −1.0 | Full bear stack — all MAs providing resistance above |

**Why this replaces Gas:** Gas (gwei) was previously §9. Since EIP-4844 (Dencun upgrade, March 2024), blob transactions moved fee pressure off the execution layer. Gas has been near 0 gwei consistently — scoring −0.5 on every analysis regardless of market conditions. It provided no signal and created a structural bearish drag on every score. Removed.

**Quant rationale for High tier:** For a 4-hour hold, where price sits relative to EMA20/50/200 RIGHT NOW is more actionable than where the weekly range has been (§2) or what the 50/200 cross says about the macro regime (§5). A trader entering at current price needs to know if they are entering above or below structure — these three EMAs represent where the largest number of market participants have their cost basis and their mental stop levels.

**Relationship with §5:** §5 tells you the regime (golden/death cross = macro). §9 tells you the position (where is price within that regime). They are complementary, not duplicative. A golden cross regime (§5 = +1.0) with price below EMA20 (§9 = −0.25) signals a pullback within a bull regime — potentially a long entry opportunity. A death cross regime (§5 = −1.0) with price above all EMAs (§9 = +1.0) signals a dead-cat bounce within a bear regime — a potential short entry.

---

### §10 — ETH Supply / Burn (Deflationary Signal)
**Tier:** LOW (×0.5) | Raw: −0.5 to +0.5 | **Max weighted: ±0.25**
**Data source:** ultrasound.money API v2 `/fees/gauge-rates` — annualized issuance and burn rates
**What it captures:** Whether the current fee burn rate exceeds ETH issuance (deflationary) or falls below it (inflationary)
**Scoring logic:**

| Condition | Raw Score |
|---|---|
| Net deflationary (burn rate > issuance rate) | +0.5 |
| Net inflationary (issuance rate > burn rate) | −0.5 |

**Quant note:** ETH supply dynamics are a long-term fundamental signal. Whether ETH is burning 34 ETH per day versus 2,400 ETH per day is driven by network activity (gas usage) and does not directly influence 4-hour price action. Kept in the scorecard as a fundamental reference and for longer-horizon trade context. Low tier ensures its maximum contribution (+0.25 weighted) cannot meaningfully influence an otherwise balanced scorecard.

---

### §11 — Staking Flows (24-Hour Net)
**Tier:** LOW (×0.5) | Raw: −1.0 to +0.5 | **Max weighted: +0.25 / −0.50**
**Data sources:** Etherscan v2 API (24h beacon deposit log count), ETH public RPC drpc.org (withdrawal sampling from 6 block samples)
**What it captures:** Net ETH entering or leaving the beacon chain over the past 24 hours
**Scoring logic:**

| Condition | Raw Score |
|---|---|
| Large unstaking event > 50,000 ETH/24h | −1.0 |
| Net staking outflow (moderate) | 0 |
| Net neutral | 0 |
| Net staking inflow | +0.5 |

**Asymmetric scoring rationale:** Normal daily staking variance (a few thousand ETH either direction) is not a tradeable signal — it's network noise. The −1.0 score only triggers on genuinely large unstaking events (>50,000 ETH in 24h) which signal either a large validator exit queue clearing or a protocol concern — both of which are potential supply shock events worth flagging. The +0.5 maximum upside reflects that steady staking inflow is mildly bullish (ETH locked = reduced circulating supply) but not dramatically so on a 4-hour timeframe.

---

### §12 — Social / CT Sentiment
**Tier:** LOW (×0.5) | Raw: −1.0 to +0.5 | **Max weighted: +0.25 / −0.50**
**Data source:** SoSoValue API `/news?category=4` — verified crypto Twitter/X accounts
**What it captures:** BULLISH/BEARISH/NEUTRAL classification of recent CT posts from verified crypto accounts
**Scoring logic:**

| Condition | Raw Score |
|---|---|
| Security alert detected (hack/exploit/rug/breach keyword) | −1.0 |
| > 60% of posts classified BEARISH | −0.5 |
| Mixed / neutral | 0 |
| > 60% of posts classified BULLISH | +0.5 |

**Current data quality limitation:** SoSoValue category 4 returns a general pool of verified crypto accounts (crypto.news, The Block, Ansem, Laura Shin, etc.) but does NOT filter to the specific high-signal accounts originally targeted (@WatcherGuru, @VitalikButerin, @PeckShieldAlert, @CertiKAlert, @whale_alert). The current pool is general CT sentiment — useful for detecting security events (keyword scan) but weak for directional signals. Low tier weight appropriately limits its influence. If targeted account feeds become available, this section should be re-evaluated for tier elevation.

---

### §13 — Derivatives: Funding Rate + Long/Short Ratio
**Tier:** HIGH (×1.5) | Raw: −1.0 to +1.0 | **Max weighted: ±1.50**
**Data sources:** HTX `/linear-swap-api/v1/swap_funding_rate` (primary), OKX `/api/v5/public/funding-rate` (secondary), HTX elite account L/S ratio, HTX OI history
**What it captures:** The cost to hold a leveraged position (funding rate) and the balance between leveraged longs and shorts
**Scoring logic:**

| Signal | Condition | Score Component |
|---|---|---|
| Funding rate | < −0.05% (shorts crowded) | +0.5 |
| Funding rate | > +0.05% (longs crowded) | −0.5 |
| Funding rate | −0.05% to +0.05% | 0 |
| L/S Ratio | > 1.5 AND RSI < 50 | +0.5 (squeeze setup with momentum context) |
| L/S Ratio | > 1.5 AND RSI ≥ 50 | 0 (crowded longs only — no squeeze signal) |
| L/S Ratio | < 0.8 (shorts outnumber longs) | −0.5 |
| OI trend | Rising OI + price falling | −1.0 (overrides, bearish divergence) |

Combined score capped at ±1.0 before multiplier.

**Quant note on funding rate interpretation:** A negative funding rate means short-sellers are paying long-holders — this is a contrarian bullish signal ONLY when paired with a directional catalyst. In isolation, deeply negative funding = market consensus is bearish. The +0.5 score for negative funding reflects the squeeze risk (shorts forced to cover pushes price up), not a belief that the bearish consensus is wrong. This is intentionally context-dependent: the flag system separately alerts `SQUEEZE RISK` when funding is extreme.

**Quant note on L/S ratio:** L/S > 1.5 means longs are crowded. With RSI ≥ 50 (momentum already bullish), additional long crowding adds risk rather than opportunity — the +0.5 squeeze bonus is withheld. With RSI < 50 (momentum neutral or bearish), a high L/S ratio in weak momentum conditions is exactly where shorts pile on and get squeezed when price reverses. This context-dependent rule prevents awarding squeeze bonus into an already-extended uptrend.

---

### §14 — Macro Risk Sentiment
**Tier:** CRITICAL (×2.0) | Raw: −1.0 to +1.0 | **Max weighted: ±2.00**
**Data source:** SoSoValue API `/news?category=13` (WSJ, Barron's, Reuters, AP, MarketWatch) → keyword-based BULLISH/BEARISH/NEUTRAL classification
**What it captures:** Whether the macro environment is risk-on or risk-off based on current headlines
**Scoring logic:**

| Condition | Raw Score |
|---|---|
| All 3 macro headlines BULLISH, no severe keywords | +1.0 |
| Bull headlines > Bear | +0.5 |
| Mixed or all neutral | 0 |
| Bear headlines > Bull | −0.5 |
| Bear headlines + severe keywords (recession/crisis/collapse/default) | −1.0 |

**Quant rationale for Critical tier:** ETH, as a risk asset, trades with a high beta to macro risk sentiment. When the Federal Reserve surprises markets (rate decision, FOMC minutes, Jackson Hole), or when CPI prints miss expectations, ETH can move 10–20% within hours. A 5× leveraged position held through a major adverse macro event is near-certain liquidation if the direction is wrong. The Critical tier ensures that a confirmed macro risk-off environment (§14 = −2.0 weighted) requires significant offsetting signals before a long is recommended.

**Limitation — classification quality:** Headline classification uses keyword scoring (BULLISH/BEARISH/NEUTRAL tags assigned during news parsing). This is not semantic — "Wall Street Surges" = BULLISH, "Fed holds rates steady" = depends on surrounding context keywords. The classification is a reasonable approximation but cannot capture nuance. Trader should cross-check the actual headlines shown in the scorecard value string.

---

### §15 — Crypto News Sentiment
**Tier:** STANDARD (×1.0) | Raw: −1.0 to +1.0 | **Max weighted: ±1.00**
**Data source:** SoSoValue API `/news?category=1` (PANews, Cointelegraph, Odaily, Benzinga, ForesightNews, ChainCatcher) → keyword classification
**What it captures:** Major ETH/crypto-specific events: exploits, protocol upgrades, regulatory approvals, ETF news
**Scoring logic:**

| Condition | Raw Score |
|---|---|
| Exploit/hack/breach/stolen detected in headlines | −1.0 |
| Bull headlines outnumber bear | +1.0 |
| Bear headlines outnumber bull | −0.5 |
| Neutral/mixed | 0 |

**Note on asymmetry:** A detected exploit scores −1.0 (maximum bearish) regardless of headline count because security events create immediate, certain negative price impact. Bullish news (ETF approvals, institutional partnerships) scores a maximum of +1.0. Standard tier reflects that crypto news is impactful but less universal than macro events or BTC direction.

---

### §16 — CEX Exchange Flows (On-Chain Accumulation)
**Tier:** HIGH (×1.5) | Raw: −1.0 to +1.0 | **Max weighted: ±1.50**
**Data source:** DefiLlama `/cexs` API — 24h and 7-day net inflows across Binance, OKX, HTX, Bybit, Kraken, Bitfinex, KuCoin
**What it captures:** Net USD equivalent flowing into or out of major centralized exchanges
**Scoring logic:**

| Condition | Raw Score |
|---|---|
| Net outflow > $100M | +1.0 | ETH/crypto leaving CEX = accumulation (bullish) |
| Any net outflow | +0.5 | |
| Approximately neutral | 0 | |
| Any net inflow | −0.5 | ETH/crypto entering CEX = preparing to sell (bearish) |
| Net inflow > $100M | −1.0 | |

**Quant note — data aggregation limitation:** DefiLlama reports aggregate net flows across all cryptocurrencies, not ETH-specific flows. A large BTC outflow with concurrent ETH inflow could net to zero or outflow, masking the ETH-specific signal. This is a known limitation. The metric remains High tier because large multi-asset CEX flow trends tend to correlate — when institutions are accumulating broadly, most major assets see outflows together.

---

### §17 — Historical Technicals: Bollinger Bands + MACD
**Tier:** STANDARD (×1.0) | Raw: −1.0 to +1.0 | **Max weighted: ±1.00**
**Data source:** Crypto.com 1D candles → pure-Python Bollinger Bands (20-period, 2σ) and MACD (12/26/9 EMA)
**What it captures:** Price position relative to statistical price range (BB) and momentum direction change (MACD cross)
**Scoring logic:**

| Signal | Condition | Component Score |
|---|---|---|
| Bollinger | Price above upper band | −0.5 (statistically extended) |
| Bollinger | Price inside bands | 0 |
| Bollinger | Price below lower band | +0.5 (oversold extension) |
| MACD | MACD line > Signal line | +0.5 (bullish cross / continuation) |
| MACD | MACD line < Signal line | −0.5 (bearish cross / continuation) |

Combined score capped at ±1.0.

**Quant note:** BB and MACD are both derived from price history. They provide confirmation but not independent information — they will generally agree with RSI (§6) and the EMA stack (§9) rather than contradict them. Standard tier is appropriate. BB is particularly useful as a volatility signal: when price is outside the bands, volatility is elevated and leverage should be reduced regardless of direction.

---

### §18 — BTC Influence (Dominance + 24h Price Direction)
**Tier:** CRITICAL (×2.0) | Raw: −1.0 to +1.0 | **Max weighted: ±2.00**
**Data sources:** CoinMarketCap global metrics (BTC dominance %), CoinGecko BTC market data (24h change %), 30-day correlation and beta calculated from CoinGecko 30D price history
**What it captures:** BTC's structural and directional influence on ETH — dominance headwind/tailwind + recent price direction
**Scoring logic:**

| Signal | Condition | Component Score |
|---|---|---|
| BTC Dominance | > 58% | −1.0 (ETH historically underperforms in high-dominance regimes) |
| BTC Dominance | 55–58% | −0.5 (moderate headwind) |
| BTC Dominance | 50–55% | 0 (neutral) |
| BTC Dominance | < 50% | +0.25 (altcoin season tailwind) |
| BTC 24h Change | > +5% AND dominance < 55% | +0.5 (BTC strongly rising, low dom — ETH tailwind) |
| BTC 24h Change | < −3% | −0.5 (BTC falling, ETH beta amplifies) |

Combined score capped at ±1.0.

**Why elevated to Critical:** ETH has a 30-day rolling correlation of 0.85–0.92 with BTC in most market regimes. BTC direction is the primary driver of ETH price on a 4-hour timeframe. Previous implementation scored §18 as either 0 or −1 only (BTC dominance binary) — it could never contribute a bullish signal. This was structurally wrong: when BTC is rallying and dominance is falling (altcoin season conditions), ETH historically outperforms. The revised bidirectional scoring correctly reflects this.

**Why dominance + direction (not just one):** BTC dominance rising while BTC is flat is very different from dominance falling while BTC is rallying. The composite captures both: a BTC rally in a low-dominance regime is the strongest ETH tailwind; high dominance regardless of BTC direction is an ETH headwind.

**Why 5% threshold for BTC 24h change (not 3%):** At 3%, normal intraday BTC volatility would fire the bullish signal too frequently, reducing signal-to-noise. A +5% single-day BTC move is a statistically significant event (~top 8% of trading days) and more reliably corresponds to a regime shift rather than noise.

---

### §19 — ETH/BTC Cross Ratio (Relative Performance)
**Tier:** STANDARD (×1.0) | Raw: −1.0 to +1.0 | **Max weighted: ±1.00**
**Data sources:** CoinGecko ETH and BTC price, 24h change % (always available); CoinMarketCap 7-day and 30-day % changes (when CMC key configured)
**What it captures:** Whether ETH is outperforming or underperforming BTC on a 24h and 7-day basis — the ETH/BTC "alpha"
**Scoring logic:**

| Signal | Condition | Component Score |
|---|---|---|
| 24h alpha (ETH 24h − BTC 24h) | > +2% | +0.5 (ETH outperforming short-term) |
| 24h alpha | −2% to +2% | 0 (tracking together) |
| 24h alpha | < −2% | −0.5 (ETH underperforming) |
| 7d alpha (ETH 7d − BTC 7d) | > +5% | +0.5 (ETH outperforming medium-term) |
| 7d alpha | −5% to +5% | 0 |
| 7d alpha | < −5% | −0.5 (ETH underperforming medium-term) |

Combined score capped at ±1.0.

**Quant note:** ETH/BTC cross ratio is the purest measure of whether ETH is in a phase of relative strength or relative weakness against its primary driver. When ETH is outperforming BTC on both 24h and 7d (score = +1.0), it indicates ETH-specific demand beyond BTC correlation — the strongest bullish signal for an ETH/USDT long trade. When ETH is underperforming on both timeframes (score = −1.0), taking an ETH long against a rising BTC is fighting the relative trend.

**Complement to §18:** §18 measures BTC's absolute direction and structural influence. §19 measures ETH's performance *relative* to BTC. They are independent signals: BTC can be rising (§18 = +0.5) while ETH underperforms (§19 = −0.5), which nets to a cautious signal — BTC tailwind exists but ETH is not capturing it.

---

### §20 — Options IV / Put-Call Skew
**Tier:** STANDARD (×1.0) | Raw: always 0 until data available | **Max weighted: N/A (placeholder)**
**Data source:** None currently — requires Deribit API or paid options data feed
**What it captures:** (Planned) Implied volatility and put/call skew from ETH options markets
**Scoring logic:** Returns N/A until a data source is configured. Score always 0.

**Why this matters:** Options IV is a leading indicator of expected price movement. IV skew (put IV > call IV = market paying more to hedge downside) is often predictive 4–8 hours ahead of directional moves. When combined with funding rate (§13), IV divergence from futures positioning is one of the strongest available signals.

**Upgrade path:** Connect to `https://www.deribit.com/api/v2/public/get_order_book` (ETH options, public) or Derive.xyz data for real-time IV surface. When data is available, elevate to HIGH tier (×1.5).

---

### §21 — Volatility Regime / Crypto VIX
**Tier:** STANDARD (×1.0) | Raw: always 0 until data available | **Max weighted: N/A (placeholder)**
**Data source:** None currently — requires DVOL index from Deribit or BitVol data
**What it captures:** (Planned) Whether the current market environment is low-vol (trend-following signals reliable) or high-vol (all signals noisier, reduce leverage)
**Scoring logic:** Returns N/A until a data source is configured. Score always 0.

**Why this matters:** In high-volatility regimes (crypto VIX > 80), all signals have higher variance — a 5× leveraged position sized for normal conditions should be halved. In low-volatility regimes (crypto VIX < 40), trend signals are more persistent and momentum trades have higher Sharpe ratios. This section will provide regime context rather than a directional signal when implemented.

**Upgrade path:** DVOL (Deribit Volatility Index) is available via `https://www.deribit.com/api/v2/public/get_index` — free, public. Score ranges: DVOL < 40 (low-vol, trend-friendly → +0.25), 40–80 (normal), > 80 (high-vol, reduce size → −0.25).

---

## 6. Hard Rule Flags (Override Layer)

Beyond the weighted score, six hard rules are evaluated post-scoring and surface as ⚠️ flags in the output. These can contradict the recommended direction:

| Flag | Trigger | Action |
|---|---|---|
| Rule 1 | ETH within 2% of key support AND net score is bearish | Warn against short entry |
| Rule 2 | ETH within 2% of key resistance AND net score is bullish | Warn against long entry |
| Rule 5 | F&G < 20 AND RSI < 30 simultaneously | CAPITULATION ZONE — weight contrarian long regardless of score |
| Rule 6 | F&G > 80 AND RSI > 70 simultaneously | EUPHORIA ZONE — weight contrarian short regardless of score |
| Rule 8 | Funding rate < −0.05% | SQUEEZE RISK — crowded shorts, flag squeeze potential |
| Rule 4 | (Future) Entry in Asia session 23:00–08:00 CST | THIN LIQUIDITY warning |

---

## 7. Known Limitations and Data Gaps

| Limitation | Impact | Mitigation |
|---|---|---|
| ETF flows are 20–32 hours lagged | §8 signal is directional, not same-day | Use weekly/monthly trend alongside daily |
| CEX flows are aggregate (all assets) | §16 may not reflect ETH-specific accumulation | Cross-check with staking flows §11 |
| Macro/crypto news classification is keyword-based | §14/§15 can misclassify nuanced headlines | Display raw headline titles in scorecard value |
| F&G indexes are lagging aggregates | §3/§4 will not detect rapid sentiment shifts | Hard rules 5/6 catch extreme readings independently |
| Social/CT (§12) uses general CT pool | Missing targeted high-signal accounts | Weight is Low; upgrade path if account-specific feeds become available |
| S/R levels computed on daily candles | May miss intraday key levels | Manual verification on 4h chart recommended |
| §14 and §18 are correlated | Risk-on macro often coincides with BTC rising — potential double-counting of +4.0 | Accepted tradeoff: when both confirm, conviction should be higher |
| No volatility regime signal | High-IV environments make all signals noisier | Manual: reduce position size when VIX > 25 or crypto IV > 80% |
| No options market data | Put/call ratio and IV skew are strong leading indicators | Not available on free-tier APIs; future enhancement |

---

## 8. Signal Correlation Map

Understanding which sections tend to move together prevents over-interpreting aligned signals that share a common cause:

| Group | Sections | Common Driver |
|---|---|---|
| Macro risk-on cluster | §14 (Macro news), §18 (BTC direction), §8 (ETF flows) | Same macro event can fire all three simultaneously |
| Technical confirmation cluster | §5 (MA cross), §9 (Price vs EMA), §17 (BB+MACD) | All derived from price history — directional agreement expected |
| Sentiment cluster | §3 (Crypto F&G), §4 (ETH F&G), §6 (RSI) | All reflect price momentum — tend to move together |
| On-chain accumulation cluster | §11 (Staking), §16 (Exchange flows) | Both reflect smart-money behavior, may confirm each other |

**Rule of thumb:** If all four sections in the macro risk-on cluster are firing simultaneously (§14 + §18 + §8 = +6.0 weighted combined), verify that they reflect genuinely independent signals rather than one event reported three ways.

---

## 9. Interpreting the Output

### Direction and Confidence

```
Direction: LONG (net +7.5, confidence 66%)
```

- **Net score > 0 → LONG.** Net score < 0 → SHORT.
- **Confidence 66%** means the weighted signals are at 37% of their maximum possible alignment. This is a moderate conviction signal — not a coin flip, not a slam dunk.
- **Confidence > 75%** is rare and requires strong alignment across Critical AND High tiers.
- **Confidence < 55%** indicates a contested signal — Option C (WAIT) should be ranked first.

### Reading the Scorecard

Each section displays: `[score] LABEL  value string`

The value string contains the actual data used for scoring — prices, rates, percentages. Always read the value, not just the label. A §8 labeled BULL with "Daily net +52M USD" is a weaker signal than one showing "+$180M" — both score +0.5 but the magnitude matters.

### Options A / B / C

- **Option A:** Primary direction. Entry zone anchored to the nearest support (for LONG) or resistance (for SHORT) identified by the swing algorithm.
- **Option B:** Contrarian. Low confidence. Only valid on a specific price trigger stated in `entry_condition`.
- **Option C:** Wait. Always valid when confidence < 55% or when a flag contradicts the direction.

**Ranked:** A/B/C are sorted by confidence. If Option C ranks first, the system is explicitly recommending no trade until a trigger fires.

---

## 10. Version History

| Version | Date | Changes |
|---|---|---|
| 1.0 | Jun 2026 | Initial build — equal weight, Anthropic LLM scoring |
| 2.0 | Jun 2026 | Deterministic rule-based scoring; four-tier weight system; §9 Gas replaced by Price vs EMA Stack; §18 BTC elevated to Critical and made bidirectional; §3/§4 F&G moved to Low tier; §2 enhanced with EMA structure; §7 elevated to High |
| 2.1 | Jun 2026 | §3/§4 F&G gradient scoring (20-45=+0.25, 55-75=−0.25 mild tiers); §13 L/S ratio made context-dependent (L/S>1.5 scores +0.5 only when RSI<50); §18 BTC bullish trigger updated from +3% to +5% (reduce noise); §19 ETH/BTC Cross Ratio added (STANDARD ×1.0, 24h+7d alpha); §20 Options IV and §21 Volatility Regime added as PLACEHOLDER sections; confidence denominator updated from 19.0 to 20.0; _source tag updated to deterministic-rules-v2 |

---

*Document maintained in `/dashboard/docs/SCORING_SPEC.md`. Update whenever scoring thresholds, tier assignments, or data sources change.*
