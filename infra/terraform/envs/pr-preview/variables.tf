variable "aws_region" {
  description = "AWS region for PR preview resources."
  type        = string
  default     = "us-east-2"
}

variable "name_prefix" {
  description = "Base prefix for ephemeral PR preview resources."
  type        = string
  default     = "arte-chatbot-preview"

  validation {
    condition = (
      !strcontains(lower(var.name_prefix), "prod") &&
      !strcontains(lower(var.name_prefix), "production") &&
      !strcontains(lower(var.name_prefix), "main")
    )
    error_message = "Preview name_prefix must not contain production or main identifiers."
  }
}

variable "pr_number" {
  description = "GitHub pull request number used to isolate this preview."
  type        = number

  validation {
    condition     = var.pr_number > 0
    error_message = "pr_number must be a positive pull request number."
  }
}

variable "pr_sha" {
  description = "Git commit SHA deployed to the preview."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-fA-F]{7,40}$", var.pr_sha))
    error_message = "pr_sha must be a 7-40 character hexadecimal Git SHA."
  }
}

variable "pr_head_ref" {
  description = "GitHub pull request head ref for traceability tags."
  type        = string
  default     = ""
}

variable "expiration_at" {
  description = "UTC expiration timestamp for cleanup visibility, format YYYY-MM-DDTHH:MM:SSZ."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", var.expiration_at))
    error_message = "expiration_at must use YYYY-MM-DDTHH:MM:SSZ UTC format."
  }
}

variable "aws_bucket_name" {
  description = "S3 bucket used by the preview backend catalog and technical PDFs."
  type        = string
}

variable "backend_runtime_secret_arns" {
  description = "Preview app secret ARNs, such as OPENAI_API_KEY and CHAT_API_KEY. Every ARN must use the /arte-chatbot/pr-preview/ namespace enforced by the execution-role boundary."
  type        = map(string)
  default     = {}

  validation {
    condition = alltrue([
      for arn in values(var.backend_runtime_secret_arns) : (
        startswith(arn, "arn:") &&
        strcontains(lower(arn), "/arte-chatbot/pr-preview/")
      )
    ])
    error_message = "Preview secret refs must be AWS ARNs in the /arte-chatbot/pr-preview/ namespace."
  }
}

variable "lambda_permissions_boundary_arn" {
  description = "Foundation-managed permissions boundary ARN required on every preview Lambda execution role."
  type        = string

  validation {
    condition     = startswith(var.lambda_permissions_boundary_arn, "arn:aws:iam::")
    error_message = "lambda_permissions_boundary_arn must be an IAM policy ARN."
  }
}

variable "lambda_execution_role_arn" {
  description = "Foundation-managed execution role ARN shared by PR preview Lambdas."
  type        = string

  validation {
    condition     = startswith(var.lambda_execution_role_arn, "arn:aws:iam::")
    error_message = "lambda_execution_role_arn must be an IAM role ARN."
  }
}

variable "backend_runtime_environment_variables" {
  description = "Additional non-sensitive PR preview backend runtime environment variables."
  type        = map(string)
  default     = {}
}

variable "lambda_package_path" {
  description = "Path to the prebuilt backend Lambda package for this preview."
  type        = string
  default     = "../../../../dist/lambda/backend.zip"
}

variable "lambda_memory_size" {
  description = "Preview Lambda memory size in MiB."
  type        = number
  default     = 1024
}

variable "lambda_timeout_seconds" {
  description = "Preview Lambda timeout in seconds."
  type        = number
  default     = 25
}

variable "lambda_session_ttl_seconds" {
  description = "Preview session TTL. Defaults to three days to bound stale state."
  type        = number
  default     = 259200
}

variable "lambda_buffer_ttl_seconds" {
  description = "Preview buffer TTL. Defaults to one day."
  type        = number
  default     = 86400
}

variable "lambda_rate_limit_ttl_seconds" {
  description = "Preview rate-limit TTL. Defaults to one day."
  type        = number
  default     = 86400
}

variable "kms_key_arns" {
  description = "Optional KMS keys needed by Lambda to decrypt preview runtime secret references."
  type        = list(string)
  default     = []
}

variable "allowed_cors_origins" {
  description = "Comma-separated CORS origins for the preview backend. Defaults to wildcard because preview uses direct API Gateway URLs."
  type        = string
  default     = "*"
}

variable "public_frontend_url" {
  description = "Optional public frontend URL exposed to the preview runtime."
  type        = string
  default     = null
}

variable "public_admin_url" {
  description = "Optional public admin URL exposed to the preview runtime."
  type        = string
  default     = null
}
