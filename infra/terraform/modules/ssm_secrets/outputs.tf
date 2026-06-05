output "secret_arns" {
  description = "Secrets Manager ARNs keyed by logical name. Marked sensitive because keys describe runtime secret usage."
  value       = { for key, secret in aws_secretsmanager_secret.this : key => secret.arn }
  sensitive   = true
}

output "ssm_parameter_arns" {
  description = "SSM parameter ARNs keyed by logical name. Marked sensitive because SecureString names can reveal secret purpose."
  value       = { for key, parameter in aws_ssm_parameter.this : key => parameter.arn }
  sensitive   = true
}

output "ssm_parameter_names" {
  description = "SSM parameter names keyed by logical name."
  value       = { for key, parameter in aws_ssm_parameter.this : key => parameter.name }
  sensitive   = true
}
