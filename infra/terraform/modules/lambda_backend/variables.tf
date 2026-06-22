variable "name" {
  description = "Base name for Lambda backend resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
}

variable "lambda_package_path" {
  description = "Path to the prebuilt Lambda zip package. The package is produced by CI/CD and must not contain local secret files."
  type        = string
}

variable "handler" {
  description = "Lambda handler entrypoint."
  type        = string
  default     = "backend.main.handler"
}

variable "runtime" {
  description = "Lambda Python runtime."
  type        = string
  default     = "python3.12"
}

variable "memory_size" {
  description = "Lambda memory size in MiB."
  type        = number
  default     = 1024
}

variable "timeout_seconds" {
  description = "Lambda timeout in seconds. Keep below API Gateway's integration timeout budget."
  type        = number
  default     = 25
}

variable "aws_region" {
  description = "AWS region for runtime configuration."
  type        = string
}

variable "aws_bucket_name" {
  description = "S3 bucket used by the backend catalog and technical PDFs."
  type        = string
}

variable "state_key_prefix" {
  description = "DynamoDB key prefix used to isolate environment state."
  type        = string
}

variable "state_table_billing_mode" {
  description = "DynamoDB state table billing mode."
  type        = string
  default     = "PAY_PER_REQUEST"
}

variable "state_table_deletion_protection_enabled" {
  description = "Enable deletion protection on the DynamoDB state table."
  type        = bool
  default     = false
}

variable "state_table_point_in_time_recovery_enabled" {
  description = "Enable point-in-time recovery on the DynamoDB state table."
  type        = bool
  default     = true
}

variable "session_ttl_seconds" {
  description = "Session item TTL in seconds."
  type        = number
  default     = 2592000
}

variable "buffer_ttl_seconds" {
  description = "Buffer item TTL in seconds."
  type        = number
  default     = 86400
}

variable "rate_limit_ttl_seconds" {
  description = "Rate limit item TTL in seconds."
  type        = number
  default     = 86400
}

variable "public_api_url" {
  description = "Public API URL exposed to the runtime."
  type        = string
  default     = null
}

variable "public_frontend_url" {
  description = "Public frontend URL exposed to the runtime."
  type        = string
  default     = null
}

variable "public_admin_url" {
  description = "Public admin URL exposed to the runtime."
  type        = string
  default     = null
}

variable "allowed_cors_origins" {
  description = "Comma-separated CORS origins for the backend."
  type        = string
}

variable "runtime_environment_variables" {
  description = "Additional non-sensitive Lambda runtime environment variables."
  type        = map(string)
  default     = {}
}

variable "runtime_secret_arns" {
  description = "Runtime secret references by app environment variable name. Values must be SSM or Secrets Manager ARNs; plaintext secrets are not accepted."
  type        = map(string)
  default     = {}

  validation {
    condition = alltrue([
      for arn in values(var.runtime_secret_arns) : startswith(arn, "arn:")
    ])
    error_message = "runtime_secret_arns values must be SSM or Secrets Manager ARNs, not raw secret values."
  }
}

variable "kms_key_arns" {
  description = "Optional KMS keys needed to decrypt runtime secret references."
  type        = list(string)
  default     = []
}

variable "access_log_retention_days" {
  description = "CloudWatch log retention days for Lambda and API Gateway access logs."
  type        = number
  default     = 14
}

variable "api_stage_name" {
  description = "HTTP API stage name."
  type        = string
  default     = "$default"
}

variable "alias_name" {
  description = "Lambda alias name receiving API Gateway traffic."
  type        = string
  default     = "live"
}

variable "tags" {
  description = "Tags applied to resources."
  type        = map(string)
  default     = {}
}
