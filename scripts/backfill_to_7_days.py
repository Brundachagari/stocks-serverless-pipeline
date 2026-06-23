import os
from datetime import datetime, timezone
from decimal import Decimal
import time

import boto3
import requests


TABLE_NAME = os.getenv("TABLE_NAME", "stock-movers")
API_KEY = os.getenv("MASSIVE_API_KEY")

WATCHLIST = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA"]

START_DATE = "2026-06-01"
END_DATE = "2026-06-22"


dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def fetch_bars(ticker):
    url = (
        f"https://api.massive.com/v2/aggs/ticker/{ticker}/range/1/day/"
        f"{START_DATE}/{END_DATE}"
    )

    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50,
        "apiKey": API_KEY,
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json().get("results", [])


def bar_to_date(timestamp_ms):
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).date().isoformat()


def main():
    if not API_KEY:
        raise ValueError("Missing MASSIVE_API_KEY environment variable")

    rows_by_date = {}

    for ticker in WATCHLIST:
        print(f"Fetching data for {ticker}...")

        try:
            bars = fetch_bars(ticker)
        except requests.exceptions.HTTPError as error:
            if error.response is not None and error.response.status_code == 429:
                print("Rate limit hit. Waiting 60 seconds, then trying again...")
                time.sleep(60)
                bars = fetch_bars(ticker)
            else:
                raise

        time.sleep(15)

        for bar in bars:
            open_price = bar.get("o")
            close_price = bar.get("c")
            timestamp = bar.get("t")

            if not open_price or not close_price or not timestamp:
                continue

            trade_date = bar_to_date(timestamp)
            percent_change = ((close_price - open_price) / open_price) * 100

            rows_by_date.setdefault(trade_date, []).append({
                "date": trade_date,
                "ticker": ticker,
                "percent_change": percent_change,
                "closing_price": close_price,
            })

    winners = []

    for trade_date, rows in rows_by_date.items():
        winner = max(rows, key=lambda row: abs(row["percent_change"]))
        winners.append(winner)

    winners = sorted(winners, key=lambda row: row["date"], reverse=True)[:7]

    for winner in winners:
        table.put_item(
            Item={
                "date": winner["date"],
                "ticker": winner["ticker"],
                "percent_change": Decimal(str(round(winner["percent_change"], 2))),
                "closing_price": Decimal(str(round(winner["closing_price"], 2))),
            }
        )

        print(
            f"Saved {winner['date']} | "
            f"{winner['ticker']} | "
            f"{winner['percent_change']:.2f}% | "
            f"${winner['closing_price']:.2f}"
        )

    print(f"Done. Added/updated {len(winners)} records in DynamoDB.")


if __name__ == "__main__":
    main()