import os
import requests
import time
from dotenv import load_dotenv
# I had to add time to avoid rate limiting issues with the stock API
# (AWS- Lambda- added retry logic)


# Local development secret handling
# The key is loaded from .env.  (AWS - Secrets Manager)
load_dotenv()

API_KEY = os.getenv("STOCK_API_KEY")

# stop early if the API key is missing to make debugging easier
if not API_KEY:
    raise ValueError("Missing STOCK_API_KEY. Add it to your .env file.")


# Required project watchlist
WATCHLIST = [
    "AAPL",   # Apple
    "MSFT",   # Microsoft
    "GOOGL",  # Google 
    "AMZN",   # Amazon
    "TSLA",   # Tesla
    "NVDA",   # NVIDIA
]

# Fixed date for local testing 
# (Lambda- replaced with logic for the latest valid trading day)
DATE = "2026-06-18"


def get_stock_change(ticker):
    """
    Fetch a stock's open/close data and calculate its daily percent change.

    This function represents the core ingestion logic that will later run inside AWS Lambda
    1. Call the external stock API
    2. Validate the response
    3. Calculate the required percent change
    4. Return clean structured data for storage
    """

    url = f"https://api.massive.com/v1/open-close/{ticker}/{DATE}"

    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    # adjusted=true helps account for stock splits (ex. $100 - 1 stock = $50 - 2 stocks)
    params = {
        "adjusted": "true"
    }

    # timeout prevents the script from hanging if the stock API is slow or unavailable
    response = requests.get(url, headers=headers, params=params, timeout=10)

    print(f"\nFetching {ticker}...")
    print("Status code:", response.status_code)

    try:
        data = response.json()
    except ValueError:
        print("Response was not JSON:")
        print(response.text)
        raise

    # API failure handling
    # (AWS- CloudWatch logs for debugging)
    if response.status_code != 200:
        raise Exception(f"API request failed for {ticker}: {data}")

    open_price = data.get("open")
    close_price = data.get("close")

    # Error handling for missing market data
    # ex. weekends, market holidays, invalid dates, or API issues
    if open_price is None or close_price is None:
        raise ValueError(f"Missing open or close price for {ticker}.")

    # Required project formula:
    # ((Close - Open) / Open) * 100
    percent_change = ((close_price - open_price) / open_price) * 100

    # Return a structured result for each stock
    return {
        "date": DATE,
        "ticker": ticker,
        "open_price": open_price,
        "closing_price": close_price,
        "percent_change": percent_change,
        "abs_percent_change": abs(percent_change)
    }


# process each stock using the same reusable function.
# shows separation of concerns:
# - get_stock_change handles one ticker
# - the loop handles the full watchlist
results = []


#during testing I got 429 rate-limit response
#I added a delay between each request
for ticker in WATCHLIST:
    try:
        time.sleep(12)
        stock_result = get_stock_change(ticker)
        results.append(stock_result)

        print(
            f"{ticker}: open={stock_result['open_price']}, "
            f"close={stock_result['closing_price']}, "
            f"change={stock_result['percent_change']:.2f}%"
        )

    # If one ticker fails- keep processing the rest of the watchlist
    # Prevents one API issue from crashing the entire daily pipeline
    except Exception as error:
        print(f"Error processing {ticker}: {error}")


if not results:
    raise Exception("No stock data was successfully retrieved.")


# Pick the stock with the biggest absolute movement
winner = max(results, key=lambda stock: stock["abs_percent_change"])


# Final daily winner record
# (AWS- stored in DynamoDB)
daily_winner_record = {
    "date": winner["date"],
    "ticker": winner["ticker"],
    "percent_change": round(winner["percent_change"], 2),
    "closing_price": winner["closing_price"],
    "absolute_movement": round(winner["abs_percent_change"], 2)
}


print("\n==============================")
print("Daily Biggest Mover")
print("==============================")
print(f"Date: {daily_winner_record['date']}")
print(f"Ticker: {daily_winner_record['ticker']}")
print(f"Closing price: {daily_winner_record['closing_price']}")
print(f"Percent change: {daily_winner_record['percent_change']}%")
print(f"Absolute movement: {daily_winner_record['absolute_movement']}%")