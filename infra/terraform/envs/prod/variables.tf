variable "aws_region" {
  description = "AWS region for production resources."
  type        = string
  default     = "us-east-2"
}

variable "name_prefix" {
  description = "Production resource name prefix."
  type        = string
  default     = "arte-chatbot-prod"

  validation {
    condition = (
      !strcontains(lower(var.name_prefix), "staging") &&
      !strcontains(lower(var.name_prefix), "local")
    )
    error_message = "Production name_prefix must not contain staging or local identifiers."
  }
}

variable "backend_hostname" {
  description = "Externally supplied production backend/API hostname. Terraform maps this host to API Gateway when enable_backend_custom_domain is true."
  type        = string
  sensitive   = true
}

variable "frontend_hostname" {
  description = "Externally supplied production frontend/app hostname. DNS may become public, but source defaults must not expose it."
  type        = string
  sensitive   = true
}

variable "admin_hostname" {
  description = "Externally supplied production admin hostname. DNS may become public, but source defaults must not expose it."
  type        = string
  sensitive   = true
}

variable "enable_backend_custom_domain" {
  description = "Create the API Gateway custom domain and Cloudflare DNS records for backend_hostname."
  type        = bool
  default     = true
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone id used only for backend custom-domain DNS records. Required when enable_backend_custom_domain is true."
  type        = string
  default     = ""
  sensitive   = true

  validation {
    condition     = !var.enable_backend_custom_domain || length(trimspace(var.cloudflare_zone_id)) > 0
    error_message = "cloudflare_zone_id is required when enable_backend_custom_domain is true."
  }
}

variable "aws_bucket_name" {
  description = "S3 bucket used by the backend catalog and technical PDFs."
  type        = string
  default     = "arte-chatbot-fichas-tecnicas"
}

variable "backend_runtime_environment_variables" {
  description = "Additional non-sensitive backend environment variables. Values must remain strings and must not contain secrets."
  type        = map(string)
  default     = {}
}

variable "backend_runtime_secret_arns" {
  description = "Backend app secret environment variables mapped to Secrets Manager or SSM ARNs, such as OPENAI_API_KEY and CHAT_API_KEY."
  type        = map(string)
  default     = {}

  validation {
    condition = alltrue([
      for value in values(var.backend_runtime_secret_arns) : startswith(value, "arn:")
    ])
    error_message = "backend_runtime_secret_arns values must be Secrets Manager or SSM ARNs, not raw secret values."
  }
}

variable "lambda_package_path" {
  description = "Path to the prebuilt production backend Lambda package."
  type        = string
  default     = "../../../../dist/lambda/backend.zip"
}

variable "lambda_memory_size" {
  description = "Production Lambda memory size in MiB."
  type        = number
  default     = 1024
}

variable "lambda_timeout_seconds" {
  description = "Production Lambda timeout in seconds."
  type        = number
  default     = 25
}

variable "lambda_session_ttl_seconds" {
  description = "Production session TTL."
  type        = number
  default     = 2592000
}

variable "lambda_buffer_ttl_seconds" {
  description = "Production buffer TTL."
  type        = number
  default     = 86400
}

variable "lambda_rate_limit_ttl_seconds" {
  description = "Production rate-limit TTL."
  type        = number
  default     = 86400
}

variable "kms_key_arns" {
  description = "Optional KMS keys needed by the Lambda runtime to decrypt runtime secret references."
  type        = list(string)
  default     = []
}

variable "github_owner" {
  description = "GitHub owner used by the OIDC deploy role."
  type        = string
  default     = ""
}

variable "github_repository" {
  description = "GitHub repository used by the OIDC deploy role."
  type        = string
  default     = "arte-chatbot"
}

variable "create_github_oidc_role" {
  description = "Create the shared GitHub OIDC provider plus separate production and PR preview deploy roles."
  type        = bool
  default     = false
}

variable "github_preview_role_name" {
  description = "Name of the GitHub Actions OIDC role dedicated to pull-request previews."
  type        = string
  default     = "arte-chatbot-preview-github-deploy"
}



variable "preview_kms_key_arns" {
  description = "Optional KMS keys used only for preview-scoped runtime secrets."
  type        = list(string)
  default     = []
}
