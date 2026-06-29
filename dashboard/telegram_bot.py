"""
ETH Dashboard Telegram Bot
Commands: /dashboard /data /news /analysis /status /help

Can run as:
  1. Background thread from app.py (when TELEGRAM_BOT_TOKEN is set)
  2. Standalone: python telegram_bot.py

Calls Flask API endpoints at localhost:5001 so all logic stays in one place.
"""

import asyncio
import json
import os
import httpx

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

BOT_TOKEN     = os.getenv("TELEGRAM_BOT_TOKEN", "")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://localhost:5001")
CHAT_ALLOWLIST_STR = os.getenv("TELEGRAM_ALLOWED_CHATS", "")
ALLOWED_CHATS = set(CHAT_ALLOWLIST_STR.split(",")) if CHAT_ALLOWLIST_STR else set()

API_TIMEOUT = 60.0  # seconds — analysis call can take ~30s


# ─── auth guard ───────────────────────────────────────────────────────────────

def is_allowed(update: Update) -> bool:
    if not ALLOWED_CHATS:
        return True  # open if no allowlist configured
    return str(update.effective_chat.id) in ALLOWED_CHATS


async def guard(update: Update) -> bool:
    if not is_allowed(update):
        await update.message.reply_text("⛔ Unauthorized.")
        return False
    return True


# ─── helpers ──────────────────────────────────────────────────────────────────

def _fmt_price(v) -> str:
    if v is None:
        return "N/A"
    return f"${float(v):,.2f}"


def _fmt_pct(v) -> str:
    if v is None:
        return "N/A"
    sign = "+" if float(v) >= 0 else ""
    return f"{sign}{float(v):.2f}%"


def _fng_emoji(v) -> str:
    if v is None:
        return "❓"
    v = int(v)
    if v <= 20:   return "😱"
    if v <= 40:   return "😨"
    if v <= 60:   return "😐"
    if v <= 80:   return "😊"
    return "🤩"


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
    if not await guard(update): return
    text = (
        "📊 *ETH/USDT Pre-Trade Dashboard*\n\n"
        "/dashboard — Web dashboard link\n"
        "/data — Live price snapshot\n"
        "/news — Macro + crypto headlines\n"
        "/analysis — Full A/B/C trade assessment\n"
        "/status — Server health check\n"
        "/help — This message"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    await update.message.reply_text(
        f"📊 *ETH Dashboard*\n{DASHBOARD_URL}/dashboard/\n\n"
        "Use /data for quick metrics or /analysis for full assessment.",
        parse_mode="Markdown",
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{DASHBOARD_URL}/dashboard/health")
            d = r.json()
        await update.message.reply_text(f"✅ Server OK — v{d.get('version', '?')}")
    except Exception as e:
        await update.message.reply_text(f"❌ Server unreachable: {e}")


async def cmd_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    msg = await update.message.reply_text("⏳ Fetching live data…")
    try:
        d = await api_get("/data")
        eth = d.get("eth", {})
        btc = d.get("btc", {})
        fg  = d.get("fear_greed", {})
        etg = d.get("eth_fear_greed", {})
        tech = d.get("technicals", {})
        gas  = d.get("gas", {})
        der  = d.get("derivatives", {})

        fng_val = fg.get("value")
        etg_val = etg.get("value")

        text = (
            f"📊 *ETH/USDT Snapshot*\n"
            f"──────────────────\n"
            f"ETH:  {_fmt_price(eth.get('price'))}  {_fmt_pct(eth.get('change_24h'))}\n"
            f"BTC:  {_fmt_price(btc.get('price'))}  {_fmt_pct(btc.get('change_24h'))}\n"
            f"BTC Dom: {btc.get('dominance', 'N/A'):.1f}%\n"
            f"\n"
            f"F&G:     {fng_val} {_fng_emoji(fng_val)}  ({fg.get('classification', 'N/A')})\n"
            f"ETH F&G: {etg_val} {_fng_emoji(etg_val)}\n"
            f"\n"
            f"RSI (1D): {tech.get('rsi', 'N/A')}\n"
            f"RSI (4H): {tech.get('rsi_4h', 'N/A')}\n"
            f"EMA20:  {_fmt_price(tech.get('ema20'))}\n"
            f"EMA50:  {_fmt_price(tech.get('ema50'))}\n"
            f"EMA200: {_fmt_price(tech.get('ema200'))}\n"
            f"\n"
            f"Gas:  {gas.get('safe', 'N/A')} / {gas.get('fast', 'N/A')} gwei\n"
            f"Funding: {der.get('funding_rate', 'N/A')}\n"
            f"L/S Ratio: {der.get('long_short_ratio', 'N/A')}\n"
        )
        supports    = tech.get("supports",    [])
        resistances = tech.get("resistances", [])
        if supports:
            text += f"Support:    {' / '.join(_fmt_price(p) for p in supports)}\n"
        if resistances:
            text += f"Resistance: {' / '.join(_fmt_price(p) for p in resistances)}\n"

        await msg.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error fetching data: {e}")


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    msg = await update.message.reply_text("⏳ Fetching news (web search)…")
    try:
        d = await api_get("/news")
        lines = ["📰 *Latest News*\n"]

        lines.append("*Macro:*")
        for h in d.get("macro", []):
            tag = {"BEARISH": "🔴", "BULLISH": "🟢", "NEUTRAL": "⚪"}.get(h.get("impact", ""), "•")
            lines.append(f"{tag} {h.get('title', '')}")
            if h.get("detail"):
                lines.append(f"   _{h['detail']}_")

        lines.append("\n*Crypto:*")
        for h in d.get("crypto", []):
            tag = {"BEARISH": "🔴", "BULLISH": "🟢", "NEUTRAL": "⚪"}.get(h.get("impact", ""), "•")
            lines.append(f"{tag} {h.get('title', '')}")
            if h.get("detail"):
                lines.append(f"   _{h['detail']}_")

        await msg.edit_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error fetching news: {e}")


async def cmd_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard(update): return
    msg = await update.message.reply_text("⏳ Running full analysis (30–60s)…")
    try:
        # fetch data + news first
        data = await api_get("/data")
        news = await api_get("/news")
        combined = {**data, "news": news}

        result = await api_post("/analysis", {"data": combined})

        agg  = result.get("aggregate", {})
        opts = result.get("options",   {})
        rank = result.get("ranked",    [])
        A = opts.get("A", {})
        B = opts.get("B", {})
        C = opts.get("C", {})

        dir_emoji = {"LONG": "🟢", "SHORT": "🔴", "WAIT": "🟡"}.get(agg.get("direction", ""), "❓")

        def zone(z):
            if isinstance(z, list) and len(z) == 2:
                return f"{_fmt_price(z[0])} – {_fmt_price(z[1])}"
            return str(z)

        text = (
            f"📊 *ETH/USDT Trade Assessment*\n"
            f"──────────────────\n"
            f"Bear: {agg.get('bearish','?')} | Neut: {agg.get('neutral','?')} | Bull: {agg.get('bullish','?')}\n"
            f"Direction: {dir_emoji} *{agg.get('direction','?')}*  (score {agg.get('net_score','?')})\n"
            f"\n"
            f"*🅐 Option A — {A.get('direction','?')} {A.get('confidence','?')}%*\n"
            f"Entry: {zone(A.get('entry_zone'))}\n"
            f"Target: {_fmt_price(A.get('target1'))} / {_fmt_price(A.get('target2'))}\n"
            f"Stop: {_fmt_price(A.get('stop'))}\n"
            f"{A.get('thesis','')}\n"
            f"\n"
            f"*🅑 Option B — {B.get('direction','?')} {B.get('confidence','?')}% (contrarian)*\n"
            f"Only if: {B.get('entry_condition','')}\n"
            f"Entry: {zone(B.get('entry_zone'))}  Stop: {_fmt_price(B.get('stop'))}\n"
            f"\n"
            f"*🅒 Option C — WAIT*\n"
            f"{C.get('reason','')}\n"
            f"Watch → A: {C.get('watch_for_A','')}\n"
            f"Watch → B: {C.get('watch_for_B','')}\n"
            f"\n"
            f"*Ranked:*\n"
        )
        for r in rank:
            text += f"{r.get('rank','?')}. {r.get('label','?')} — {r.get('summary','')}\n"

        flags = result.get("flags", [])
        if flags:
            text += "\n⚠️ *Flags:*\n" + "\n".join(f"• {f}" for f in flags)

        # Telegram has 4096 char limit — truncate if needed
        if len(text) > 4000:
            text = text[:3990] + "\n…[truncated]"

        await msg.edit_text(text, parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Analysis error: {e}")


# ─── bot startup ──────────────────────────────────────────────────────────────

def run():
    """Called by app.py background thread OR directly when run as __main__."""
    if not BOT_TOKEN:
        print("[telegram] TELEGRAM_BOT_TOKEN not set — bot disabled")
        return

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("help",      cmd_help))
    app.add_handler(CommandHandler("start",     cmd_help))
    app.add_handler(CommandHandler("dashboard", cmd_dashboard))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("data",      cmd_data))
    app.add_handler(CommandHandler("news",      cmd_news))
    app.add_handler(CommandHandler("analysis",  cmd_analysis))

    print("[telegram] bot polling…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run()
