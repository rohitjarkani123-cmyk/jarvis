"""
Analysis engine:
  - MCX fair value from LME + India import duties
  - OI institutional-activity interpretation
  - Multi-factor signal generation (BUY / SHORT / NO TRADE)
"""

import config


# ─────────────────────────────────────────────────────────────────
# FAIR VALUE
# ─────────────────────────────────────────────────────────────────

def calculate_fair_value(data: dict) -> dict | None:
    """
    Calculate MCX Aluminum fair value from LME price + India import cost.

    Formula (per MT → converted to per kg):
        CIF value   = LME price + physical CIF premium
        BCD         = CIF × 7.5%
        SWS         = BCD × 10%
        IGST base   = CIF + BCD + SWS
        IGST        = IGST_base × 18%
        Landed cost = CIF + BCD + SWS + IGST
        Fair value  = Landed cost / 1000  (INR per kg)

    Returns None if critical data is missing.
    """
    lme_usd_mt  = (data.get("LME_AL",  {}).get("close") or 0.0)
    usd_inr     = (data.get("USD_INR", {}).get("close") or 0.0)
    mcx_inr_kg  = (data.get("MCX_AL",  {}).get("close") or 0.0)

    if lme_usd_mt <= 0 or usd_inr <= 0:
        return None

    # Step 1 – import cost in USD/MT (LME + physical premium)
    cif_usd_mt = lme_usd_mt + config.INDIA_CIF_PREMIUM_USD_MT

    # Step 2 – convert to INR/MT
    cif_inr_mt = cif_usd_mt * usd_inr

    # Step 3 – customs duties
    bcd      = cif_inr_mt * config.BASIC_CUSTOMS_DUTY
    sws      = bcd        * config.SOCIAL_WELFARE_SURCHARGE
    igst     = (cif_inr_mt + bcd + sws) * config.IGST_RATE
    duty     = bcd + sws + igst

    landed_inr_mt = cif_inr_mt + duty
    fv_per_kg     = landed_inr_mt / 1000.0

    gap_inr  = mcx_inr_kg - fv_per_kg
    gap_pct  = (gap_inr / fv_per_kg * 100) if fv_per_kg > 0 else 0.0

    return {
        "lme_usd_mt"       : round(lme_usd_mt,    2),
        "cif_premium_usd"  : config.INDIA_CIF_PREMIUM_USD_MT,
        "cif_usd_mt"       : round(cif_usd_mt,    2),
        "usd_inr"          : round(usd_inr,        2),
        "cif_inr_mt"       : round(cif_inr_mt,     0),
        "bcd_inr"          : round(bcd,             0),
        "sws_inr"          : round(sws,             0),
        "igst_inr"         : round(igst,            0),
        "total_duty_inr"   : round(duty,            0),
        "landed_inr_mt"    : round(landed_inr_mt,   0),
        "fair_value_per_kg": round(fv_per_kg,       2),
        "mcx_price"        : round(mcx_inr_kg,      2),
        "gap_inr"          : round(gap_inr,         2),
        "gap_pct"          : round(gap_pct,         2),
    }


# ─────────────────────────────────────────────────────────────────
# OI / INSTITUTIONAL ACTIVITY
# ─────────────────────────────────────────────────────────────────

def interpret_oi(key: str, data: dict) -> tuple[str, str, str]:
    """
    Interpret Open Interest change vs price direction.

    Returns
    -------
    (interpretation_text, sentiment, emoji)
    sentiment: "bullish" | "bearish" | "neutral"
    """
    d             = data.get(key, {})
    price_change  = d.get("change", 0.0)
    oi            = d.get("open_interest", 0.0)
    oi_change_pct = d.get("oi_change_pct", 0.0)

    if not oi:
        return "OI data unavailable", "neutral", "⚪"

    price_up = price_change > 0
    oi_up    = oi_change_pct >  config.OI_CHANGE_SIGNIFICANT
    oi_down  = oi_change_pct < -config.OI_CHANGE_SIGNIFICANT

    if price_up and oi_up:
        return "LONG BUILDUP – Institutional BUYING active",          "bullish", "🟢"
    if price_up and oi_down:
        return "SHORT COVERING – Shorts exiting (less reliable move)", "neutral", "🟡"
    if not price_up and oi_up:
        return "SHORT BUILDUP – Institutional SELLING active",         "bearish", "🔴"
    if not price_up and oi_down:
        return "LONG UNWINDING – Longs exiting (potential bottom near)","neutral", "🟠"
    return "Consolidation – No clear institutional direction",          "neutral", "⚪"


# ─────────────────────────────────────────────────────────────────
# SIGNAL ENGINE
# ─────────────────────────────────────────────────────────────────

def generate_signal(data: dict, fv: dict | None) -> dict:
    """
    Score all available factors and produce a trading signal.

    Returns
    -------
    {
        signal          : "BUY" | "STRONG BUY" | "SHORT" | "STRONG SHORT" | "NO TRADE"
        score           : int   (positive = bullish, negative = bearish)
        bullish_factors : list[str]
        bearish_factors : list[str]
    }
    """
    bullish: list[str] = []
    bearish: list[str] = []

    def b(txt: str): bullish.append(txt)
    def s(txt: str): bearish.append(txt)

    # 1. Fair Value – most important single factor
    if fv:
        gp = fv["gap_pct"]
        if gp < config.FV_BUY_THRESHOLD:
            b(f"MCX {abs(gp):.1f}% BELOW Fair Value → undervalued, import cost ₹{fv['fair_value_per_kg']:.2f}")
        elif gp > config.FV_SELL_THRESHOLD:
            s(f"MCX {gp:.1f}% ABOVE Fair Value → overvalued, import cost ₹{fv['fair_value_per_kg']:.2f}")

    def _chg(key: str) -> float:
        return data.get(key, {}).get("change", 0.0) or 0.0

    # 2. LME / COMEX aluminum trend
    lme_c = _chg("LME_AL")
    if   lme_c >  0.5: b(f"LME Aluminum rising +{lme_c:.2f}%")
    elif lme_c < -0.5: s(f"LME Aluminum falling {lme_c:.2f}%")

    # 3. Shanghai SHFE aluminum trend
    sh_c = _chg("SHFE_AL")
    if   sh_c >  0.5: b(f"Shanghai Aluminum rising +{sh_c:.2f}%")
    elif sh_c < -0.5: s(f"Shanghai Aluminum falling {sh_c:.2f}%")

    # 4. USD/INR  (rising = weaker rupee = imports costlier = MCX up)
    inr_c = _chg("USD_INR")
    if   inr_c >  0.2: b(f"INR weakening +{inr_c:.2f}% → import cost rises → MCX up")
    elif inr_c < -0.2: s(f"INR strengthening {inr_c:.2f}% → import cost falls → MCX down")

    # 5. DXY  (strong dollar = metal headwind)
    dxy_c = _chg("DXY")
    if   dxy_c >  0.3: s(f"DXY up {dxy_c:.2f}% → strong dollar pressures metals")
    elif dxy_c < -0.3: b(f"DXY down {dxy_c:.2f}% → weak dollar supports metals")

    # 6. Copper (best leading indicator for base-metals complex)
    cu_c = _chg("COPPER_HG")
    if   cu_c >  0.5: b(f"Copper up {cu_c:.2f}% → base metals complex bullish")
    elif cu_c < -0.5: s(f"Copper down {cu_c:.2f}% → base metals complex bearish")

    # 7. Crude oil (energy cost for aluminium smelting ≈ 30-40% of cost)
    crude_c = _chg("CRUDE_WTI")
    if   crude_c >  1.0: b(f"Crude up {crude_c:.2f}% → higher smelting cost → aluminum higher")
    elif crude_c < -1.0: s(f"Crude down {crude_c:.2f}% → lower smelting cost → margin pressure")

    # 8. Shanghai Composite (China demand proxy)
    sh_eq_c = _chg("SHANGHAI_COMP")
    if   sh_eq_c >  0.5: b(f"Shanghai Composite +{sh_eq_c:.2f}% → China demand positive")
    elif sh_eq_c < -0.5: s(f"Shanghai Composite {sh_eq_c:.2f}% → China demand concern")

    # 9. Alumina (raw material cost – 30% of aluminum production cost)
    ao_c = _chg("SHFE_ALUMINA")
    if   ao_c >  1.0: b(f"Alumina up {ao_c:.2f}% → production cost rising → support aluminum")
    elif ao_c < -1.0: s(f"Alumina down {ao_c:.2f}% → production cost easing")

    # 10. Zinc & Nickel (base metals breadth)
    zn_c = _chg("ZINC_LME")
    ni_c = _chg("NICKEL_LME")
    metals_bullish = sum(1 for c in [zn_c, ni_c] if c > 0.5)
    metals_bearish = sum(1 for c in [zn_c, ni_c] if c < -0.5)
    if metals_bullish == 2: b(f"Zinc +{zn_c:.1f}% & Nickel +{ni_c:.1f}% – broad metals rally")
    if metals_bearish == 2: s(f"Zinc {zn_c:.1f}% & Nickel {ni_c:.1f}% – broad metals sell-off")

    # 11. MCX OI (institutional positioning)
    mcx_oi_txt, mcx_oi_sentiment, _ = interpret_oi("MCX_AL", data)
    if   mcx_oi_sentiment == "bullish": b(f"MCX OI: {mcx_oi_txt}")
    elif mcx_oi_sentiment == "bearish": s(f"MCX OI: {mcx_oi_txt}")

    # 12. SHFE OI (China institutional positioning)
    sh_oi_txt, sh_oi_sentiment, _ = interpret_oi("SHFE_AL", data)
    if   sh_oi_sentiment == "bullish": b(f"Shanghai OI: {sh_oi_txt}")
    elif sh_oi_sentiment == "bearish": s(f"Shanghai OI: {sh_oi_txt}")

    # 13. MCX volume surge (confirms direction)
    mcx_vol_ratio = data.get("MCX_AL", {}).get("vol_ratio", 1.0) or 1.0
    mcx_price_chg = _chg("MCX_AL")
    if mcx_vol_ratio >= config.VOL_SURGE_RATIO:
        if   mcx_price_chg > 0: b(f"MCX volume {mcx_vol_ratio:.1f}x avg – institutional buying confirmed")
        elif mcx_price_chg < 0: s(f"MCX volume {mcx_vol_ratio:.1f}x avg – institutional selling confirmed")

    # 14. Nifty / Sensex (domestic risk appetite)
    nifty_c = _chg("NIFTY")
    if   nifty_c >  0.5: b(f"Nifty +{nifty_c:.2f}% – positive domestic risk appetite")
    elif nifty_c < -0.5: s(f"Nifty {nifty_c:.2f}% – domestic risk-off sentiment")

    # ── Score & Signal ────────────────────────────────────────────
    score = len(bullish) - len(bearish)

    if   score >= config.STRONG_SIGNAL_MIN:  signal = "STRONG BUY"
    elif score >= config.BULLISH_THRESHOLD:  signal = "BUY"
    elif score <= -config.STRONG_SIGNAL_MIN: signal = "STRONG SHORT"
    elif score <= -config.BEARISH_THRESHOLD: signal = "SHORT"
    else:                                    signal = "NO TRADE"

    return {
        "signal"         : signal,
        "score"          : score,
        "bullish_factors": bullish,
        "bearish_factors": bearish,
    }
