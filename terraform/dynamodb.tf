resource "aws_dynamodb_table" "stock_movers" {
  name         = "stock-movers"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "date"

  attribute {
    name = "date"
    type = "S"
  }

  tags = {
    Project = "stocks-serverless-pipeline"
    Purpose = "store-daily-stock-movers"
  }
}