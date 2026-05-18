#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║       ALUMINUM PRO TRADER — LIVE LEARNING SYSTEM  v2.0          ║
╠══════════════════════════════════════════════════════════════════╣
║  INSTALL:  pip3 install requests pytz "python-telegram-bot[job-queue]"
║  RUN:      python3 aluminum_pro.py                               ║
║  KEEP ALIVE: screen -S jarvis  →  run  →  Ctrl+A D to detach    ║
╠══════════════════════════════════════════════════════════════════╣
║  Data: TradingView scanner (no API key needed)                   ║
║  Tracks: SHFE · LME · MCX · metals · crude · FX · equity        ║
║  Features: VWAP · OI · RSI · EMA · Bollinger · Fair Value       ║
║            14-factor weighted signal · self-learning engine      ║
║  Commands: /report /signal /fairvalue /shanghai /lme /mcx       ║
║            /factors /history /learn /help                        ║
║  Auto-reports: 06:45 / 09:05 / 13:05 / 23:35 IST + 30-min live ║
╚══════════════════════════════════════════════════════════════════╝
"""

# ─────────────────────────────────────────────────────────────────
import os, sys, json, logging, asyncio, statistics
from datetime import datetime, date
from datetime import time as dtime
from collections import deque, defaultdict
from pathlib import Path

import requests, pytz
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ═════════════════════════════════════════════════════════════════
# § 1  CONFIG  ← only edit these two
# ═════════════════════════════════════════════════════════════════

BOT_TOKEN = "8459666504:AAFu7gYcUq2UlwV6OIMNZCscHGZ0DAnhBes"
CHAT_ID   = "1047128404"

IST      = pytz.timezone("Asia/Kolkata")
DATA_DIR = Path("jarvis_data")
DATA_DIR.mkdir(exist_ok=True)

# ═════════════════════════════════════════════════════════════════
# § 2  SYMBOLS  (TradingView EXCHANGE:SYMBOL)
# ═════════════════════════════════════════════════════════════════

SYMBOLS = {
    # ── Primary aluminum ─────────────────────────────────────────
    "SHFE_AL"      : "SHFE:AL1!",        # Shanghai Futures Exchange
    "LME_AL"       : "COMEX:ALI1!",      # COMEX ALI = best LME proxy
    "MCX_AL"       : "MCX:ALUMINIUM1!",  # MCX India

    # ── Raw material ─────────────────────────────────────────────
    "SHFE_ALUMINA" : "SHFE:AO1!",        # Alumina (~30% of Al cost)

    # ── Currencies ───────────────────────────────────────────────
    "USD_INR"      : "FX:USDINR",
    "USD_CNH"      : "FX:USDCNH",
    "DXY"          : "TVC:DXY",

    # ── Energy (~35% of smelting cost) ───────────────────────────
    "CRUDE_WTI"    : "NYMEX:CL1!",
    "CRUDE_MCX"    : "MCX:CRUDEOIL1!",

    # ── Base metals complex ───────────────────────────────────────
    "COPPER_HG"    : "COMEX:HG1!",       # Best leading indicator
    "ZINC_LME"     : "LME:ZINC",
    "NICKEL_LME"   : "LME:NICKEL",
    "LEAD_LME"     : "LME:LEAD",

    # ── Equity indices ───────────────────────────────────────────
    "NIFTY"        : "NSE:NIFTY50",
    "SENSEX"       : "BSE:SENSEX",
    "SHANGHAI_COMP": "SSE:000001",
}

# TradingView scanner columns (all fetched in one HTTP request)
TV_COLS = [
    "close", "open", "high", "low",
    "volume", "change", "change_abs",
    "open_interest",    # OI (futures)
    "VWAP",             # Session VWAP
    "RSI",              # RSI(14)
    "Recommend.All",    # Overall TV rec  (-1 sell → +1 buy)
    "ADX",              # Trend strength 0-100
    "EMA20",            # 20-period EMA
    "EMA50",            # 50-period EMA
    "BB.upper",         # Bollinger upper
    "BB.lower",         # Bollinger lower
    "Mom",              # Momentum
]

TV_URL = "https://scanner.tradingview.com/global/scan"

# ═════════════════════════════════════════════════════════════════
# § 3  INDIA IMPORT DUTY STRUCTURE  (FY 2025-26)
# ═════════════════════════════════════════════════════════════════

CIF_PREMIUM_USD_MT = 310    # Physical delivery + freight + insurance
BCD_RATE           = 0.075  # Basic Customs Duty 7.5%
SWS_RATE           = 0.10   # Social Welfare Surcharge (10% of BCD)
IGST_RATE_         = 0.18   # IGST 18%

# ═════════════════════════════════════════════════════════════════
# § 4  LEARNING ENGINE  (settings + history stored as JSON)
# ═════════════════════════════════════════════════════════════════

SETTINGS_FILE = DATA_DIR / "settings.json"
HISTORY_FILE  = DATA_DIR / "history.json"
SIGNALS_FILE  = DATA_DIR / "signals.json"

# Default factor weights & thresholds — system adapts these over time
_DEFAULTS = {
    # Signal thresholds
    "fv_buy_pct"    : -1.5,   # MCX < FV by 1.5% = bullish factor
    "fv_sell_pct"   :  1.5,   # MCX > FV by 1.5% = bearish factor
    "bullish_min"   :  4.0,   # weighted score for BUY
    "bearish_min"   :  4.0,   # weighted score for SHORT
    "strong_min"    :  7.0,   # score for STRONG BUY/SHORT
    "vol_surge"     :  1.5,   # volume ratio for surge detection
    "oi_sig_pct"    :  2.0,   # OI % change considered significant
    # Factor weights (higher = more influence on signal)
    "w_fair_value"  : 2.0,    # most important
    "w_lme"         : 1.0,
    "w_shfe"        : 1.0,
    "w_usd_inr"     : 0.8,
    "w_dxy"         : 0.8,
    "w_copper"      : 1.2,    # copper leads base metals
    "w_crude"       : 0.7,
    "w_shanghai_eq" : 0.9,
    "w_alumina"     : 0.8,
    "w_metals"      : 0.6,
    "w_mcx_oi"      : 1.5,    # OI = institutional money
    "w_shfe_oi"     : 1.2,
    "w_mcx_vol"     : 1.0,
    "w_nifty"       : 0.5,
}


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            return {**_DEFAULTS, **json.loads(SETTINGS_FILE.read_text())}
        except Exception:
            pass
    return dict(_DEFAULTS)


def save_settings(s: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(s, indent=2))


def load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            pass
    return []


def append_history(rec: dict) -> None:
    h = load_history()
    h.append(rec)
    HISTORY_FILE.write_text(json.dumps(h[-365:], indent=2))


def load_signals() -> list:
    if SIGNALS_FILE.exists():
        try:
            return json.loads(SIGNALS_FILE.read_text())
        except Exception:
            pass
    return []


def _write_signals(sigs: list) -> None:
    SIGNALS_FILE.write_text(json.dumps(sigs[-1000:], indent=2))


def record_signal(sig: dict, fv_price: float, mcx_price: float) -> None:
    sigs = load_signals()
    sigs.append({
        "ts"            : datetime.now(IST).isoformat(),
        "date"          : date.today().isoformat(),
        "signal"        : sig["signal"],
        "score"         : sig["score"],
        "mcx_at_signal" : mcx_price,
        "fv_at_signal"  : fv_price,
        "active_factors": sig.get("active_factors", []),
        "outcome"       : None,
    })
    _write_signals(sigs)


def evaluate_today_signal(mcx_close: float) -> None:
    """Called at MCX close – marks morning signal as correct/wrong."""
    sigs = load_signals()
    today = date.today().isoformat()
    for i in range(len(sigs) - 1, -1, -1):
        s = sigs[i]
        if s.get("outcome") is not None:
            break
        if s.get("date") != today:
            break
        open_px = s.get("mcx_at_signal", 0)
        direction = s.get("signal", "")
        if open_px > 0 and mcx_close > 0:
            price_up = mcx_close > open_px
            if ("BUY" in direction and price_up) or ("SHORT" in direction and not price_up):
                sigs[i]["outcome"] = "correct"
            else:
                sigs[i]["outcome"] = "wrong"
        break
    _write_signals(sigs)


def auto_learn(settings: dict) -> tuple[dict, str]:
    """
    Review last 30 evaluated signals.
    Increase weight of accurate factors, decrease inaccurate ones.
    """
    sigs = [s for s in load_signals() if s.get("outcome")]
    if len(sigs) < 5:
        return settings, "Need at least 5 completed signals to learn. Keep running!"

    recent  = sigs[-30:]
    correct = sum(1 for s in recent if s["outcome"] == "correct")
    acc_pct = correct / len(recent) * 100

    # Factor accuracy
    fscores: dict = defaultdict(lambda: {"c": 0, "t": 0})
    for s in recent:
        ok = s["outcome"] == "correct"
        for f in s.get("active_factors", []):
            fscores[f]["t"] += 1
            if ok:
                fscores[f]["c"] += 1

    # Map factor_key → settings key
    wmap = {
        "fair_value": "w_fair_value", "lme": "w_lme", "shfe": "w_shfe",
        "usd_inr": "w_usd_inr",       "dxy": "w_dxy", "copper": "w_copper",
        "crude": "w_crude", "shanghai_eq": "w_shanghai_eq", "alumina": "w_alumina",
        "metals": "w_metals", "mcx_oi": "w_mcx_oi", "shfe_oi": "w_shfe_oi",
        "mcx_vol": "w_mcx_vol", "nifty": "w_nifty",
    }

    changes = []
    for fk, wk in wmap.items():
        fs = fscores.get(fk, {})
        if fs.get("t", 0) < 3:
            continue
        factor_acc = fs["c"] / fs["t"]
        old = settings.get(wk, 1.0)
        if factor_acc >= 0.65:
            new = round(min(3.0, old + 0.1), 2)
        elif factor_acc <= 0.35:
            new = round(max(0.3, old - 0.1), 2)
        else:
            continue
        if new != old:
            settings[wk] = new
            changes.append(f"  {'↑' if new>old else '↓'} {fk}: {old:.1f}→{new:.1f}  ({factor_acc*100:.0f}% acc)")

    lines = [
        f"📚 LEARNING COMPLETE",
        f"Signals reviewed: {len(recent)}",
        f"Overall accuracy: {acc_pct:.1f}%",
    ]
    if changes:
        lines += ["", "Weight adjustments:"] + changes
    else:
        lines.append("No weight changes — factors performing within expected range.")

    return settings, "\n".join(lines)


# ═════════════════════════════════════════════════════════════════
# § 5  DATA FETCHER
# ═════════════════════════════════════════════════════════════════

_vol_hist: dict = defaultdict(lambda: deque(maxlen=25))
_oi_hist:  dict = defaultdict(lambda: deque(maxlen=25))


def _f(v, default=0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def fetch_all() -> dict:
    """Single TradingView scanner request for all symbols."""
    tickers = list(SYMBOLS.values())
    rev     = {v: k for k, v in SYMBOLS.items()}

    try:
        r = requests.post(
            TV_URL,
            json={"symbols": {"tickers": tickers}, "columns": TV_COLS},
            headers={
                "Content-Type": "application/json",
                "Referer"     : "https://www.tradingview.com/",
                "User-Agent"  : "Mozilla/5.0 (X11; Linux x86_64) Chrome/120",
            },
            timeout=30,
        )
        r.raise_for_status()
        raw = r.json().get("data", [])
    except Exception as e:
        log.error("TradingView fetch failed: %s", e)
        return {}

    result: dict = {}
    for item in raw:
        ticker = item["s"]
        key    = rev.get(ticker, ticker)
        vals   = item.get("d", [])

        p: dict = {}
        for i, col in enumerate(TV_COLS):
            p[col] = _f(vals[i] if i < len(vals) else None)

        cl  = p["close"]
        vol = p["volume"]
        oi  = p["open_interest"]

        # ── Volume ratio vs rolling average ───────────────────────
        if vol > 0:
            _vol_hist[key].append(vol)
        hv = list(_vol_hist[key])
        if len(hv) >= 3:
            avg = statistics.mean(hv[:-1] or hv)
            p["vol_ratio"] = round(vol / avg if avg > 0 else 1.0, 2)
        else:
            p["vol_ratio"] = 1.0

        # ── OI change % vs previous reading ───────────────────────
        if oi > 0:
            ho = list(_oi_hist[key])
            p["oi_chg_pct"] = round((oi - ho[-1]) / ho[-1] * 100, 2) if ho else 0.0
            _oi_hist[key].append(oi)
        else:
            p["oi_chg_pct"] = 0.0

        # ── VWAP delta ────────────────────────────────────────────
        vwap = p.get("VWAP", 0)
        p["vwap_delta"] = round(cl - vwap, 4) if vwap else 0.0

        # ── EMA position ──────────────────────────────────────────
        e20 = p.get("EMA20", 0); e50 = p.get("EMA50", 0)
        p["above_ema20"] = (cl > e20) if e20 else None
        p["above_ema50"] = (cl > e50) if e50 else None

        # ── Bollinger Band % position (0=lower, 1=upper) ──────────
        bbu = p.get("BB.upper", 0); bbl = p.get("BB.lower", 0)
        p["bb_pct"] = round((cl - bbl) / (bbu - bbl), 3) if bbu > bbl > 0 else None

        p["ticker"] = ticker
        result[key] = p

    log.info("Fetched %d/%d symbols", len(result), len(SYMBOLS))
    return result


# ═════════════════════════════════════════════════════════════════
# § 6  FAIR VALUE ENGINE
# ═════════════════════════════════════════════════════════════════

def calc_fv(data: dict) -> dict | None:
    lme     = _f(data.get("LME_AL",  {}).get("close"))
    usd_inr = _f(data.get("USD_INR", {}).get("close"))
    mcx     = _f(data.get("MCX_AL",  {}).get("close"))

    if lme <= 0 or usd_inr <= 0:
        return None

    cif_usd  = lme + CIF_PREMIUM_USD_MT          # LME + physical premium ($/MT)
    cif_inr  = cif_usd * usd_inr                  # convert to INR/MT
    bcd      = cif_inr * BCD_RATE                 # Basic Customs Duty
    sws      = bcd     * SWS_RATE                 # Social Welfare Surcharge
    igst     = (cif_inr + bcd + sws) * IGST_RATE_ # IGST on assessable value
    duty     = bcd + sws + igst
    fv_kg    = (cif_inr + duty) / 1000            # INR per kg
    gap      = mcx - fv_kg
    gap_pct  = (gap / fv_kg * 100) if fv_kg > 0 else 0.0

    return {
        "lme"       : round(lme,      2),
        "cif_prem"  : CIF_PREMIUM_USD_MT,
        "cif_usd"   : round(cif_usd,  2),
        "usd_inr"   : round(usd_inr,  2),
        "cif_inr"   : round(cif_inr,  0),
        "bcd"       : round(bcd,       0),
        "sws"       : round(sws,       0),
        "igst"      : round(igst,      0),
        "duty"      : round(duty,      0),
        "fv_kg"     : round(fv_kg,     2),
        "mcx"       : round(mcx,       2),
        "gap"       : round(gap,       2),
        "gap_pct"   : round(gap_pct,   2),
    }


# ═════════════════════════════════════════════════════════════════
# § 7  OI INSTITUTIONAL ACTIVITY INTERPRETER
# ═════════════════════════════════════════════════════════════════

def read_oi(key: str, data: dict, sig_pct: float = 2.0) -> tuple[str, str, str]:
    """Returns (text, sentiment, emoji). sentiment = bullish|bearish|neutral"""
    d   = data.get(key, {})
    chg = _f(d.get("change"))
    oi  = _f(d.get("open_interest"))
    oic = _f(d.get("oi_chg_pct"))

    if oi <= 0:
        return "OI data unavailable", "neutral", "⚪"

    up = chg > 0
    if up  and oic >  sig_pct: return "LONG BUILDUP — institutional BUYING active",          "bullish", "🟢"
    if up  and oic < -sig_pct: return "SHORT COVERING — shorts exiting (weaker move)",        "neutral", "🟡"
    if not up and oic >  sig_pct: return "SHORT BUILDUP — institutional SELLING active",      "bearish", "🔴"
    if not up and oic < -sig_pct: return "LONG UNWINDING — longs exiting (watch for bottom)","neutral", "🟠"
    return "Consolidation — no clear institutional direction",                                  "neutral", "⚪"


# ═════════════════════════════════════════════════════════════════
# § 8  SIGNAL ENGINE  (weighted, self-learning)
# ═════════════════════════════════════════════════════════════════

def make_signal(data: dict, fv: dict | None, W: dict) -> dict:
    bw = 0.0; sw = 0.0          # bullish / bearish weighted scores
    bull: list[tuple[str,str]] = []   # (text, factor_key)
    bear: list[tuple[str,str]] = []

    def B(txt, key, w): nonlocal bw; bw += w; bull.append((txt, key))
    def S(txt, key, w): nonlocal sw; sw += w; bear.append((txt, key))
    def c(k): return _f(data.get(k, {}).get("change"))

    # 1. Fair Value — most important factor
    if fv:
        gp = fv["gap_pct"]; w = W.get("w_fair_value", 2.0)
        if   gp < W.get("fv_buy_pct",  -1.5): B(f"MCX {abs(gp):.1f}% BELOW Fair Value ₹{fv['fv_kg']:.2f} → undervalued", "fair_value", w)
        elif gp > W.get("fv_sell_pct",  1.5): S(f"MCX {gp:.1f}% ABOVE Fair Value ₹{fv['fv_kg']:.2f} → overvalued",        "fair_value", w)

    # 2. LME trend
    lc = c("LME_AL"); w = W.get("w_lme", 1.0)
    if   lc >  0.5: B(f"LME +{lc:.2f}%", "lme", w)
    elif lc < -0.5: S(f"LME {lc:.2f}%",  "lme", w)

    # 3. Shanghai SHFE trend
    sc = c("SHFE_AL"); w = W.get("w_shfe", 1.0)
    if   sc >  0.5: B(f"Shanghai +{sc:.2f}%", "shfe", w)
    elif sc < -0.5: S(f"Shanghai {sc:.2f}%",  "shfe", w)

    # 4. USD/INR — rising = weaker rupee = costlier imports = MCX up
    ic = c("USD_INR"); w = W.get("w_usd_inr", 0.8)
    if   ic >  0.2: B(f"INR weakening +{ic:.2f}% → import cost rises → MCX support", "usd_inr", w)
    elif ic < -0.2: S(f"INR strengthening {ic:.2f}% → import cost falls → MCX pressure", "usd_inr", w)

    # 5. DXY — strong dollar = metal headwind
    dc = c("DXY"); w = W.get("w_dxy", 0.8)
    if   dc >  0.3: S(f"DXY +{dc:.2f}% → strong dollar pressures commodities", "dxy", w)
    elif dc < -0.3: B(f"DXY {dc:.2f}% → weak dollar lifts commodities",        "dxy", w)

    # 6. Copper — best base-metal leading indicator
    cc = c("COPPER_HG"); w = W.get("w_copper", 1.2)
    if   cc >  0.5: B(f"Copper +{cc:.2f}% → base metals complex bullish", "copper", w)
    elif cc < -0.5: S(f"Copper {cc:.2f}% → base metals complex bearish",  "copper", w)

    # 7. Crude — 35% of smelting cost
    crc = c("CRUDE_WTI"); w = W.get("w_crude", 0.7)
    if   crc >  1.0: B(f"Crude +{crc:.2f}% → higher smelting cost → aluminum support", "crude", w)
    elif crc < -1.0: S(f"Crude {crc:.2f}% → lower energy cost → margin pressure",      "crude", w)

    # 8. Shanghai Composite — China demand proxy
    shc = c("SHANGHAI_COMP"); w = W.get("w_shanghai_eq", 0.9)
    if   shc >  0.5: B(f"Shanghai Composite +{shc:.2f}% → China demand positive", "shanghai_eq", w)
    elif shc < -0.5: S(f"Shanghai Composite {shc:.2f}% → China demand concern",   "shanghai_eq", w)

    # 9. Alumina — 30% of aluminum production cost
    aoc = c("SHFE_ALUMINA"); w = W.get("w_alumina", 0.8)
    if   aoc >  1.0: B(f"Alumina +{aoc:.2f}% → production cost rising → aluminum support", "alumina", w)
    elif aoc < -1.0: S(f"Alumina {aoc:.2f}% → production cost easing",                     "alumina", w)

    # 10. Metals breadth — zinc + nickel both moving same direction
    zc = c("ZINC_LME"); nc = c("NICKEL_LME"); w = W.get("w_metals", 0.6)
    if sum(1 for x in [zc,nc] if x >  0.5) == 2: B(f"Zinc+Nickel both rising → broad metals rally",    "metals", w)
    if sum(1 for x in [zc,nc] if x < -0.5) == 2: S(f"Zinc+Nickel both falling → broad metals sell-off","metals", w)

    # 11. MCX OI — institutional positioning
    mt, ms, _ = read_oi("MCX_AL",  data, W.get("oi_sig_pct", 2.0)); w = W.get("w_mcx_oi", 1.5)
    if ms == "bullish": B(f"MCX OI: {mt}",      "mcx_oi", w)
    if ms == "bearish": S(f"MCX OI: {mt}",      "mcx_oi", w)

    # 12. SHFE OI — China institutional positioning
    st, ss, _ = read_oi("SHFE_AL", data, W.get("oi_sig_pct", 2.0)); w = W.get("w_shfe_oi", 1.2)
    if ss == "bullish": B(f"Shanghai OI: {st}", "shfe_oi", w)
    if ss == "bearish": S(f"Shanghai OI: {st}", "shfe_oi", w)

    # 13. MCX volume surge — confirms institutional direction
    vr  = _f(data.get("MCX_AL", {}).get("vol_ratio"), 1.0)
    mc  = c("MCX_AL"); w = W.get("w_mcx_vol", 1.0)
    if vr >= W.get("vol_surge", 1.5):
        if   mc > 0: B(f"MCX volume {vr:.1f}× avg — institutional buying confirmed",  "mcx_vol", w)
        elif mc < 0: S(f"MCX volume {vr:.1f}× avg — institutional selling confirmed", "mcx_vol", w)

    # 14. Nifty — domestic risk appetite
    nfc = c("NIFTY"); w = W.get("w_nifty", 0.5)
    if   nfc >  0.5: B(f"Nifty +{nfc:.2f}% → positive domestic risk appetite", "nifty", w)
    elif nfc < -0.5: S(f"Nifty {nfc:.2f}% → domestic risk-off",                "nifty", w)

    score = bw - sw
    bmin = W.get("bullish_min", 4.0); bemin = W.get("bearish_min", 4.0); smin = W.get("strong_min", 7.0)

    if   score >= smin:  sig = "STRONG BUY"
    elif score >= bmin:  sig = "BUY"
    elif score <= -smin: sig = "STRONG SHORT"
    elif score <= -bemin:sig = "SHORT"
    else:                sig = "NO TRADE"

    return {
        "signal"        : sig,
        "score"         : round(score, 2),
        "bull_w"        : round(bw, 2),
        "bear_w"        : round(sw, 2),
        "bull"          : bull,   # [(text, key)]
        "bear"          : bear,
        "active_factors": [k for _,k in bull] + [k for _,k in bear],
    }


# ═════════════════════════════════════════════════════════════════
# § 9  MESSAGE FORMATTERS
# ═════════════════════════════════════════════════════════════════

def _now() -> str:
    return datetime.now(IST).strftime("%d %b %Y  %H:%M IST")

def _c(v, u="%") -> str:
    if v > 0: return f"🟢 +{v:.2f}{u}"
    if v < 0: return f"🔴 {v:.2f}{u}"
    return f"⚪ {v:.2f}{u}"

def _oi_a(p) -> str:
    if p > 0: return f"↑ +{p:.2f}%"
    if p < 0: return f"↓ {p:.2f}%"
    return "→ flat"

def _si(s) -> str:
    return {"BUY":"🟢","STRONG BUY":"🟢🟢","SHORT":"🔴","STRONG SHORT":"🔴🔴","NO TRADE":"⚪"}.get(s,"⚪")

def _vwap_ln(key, data, sym="₹", dec=2) -> str:
    d = data.get(key, {}); cl = _f(d.get("close")); vwap = _f(d.get("VWAP"))
    if not vwap: return ""
    diff = cl - vwap; pos = "above" if diff > 0 else "below"
    return f"VWAP  : {sym}{vwap:.{dec}f}  (price {pos} VWAP by {sym}{abs(diff):.{dec}f})"

def _ema_ln(key, data) -> str:
    d = data.get(key, {}); a20 = d.get("above_ema20"); a50 = d.get("above_ema50")
    if a20 is None and a50 is None: return ""
    return f"EMAs  : {'↑' if a20 else '↓'}EMA20  {'↑' if a50 else '↓'}EMA50"

def _bb_ln(key, data) -> str:
    pct = data.get(key, {}).get("bb_pct")
    if pct is None: return ""
    if pct > 0.85: z = "near UPPER band (overbought zone)"
    elif pct < 0.15: z = "near LOWER band (oversold zone)"
    else: z = f"mid-band ({pct*100:.0f}% of range)"
    return f"BB    : {z}"

def _rsi_ln(key, data) -> str:
    rsi = _f(data.get(key, {}).get("RSI"))
    if not rsi: return ""
    tag = " 🔥overbought" if rsi>70 else " 🧊oversold" if rsi<30 else ""
    return f"RSI   : {rsi:.1f}{tag}"

def _adx_ln(key, data) -> str:
    adx = _f(data.get(key, {}).get("ADX"))
    if not adx: return ""
    strength = "Strong trend" if adx>25 else "Weak/no trend"
    return f"ADX   : {adx:.1f}  ({strength})"


# ── Full report ─────────────────────────────────────────────────

def fmt_full(data: dict, fv: dict | None, sig: dict) -> str:
    s = sig["signal"]; icon = _si(s)
    bull = sig["bull"]; bear = sig["bear"]

    L = [
        "🏭 <b>ALUMINUM PRO — LIVE FULL REPORT</b>",
        f"<b>{_now()}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"🎯 <b>SIGNAL: {icon} {s}</b>",
        f"Score: {sig['score']:+.1f}  (Bull {sig['bull_w']:.1f} vs Bear {sig['bear_w']:.1f})",
        f"{len(bull)} bullish · {len(bear)} bearish factors",
        "",
    ]

    # Fair Value block
    if fv:
        gi = "🟢" if fv["gap_pct"]<-1 else ("🔴" if fv["gap_pct"]>1 else "⚪")
        L += [
            "📊 <b>FAIR VALUE (LME → MCX India)</b>",
            f"LME    : ${fv['lme']:.0f}/MT + ${fv['cif_prem']} CIF prem",
            f"× INR  : {fv['usd_inr']:.2f}  = ₹{fv['cif_inr']:,.0f}/MT",
            f"Duties : BCD ₹{fv['bcd']:,.0f} + SWS ₹{fv['sws']:,.0f} + IGST ₹{fv['igst']:,.0f}",
            f"→ <b>Fair Value : ₹{fv['fv_kg']:.2f}/kg</b>",
            f"MCX Now: ₹{fv['mcx']:.2f}/kg",
            f"Gap    : {gi} ₹{fv['gap']:+.2f}  ({fv['gap_pct']:+.2f}%)",
            "",
        ]

    # Shanghai
    sh = data.get("SHFE_AL", {})
    oi_t, _, oi_e = read_oi("SHFE_AL", data)
    L += ["🇨🇳 <b>SHANGHAI ALUMINUM  SHFE:AL1!</b>",
          f"Price : ¥{sh.get('close',0):,.0f}/MT  {_c(sh.get('change',0))}",
          f"O ¥{sh.get('open',0):,.0f}  H ¥{sh.get('high',0):,.0f}  L ¥{sh.get('low',0):,.0f}"]
    for ln in [_vwap_ln("SHFE_AL",data,"¥",0), _ema_ln("SHFE_AL",data), _rsi_ln("SHFE_AL",data)]:
        if ln: L.append(ln)
    if sh.get("open_interest"):
        L += [f"OI    : {sh['open_interest']:,.0f}  {_oi_a(sh.get('oi_chg_pct',0))}",
              f"🏦 {oi_e} {oi_t}"]
    L.append("")

    # LME
    lme = data.get("LME_AL", {})
    oi_t2, _, oi_e2 = read_oi("LME_AL", data)
    L += ["🌐 <b>LME ALUMINUM  COMEX:ALI1!</b>",
          f"Price : ${lme.get('close',0):,.2f}/MT  {_c(lme.get('change',0))}",
          f"O ${lme.get('open',0):,.2f}  H ${lme.get('high',0):,.2f}  L ${lme.get('low',0):,.2f}"]
    for ln in [_vwap_ln("LME_AL",data,"$",2), _ema_ln("LME_AL",data), _rsi_ln("LME_AL",data)]:
        if ln: L.append(ln)
    if lme.get("open_interest"):
        L += [f"OI    : {lme['open_interest']:,.0f}  {_oi_a(lme.get('oi_chg_pct',0))}",
              f"🏦 {oi_e2} {oi_t2}"]
    L.append("")

    # MCX
    mcx = data.get("MCX_AL", {})
    oi_t3, _, oi_e3 = read_oi("MCX_AL", data)
    L += ["🇮🇳 <b>MCX ALUMINUM  ALUMINIUM1!</b>",
          f"Price : ₹{mcx.get('close',0):.2f}/kg  {_c(mcx.get('change',0))}",
          f"O ₹{mcx.get('open',0):.2f}  H ₹{mcx.get('high',0):.2f}  L ₹{mcx.get('low',0):.2f}"]
    for ln in [_vwap_ln("MCX_AL",data), _ema_ln("MCX_AL",data),
               _bb_ln("MCX_AL",data),   _rsi_ln("MCX_AL",data), _adx_ln("MCX_AL",data)]:
        if ln: L.append(ln)
    if mcx.get("open_interest"):
        L += [f"OI    : {mcx['open_interest']:,.0f}  {_oi_a(mcx.get('oi_chg_pct',0))}",
              f"🏦 {oi_e3} {oi_t3}"]
    vr = mcx.get("vol_ratio", 1.0)
    L.append(f"Vol   : {vr:.2f}× avg {'📈 SURGE' if vr>=1.5 else ''}")
    L.append("")

    # Currencies
    ui=data.get("USD_INR",{}); uc=data.get("USD_CNH",{}); dy=data.get("DXY",{})
    L += ["💱 <b>CURRENCIES</b>",
          f"USD/INR : {ui.get('close',0):.2f}  {_c(ui.get('change',0))}",
          f"USD/CNH : {uc.get('close',0):.4f}  {_c(uc.get('change',0))}",
          f"DXY     : {dy.get('close',0):.2f}  {_c(dy.get('change',0))}",
          ""]

    # Factors
    cr=data.get("CRUDE_WTI",{}); cu=data.get("COPPER_HG",{})
    zn=data.get("ZINC_LME",{}); ni=data.get("NICKEL_LME",{}); ld=data.get("LEAD_LME",{})
    ao=data.get("SHFE_ALUMINA",{})
    L += ["⚡ <b>KEY FACTORS</b>",
          f"Crude WTI : ${cr.get('close',0):.2f}  {_c(cr.get('change',0))}",
          f"Copper    : ${cu.get('close',0):.4f}/lb  {_c(cu.get('change',0))}",
          f"Zinc      : ${zn.get('close',0):,.0f}/MT  {_c(zn.get('change',0))}",
          f"Nickel    : ${ni.get('close',0):,.0f}/MT  {_c(ni.get('change',0))}",
          f"Lead      : ${ld.get('close',0):,.0f}/MT  {_c(ld.get('change',0))}"]
    if ao.get("close"):
        L.append(f"Alumina   : ¥{ao['close']:,.0f}/MT  {_c(ao.get('change',0))}")
    L.append("")

    # Indices
    nf=data.get("NIFTY",{}); sx=data.get("SENSEX",{}); sh2=data.get("SHANGHAI_COMP",{})
    L += ["📈 <b>EQUITY INDICES</b>",
          f"Nifty 50  : {nf.get('close',0):,.2f}  {_c(nf.get('change',0))}",
          f"Sensex    : {sx.get('close',0):,.2f}  {_c(sx.get('change',0))}",
          f"Shanghai  : {sh2.get('close',0):,.2f}  {_c(sh2.get('change',0))}",
          ""]

    # Signal reasoning
    if bull:
        L.append("🟢 <b>BULLISH FACTORS</b>")
        L.extend(f"• {t}" for t,_ in bull)
        L.append("")
    if bear:
        L.append("🔴 <b>BEARISH FACTORS</b>")
        L.extend(f"• {t}" for t,_ in bear)
        L.append("")

    L += ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
          "<i>⚠️ Educational only. Not financial advice.</i>"]
    return "\n".join(L)


# ── Signal-only (for 30-min live updates) ───────────────────────

def fmt_signal(data: dict, fv: dict | None, sig: dict) -> str:
    s = sig["signal"]; icon = _si(s)
    L = [f"🎯 <b>LIVE SIGNAL — {_now()}</b>",
         f"<b>{icon} {s}</b>  (Score {sig['score']:+.1f})", ""]
    if fv:
        gi = "🟢" if fv["gap_pct"]<-1 else ("🔴" if fv["gap_pct"]>1 else "⚪")
        L += [f"MCX ₹{fv['mcx']:.2f}  |  FV ₹{fv['fv_kg']:.2f}",
              f"Gap {gi} {fv['gap_pct']:+.2f}%", ""]
    sh=data.get("SHFE_AL",{}); lme=data.get("LME_AL",{}); mcx=data.get("MCX_AL",{})
    L += [f"Shanghai : ¥{sh.get('close',0):,.0f}  {_c(sh.get('change',0))}",
          f"LME      : ${lme.get('close',0):,.2f}  {_c(lme.get('change',0))}",
          f"MCX      : ₹{mcx.get('close',0):.2f}  {_c(mcx.get('change',0))}", ""]
    all_f = [(t,"🟢") for t,_ in sig["bull"]] + [(t,"🔴") for t,_ in sig["bear"]]
    if all_f:
        L.append("<b>Key Reasons:</b>")
        for t,e in all_f[:6]: L.append(f"{e} {t}")
    return "\n".join(L)


def fmt_pre_market(data: dict, fv: dict | None) -> str:
    lme=data.get("LME_AL",{}); sh=data.get("SHFE_AL",{})
    ui=data.get("USD_INR",{}); dy=data.get("DXY",{}); cr=data.get("CRUDE_WTI",{}); cu=data.get("COPPER_HG",{})
    L = ["🌅 <b>PRE-MARKET BRIEFING</b>", f"<b>{_now()}</b>",
         "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "",
         "🌐 <b>Overnight LME Aluminum</b>",
         f"${lme.get('close',0):,.2f}/MT  {_c(lme.get('change',0))}",
         f"O ${lme.get('open',0):,.2f}  H ${lme.get('high',0):,.2f}  L ${lme.get('low',0):,.2f}", "",
         "🇨🇳 <b>Shanghai (last session)</b>",
         f"¥{sh.get('close',0):,.0f}/MT  {_c(sh.get('change',0))}", "",
         "💱 <b>Currencies</b>",
         f"USD/INR: {ui.get('close',0):.2f}  {_c(ui.get('change',0))}",
         f"DXY    : {dy.get('close',0):.2f}  {_c(dy.get('change',0))}", "",
         "⚡ <b>Key Factors</b>",
         f"Crude  : ${cr.get('close',0):.2f}  {_c(cr.get('change',0))}",
         f"Copper : ${cu.get('close',0):.4f}  {_c(cu.get('change',0))}", ""]
    if fv:
        mp = data.get("MCX_AL",{}).get("close",0)
        gi = "🟢" if fv["gap_pct"]<-1 else ("🔴" if fv["gap_pct"]>1 else "⚪")
        L += ["📊 <b>MCX Expected Fair Value at Open</b>",
              f"Fair Value : ₹{fv['fv_kg']:.2f}/kg",
              f"Prev MCX   : ₹{mp:.2f}/kg",
              f"Gap bias   : {gi} {fv['gap_pct']:+.2f}%", ""]
    L.append("⏰ SHFE 06:30 IST  |  MCX opens 09:00 IST")
    return "\n".join(L)


def fmt_mcx_open(data: dict, fv: dict | None, sig: dict) -> str:
    s=sig["signal"]; icon=_si(s); mcx=data.get("MCX_AL",{})
    L = ["🔔 <b>MCX MARKET OPEN</b>", f"<b>{_now()}</b>",
         "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
         f"🎯 <b>OPENING SIGNAL: {icon} {s}</b>  (Score {sig['score']:+.1f})", "",
         f"MCX Open  : ₹{mcx.get('open',0):.2f}/kg",
         f"MCX Ref   : ₹{mcx.get('close',0):.2f}/kg  {_c(mcx.get('change',0))}"]
    if fv:
        gi = "🟢" if fv["gap_pct"]<-1 else ("🔴" if fv["gap_pct"]>1 else "⚪")
        L += [f"Fair Value: ₹{fv['fv_kg']:.2f}/kg",
              f"Gap       : {gi} {fv['gap_pct']:+.2f}%"]
    vl = _vwap_ln("MCX_AL", data)
    if vl: L.append(vl)
    L.append("")
    all_f = [(t,"🟢") for t,_ in sig["bull"][:3]] + [(t,"🔴") for t,_ in sig["bear"][:3]]
    if all_f:
        L.append("<b>Key Reasons:</b>")
        for t,e in all_f: L.append(f"{e} {t}")
    return "\n".join(L)


def fmt_mcx_close(data: dict, fv: dict | None) -> str:
    mcx=data.get("MCX_AL",{}); sh=data.get("SHFE_AL",{}); lme=data.get("LME_AL",{})
    L = ["🌙 <b>MCX CLOSE SUMMARY</b>", f"<b>{_now()}</b>",
         "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", "",
         "🇮🇳 <b>MCX Aluminum Final</b>",
         f"Close : ₹{mcx.get('close',0):.2f}/kg  {_c(mcx.get('change',0))}",
         f"High  : ₹{mcx.get('high',0):.2f}  |  Low: ₹{mcx.get('low',0):.2f}"]
    for ln in [_vwap_ln("MCX_AL",data), _rsi_ln("MCX_AL",data)]:
        if ln: L.append(ln)
    if mcx.get("open_interest"):
        L.append(f"OI    : {mcx['open_interest']:,.0f}  {_oi_a(mcx.get('oi_chg_pct',0))}")
    L += ["", "🌐 <b>Tomorrow's Reference Points</b>",
          f"LME     : ${lme.get('close',0):,.2f}  {_c(lme.get('change',0))}",
          f"Shanghai: ¥{sh.get('close',0):,.0f}  {_c(sh.get('change',0))}"]
    if fv:
        gi = "🟢" if fv["gap_pct"]<-1 else ("🔴" if fv["gap_pct"]>1 else "⚪")
        L += ["", f"📊 <b>Fair Value: ₹{fv['fv_kg']:.2f}/kg</b>",
              f"Gap {gi} {fv['gap_pct']:+.2f}%  (tomorrow's opening bias)"]
    L += ["", "⏰ Shanghai opens 06:30 IST tomorrow",
          "<i>⚠️ Educational only. Not financial advice.</i>"]
    return "\n".join(L)


# ═════════════════════════════════════════════════════════════════
# § 10  TELEGRAM BOT
# ═════════════════════════════════════════════════════════════════

HELP_MSG = """🏭 <b>ALUMINUM PRO TRADER v2.0</b>
Live · Fair Value · OI · VWAP · RSI · Self-Learning

<b>Commands</b>
/report    – Full live report (all markets + signal)
/signal    – Current BUY / SHORT / NO TRADE
/fairvalue – LME → MCX fair value breakdown (step-by-step)
/shanghai  – SHFE deep-dive (OI, VWAP, RSI, alumina)
/lme       – LME aluminum + base metals complex
/mcx       – MCX aluminum + India macro factors
/factors   – All 14 factors with plain-English interpretation
/history   – Signal history, accuracy, learned weights
/learn     – Force learning update from signal history
/help      – This message

<b>Auto Reports (IST)</b>
06:45 Pre-market  |  09:05 MCX Open
13:05 LME Open    |  23:35 MCX Close
+ Live signal every 30 min

<i>⚠️ Educational only. Not financial advice.</i>"""

_S: dict = {}   # global settings (loaded in main)

log = logging.getLogger("jarvis")


async def _get() -> tuple[dict, dict | None, dict]:
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, fetch_all)
    fv   = calc_fv(data)
    sig  = make_signal(data, fv, _S)
    return data, fv, sig


async def _push(bot, text: str) -> None:
    await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="HTML")


async def cmd_start(u: Update, _c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text(HELP_MSG, parse_mode="HTML")

async def cmd_help(u: Update, _c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text(HELP_MSG, parse_mode="HTML")

async def cmd_report(u: Update, _c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text("⏳ Fetching all markets…")
    data, fv, sig = await _get()
    await u.message.reply_text(fmt_full(data, fv, sig), parse_mode="HTML")

async def cmd_signal(u: Update, _c: ContextTypes.DEFAULT_TYPE):
    data, fv, sig = await _get()
    await u.message.reply_text(fmt_signal(data, fv, sig), parse_mode="HTML")

async def cmd_fairvalue(u: Update, _c: ContextTypes.DEFAULT_TYPE):
    data, fv, _ = await _get()
    if not fv:
        await u.message.reply_text("❌ LME or USD/INR data unavailable.")
        return
    L = [
        "📊 <b>MCX FAIR VALUE — STEP BY STEP</b>", "",
        "<b>① LME Price + Physical CIF Premium</b>",
        f"  LME (COMEX proxy)  : ${fv['lme']:.2f}/MT",
        f"  + Physical CIF prem: ${fv['cif_prem']}/MT",
        f"  = Import cost      : ${fv['cif_usd']:.2f}/MT",
        "",
        "<b>② Convert to INR</b>",
        f"  USD/INR      : {fv['usd_inr']:.2f}",
        f"  CIF in INR   : ₹{fv['cif_inr']:,.0f}/MT",
        "",
        "<b>③ India Import Duties</b>",
        f"  BCD (7.5%)   : ₹{fv['bcd']:,.0f}",
        f"  SWS (10%BCD) : ₹{fv['sws']:,.0f}",
        f"  IGST (18%)   : ₹{fv['igst']:,.0f}",
        f"  Total duty   : ₹{fv['duty']:,.0f}/MT",
        "",
        "<b>④ Landed Cost → Per kg</b>",
        f"  Landed/MT    : ₹{fv['cif_inr']+fv['duty']:,.0f}",
        f"  <b>Fair Value   : ₹{fv['fv_kg']:.2f}/kg</b>",
        "",
        f"MCX Current  : ₹{fv['mcx']:.2f}/kg",
    ]
    gi = "🟢" if fv["gap_pct"]<-1 else ("🔴" if fv["gap_pct"]>1 else "⚪")
    L += [f"Gap          : {gi} ₹{fv['gap']:+.2f}  ({fv['gap_pct']:+.2f}%)", "",
          "Gap < -1.5% → MCX undervalued → BUY bias",
          "Gap > +1.5% → MCX overvalued  → SHORT bias"]
    await u.message.reply_text("\n".join(L), parse_mode="HTML")

async def cmd_shanghai(u: Update, _c: ContextTypes.DEFAULT_TYPE):
    data, fv, _ = await _get()
    sh=data.get("SHFE_AL",{}); ao=data.get("SHFE_ALUMINA",{})
    shc=data.get("SHANGHAI_COMP",{}); uc=data.get("USD_CNH",{})
    oi_t, _, oi_e = read_oi("SHFE_AL", data)
    L = ["🇨🇳 <b>SHANGHAI ALUMINUM DEEP-DIVE</b>", "",
         f"Price : ¥{sh.get('close',0):,.0f}/MT  {_c(sh.get('change',0))}",
         f"Open  : ¥{sh.get('open',0):,.0f}",
         f"High  : ¥{sh.get('high',0):,.0f}",
         f"Low   : ¥{sh.get('low',0):,.0f}"]
    for ln in [_vwap_ln("SHFE_AL",data,"¥",0), _ema_ln("SHFE_AL",data),
               _bb_ln("SHFE_AL",data), _rsi_ln("SHFE_AL",data), _adx_ln("SHFE_AL",data)]:
        if ln: L.append(ln)
    if sh.get("open_interest"):
        L += ["", f"OI    : {sh['open_interest']:,.0f}  {_oi_a(sh.get('oi_chg_pct',0))}",
              f"🏦 <b>Institutional Activity</b>", f"{oi_e} {oi_t}", "",
              "<b>OI Pattern Key</b>",
              "🟢 Price↑ + OI↑ = Long Buildup (real buying)",
              "🟡 Price↑ + OI↓ = Short Covering (weak move)",
              "🔴 Price↓ + OI↑ = Short Buildup (real selling)",
              "🟠 Price↓ + OI↓ = Long Unwinding (potential bottom)"]
    if ao.get("close"):
        L += ["", "🔩 <b>Alumina SHFE:AO1! (raw material, ~30% of Al cost)</b>",
              f"¥{ao['close']:,.0f}/MT  {_c(ao.get('change',0))}"]
    L += ["", "📈 <b>China Market Context</b>",
          f"Shanghai Composite: {shc.get('close',0):,.2f}  {_c(shc.get('change',0))}",
          f"USD/CNH           : {uc.get('close',0):.4f}  {_c(uc.get('change',0))}"]
    if fv: L += ["", f"<b>MCX Fair Value (reference): ₹{fv['fv_kg']:.2f}/kg</b>"]
    await u.message.reply_text("\n".join(L), parse_mode="HTML")

async def cmd_lme(u: Update, _c: ContextTypes.DEFAULT_TYPE):
    data, fv, _ = await _get()
    lme=data.get("LME_AL",{}); cu=data.get("COPPER_HG",{})
    zn=data.get("ZINC_LME",{}); ni=data.get("NICKEL_LME",{}); ld=data.get("LEAD_LME",{})
    cr=data.get("CRUDE_WTI",{}); dy=data.get("DXY",{})
    oi_t, _, oi_e = read_oi("LME_AL", data)
    L = ["🌐 <b>LME ALUMINUM  COMEX:ALI1!</b>", "",
         f"Price : ${lme.get('close',0):,.2f}/MT  {_c(lme.get('change',0))}",
         f"Open  : ${lme.get('open',0):,.2f}",
         f"High  : ${lme.get('high',0):,.2f}",
         f"Low   : ${lme.get('low',0):,.2f}"]
    for ln in [_vwap_ln("LME_AL",data,"$",2), _ema_ln("LME_AL",data),
               _rsi_ln("LME_AL",data), _adx_ln("LME_AL",data)]:
        if ln: L.append(ln)
    if lme.get("open_interest"):
        L += [f"OI    : {lme['open_interest']:,.0f}  {_oi_a(lme.get('oi_chg_pct',0))}",
              f"🏦 {oi_e} {oi_t}"]
    if fv:
        gi = "🟢" if fv["gap_pct"]<0 else "🔴"
        L += ["", "📊 <b>MCX Fair Value from LME</b>",
              f"FV ₹{fv['fv_kg']:.2f}/kg  |  MCX ₹{fv['mcx']:.2f}",
              f"Gap {gi} {fv['gap_pct']:+.2f}%"]
    L += ["", "🔩 <b>Base Metals Complex</b>",
          f"Copper (leader): ${cu.get('close',0):.4f}/lb  {_c(cu.get('change',0))}",
          f"Zinc           : ${zn.get('close',0):,.0f}/MT  {_c(zn.get('change',0))}",
          f"Nickel         : ${ni.get('close',0):,.0f}/MT  {_c(ni.get('change',0))}",
          f"Lead           : ${ld.get('close',0):,.0f}/MT  {_c(ld.get('change',0))}",
          "", "⚡ <b>Macro</b>",
          f"Crude WTI: ${cr.get('close',0):.2f}  {_c(cr.get('change',0))}",
          f"DXY      : {dy.get('close',0):.2f}  {_c(dy.get('change',0))}"]
    await u.message.reply_text("\n".join(L), parse_mode="HTML")

async def cmd_mcx(u: Update, _c_: ContextTypes.DEFAULT_TYPE):
    data, fv, sig = await _get()
    mcx=data.get("MCX_AL",{}); ui=data.get("USD_INR",{})
    cm=data.get("CRUDE_MCX",{}); nf=data.get("NIFTY",{}); sx=data.get("SENSEX",{})
    oi_t, _, oi_e = read_oi("MCX_AL", data)
    L = ["🇮🇳 <b>MCX ALUMINUM DEEP-DIVE</b>", "",
         f"Price : ₹{mcx.get('close',0):.2f}/kg  {_c(mcx.get('change',0))}",
         f"Open  : ₹{mcx.get('open',0):.2f}",
         f"High  : ₹{mcx.get('high',0):.2f}",
         f"Low   : ₹{mcx.get('low',0):.2f}"]
    for ln in [_vwap_ln("MCX_AL",data), _ema_ln("MCX_AL",data),
               _bb_ln("MCX_AL",data), _rsi_ln("MCX_AL",data), _adx_ln("MCX_AL",data)]:
        if ln: L.append(ln)
    if mcx.get("open_interest"):
        L += [f"OI    : {mcx['open_interest']:,.0f}  {_oi_a(mcx.get('oi_chg_pct',0))}",
              f"🏦 {oi_e} {oi_t}"]
    vr = mcx.get("vol_ratio",1.0)
    L.append(f"Vol   : {vr:.2f}× avg {'📈 SURGE' if vr>=1.5 else ''}")
    if fv:
        gi = "🟢" if fv["gap_pct"]<-1 else ("🔴" if fv["gap_pct"]>1 else "⚪")
        L += ["", "📊 <b>Fair Value</b>",
              f"FV ₹{fv['fv_kg']:.2f}  |  Gap {gi} {fv['gap_pct']:+.2f}%"]
    L += ["", "🇮🇳 <b>India Macro</b>",
          f"USD/INR  : {ui.get('close',0):.2f}  {_c(ui.get('change',0))}"]
    if cm.get("close"):
        L.append(f"MCX Crude: ₹{cm['close']:,.2f}  {_c(cm.get('change',0))}")
    L += [f"Nifty    : {nf.get('close',0):,.2f}  {_c(nf.get('change',0))}",
          f"Sensex   : {sx.get('close',0):,.2f}  {_c(sx.get('change',0))}",
          "", f"🎯 <b>Signal: {sig['signal']}</b>  (Score {sig['score']:+.1f})"]
    await u.message.reply_text("\n".join(L), parse_mode="HTML")

async def cmd_factors(u: Update, _c: ContextTypes.DEFAULT_TYPE):
    data, _, _ = await _get()
    ui=data.get("USD_INR",{}); uc=data.get("USD_CNH",{}); dy=data.get("DXY",{})
    cr=data.get("CRUDE_WTI",{}); cu=data.get("COPPER_HG",{})
    zn=data.get("ZINC_LME",{}); ni=data.get("NICKEL_LME",{}); ld=data.get("LEAD_LME",{})
    ao=data.get("SHFE_ALUMINA",{}); nf=data.get("NIFTY",{}); sx=data.get("SENSEX",{})
    sh=data.get("SHANGHAI_COMP",{})

    ic=ui.get("change",0); dc=dy.get("change",0); crc=cr.get("change",0)
    cuc=cu.get("change",0); shc=sh.get("change",0); aoc=ao.get("change",0)

    L = ["⚡ <b>ALL FACTORS — ALUMINUM MCX</b>", "",
         "💱 <b>CURRENCY IMPACT</b>",
         f"USD/INR : {ui.get('close',0):.2f}  {_c(ic)}",
         ("  ↳ 🟢 Rupee weaker → imports costlier → MCX up" if ic>0.2 else
          "  ↳ 🔴 Rupee stronger → imports cheaper → MCX down" if ic<-0.2 else ""),
         f"USD/CNH : {uc.get('close',0):.4f}  {_c(uc.get('change',0))}",
         f"DXY     : {dy.get('close',0):.2f}  {_c(dc)}",
         ("  ↳ 🔴 Strong dollar → commodity headwind" if dc>0.3 else
          "  ↳ 🟢 Weak dollar → commodity support" if dc<-0.3 else ""),
         "",
         "⛽ <b>ENERGY  (≈35% of smelting cost)</b>",
         f"WTI Crude: ${cr.get('close',0):.2f}  {_c(crc)}",
         ("  ↳ 🟢 Higher energy → production cost up → aluminum support" if crc>1 else
          "  ↳ 🔴 Lower energy → margin pressure on smelters" if crc<-1 else ""),
         "",
         "🔩 <b>BASE METALS COMPLEX</b>",
         f"Copper (best indicator): ${cu.get('close',0):.4f}/lb  {_c(cuc)}",
         ("  ↳ 🟢 Copper leads metals complex higher" if cuc>0.5 else
          "  ↳ 🔴 Copper pulls metals complex lower" if cuc<-0.5 else ""),
         f"Zinc   : ${zn.get('close',0):,.0f}/MT  {_c(zn.get('change',0))}",
         f"Nickel : ${ni.get('close',0):,.0f}/MT  {_c(ni.get('change',0))}",
         f"Lead   : ${ld.get('close',0):,.0f}/MT  {_c(ld.get('change',0))}"]
    if ao.get("close"):
        L += [f"Alumina: ¥{ao['close']:,.0f}/MT  {_c(aoc)}",
              ("  ↳ 🟢 Alumina rising → production cost up → bullish" if aoc>1 else
               "  ↳ 🔴 Alumina falling → production cost easing" if aoc<-1 else "")]
    L += ["",
          "📈 <b>EQUITY MARKETS (risk appetite & demand)</b>",
          f"Nifty 50  : {nf.get('close',0):,.2f}  {_c(nf.get('change',0))}",
          f"Sensex    : {sx.get('close',0):,.2f}  {_c(sx.get('change',0))}",
          f"Shanghai  : {sh.get('close',0):,.2f}  {_c(shc)}",
          ("  ↳ 🟢 China market up → demand optimism → metals positive" if shc>0.5 else
           "  ↳ 🔴 China market down → demand concerns → metals pressure" if shc<-0.5 else "")]
    await u.message.reply_text("\n".join(L), parse_mode="HTML")

async def cmd_history(u: Update, _c: ContextTypes.DEFAULT_TYPE):
    sigs = load_signals()
    if not sigs:
        await u.message.reply_text("📚 No signal history yet. Keep the bot running — it records every MCX open signal.")
        return
    recent = sigs[-20:]
    done   = [s for s in recent if s.get("outcome")]
    corr   = sum(1 for s in done if s["outcome"]=="correct")
    acc    = corr/len(done)*100 if done else 0

    L = ["📚 <b>SIGNAL HISTORY & ACCURACY</b>",
         f"Total signals recorded: {len(sigs)}",
         f"Last 20 evaluated     : {len(done)}",
         f"Accuracy              : {acc:.1f}%", ""]

    L.append("<b>Recent Signals</b>")
    for s in reversed(recent[-10:]):
        ts  = s.get("ts","")[:16]; sig2 = s.get("signal","?")
        out = s.get("outcome","pending")
        e   = "✅" if out=="correct" else ("❌" if out=="wrong" else "⏳")
        L.append(f"{e} {ts}  {sig2}")

    # Factor accuracy
    fscores: dict = defaultdict(lambda:{"c":0,"t":0})
    for s in [x for x in sigs if x.get("outcome")]:
        ok = s["outcome"]=="correct"
        for f in s.get("active_factors",[]):
            fscores[f]["t"] += 1
            if ok: fscores[f]["c"] += 1

    ranked = sorted([(k,v) for k,v in fscores.items() if v["t"]>=5],
                    key=lambda x: x[1]["c"]/x[1]["t"], reverse=True)
    if ranked:
        L += ["", "<b>Factor Accuracy (≥5 signals)</b>"]
        for k,v in ranked[:8]:
            a = v["c"]/v["t"]*100
            L.append(f"{'🟢' if a>=60 else '🔴' if a<=40 else '🟡'} {k}: {a:.0f}%  ({v['t']} signals)")

    L += ["", "<b>Current Learned Weights</b>",
          f"FV: {_S.get('w_fair_value',2):.1f}  LME: {_S.get('w_lme',1):.1f}  SHFE: {_S.get('w_shfe',1):.1f}",
          f"Copper: {_S.get('w_copper',1.2):.1f}  MCX-OI: {_S.get('w_mcx_oi',1.5):.1f}  DXY: {_S.get('w_dxy',0.8):.1f}"]
    await u.message.reply_text("\n".join(L), parse_mode="HTML")

async def cmd_learn(u: Update, _c: ContextTypes.DEFAULT_TYPE):
    global _S
    await u.message.reply_text("🧠 Running learning algorithm on signal history…")
    _S, summary = auto_learn(_S)
    save_settings(_S)
    await u.message.reply_text(summary)


# ═════════════════════════════════════════════════════════════════
# § 11  SCHEDULED JOBS
# ═════════════════════════════════════════════════════════════════

async def job_pre_market(ctx: ContextTypes.DEFAULT_TYPE):
    data, fv, _ = await _get()
    await _push(ctx.bot, fmt_pre_market(data, fv))

async def job_mcx_open(ctx: ContextTypes.DEFAULT_TYPE):
    data, fv, sig = await _get()
    await _push(ctx.bot, fmt_mcx_open(data, fv, sig))
    if fv:
        record_signal(sig, fv["fv_kg"], fv["mcx"])

async def job_lme_open(ctx: ContextTypes.DEFAULT_TYPE):
    data, fv, sig = await _get()
    await _push(ctx.bot, fmt_full(data, fv, sig))

async def job_mcx_close(ctx: ContextTypes.DEFAULT_TYPE):
    global _S
    data, fv, _ = await _get()
    await _push(ctx.bot, fmt_mcx_close(data, fv))

    # Evaluate today's opening signal
    mcx_close = _f(data.get("MCX_AL", {}).get("close"))
    if mcx_close > 0:
        evaluate_today_signal(mcx_close)

    # Save daily history
    if fv:
        append_history({
            "date"    : date.today().isoformat(),
            "mcx"     : fv["mcx"],  "fv"      : fv["fv_kg"],
            "gap_pct" : fv["gap_pct"], "lme"   : fv["lme"],
            "usd_inr" : fv["usd_inr"],
        })

    # Auto-learn every Friday (weekday 4)
    if datetime.now(IST).weekday() == 4:
        _S, summary = auto_learn(_S)
        save_settings(_S)
        await _push(ctx.bot, "🧠 <b>Weekly Auto-Learn Complete</b>\n\n" + summary)

async def job_live_signal(ctx: ContextTypes.DEFAULT_TYPE):
    data, fv, sig = await _get()
    await _push(ctx.bot, fmt_signal(data, fv, sig))


# ═════════════════════════════════════════════════════════════════
# § 12  MAIN
# ═════════════════════════════════════════════════════════════════

def main() -> None:
    global _S
    _S = load_settings()

    logging.basicConfig(
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        level=logging.INFO,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("jarvis.log"),
        ],
    )

    log.info("=" * 60)
    log.info("ALUMINUM PRO TRADER v2.0 — Starting")
    log.info("Data dir : %s", DATA_DIR.resolve())
    log.info("Chat ID  : %s", CHAT_ID)
    log.info("=" * 60)

    app = Application.builder().token(BOT_TOKEN).build()

    for cmd, fn in [
        ("start",    cmd_start),   ("help",      cmd_help),
        ("report",   cmd_report),  ("signal",    cmd_signal),
        ("fairvalue",cmd_fairvalue),("shanghai", cmd_shanghai),
        ("lme",      cmd_lme),     ("mcx",       cmd_mcx),
        ("factors",  cmd_factors), ("history",   cmd_history),
        ("learn",    cmd_learn),
    ]:
        app.add_handler(CommandHandler(cmd, fn))

    jq = app.job_queue
    jq.run_daily(job_pre_market,  dtime(6,  45, tzinfo=IST))
    jq.run_daily(job_mcx_open,    dtime(9,   5, tzinfo=IST))
    jq.run_daily(job_lme_open,    dtime(13,  5, tzinfo=IST))
    jq.run_daily(job_mcx_close,   dtime(23, 35, tzinfo=IST))
    jq.run_repeating(job_live_signal, interval=1800, first=90)  # 30-min, first after 90s

    log.info("Bot polling started. Commands + auto-reports active.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
