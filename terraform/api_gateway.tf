resource "aws_apigatewayv2_api" "stock_movers_api" {
  name          = "stock-movers-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = ["*"]
    allow_methods = ["GET", "OPTIONS"]
    allow_headers = ["content-type"]
  }
}

resource "aws_apigatewayv2_integration" "get_movers_lambda" {
  api_id                 = aws_apigatewayv2_api.stock_movers_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api_get_movers.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "get_movers_route" {
  api_id    = aws_apigatewayv2_api.stock_movers_api.id
  route_key = "GET /movers"
  target    = "integrations/${aws_apigatewayv2_integration.get_movers_lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.stock_movers_api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "allow_api_gateway" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api_get_movers.function_name
  principal     = "apigateway.amazonaws.com"

  source_arn = "${aws_apigatewayv2_api.stock_movers_api.execution_arn}/*/*"
}