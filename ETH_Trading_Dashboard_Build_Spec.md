# ETH/USDT Pre-Trade Dashboard — Project Specification
**Version:** 2.1 | **Updated:** June 30, 2026 | **Platform:** HTX ETH/USDT Perpetual | **Author:** Esteban

---

## Project Overview

A **Flask API server + Telegram bot** that aggregates live market data across 40+ sources, scores 21 signal sections using deterministic rule-based logic, and delivers structured pre-trade assessments via Telegram commands.

All data fetching, indicator calculation, scoring, and output happen server-side. Zero LLM calls at runtime — analysis is pure Python logic. Telegram is the sole interface.

### Trading Parameters
| Parameter | Value |
|---|---|
| Exchange | HTX Futures |
| Instrument | ETH/USDT Perpetual |
| Leverage | 5× (Long or Short) |
| Typical hold | 4–12 hours |
| Stop loss | ~20% adverse ETH move |
| Take profit target | ~40% ETH move |
| Manual early exit | 5–10% gain if momentum stalls |
| Entry discipline | Cancel unfilled limit orders if setup invalidates |

---

## Architecture

```
Telegram User
     │  /data  /news  /analysis  /status
     ▼
telegram_bot.py  (python-telegram-bot v21, subprocess of app.py)
     │
     ▼
Flask API Server  (app.py, port 5001, prefix /dashboard/api/)
     ├── GET  /data      → fetch ~40 external APIs concurrently (aiohttp)
     ├── GET  /news      → SoSoValue macro + crypto + CT posts (ThreadPoolExecutor)
     ├── POST /analysis  → deterministic 21-section scoring (pure Python)
     ├── GET  /full      → data + news + analysis in one call
     └── GET  /health    → version check
```

**Key design decisions:**
- All API calls are server-side — avoids browser CORS restrictions
- `asyncio.gather` parallelizes all data fetches; single round-trip per `/data` call
- `/analysis` is CPU-only — no network calls, no LLM — takes <50ms
- `/news` has 30-minute cache; `/data` has 5-minute cache
- Bot supervisor in `app.py` — auto-restarts the bot subprocess on crash

---

## Server

| Detail | Value |
|---|---|
| Host | 100.81.66.33 |
| SSH port | 2223 |
| SSH user | tecviva |
| SSH key | `~/.ssh/harmonykey` |
| Repo path | `/home/tecviva/analytical-dashboards/` |
| Virtualenv | `/home/tecviva/analytical-dashboards/dashboard/venv/` |
| Flask port | 5001 |
| API prefix | `/dashboard/api/` |
| `.env` location | `/home/tecviva/analytical-dashboards/dashboard/.env` |

### Systemd service (manual install — requires sudo password)
```bash
sudo cp ~/analytical-dashboards/dashboard/eth-dashboard.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable eth-dashboard
sudo systemctl start eth-dashboard
```
Reference existing bot service: `/etc/systemd/system/tecbot-telegram.service`

### Manual start (current)
```bash
cd /home/tecviva/analytical-dashboards/dashboard
nohup venv/bin/python app.py > /tmp/dashboard.log 2>&1 &
```

---

## File Structure

```
analytical-dashboards/
├── ETH_Trading_Dashboard_Build_Spec.md   ← This file
└── dashboard/
    ├── app.py                            ← Flask entry point + bot supervisor
    ├── requirements.txt
    ├── .env                              ← API keys (never committed)
    ├── .env.example                      ← Key template (committed)
    ├── eth-dashboard.service             ← Systemd unit file
    ├── routes/
    │   ├── data.py                       ← /data — 40+ concurrent API fetches
    │   ├── news.py                       ← /news — SoSoValue macro/crypto/social
    │   └── analysis.py                   ← /analysis — 21-section scoring engine
    ├── services/
    │   └── technicals.py                 ← Pure-Python: EMA, RSI, MACD, BB, S/R
    ├── telegram_bot.py                   ← Bot commands: /data /news /analysis /status
    └── docs/
        └── SCORING_SPEC.md              ← Full quantitative scoring specification
```

---

## API Keys

```bash
# dashboard/.env  (never commit — copy from .env.example)

COINGECKO_API_KEY=       # coingecko.com/developers — Free Demo tier
ETHERSCAN_API_KEY=       # etherscan.io/apis — Free (5 calls/sec)
SOSOVALUE_API_KEY=       # sosovalue.com/developer — Free tier
CRYPTOQUANT_API_KEY=     # cryptoquant.com — Basic plan
CMC_API_KEY=             # coinmarketcap.com/api — Free/Basic

TELEGRAM_BOT_TOKEN=      # t.me/BotFather
TELEGRAM_ALLOWED_CHATS=  # comma-separated chat IDs (blank = allow all)
DASHBOARD_CHANNEL_ID=    # channel to post results (blank = reply in DM)

PORT=5001
DASHBOARD_URL=http://localhost:5001
```

**No key required — called freely:**
- `api.alternative.me/fng/` — fallback F&G index
- `ethereumfear.com` — ETH-specific F&G
- `api.llama.fi/` — DefiLlama CEX flows, Lido TVL, staking APR
- `www.okx.com/api/v5/public/` — funding rate, OI, L/S ratio
- `api.hbdm.com/linear-swap-api/v1/` — HTX funding, OI, L/S, liquidations
- `ultrasound.money/api/v2/` — ETH burn/supply metrics
- `scanner.tradingview.com/america/scan` — ETF volume scanner
- `eth.drpc.org` — ETH public RPC (withdrawal sampling)
- `api.crypto.com/exchange/v1/public/` — OHLCV candles, tickers

---

## Data Sources by Signal Section

| Section | Source | Endpoint / Method |
|---|---|---|
| §1 ETH Price | CoinGecko | `/coins/ethereum` |
| §2 Weekly Range vs EMA | CoinGecko 7D history + Crypto.com 1D candles | `market_chart?days=7` + `get-candlestick 1D` |
| §3 Crypto F&G | CoinMarketCap (primary) / alternative.me (fallback) | `/v3/fear-and-greed/latest` |
| §4 ETH F&G | ethereumfear.com | Next.js page scrape (`__NEXT_DATA__` JSON) |
| §5 EMA50/200 Cross | Crypto.com 200-day 1D candles → Python EMA | `get-candlestick 1D count=200` |
| §6 RSI Daily | Crypto.com 1D + 4H candles → Wilder RSI(14) | `get-candlestick 1D/4h` |
| §7 S/R Reward-Risk | Crypto.com 1D candles → Python swing algorithm | 50-candle lookback, 1.5% cluster |
| §8 ETF Flows | SoSoValue | `/etfs/summary-history?symbol=ETH&country_code=US` |
| §9 Price vs EMA Stack | Crypto.com 1D candles → EMA20/50/200 | Same candle data as §5/§6 |
| §10 Supply/Burn | ultrasound.money | `/api/v2/fees/gauge-rates` + `/burn-rates` |
| §11 Staking Flows | Etherscan v2 deposits + ETH public RPC withdrawals | Beacon deposit logs + `eth_getBlockByNumber` |
| §12 Social/CT | SoSoValue | `/news?category=4` (verified crypto CT accounts) |
| §13 Derivatives | HTX (primary) + OKX (secondary) | Funding, OI, elite L/S ratio, OI history |
| §14 Macro News | SoSoValue | `/news?category=13` (WSJ, Reuters, AP, Barron's) |
| §15 Crypto News | SoSoValue | `/news?category=1` (Cointelegraph, PANews, Odaily) |
| §16 Exchange Flows | DefiLlama | `/cexs` — 7 major CEX net 24h inflows |
| §17 Bollinger + MACD | Crypto.com 1D candles → Python BB(20,2σ) + MACD(12/26/9) | Same candle data |
| §18 BTC Influence | CoinMarketCap (dominance) + CoinGecko BTC | Global metrics + `/coins/bitcoin` |
| §19 ETH/BTC Cross | CoinGecko + CMC 24h/7d changes | Derived from existing price data |
| §20 Options IV | — | Placeholder — pending Deribit API |
| §21 Volatility Regime | — | Placeholder — pending DVOL data |

**Additional data fetched (supplementary):**
- CoinMarketCap global metrics and ETH/BTC quotes — volume split, multi-timeframe % changes
- TradingView ETF scanner — ETH + BTC spot ETF volume proxy (8 ETH, 6 BTC tickers)
- HTX liquidations (24h, 2 pages) + OKX liquidations — combined into 1h/4h/12h/24h buckets
- Etherscan `ethsupply2` — circulating supply, total burned, beacon deposits/withdrawals
- DefiLlama Lido protocol + LST pools — staking APR, TVL
- CoinGecko 30-day BTC price history — rolling 30d Pearson correlation and beta vs ETH

---

## Telegram Commands

| Command | Action |
|---|---|
| `/data` | Full live snapshot — price, EMAs, RSI, F&G, gas, ETF flows, derivatives, staking, CEX flows, BTC correlation |
| `/news` | Latest macro headlines (SoSoValue cat13), crypto news (cat1), CT posts (cat4) |
| `/analysis` | Fetches `/data` + `/news`, runs 21-section scoring, returns direction/confidence/scorecard/Options A-B-C |
| `/status` | Server health check |
| `/help` | Command list |
| `/dashboard` | Server URL |

**Output routing:** If `DASHBOARD_CHANNEL_ID` is set, results post to channel and bot acks in DM. Otherwise, results go directly to DM. Messages >4000 chars are auto-split.

---

## Scoring Engine

The full specification is in `dashboard/docs/SCORING_SPEC.md`. Summary:

- **21 sections** — §1 context, §2–§19 scored, §20–§21 placeholders
- **Raw scores:** −1.0, −0.5, 0, +0.5, +1.0 per section
- **4 tier weights:** CRITICAL ×2.0 · HIGH ×1.5 · STANDARD ×1.0 · LOW ×0.5
- **Confidence:** `50% + (weighted_net / 20.0) × 40%`, floor 40%, cap 90%
- **Trade options:** A (primary), B (contrarian), C (wait) — ranked by confidence
- **Hard rule flags:** 5 post-scoring override rules (near support/resistance, capitulation/euphoria zones, squeeze risk)
- **Zero LLM calls** — `_source: deterministic-rules-v2`

### Tier assignments
| Tier | Sections |
|---|---|
| CRITICAL ×2.0 | §5 MA Cross · §8 ETF Flows · §14 Macro · §18 BTC Influence |
| HIGH ×1.5 | §6 RSI · §7 S/R R/R · §9 Price vs EMA Stack · §13 Derivatives · §16 CEX Flows |
| STANDARD ×1.0 | §2 Weekly Range · §15 Crypto News · §17 BB+MACD · §19 ETH/BTC Cross |
| LOW ×0.5 | §3 Crypto F&G · §4 ETH F&G · §10 Supply/Burn · §11 Staking · §12 Social/CT |

---

## API Call Budget

`/data` makes ~40 concurrent calls per refresh. `/news` makes 3 calls (30-min cache). At 3 refreshes/day:

| API | Calls/refresh | Daily (3×) | Limit | Headroom |
|---|---|---|---|---|
| CoinGecko | 7 | 21 | 30/min, ~10k/day (Demo) | Ample |
| Etherscan | 4 | 12 | 5/sec, 100k/day | Ample |
| SoSoValue data | 1 | 3 | 20/min, 100k/mo | Ample |
| SoSoValue news | 3 (cached 30min) | 3–9 | 20/min | Ample |
| CMC | 3 | 9 | 10k/mo (Free) | Ample |
| CryptoQuant | 0 active | 0 | 50/day (Basic) | Reserved |
| OKX / HTX | 8 | 24 | No published limit (public) | Ample |
| ultrasound.money | 4 | 12 | No published limit (public) | Ample |
| DefiLlama | 3 | 9 | No published limit (public) | Ample |
| Crypto.com | 4 | 12 | No published limit (public) | Ample |
| ETH public RPC | 8 | 24 | No published limit (public) | Ample |
| TradingView scanner | 1 | 3 | No published limit (public) | Ample |

> CryptoQuant Basic plan (50 req/day) is reserved for future on-chain signals. Exchange flows now come from DefiLlama (free, no limit). Derivatives come from HTX/OKX public APIs (no key, no limit).

---

## Technical Indicators (Pure Python)

All indicators computed in `services/technicals.py` from Crypto.com 1D/4H candle OHLCV. No external indicator library.

| Indicator | Method | Output |
|---|---|---|
| EMA (20, 50, 200) | Wilder exponential smoothing | Current value + 100-point series for charting |
| RSI (14) | Wilder's method | Daily + 4H values |
| MACD (12/26/9) | EMA difference + signal EMA | Line, signal, histogram |
| Bollinger Bands (20, 2σ) | SMA ± 2 standard deviations | Upper, middle, lower |
| Support/Resistance | 50-candle swing high/low + 1.5% clustering | Top 3 supports, top 3 resistances |
| ETH/BTC Correlation | 30-day Pearson r | Rolling coefficient |
| ETH beta | Covariance / BTC variance | 30-day beta to BTC |

---

## Trading Discipline Rules (Hardcoded in Scoring Engine)

These fire as `flags` in the `/analysis` output and override the directional recommendation:

1. **Never short at key support** — ETH within 2% of nearest support AND net score bearish → flag
2. **Never long into resistance** — ETH within 2% of nearest resistance AND net score bullish → flag
3. **Capitulation zone** — F&G < 20 AND RSI < 30 simultaneously → flag contrarian long
4. **Euphoria zone** — F&G > 80 AND RSI > 70 simultaneously → flag contrarian short
5. **Squeeze risk** — Funding rate < −0.05% → flag crowded shorts / squeeze potential

---

## Upgrade Paths (Future Sections)

| Section | What | When |
|---|---|---|
| §20 Options IV/Skew | Deribit public API — ETH options IV and put/call skew | When added |
| §21 Volatility Regime | DVOL index from Deribit — low/normal/high vol regime | When added |
| §13 enhancement | Options IV divergence from futures positioning | After §20 |
| §12 enhancement | Targeted account feeds (@PeckShieldAlert, @VitalikButerin, @WatcherGuru) | If account-level CT API becomes available |
| CryptoQuant | On-chain exchange flows (ETH-specific, not aggregate) | CryptoQuant Professional tier |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0 | Jun 27, 2026 | Initial spec — React artifact, Claude AI scoring, 18 metrics |
| 1.1 | Jun 28, 2026 | TradingView: replaced Advanced Charts with Lightweight Charts™ |
| 1.2 | Jun 28, 2026 | Added mandatory A/B/C options panel |
| 2.0 | Jun 28, 2026 | Migrated to Flask API + Telegram bot; all fetches server-side; replaced Anthropic LLM scoring with deterministic Python rules; zero token usage |
| 2.1 | Jun 30, 2026 | Weighted 4-tier scoring (CRITICAL/HIGH/STANDARD/LOW); §9 Gas replaced by Price vs EMA Stack; §2 EMA-aware; §3/§4 gradient F&G; §13 L/S context-dependent; §18 bidirectional (5% BTC threshold); §19 ETH/BTC Cross added; §20/§21 placeholders; confidence denominator 20.0; Telegram is sole interface (no React frontend) |

---

*All trading decisions are the sole responsibility of the trader. This tool is for informational purposes only.*
