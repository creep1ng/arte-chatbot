output "function_name" {
  description = "Lambda backend function name."
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "Lambda backend function ARN."
  value       = aws_lambda_function.this.arn
}

output "alias_name" {
  description = "Lambda alias receiving HTTP API traffic."
  value       = aws_lambda_alias.this.name
}

output "alias_arn" {
  description = "Lambda alias ARN receiving HTTP API traffic."
  value       = aws_lambda_alias.this.arn
}

output "published_version" {
  description = "Published Lambda version currently targeted by the alias."
  value       = aws_lambda_function.this.version
}

output "role_arn" {
  description = "Lambda execution role ARN."
  value       = local.execution_role_arn
}

output "state_table_name" {
  description = "DynamoDB state table name."
  value       = aws_dynamodb_table.state.name
}

output "state_table_arn" {
  description = "DynamoDB state table ARN."
  value       = aws_dynamodb_table.state.arn
}

output "http_api_id" {
  description = "API Gateway HTTP API id."
  value       = aws_apigatewayv2_api.this.id
}

output "http_api_endpoint" {
  description = "API Gateway HTTP API base endpoint."
  value       = aws_apigatewayv2_api.this.api_endpoint
}

output "invoke_url" {
  description = "Direct stage invoke URL for validation."
  value       = aws_apigatewayv2_stage.this.invoke_url
}

output "log_group_name" {
  description = "Lambda CloudWatch log group name."
  value       = aws_cloudwatch_log_group.lambda.name
}
