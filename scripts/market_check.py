import os
import time
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from io import StringIO


# ============================================================
# CONFIG
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HISTORY_PERIOD = "1y"
BATCH_SIZE = 40

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.nseindia.com/",
}


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        raise Exception("Telegram secrets (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID) are missing.")

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    max_length = 4000

    while message:
        part = message[:max_length]
        if len(message) > max_length:
            split_at = part.rfind("\n")
            if split_at > 500:
                part = part[:split_at]

        response = requests.post(
            url,
            data={"chat_id": CHAT_ID, "text": part},
            timeout=30
        )

        print("Telegram Response:", response.status_code)
        if response.status_code != 200:
            raise Exception(f"Telegram API Error: {response.text}")

        message = message[len(part):]


# ============================================================
# INDEX DATA
# ============================================================

def get_index_data(symbol):

weekly = yf.Ticker(symbol).history(
    period="5y",
    interval="1wk",
    auto_adjust=False
)

weekly_close = weekly["Close"].dropna()

weekly_delta = weekly_close.diff()
weekly_gain = weekly_delta.clip(lower=0)
weekly_loss = -weekly_delta.clip(upper=0)

weekly_avg_gain = weekly_gain.rolling(14).mean()
weekly_avg_loss = weekly_loss.rolling(14).mean()

weekly_rs = weekly_avg_gain / weekly_avg_loss.replace(0, np.nan)
weekly_rsi_series = 100 - (100 / (1 + weekly_rs))

weekly_rsi = float(
    weekly_rsi_series.dropna().iloc[-1]
)
    
    data = yf.Ticker(symbol).history(
        period=HISTORY_PERIOD,
        interval="1d",
        auto_adjust=False
    )

    if data.empty:
        raise Exception(f"No data returned for {symbol}")

    close = data["Close"].dropna()

    if len(close) < 200:
        raise Exception(f"Not enough historical data for {symbol}")

    current = float(close.iloc[-1])
    previous = float(close.iloc[-2])

high_52w = float(close.tail(252).max())

drawdown = (
    (high_52w - current)
    / high_52w
) * 100

    change = ((current - previous) / previous) * 100

    dma50 = close.rolling(50).mean().iloc[-1]
    dma200 = close.rolling(200).mean().iloc[-1]

    vs50 = ((current - dma50) / dma50) * 100
    vs200 = ((current - dma200) / dma200) * 100

    # RSI 14 (Daily)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    rsi = float(rsi_series.dropna().iloc[-1])

    # Monthly RSI 14
    monthly = yf.Ticker(symbol).history(
        period="10y",
        interval="1mo",
        auto_adjust=False
    )

    monthly_close = monthly["Close"].dropna()

    if len(monthly_close) < 20:
        raise Exception(f"Not enough monthly data for {symbol}")

    monthly_delta = monthly_close.diff()
    monthly_gain = monthly_delta.clip(lower=0)
    monthly_loss = -monthly_delta.clip(upper=0)

    monthly_avg_gain = monthly_gain.rolling(14).mean()
    monthly_avg_loss = monthly_loss.rolling(14).mean()

    monthly_rs = monthly_avg_gain / monthly_avg_loss.replace(0, np.nan)
    monthly_rsi_series = 100 - (100 / (1 + monthly_rs))
    monthly_rsi = float(monthly_rsi_series.dropna().iloc[-1])

    # RSI Status
    if rsi >= 70:
        rsi_status = "OVERBOUGHT"
    elif rsi >= 60:
        rsi_status = "STRONG"
    elif rsi >= 50:
        rsi_status = "POSITIVE"
    elif rsi >= 40:
        rsi_status = "WEAK"
    elif rsi >= 30:
        rsi_status = "VERY WEAK"
    else:
        rsi_status = "OVERSOLD"

    # Trend Determination
    if current > dma50 and dma50 > dma200 and monthly_rsi >= 60:
        trend = "STRONG UPTREND"
    elif current > dma50 and dma50 > dma200:
        trend = "UPTREND"
    elif current < dma50 and dma50 < dma200:
        trend = "DOWNTREND"
    else:
        trend = "NEUTRAL"

return {
    "close": round(current, 2),
    "change": round(change, 2),

    "dma50": round(float(dma50), 2),
    "dma200": round(float(dma200), 2),

    "vs50": round(float(vs50), 2),
    "vs200": round(float(vs200), 2),

    "rsi": round(rsi, 2),
    "weekly_rsi": round(weekly_rsi, 2),
    "monthly_rsi": round(monthly_rsi, 2),

    "high_52w": round(high_52w, 2),
    "drawdown": round(drawdown, 2),

    "rsi_status": rsi_status,
    "trend": trend
}


# ============================================================
# NSE INDEX CSV & VALUATION
# ============================================================

def get_nse_index_csv(date_obj):
    date_text = date_obj.strftime("%d%m%Y")
    url = f"https://archives.nseindia.com/content/indices/ind_close_all_{date_text}.csv"

    try:
        session = requests.Session()
        response = session.get(url, headers=HEADERS, timeout=20)
        
        if response.status_code != 200 or len(response.content) < 5000:
            return None

        return pd.read_csv(StringIO(response.text))
    except Exception as e:
        print(f"NSE CSV error for {date_text}: {e}")
        return None


def get_nse_valuation():
    today = datetime.now()

    for days_back in range(0, 10):
        date_to_check = today - timedelta(days=days_back)
        df = get_nse_index_csv(date_to_check)

        if df is None:
            continue

        df.columns = [str(c).strip() for c in df.columns]

        if "Index Name" not in df.columns:
            continue

        rows = df[df["Index Name"].astype(str).str.strip().str.upper() == "NIFTY 50"]

        if rows.empty:
            continue

        row = rows.iloc[0]

        def safe_float(value):
            try:
                if pd.isna(value):
                    return None
                text = str(value).strip()
                if text in ["", "-", "NA", "N/A"]:
                    return None
                return float(text.replace(",", ""))
            except Exception:
                return None

        pe = safe_float(row.get("P/E"))
        pb = safe_float(row.get("P/B"))
        dividend_yield = safe_float(row.get("Div Yield"))
        close = safe_float(row.get("Closing"))

        return {
            "date": str(row.get("Index Date", date_to_check.strftime("%d-%m-%Y"))),
            "pe": pe,
            "pb": pb,
            "dividend_yield": dividend_yield,
            "close": close
        }

    return {
        "date": "Unavailable",
        "pe": None,
        "pb": None,
        "dividend_yield": None,
        "close": None
    }


# ============================================================
# INDIA VIX
# ============================================================

def get_india_vix():
    try:
        data = yf.Ticker("^INDIAVIX").history(period="1mo", interval="1d", auto_adjust=False)
        if data.empty:
            return None
        close = data["Close"].dropna()
        return round(float(close.iloc[-1]), 2) if not close.empty else None
    except Exception as e:
        print(f"India VIX error: {e}")
        return None


# ============================================================
# CONSTITUENTS
# ============================================================

def get_nse_constituents(url):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    df = pd.read_csv(StringIO(response.text))

    if "Symbol" not in df.columns:
        raise Exception("Symbol column not found in NSE file.")

    symbols = [str(s).strip() + ".NS" for s in df["Symbol"].dropna() if str(s).strip()]
    if not symbols:
        raise Exception("No constituents found.")

    return symbols


def get_nifty100_symbols():
    return get_nse_constituents("https://archives.nseindia.com/content/indices/ind_nifty100list.csv")

def get_midcap150_symbols():
    return get_nse_constituents("https://archives.nseindia.com/content/indices/ind_niftymidcap150list.csv")

def get_smallcap250_symbols():
    return get_nse_constituents("https://archives.nseindia.com/content/indices/ind_niftysmallcap250list.csv")


# ============================================================
# MARKET BREADTH
# ============================================================

def calculate_breadth(symbols):
    total, above50, above200 = 0, 0, 0

    for start in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[start:start + BATCH_SIZE]
        print(f"Breadth {start + 1}-{start + len(batch)} of {len(symbols)}")

        try:
            data = yf.download(
                tickers=batch,
                period=HISTORY_PERIOD,
                interval="1d",
                auto_adjust=False,
                progress=False
            )
        except Exception as e:
            print(f"Batch error: {e}")
            continue

        for symbol in batch:
            try:
                if len(batch) == 1:
                    close = data["Close"]
                else:
                    close = data["Close"][symbol] if "Close" in data and symbol in data["Close"] else None

                if close is None:
                    continue

                close = close.dropna()
                if len(close) < 200:
                    continue

                current = float(close.iloc[-1])
                dma50 = close.rolling(50).mean().iloc[-1]
                dma200 = close.rolling(200).mean().iloc[-1]

                total += 1
                if current > dma50:
                    above50 += 1
                if current > dma200:
                    above200 += 1

            except Exception as e:
                continue

        time.sleep(1)

    if total == 0:
        return {"total": 0, "above50": 0, "above200": 0, "pct50": 0, "pct200": 0}

    return {
        "total": total,
        "above50": above50,
        "above200": above200,
        "pct50": round(above50 / total * 100, 1),
        "pct200": round(above200 / total * 100, 1)
    }


# ============================================================
# SCORING FUNCTIONS
# ============================================================

def technical_score(data):
    score = 0
    if data["close"] > data["dma50"]:
        score += 40
    if data["close"] > data["dma200"]:
        score += 30
    if data["dma50"] > data["dma200"]:
        score += 30
    return score


def breadth_score(breadth):
    if breadth["total"] == 0:
        return 0
    return round(breadth["pct50"] * 0.40 + breadth["pct200"] * 0.60, 1)


def rsi_score(rsi):
    if 55 <= rsi < 65:
        return 100
    if 50 <= rsi < 55:
        return 85
    if 65 <= rsi < 70:
        return 80
    if 45 <= rsi < 50:
        return 65
    if 40 <= rsi < 45:
        return 50
    if 70 <= rsi < 75:
        return 55
    if rsi >= 75:
        return 35
    if 30 <= rsi < 40:
        return 40
    return 25


def segment_technical_score(index_data, breadth):
    tech = technical_score(index_data)
    breadth_val = breadth_score(breadth)
    rsi_val = rsi_score(index_data["rsi"])
    return round(tech * 0.40 + breadth_val * 0.40 + rsi_val * 0.20, 1)


def calculate_valuation_score(pe, pb, dividend_yield):
    # PE Score
    if pe is None:
        pe_score = 50
    elif pe <= 16:
        pe_score = 100
    elif pe <= 18:
        pe_score = 90
    elif pe <= 20.5:
        pe_score = 80
    elif pe <= 22:
        pe_score = 70
    elif pe <= 24:
        pe_score = 55
    elif pe <= 27:
        pe_score = 40
    else:
        pe_score = 25

    # PB Score
    if pb is None:
        pb_score = 50
    elif pb <= 2:
        pb_score = 100
    elif pb <= 2.5:
        pb_score = 90
    elif pb <= 3:
        pb_score = 80
    elif pb <= 3.5:
        pb_score = 70
    elif pb <= 4:
        pb_score = 55
    elif pb <= 5:
        pb_score = 40
    else:
        pb_score = 25

    # Dividend Yield Score
    if dividend_yield is None:
        dy_score = 50
    elif dividend_yield >= 2:
        dy_score = 100
    elif dividend_yield >= 1.5:
        dy_score = 85
    elif dividend_yield >= 1.2:
        dy_score = 70
    elif dividend_yield >= 1:
        dy_score = 55
    else:
        dy_score = 40

    return round(pe_score * 0.55 + pb_score * 0.30 + dy_score * 0.15, 1)


def vix_score(vix):
    if vix is None:
        return 50
    if vix < 12:
        return 70
    if vix < 15:
        return 85
    if vix < 18:
        return 75
    if vix < 22:
        return 60
    if vix < 28:
        return 40
    if vix < 35:
        return 25
    return 15

def god_score(
    price,
    dma50,
    dma200,
    weekly_rsi,
    monthly_rsi,
    drawdown,
    vix,
    breadth
):
    score = 50

    if price < dma200:
        score += 15
    elif price < dma50:
        score += 8
    elif price > dma50 * 1.12:
        score -= 12

    if dma50 < dma200:
        score += 10

    if monthly_rsi > 72 and weekly_rsi > 68:
        score -= 20
    elif monthly_rsi > 65:
        score -= 10
    elif monthly_rsi < 35 and weekly_rsi < 30:
        score += 25
    elif weekly_rsi < 40:
        score += 12

    if drawdown >= 15:
        score += 20
    elif drawdown >= 8:
        score += 12
    elif drawdown >= 3:
        score += 5

    if vix > 24:
        score += 10
    elif vix < 11.5:
        score -= 8

    if breadth < 25:
        score += 10
    elif breadth > 85:
        score -= 8

    return max(0,min(100,score))



def score_status(score):
    if score >= 80:
        return "VERY STRONG 🟢"
    if score >= 70:
        return "STRONG 🟢"
    if score >= 60:
        return "POSITIVE 🟢"
    if score >= 50:
        return "NEUTRAL 🟡"
    if score >= 40:
        return "WEAK 🟠"
    return "VERY WEAK 🔴"


def get_action(score):

    if score >= 90:
        return "🚀 MUST BUY"

    elif score >= 80:
        return "🟢 AGGRESSIVE LONG-TERM BUYING ZONE"

    elif score >= 70:
        return "🟢 AGGRESSIVE BUY"

    elif score >= 60:
        return "🟢 BUY ON DIPS"

    elif score >= 50:
        return "🟡 SIP ONLY"

    elif score >= 35:
        return "🟠 AVOID LARGE LUMPSUM"

    else:
        return "🔴 EXPENSIVE"


def get_allocation(overall, large, mid, small):
    if overall >= 80:
        allocation = {"large": 55, "mid": 30, "small": 15}
    elif overall >= 70:
        allocation = {"large": 60, "mid": 25, "small": 15}
    elif overall >= 60:
        allocation = {"large": 65, "mid": 25, "small": 10}
    elif overall >= 50:
        allocation = {"large": 70, "mid": 20, "small": 10}
    elif overall >= 40:
        allocation = {"large": 80, "mid": 15, "small": 5}
    else:
        allocation = {"large": 90, "mid": 10, "small": 0}

    # Small/Mid Cap risk protection adjustments
    if small < 50:
        shift = min(allocation["small"], 5)
        allocation["small"] -= shift
        allocation["large"] += shift

    if mid < 50:
        shift = min(allocation["mid"], 5)
        allocation["mid"] -= shift
        allocation["large"] += shift

    return allocation


def investment_strategy(score, price, dma200, monthly_rsi):
    if score >= 65 or (price < dma200 and monthly_rsi < 45):
        return {
            "stage": "🟢 DARK GREEN",
            "sip": "100%",
            "lumpsum": "100% Deploy",
            "action": "AGGRESSIVE BUY: SIP + ALL AVAILABLE SURPLUS CASH | Loan Prepayment 0%"
        }
    elif 51 <= score <= 64 or price < dma200:
        return {
            "stage": "🟢 LIGHT GREEN",
            "sip": "100%",
            "lumpsum": "50% Deploy",
            "action": "BUY | Loan Prepayment 0%"
        }
    elif 40 <= score <= 50:
        return {
            "stage": "🟡 YELLOW",
            "sip": "100%",
            "lumpsum": "0% Deploy",
            "action": "Continue SIP | 50% Home Loan Prepayment"
        }
    elif 25 <= score <= 39 or (60 < monthly_rsi < 70):
        return {
            "stage": "🟠 ORANGE",
            "sip": "100%",
            "lumpsum": "0% Deploy",
            "action": "70% Home Loan Prepayment / Gold ETF"
        }
    else:
        return {
            "stage": "🔴 RED",
            "sip": "0%",
            "lumpsum": "0% Deploy",
            "action": "Rebalancing / SELL 20% Small Cap → Shift to Loan Prepayment"
        }


# ============================================================
# MAIN EXECUTION
# ============================================================

if __name__ == "__main__":
    try:
        print("======================================")
        print("AI WEALTH MANAGER STARTED")
        print("======================================")

        # Index Data
        print("Getting index data...")
        nifty50 = get_index_data("^NSEI")
        nifty100 = get_index_data("^CNX100")
        midcap150 = get_index_data("NIFTYMIDCAP150.NS")
        smallcap250 = get_index_data("NIFTYSMLCAP250.NS")
        nifty500 = get_index_data("^CRSLDX")
        sensex = get_index_data("^BSESN")

        # Valuation
        print("Getting NSE valuation...")
        valuation_data = get_nse_valuation()
        pe, pb, dividend_yield = valuation_data["pe"], valuation_data["pb"], valuation_data["dividend_yield"]

        # VIX
        print("Getting India VIX...")
        india_vix = get_india_vix()

        # Constituents
        print("Getting constituents...")
        nifty100_symbols = get_nifty100_symbols()
        midcap150_symbols = get_midcap150_symbols()
        smallcap250_symbols = get_smallcap250_symbols()

        # Breadth
        print("Calculating Large Cap breadth...")
        large_breadth = calculate_breadth(nifty100_symbols)

        print("Calculating Mid Cap breadth...")
        mid_breadth = calculate_breadth(midcap150_symbols)

        print("Calculating Small Cap breadth...")
        small_breadth = calculate_breadth(smallcap250_symbols)

        # Technical Scores
        large_technical = segment_technical_score(nifty100, large_breadth)
        mid_technical = segment_technical_score(midcap150, mid_breadth)
        small_technical = segment_technical_score(smallcap250, small_breadth)

        valuation_score_value = calculate_valuation_score(pe, pb, dividend_yield)
        vix_score_value = vix_score(india_vix)

        nifty500_technical = technical_score(nifty500)
        overall_technical = round(
            large_technical * 0.40 + mid_technical * 0.30 + small_technical * 0.20 + nifty500_technical * 0.10, 1
        )

        # Final Scores & Status
      overall_score = round(
    large_score * 0.50 +
    mid_score * 0.30 +
    small_score * 0.20,
    1
)

large_score = god_score(
    nifty100["close"],
    nifty100["dma50"],
    nifty100["dma200"],
    nifty100["weekly_rsi"],
    nifty100["monthly_rsi"],
    nifty100["drawdown"],
    india_vix,
    large_breadth["pct200"]
)

mid_score = god_score(
    midcap150["close"],
    midcap150["dma50"],
    midcap150["dma200"],
    midcap150["weekly_rsi"],
    midcap150["monthly_rsi"],
    midcap150["drawdown"],
    india_vix,
    mid_breadth["pct200"]
)

small_score = god_score(
    smallcap250["close"],
    smallcap250["dma50"],
    smallcap250["dma200"],
    smallcap250["weekly_rsi"],
    smallcap250["monthly_rsi"],
    smallcap250["drawdown"],
    india_vix,
    small_breadth["pct200"]
)

        overall_status = score_status(overall_score)
        large_status = score_status(large_score)
        mid_status = score_status(mid_score)
        small_status = score_status(small_score)

        overall_action = get_action(overall_score)
        large_action = get_action(large_score)
        mid_action = get_action(mid_score)
        small_action = get_action(small_score)

        allocation = get_allocation(overall_score, large_score, mid_score, small_score)
        strategy = investment_strategy(overall_score, nifty50["close"], nifty50["dma200"], nifty50["monthly_rsi"])

        pe_text = f"{pe:.2f}" if pe is not None else "N/A"
        pb_text = f"{pb:.2f}" if pb is not None else "N/A"
        dy_text = f"{dividend_yield:.2f}%" if dividend_yield is not None else "N/A"
        vix_text = f"{india_vix:.2f}" if india_vix is not None else "N/A"

        # Report Framing
        message = f"""🤖 AI WEALTH MANAGER
📊 DAILY MARKET INTELLIGENCE
━━━━━━━━━━━━━━━━━━━━━━━━

🎯 FINAL MARKET SCORE

{overall_score}/100
{overall_status}

ACTION: {overall_action}

━━━━━━━━━━━━━━━━━━━━━━━━

🌐 MARKET VALUATION

NIFTY 50 PE: {pe_text}
NIFTY 50 PB: {pb_text}
DIVIDEND YIELD: {dy_text}
VALUATION SCORE: {valuation_score_value}/100
VALUATION DATA DATE: {valuation_data['date']}

━━━━━━━━━━━━━━━━━━━━━━━━

⚡ INDIA VIX

Current VIX: {vix_text}
VIX SCORE: {vix_score_value}/100

━━━━━━━━━━━━━━━━━━━━━━━━

🟢 LARGE CAP : NIFTY 100

Price: {nifty100['close']}
Daily Change: {nifty100['change']}%
50 DMA: {nifty100['dma50']}
200 DMA: {nifty100['dma200']}
Price vs 50 DMA: {nifty100['vs50']}%
Price vs 200 DMA: {nifty100['vs200']}%
Monthly RSI: {nifty100['monthly_rsi']}
Trend: {nifty100['trend']}
Breadth >50 DMA: {large_breadth['pct50']}%
Breadth >200 DMA: {large_breadth['pct200']}%
Stocks Analyzed: {large_breadth['total']}

🎯 LARGE CAP SCORE: {large_score}/100
{large_status}
ACTION: {large_action}

━━━━━━━━━━━━━━━━━━━━━━━━

🟡 MID CAP : NIFTY MIDCAP 150

Price: {midcap150['close']}
Daily Change: {midcap150['change']}%
50 DMA: {midcap150['dma50']}
200 DMA: {midcap150['dma200']}
Price vs 50 DMA: {midcap150['vs50']}%
Price vs 200 DMA: {midcap150['vs200']}%
Monthly RSI: {midcap150['monthly_rsi']}
Trend: {midcap150['trend']}
Breadth >50 DMA: {mid_breadth['pct50']}%
Breadth >200 DMA: {mid_breadth['pct200']}%
Stocks Analyzed: {mid_breadth['total']}

🎯 MID CAP SCORE: {mid_score}/100
{mid_status}
ACTION: {mid_action}

━━━━━━━━━━━━━━━━━━━━━━━━

🔴 SMALL CAP : NIFTY SMALLCAP 250

Price: {smallcap250['close']}
Daily Change: {smallcap250['change']}%
50 DMA: {smallcap250['dma50']}
200 DMA: {smallcap250['dma200']}
Price vs 50 DMA: {smallcap250['vs50']}%
Price vs 200 DMA: {smallcap250['vs200']}%
Monthly RSI: {smallcap250['monthly_rsi']}
Trend: {smallcap250['trend']}
Breadth >50 DMA: {small_breadth['pct50']}%
Breadth >200 DMA: {small_breadth['pct200']}%
Stocks Analyzed: {small_breadth['total']}

🎯 SMALL CAP SCORE: {small_score}/100
{small_status}
ACTION: {small_action}

━━━━━━━━━━━━━━━━━━━━━━━━

🇮🇳 NIFTY 50

Price: {nifty50['close']}
Daily Change: {nifty50['change']}%
Monthly RSI: {nifty50['monthly_rsi']}
Trend: {nifty50['trend']}

━━━━━━━━━━━━━━━━━━━━━━━━

🇮🇳 SENSEX

Price: {sensex['close']}
Daily Change: {sensex['change']}%
Monthly RSI: {sensex['monthly_rsi']}
Trend: {sensex['trend']}

━━━━━━━━━━━━━━━━━━━━━━━━

💰 INVESTMENT STRATEGY

MARKET STAGE: {strategy['stage']}
Equity SIP: {strategy['sip']}
Lump Sum: {strategy['lumpsum']}
Recommendation: {strategy['action']}

━━━━━━━━━━━━━━━━━━━━━━━━

💰 SUGGESTED ALLOCATION

Large Cap: {allocation['large']}%
Mid Cap: {allocation['mid']}%
Small Cap: {allocation['small']}%
"""

        # Dispatch via Telegram
        send_telegram(message)
        print("Market intelligence report generated and sent successfully!")

    except Exception as e:
        print(f"Error running AI Wealth Manager: {e}")
