import json
import os
from decimal import Decimal

import boto3


TABLE_NAME = os.getenv("TABLE_NAME", "stock-movers")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def decimal_to_number(value):
    """Convert DynamoDB Decimals to normal Python numbers for JSON."""
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    return value


def clean_item(item):
    """Return only the fields the frontend needs."""
    return {
        "date": item.get("date"),
        "ticker": item.get("ticker"),
        "percent_change": decimal_to_number(item.get("percent_change")),
        "closing_price": decimal_to_number(item.get("closing_price")),
    }


def get_limit(event):
    """Allow /movers?limit=3 while defaulting to 7."""
    query_params = event.get("queryStringParameters") or {}

    try:
        limit = int(query_params.get("limit", 7))
    except (TypeError, ValueError):
        limit = 7

    # Keep the API safe: minimum 1 record, maximum 30 records
    return max(1, min(limit, 30))


def lambda_handler(event, context):
    """GET /movers — returns the most recent stock mover records."""
    try:
        limit = get_limit(event)

        # The table is small because we store one winning stock per day.
        # A scan is okay here. If this grew much larger, a Query/GSI would be better.
        response = table.scan()
        items = response.get("Items", [])

        # Handle scan pagination just in case the table grows later.
        while "LastEvaluatedKey" in response:
            response = table.scan(
                ExclusiveStartKey=response["LastEvaluatedKey"]
            )
            items.extend(response.get("Items", []))

        sorted_items = sorted(
            items,
            key=lambda item: item.get("date", ""),
            reverse=True,
        )

        latest_items = sorted_items[:limit]
        cleaned_results = [clean_item(item) for item in latest_items]

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Cache-Control": "public, max-age=60",
                "X-Data-Source": "DynamoDB",
                "X-Record-Limit": str(limit),
            },
            "body": json.dumps({
                "count": len(cleaned_results),
                "limit": limit,
                "movers": cleaned_results,
            }),
        }

    except Exception as error:
        print(f"Error retrieving movers: {error}")

        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({
                "message": "Failed to retrieve stock movers."
            }),
        }