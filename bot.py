"""
Aluminum Pro Trader – Telegram Bot
Commands: /start /report /signal /fairvalue /shanghai /lme /mcx /factors /help
Scheduled: pre-market (06:45), MCX open (09:05), LME open (13:05), MCX close (23:35)
Live signal updates every 30 min during MCX hours.
"""

import asyncio
import logging
from datetime import time as dtime

import pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import config
from fetcher import fetch_market_data
from analyzer import calculate_fair_value, generate_signal, interpret_oi
from formatter import (
    format_full_report,
    format_signal_only,
    format_pre_market,
    format_mcx_open,
    format_mcx_close,
    _chg_tag, _oi_arrow,      # small helpers reused in inline commands
)

IST    = pytz.timezone("Asia/Kolkata")
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Core data helper
# ─────────────────────────────────────────────────────────────────

async def _get_data() -> tuple[dict, dict | None, dict]:
    """Fetch + analyse in a thread-pool (non-blocking)."""
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, fetch_market_data, config.SYMBOLS)
    fv   = calculate_fair_value(data)
    sig  = generate_signal(data, fv)
    return data, fv, sig


async def _send(bot, text: str) -> None:
    """Send a message to the configured chat ID."""
    await bot.send_message(
        chat_id=config.TELEGRAM_CHAT_ID,
        text=text,
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────
# /start  /help
# ─────────────────────────────────────────────────────────────────

HELP_TEXT = """<b>🏭 ALUMINUM PRO TRADER BOT</b>

Professional MCX aluminum analysis powered by
Shanghai SHFE · LME · Fair Value · OI · Currencies · Equities

<b>Commands</b>
/report     – Full market report (all factors)
/signal     – Current BUY / SHORT / NO TRADE signal
/fairvalue  – Fair value breakdown (LME → MCX with duties)
/shanghai   – Shanghai SHFE aluminum deep-dive
/lme        – LME aluminum + base metals
/mcx        – MCX aluminum + India factors
/factors    – All macro factors with interpretation

<b>Auto Reports (IST)</b>
06:45 – Pre-market brief (before Shanghai open)
09:05 – MCX market open signal
13:05 – LME ring open update
23:35 – MCX close summary

Plus live signal update every 30 min during MCX hours.
<i>⚠️ Educational only. Not financial advice.</i>"""


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────
# /report
# ─────────────────────────────────────────────────────────────────

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("⏳ Fetching all markets…")
    data, fv, sig = await _get_data()
    await update.message.reply_text(format_full_report(data, fv, sig), parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────
# /signal
# ─────────────────────────────────────────────────────────────────

async def cmd_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data, fv, sig = await _get_data()
    await update.message.reply_text(format_signal_only(data, fv, sig), parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────
# /fairvalue
# ─────────────────────────────────────────────────────────────────

async def cmd_fairvalue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data, fv, _ = await _get_data()
    if not fv:
        await update.message.reply_text("❌ Fair value unavailable – LME or USD/INR data missing.")
        return

    lines = [
        "<b>📊 MCX ALUMINUM FAIR VALUE — STEP BY STEP</b>",
        "",
        "<b>Step 1 – LME Price + Physical Premium</b>",
        f"  LME (COMEX proxy): ${fv['lme_usd_mt']:.2f}/MT",
        f"  + CIF premium    : ${fv['cif_premium_usd']}/MT",
        f"  = Import cost    : ${fv['cif_usd_mt']:.2f}/MT",
        "",
        "<b>Step 2 – Convert to INR</b>",
        f"  USD/INR    : {fv['usd_inr']:.2f}",
        f"  CIF (INR)  : ₹{fv['cif_inr_mt']:,.0f}/MT",
        "",
        "<b>Step 3 – India Import Duties</b>",
        f"  BCD  (7.5%) : ₹{fv['bcd_inr']:,.0f}",
        f"  SWS  (10%BCD): ₹{fv['sws_inr']:,.0f}",
        f"  IGST (18%)  : ₹{fv['igst_inr']:,.0f}",
        f"  Total duty  : ₹{fv['total_duty_inr']:,.0f}/MT",
        "",
        "<b>Step 4 – Landed Cost & Fair Value</b>",
        f"  Landed cost : ₹{fv['landed_inr_mt']:,.0f}/MT",
        f"  <b>Fair Value  : ₹{fv['fair_value_per_kg']:.2f}/kg</b>",
        "",
        f"<b>MCX Current  : ₹{fv['mcx_price']:.2f}/kg</b>",
    ]
    gap_icon = "🟢" if fv["gap_pct"] < -1 else ("🔴" if fv["gap_pct"] > 1 else "⚪")
    lines += [
        f"Gap         : {gap_icon} ₹{fv['gap_inr']:+.2f}/kg  ({fv['gap_pct']:+.2f}%)",
        "",
        "Interpretation:",
        "  Gap < -1.5% → MCX undervalued → imports would flow → BUY bias",
        "  Gap > +1.5% → MCX overvalued  → sell pressure expected  → SELL bias",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────
# /shanghai
# ─────────────────────────────────────────────────────────────────

async def cmd_shanghai(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data, fv, _ = await _get_data()
    sh      = data.get("SHFE_AL",       {})
    ao      = data.get("SHFE_ALUMINA",  {})
    sh_eq   = data.get("SHANGHAI_COMP", {})
    usd_cnh = data.get("USD_CNH",       {})

    oi_txt, _, oi_emoji = interpret_oi("SHFE_AL", data)

    lines = [
        "<b>🇨🇳 SHANGHAI ALUMINUM DEEP-DIVE</b>",
        f"Symbol: SHFE:AL1!",
        "",
        f"Price  : ¥{sh.get('close',0):,.0f}/MT  {_chg_tag(sh.get('change',0))}",
        f"Open   : ¥{sh.get('open',0):,.0f}",
        f"High   : ¥{sh.get('high',0):,.0f}",
        f"Low    : ¥{sh.get('low',0):,.0f}",
    ]
    if sh.get("VWAP"):
        diff = sh["close"] - sh["VWAP"]
        pos  = "above" if diff > 0 else "below"
        lines.append(f"VWAP   : ¥{sh['VWAP']:,.0f}  (price {pos} VWAP by ¥{abs(diff):,.0f})")
    if sh.get("open_interest"):
        lines += [
            f"OI     : {sh['open_interest']:,.0f}",
            f"OI Δ   : {_oi_arrow(sh.get('oi_change_pct', 0))}",
        ]
    lines += [
        "",
        f"<b>🏦 Institutional Activity</b>",
        f"{oi_emoji} {oi_txt}",
        "",
        "<b>OI Pattern Interpretation Guide</b>",
        "🟢 Price↑ + OI↑ = Long Buildup (real buying)",
        "🟡 Price↑ + OI↓ = Short Covering (less reliable)",
        "🔴 Price↓ + OI↑ = Short Buildup (real selling)",
        "🟠 Price↓ + OI↓ = Long Unwinding (potential bottom)",
        "",
    ]
    if ao.get("close", 0) > 0:
        lines += [
            "<b>🔩 Alumina (SHFE:AO1!) – Raw Material Cost</b>",
            f"¥{ao['close']:,.0f}/MT  {_chg_tag(ao.get('change', 0))}",
            "Impact: Alumina ≈ 30% of aluminum production cost",
            "",
        ]
    lines += [
        "<b>📈 China Market Sentiment</b>",
        f"Shanghai Composite: {sh_eq.get('close',0):,.2f}  {_chg_tag(sh_eq.get('change',0))}",
        f"USD/CNH           : {usd_cnh.get('close',0):.4f}  {_chg_tag(usd_cnh.get('change',0))}",
    ]
    if fv:
        lines += [
            "",
            f"<b>MCX Fair Value (from SHFE context): ₹{fv['fair_value_per_kg']:.2f}/kg</b>",
        ]
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────
# /lme
# ─────────────────────────────────────────────────────────────────

async def cmd_lme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data, fv, _ = await _get_data()
    lme    = data.get("LME_AL",   {})
    copper = data.get("COPPER_HG",{})
    zinc   = data.get("ZINC_LME", {})
    nickel = data.get("NICKEL_LME",{})
    lead   = data.get("LEAD_LME", {})
    crude  = data.get("CRUDE_WTI",{})
    dxy    = data.get("DXY",      {})

    oi_txt, _, oi_emoji = interpret_oi("LME_AL", data)

    lines = [
        "<b>🌐 LME ALUMINUM ANALYSIS</b>",
        "Symbol: COMEX:ALI1! (best LME proxy)",
        "",
        f"Price  : ${lme.get('close',0):,.2f}/MT  {_chg_tag(lme.get('change',0))}",
        f"Open   : ${lme.get('open',0):,.2f}",
        f"High   : ${lme.get('high',0):,.2f}",
        f"Low    : ${lme.get('low',0):,.2f}",
    ]
    if lme.get("VWAP"):
        lines.append(f"VWAP   : ${lme['VWAP']:,.2f}")
    if lme.get("open_interest"):
        lines += [
            f"OI     : {lme['open_interest']:,.0f}",
            f"OI Δ   : {_oi_arrow(lme.get('oi_change_pct',0))}",
        ]
    lines += [
        "",
        f"<b>🏦 Institutional Activity</b>",
        f"{oi_emoji} {oi_txt}",
        "",
    ]
    if fv:
        gap_icon = "🟢" if fv["gap_pct"] < 0 else "🔴"
        lines += [
            "<b>📊 MCX Fair Value from LME</b>",
            f"LME → MCX Fair Value: ₹{fv['fair_value_per_kg']:.2f}/kg",
            f"MCX Current        : ₹{fv['mcx_price']:.2f}/kg",
            f"Gap                : {gap_icon} {fv['gap_pct']:+.2f}%",
            "",
        ]
    lines += [
        "<b>🔩 Base Metals Complex</b>",
        f"Copper (leader) : ${copper.get('close',0):.4f}/lb  {_chg_tag(copper.get('change',0))}",
        f"Zinc            : ${zinc.get('close',0):,.0f}/MT  {_chg_tag(zinc.get('change',0))}",
        f"Nickel          : ${nickel.get('close',0):,.0f}/MT  {_chg_tag(nickel.get('change',0))}",
        f"Lead            : ${lead.get('close',0):,.0f}/MT  {_chg_tag(lead.get('change',0))}",
        "",
        "<b>⚡ Macro</b>",
        f"Crude WTI : ${crude.get('close',0):.2f}  {_chg_tag(crude.get('change',0))}",
        f"DXY       : {dxy.get('close',0):.2f}  {_chg_tag(dxy.get('change',0))}",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────
# /mcx
# ─────────────────────────────────────────────────────────────────

async def cmd_mcx(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data, fv, sig = await _get_data()
    mcx      = data.get("MCX_AL",    {})
    usd_inr  = data.get("USD_INR",   {})
    crude_mcx= data.get("CRUDE_MCX", {})
    crude_wti= data.get("CRUDE_WTI", {})
    nifty    = data.get("NIFTY",     {})
    sensex   = data.get("SENSEX",    {})

    oi_txt, _, oi_emoji = interpret_oi("MCX_AL", data)

    lines = [
        "<b>🇮🇳 MCX ALUMINUM DEEP-DIVE</b>",
        "Symbol: MCX:ALUMINIUM1!",
        "",
        f"Price  : ₹{mcx.get('close',0):.2f}/kg  {_chg_tag(mcx.get('change',0))}",
        f"Open   : ₹{mcx.get('open',0):.2f}",
        f"High   : ₹{mcx.get('high',0):.2f}",
        f"Low    : ₹{mcx.get('low',0):.2f}",
    ]
    if mcx.get("VWAP"):
        diff = mcx["close"] - mcx["VWAP"]
        pos  = "above" if diff > 0 else "below"
        lines.append(f"VWAP   : ₹{mcx['VWAP']:.2f}  (price {pos} VWAP by ₹{abs(diff):.2f})")
    if mcx.get("open_interest"):
        lines += [
            f"OI     : {mcx['open_interest']:,.0f}",
            f"OI Δ   : {_oi_arrow(mcx.get('oi_change_pct',0))}",
        ]
    lines.append(f"Volume : {mcx.get('vol_ratio',1.0):.2f}× average")
    lines += [
        "",
        f"<b>🏦 Institutional Activity</b>",
        f"{oi_emoji} {oi_txt}",
        "",
    ]
    if fv:
        gap_icon = "🟢" if fv["gap_pct"] < -1 else ("🔴" if fv["gap_pct"] > 1 else "⚪")
        lines += [
            "<b>📊 Fair Value</b>",
            f"Fair Value : ₹{fv['fair_value_per_kg']:.2f}/kg",
            f"Gap        : {gap_icon} ₹{fv['gap_inr']:+.2f}  ({fv['gap_pct']:+.2f}%)",
            "",
        ]
    lines += [
        "<b>🇮🇳 India Macro Context</b>",
        f"USD/INR    : {usd_inr.get('close',0):.2f}  {_chg_tag(usd_inr.get('change',0))}",
    ]
    if crude_mcx.get("close", 0) > 0:
        lines.append(f"MCX Crude  : ₹{crude_mcx['close']:,.2f}  {_chg_tag(crude_mcx.get('change',0))}")
    else:
        lines.append(f"Crude WTI  : ${crude_wti.get('close',0):.2f}  {_chg_tag(crude_wti.get('change',0))}")
    lines += [
        f"Nifty 50   : {nifty.get('close',0):,.2f}  {_chg_tag(nifty.get('change',0))}",
        f"Sensex     : {sensex.get('close',0):,.2f}  {_chg_tag(sensex.get('change',0))}",
        "",
        f"<b>🎯 Signal: {sig.get('signal','NO TRADE')}</b>  (Score: {sig.get('score',0):+d})",
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────
# /factors
# ─────────────────────────────────────────────────────────────────

async def cmd_factors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data, _, _ = await _get_data()

    usd_inr  = data.get("USD_INR",       {})
    usd_cnh  = data.get("USD_CNH",       {})
    dxy      = data.get("DXY",           {})
    crude    = data.get("CRUDE_WTI",     {})
    copper   = data.get("COPPER_HG",     {})
    zinc     = data.get("ZINC_LME",      {})
    nickel   = data.get("NICKEL_LME",    {})
    lead     = data.get("LEAD_LME",      {})
    alumina  = data.get("SHFE_ALUMINA",  {})
    nifty    = data.get("NIFTY",         {})
    sensex   = data.get("SENSEX",        {})
    sh_comp  = data.get("SHANGHAI_COMP", {})

    lines = ["<b>⚡ ALL FACTORS AFFECTING MCX ALUMINUM</b>", ""]

    # Currency
    inr_c  = usd_inr.get("change", 0)
    dxy_c  = dxy.get("change", 0)
    lines += [
        "<b>💱 CURRENCY IMPACT</b>",
        f"USD/INR : {usd_inr.get('close',0):.2f}  {_chg_tag(inr_c)}",
    ]
    if inr_c > 0.2:
        lines.append("  ↳ 🟢 Rupee weakening → imports costlier → MCX bullish")
    elif inr_c < -0.2:
        lines.append("  ↳ 🔴 Rupee strengthening → imports cheaper → MCX bearish")
    lines.append(f"USD/CNH : {usd_cnh.get('close',0):.4f}  {_chg_tag(usd_cnh.get('change',0))}")
    lines.append(f"DXY     : {dxy.get('close',0):.2f}  {_chg_tag(dxy_c)}")
    if dxy_c > 0.3:
        lines.append("  ↳ 🔴 Strong dollar → global metal price headwind")
    elif dxy_c < -0.3:
        lines.append("  ↳ 🟢 Weak dollar → global metal price support")
    lines.append("")

    # Energy
    crude_c = crude.get("change", 0)
    lines += [
        "<b>⛽ ENERGY COST  (smelting ≈ 30-40% of aluminum cost)</b>",
        f"WTI Crude: ${crude.get('close',0):.2f}  {_chg_tag(crude_c)}",
    ]
    if crude_c > 1.0:
        lines.append("  ↳ 🟢 Higher energy cost → production cost up → aluminum support")
    elif crude_c < -1.0:
        lines.append("  ↳ 🔴 Lower energy → margin pressure on smelters")
    lines.append("")

    # Base metals
    cu_c = copper.get("change", 0)
    lines += [
        "<b>🔩 BASE METALS COMPLEX</b>",
        f"Copper (best indicator): ${copper.get('close',0):.4f}/lb  {_chg_tag(cu_c)}",
    ]
    if cu_c > 0.5:
        lines.append("  ↳ 🟢 Copper leading metals complex higher")
    elif cu_c < -0.5:
        lines.append("  ↳ 🔴 Copper pulling metals complex lower")
    lines += [
        f"Zinc   : ${zinc.get('close',0):,.0f}/MT  {_chg_tag(zinc.get('change',0))}",
        f"Nickel : ${nickel.get('close',0):,.0f}/MT  {_chg_tag(nickel.get('change',0))}",
        f"Lead   : ${lead.get('close',0):,.0f}/MT  {_chg_tag(lead.get('change',0))}",
    ]
    if alumina.get("close", 0) > 0:
        ao_c = alumina.get("change", 0)
        lines.append(f"Alumina: ¥{alumina['close']:,.0f}/MT  {_chg_tag(ao_c)}")
        if ao_c > 1.0:
            lines.append("  ↳ 🟢 Alumina rising → aluminum production cost up → bullish")
        elif ao_c < -1.0:
            lines.append("  ↳ 🔴 Alumina falling → production cost easing")
    lines.append("")

    # Equities
    sh_c = sh_comp.get("change", 0)
    lines += [
        "<b>📈 EQUITY MARKETS (risk appetite & demand)</b>",
        f"Nifty 50  : {nifty.get('close',0):,.2f}  {_chg_tag(nifty.get('change',0))}",
        f"Sensex    : {sensex.get('close',0):,.2f}  {_chg_tag(sensex.get('change',0))}",
        f"Shanghai  : {sh_comp.get('close',0):,.2f}  {_chg_tag(sh_c)}",
    ]
    if sh_c > 0.5:
        lines.append("  ↳ 🟢 China market up → demand optimism → metals positive")
    elif sh_c < -0.5:
        lines.append("  ↳ 🔴 China market down → demand concerns → metals negative")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────
# Scheduled Job Callbacks
# ─────────────────────────────────────────────────────────────────

async def _job_pre_market(context: ContextTypes.DEFAULT_TYPE) -> None:
    data, fv, _ = await _get_data()
    await _send(context.bot, format_pre_market(data, fv))


async def _job_mcx_open(context: ContextTypes.DEFAULT_TYPE) -> None:
    data, fv, sig = await _get_data()
    await _send(context.bot, format_mcx_open(data, fv, sig))


async def _job_lme_open(context: ContextTypes.DEFAULT_TYPE) -> None:
    data, fv, sig = await _get_data()
    await _send(context.bot, format_full_report(data, fv, sig))


async def _job_mcx_close(context: ContextTypes.DEFAULT_TYPE) -> None:
    data, fv, sig = await _get_data()
    await _send(context.bot, format_mcx_close(data, fv, sig))


async def _job_live_signal(context: ContextTypes.DEFAULT_TYPE) -> None:
    data, fv, sig = await _get_data()
    await _send(context.bot, format_signal_only(data, fv, sig))


# ─────────────────────────────────────────────────────────────────
# Bot Main
# ─────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        format="%(asctime)s  %(levelname)-8s  %(name)s – %(message)s",
        level=logging.INFO,
    )

    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Register command handlers
    for cmd, fn in [
        ("start",     cmd_start),
        ("help",      cmd_help),
        ("report",    cmd_report),
        ("signal",    cmd_signal),
        ("fairvalue", cmd_fairvalue),
        ("shanghai",  cmd_shanghai),
        ("lme",       cmd_lme),
        ("mcx",       cmd_mcx),
        ("factors",   cmd_factors),
    ]:
        app.add_handler(CommandHandler(cmd, fn))

    # Scheduled jobs (IST timezone-aware)
    jq = app.job_queue
    jq.run_daily(_job_pre_market,  dtime(config.REPORT_PRE_MARKET_H,  config.REPORT_PRE_MARKET_M,  tzinfo=IST))
    jq.run_daily(_job_mcx_open,    dtime(config.REPORT_MCX_OPEN_H,    config.REPORT_MCX_OPEN_M,    tzinfo=IST))
    jq.run_daily(_job_lme_open,    dtime(config.REPORT_LME_OPEN_H,    config.REPORT_LME_OPEN_M,    tzinfo=IST))
    jq.run_daily(_job_mcx_close,   dtime(config.REPORT_MCX_CLOSE_H,   config.REPORT_MCX_CLOSE_M,   tzinfo=IST))

    # Live signal every 30 min, first run after 60 s so bot is warmed up
    jq.run_repeating(_job_live_signal,
                     interval=config.UPDATE_INTERVAL_MIN * 60,
                     first=60)

    logger.info("🏭 Aluminum Pro Trader Bot starting (polling)…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
