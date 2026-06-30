"""
ETH Dashboard Telegram Bot
Commands: /dashboard /data /news /analysis /status /help

Pattern (same as TecBot):
  - You DM the bot a command
  - Bot posts the full result to DASHBOARD_CHANNEL_ID
  - Bot acks in your DM: "✅ Posted to channel"
  - If DASHBOARD_CHANNEL_ID is not set, result goes directly to DM
"""

import os
import json
import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:5001")
CHANNEL_ID    = os.getenv("DASHBOARD_CHANNEL_ID", "")   # e.g. -1004498661915
API_TIMEOUT   = 90.0

PIDFILE = "/tmp/eth-dashboard-bot.pid"


# ─── helpers ──────────────────────────────────────────────────────────────────

def _md(text: str) -> str:
    """Escape characters that break Telegram MarkdownV1 parser."""
    if not text:
        return ""
    # [ ] cause false link detection; _ * ` are formatting chars
    for ch in ["[", "]", "_", "*", "`"]:
        text = text.replace(ch, f"\\{ch}")
    return text


def _fmt_price(v) -> str:
    if v is None: return "N/A"
    return f"${float(v):,.2f}"

def _fmt_pct(v) -> str:
    if v is None: return "N/A"
    sign = "+" if float(v) >= 0 else ""
    return f"{sign}{float(v):.2f}%"

def _fng_emoji(v) -> str:
    if v is None: return "❓"
    v = int(v)
    if v <= 20: return "😱"
    if v <= 40: return "😨"
    if v <= 60: return "😐"
    if v <= 80: return "😊"
    return "🤩"


async def _post(context: ContextTypes.DEFAULT_TYPE, update: Update, text: str):
    """
    Send text to the channel (if configured) and ack in DM.
    If no channel configured, send full text in DM.
    Splits messages longer than 4000 chars.
    """
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]

    if CHANNEL_ID:
        for chunk in chunks:
            try:
                await context.bot.send_message(
                    chat_id=CHANNEL_ID, text=chunk, parse_mode="Markdown"
                )
            except Exception as e:
                print(f"[telegram] channel post failed: {e}")
                # fall back to DM on channel error
                await update.message.reply_text(chunk, parse_mode="Markdown")
                return
        await update.message.reply_text("✅ Posted to channel")
    else:
        for chunk in chunks:
            await update.message.reply_text(chunk, parse_mode="Markdown")


async def api_get(path: str) -> dict:
    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
        r = await client.get(f"{DASHBOARD_URL}/dashboard/api{path}")
        r.raise_for_status()
        return r.json()


async def api_post(path: str, body: dict) -> dict:
    async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
        r = await client.post(f"{DASHBOARD_URL}/dashboard/api{path}", json=body)
        r.raise_for_status()
        return r.json()


# ─── command handlers ─────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📊 *ETH/USDT Pre-Trade Dashboard*\n\n"
        "/data — Live ETH/BTC snapshot\n"
        "/news — Macro + crypto headlines\n"
        "/analysis — Full A/B/C trade assessment\n"
        "/status — Server health\n"
        "/help — This message"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 *ETH Dashboard*\nAPI server: `{DASHBOARD_URL}/dashboard/api/`\n\n"
        "Use /data for a live snapshot or /analysis for the full A/B/C assessment.",
        parse_mode="Markdown",
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{DASHBOARD_URL}/dashboard/health")
            d = r.json()
        await update.message.reply_text(f"✅ Server OK — v{d.get('version','?')}")
    except Exception as e:
        await update.message.reply_text(f"❌ Server unreachable: {e}")


async def cmd_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Fetching live data…")
    try:
        d    = await api_get("/data")
        eth  = d.get("eth",  {})
        btc  = d.get("btc",  {})
        fg   = d.get("fear_greed", {})
        etg  = d.get("eth_fear_greed", {})
        tech = d.get("technicals", {})
        gas  = d.get("gas",  {})
        der  = d.get("derivatives", {})
        wr   = d.get("weekly_range", {})
        mkt  = d.get("market", {})
        sup_ = d.get("supply", {})
        stk  = d.get("staking", {})
        etf  = d.get("etf_flows", {})
        cex  = d.get("exchange_flows", {})

        okx  = der.get("okx", {})
        htx  = der.get("htx", {})
        liqs = der.get("liquidations", {})

        # ── helpers ───────────────────────────────────────────────────────────
        def _b(v):
            return f"${float(v)/1e9:.2f}B" if v is not None else "N/A"
        def _t(v):
            return f"${float(v)/1e12:.2f}T" if v is not None else "N/A"
        def _n(v, fmt=".1f"):
            return format(float(v), fmt) if v is not None else "N/A"
        def _g(v):
            """Format gwei: show 2 dp if < 1, else 0 dp."""
            if v is None: return "N/A"
            f = float(v)
            return f"{f:.2f}" if f < 1 else f"{f:.0f}"

        # ── derived values ────────────────────────────────────────────────────
        rsi_val = tech.get("rsi")
        rsi_cls = (
            "Oversold"        if rsi_val < 30 else
            "Near Oversold"   if rsi_val < 45 else
            "Neutral"         if rsi_val < 55 else
            "Near Overbought" if rsi_val < 70 else
            "Overbought"
        ) if rsi_val else "N/A"
        supp = tech.get("supports",    [])
        res  = tech.get("resistances", [])

        fng_val = fg.get("value")
        etg_val = etg.get("value")
        fng_7d  = fg.get("7d_trend", [])

        burn_day  = sup_.get("burn_rate_eth_per_day")
        iss_day   = sup_.get("issuance_eth_per_day")
        net_daily = sup_.get("net_daily_eth")
        sc_24h    = sup_.get("supply_change_24h")
        is_defl   = sup_.get("is_deflationary")
        staked    = sup_.get("total_eth_staked_usm")
        circ      = sup_.get("circulating_eth")
        burned    = sup_.get("total_burned_eth")

        cex_dir  = cex.get("direction_24h", "")
        cex_24h  = cex.get("total_24h_usd_m")
        cex_1w   = cex.get("total_1w_usd_m")
        # 🟢 outflow = ETH leaving exchanges = accumulation = bullish signal
        cex_icon = "🔴" if cex_dir == "inflow" else "🟢" if cex_dir == "outflow" else "⚪"

        etf_date    = etf.get("date", "N/A")
        etf_daily   = etf.get("daily_net_inflow_usd")
        etf_weekly  = etf.get("weekly_net_inflow_usd")
        etf_monthly = etf.get("monthly_net_inflow_usd")
        etf_aum     = etf.get("total_aum_usd")
        etf_cum     = etf.get("cum_net_inflow_usd")
        etf_source  = etf.get("source", "SoSoValue")

        def _flow(v):
            """Format net flow: 🟢 +$12.1M or 🔴 -$45.3M"""
            if v is None: return "N/A"
            m = abs(float(v)) / 1e6
            if float(v) >= 0:
                return f"🟢 +${m:.1f}M  (inflow)"
            return f"🔴 -${m:.1f}M  (outflow)"

        # ── assemble ──────────────────────────────────────────────────────────
        L = []
        L.append("📊 *ETH/USDT Pre-Trade Dashboard*")
        L.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # §1 Price Action + weekly range merged
        L.append("\n*§1 Price Action*")
        L.append(f"ETH  {_fmt_price(eth.get('price'))}  "
                 f"24h {_fmt_pct(eth.get('change_24h'))}  "
                 f"7d {_fmt_pct(eth.get('change_7d'))}  "
                 f"30d {_fmt_pct(eth.get('change_30d'))}")
        L.append(f"Range 24h: {_fmt_price(eth.get('price_24h_low'))} – {_fmt_price(eth.get('price_24h_high'))}")
        L.append(f"Range 7d:  {_fmt_price(wr.get('low'))} – {_fmt_price(wr.get('high'))}  "
                 f"(avg {_fmt_price(wr.get('avg'))})")
        L.append(f"MCap: {_b(eth.get('market_cap'))}")
        L.append(f"24h Vol (all venues): {_b(eth.get('volume_24h'))}")
        L.append(f"  CEX {_b(eth.get('cex_volume_24h'))} — centralized order books")
        L.append(f"  DEX {_b(eth.get('dex_volume_24h'))} — on-chain AMM / DeFi")

        # §2 BTC / Market
        L.append("\n*§2 BTC / Global Market*")
        L.append(f"BTC  {_fmt_price(btc.get('price'))}  "
                 f"24h {_fmt_pct(btc.get('change_24h'))}  "
                 f"7d {_fmt_pct(btc.get('change_7d'))}  "
                 f"30d {_fmt_pct(btc.get('change_30d'))}")
        L.append(f"BTC Dom {_n(btc.get('dominance'))}%  ETH Dom {_n(mkt.get('eth_dominance'))}%")
        L.append(f"Total MCap: {_t(mkt.get('total_market_cap_usd'))}")
        L.append(f"Stablecoins: {_b(mkt.get('stablecoin_market_cap'))}  "
                 f"↑ rising = dry powder entering market")
        L.append(f"DeFi Vol 24h: {_b(mkt.get('defi_volume_24h_usd'))}")
        L.append(f"Derivatives Vol 24h: {_b(mkt.get('derivatives_volume_24h'))}")

        # §3 Fear & Greed
        L.append("\n*§3 Fear \\& Greed (CoinMarketCap)*")
        L.append(f"BTC: {fng_val} {_fng_emoji(fng_val)}  {_md(fg.get('classification',''))}")
        L.append(f"ETH: {etg_val} {_fng_emoji(etg_val)}")
        if fng_7d:
            trend_str = " → ".join(str(v) for v in fng_7d[-7:])
            L.append(f"7d: {_md(trend_str)}  (0=Extreme Fear, 100=Extreme Greed)")

        # §4 Technicals
        L.append("\n*§4 Technicals*")
        L.append(f"RSI (1D): {_n(rsi_val)} — {rsi_cls}")
        L.append(f"RSI (4H): {_n(tech.get('rsi_4h'))}")
        L.append(f"EMA20:  {_fmt_price(tech.get('ema20'))}  (short-term trend)")
        L.append(f"EMA50:  {_fmt_price(tech.get('ema50'))}  (medium-term trend)")
        L.append(f"EMA200: {_fmt_price(tech.get('ema200'))}  (long-term trend / bull-bear line)")
        if supp:
            for i, p in enumerate(supp, 1):
                L.append(f"S{i}: {_fmt_price(p)}  (demand zone — buyers historically step in)")
        if res:
            for i, p in enumerate(res, 1):
                L.append(f"R{i}: {_fmt_price(p)}  (supply zone — sellers historically step in)")

        # §5 Gas
        L.append("\n*§5 Gas (Ethereum L1)*")
        L.append(f"Safe: {_g(gas.get('safe'))} | "
                 f"Propose: {_g(gas.get('propose'))} | "
                 f"Fast: {_g(gas.get('fast'))} gwei")

        # §6 ETF Flows (SoSoValue — actual net dollar flows)
        L.append(f"\n*§6 ETF Flows ({etf_source} | {etf_date})*")
        L.append(f"Daily:   {_flow(etf_daily)}")
        L.append(f"Weekly:  {_flow(etf_weekly)}")
        L.append(f"Monthly: {_flow(etf_monthly)}")
        L.append(f"Total ETH ETF AUM: {_b(etf_aum)}")
        L.append(f"Cum. inflow (since launch): {_b(etf_cum)}")
        L.append("  🟢 inflow = new $ into ETH ETFs = institutional buying")
        L.append("  🔴 outflow = $ leaving ETH ETFs = institutional selling")

        # §7 Derivatives
        L.append("\n*§7 Derivatives*")
        L.append("OKX ETH-USDT-SWAP")
        L.append(f"  Funding: {okx.get('funding_rate','N/A')}%  "
                 f"(+ = longs pay shorts; - = shorts pay longs)")
        L.append(f"  OI: {_b(okx.get('open_interest_usd'))}  "
                 f"L/S: {okx.get('long_short_ratio','N/A')}")
        L.append("HTX ETH-USDT (USDT-M Perp — your exchange)")
        L.append(f"  Funding: {htx.get('funding_rate','N/A')}%")
        L.append(f"  OI: {_b(htx.get('open_interest_usd'))}  "
                 f"L/S: {htx.get('long_short_ratio','N/A')}")
        oi_pct = htx.get("oi_24h_change_pct")
        oi_trend = htx.get("oi_trend", "")
        if oi_pct is not None:
            trend_arrow = "↑" if oi_trend == "rising" else "↓" if oi_trend == "falling" else "→"
            L.append(f"  OI 24h: {oi_pct:+.1f}% {trend_arrow} {oi_trend}  "
                     f"(rising OI + price = strong trend; falling OI = weakening)")
        L.append("Liquidations (OKX + HTX combined)")
        if liqs:
            liq24 = liqs.get("24h", {})
            liq4  = liqs.get("4h",  {})
            liq1  = liqs.get("1h",  {})
            if liq24:
                bias = liq24.get("bias","")
                bias_note = ("⚠️ more longs blown out — selling pressure" if bias == "long_heavy"
                             else "⚠️ more shorts blown out — short squeeze" if bias == "short_heavy"
                             else "balanced")
                L.append(f"  24h: Long ${liq24.get('long_usd_m','?')}M  "
                         f"Short ${liq24.get('short_usd_m','?')}M  {bias_note}")
            if liq4:
                L.append(f"   4h: Long ${liq4.get('long_usd_m','?')}M  "
                         f"Short ${liq4.get('short_usd_m','?')}M")
            if liq1:
                L.append(f"   1h: Long ${liq1.get('long_usd_m','?')}M  "
                         f"Short ${liq1.get('short_usd_m','?')}M")
        else:
            L.append("  No significant liquidations in sample window")
        L.append("Note: futures/spot net flows require CoinGlass paid API")

        # §8 Supply / Burn
        L.append("\n*§8 Supply / Burn*")
        L.append(f"Circulating supply: {f'{circ:,}' if circ else 'N/A'} ETH")
        L.append(f"Total burned (EIP-1559 all-time): {f'{burned:,}' if burned else 'N/A'} ETH")
        L.append(f"Issuance:  +{f'{iss_day:,.1f}' if iss_day else 'N/A'} ETH/day  "
                 f"(PoS validator rewards)")
        L.append(f"Burn:      -{f'{burn_day:,.1f}' if burn_day else 'N/A'} ETH/day  "
                 f"(EIP-1559 base fee destroyed)")
        if net_daily is not None and sc_24h is not None:
            defl_str = "🔥 DEFLATIONARY" if is_defl else "📈 INFLATIONARY"
            L.append(f"Net Δ/day: {sc_24h:+.1f} ETH  →  {defl_str}")
            L.append(f"  (negative = supply shrinking; positive = supply growing)")

        # §9 Staking
        staked_24h   = stk.get("staked_24h_eth")
        validators_in = stk.get("validators_entered_24h")
        unstaked_24h  = stk.get("unstaked_24h_eth_est")
        net_stake     = stk.get("net_stake_change_24h")
        L.append("\n*§9 Staking*")
        L.append(f"Total staked: {f'{staked:,}' if staked else 'N/A'} ETH  "
                 f"({f'{staked/circ*100:.1f}' if staked and circ else '?'}% of supply locked)")
        L.append(f"Staking APR: {stk.get('staking_apr_pct','N/A')}%  "
                 f"(stETH/wstETH via Lido)")
        L.append(f"Lido TVL: {_b(stk.get('lido_tvl_usd'))}")
        L.append("24h Staking Activity (beacon chain):")
        if staked_24h is not None:
            L.append(f"  Staked:   +{staked_24h:,} ETH  "
                     f"({validators_in:,} new validators × 32 ETH)")
        else:
            L.append("  Staked:   N/A")
        if unstaked_24h is not None:
            L.append(f"  Unstaked: ~{unstaked_24h:,} ETH  (block sample estimate)")
        else:
            L.append("  Unstaked: N/A")
        if net_stake is not None:
            arrow = "↑" if net_stake > 0 else "↓"
            L.append(f"  Net 24h:  {net_stake:+,} ETH {arrow}  "
                     f"({'net staking' if net_stake > 0 else 'net unstaking'})")

        # §10 Exchange Flows
        L.append("\n*§10 Exchange Flows (DefiLlama CEX)*")
        L.append(f"{cex_icon} Net 24h: ${cex_24h}M {cex_dir.upper() if cex_dir else ''}  |  "
                 f"1w: ${cex_1w}M")
        L.append("  🟢 outflow = ETH leaving exchanges = accumulation (bullish)")
        L.append("  🔴 inflow  = ETH entering exchanges = sell pressure (bearish)")
        exch = cex.get("exchanges", {})
        for name in ["Binance", "OKX", "HTX", "Bybit"]:
            e = exch.get(name)
            if e:
                L.append(f"  {name}: 24h ${e.get('inflow_24h_usd_m','?')}M  "
                         f"1w ${e.get('inflow_1w_usd_m','?')}M  "
                         f"TVL {_b((e.get('tvl_usd_b') or 0)*1e9)}")

        # §11 BTC/ETH Correlation
        r    = btc.get("correlation_30d")
        beta = btc.get("beta_30d")
        L.append("\n*§11 BTC/ETH Correlation (30-day)*")
        L.append(f"Pearson r = {r if r is not None else 'N/A'}")
        L.append(f"  → how closely ETH tracks BTC (1.0 = moves in lockstep, 0 = no relation)")
        L.append(f"Beta β = {beta if beta is not None else 'N/A'}")
        L.append(f"  → ETH amplification of BTC moves (β=1.23 means BTC +1% → ETH +1.23%)")
        if r is not None and beta is not None:
            r_f, b_f = float(r), float(beta)
            if r_f > 0.85 and b_f > 1.1:
                interp = "ETH is a high-beta BTC proxy — BTC drives direction"
            elif r_f > 0.7:
                interp = "Strong BTC correlation — monitor BTC for entry signals"
            elif r_f < 0.4:
                interp = "Low correlation — ETH moving on its own fundamentals"
            else:
                interp = "Moderate correlation"
            L.append(f"  → {_md(interp)}")

        await msg.delete()
        await _post(context, update, "\n".join(L))
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Fetching news…")
    try:
        d = await api_get("/news")
        lines = ["📰 *Market News*\n"]

        lines.append("*Macro:*")
        macro = d.get("macro", [])
        if not macro:
            lines.append("No macro events retrieved.")
        for h in macro:
            tag = {"BEARISH": "🔴", "BULLISH": "🟢", "NEUTRAL": "⚪"}.get(h.get("impact",""), "•")
            lines.append(f"{tag} {_md(h.get('title',''))}")
            if h.get("detail"):
                lines.append(f"   {_md(h['detail'])}")

        lines.append("\n*Crypto:*")
        crypto = d.get("crypto", [])
        if not crypto:
            lines.append("No crypto events retrieved.")
        for h in crypto:
            tag = {"BEARISH": "🔴", "BULLISH": "🟢", "NEUTRAL": "⚪"}.get(h.get("impact",""), "•")
            src  = f" ({h['source']})" if h.get("source") else ""
            lines.append(f"{tag}{_md(src)} {_md(h.get('title',''))}")
            if h.get("detail"):
                lines.append(f"   {_md(h['detail'])}")

        social = d.get("social", [])
        if social:
            lines.append("\n*CT / X Posts:*")
            for h in social:
                tag = {"BEARISH": "🔴", "BULLISH": "🟢", "NEUTRAL": "⚪"}.get(h.get("impact",""), "•")
                src  = f" @{h['source']}" if h.get("source") else ""
                lines.append(f"{tag}{_md(src)} {_md(h.get('title',''))}")

        await msg.delete()
        await _post(context, update, "\n".join(lines))
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def cmd_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Running analysis…")
    try:
        data   = await api_get("/data")
        news   = await api_get("/news")
        result = await api_post("/analysis", {"data": {**data, "news": news}})

        agg  = result.get("aggregate", {})
        opts = result.get("options",   {})
        rank = result.get("ranked",    [])
        A = opts.get("A", {})
        B = opts.get("B", {})
        C = opts.get("C", {})

        dir_emoji = {"LONG": "🟢", "SHORT": "🔴", "WAIT": "🟡"}.get(agg.get("direction",""), "❓")

        def zone(z):
            if isinstance(z, list) and len(z) == 2:
                return f"{_fmt_price(z[0])} – {_fmt_price(z[1])}"
            return str(z) if z else "N/A"

        sc = result.get("scorecard", {})
        bear = agg.get("bearish", 0)
        bull = agg.get("bullish", 0)
        neut = agg.get("neutral", 0)
        total = bear + bull + neut or 21
        bull_bar = int(round(bull / total * 20))
        bear_bar = 20 - bull_bar
        net   = agg.get("net_score", 0)
        conf  = agg.get("confidence", "?")

        text = (
            f"📊 *ETH/USDT Trade Assessment*\n"
            f"─────────────────────────────\n"
            f"{'🔴' * bear_bar}{'🟢' * bull_bar}\n"
            f"Bear {bear} | Neut {neut:.0f} | Bull {bull}\n"
            f"Direction: {dir_emoji} *{agg.get('direction','?')}*  (net {net:+.1f} | {conf}% confidence)\n"
            f"\n"
            f"┌─ 🅐 *Option A — {A.get('direction','?')} {A.get('confidence','?')}%*\n"
            f"│ Entry:  {zone(A.get('entry_zone'))}\n"
            f"│ Target: {_fmt_price(A.get('target1'))} → {_fmt_price(A.get('target2'))}\n"
            f"│ Stop:   {_fmt_price(A.get('stop'))}\n"
            f"│ {_md(A.get('thesis',''))}\n"
            f"│ Risks: {_md(', '.join(A.get('risks', [])))}\n"
            f"\n"
            f"┌─ 🅑 *Option B — {B.get('direction','?')} {B.get('confidence','?')}% (contrarian)*\n"
            f"│ Only if: {_md(B.get('entry_condition',''))}\n"
            f"│ Entry: {zone(B.get('entry_zone'))}  Stop: {_fmt_price(B.get('stop'))}\n"
            f"│ {_md(B.get('thesis',''))}\n"
            f"\n"
            f"┌─ 🅒 *Option C — WAIT*\n"
            f"│ {_md(C.get('reason',''))}\n"
            f"│ → A: {_md(C.get('watch_for_A',''))}\n"
            f"│ → B: {_md(C.get('watch_for_B',''))}\n"
            f"\n"
            f"*Ranked:*\n"
        )
        for r in rank:
            text += f"{r.get('rank','?')}. {r.get('label','?')} — {r.get('summary','')}\n"

        flags = result.get("flags", [])
        if flags:
            text += "\n⚠️ " + " | ".join(flags)

        await msg.delete()
        await _post(context, update, text)
    except Exception as e:
        await msg.edit_text(f"❌ Analysis error: {e}")


# ─── PID lock ─────────────────────────────────────────────────────────────────

def _acquire_lock() -> bool:
    import signal
    if os.path.exists(PIDFILE):
        try:
            old_pid = int(open(PIDFILE).read().strip())
            os.kill(old_pid, signal.SIG_DFL)
            print(f"[telegram] another instance running (pid {old_pid}), exiting")
            return False
        except (OSError, ValueError):
            pass
    open(PIDFILE, "w").write(str(os.getpid()))
    return True

def _release_lock():
    try: os.remove(PIDFILE)
    except FileNotFoundError: pass


# ─── entry point ──────────────────────────────────────────────────────────────

def run():
    if not BOT_TOKEN:
        print("[telegram] TELEGRAM_BOT_TOKEN not set — disabled")
        return
    if not _acquire_lock():
        return
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        for cmd, fn in [
            ("help",      cmd_help),
            ("start",     cmd_help),
            ("dashboard", cmd_dashboard),
            ("status",    cmd_status),
            ("data",      cmd_data),
            ("news",      cmd_news),
            ("analysis",  cmd_analysis),
        ]:
            application.add_handler(CommandHandler(cmd, fn))

        ch = f" → channel {CHANNEL_ID}" if CHANNEL_ID else " → DM only"
        print(f"[telegram] bot polling… (pid {os.getpid()}){ch}", flush=True)
        application.run_polling(drop_pending_updates=True)
    finally:
        _release_lock()


if __name__ == "__main__":
    run()
