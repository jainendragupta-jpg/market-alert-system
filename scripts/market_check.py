import os
import time
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


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
        "Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/json,text/plain,*/*",
}


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not TOKEN or not CHAT_ID:
        raise Exception(
            "Telegram secrets are missing."
        )

    url = (
        f"https://api.telegram.org/"
        f"bot{TOKEN}/sendMessage"
    )

    max_length = 4000

    while message:

        part = message[:max_length]

        if len(message) > max_length:

            split_at = part.rfind("\n")

            if split_at > 500:
                part = part[:split_at]

        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": part
            },
            timeout=30
        )

        print(
            "Telegram:",
            response.status_code,
            response.text
        )

        if response.status_code != 200:
            raise Exception(
                response.text
            )

        message = message[len(part):]


# ============================================================
# INDEX DATA
# ============================================================

def get_index_data(symbol):

    data = yf.Ticker(symbol).history(
        period=HISTORY_PERIOD,
        interval="1d",
        auto_adjust=False
    )

    if data.empty:
        raise Exception(
            f"No data returned for {symbol}"
        )

    close = data["Close"].dropna()

    if len(close) < 200:
        raise Exception(
            f"Not enough data for {symbol}"
        )

    current = float(close.iloc[-1])
    previous = float(close.iloc[-2])

    change = (
        (current - previous)
        / previous
    ) * 100

    dma50 = close.rolling(50).mean().iloc[-1]
    dma200 = close.rolling(200).mean().iloc[-1]

    vs50 = (
        (current - dma50)
        / dma50
    ) * 100

    vs200 = (
        (current - dma200)
        / dma200
    ) * 100

    # --------------------------------------------------------
    # RSI 14
    # --------------------------------------------------------

    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss.replace(
        0,
        np.nan
    )

    rsi_series = (
        100
        -
        (100 / (1 + rs))
    )

    rsi = float(
        rsi_series.dropna().iloc[-1]
    )

    # --------------------------------------------------------
    # RSI STATUS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    if (
        current > dma50
        and dma50 > dma200
    ):
        trend = "STRONG UPTREND"

    elif (
        current > dma50
        and dma50 > dma200
    ):
        trend = "UPTREND"

    elif (
        current < dma50
        and dma50 < dma200
    ):
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
        "rsi_status": rsi_status,
        "trend": trend
    }


# ============================================================
# NSE INDEX CSV
# ============================================================

def get_nse_index_csv(date_obj):

    date_text = date_obj.strftime("%d%m%Y")

    url = (
        "https://archives.nseindia.com/"
        "content/indices/"
        f"ind_close_all_{date_text}.csv"
    )

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        if response.status_code != 200:
            return None

        if len(response.content) < 5000:
            return None

        from io import StringIO

        df = pd.read_csv(
            StringIO(response.text)
        )

        return df

    except Exception as e:

        print(
            "NSE CSV error:",
            e
        )

        return None


# ============================================================
# NSE VALUATION DATA
# ============================================================

def get_nse_valuation():

    today = datetime.now()

    for days_back in range(0, 10):

        date_to_check = (
            today
            - timedelta(
                days=days_back
            )
        )

        df = get_nse_index_csv(
            date_to_check
        )

        if df is None:
            continue

        df.columns = [
            str(c).strip()
            for c in df.columns
        ]

        if "Index Name" not in df.columns:
            continue

        rows = df[
            df["Index Name"]
            .astype(str)
            .str.strip()
            .str.upper()
            == "NIFTY 50"
        ]

        if rows.empty:
            continue

        row = rows.iloc[0]

        def safe_float(value):

            try:

                if pd.isna(value):
                    return None

                text = str(value).strip()

                if text in [
                    "",
                    "-",
                    "NA",
                    "N/A"
                ]:
                    return None

                return float(
                    text.replace(
                        ",",
                        ""
                    )
                )

            except Exception:

                return None

        pe = safe_float(
            row.get("P/E")
        )

        pb = safe_float(
            row.get("P/B")
        )

        dividend_yield = safe_float(
            row.get("Div Yield")
        )

        close = safe_float(
            row.get("Closing")
        )

        return {
            "date": str(
                row.get(
                    "Index Date",
                    date_to_check.strftime(
                        "%d-%m-%Y"
                    )
                )
            ),
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

        data = yf.Ticker(
            "^INDIAVIX"
        ).history(
            period="1mo",
            interval="1d",
            auto_adjust=False
        )

        if data.empty:
            return None

        close = data["Close"].dropna()

        if close.empty:
            return None

        return round(
            float(close.iloc[-1]),
            2
        )

    except Exception as e:

        print(
            "India VIX error:",
            e
        )

        return None


# ============================================================
# CONSTITUENTS
# ============================================================

def get_nse_constituents(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    from io import StringIO

    df = pd.read_csv(
        StringIO(response.text)
    )

    symbols = []

    if "Symbol" not in df.columns:
        raise Exception(
            "Symbol column not found in NSE file."
        )

    for symbol in df["Symbol"].dropna():

        symbol = str(symbol).strip()

        if symbol:

            symbols.append(
                symbol + ".NS"
            )

    if not symbols:

        raise Exception(
            "No constituents found."
        )

    return symbols


def get_nifty100_symbols():

    return get_nse_constituents(
        "https://archives.nseindia.com/"
        "content/indices/"
        "ind_nifty100list.csv"
    )


def get_midcap150_symbols():

    return get_nse_constituents(
        "https://archives.nseindia.com/"
        "content/indices/"
        "ind_niftymidcap150list.csv"
    )


def get_smallcap250_symbols():

    return get_nse_constituents(
        "https://archives.nseindia.com/"
        "content/indices/"
        "ind_niftysmallcap250list.csv"
    )


# ============================================================
# MARKET BREADTH
# ============================================================

def calculate_breadth(symbols):

    total = 0
    above20 = 0
    above50 = 0
    above200 = 0

    for start in range(
        0,
        len(symbols),
        BATCH_SIZE
    ):

        batch = symbols[
            start:
            start + BATCH_SIZE
        ]

        print(
            f"Breadth "
            f"{start + 1}-"
            f"{start + len(batch)} "
            f"of {len(symbols)}"
        )

        try:

            data = yf.download(
                tickers=batch,
                period=HISTORY_PERIOD,
                interval="1d",
                auto_adjust=False,
                group_by="ticker",
                threads=True,
                progress=False
            )

        except Exception as e:

            print(
                "Batch error:",
                e
            )

            continue

        for symbol in batch:

            try:

                if (
                    len(batch) == 1
                    and "Close" in data
                ):

                    close = data["Close"]

                else:

                    if not hasattr(
                        data.columns,
                        "levels"
                    ):
                        continue

                    if (
                        symbol
                        not in data.columns.levels[0]
                    ):
                        continue

                    close = data[
                        symbol
                    ]["Close"]

                close = (
                    close
                    .dropna()
                )

                if len(close) < 200:
                    continue

                current = float(
                    close.iloc[-1]
                )

                dma20 = (
                    close
                    .rolling(20)
                    .mean()
                    .iloc[-1]
                )

                dma50 = (
                    close
                    .rolling(50)
                    .mean()
                    .iloc[-1]
                )

                dma200 = (
                    close
                    .rolling(200)
                    .mean()
                    .iloc[-1]
                )

                total += 1

                if current > dma20:
                    above20 += 1

                if current > dma50:
                    above50 += 1

                if current > dma200:
                    above200 += 1

            except Exception as e:

                print(
                    f"Skipping {symbol}: {e}"
                )

                continue

        time.sleep(1)

    if total == 0:

        return {
            "total": 0,
            "above20": 0,
            "above50": 0,
            "above200": 0,
            "pct20": 0,
            "pct50": 0,
            "pct200": 0
        }

    return {
        "total": total,
        "above20": above20,
        "above50": above50,
        "above200": above200,
        "pct20": round(
            above20 / total * 100,
            1
        ),
        "pct50": round(
            above50 / total * 100,
            1
        ),
        "pct200": round(
            above200 / total * 100,
            1
        )
    }


# ============================================================
# TECHNICAL SCORE
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


# ============================================================
# BREADTH SCORE
# ============================================================

def breadth_score(breadth):

    if breadth["total"] == 0:
        return 0

    return round(
        breadth["pct50"] * 0.40 +
        breadth["pct200"] * 0.60,
        1
    )


# ============================================================
# RSI SCORE
# ============================================================

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


# ============================================================
# SEGMENT TECHNICAL SCORE
# ============================================================

def segment_technical_score(
    index_data,
    breadth
):

    tech = technical_score(
        index_data
    )

    breadth_value = breadth_score(
        breadth
    )

    rsi_value = rsi_score(
        index_data["rsi"]
    )

    return round(
        tech * 0.40
        +
        breadth_value * 0.40
        +
        rsi_value * 0.20,
        1
    )


# ============================================================
# VALUATION SCORE
# ============================================================

def calculate_valuation_score(
    pe,
    pb,
    dividend_yield
):

    # --------------------------------------------------------
    # PE SCORE
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # PB SCORE
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # DIVIDEND YIELD SCORE
    # --------------------------------------------------------

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


    return round(
        pe_score * 0.55
        +
        pb_score * 0.30
        +
        dy_score * 0.15,
        1
    )


# ============================================================
# VIX SCORE
# ============================================================

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


# ============================================================
# FINAL MARKET SCORE
# ============================================================

def final_market_score(
    technical,
    valuation,
    vix
):

    score = (
        technical * 0.50
        +
        valuation * 0.30
        +
        vix * 0.20
    )

    return round(
        min(
            max(score, 0),
            100
        ),
        1
    )


# ============================================================
# STATUS
# ============================================================

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


# ============================================================
# ACTION
# ============================================================

def get_action(score):

    if score >= 80:
        return "INVEST AGGRESSIVELY 🟢"

    if score >= 70:
        return "INVEST 🟢"

    if score >= 60:
        return "SELECTIVE INVEST 🟢"

    if score >= 50:
        return "HOLD / SIP 🟡"

    if score >= 40:
        return "REDUCE NEW INVESTMENT 🟠"

    return "WAIT / DEFENSIVE 🔴"


# ============================================================
# ALLOCATION
# ============================================================

def get_allocation(
    overall,
    large,
    mid,
    small
):

    if overall >= 80:

        allocation = {
            "large": 55,
            "mid": 30,
            "small": 15
        }

    elif overall >= 70:

        allocation = {
            "large": 60,
            "mid": 25,
            "small": 15
        }

    elif overall >= 60:

        allocation = {
            "large": 65,
            "mid": 25,
            "small": 10
        }

    elif overall >= 50:

        allocation = {
            "large": 70,
            "mid": 20,
            "small": 10
        }

    elif overall >= 40:

        allocation = {
            "large": 80,
            "mid": 15,
            "small": 5
        }

    else:

        allocation = {
            "large": 90,
            "mid": 10,
            "small": 0
        }


    # Small cap protection

    if small < 50:

        shift = min(
            allocation["small"],
            5
        )

        allocation["small"] -= shift
        allocation["large"] += shift


    # Mid cap protection

    if mid < 50:

        shift = min(
            allocation["mid"],
            5
        )

        allocation["mid"] -= shift
        allocation["large"] += shift


    return allocation


def investment_strategy(score, price, dma200, rsi):

    if score >= 65 or (price < dma200 and rsi < 45):
        return {
            "stage": "🟢 DARK GREEN",
            "sip": "100%",
            "lumpsum": "100%",
            "action": "AGGRESSIVE BUY"
        }

    elif score >= 51:
        return {
            "stage": "🟢 LIGHT GREEN",
            "sip": "100%",
            "lumpsum": "50%",
            "action": "BUY"
        }

    elif score >= 40:
        return {
            "stage": "🟡 YELLOW",
            "sip": "100%",
            "lumpsum": "0%",
            "action": "50% HOME LOAN PREPAYMENT"
        }

    elif score >= 25 or (60 < rsi < 70):
        return {
            "stage": "🟠 ORANGE",
            "sip": "100%",
            "lumpsum": "0%",
            "action": "70% LOAN PREPAYMENT / Buy GOLD ETF"
        }

    else:
        return {
            "stage": "🔴 RED",
            "sip": "0%",
            "lumpsum": "0%",
            "action": "SELL 20% SMALLCAP"
        }


# ============================================================
# MAIN
# ============================================================

try:

    print(
        "======================================"
    )

    print(
        "AI WEALTH MANAGER STARTED"
    )

    print(
        "======================================"
    )


    # ========================================================
    # INDEX DATA
    # ========================================================

    print("Getting index data...")

    nifty50 = get_index_data(
        "^NSEI"
    )

    nifty100 = get_index_data(
        "^CNX100"
    )

    midcap150 = get_index_data(
        "NIFTYMIDCAP150.NS"
    )

    smallcap250 = get_index_data(
        "NIFTYSMLCAP250.NS"
    )

    nifty500 = get_index_data(
        "^CRSLDX"
    )

    sensex = get_index_data(
        "^BSESN"
    )


    # ========================================================
    # NSE VALUATION DATA
    # ========================================================

    print(
        "Getting NSE valuation..."
    )

    valuation_data = get_nse_valuation()

    pe = valuation_data["pe"]

    pb = valuation_data["pb"]

    dividend_yield = (
        valuation_data["dividend_yield"]
    )

    print(
        "Nifty 50 PE:",
        pe
    )

    print(
        "Nifty 50 PB:",
        pb
    )

    print(
        "Dividend Yield:",
        dividend_yield
    )


    # ========================================================
    # INDIA VIX
    # ========================================================

    print(
        "Getting India VIX..."
    )

    india_vix = get_india_vix()

    print(
        "India VIX:",
        india_vix
    )


    # ========================================================
    # CONSTITUENTS
    # ========================================================

    print(
        "Getting constituents..."
    )

    nifty100_symbols = (
        get_nifty100_symbols()
    )

    midcap150_symbols = (
        get_midcap150_symbols()
    )

    smallcap250_symbols = (
        get_smallcap250_symbols()
    )


    # ========================================================
    # BREADTH
    # ========================================================

    print(
        "Calculating Large Cap breadth..."
    )

    large_breadth = calculate_breadth(
        nifty100_symbols
    )


    print(
        "Calculating Mid Cap breadth..."
    )

    mid_breadth = calculate_breadth(
        midcap150_symbols
    )


    print(
        "Calculating Small Cap breadth..."
    )

    small_breadth = calculate_breadth(
        smallcap250_symbols
    )


    # ========================================================
    # TECHNICAL SCORES
    # ========================================================

    large_technical = (
        segment_technical_score(
            nifty100,
            large_breadth
        )
    )

    mid_technical = (
        segment_technical_score(
            midcap150,
            mid_breadth
        )
    )

    small_technical = (
        segment_technical_score(
            smallcap250,
            small_breadth
        )
    )


    # ========================================================
    # VALUATION SCORE
    #
    # IMPORTANT:
    # Do NOT overwrite valuation_data.
    # ========================================================

    valuation_score_value = (
        calculate_valuation_score(
            pe,
            pb,
            dividend_yield
        )
    )


    # ========================================================
    # VIX SCORE
    # ========================================================

    vix_score_value = vix_score(
        india_vix
    )


    # ========================================================
    # OVERALL TECHNICAL SCORE
    # ========================================================

    nifty500_technical = (
        technical_score(
            nifty500
        )
    )

    overall_technical = round(
        (
            large_technical * 0.40
            +
            mid_technical * 0.30
            +
            small_technical * 0.20
            +
            nifty500_technical * 0.10
        ),
        1
    )


    # ========================================================
    # FINAL OVERALL SCORE
    # ========================================================

    overall_score = final_market_score(
        overall_technical,
        valuation_score_value,
        vix_score_value
    )


    # ========================================================
    # SEGMENT SCORES
    # ========================================================

    large_score = round(
        large_technical * 0.70
        +
        valuation_score_value * 0.20
        +
        vix_score_value * 0.10,
        1
    )

    mid_score = round(
        mid_technical * 0.70
        +
        valuation_score_value * 0.20
        +
        vix_score_value * 0.10,
        1
    )

    small_score = round(
        small_technical * 0.70
        +
        valuation_score_value * 0.20
        +
        vix_score_value * 0.10,
        1
    )


    # ========================================================
    # STATUS
    # ========================================================

    overall_status = score_status(
        overall_score
    )

    large_status = score_status(
        large_score
    )

    mid_status = score_status(
        mid_score
    )

    small_status = score_status(
        small_score
    )


    # ========================================================
    # ACTIONS
    # ========================================================

    overall_action = get_action(
        overall_score
    )

    large_action = get_action(
        large_score
    )

    mid_action = get_action(
        mid_score
    )

    small_action = get_action(
        small_score
    )


    # ========================================================
    # ALLOCATION
    # ========================================================

    allocation = get_allocation(
        overall_score,
        large_score,
        mid_score,
        small_score
    )

    strategy = investment_strategy(
    overall_score,
    nifty50["close"],
    nifty50["dma200"],
    nifty50["rsi"]
)


    # ========================================================
    # SAFE TEXT VALUES
    # ========================================================

    pe_text = (
        f"{pe:.2f}"
        if pe is not None
        else "N/A"
    )

    pb_text = (
        f"{pb:.2f}"
        if pb is not None
        else "N/A"
    )

    dy_text = (
        f"{dividend_yield:.2f}%"
        if dividend_yield is not None
        else "N/A"
    )

    vix_text = (
        f"{india_vix:.2f}"
        if india_vix is not None
        else "N/A"
    )


    # ========================================================
    # TELEGRAM REPORT
    # ========================================================

    message = f"""
🤖 AI WEALTH MANAGER
📊 DAILY MARKET INTELLIGENCE
━━━━━━━━━━━━━━━━━━━━━━━━

🎯 FINAL MARKET SCORE

{overall_score}/100
{overall_status}

ACTION:
{overall_action}

━━━━━━━━━━━━━━━━━━━━━━━━

🌐 MARKET VALUATION

NIFTY 50 PE:
{pe_text}

NIFTY 50 PB:
{pb_text}

DIVIDEND YIELD:
{dy_text}

VALUATION SCORE:
{valuation_score_value}/100

VALUATION DATA DATE:
{valuation_data['date']}

━━━━━━━━━━━━━━━━━━━━━━━━

⚡ INDIA VIX

Current VIX:
{vix_text}

VIX SCORE:
{vix_score_value}/100

━━━━━━━━━━━━━━━━━━━━━━━━

🟢 LARGE CAP
NIFTY 100

Price:
{nifty100['close']}

Daily Change:
{nifty100['change']}%

20 DMA:
{nifty100['dma20']}

50 DMA:
{nifty100['dma50']}

200 DMA:
{nifty100['dma200']}

Price vs 50 DMA:
{nifty100['vs50']}%

Price vs 200 DMA:
{nifty100['vs200']}%

RSI:
{nifty100['rsi']}
({nifty100['rsi_status']})

Trend:
{nifty100['trend']}

Breadth >20 DMA:
{large_breadth['pct20']}%

Breadth >50 DMA:
{large_breadth['pct50']}%

Breadth >200 DMA:
{large_breadth['pct200']}%

Stocks Analyzed:
{large_breadth['total']}

🎯 LARGE CAP SCORE:
{large_score}/100

{large_status}

ACTION:
{large_action}

━━━━━━━━━━━━━━━━━━━━━━━━

🟡 MID CAP
NIFTY MIDCAP 150

Price:
{midcap150['close']}

Daily Change:
{midcap150['change']}%

20 DMA:
{midcap150['dma20']}

50 DMA:
{midcap150['dma50']}

200 DMA:
{midcap150['dma200']}

Price vs 50 DMA:
{midcap150['vs50']}%

Price vs 200 DMA:
{midcap150['vs200']}%

RSI:
{midcap150['rsi']}
({midcap150['rsi_status']})

Trend:
{midcap150['trend']}

Breadth >20 DMA:
{mid_breadth['pct20']}%

Breadth >50 DMA:
{mid_breadth['pct50']}%

Breadth >200 DMA:
{mid_breadth['pct200']}%

Stocks Analyzed:
{mid_breadth['total']}

🎯 MID CAP SCORE:
{mid_score}/100

{mid_status}

ACTION:
{mid_action}

━━━━━━━━━━━━━━━━━━━━━━━━

🔴 SMALL CAP
NIFTY SMALLCAP 250

Price:
{smallcap250['close']}

Daily Change:
{smallcap250['change']}%

20 DMA:
{smallcap250['dma20']}

50 DMA:
{smallcap250['dma50']}

200 DMA:
{smallcap250['dma200']}

Price vs 50 DMA:
{smallcap250['vs50']}%

Price vs 200 DMA:
{smallcap250['vs200']}%

RSI:
{smallcap250['rsi']}
({smallcap250['rsi_status']})

Trend:
{smallcap250['trend']}

Breadth >20 DMA:
{small_breadth['pct20']}%

Breadth >50 DMA:
{small_breadth['pct50']}%

Breadth >200 DMA:
{small_breadth['pct200']}%

Stocks Analyzed:
{small_breadth['total']}

🎯 SMALL CAP SCORE:
{small_score}/100

{small_status}

ACTION:
{small_action}

━━━━━━━━━━━━━━━━━━━━━━━━

🇮🇳 NIFTY 50

Price:
{nifty50['close']}

Daily Change:
{nifty50['change']}%

RSI:
{nifty50['rsi']}

Trend:
{nifty50['trend']}

━━━━━━━━━━━━━━━━━━━━━━━━

🇮🇳 SENSEX

Price:
{sensex['close']}

Daily Change:
{sensex['change']}%

RSI:
{sensex['rsi']}

Trend:
{sensex['trend']}


━━━━━━━━━━━━━━━━━━━━

💰 INVESTMENT STRATEGY

Market Stage:
{strategy['stage']}

Equity SIP:
{strategy['sip']}

Lump Sum:
{strategy['lumpsum']}

Recommendation:
{strategy['action']}

━━━━━━━━━━━━━━━━━━━━━━━━

💰 SUGGESTED ALLOCATION

🟢 LARGE CAP:
{allocation['large']}%

🟡 MID CAP:
{allocation['mid']}%

🔴 SMALL CAP:
{allocation['small']}%

━━━━━━━━━━━━━━━━━━━━━━━━

📌 DECISION FRAMEWORK

80+  → Aggressive Investment
70–79 → Investment
60–69 → Selective Investment
50–59 → Hold / Continue SIP
40–49 → Reduce New Investment
<40 → Wait / Defensive

━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ IMPORTANT

Quantitative decision-support only.
Not a guaranteed-profit system.

Valuation thresholds are initial
rules and will be validated through
historical backtesting.

━━━━━━━━━━━━━━━━━━━━━━━━

🤖 GitHub Actions Active
📱 Telegram Active
📊 AI Wealth Manager
━━━━━━━━━━━━━━━━━━━━━━━━
"""


    # ========================================================
    # SEND TELEGRAM
    # ========================================================

    send_telegram(
        message
    )


    print(
        "======================================"
    )

    print(
        "AI WEALTH MANAGER COMPLETED"
    )

    print(
        "======================================"
    )


except Exception as e:

    error_message = f"""
❌ AI WEALTH MANAGER ERROR

{str(e)}

Please check GitHub Actions logs.
"""

    print(
        error_message
    )

    try:

        send_telegram(
            error_message
        )

    except Exception as telegram_error:

        print(
            "Telegram error:",
            telegram_error
        )
