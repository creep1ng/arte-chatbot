output "role_arn" {
  description = "GitHub Actions deploy role ARN."
  value       = aws_iam_role.this.arn
}

output "role_name" {
  description = "GitHub Actions deploy role name."
  value       = aws_iam_role.this.name
}

output "preview_role_arn" {
  description = "GitHub Actions PR preview deploy role ARN."
  value       = aws_iam_role.preview.arn
}

output "preview_role_name" {
  description = "GitHub Actions PR preview deploy role name."
  value       = aws_iam_role.preview.name
}

output "preview_lambda_permissions_boundary_arn" {
  description = "Permissions boundary required on PR preview Lambda execution roles."
  value       = aws_iam_policy.preview_lambda_boundary.arn
}

output "preview_lambda_execution_role_arn" {
  description = "Foundation-managed execution role shared by PR preview Lambdas."
  value       = aws_iam_role.preview_lambda.arn
}
