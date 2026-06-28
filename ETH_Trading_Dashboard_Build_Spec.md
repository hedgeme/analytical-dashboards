# ETH/USDT Pre-Trade Dashboard — Project Build Specification
**Version:** 1.1 | **Updated:** June 28, 2026 | **Platform:** HTX Futures | **Author:** Esteban

---

## 📋 Project Overview

This is a **pre-trade assessment dashboard** built as an interactive React artifact in Claude.ai. It is initiated by the trader immediately before placing a 5× leveraged ETH/USDT futures position on HTX. The dashboard auto-fetches live data across 18 metric categories, scores each signal, and outputs a structured trade recommendation with entry, stop, and target levels.

### Trading Parameters (Standard)
| Parameter | Value |
|-----------|-------|
| Exchange | HTX Futures |
| Instrument | ETH/USDT Perpetual |
| Leverage | 5× (Long or Short) |
| Typical hold | 8–12 hours |
| Stop loss | 20% |
| Take profit target | 40% |
| Manual early exit | 5–10% gain if momentum stalls |
| Entry discipline | Cancel unfilled limit orders if setup invalidates — no chasing |

---

## 🏗️ Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| UI Framework | React (JSX) | Rendered as Claude artifact |
| Styling | Tailwind CSS (base classes only) | No compiler — pre-defined base stylesheet |
| Charts | **TradingView Lightweight Charts™ v4.2** | Apache 2.0 open source — loaded via CDN, fed by our own OHLCV data |
| State | React useState / useReducer | No localStorage (not supported in artifacts) |
| API calls | fetch() in browser | All APIs called client-side |
| AI Analysis | Anthropic Claude API (claude-sonnet-4-6) | Via `/v1/messages` endpoint — key injected at runtime |

---

## 📈 TradingView — Critical Clarification (Updated v1.1)

TradingView offers three distinct products. Only one is appropriate for this dashboard.

### The three TradingView products

| Product | License | Personal use? | Requires approval? | What it gives you |
|---|---|---|---|---|
| **Advanced Charts (Charting Library)** | Free for companies on public web projects only | ❌ No — explicitly excluded | ✅ Yes — GitHub access required, days to provision | Full charting library, custom datafeed, 100+ indicators |
| **Trading Platform** | Commercial enterprise license | ❌ No | ✅ Yes — paid negotiated license | Full broker integration, order management, multi-chart |
| **Lightweight Charts™** | Apache 2.0 — fully open source | ✅ Yes | ❌ None — CDN, instant | Candlestick, line, area, bar charts — interactive, performant |

### Why the API docs linked (charting-library-docs) are NOT for this project

The documentation at `tradingview.com/charting-library-docs/latest/api/` covers the **Advanced Charts (Charting Library)** product — a restricted library unavailable for personal or private dashboard use. It requires:
- Company entity applying for a license
- GitHub SSH access to a private TradingView repository
- Self-hosted server with your own market data feed
- None of which apply to a Claude artifact

### What we use instead: TradingView Lightweight Charts™

Lightweight Charts is TradingView's open-source library, Apache 2.0 licensed, with zero restrictions for personal projects.

**CDN import (no installation, no approval, no key):**
```javascript
// Load in React artifact via script tag
https://cdnjs.cloudflare.com/ajax/libs/lightweight-charts/4.2.0/lightweight-charts.standalone.production.js
```

**Why this is actually better than the Charting Library for our use case:**

| Capability | TradingView widget embed (old plan) | Lightweight Charts™ (current plan) |
|---|---|---|
| Data source | TradingView's servers | Our own APIs (Crypto.com + CoinGecko) |
| RSI / MACD / EMAs | Pre-calculated by TradingView | Calculated from our live OHLCV, overlaid as series |
| Candlestick timeframe | Fixed by widget | We control — 4H, 1D, 1W switchable |
| Live data | TradingView feed | Crypto.com MCP + CoinGecko API |
| API key | None | None |
| Works in Claude artifact | ✅ | ✅ |
| Approval required | ❌ | ❌ |
| Data we control | ❌ No | ✅ Yes — our own OHLCV feeds the chart |

### Lightweight Charts implementation pattern

```javascript
import { createChart } from 'lightweight-charts';

// Create chart with OHLCV from Crypto.com MCP / CoinGecko
const chart = createChart(document.getElementById('chart'), {
  width: 680,
  height: 300,
  layout: { background: { color: 'transparent' }, textColor: '#888' },
  grid: { vertLines: { color: '#2c2c2a' }, horzLines: { color: '#2c2c2a' } },
  timeScale: { timeVisible: true, secondsVisible: false },
});

const candleSeries = chart.addCandlestickSeries({
  upColor: '#639922', downColor: '#A32D2D',
  borderUpColor: '#639922', borderDownColor: '#A32D2D',
  wickUpColor: '#639922', wickDownColor: '#A32D2D',
});

// Feed with live OHLCV data from Crypto.com MCP
candleSeries.setData(ohlcvData); // [{time, open, high, low, close}]

// Overlay EMA-20, EMA-50, EMA-200 as line series
const ema20 = chart.addLineSeries({ color: '#FAC775', lineWidth: 1 });
const ema50 = chart.addLineSeries({ color: '#3987e5', lineWidth: 1 });
const ema200 = chart.addLineSeries({ color: '#E24B4A', lineWidth: 1, lineStyle: 2 });
```

---

## 🔑 API Keys Required

Collect all of these before starting the build session:

| API | Key location | Cost | Used for |
|-----|-------------|------|---------|
| **CoinGecko** | coingecko.com/en/developers/dashboard | Free tier | Price, market cap, dominance, volume, OHLCV history |
| **CryptoQuant** | cryptoquant.com → API settings | Free (beta MCP) | On-chain, derivatives, staking, exchange flows, 245+ metrics |
| **SoSoValue** | sosovalue.com/developer | Free demo tier | ETH + BTC spot ETF daily net flows |
| **Etherscan** | etherscan.io/apis | Free (5 calls/sec) | Gas tracker — live gwei oracle |
| **Anthropic Claude API** | console.anthropic.com | Pay per token | AI signal interpretation and scoring |

**Connected MCP Servers (already active in Claude.ai — no key entry required):**
- Crypto.com MCP — live price, OHLCV candlesticks, mark price, bid/ask, funding rate
- CryptoQuant MCP — 245+ on-chain metrics (beta, confirm tool call approvals)

**Free public APIs — no key, no signup, called directly in the app:**

| API | Endpoint | Covers |
|-----|---------|--------|
| Alternative.me F&G | `https://api.alternative.me/fng/` | §3 Crypto Fear & Greed |
| Ethereum Fear | `https://ethereumfear.com/` | §4 ETH-specific F&G (confirmed fetchable) |
| Reddit JSON | `https://www.reddit.com/r/ethereum/hot.json` | §12 Reddit sentiment |
| Reddit JSON | `https://www.reddit.com/r/CryptoCurrency/hot.json` | §12 Reddit sentiment |
| DefiLlama | `https://api.llama.fi/` | §10 supply, §11 staking/LST data |

> ⚠️ **Security note:** Never commit actual API keys to GitHub. Use `.env.example` with blank values and load from environment variables or paste at runtime.

---

## 📊 The 18 Metric Framework

Each metric maps to a confirmed live data source. The dashboard fetches all simultaneously on load.

### §1 — ETH Live Price + Intraday Range
- **Primary source:** Crypto.com MCP `get_ticker ETH_USD` — live bid/ask/last/24h-high/24h-low
- **Secondary source:** CoinGecko API `/coins/ethereum`
- **Output:** Current price, 24h high, 24h low, % change, volume
- **Signal type:** Context (not scored independently — sets the frame)

### §2 — 1-Week Average + Weekly Range
- **Source:** CoinGecko API `/coins/ethereum/market_chart?vs_currency=usd&days=7`
- **Supplementary:** Crypto.com `get_candlestick ETH_USD 1D` (last 7 candles)
- **Output:** 7-day high, 7-day low, 7-day average price
- **Signal type:** Trend context — is current price in upper, middle, or lower third of range?

### §3 — Crypto Fear & Greed Index (Overall)
- **Source:** `https://api.alternative.me/fng/` — confirmed live, updates every 5 minutes, no key
- **Output:** Score 0–100, classification, time until next update
- **Variants available:** `?limit=7` for 7-day trend, `?limit=30` for monthly
- **Score:** <25 = contrarian long possible (+0.5); >75 = contrarian short possible (−0.5); used with other signals

### §4 — ETH-Specific Fear & Greed
- **Source:** `https://ethereumfear.com/` — confirmed accessible via fetch, returns ETH-specific index
- **Output:** ETH-only index value 0–100 and classification
- **Note:** Value is in page HTML — parse from static content (JS-rendered chart unavailable but value is accessible)
- **Signal:** Supplements §3 with ETH-specific sentiment weighting

### §5 — 50-Day MA vs 200-Day MA
- **Source:** Calculated from CoinGecko `/coins/ethereum/market_chart?days=200` daily closing prices
- **Calculation:** Rolling 50-period and 200-period SMA on daily close candles
- **Signal rules:**
  - Price below 50MA below 200MA = death cross = strong bearish (−1)
  - Price above 50MA above 200MA = golden cross = strong bullish (+1)
  - Price between MAs = mixed/transitional (−0.5 or +0.5 depending on direction)
- **Chart overlay:** EMA-20 (amber), EMA-50 (blue), EMA-200 (red dashed) — rendered on Lightweight Charts

### §6 — RSI (Relative Strength Index)
- **Source:** Calculated from daily OHLCV using standard 14-period Wilder RSI formula
- **Data:** Crypto.com `get_candlestick ETH_USD 1D` (50 candles) or CoinGecko historical
- **Thresholds:**
  - RSI < 30 = oversold → contrarian long signal (+1)
  - RSI 30–45 = weak/recovering (−0.5 to 0)
  - RSI 45–55 = neutral (0)
  - RSI 55–70 = bullish momentum (+0.5)
  - RSI > 70 = overbought → contrarian short signal (−1)
- **4-hour RSI also calculated** for intraday confirmation (shorter-term signal)
- **Chart overlay:** RSI rendered as separate panel below candlestick chart in Lightweight Charts

### §7 — Resistance Overhead / Support Below
- **Source:** Derived from OHLCV price history swing analysis + CryptoQuant liquidation wall data
- **Identifies:**
  - Prior swing highs (resistance zones)
  - EMA clusters (dynamic resistance/support)
  - Psychological round numbers ($1,500 / $1,600 / $1,700 etc.)
  - Bollinger Band upper/lower (±2σ from 20-period MA)
  - CryptoQuant liquidation heatmap concentrations
- **Output:** Top 3 resistance levels above price, top 3 support levels below price
- **Signal:** R/R ratio — distance to target vs distance to stop
- **Chart overlay:** Horizontal lines on Lightweight Charts at key levels

### §8 — ETF Flows (ETH + BTC Spot)
- **Source:** SoSoValue API (free demo key — sign up at sosovalue.com/developer)
- **Endpoints:**
  - ETH spot ETF daily net flow (individual fund breakdown available)
  - BTC spot ETF daily net flow
  - 5-day historical ETF flow trend
- **Signal rules:**
  - Net outflows > $100M over 2 days = strong bearish (−1)
  - Outflow streak > 5 days = structural bearish (−1)
  - Net inflows > $100M = bullish (+1)
  - Inflow reversal after outflow streak = early bull signal (+0.5)

### §9 — Gas Tracker
- **Source:** Etherscan API `https://api.etherscan.io/api?module=gastracker&action=gasoracle&apikey={KEY}`
- **Output:** Safe gwei, Proposed gwei, Fast gwei, Base fee
- **Signal rules:**
  - Gas < 1 gwei = ultra-low on-chain demand = bearish ETH utility narrative (−0.5)
  - Gas 1–10 gwei = low-normal demand (0)
  - Gas 10–50 gwei = active demand = bullish (+0.5)
  - Gas > 50 gwei = high activity / DeFi surge = strong bullish (+1)

### §10 — ETH Supply Change (Inflation vs Burn)
- **Primary source:** CryptoQuant MCP — supply metrics, daily issuance, burn rate
- **Secondary source:** DefiLlama free API `https://api.llama.fi/` — protocol-level supply data
- **Note:** ultrasound.money and dune.com are JS-rendered — inaccessible via fetch; CryptoQuant replaces both
- **Output:** Current circulating supply, daily issuance rate, daily burn rate, net supply change
- **Signal:** Net deflationary = bullish (+0.5); mild inflation = neutral (0); accelerating inflation = bearish (−0.5)
- **Context:** Glamsterdam upgrade (delayed to Q3 2026) expected to improve burn mechanism

### §11 — ETH Staking + Unstaking (24hr)
- **Primary source:** CryptoQuant MCP — staking flows, validator queue, unstaking
- **Secondary source:** DefiLlama free API `https://api.llama.fi/protocol/lido` + `https://api.llama.fi/lst`
- **Note:** defillama.com/lst and defillama.com/chain/ethereum are JS-rendered; use the API endpoints directly
- **Output:** Total ETH staked (M), 24hr net stake inflows, 24hr unstaking outflows, staking APR
- **Signal:** Net unstaking > 50K ETH/day = supply pressure bearish (−1); record staking queue = bullish (+1)

### §12 — Social Media Sentiment (48hr)
- **Reddit (free JSON API — no key):**
  - `https://www.reddit.com/r/ethereum/hot.json`
  - `https://www.reddit.com/r/CryptoCurrency/hot.json`
  - `https://www.reddit.com/r/ethtrader/hot.json`
  - `https://www.reddit.com/search.json?q=ethereum&sort=hot&t=day`
- **X/Twitter — via web search (no Twitter API key):**
  - @CoinDesk — breaking crypto news
  - @PeckShieldAlert — security exploits and hacks
  - @CertiKAlert — smart contract vulnerabilities
  - @cryptorover — price and sentiment commentary
  - @DefiLlama — TVL and protocol flows
- **Output:** Top 5 Reddit post titles, upvote ratio, bullish/bearish post count, security alert flag
- **Signal:** Extreme bearish posts + low engagement = contrarian bottom signal (+0.5); euphoria = short signal (−0.5)
- **Note:** X.com pages are blocked by robots.txt — web search is the reliable workaround for our specific accounts

### §13 — Derivatives Data (replaces CoinGlass)
**CoinGlass website is JS-rendered and bot-blocked. All sub-metrics sourced from CryptoQuant MCP instead.**
CryptoQuant data is the upstream source CoinGlass itself uses.

| CoinGlass metric | CryptoQuant MCP replacement | Signal direction |
|---|---|---|
| (a) Price performance 4h/24h/7d | Price feed + OHLCV | Trend context |
| (b) Long/Short ratio | `long-short-ratio` endpoint | >1.5 long-heavy = squeeze risk |
| (c) Liquidations 1h/4h/12h/24h | `liquidations` endpoint | 80%+ longs = exhaustion bounce |
| (d) Futures flows | `futures-flow` endpoint | Net positive = bullish |
| (e) Spot flows | `spot-flow` endpoint | Inflows = buying pressure |
| (f) OI-weighted funding rate | `funding-rate` endpoint | Negative = net short = squeeze risk |
| (g) Open interest trend | `open-interest` endpoint | OI up + price down = bearish continuation |

**Liquidation heatmap signals:**
- Short squeeze zone identified above current price → sets short-term target for longs
- Long liquidation wall below current price → sets stop discipline for longs

### §14 — Macro Economics News
- **Primary source:** Web search — Fed, CPI, PCE, Nasdaq, DXY, Treasury yields
- **Secondary source:** Yahoo Finance (fetch works — confirmed accessible)
- **Output:** Top 3 macro events in last 24hrs with directional tag
- **Auto-flag triggers:**
  - Fed rate decision or statement → HIGH IMPACT
  - PCE / CPI print → HIGH IMPACT (PCE 4.1% confirmed June 25, 2026 — 3-year high)
  - Nasdaq move > 1.5% either direction → MEDIUM IMPACT
  - DXY move > 0.5% → MEDIUM IMPACT
  - Geopolitical escalation (oil, conflict) → VARIABLE
- **Signal:** Risk-off macro (−1) / neutral (0) / risk-on (+1)
- **Current context:** Fed Chair Warsh hawkish; 3 rate hikes priced for 2026; PCE elevated

### §15 — Crypto News
- **Source 1:** PANews — `https://www.panewslab.com/en` (confirmed fetchable — full page + articles)
- **Source 2:** Web search for breaking crypto news, protocol updates, regulatory actions
- **Output:** Top 3 crypto-specific headlines in last 24hrs with impact tag
- **Auto-flag (HIGH priority):**
  - Exchange hacks or protocol exploits (check @PeckShieldAlert, @CertiKAlert via web search)
  - ETF approval or rejection news
  - Regulatory enforcement actions
  - Major protocol upgrade announcements
- **Note:** CoinGecko heatmap is JS-rendered — describe sector performance in text instead
- **Note:** TradingView news page is JS-rendered — PANews + web search replaces it

### §16 — Exchange Inflows / Outflows
- **Source:** CryptoQuant MCP exchange flow data (core metric — one of their strongest datasets)
- **Note:** CoinGecko exchanges page is JS-rendered and inaccessible — CryptoQuant replaces it
- **Output:** Net ETH inflow/outflow to major exchanges (Binance, OKX, Coinbase) last 24hrs
- **Signal:**
  - Large net inflows to exchanges = coins moving for potential sale = bearish (−1)
  - Large net outflows from exchanges = accumulation / cold storage = bullish (+1)
  - Neutral flow = (0)

### §17 — ETH Historical Performance
- **Source 1:** CoinGecko API `/coins/ethereum/market_chart?days=365` for 1-year price history
- **Source 2:** Crypto.com `get_candlestick ETH_USD 1D` for recent OHLCV
- **Note:** TradingView seasonals and technicals pages are JS-rendered — cannot be fetched. Data is derived from our own OHLCV.
- **Output:**
  - Same day-of-week historical average return (e.g., "Saturdays historically +0.3%")
  - Same calendar month average performance
  - Bollinger Band position (upper/mid/lower)
  - MACD signal line position
- **Chart:** TradingView Lightweight Charts™ renders the live candlestick with EMA-20/50/200 overlaid from our calculated values

### §18 — BTC Price + ETH Correlation
- **Primary source:** Crypto.com MCP `get_ticker BTC_USD` — live BTC price, 24h range
- **Secondary source:** CoinGecko API `/coins/bitcoin` — market data, dominance
- **Note:** TradingView BTC pages (news, technicals, ETFs) are all JS-rendered — web search + CoinGecko replace them
- **Output:**
  - BTC live price + intraday range
  - BTC 24h % change
  - BTC dominance % (from CoinGecko global data)
  - 30-day rolling ETH/BTC correlation coefficient (calculated from historical OHLCV)
  - ETH beta to BTC (amplification factor)
- **Key signal rules:**
  - BTC dominance > 58% = alt capital draining = bearish ETH (−1)
  - ETH underperforming a BTC bounce = relative weakness = additional bearish flag
  - BTC breaking key support → ETH cascades harder (high beta)
  - BTC reclaiming key resistance → ETH squeezes faster
  - **BTC is the trigger instrument — watch BTC for entry timing, not ETH**

---

## 🎨 Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  ETH/USDT PRE-TRADE DASHBOARD     [Date] [Time CST]     [REFRESH] │
├──────────────┬──────────────┬──────────────┬──────────────────────┤
│  ETH PRICE   │  BTC PRICE   │  CRYPTO F&G  │  ETH F&G            │
│  $X,XXX      │  $XX,XXX     │  XX / Label  │  XX / Label         │
│  ▲/▼ X.X%   │  ▲/▼ X.X%   │  (Overall)   │  (ETH-specific)     │
├──────────────┴──────────────┴──────────────┴──────────────────────┤
│  CANDLESTICK CHART — TradingView Lightweight Charts™               │
│  Live OHLCV from Crypto.com MCP / CoinGecko API                   │
│  EMA-20 (amber) · EMA-50 (blue) · EMA-200 (red dashed)            │
│  Key resistance/support lines overlaid as horizontal markers       │
│  [4H] [1D] [1W] timeframe toggle                                   │
│  RSI panel below (14-period, line chart)                           │
├─────────────────────────────┬───────────────────────────────────────┤
│  TECHNICALS (§5 §6 §7)      │  SENTIMENT & FLOWS (§3 §4 §8 §12)   │
│  EMA20: $X,XXX [↑/↓]       │  F&G: XX → Extreme Fear/Greed       │
│  EMA50: $X,XXX [↑/↓]       │  ETH F&G: XX                        │
│  EMA200:$X,XXX [↑/↓]       │  ETH ETF flows: +/-$XXM (2d)        │
│  RSI (daily): XX.X          │  BTC ETF flows: +/-$XXM (2d)        │
│  RSI (4hr):  XX.X           │  Reddit: XX posts, X% bullish       │
│  MACD: Positive/Negative    │  Alerts: [latest PeckShield/Certik] │
│  Bollinger: [Band position] │                                       │
│  Support: $X,XXX / $X,XXX  │                                       │
│  Resistance: $X,XXX / $X,X │                                       │
├─────────────────────────────┼───────────────────────────────────────┤
│  ON-CHAIN (§9 §10 §11 §16)  │  DERIVATIVES §13 (via CryptoQuant)  │
│  Gas: X.X gwei [Safe/Fast]  │  Long/Short: X.XX                   │
│  Supply Δ: +/-X ETH/day    │  Funding rate: +/-X.XXX%            │
│  Total staked: XXM ETH      │  Open Interest: $XXB [↑↓]           │
│  Stake 24h: +/-X,XXX ETH   │  Liq 24h: $XXXM (XX% longs/shorts) │
│  Exchange inflow: +/-XXXK  │  Squeeze zone: $X,XXX               │
├─────────────────────────────┴───────────────────────────────────────┤
│  MACRO & NEWS (§14 §15)                                             │
│  [Headline 1] [BEARISH / BULLISH / NEUTRAL]                        │
│  [Headline 2] [BEARISH / BULLISH / NEUTRAL]                        │
│  [Headline 3] [BEARISH / BULLISH / NEUTRAL]                        │
├─────────────────────────────────────────────────────────────────────┤
│  BTC CORRELATION (§18)                                              │
│  BTC: $XX,XXX [▲/▼ X.X%] · Dom: XX.X% · ETH/BTC corr: X.XX     │
│  ETH beta: X.XX · [ETH following / diverging from BTC]            │
├─────────────────────────────────────────────────────────────────────┤
│  SIGNAL SCORECARD (18 tiles, color-coded BEAR/BULL/NEUT)          │
│  §1 §2 §3 §4 §5 §6 §7 §8 §9 §10 §11 §12 §13 §14 §15 §16 §17 §18│
│                                                                     │
│  ████████████████████░░░░░░░░░░  BEAR vs BULL aggregate bar       │
│  X.X bearish    X.X neutral    X.X bullish                        │
├─────────────────────────────────────────────────────────────────────┤
│  ╔═════════════════════════════════════════════════════════════╗   │
│  ║  RECOMMENDATION:  SHORT / LONG / WAIT                      ║   │
│  ║  Confidence: XX%  ·  Contrarian risk: XX%                  ║   │
│  ║                                                             ║   │
│  ║  Entry:     $X,XXX – $X,XXX                                ║   │
│  ║  Target 1:  $X,XXX (primary)                               ║   │
│  ║  Target 2:  $X,XXX (if momentum continues)                 ║   │
│  ║  Stop loss: $X,XXX (20% from entry ≈ $X,XXX)              ║   │
│  ║  Exit early:$X,XXX (take 5–10% if momentum stalls)        ║   │
│  ║  Hold window: [ENTRY TIME] → [EXIT TIME CST]               ║   │
│  ║  Watch: [BTC level / RSI trigger / news event]             ║   │
│  ║  Kill switch: [Primary thesis-invalidation trigger]        ║   │
│  ╚═════════════════════════════════════════════════════════════╝   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## ⚡ How the Dashboard Is Initiated

The dashboard is a **React JSX artifact in Claude.ai**. Here is the exact workflow:

### Step 1 — Open a new Claude.ai chat
Paste the system prompt (see §Build Instructions below) at the very start of the chat.

### Step 2 — Provide current session context
Before the dashboard renders, you provide:
```
=== TRADE SESSION ===
Date: [MM/DD/YY]
Time: [HH:MM CST]
ETH price (my screen): $[PRICE]
BTC price (my screen): $[PRICE]
Planned hold: [8–12 hrs / 6–8 hrs / specify]
Any known catalysts today: [Fed speakers / earnings / macro events / none]
=====================
```
> Your screen price is the authoritative live price — it overrides any API fetch discrepancy.

### Step 3 — Dashboard auto-fetches all 18 data sources simultaneously
On render, the app calls in parallel:
- Crypto.com MCP — ETH + BTC live tickers and OHLCV
- CoinGecko API — market data, historical OHLCV, dominance
- Alternative.me API — Fear & Greed Index (live, no key)
- ethereumfear.com — ETH-specific F&G (fetch, no key)
- Etherscan API — Gas oracle
- SoSoValue API — ETH + BTC ETF flows
- DefiLlama free API — Staking, LST, supply data
- Reddit JSON API — r/ethereum, r/CryptoCurrency hot posts
- CryptoQuant API — Derivatives, exchange flows, on-chain metrics
- Anthropic Claude API — News fetch + signal scoring

### Step 4 — Lightweight Charts™ renders with live data
The candlestick chart is populated with OHLCV data from Crypto.com / CoinGecko. EMA-20/50/200 are calculated and overlaid. RSI renders as a separate panel below.

### Step 5 — Claude API scores and recommends
All fetched data is passed to `claude-sonnet-4-6` which:
- Scores each of the 18 metrics (−1 to +1)
- Weights signals by category importance
- Generates recommendation with specific price levels and hold window

### Step 6 — Review and trade
The scorecard and recommendation render. You review, decide, and trade. Click REFRESH at any time for updated data.

---

## 📤 Required Output Format

Every assessment must produce this exact structure. **Nothing may be removed. Additional metrics may be added.**

```
SIGNAL SCORECARD
────────────────
§1  ETH Price:        $X,XXX | Range: $X,XXX–$X,XXX             [CONTEXT]
§2  Weekly Range:     High $X,XXX / Low $X,XXX / Avg $X,XXX      [CONTEXT]
§3  Crypto F&G:       XX — Extreme Fear/Fear/Neutral/Greed        [BEAR/BULL/NEUT]
§4  ETH F&G:          XX — [Classification]                       [BEAR/BULL/NEUT]
§5  50/200 MA:        50MA $X,XXX [Above/Below] 200MA $X,XXX     [BEAR/BULL]
§6  RSI:              XX.X daily / XX.X 4hr — [Classification]   [BEAR/BULL/NEUT]
§7  R/S Levels:       R1 $X,XXX · R2 $X,XXX / S1 $X,XXX · S2   [BEAR/BULL/NEUT]
§8  ETF Flows:        ETH $X.XM / BTC $X.XM (2-day net)          [BEAR/BULL/NEUT]
§9  Gas:              X.X gwei Safe / X.X Fast — [Demand level]  [BEAR/BULL/NEUT]
§10 Supply/Burn:      Net ±X,XXX ETH/day [Inflation/Deflation]   [BEAR/BULL/NEUT]
§11 Staking:          XXXM staked / ±X,XXX net 24hr              [BEAR/BULL/NEUT]
§12 Social:           Reddit XX% bull / X security alerts (48hr)  [BEAR/BULL/NEUT]
§13 Derivatives:      L/S X.XX / Fund X.XXX% / OI $XXB           [BEAR/BULL/NEUT]
§14 Macro:            [Top headline] — [Risk-off/Risk-on]         [BEAR/BULL/NEUT]
§15 Crypto News:      [Top headline] — [Impact]                   [BEAR/BULL/NEUT]
§16 Exchange Flows:   ±XX,XXX ETH net inflow 24hr                 [BEAR/BULL/NEUT]
§17 Historical:       [Day avg return] / Bollinger [pos] / MACD  [BEAR/BULL/NEUT]
§18 BTC Correlation:  BTC $XX,XXX / Dom XX% / Corr X.XX / β X.X [BEAR/BULL/NEUT]

AGGREGATE SCORE
───────────────
Bearish signals:  X.X / 18
Neutral signals:  X.X / 18
Bullish signals:  X.X / 18
[Visual bar: ████████████████░░░░░░]

RECOMMENDATION
──────────────
Direction:        SHORT / LONG / WAIT
Confidence:       XX%
Contrarian risk:  XX%

Entry zone:       $X,XXX – $X,XXX
Primary target:   $X,XXX (X% spot move = X% at 5×)
Secondary target: $X,XXX (if momentum continues)
Stop loss:        $X,XXX (20% from entry)
Manual exit:      $X,XXX – $X,XXX (5–10% if momentum stalls)
Hold window:      [ENTRY TIME CST] → [EXIT TIME CST]
BTC trigger:      [Specific BTC level that confirms or kills the thesis]
Key risk:         [Primary thesis-invalidation scenario]
```

---

## 🔧 Build Instructions for New Chat

### System prompt — paste this at the start of the build session:

---

> **You are building a pre-trade ETH/USDT futures dashboard for a 5× leveraged trader on HTX.**
>
> Build a single React JSX artifact (all CSS inline or Tailwind base classes, no separate files) that:
>
> 1. On load, simultaneously fetches live data from all APIs listed in this spec
> 2. Renders a live candlestick chart using **TradingView Lightweight Charts™ v4.2** loaded from CDN: `https://cdnjs.cloudflare.com/ajax/libs/lightweight-charts/4.2.0/lightweight-charts.standalone.production.js`
> 3. Calculates EMA-20, EMA-50, EMA-200, 14-period RSI from OHLCV data and overlays them on the chart
> 4. Calls the Anthropic Claude API (`claude-sonnet-4-6`) to score each of 18 metrics and generate a trade recommendation
> 5. Renders the full dashboard layout: live metrics → scorecard tiles → bear/bull bar → recommendation box
> 6. Includes a REFRESH button to re-fetch all data and recalculate
>
> **Do NOT use:**
> - TradingView Advanced Charts library (requires company license + GitHub access — not available)
> - TradingView Trading Platform (commercial license — not available)
> - TradingView widget embed (no data control — replaced by Lightweight Charts™)
> - localStorage or sessionStorage (not supported in Claude artifacts)
>
> **Chart implementation (Lightweight Charts™):**
> ```javascript
> // Load from CDN, then:
> const chart = LightweightCharts.createChart(container, { width: 680, height: 280 });
> const candleSeries = chart.addCandlestickSeries({ upColor: '#639922', downColor: '#A32D2D' });
> candleSeries.setData(ohlcvData); // [{time, open, high, low, close}] from Crypto.com / CoinGecko
> // Add EMA overlays as line series, RSI as separate chart panel
> ```
>
> **API Keys (inject as constants at top of file — user provides values):**
> ```javascript
> const COINGECKO_API_KEY = "USER_PROVIDES";
> const SOSOVALUE_API_KEY = "USER_PROVIDES";
> const ETHERSCAN_API_KEY = "USER_PROVIDES";
> const CRYPTOQUANT_API_KEY = "USER_PROVIDES";
> const ANTHROPIC_API_KEY = "USER_PROVIDES";
> // No key needed: Alternative.me, ethereumfear.com, Reddit JSON, DefiLlama
> ```
>
> **Data sources by section:**
> - §1,2,18: Crypto.com MCP `get_ticker ETH_USD / BTC_USD` + `get_candlestick ETH_USD 1D`
> - §1,2,5,6,17,18: CoinGecko API `https://api.coingecko.com/api/v3/`
> - §3: `https://api.alternative.me/fng/` (no key)
> - §4: `https://ethereumfear.com/` (fetch static HTML — parse index value)
> - §8: SoSoValue API (ETH + BTC spot ETF daily net flow endpoints)
> - §9: Etherscan `https://api.etherscan.io/api?module=gastracker&action=gasoracle`
> - §10,11: DefiLlama `https://api.llama.fi/protocol/lido` + `/lst` (no key)
> - §12: Reddit `https://www.reddit.com/r/ethereum/hot.json` + `/r/CryptoCurrency/hot.json`
> - §13: CryptoQuant API (long-short-ratio, liquidations, funding-rate, open-interest, futures-flow, spot-flow)
> - §14,15: Anthropic Claude API with web_search tool for macro + crypto news
> - §16: CryptoQuant API exchange-flow endpoint
> - §7: Derived from OHLCV swing high/low identification + EMA cluster analysis
>
> **Scoring logic (pass to Claude API as system context):**
> Each metric scored: −1 (bearish), −0.5 (mildly bearish), 0 (neutral), +0.5 (mildly bullish), +1 (bullish).
> Net score < 0 = SHORT, > 0 = LONG, near 0 = WAIT.
> Confidence % = (|net score| / 18) × 100.
>
> **Trader parameters baked into scoring:**
> - 5× leverage · 8–12hr hold · 20% stop · 40% TP · manual exit 5–10%
> - Never short at key support · Never long at key resistance
> - BTC is the primary trigger instrument — flag BTC level in recommendation
> - Flag Asia session entry (23:00–08:00 CST) as thin liquidity warning
> - Flag F&G < 20 + RSI < 30 as capitulation zone → weight long contrarian
> - Flag F&G > 80 + RSI > 70 as euphoria zone → weight short contrarian
>
> **Build the complete artifact in one response. Ask for API keys before starting.**

---

## 📁 Recommended GitHub Repository Structure

```
eth-trading-dashboard/
├── README.md                              ← This document (copy here)
├── dashboard/
│   ├── ETH_Dashboard.jsx                  ← Main React artifact (export from Claude)
│   └── screenshots/
│       └── dashboard_preview.png
├── specs/
│   ├── ETH_Trading_Dashboard_Build_Spec.md  ← This file
│   └── api_endpoints.md                   ← Full API endpoint reference
├── trade_logs/
│   └── YYYY-MM-DD_trade_log.md            ← Daily trade session notes
└── .env.example                           ← API key template — never commit actual keys
```

### `.env.example` template:
```bash
# ETH Trading Dashboard — API Keys
# Copy to .env and fill in values. NEVER commit .env to git.

COINGECKO_API_KEY=
SOSOVALUE_API_KEY=
ETHERSCAN_API_KEY=
CRYPTOQUANT_API_KEY=
ANTHROPIC_API_KEY=

# No key required for these — called directly:
# api.alternative.me/fng/
# ethereumfear.com
# reddit.com/r/ethereum.json
# api.llama.fi/
```

---

## ✅ Pre-Build Checklist

Before starting the build chat, confirm all of the following:

**API Keys:**
- [ ] CoinGecko API key — regenerated (old key exposed in chat June 27)
- [ ] SoSoValue API key — signed up at sosovalue.com/developer (free demo tier)
- [ ] Etherscan API key — already on record from account
- [ ] CryptoQuant API key — from cryptoquant.com account
- [ ] Anthropic API key — from console.anthropic.com (for in-app Claude scoring calls)

**MCP Connectors (Claude.ai):**
- [ ] Crypto.com MCP connected — approve tool calls when prompted
- [ ] CryptoQuant MCP connected — follow setup at docs.cryptoquant.com/guides/mcp-server

**Environment:**
- [ ] Claude.ai open in browser (Pro or Team plan for artifact rendering)
- [ ] This build spec document open for reference during build
- [ ] New chat started — do not build in an existing conversation

**TradingView (no action needed):**
- [ ] Lightweight Charts™ loads from CDN automatically — no account, no approval, no key
- [ ] Do NOT attempt to request Advanced Charts library access — it is for companies only

---

## 🚨 Trading Discipline Rules (Hardcoded in Dashboard)

These rules are displayed as warnings in the dashboard UI and enforced in the AI scoring logic. They cannot be removed.

1. **Never short at key support** — if ETH sits on a major support level, score short entry as sub-optimal and flag
2. **Never long into resistance** — if ETH is directly below a resistance cluster, flag long entry as sub-optimal
3. **Cancel unfilled limit orders if thesis breaks** — dashboard flags if original entry level is no longer valid
4. **Flag Asia session entries** — entries between 23:00–08:00 CST surface a thin-liquidity warning
5. **BTC is the steering wheel** — ETH amplifies BTC moves. If BTC direction is unclear, flag WAIT and watch BTC
6. **Capitulation zone:** F&G < 20 + RSI < 30 → weight contrarian long more heavily, flag potential bounce
7. **Euphoria zone:** F&G > 80 + RSI > 70 → weight contrarian short more heavily, flag potential top
8. **4-day consecutive move** — flag selling/buying exhaustion if ETH has moved the same direction 4+ days
9. **Volume confirmation** — flag if daily volume is declining vs 7-day average (conviction fading)
10. **Funding rate extreme** — funding rate < −0.05% = crowded short → flag squeeze risk for longs

---

## 📅 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | June 27, 2026 | Initial spec — 18 metrics mapped to live data sources |
| 1.1 | June 28, 2026 | TradingView section rewritten: Advanced Charts library is company-only and inaccessible; replaced with TradingView Lightweight Charts™ (Apache 2.0, CDN, open source). Chart now fed by our own Crypto.com/CoinGecko OHLCV data. Added complete data source access audit confirming what is and is not fetchable. Added 3 additional trading discipline rules. Updated system prompt with explicit Lightweight Charts implementation instructions. |

---

*Built in collaboration with Claude (Anthropic) during live trading sessions June 24–28, 2026.*
*All trading decisions are the sole responsibility of the trader. This tool is for informational purposes only.*
