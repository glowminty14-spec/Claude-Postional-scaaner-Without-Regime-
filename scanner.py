"""
scanner.py — Daily VCP Scanner
Synced exactly to backtest_vcp_1lakh.py (27.1% CAGR, 61.3% WR, 2.37x PF)

CHANGES FROM PREVIOUS SCANNER (to match backtest):
  1. MAX_RISK_PCT      : 0.08 → 0.11   ← CRITICAL, was stopping out too early
  2. vol_surge scoring : 7x+=2.0 → 5x+=2.0  (matches backtest scoring)
  3. SL calculation    : same 3-method max (atr, base_low, pct cap)
  4. All filter values : confirmed identical to backtest

Run: python scanner.py
"""

import yfinance as yf
import pandas as pd
import pandas_ta as ta
import time, io, requests, warnings
warnings.filterwarnings("ignore")

from telegram_bot import send_entry_alert, send_no_signal_alert
from trade_manager import add_trade

# ═══════════════════════════════════════════════
#  CONFIG — EXACTLY matching backtest_vcp_1lakh.py
#  DO NOT change these without also changing backtest
# ═══════════════════════════════════════════════
MIN_SCORE         = 11.0
MAX_HOLD_DAYS     = 70           # ← backtest uses 70, old scanner had 60
ATR_MULTIPLIER_SL = 2.5
RR_RATIO_T1       = 2.5
RR_RATIO_T2       = 5.0
LIQUIDITY_MIN_CR  = 5
MAX_RISK_PCT      = 0.11         # ← FIXED: was 0.08, backtest uses 0.11

VCP_ADX_MIN       = 25
VCP_VOL_MIN       = 2.0
VCP_BASE_DAYS     = 7
VCP_BASE_RANGE    = 0.12
VCP_BASE_MIN      = 0.05
VCP_VOL_DRYUP     = 0.90
VCP_RSI_MIN       = 45
VCP_RSI_MAX       = 75
MAX_RUN_60D       = 0.40
MIN_RS_VS_NIFTY   = 0.00

# ═══════════════════════════════════════════════
#  CAPITAL CONFIG
# ═══════════════════════════════════════════════
CAPITAL           = 100_000
RISK_PER_TRADE    = 0.04         # 4% risk = ₹4,000 per trade

# ═══════════════════════════════════════════════
#  FETCH NIFTY 200
# ═══════════════════════════════════════════════
def fetch_nifty200():
    url = "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.nseindia.com/",
    }
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        time.sleep(1)
        r = session.get(url, headers=headers, timeout=15)
        if r.status_code == 200 and len(r.content) > 500:
            df = pd.read_csv(io.StringIO(r.content.decode("utf-8")))
            symbols = [str(row["Symbol"]).strip() + ".NS" for _, row in df.iterrows()]
            print(f"  Live Nifty 200 fetched: {len(symbols)} stocks")
            return symbols
    except Exception as e:
        print(f"  NSE fetch failed ({e}), using fallback list")

    return [
        "RELIANCE.NS","HDFCBANK.NS","INFY.NS","ICICIBANK.NS","TCS.NS",
        "SBIN.NS","BHARTIARTL.NS","WIPRO.NS","AXISBANK.NS","SUNPHARMA.NS",
        "TATAMOTORS.NS","ADANIPORTS.NS","POLYCAB.NS","SIEMENS.NS","ABB.NS",
        "HINDALCO.NS","TATASTEEL.NS","COALINDIA.NS","ONGC.NS","NTPC.NS",
        "POWERGRID.NS","BAJFINANCE.NS","BAJAJFINSV.NS","MARUTI.NS","TITAN.NS",
        "NESTLEIND.NS","BRITANNIA.NS","ASIANPAINT.NS","PIDILITIND.NS","BERGEPAINT.NS",
        "APOLLOHOSP.NS","DRREDDY.NS","CIPLA.NS","DIVISLAB.NS","LTIM.NS",
        "HCLTECH.NS","TECHM.NS","MPHASIS.NS","COFORGE.NS","ADANIPOWER.NS",
        "TATAPOWER.NS","TORNTPOWER.NS","NHPC.NS","INDUSINDBK.NS","FEDERALBNK.NS",
        "AUBANK.NS","IDFCFIRSTB.NS","VOLTAS.NS","CUMMINSIND.NS","HAVELLS.NS",
        "IRCTC.NS","CHOLAFIN.NS","MUTHOOTFIN.NS","LTTS.NS","PERSISTENT.NS",
        "TATACOMM.NS","MOTHERSON.NS","BOSCHLTD.NS","MRF.NS","APOLLOTYRE.NS",
        "HEROMOTOCO.NS","EICHERMOT.NS","BALKRISIND.NS","JSWSTEEL.NS","SAIL.NS",
        "NATIONALUM.NS","VEDL.NS","NMDC.NS","GAIL.NS","IOC.NS",
        "BPCL.NS","HPCL.NS","TATACONSUM.NS","GODREJCP.NS","DABUR.NS",
        "MARICO.NS","COLPAL.NS","EMAMILTD.NS","MCDOWELL-N.NS","UBL.NS",
        "OBEROIRLTY.NS","GODREJPROP.NS","DLF.NS","PRESTIGE.NS","BRIGADE.NS",
        "INDIGO.NS","CONCOR.NS","RVNL.NS","IRFC.NS","KOTAKBANK.NS",
        "LT.NS","M&M.NS","BAJAJ-AUTO.NS","GRASIM.NS","TRENT.NS",
        "PAGEIND.NS","BATAINDIA.NS","PHOENIXLTD.NS","TORNTPHARM.NS","ALKEM.NS",
        "VBL.NS","SBICARD.NS","HDFCAMC.NS","CANFINHOME.NS","MANAPPURAM.NS",
        "KPITTECH.NS","TATAELXSI.NS","CYIENT.NS","BEL.NS","HAL.NS",
        "KEC.NS","THERMAX.NS","BHEL.NS","LAURUS.NS","GLENMARK.NS",
        "IPCALAB.NS","AJANTPHARM.NS","NATCOPHARM.NS","GRANULES.NS","MANKIND.NS",
        "HDFCLIFE.NS","SBILIFE.NS","ICICIGI.NS","UTIAMC.NS","NIPPONEAMC.NS",
        "PNBHOUSING.NS","LICHSGFIN.NS","RBLBANK.NS","BANDHANBNK.NS",
        "SOBHA.NS","MAHINDCIE.NS","BLUESTARCO.NS","WHIRLPOOL.NS",
        "CROMPTON.NS","ORIENTELEC.NS","VGUARD.NS","AMBER.NS","DIXONTECH.NS",
        "RAILTEL.NS","TIINDIA.NS","SONACOMS.NS","CRAFTSMAN.NS","ENDURANCE.NS",
        "SPICEJET.NS","BAJAJHFL.NS","PAYTM.NS","NYKAA.NS","ZOMATO.NS",
        "DMART.NS",
    ]

# ═══════════════════════════════════════════════
#  MARKET REGIME — identical logic to backtest
# ═══════════════════════════════════════════════
def get_market_regime():
    """
    STRONG_BULL : Price > EMA50 > EMA200
    BULLISH     : Price > EMA50
    BEARISH     : Price < EMA50  → NO trades
    NEUTRAL     : Mixed
    """
    try:
        nifty = yf.download("^NSEI", period="2y", progress=False, auto_adjust=True)
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.get_level_values(0)
        close = nifty["Close"].dropna()
        if len(close) < 210:
            return "NEUTRAL", 0.0

        ema50  = float(ta.ema(close, 50).iloc[-1])
        ema200 = float(ta.ema(close, 200).iloc[-1])
        price  = float(close.iloc[-1])
        r60    = float((price / close.iloc[-60]) - 1)

        if   price > ema50 > ema200: regime = "STRONG_BULL"
        elif price > ema50:          regime = "BULLISH"
        elif price < ema50:          regime = "BEARISH"
        else:                        regime = "NEUTRAL"

        return regime, r60
    except Exception as e:
        print(f"  Regime error: {e}")
        return "NEUTRAL", 0.0

# ═══════════════════════════════════════════════
#  POSITION SIZE CALCULATOR
# ═══════════════════════════════════════════════
def calculate_position(entry, sl, capital=CAPITAL, risk_pct=RISK_PER_TRADE):
    risk_amount    = capital * risk_pct
    risk_per_share = entry - sl
    if risk_per_share <= 0:
        return 0, 0
    shares         = int(risk_amount / risk_per_share)
    position_value = shares * entry
    return shares, round(position_value, 0)

# ═══════════════════════════════════════════════
#  VCP SIGNAL DETECTION
#  Filters and scoring EXACTLY match backtest
# ═══════════════════════════════════════════════
def detect_vcp_signal(ticker, market_trend, nifty_r60):
    try:
        df = yf.download(ticker, period="3y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            try:    df = df.xs(ticker, level=1, axis=1)
            except: df = df.droplevel(1, axis=1)
        if any(c not in df.columns for c in ["Open","High","Low","Close","Volume"]):
            return None
        df.index = pd.to_datetime(df.index)

        if market_trend == "BEARISH":
            return None

        # ── DAILY INDICATORS ──────────────────
        df["EMA20"]     = ta.ema(df["Close"], 20)
        df["EMA50"]     = ta.ema(df["Close"], 50)
        df["EMA200"]    = ta.ema(df["Close"], 200)
        df["RSI"]       = ta.rsi(df["Close"], 14)
        df["ATR"]       = ta.atr(df["High"], df["Low"], df["Close"], 14)
        adx_df          = ta.adx(df["High"], df["Low"], df["Close"], 14)
        df              = pd.concat([df, adx_df], axis=1)
        df["OBV"]       = ta.obv(df["Close"], df["Volume"])
        df["OBV_EMA20"] = ta.ema(df["OBV"], 20)
        df["OBV_EMA50"] = ta.ema(df["OBV"], 50)
        df["AvgVol20"]  = df["Volume"].rolling(20).mean()
        df["AvgVol40"]  = df["Volume"].rolling(40).mean()
        df.dropna(inplace=True)

        if len(df) < 60:
            return None

        curr     = df.iloc[-1]
        adx_cols = [c for c in df.columns if "ADX_14" in c]
        if not adx_cols:
            return None

        adx_val   = float(curr[adx_cols[0]])
        rsi       = float(curr["RSI"])
        entry     = float(curr["Close"])
        ema20     = float(curr["EMA20"])
        ema50     = float(curr["EMA50"])
        ema200    = float(curr["EMA200"])
        avg_vol   = float(df["AvgVol20"].iloc[-2])
        vol_surge = float(curr["Volume"]) / avg_vol if avg_vol > 0 else 0

        # ── WEEKLY INDICATORS ─────────────────
        weekly = df.resample("W").agg({
            "Open":"first","High":"max","Low":"min",
            "Close":"last","Volume":"sum"
        }).dropna()
        if len(weekly) < 50:
            return None
        weekly["W_EMA20"]   = ta.ema(weekly["Close"], 20)
        weekly["W_EMA50"]   = ta.ema(weekly["Close"], 50)
        weekly["W_OBV"]     = ta.obv(weekly["Close"], weekly["Volume"])
        weekly["W_OBV_EMA"] = ta.ema(weekly["W_OBV"], 20)
        weekly.dropna(inplace=True)
        if len(weekly) < 5:
            return None

        w_curr   = weekly.iloc[-1]
        w_ema20  = float(w_curr["W_EMA20"])
        w_ema50  = float(w_curr["W_EMA50"])
        w_obv_up = float(w_curr["W_OBV"]) > float(w_curr["W_OBV_EMA"])

        # ══════════════════════════════════════
        #  FILTER BLOCK 1 — identical to backtest
        # ══════════════════════════════════════
        if avg_vol * entry < LIQUIDITY_MIN_CR * 1e7:    return None
        if entry < ema200:                               return None
        if entry < w_ema50:                              return None
        if w_ema20 < w_ema50:                            return None
        if adx_val < VCP_ADX_MIN:                        return None
        if rsi < VCP_RSI_MIN or rsi > VCP_RSI_MAX:      return None

        stock_r60 = float((entry / df["Close"].iloc[-60]) - 1)
        if stock_r60 < nifty_r60 + MIN_RS_VS_NIFTY:     return None
        if stock_r60 > MAX_RUN_60D:                      return None
        if not w_obv_up:                                 return None
        if float(curr["OBV"]) < float(curr["OBV_EMA50"]): return None

        # ══════════════════════════════════════
        #  FILTER BLOCK 2 — BASE
        # ══════════════════════════════════════
        base       = df.iloc[-VCP_BASE_DAYS-1:-1]
        if len(base) < VCP_BASE_DAYS:                    return None
        base_high  = float(base["High"].max())
        base_low   = float(base["Low"].min())
        base_range = (base_high - base_low) / base_low
        if base_range > VCP_BASE_RANGE:                  return None
        if base_range < VCP_BASE_MIN:                    return None
        avg_vol_40   = float(df["AvgVol40"].iloc[-2])
        avg_vol_base = float(base["Volume"].mean())
        vol_ratio    = avg_vol_base / avg_vol_40 if avg_vol_40 > 0 else 999
        if vol_ratio > VCP_VOL_DRYUP:                    return None

        # ══════════════════════════════════════
        #  FILTER BLOCK 3 — BREAKOUT
        # ══════════════════════════════════════
        if entry <= base_high:                           return None
        if vol_surge < VCP_VOL_MIN:                      return None
        if 5.0 <= vol_surge < 7.0:                       return None

        day_range = float(curr["High"]) - float(curr["Low"])
        if day_range > 0:
            close_pos = (entry - float(curr["Low"])) / day_range
            if close_pos < 0.5:                          return None

        if not (ema20 > ema200):                         return None

        last_20      = df.tail(20)
        green_vol    = last_20[last_20["Close"] > last_20["Open"]]["Volume"].sum()
        red_vol      = last_20[last_20["Close"] < last_20["Open"]]["Volume"].sum() or 1
        buy_pressure = float(green_vol / red_vol)
        if buy_pressure < 1.2:                           return None

        # ══════════════════════════════════════
        #  SCORING — identical to backtest
        # ══════════════════════════════════════
        score = 5.0

        if   base_range < 0.05: score += 3.0
        elif base_range < 0.08: score += 2.0
        elif base_range < 0.10: score += 1.0
        elif base_range < 0.12: score += 0.5

        if   vol_ratio < 0.60:  score += 2.0
        elif vol_ratio < 0.70:  score += 1.5
        elif vol_ratio < 0.80:  score += 1.0
        elif vol_ratio < 0.90:  score += 0.5

        # ── FIXED: vol_surge scoring matches backtest ──
        if   vol_surge >= 5.0:  score += 2.0   # ← was 7x in old scanner
        elif vol_surge >= 4.0:  score += 1.5
        elif vol_surge >= 3.5:  score += 1.0
        elif vol_surge >= 3.0:  score += 0.5
        elif vol_surge >= 2.0:  score += 0.25

        if   adx_val >= 50:     score += 3.0
        elif adx_val >= 45:     score += 2.5
        elif adx_val >= 40:     score += 2.0
        elif adx_val >= 38:     score += 1.5
        elif adx_val >= 35:     score += 1.0
        elif adx_val >= 33:     score += 0.5
        elif adx_val >= 28:     score += 0.25

        if w_obv_up:             score += 1.5

        if   buy_pressure >= 3.0: score += 2.0
        elif buy_pressure >= 2.5: score += 1.5
        elif buy_pressure >= 2.0: score += 1.0
        elif buy_pressure >= 1.5: score += 0.5
        elif buy_pressure >= 1.2: score += 0.25

        if ema20 > ema50 > ema200:           score += 1.0
        if w_ema20 > w_ema50:                score += 0.5
        if stock_r60 > nifty_r60 + 0.10:    score += 1.0
        elif stock_r60 > nifty_r60 + 0.05:  score += 0.5
        if market_trend == "STRONG_BULL":    score += 0.5

        if score < MIN_SCORE:                            return None

        # ══════════════════════════════════════
        #  SL & TARGETS — identical to backtest
        # ══════════════════════════════════════
        atr_val = float(curr["ATR"])
        sl_atr  = entry - ATR_MULTIPLIER_SL * atr_val   # ATR method
        sl_base = base_low * 0.99                        # Below base low
        sl_pct  = entry * (1 - MAX_RISK_PCT)             # 11% hard cap

        sl   = round(max(sl_atr, sl_base, sl_pct), 1)
        risk = entry - sl

        if risk <= 0:
            return None
        if risk / entry > MAX_RISK_PCT:
            sl   = round(entry * (1 - MAX_RISK_PCT), 1)
            risk = entry - sl

        target1 = round(entry + risk * RR_RATIO_T1, 1)  # 2.5R
        target2 = round(entry + risk * RR_RATIO_T2, 1)  # 5.0R

        shares, position_val = calculate_position(entry, sl)

        return {
            "ticker":       ticker.replace(".NS", ""),
            "entry":        round(entry, 1),
            "sl":           sl,
            "target1":      target1,
            "target2":      target2,
            "atr":          round(atr_val, 2),
            "score":        round(score, 1),
            "rsi":          round(rsi, 1),
            "adx":          round(adx_val, 1),
            "vol_surge":    round(vol_surge, 1),
            "base_range":   round(base_range * 100, 1),
            "vol_dryup":    round(vol_ratio, 2),
            "buy_pressure": round(buy_pressure, 1),
            "stock_r60":    round(stock_r60 * 100, 1),
            "market":       market_trend,
            "shares":       shares,
            "position_val": position_val,
            "risk_amt":     round(shares * (entry - sl), 0),
        }

    except Exception as e:
        print(f"    Error {ticker}: {e}")
        return None

# ═══════════════════════════════════════════════
#  MAIN SCAN
# ═══════════════════════════════════════════════
def run_scan():
    print("=" * 58)
    print("  VCP SCANNER — Synced to Backtest v1 (27.1% CAGR)")
    print("=" * 58)

    print("\n  Checking market regime...")
    regime, nifty_r60 = get_market_regime()

    print(f"  Market Regime : {regime}")
    print(f"  Nifty 60d     : {round(nifty_r60*100,1)}%")
    print(f"  Capital       : ₹{CAPITAL:,.0f}")
    print(f"  Risk/trade    : {int(RISK_PER_TRADE*100)}% = ₹{int(CAPITAL*RISK_PER_TRADE):,}")
    print(f"  Hard SL Cap   : {int(MAX_RISK_PCT*100)}%")
    print(f"  T1 Target     : {RR_RATIO_T1}R  |  T2: {RR_RATIO_T2}R")

    if regime == "BEARISH":
        msg = (
            f"⚠️ <b>MARKET IS BEARISH</b>\n\n"
            f"Nifty is below EMA50.\n"
            f"No trades today.\n\n"
            f"Regime    : {regime}\n"
            f"Nifty 60d : {round(nifty_r60*100,1)}%"
        )
        from telegram_bot import send_message
        send_message(msg)
        print("\n  ⚠️  BEARISH — scan stopped. No trades.")
        return

    stocks  = fetch_nifty200()
    signals = []
    total   = len(stocks)
    print(f"\n  Scanning {total} stocks...\n")

    for i, ticker in enumerate(stocks):
        print(f"  [{i+1:>3}/{total}] {ticker:<22}", end=" ", flush=True)
        sig = detect_vcp_signal(ticker, regime, nifty_r60)
        if sig:
            signals.append(sig)
            print(
                f"✅ Score:{sig['score']}  "
                f"ADX:{sig['adx']}  "
                f"Vol:{sig['vol_surge']}x  "
                f"RSI:{sig['rsi']}  "
                f"Shares:{sig['shares']}"
            )
        else:
            print("—")
        time.sleep(0.3)

    print(f"\n{'='*58}")
    print(f"  SCAN COMPLETE — {len(signals)} signal(s) found")
    print(f"{'='*58}\n")

    if not signals:
        send_no_signal_alert()
        print("  No signals today. Telegram notified.")
        return

    signals.sort(key=lambda x: x["score"], reverse=True)

    for sig in signals:
        reward_t1 = round(sig["shares"] * (sig["target1"] - sig["entry"]), 0)
        reward_t2 = round(sig["shares"] * (sig["target2"] - sig["entry"]), 0)
        sl_pct    = round((sig["entry"] - sig["sl"]) / sig["entry"] * 100, 1)

        print(f"  ✅ {sig['ticker']:<12} Score:{sig['score']}  Regime:{sig['market']}")
        print(f"     Entry : ₹{sig['entry']}   SL : ₹{sig['sl']} (-{sl_pct}%)   "
              f"T1 : ₹{sig['target1']}   T2 : ₹{sig['target2']}")
        print(f"     Shares: {sig['shares']}   "
              f"Deploy: ₹{sig['position_val']:,.0f}   "
              f"Risk: ₹{sig['risk_amt']:,.0f}   "
              f"T1 profit: ₹{reward_t1:,.0f}   "
              f"T2 profit: ₹{reward_t2:,.0f}")
        print(f"     ADX:{sig['adx']}  RSI:{sig['rsi']}  "
              f"Vol:{sig['vol_surge']}x  Base:{sig['base_range']}%  "
              f"VolDryup:{sig['vol_dryup']}  BuyPressure:{sig['buy_pressure']}")
        print()

        send_entry_alert(sig)
        add_trade(sig)
        time.sleep(1)

    # Capital check
    total_deploy = sum(s["position_val"] for s in signals)
    total_risk   = sum(s["risk_amt"] for s in signals)
    print(f"  Capital summary:")
    print(f"  Total to deploy : ₹{total_deploy:,.0f}")
    print(f"  Total at risk   : ₹{total_risk:,.0f}")
    print(f"  Available cap   : ₹{CAPITAL:,.0f}")
    if total_deploy > CAPITAL * 0.80:
        print(f"\n  ⚠️  WARNING: Signals need ₹{total_deploy:,.0f} but cap is ₹{CAPITAL:,.0f}")
        print(f"  → Take only TOP {min(len(signals), 2)} signals by score")
        print(f"  → Top 2 signals: {[s['ticker'] for s in signals[:2]]}")

if __name__ == "__main__":
    run_scan()
