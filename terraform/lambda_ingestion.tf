variable "stock_api_key" {
  description = "API key for the stock data provider"
  type        = string
  sensitive   = true
}

# Packages the ingestion Lambda directly from its Python file.
# No external dependencies are needed because the Lambda uses urllib.
data "archive_file" "ingestion_lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/ingestion/lambda_function.py"
  output_path = "${path.module}/ingestion_lambda.zip"
}

# IAM role for the scheduled ingestion Lambda.
resource "aws_iam_role" "ingestion_lambda_role" {
  name = "stock-movers-ingestion-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        },
        Action = "sts:AssumeRole"
      }
    ]
  })
}

# This Lambda writes the daily winner to DynamoDB and logs to CloudWatch.
resource "aws_iam_role_policy" "ingestion_lambda_policy" {
  name = "stock-movers-ingestion-lambda-policy"
  role = aws_iam_role.ingestion_lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "dynamodb:PutItem"
        ],
        Resource = aws_dynamodb_table.stock_movers.arn
      },
      {
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "*"
      }
    ]
  })
}

# Scheduled Lambda that fetches stock data, finds the biggest mover, and stores it.
resource "aws_lambda_function" "ingestion_lambda" {
  function_name = "stock-movers-ingestion"
  role          = aws_iam_role.ingestion_lambda_role.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.11"
  timeout       = 120

  filename         = data.archive_file.ingestion_lambda_zip.output_path
  source_code_hash = data.archive_file.ingestion_lambda_zip.output_base64sha256

  environment {
    variables = {
      TABLE_NAME            = aws_dynamodb_table.stock_movers.name
      STOCK_API_KEY         = var.stock_api_key
      API_BASE_URL          = "https://api.massive.com"
      REQUEST_DELAY_SECONDS = "12"
    }
  }
}

# Runs once per weekday after market close.
resource "aws_cloudwatch_event_rule" "daily_ingestion_schedule" {
  name                = "stock-movers-daily-ingestion"
  description         = "Runs the stock mover ingestion Lambda once per weekday after market close"
  schedule_expression = "cron(0 23 ? * MON-FRI *)"
}

resource "aws_cloudwatch_event_target" "daily_ingestion_target" {
  rule      = aws_cloudwatch_event_rule.daily_ingestion_schedule.name
  target_id = "stock-movers-ingestion-lambda"
  arn       = aws_lambda_function.ingestion_lambda.arn
}

resource "aws_lambda_permission" "allow_eventbridge_ingestion" {
  statement_id  = "AllowEventBridgeInvokeIngestion"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingestion_lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_ingestion_schedule.arn
}