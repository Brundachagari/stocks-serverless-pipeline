import json
import os
from decimal import Decimal

import boto3

# Terraform sets TABLE_NAME per environment so it is not tied to one table.
# boto3 setup lives at module scope on purpose: only runs on cold start
TABLE_NAME = os.getenv("TABLE_NAME", "stock-movers")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def decimal_to_number(value):
# DynamoDB gives numbers back as Decimal — json can't handle those directly
# Drop to int if it's whole; everything else float 
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    return value


def clean_item(item):
    # Reshape a raw DynamoDB row into what the frontend wants
    # Keeps DynamoDB specifics out of the UI.
    return {
        "date": item.get("date"),
        "ticker": item.get("ticker"),
        "percent_change": decimal_to_number(item.get("percent_change")),
        "closing_price": decimal_to_number(item.get("closing_price")),
    }


def lambda_handler(event, context):
    # Read side of GET /movers. 
    # This Lambda only reads / the daily cron Lambda only that writes
    # Splitting them keeps the write job safe from
    # API traffic and lets this function run on read-only IAM perms
    try:
        # scan() pulls the whole table. Fine here on purpose: one row per day, so
        # it stays tiny. Would swap to a Query/GSI if this ever got big.
        response = table.scan()
        items = response.get("Items", [])

        # One winner per day means date alone is enough to sort on, and ISO dates
        # already sort right as strings
        sorted_items = sorted(
            items,
            key=lambda item: item.get("date", ""),
            reverse=True,
        )

        latest_seven = sorted_items[:7]
        cleaned_results = [clean_item(item) for item in latest_seven]

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                # CORS so the S3 frontend can call this from the browser
                # * is fine because it's public read-only.
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(cleaned_results),
        }

    except Exception as error:
        # print goes to CloudWatch; client just gets a generic 500.
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