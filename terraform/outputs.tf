output "stock_movers_table_name" {
  value = aws_dynamodb_table.stock_movers.name
}

output "stock_movers_table_arn" {
  value = aws_dynamodb_table.stock_movers.arn
}