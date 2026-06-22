output "service_name" {
  description = "ECS service name."
  value       = aws_ecs_service.this.name
}

output "service_arn" {
  description = "ECS service ARN."
  value       = aws_ecs_service.this.id
}

output "task_definition_arn" {
  description = "ECS task definition ARN."
  value       = aws_ecs_task_definition.this.arn
}

output "task_role_arn" {
  description = "Application task role ARN."
  value       = aws_iam_role.task.arn
}

output "execution_role_arn" {
  description = "ECS execution role ARN."
  value       = aws_iam_role.execution.arn
}

output "security_group_id" {
  description = "Fargate task security group id."
  value       = aws_security_group.this.id
}

output "log_group_arn" {
  description = "CloudWatch log group ARN."
  value       = aws_cloudwatch_log_group.this.arn
}
