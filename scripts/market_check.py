import os
import time
import requests
import yfinance as yf
import pandas as pd
import numpy as np


# ============================================================
# CONFIGURATION
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HISTORY_PERIOD = "1y"
BATCH_SIZE = 40


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    """
    Send message to Telegram.
    Telegram has a message length limit, so split long reports.
    """

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    max_length = 4000

    parts = []

    while len(message) > max_length:
        split_position = message.rfind("\n", 0, max_length)

        if split_position == -1:
            split_position = max_length

        parts.append(message[:split_position])
        message = message[split_position:]

    parts.append(message)

    for part in parts:

        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": part
            },
            timeout=30
        )

        print("Telegram Status:", response.status_code)
        print("Telegram Response:", response.text)

        if response.status_code != 200:
            raise Exception(
                f"Telegram error: {response.text}"
            )


# ============================================================
# INDEX DATA
# ============================================================

def get_index_data(symbol):

    data = yf.Ticker(symbol).history(
        period=HISTORY_PERIOD,
        auto_adjust=False
    )

    if data.empty or len(data) < 200:
        raise Exception(
            f"Not enough historical data for {symbol}"
        )

    close_series = data["Close"].dropna()

    close = float(close_series.iloc[-1])
    previous_close = float(close_series.iloc[-2])

    daily_change = (
        (close - previous_close)
        / previous_close
    ) * 100


    # --------------------------------------------------------
    # MOVING AVERAGES
    # --------------------------------------------------------

    dma20 = close_series.rolling(20).mean().iloc[-1]
    dma50 = close_series.rolling(50).mean().iloc[-1]
    dma200 = close_series.rolling(200).mean().iloc[-1]


    # --------------------------------------------------------
    # PRICE VS MOVING AVERAGES
    # --------------------------------------------------------

    price_vs_20 = (
        (close - dma20)
        / dma20
    ) * 100

    price_vs_50 = (
        (close - dma50)
        / dma50
    ) * 100

    price_vs_200 = (
        (close - dma200)
        / dma200
    ) * 100


    # --------------------------------------------------------
    # RSI 14
    # --------------------------------------------------------

    delta = close_series.diff()

    gain = delta.clip(lower=0)

    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()

    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    rsi_series = 100 - (
        100 / (1 + rs)
    )

    rsi_value = float(
        rsi_series.dropna().iloc[-1]
    )


    # --------------------------------------------------------
    # RSI STATUS
    # --------------------------------------------------------

    if rsi_value >= 70:

        rsi_status = "OVERBOUGHT"

    elif rsi_value >= 60:

        rsi_status = "STRONG"

    elif rsi_value >= 50:

        rsi_status = "POSITIVE"

    elif rsi_value >= 40:

        rsi_status = "WEAK"

    elif rsi_value >= 30:

        rsi_status = "VERY WEAK"

    else:

        rsi_status = "OVERSOLD"


    # --------------------------------------------------------
    # TREND
    # --------------------------------------------------------

    if (
        close > dma20
        and dma20 > dma50
        and dma50 > dma200
    ):

        trend = "STRONG UPTREND"

    elif (
        close > dma50
        and dma50 > dma200
    ):

        trend = "UPTREND"

    elif (
        close < dma50
        and dma50 < dma200
    ):

        trend = "DOWNTREND"

    else:

        trend = "NEUTRAL"


    return {

        "close": round(close, 2),

        "change": round(
            daily_change,
            2
        ),

        "dma20": round(
            float(dma20),
            2
        ),

        "dma50": round(
            float(dma50),
            2
        ),

        "dma200": round(
            float(dma200),
            2
        ),

        "vs20": round(
            float(price_vs_20),
            2
        ),

        "vs50": round(
            float(price_vs_50),
            2
        ),

        "vs200": round(
            float(price_vs_200),
            2
        ),

        "rsi": round(
            rsi_value,
            2
        ),

        "rsi_status": rsi_status,

        "trend": trend
    }


# ============================================================
# NSE CONSTITUENT LISTS
# ============================================================

def get_nse_csv(url):

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120 Safari/537.36"
        )
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    from io import StringIO

    return pd.read_csv(
        StringIO(response.text)
    )


def get_nifty100_symbols():

    url = (
        "https://archives.nseindia.com/"
        "content/indices/"
        "ind_nifty100list.csv"
    )

    df = get_nse_csv(url)

    symbols = []

    for symbol in df["Symbol"].dropna():

        symbols.append(
            str(symbol).strip() + ".NS"
        )

    return symbols


def get_midcap150_symbols():

    url = (
        "https://archives.nseindia.com/"
        "content/indices/"
        "ind_niftymidcap150list.csv"
    )

    df = get_nse_csv(url)

    symbols = []

    for symbol in df["Symbol"].dropna():

        symbols.append(
            str(symbol).strip() + ".NS"
        )

    return symbols


def get_smallcap250_symbols():

    url = (
        "https://archives.nseindia.com/"
        "content/indices/"
        "ind_niftysmallcap250list.csv"
    )

    df = get_nse_csv(url)

    symbols = []

    for symbol in df["Symbol"].dropna():

        symbols.append(
            str(symbol).strip() + ".NS"
        )

    return symbols


# ============================================================
# MARKET BREADTH
# ============================================================

def calculate_breadth(symbols):

    total = 0

    above_20 = 0

    above_50 = 0

    above_200 = 0

    failed_symbols = []


    # --------------------------------------------------------
    # Process in batches
    # --------------------------------------------------------

    for start in range(
        0,
        len(symbols),
        BATCH_SIZE
    ):

        batch = symbols[
            start:start + BATCH_SIZE
        ]

        print(
            f"Downloading breadth batch "
            f"{start + 1}-{start + len(batch)} "
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
                "Batch download error:",
                str(e)
            )

            failed_symbols.extend(batch)

            continue


        # ----------------------------------------------------
        # Analyze each stock
        # ----------------------------------------------------

        for symbol in batch:

            try:

                if len(batch) == 1:

                    close_data = data["Close"]

                else:

                    if symbol not in data.columns.levels[0]:

                        failed_symbols.append(symbol)

                        continue

                    close_data = data[
                        symbol
                    ]["Close"]


                close_data = close_data.dropna()


                if len(close_data) < 200:

                    failed_symbols.append(symbol)

                    continue


                current_price = float(
                    close_data.iloc[-1]
                )


                dma20 = float(
                    close_data
                    .rolling(20)
                    .mean()
                    .iloc[-1]
                )


                dma50 = float(
                    close_data
                    .rolling(50)
                    .mean()
                    .iloc[-1]
                )


                dma200 = float(
                    close_data
                    .rolling(200)
                    .mean()
                    .iloc[-1]
                )


                total += 1


                if current_price > dma20:

                    above_20 += 1


                if current_price > dma50:

                    above_50 += 1


                if current_price > dma200:

                    above_200 += 1


            except Exception as e:

                print(
                    f"Stock error {symbol}: {e}"
                )

                failed_symbols.append(symbol)


        time.sleep(1)


    # --------------------------------------------------------
    # Percentages
    # --------------------------------------------------------

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


    pct20 = (
        above_20 / total
    ) * 100


    pct50 = (
        above_50 / total
    ) * 100


    pct200 = (
        above_200 / total
    ) * 100


    return {

        "total": total,

        "above20": above_20,

        "above50": above_50,

        "above200": above_200,

        "pct20": round(
            pct20,
            2
        ),

        "pct50": round(
            pct50,
            2
        ),

        "pct200": round(
            pct200,
            2
        )
    }


# ============================================================
# BREADTH SCORE
# ============================================================

def breadth_score(breadth):

    if breadth["total"] == 0:

        return 0


    # Weighted breadth score
    #
    # 20 DMA = 20%
    # 50 DMA = 30%
    # 200 DMA = 50%

    score = (
        breadth["pct20"] * 0.20
        +
        breadth["pct50"] * 0.30
        +
        breadth["pct200"] * 0.50
    )

    return round(
        min(max(score, 0), 100),
        1
    )


# ============================================================
# TREND SCORE
# ============================================================

def trend_score(data):

    score = 0


    # Price above 20 DMA
    if data["close"] > data["dma20"]:

        score += 15


    # Price above 50 DMA
    if data["close"] > data["dma50"]:

        score += 20


    # Price above 200 DMA
    if data["close"] > data["dma200"]:

        score += 25


    # 20 DMA above 50 DMA
    if data["dma20"] > data["dma50"]:

        score += 15


    # 50 DMA above 200 DMA
    if data["dma50"] > data["dma200"]:

        score += 25


    return score


# ============================================================
# RSI SCORE
# ============================================================

def rsi_score(rsi):

    if 55 <= rsi < 65:

        return 100

    elif 50 <= rsi < 55:

        return 85

    elif 65 <= rsi < 70:

        return 80

    elif 45 <= rsi < 50:

        return 65

    elif 40 <= rsi < 45:

        return 50

    elif 70 <= rsi < 75:

        return 55

    elif rsi >= 75:

        return 35

    elif 30 <= rsi < 40:

        return 40

    else:

        return 25


# ============================================================
# SEGMENT SCORE
# ============================================================

def calculate_segment_score(
    index_data,
    breadth
):

    trend = trend_score(
        index_data
    )

    rsi = rsi_score(
        index_data["rsi"]
    )

    breadth_value = breadth_score(
        breadth
    )


    # --------------------------------------------------------
    # Current weights
    #
    # Trend   = 40%
    # Breadth = 40%
    # RSI     = 20%
    #
    # Valuation will be added later.
    # --------------------------------------------------------

    score = (
        trend * 0.40
        +
        breadth_value * 0.40
        +
        rsi * 0.20
    )


    return round(
        score,
        1
    )


# ============================================================
# SCORE STATUS
# ============================================================

def score_status(score):

    if score >= 80:

        return "VERY STRONG 🟢"

    elif score >= 70:

        return "STRONG 🟢"

    elif score >= 60:

        return "POSITIVE 🟢"

    elif score >= 50:

        return "NEUTRAL 🟡"

    elif score >= 40:

        return "WEAK 🟠"

    else:

        return "VERY WEAK 🔴"


# ============================================================
# ALLOCATION VIEW
# ============================================================

def allocation_view(
    large_score,
    mid_score,
    small_score,
    overall_score
):

    if overall_score >= 75:

        market_view = "RISK-ON 🟢"

    elif overall_score >= 60:

        market_view = "MODERATELY POSITIVE 🟢"

    elif overall_score >= 50:

        market_view = "NEUTRAL 🟡"

    elif overall_score >= 40:

        market_view = "CAUTIOUS 🟠"

    else:

        market_view = "RISK-OFF 🔴"


    # --------------------------------------------------------
    # Large Cap
    # --------------------------------------------------------

    if large_score >= 75:

        large_view = "HIGHER PRIORITY 🟢"

    elif large_score >= 60:

        large_view = "MODERATE 🟢"

    elif large_score >= 50:

        large_view = "NEUTRAL 🟡"

    else:

        large_view = "CAUTION 🔴"


    # --------------------------------------------------------
    # Mid Cap
    # --------------------------------------------------------

    if mid_score >= 75:

        mid_view = "HIGHER PRIORITY 🟢"

    elif mid_score >= 60:

        mid_view = "MODERATE 🟢"

    elif mid_score >= 50:

        mid_view = "NEUTRAL 🟡"

    else:

        mid_view = "CAUTION 🔴"


    # --------------------------------------------------------
    # Small Cap
    # --------------------------------------------------------

    if small_score >= 75:

        small_view = "HIGHER PRIORITY 🟢"

    elif small_score >= 60:

        small_view = "MODERATE 🟢"

    elif small_score >= 50:

        small_view = "NEUTRAL 🟡"

    else:

        small_view = "CAUTION 🔴"


    return (
        market_view,
        large_view,
        mid_view,
        small_view
    )


# ============================================================
# MAIN PROGRAM
# ============================================================

try:

    print("Starting AI Wealth Manager...")


    # ========================================================
    # INDEX DATA
    # ========================================================

    print("Downloading index data...")


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
    # CONSTITUENTS
    # ========================================================

    print("Downloading Nifty 100 constituents...")

    nifty100_symbols = (
        get_nifty100_symbols()
    )


    print("Downloading Midcap 150 constituents...")

    midcap150_symbols = (
        get_midcap150_symbols()
    )


    print("Downloading Smallcap 250 constituents...")

    smallcap250_symbols = (
        get_smallcap250_symbols()
    )


    print(
        "Nifty 100 stocks:",
        len(nifty100_symbols)
    )

    print(
        "Midcap 150 stocks:",
        len(midcap150_symbols)
    )

    print(
        "Smallcap 250 stocks:",
        len(smallcap250_symbols)
    )


    # ========================================================
    # MARKET BREADTH
    # ========================================================

    print("Calculating Large Cap breadth...")

    large_breadth = calculate_breadth(
        nifty100_symbols
    )


    print("Calculating Mid Cap breadth...")

    mid_breadth = calculate_breadth(
        midcap150_symbols
    )


    print("Calculating Small Cap breadth...")

    small_breadth = calculate_breadth(
        smallcap250_symbols
    )


    # ========================================================
    # SCORES
    # ========================================================

    print("Calculating segment scores...")


    large_score = calculate_segment_score(
        nifty100,
        large_breadth
    )


    mid_score = calculate_segment_score(
        midcap150,
        mid_breadth
    )


    small_score = calculate_segment_score(
        smallcap250,
        small_breadth
    )


    # Overall market score
    #
    # Weighted toward Nifty 500 + segment scores.

    overall_score = round(
        (
            nifty500_score := (
                trend_score(nifty500) * 0.40
                +
                breadth_score(
                    large_breadth
                ) * 0.20
                +
                breadth_score(
                    mid_breadth
                ) * 0.20
                +
                breadth_score(
                    small_breadth
                ) * 0.20
            )
        ),
        1
    )


    # ========================================================
    # STATUS
    # ========================================================

    large_status = score_status(
        large_score
    )

    mid_status = score_status(
        mid_score
    )

    small_status = score_status(
        small_score
    )

    overall_status = score_status(
        overall_score
    )


    # ========================================================
    # ALLOCATION VIEW
    # ========================================================

    (
        market_view,
        large_view,
        mid_view,
        small_view
    ) = allocation_view(
        large_score,
        mid_score,
        small_score,
        overall_score
    )


    # ========================================================
    # TELEGRAM REPORT
    # ========================================================

    message = f"""
🤖 AI WEALTH MANAGER
📊 DAILY MARKET INTELLIGENCE
━━━━━━━━━━━━━━━━━━━━━━━━

🌐 OVERALL MARKET

NIFTY 500
Price: {nifty500['close']}
Daily Change: {nifty500['change']}%

20 DMA: {nifty500['dma20']}
50 DMA: {nifty500['dma50']}
200 DMA: {nifty500['dma200']}

Price vs 50 DMA:
{nifty500['vs50']}%

Price vs 200 DMA:
{nifty500['vs200']}%

RSI 14:
{nifty500['rsi']} ({nifty500['rsi_status']})

Trend:
{nifty500['trend']}

🎯 OVERALL MARKET SCORE
{overall_score}/100
{overall_status}

━━━━━━━━━━━━━━━━━━━━━━━━

🟢 LARGE CAP
NIFTY 100

Price: {nifty100['close']}
Daily Change: {nifty100['change']}%

20 DMA: {nifty100['dma20']}
50 DMA: {nifty100['dma50']}
200 DMA: {nifty100['dma200']}

Price vs 50 DMA:
{nifty100['vs50']}%

Price vs 200 DMA:
{nifty100['vs200']}%

RSI 14:
{nifty100['rsi']} ({nifty100['rsi_status']})

Trend:
{nifty100['trend']}

📈 BREADTH

Stocks Analyzed:
{large_breadth['total']}

Above 20 DMA:
{large_breadth['above20']}
({large_breadth['pct20']}%)

Above 50 DMA:
{large_breadth['above50']}
({large_breadth['pct50']}%)

Above 200 DMA:
{large_breadth['above200']}
({large_breadth['pct200']}%)

🎯 LARGE CAP SCORE
{large_score}/100
{large_status}

━━━━━━━━━━━━━━━━━━━━━━━━

🟡 MID CAP
NIFTY MIDCAP 150

Price: {midcap150['close']}
Daily Change: {midcap150['change']}%

20 DMA: {midcap150['dma20']}
50 DMA: {midcap150['dma50']}
200 DMA: {midcap150['dma200']}

Price vs 50 DMA:
{midcap150['vs50']}%

Price vs 200 DMA:
{midcap150['vs200']}%

RSI 14:
{midcap150['rsi']} ({midcap150['rsi_status']})

Trend:
{midcap150['trend']}

📈 BREADTH

Stocks Analyzed:
{mid_breadth['total']}

Above 20 DMA:
{mid_breadth['above20']}
({mid_breadth['pct20']}%)

Above 50 DMA:
{mid_breadth['above50']}
({mid_breadth['pct50']}%)

Above 200 DMA:
{mid_breadth['above200']}
({mid_breadth['pct200']}%)

🎯 MID CAP SCORE
{mid_score}/100
{mid_status}

━━━━━━━━━━━━━━━━━━━━━━━━

🔴 SMALL CAP
NIFTY SMALLCAP 250

Price: {smallcap250['close']}
Daily Change: {smallcap250['change']}%

20 DMA: {smallcap250['dma20']}
50 DMA: {smallcap250['dma50']}
200 DMA: {smallcap250['dma200']}

Price vs 50 DMA:
{smallcap250['vs50']}%

Price vs 200 DMA:
{smallcap250['vs200']}%

RSI 14:
{smallcap250['rsi']} ({smallcap250['rsi_status']})

Trend:
{smallcap250['trend']}

📈 BREADTH

Stocks Analyzed:
{small_breadth['total']}

Above 20 DMA:
{small_breadth['above20']}
({small_breadth['pct20']}%)

Above 50 DMA:
{small_breadth['above50']}
({small_breadth['pct50']}%)

Above 200 DMA:
{small_breadth['above200']}
({small_breadth['pct200']}%)

🎯 SMALL CAP SCORE
{small_score}/100
{small_status}

━━━━━━━━━━━━━━━━━━━━━━━━

🇮🇳 NIFTY 50

Price: {nifty50['close']}
Daily Change: {nifty50['change']}%

RSI: {nifty50['rsi']}
Trend: {nifty50['trend']}

🇮🇳 SENSEX

Price: {sensex['close']}
Daily Change: {sensex['change']}%

RSI: {sensex['rsi']}
Trend: {sensex['trend']}

━━━━━━━━━━━━━━━━━━━━━━━━

💰 ALLOCATION VIEW

Overall Market:
{market_view}

🟢 Large Cap:
{large_view}

🟡 Mid Cap:
{mid_view}

🔴 Small Cap:
{small_view}

━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ IMPORTANT

This is a rule-based market
analysis system.

It is NOT a guarantee of
investment returns.

Valuation, VIX, earnings,
macro indicators and
historical backtesting will
be added in the next phase.

🤖 GitHub Actions Active
📱 Telegram Alert Active
━━━━━━━━━━━━━━━━━━━━━━━━
"""


    # ========================================================
    # SEND TELEGRAM
    # ========================================================

    send_telegram(
        message
    )


    print(
        "AI Wealth Manager completed successfully."
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
