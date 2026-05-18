"""
Telegram message formatter.
Builds professional HTML-formatted messages for all report types.
"""

from datetime import datetime
import pytz
from analyzer import interpret_oi

IST = pytz.timezone("Asia/Kolkata")


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(IST).strftime("%d %b %Y  %H:%M IST")


def _chg_tag(val: float, unit: str = "%") -> str:
    """Green / red emoji + value."""
    if val > 0:
        return f"🟢 +{val:.2f}{unit}"
    if val < 0:
        return f"🔴 {val:.2f}{unit}"
    return f"⚪ {val:.2f}{unit}"


def _oi_arrow(pct: float) -> str:
    if pct > 0:
        return f"↑ +{pct:.2f}%"
    if pct < 0:
        return f"↓ {pct:.2f}%"
    return f"→ flat"


def _sig_emoji(signal: str) -> str:
    return {
        "BUY"         : "🟢",
        "STRONG BUY"  : "🟢🟢",
        "SHORT"       : "🔴",
        "STRONG SHORT": "🔴🔴",
        "NO TRADE"    : "⚪",
    }.get(signal, "⚪")


# ─────────────────────────────────────────────────────────────────
# FULL REPORT  (/report)
# ─────────────────────────────────────────────────────────────────

def format_full_report(data: dict, fv: dict | None, signal_result: dict) -> str:
    sig       = signal_result.get("signal", "NO TRADE")
    score     = signal_result.get("score", 0)
    bullish   = signal_result.get("bullish_factors", [])
    bearish   = signal_result.get("bearish_factors", [])
    sig_icon  = _sig_emoji(sig)

    lines = [
        f"<b>🏭 ALUMINUM PRO — FULL REPORT</b>",
        f"<b>{_now()}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"<b>🎯 SIGNAL: {sig_icon} {sig}</b>",
        f"Score {score:+d}  |  {len(bullish)} bullish / {len(bearish)} bearish factors",
        "",
    ]

    # ── Fair Value ────────────────────────────────────────────────
    if fv:
        gap_icon = "🟢" if fv["gap_pct"] < -1 else ("🔴" if fv["gap_pct"] > 1 else "⚪")
        lines += [
            "<b>📊 FAIR VALUE (LME → MCX)</b>",
            f"LME price  : ${fv['lme_usd_mt']:.0f}/MT",
            f"+ CIF prem : ${fv['cif_premium_usd']}/MT",
            f"× USD/INR  : {fv['usd_inr']:.2f}",
            f"+ Duties   : ₹{fv['total_duty_inr']:,.0f}/MT  (BCD+SWS+IGST)",
            f"→ <b>Fair Value : ₹{fv['fair_value_per_kg']:.2f}/kg</b>",
            f"MCX Current: ₹{fv['mcx_price']:.2f}/kg",
            f"Gap        : {gap_icon} ₹{fv['gap_inr']:+.2f}  ({fv['gap_pct']:+.2f}%)",
            "",
        ]

    # ── Shanghai ──────────────────────────────────────────────────
    sh  = data.get("SHFE_AL", {})
    sh_oi_txt, _, sh_oi_emoji = interpret_oi("SHFE_AL", data)
    lines += [
        "<b>🇨🇳 SHANGHAI ALUMINUM  SHFE:AL1!</b>",
        f"Price : ¥{sh.get('close',0):,.0f}/MT  {_chg_tag(sh.get('change',0))}",
        f"O ¥{sh.get('open',0):,.0f}  H ¥{sh.get('high',0):,.0f}  L ¥{sh.get('low',0):,.0f}",
    ]
    if sh.get("VWAP"):
        diff = sh["close"] - sh["VWAP"]
        pos  = "above" if diff > 0 else "below"
        lines.append(f"VWAP: ¥{sh['VWAP']:,.0f}  (price {pos} by ¥{abs(diff):,.0f})")
    if sh.get("open_interest"):
        lines.append(f"OI: {sh['open_interest']:,.0f}  {_oi_arrow(sh.get('oi_change_pct',0))}")
    lines += [f"🏦 {sh_oi_emoji} {sh_oi_txt}", ""]

    # ── LME ───────────────────────────────────────────────────────
    lme = data.get("LME_AL", {})
    lme_oi_txt, _, lme_oi_emoji = interpret_oi("LME_AL", data)
    lines += [
        "<b>🌐 LME ALUMINUM  COMEX:ALI1!</b>",
        f"Price : ${lme.get('close',0):,.2f}/MT  {_chg_tag(lme.get('change',0))}",
        f"O ${lme.get('open',0):,.2f}  H ${lme.get('high',0):,.2f}  L ${lme.get('low',0):,.2f}",
    ]
    if lme.get("VWAP"):
        lines.append(f"VWAP: ${lme['VWAP']:,.2f}")
    if lme.get("open_interest"):
        lines.append(f"OI: {lme['open_interest']:,.0f}  {_oi_arrow(lme.get('oi_change_pct',0))}")
    lines += [f"🏦 {lme_oi_emoji} {lme_oi_txt}", ""]

    # ── MCX ───────────────────────────────────────────────────────
    mcx = data.get("MCX_AL", {})
    mcx_oi_txt, _, mcx_oi_emoji = interpret_oi("MCX_AL", data)
    lines += [
        "<b>🇮🇳 MCX ALUMINUM  ALUMINIUM1!</b>",
        f"Price : ₹{mcx.get('close',0):.2f}/kg  {_chg_tag(mcx.get('change',0))}",
        f"O ₹{mcx.get('open',0):.2f}  H ₹{mcx.get('high',0):.2f}  L ₹{mcx.get('low',0):.2f}",
    ]
    if mcx.get("VWAP"):
        diff = mcx["close"] - mcx["VWAP"]
        pos  = "above" if diff > 0 else "below"
        lines.append(f"VWAP: ₹{mcx['VWAP']:.2f}  (price {pos} by ₹{abs(diff):.2f})")
    if mcx.get("open_interest"):
        lines.append(f"OI: {mcx['open_interest']:,.0f}  {_oi_arrow(mcx.get('oi_change_pct',0))}")
    lines.append(f"Volume: {mcx.get('vol_ratio',1.0):.2f}× avg")
    lines += [f"🏦 {mcx_oi_emoji} {mcx_oi_txt}", ""]

    # ── Currencies ────────────────────────────────────────────────
    usd_inr  = data.get("USD_INR",  {})
    usd_cnh  = data.get("USD_CNH",  {})
    dxy      = data.get("DXY",      {})
    lines += [
        "<b>💱 CURRENCIES</b>",
        f"USD/INR : {usd_inr.get('close',0):.2f}  {_chg_tag(usd_inr.get('change',0))}",
        f"USD/CNH : {usd_cnh.get('close',0):.4f}  {_chg_tag(usd_cnh.get('change',0))}",
        f"DXY     : {dxy.get('close',0):.2f}  {_chg_tag(dxy.get('change',0))}",
        "",
    ]

    # ── Factors ───────────────────────────────────────────────────
    crude  = data.get("CRUDE_WTI",   {})
    copper = data.get("COPPER_HG",   {})
    zinc   = data.get("ZINC_LME",    {})
    nickel = data.get("NICKEL_LME",  {})
    lead   = data.get("LEAD_LME",    {})
    alumina= data.get("SHFE_ALUMINA",{})
    lines += [
        "<b>⚡ KEY FACTORS</b>",
        f"Crude WTI : ${crude.get('close',0):.2f}    {_chg_tag(crude.get('change',0))}",
        f"Copper    : ${copper.get('close',0):.4f}  {_chg_tag(copper.get('change',0))}",
        f"Zinc      : ${zinc.get('close',0):,.0f}/MT  {_chg_tag(zinc.get('change',0))}",
        f"Nickel    : ${nickel.get('close',0):,.0f}/MT  {_chg_tag(nickel.get('change',0))}",
        f"Lead      : ${lead.get('close',0):,.0f}/MT  {_chg_tag(lead.get('change',0))}",
    ]
    if alumina.get("close", 0) > 0:
        lines.append(f"Alumina   : ¥{alumina['close']:,.0f}/MT  {_chg_tag(alumina.get('change',0))}")
    lines.append("")

    # ── Equities ──────────────────────────────────────────────────
    nifty   = data.get("NIFTY",        {})
    sensex  = data.get("SENSEX",       {})
    sh_comp = data.get("SHANGHAI_COMP",{})
    lines += [
        "<b>📈 EQUITY INDICES</b>",
        f"Nifty 50  : {nifty.get('close',0):,.2f}  {_chg_tag(nifty.get('change',0))}",
        f"Sensex    : {sensex.get('close',0):,.2f}  {_chg_tag(sensex.get('change',0))}",
        f"Shanghai  : {sh_comp.get('close',0):,.2f}  {_chg_tag(sh_comp.get('change',0))}",
        "",
    ]

    # ── Signal Reasoning ──────────────────────────────────────────
    if bullish:
        lines.append("<b>🟢 BULLISH FACTORS</b>")
        lines.extend(f"• {f}" for f in bullish)
        lines.append("")
    if bearish:
        lines.append("<b>🔴 BEARISH FACTORS</b>")
        lines.extend(f"• {f}" for f in bearish)
        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "<i>⚠️ Educational only. Not financial advice.</i>",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
# SIGNAL ONLY  (/signal and interval updates)
# ─────────────────────────────────────────────────────────────────

def format_signal_only(data: dict, fv: dict | None, signal_result: dict) -> str:
    sig      = signal_result.get("signal", "NO TRADE")
    score    = signal_result.get("score", 0)
    bullish  = signal_result.get("bullish_factors", [])
    bearish  = signal_result.get("bearish_factors", [])
    sig_icon = _sig_emoji(sig)

    lines = [
        f"<b>🎯 SIGNAL UPDATE — {_now()}</b>",
        f"<b>{sig_icon} {sig}</b>  (Score: {score:+d})",
        "",
    ]

    if fv:
        gap_icon = "🟢" if fv["gap_pct"] < -1 else ("🔴" if fv["gap_pct"] > 1 else "⚪")
        lines += [
            f"MCX: ₹{fv['mcx_price']:.2f}  |  Fair Value: ₹{fv['fair_value_per_kg']:.2f}",
            f"Gap: {gap_icon} {fv['gap_pct']:+.2f}%",
            "",
        ]

    mcx = data.get("MCX_AL", {})
    sh  = data.get("SHFE_AL", {})
    lme = data.get("LME_AL", {})
    lines += [
        f"Shanghai : ¥{sh.get('close',0):,.0f}  {_chg_tag(sh.get('change',0))}",
        f"LME      : ${lme.get('close',0):,.2f}  {_chg_tag(lme.get('change',0))}",
        f"MCX      : ₹{mcx.get('close',0):.2f}  {_chg_tag(mcx.get('change',0))}",
        "",
    ]

    all_factors = [(f, "🟢") for f in bullish] + [(f, "🔴") for f in bearish]
    if all_factors:
        lines.append("<b>Top Reasons:</b>")
        for f, icon in all_factors[:6]:
            lines.append(f"{icon} {f}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
# PRE-MARKET BRIEFING  (06:45 IST – before Shanghai opens)
# ─────────────────────────────────────────────────────────────────

def format_pre_market(data: dict, fv: dict | None) -> str:
    lines = [
        "<b>🌅 PRE-MARKET BRIEFING</b>",
        f"<b>{_now()}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "<b>🌐 Overnight LME Aluminum</b>",
    ]

    lme = data.get("LME_AL", {})
    lines += [
        f"${lme.get('close',0):,.2f}/MT  {_chg_tag(lme.get('change',0))}",
        f"O ${lme.get('open',0):,.2f}  H ${lme.get('high',0):,.2f}  L ${lme.get('low',0):,.2f}",
        "",
    ]

    sh = data.get("SHFE_AL", {})
    lines += [
        "<b>🇨🇳 Shanghai Aluminum (prev session)</b>",
        f"¥{sh.get('close',0):,.0f}/MT  {_chg_tag(sh.get('change',0))}",
        "",
    ]

    usd_inr = data.get("USD_INR", {})
    dxy     = data.get("DXY",     {})
    crude   = data.get("CRUDE_WTI",{})
    copper  = data.get("COPPER_HG",{})
    lines += [
        "<b>💱 Currencies</b>",
        f"USD/INR: {usd_inr.get('close',0):.2f}  {_chg_tag(usd_inr.get('change',0))}",
        f"DXY    : {dxy.get('close',0):.2f}  {_chg_tag(dxy.get('change',0))}",
        "",
        "<b>⚡ Key Factors</b>",
        f"Crude WTI: ${crude.get('close',0):.2f}  {_chg_tag(crude.get('change',0))}",
        f"Copper   : ${copper.get('close',0):.4f}  {_chg_tag(copper.get('change',0))}",
        "",
    ]

    if fv:
        mcx_prev = data.get("MCX_AL", {}).get("close", 0)
        exp_gap  = mcx_prev - fv["fair_value_per_kg"]
        gap_icon = "🟢" if fv["gap_pct"] < -1 else ("🔴" if fv["gap_pct"] > 1 else "⚪")
        lines += [
            "<b>📊 MCX Expected at Open</b>",
            f"Fair Value   : ₹{fv['fair_value_per_kg']:.2f}/kg",
            f"Prev MCX     : ₹{mcx_prev:.2f}/kg",
            f"Expected gap : {gap_icon} ₹{exp_gap:+.2f}  ({fv['gap_pct']:+.2f}%)",
            "",
        ]

    lines += [
        "⏰ SHFE opens 06:30 IST | MCX opens 09:00 IST",
        "<i>Watch Shanghai for direction signal.</i>",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
# MCX OPEN REPORT  (09:05 IST)
# ─────────────────────────────────────────────────────────────────

def format_mcx_open(data: dict, fv: dict | None, signal_result: dict) -> str:
    sig      = signal_result.get("signal", "NO TRADE")
    score    = signal_result.get("score", 0)
    sig_icon = _sig_emoji(sig)

    mcx = data.get("MCX_AL", {})
    sh  = data.get("SHFE_AL", {})
    lme = data.get("LME_AL", {})

    lines = [
        "<b>🔔 MCX MARKET OPEN</b>",
        f"<b>{_now()}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"<b>🎯 OPENING SIGNAL: {sig_icon} {sig}</b>  (Score: {score:+d})",
        "",
        f"MCX Open  : ₹{mcx.get('open',0):.2f}/kg",
        f"MCX Prev  : ₹{mcx.get('close',0):.2f}/kg  {_chg_tag(mcx.get('change',0))}",
    ]
    if fv:
        gap_icon = "🟢" if fv["gap_pct"] < -1 else ("🔴" if fv["gap_pct"] > 1 else "⚪")
        lines += [
            f"Fair Value: ₹{fv['fair_value_per_kg']:.2f}/kg",
            f"Gap       : {gap_icon} {fv['gap_pct']:+.2f}%",
        ]
    lines += [
        "",
        f"Shanghai  : ¥{sh.get('close',0):,.0f}  {_chg_tag(sh.get('change',0))}",
        f"LME       : ${lme.get('close',0):,.2f}  {_chg_tag(lme.get('change',0))}",
    ]

    bullish = signal_result.get("bullish_factors", [])
    bearish = signal_result.get("bearish_factors", [])
    all_factors = [(f, "🟢") for f in bullish[:3]] + [(f, "🔴") for f in bearish[:3]]
    if all_factors:
        lines.append("")
        lines.append("<b>Key Reasons:</b>")
        for f, icon in all_factors:
            lines.append(f"{icon} {f}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
# MCX CLOSE REPORT  (23:35 IST)
# ─────────────────────────────────────────────────────────────────

def format_mcx_close(data: dict, fv: dict | None, signal_result: dict) -> str:
    mcx = data.get("MCX_AL", {})
    sh  = data.get("SHFE_AL", {})
    lme = data.get("LME_AL", {})

    lines = [
        "<b>🌙 MCX MARKET CLOSE SUMMARY</b>",
        f"<b>{_now()}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "<b>🇮🇳 MCX Aluminum Final</b>",
        f"Close : ₹{mcx.get('close',0):.2f}/kg  {_chg_tag(mcx.get('change',0))}",
        f"High  : ₹{mcx.get('high',0):.2f}  |  Low: ₹{mcx.get('low',0):.2f}",
    ]
    if mcx.get("VWAP"):
        lines.append(f"VWAP  : ₹{mcx['VWAP']:.2f}")
    if mcx.get("open_interest"):
        lines.append(f"OI    : {mcx['open_interest']:,.0f}  {_oi_arrow(mcx.get('oi_change_pct',0))}")
    lines += [
        "",
        "<b>Global Reference for Tomorrow</b>",
        f"Shanghai: ¥{sh.get('close',0):,.0f}  {_chg_tag(sh.get('change',0))}",
        f"LME     : ${lme.get('close',0):,.2f}  {_chg_tag(lme.get('change',0))}",
    ]
    if fv:
        gap_icon = "🟢" if fv["gap_pct"] < -1 else ("🔴" if fv["gap_pct"] > 1 else "⚪")
        lines += [
            "",
            f"<b>📊 Fair Value: ₹{fv['fair_value_per_kg']:.2f}/kg</b>",
            f"Gap: {gap_icon} {fv['gap_pct']:+.2f}%  (tomorrow's opening bias)",
        ]
    lines += [
        "",
        "⏰ Shanghai opens 06:30 IST tomorrow",
        "<i>⚠️ Educational only. Not financial advice.</i>",
    ]
    return "\n".join(lines)
