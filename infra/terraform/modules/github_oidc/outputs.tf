output "role_arn" {
  description = "GitHub Actions deploy role ARN."
  value       = aws_iam_role.this.arn
}

output "role_name" {
  description = "GitHub Actions deploy role name."
  value       = aws_iam_role.this.name
}
