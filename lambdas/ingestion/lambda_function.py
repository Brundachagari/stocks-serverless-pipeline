import json
import os
import time
from datetime import date, timedelta
from decimal import Decimal

import requests
import boto3


WATCHLIST = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA"]

TABLE_NAME = os.getenv("TABLE_NAME", "stock-movers")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def last_market_day():
    """
    Return the most recent weekday as YYYY-MM-DD.

    We want yesterday's session, but markets are closed on weekends, so a
    Monday run has to reach back to Friday. This doesn't account for holidays —
    on those days the API just returns nothing and the ticker gets skipped.
    """
    day = date.today() - timedelta(days=1)
    while day.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        day -= timedelta(days=1)
    return day.isoformat()


TARGET_DATE = last_market_day()


def get_stock_change(ticker, api_key):
    """Fetch one ticker's open/close and return its daily percent change."""
    url = f"https://api.massive.com/v1/open-close/{ticker}/{TARGET_DATE}"
    headers = {"Authorization": f"Bearer {api_key}"}
    params = {"adjusted": "true"}

    response = requests.get(url, headers=headers, params=params, timeout=10)
    print(f"Fetching {ticker}... status {response.status_code}")

    # Back off once on a rate limit, then retry. If it fails again we let the
    # caller catch it so one bad ticker doesn't sink the whole run.
    if response.status_code == 429:
        print(f"Rate limited on {ticker}, waiting 65s before one retry...")
        time.sleep(65)
        response = requests.get(url, headers=headers, params=params, timeout=10)

    try:
        data = response.json()
    except ValueError:
        print(f"Non-JSON response for {ticker}: {response.text}")
        raise

    if response.status_code != 200:
        raise Exception(f"API request failed for {ticker}: {data}")

    open_price = data.get("open")
    close_price = data.get("close")
    if open_price is None or close_price is None:
        # Happens on holidays or for a ticker the API has no data for that day.
        raise ValueError(f"Missing open or close price for {ticker}.")

    percent_change = ((close_price - open_price) / open_price) * 100
    return {
        "date": TARGET_DATE,
        "ticker": ticker,
        "open_price": open_price,
        "closing_price": close_price,
        "percent_change": percent_change,
        # Stored separately so the winner pick can rank by size of move
        # regardless of direction — a -8% day should beat a +3% day.
        "abs_percent_change": abs(percent_change),
    }


def save_winner_to_dynamodb(record):
    """Write the day's winner to DynamoDB. Date is the partition key, one row per day."""
    # DynamoDB rejects Python floats, so numerics go in as Decimal. Converting
    # via str() avoids the float-precision garbage you get from Decimal(float).
    item = {
        "date": record["date"],
        "ticker": record["ticker"],
        "percent_change": Decimal(str(record["percent_change"])),
        "closing_price": Decimal(str(record["closing_price"])),
    }
    table.put_item(Item=item)
    print(f"Saved winner: {item}")


def lambda_handler(event, context):
    """Daily EventBridge trigger: find the biggest mover and store it."""
    api_key = os.getenv("STOCK_API_KEY")
    if not api_key:
        raise ValueError("Missing STOCK_API_KEY environment variable.")

    results = []
    for ticker in WATCHLIST:
        try:
            # Space calls out to stay under the API's rate limit. Tune this to
            # whatever the Massive free tier actually allows — 15s is cautious.
            time.sleep(15)
            results.append(get_stock_change(ticker, api_key))
        except Exception as error:
            # Skip the failed ticker but keep going — we'd rather pick a winner
            # from 5 good tickers than fail the whole day over 1 bad response.
            print(f"Error processing {ticker}: {error}")

    if not results:
        raise Exception("No stock data was successfully retrieved.")

    winner = max(results, key=lambda s: s["abs_percent_change"])
    daily_winner_record = {
        "date": winner["date"],
        "ticker": winner["ticker"],
        "percent_change": round(winner["percent_change"], 2),
        "closing_price": winner["closing_price"],
    }
    print(f"Daily winner: {daily_winner_record}")

    save_winner_to_dynamodb(daily_winner_record)

    return {"statusCode": 200, "body": json.dumps(daily_winner_record)}