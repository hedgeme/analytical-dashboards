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
        "/dashboard — Web dashboard link\n"
        "/status — Server health\n"
        "/help — This message"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 *ETH Dashboard*\n{DASHBOARD_URL}/dashboard/\n\n"
        "Use /data for a quick snapshot or /analysis for the full A/B/C assessment.",
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

        fng_val = fg.get("value")
        etg_val = etg.get("value")
        rsi_val = tech.get("rsi")
        rsi_cls = ("Oversold" if rsi_val and rsi_val < 30 else
                   "Overbought" if rsi_val and rsi_val > 70 else "Neutral") if rsi_val else "N/A"

        supp = tech.get("supports",    [])
        res  = tech.get("resistances", [])
        sup_str = " / ".join(_fmt_price(p) for p in supp) if supp else "N/A"
        res_str = " / ".join(_fmt_price(p) for p in res)  if res  else "N/A"

        text = (
            f"📊 *ETH/USDT Snapshot*\n"
            f"─────────────────────\n"
            f"ETH  {_fmt_price(eth.get('price'))}  {_fmt_pct(eth.get('change_24h'))}\n"
            f"BTC  {_fmt_price(btc.get('price'))}  {_fmt_pct(btc.get('change_24h'))}\n"
            f"BTC Dom: {btc.get('dominance', 0):.1f}%\n"
            f"\n"
            f"7d High: {_fmt_price(wr.get('high'))}  Low: {_fmt_price(wr.get('low'))}\n"
            f"\n"
            f"F&G:     {fng_val} {_fng_emoji(fng_val)}  {fg.get('classification','')}\n"
            f"ETH F&G: {etg_val} {_fng_emoji(etg_val)}\n"
            f"\n"
            f"RSI (1D): {round(rsi_val,1) if rsi_val else 'N/A'} — {rsi_cls}\n"
            f"RSI (4H): {round(tech.get('rsi_4h',0),1) if tech.get('rsi_4h') else 'N/A'}\n"
            f"EMA20:  {_fmt_price(tech.get('ema20'))}\n"
            f"EMA50:  {_fmt_price(tech.get('ema50'))}\n"
            f"EMA200: {_fmt_price(tech.get('ema200'))}\n"
            f"\n"
            f"Support:    {sup_str}\n"
            f"Resistance: {res_str}\n"
            f"\n"
            f"Gas:     {gas.get('safe','N/A')} / {gas.get('fast','N/A')} gwei\n"
            f"Funding: {der.get('funding_rate','N/A')}%\n"
            f"L/S:     {der.get('long_short_ratio','N/A')}\n"
            f"OI:      ${der.get('open_interest_usd', 0)/1e9:.2f}B\n" if der.get('open_interest_usd') else f"OI:      N/A\n"
        )

        await msg.delete()
        await _post(context, update, text)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Searching news (~15s)…")
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

        lines.append("\n*Crypto / X:*")
        crypto = d.get("crypto", [])
        if not crypto:
            lines.append("No crypto events retrieved.")
        for h in crypto:
            tag = {"BEARISH": "🔴", "BULLISH": "🟢", "NEUTRAL": "⚪"}.get(h.get("impact",""), "•")
            src  = f" ({h['source']})" if h.get("source") else ""
            lines.append(f"{tag}{_md(src)} {_md(h.get('title',''))}")
            if h.get("detail"):
                lines.append(f"   {_md(h['detail'])}")

        await msg.delete()
        await _post(context, update, "\n".join(lines))
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")


async def cmd_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Running full analysis (~45s)…")
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
        total = bear + bull + neut or 18
        bull_bar = int(round(bull / total * 20))
        bear_bar = 20 - bull_bar

        text = (
            f"📊 *ETH/USDT Trade Assessment*\n"
            f"─────────────────────────────\n"
            f"{'🔴' * bear_bar}{'🟢' * bull_bar}\n"
            f"Bear {bear} | Neut {neut} | Bull {bull}\n"
            f"Direction: {dir_emoji} *{agg.get('direction','?')}*  (net {agg.get('net_score','?')})\n"
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
