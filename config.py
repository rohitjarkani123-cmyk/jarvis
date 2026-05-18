"""
Aluminum Pro Trader - Configuration
Edit TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID before running.
"""

# ─────────────────────────────────────────────────────────────────
# TELEGRAM SETUP  (fill these in)
# ─────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = "8459666504:AAFu7gYcUq2UlwV6OIMNZCscHGZ0DAnhBes"
TELEGRAM_CHAT_ID   = "1047128404"

# ─────────────────────────────────────────────────────────────────
# ALL SYMBOLS  (TradingView format: EXCHANGE:SYMBOL)
# ─────────────────────────────────────────────────────────────────
SYMBOLS = {
    # ── Primary Aluminum ──────────────────────────────────────────
    "SHFE_AL"      : "SHFE:AL1!",        # Shanghai Futures Exchange aluminum
    "LME_AL"       : "COMEX:ALI1!",      # COMEX ALI = best liquid LME proxy
    "MCX_AL"       : "MCX:ALUMINIUM1!",  # MCX India aluminum

    # ── Raw Material ──────────────────────────────────────────────
    "SHFE_ALUMINA" : "SHFE:AO1!",        # Alumina futures (smelting input)

    # ── Currencies ────────────────────────────────────────────────
    "USD_INR"      : "FX:USDINR",        # Dollar vs Indian Rupee
    "USD_CNH"      : "FX:USDCNH",        # Dollar vs Offshore Yuan
    "DXY"          : "TVC:DXY",          # US Dollar Index

    # ── Energy (smelting cost) ────────────────────────────────────
    "CRUDE_WTI"    : "NYMEX:CL1!",       # WTI Crude Oil
    "CRUDE_MCX"    : "MCX:CRUDEOIL1!",   # MCX Crude (India)

    # ── Base Metals Complex ───────────────────────────────────────
    "COPPER_HG"    : "COMEX:HG1!",       # Copper – leading industrial indicator
    "ZINC_LME"     : "LME:ZINC",         # LME Zinc
    "NICKEL_LME"   : "LME:NICKEL",       # LME Nickel
    "LEAD_LME"     : "LME:LEAD",         # LME Lead

    # ── Equity Indices (demand/sentiment) ─────────────────────────
    "NIFTY"        : "NSE:NIFTY50",      # India Nifty 50
    "SENSEX"       : "BSE:SENSEX",       # India BSE Sensex
    "SHANGHAI_COMP": "SSE:000001",       # China Shanghai Composite
}

# ─────────────────────────────────────────────────────────────────
# MCX FAIR VALUE – India Import Duty Structure (as of 2025-26)
# ─────────────────────────────────────────────────────────────────
INDIA_CIF_PREMIUM_USD_MT  = 310    # Physical delivery premium + freight/insurance
BASIC_CUSTOMS_DUTY        = 0.075  # 7.5% BCD on CIF value
SOCIAL_WELFARE_SURCHARGE  = 0.10   # 10% of BCD  (= 0.75% of CIF)
IGST_RATE                 = 0.18   # 18% IGST on (CIF + BCD + SWS)

# ─────────────────────────────────────────────────────────────────
# SIGNAL THRESHOLDS
# ─────────────────────────────────────────────────────────────────
BULLISH_THRESHOLD         = 4      # Min bullish factors for BUY
BEARISH_THRESHOLD         = 4      # Min bearish factors for SHORT
STRONG_SIGNAL_MIN         = 7      # Score for STRONG BUY / STRONG SHORT

FV_BUY_THRESHOLD          = -1.5   # MCX < FV by 1.5%  → bullish factor
FV_SELL_THRESHOLD         =  1.5   # MCX > FV by 1.5%  → bearish factor

OI_CHANGE_SIGNIFICANT     = 2.0    # OI change % considered significant
VOL_SURGE_RATIO           = 1.5    # Volume 1.5× average = institutional

# ─────────────────────────────────────────────────────────────────
# SCHEDULED REPORTS (IST, 24-h)
# ─────────────────────────────────────────────────────────────────
# SHFE: 09:00 CST = 06:30 IST | LME ring: 07:30 GMT = 13:00 IST
REPORT_PRE_MARKET_H,  REPORT_PRE_MARKET_M  =  6, 45   # Before SHFE open
REPORT_MCX_OPEN_H,    REPORT_MCX_OPEN_M    =  9,  5   # MCX opens 09:00 IST
REPORT_LME_OPEN_H,    REPORT_LME_OPEN_M    = 13,  5   # LME ring opens
REPORT_MCX_CLOSE_H,   REPORT_MCX_CLOSE_M   = 23, 35   # After MCX closes

UPDATE_INTERVAL_MIN = 30           # Live signal update interval during market hours

# ─────────────────────────────────────────────────────────────────
# DATA FETCH
# ─────────────────────────────────────────────────────────────────
TV_SCANNER_URL      = "https://scanner.tradingview.com/global/scan"
REQUEST_TIMEOUT_SEC = 30
HISTORY_MAXLEN      = 20           # Rolling history window for vol/OI comparison
