import json
import os
from decimal import Decimal

import boto3


TABLE_NAME = os.getenv("TABLE_NAME", "stock-movers")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def decimal_to_number(value):
    """Convert DynamoDB Decimals to plain int/float so json.dumps can handle them."""
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    return value


def clean_item(item):
    return {
        "date": item.get("date"),
        "ticker": item.get("ticker"),
        "percent_change": decimal_to_number(item.get("percent_change")),
        "closing_price": decimal_to_number(item.get("closing_price")),
    }


def lambda_handler(event, context):
    """GET /movers — returns the 7 most recent daily winners."""
    try:
        # One row per day, so the table stays tiny. A full scan + in-memory
        # sort is cheaper than maintaining a GSI just to grab 7 rows.
        items = table.scan().get("Items", [])

        sorted_items = sorted(items, key=lambda i: i.get("date", ""), reverse=True)
        cleaned_results = [clean_item(i) for i in sorted_items[:7]]

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(cleaned_results),
        }

    except Exception as error:
        print(f"Error retrieving movers: {error}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"message": "Failed to retrieve stock movers."}),
        }