output "stock_movers_table_name" {
  value = aws_dynamodb_table.stock_movers.name
}

output "stock_movers_table_arn" {
  value = aws_dynamodb_table.stock_movers.arn
}

output "api_url" {
  value = "${aws_apigatewayv2_api.stock_movers_api.api_endpoint}/movers"
}

output "ingestion_lambda_name" {
  value = aws_lambda_function.ingestion_lambda.function_name
}

output "frontend_url" {
  value = "http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}"
}