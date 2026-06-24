resource "aws_secretsmanager_secret" "stock_api_key" {
  name        = "stock-movers/massive-api-key"
  description = "Massive API key for stock movers ingestion Lambda"
}