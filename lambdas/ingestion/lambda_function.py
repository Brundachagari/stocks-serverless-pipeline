import json
import os
import time
from decimal import Decimal
import requests
import boto3



# Required watchlist from the project prompt
WATCHLIST = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "TSLA",
    "NVDA",
]

# Temporary fixed date for Lambda testing
DATE = "2026-06-18"

# DynamoDB table name created by Terraform.
# lets the Lambda know where to store the final daily winner record.
# In AWS - passed in through an environment variable.
TABLE_NAME = os.getenv("TABLE_NAME", "stock-movers")

# boto3 connects Python/Lambda to AWS services
# connects this ingestion Lambda to DynamoDB
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def get_stock_change(ticker, api_key):
    """
    Fetch one stock's open/close data and calculate its daily percent change

    core ingestion logic:
    1. Call the external stock API
    2. Validate the response
    3. Calculate percent change
    4. Return clean structured data

    supports separation of concerns
    """

    url = f"https://api.massive.com/v1/open-close/{ticker}/{DATE}"

    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    params = {
        "adjusted": "true"
    }

    # Timeout prevents the Lambda from hanging if the external API is slow
    # AWS- logs would be visible in CloudWatch
    response = requests.get(url, headers=headers, params=params, timeout=10)

    print(f"Fetching {ticker}...")
    print("Status code:", response.status_code)

    try:
        data = response.json()
    except ValueError:
        print("Response was not JSON:")
        print(response.text)
        raise

    # Handle API rate limits
    # 429 - the stock API received too many requests quickly
    # Retrying once after a delay makes ingestion job more reliable
    if response.status_code == 429:
        print(f"Rate limit hit for {ticker}. Waiting 65 seconds before retrying...")
        time.sleep(65)

        response = requests.get(url, headers=headers, params=params, timeout=10)
        print("Retry status code:", response.status_code)

        try:
            data = response.json()
        except ValueError:
            print("Retry response was not JSON:")
            print(response.text)
            raise

    # If the API still fails -stop this ticker and let the caller handle the error
    # error handling
    if response.status_code != 200:
        raise Exception(f"API request failed for {ticker}: {data}")

    open_price = data.get("open")
    close_price = data.get("close")

    if open_price is None or close_price is None:
        raise ValueError(f"Missing open or close price for {ticker}.")

    percent_change = ((close_price - open_price) / open_price) * 100

    return {
        "date": DATE,
        "ticker": ticker,
        "open_price": open_price,
        "closing_price": close_price,
        "percent_change": percent_change,
        "abs_percent_change": abs(percent_change)
    }


# This function is the storage step
# It writes the final daily winner record into DynamoDB
def save_winner_to_dynamodb(record):
    """
    Store the final daily winner record in DynamoDB.

    This completes the ingestion pipeline:
    Stock API -> Lambda -> DynamoDB

    This also matches the project requirement to store:
    Date, Ticker Symbol, Percent Change, and Closing Price.
    """

    # DynamoDB does not accept regular Python float values
    # Decimal used for numeric values
    item = {
        "date": record["date"],
        "ticker": record["ticker"],
        "percent_change": Decimal(str(record["percent_change"])),
        "closing_price": Decimal(str(record["closing_price"]))
    }

    # put_item writes one item into the DynamoDB table
    # date is the table's primary key :this stores one winner per date
    table.put_item(Item=item)

    print("Saved winner to DynamoDB:")
    print(item)


def lambda_handler(event, context):
    """
    AWS Lambda entry point

    EventBridge will trigger this Lambda once per day
    ingestion Lambda is responsible for:
      1. Fetching stock data
      2. Calculating the daily biggest mover
      3. Returning a clean winner record
      4. Later writing that record to DynamoDB
      future API Lambda, which will only retrieve data
    """

    api_key = os.getenv("STOCK_API_KEY")

    if not api_key:
        raise ValueError("Missing STOCK_API_KEY environment variable.")

    results = []

    for ticker in WATCHLIST:
        try:
            time.sleep(15)
            stock_result = get_stock_change(ticker, api_key)
            results.append(stock_result)

        except Exception as error:
            print(f"Error processing {ticker}: {error}")

    if not results:
        raise Exception("No stock data was successfully retrieved.")

    winner = max(results, key=lambda stock: stock["abs_percent_change"])

    daily_winner_record = {
        "date": winner["date"],
        "ticker": winner["ticker"],
        "percent_change": round(winner["percent_change"], 2),
        "closing_price": winner["closing_price"]
    }

    print("Daily winner record:")
    print(daily_winner_record)

    # Lambda now writes the winner into DynamoDB.
    # the function was only returned the result
    # it now stores the result so the future API Lambda can retrieve it
    save_winner_to_dynamodb(daily_winner_record)

    # The main output of this function will be writing the record to DynamoDB
    return {
        "statusCode": 200,
        "body": json.dumps(daily_winner_record)
    }