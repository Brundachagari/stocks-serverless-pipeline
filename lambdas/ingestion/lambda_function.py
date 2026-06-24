import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal

import boto3

# Everything that might differ between environments is read from the env so the
# same code runs locally, in staging, and in prod without edits. Terraform sets
# these on the function; the defaults here just keep local testing painless.
TABLE_NAME = os.getenv("TABLE_NAME", "stock-movers")
STOCK_API_SECRET_ARN = os.getenv("STOCK_API_SECRET_ARN")
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.massive.com")

# The free API tier caps us at ~5 requests/minute, so we space calls ~12s apart.
# Pulled out as a knob in case we upgrade the plan and want to speed this up.
REQUEST_DELAY_SECONDS = float(os.getenv("REQUEST_DELAY_SECONDS", "12"))

WATCHLIST = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA"]

# Create these at module scope, not inside the handler: Lambda reuses a warm
# container across invocations, so the boto3 client/table get reused instead of
# rebuilt on every call. Cheap, but it shaves cold-start work off warm runs.
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

secrets_client = boto3.client("secretsmanager")
_cached_stock_api_key = None


def get_stock_api_key():
    global _cached_stock_api_key

    if _cached_stock_api_key:
        return _cached_stock_api_key

    if not STOCK_API_SECRET_ARN:
        raise ValueError("Missing STOCK_API_SECRET_ARN environment variable.")

    response = secrets_client.get_secret_value(
        SecretId=STOCK_API_SECRET_ARN
    )

    secret_string = response.get("SecretString")
    if not secret_string:
        raise ValueError("Secret value is empty.")

    secret_json = json.loads(secret_string)
    api_key = secret_json.get("STOCK_API_KEY")

    if not api_key:
        raise ValueError("STOCK_API_KEY not found in secret.")

    _cached_stock_api_key = api_key
    return api_key


def fetch_previous_day_bar(ticker):
    # Pull the real API key from Secrets Manager at runtime instead of storing
    # it directly in Lambda environment variables.
    stock_api_key = get_stock_api_key()

    # The "/prev" endpoint hands back the most recent *completed* trading day's
    # bar. Letting the API resolve that means we don't have to reason about
    # weekends, holidays, or market hours ourselves.
    url = (
        f"{API_BASE_URL}/v2/aggs/ticker/{ticker}/prev"
        f"?adjusted=true&apiKey={stock_api_key}"
    )

    # Short timeout so a hung connection can't pin the function until Lambda's
    # own timeout kills it; we'd rather surface the error and move on.
    with urllib.request.urlopen(url, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))

    results = data.get("results", [])
    if not results:
        # An empty result usually means a bad ticker or a day with no trading,
        # so treat it as a hard error rather than silently storing nothing.
        raise ValueError(f"No stock data returned for {ticker}")

    bar = results[0]
    open_price = float(bar["o"])
    close_price = float(bar["c"])

    # The API reports the bar's timestamp in epoch milliseconds, so divide by
    # 1000 before handing it to datetime. We keep just the date (UTC) since the
    # bar represents a whole day, and use it as part of the DynamoDB key.
    date_from_api = datetime.fromtimestamp(
        bar["t"] / 1000,
        tz=timezone.utc,
    ).date().isoformat()

    # "Move" here is the intraday open-to-close swing, not change vs. the prior
    # close. Worth stating outright since both are reasonable definitions of a
    # daily move and they can disagree on gap days.
    percent_change = ((close_price - open_price) / open_price) * 100

    return {
        "date": date_from_api,
        "ticker": ticker,
        "percent_change": percent_change,
        "closing_price": close_price,
    }


def to_decimal(value):
    # DynamoDB rejects native floats, so numbers have to go in as Decimal.
    # Building the Decimal from a *string* (not the float directly) sidesteps
    # binary-float artifacts like 1.1 -> 1.1000000000000001. Round to cents
    # first since two decimal places is all this data needs.
    return Decimal(str(round(value, 2)))


def lambda_handler(event, context):
    try:
        movers = []
        for index, ticker in enumerate(WATCHLIST):
            # Pace every request after the first. Skipping the sleep on index 0
            # avoids a pointless delay before the run even starts.
            if index > 0:
                time.sleep(REQUEST_DELAY_SECONDS)
            stock_data = fetch_previous_day_bar(ticker)
            movers.append(stock_data)

        # "Biggest mover" means the largest swing in either direction, so we
        # compare on absolute value — a -8% drop should beat a +5% gain.
        biggest_mover = max(
            movers,
            key=lambda item: abs(item["percent_change"]),
        )

        # Convert the numeric fields to Decimal only at the write boundary; the
        # rest of the code stays in plain floats, which are easier to work with.
        item = {
            "date": biggest_mover["date"],
            "ticker": biggest_mover["ticker"],
            "percent_change": to_decimal(biggest_mover["percent_change"]),
            "closing_price": to_decimal(biggest_mover["closing_price"]),
        }
        table.put_item(Item=item)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Daily mover stored successfully.",
                # json.dumps can't serialize Decimal, so cast back to float for
                # the response payload. (The authoritative copy in Dynamo stays
                # Decimal — this is only for the API response.)
                "item": {
                    "date": item["date"],
                    "ticker": item["ticker"],
                    "percent_change": float(item["percent_change"]),
                    "closing_price": float(item["closing_price"]),
                },
            }),
        }
    except Exception as error:
        # Catch-all so a single bad ticker or API hiccup returns a clean 500
        # instead of an unhandled stack trace. The print lands in CloudWatch,
        # which is where we'd actually go to debug a failed scheduled run.
        print(f"Error processing daily mover: {error}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Failed to process daily mover.",
                "error": str(error),
            }),
        }