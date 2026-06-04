variable "aws_region" {
  description = "AWS region for local staging resources."
  type        = string
  default     = "us-east-2"
}

variable "staging_id" {
  description = "Unique local staging id, usually pr-<number> or a developer/candidate identifier."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,30}$", var.staging_id))
    error_message = "staging_id must be 2-31 chars using lowercase letters, numbers, and hyphens."
  }

  validation {
    condition = !contains([
      "api",
      "app",
      "admin",
      "prod",
      "production",
      "main",
    ], lower(var.staging_id)) && !strcontains(lower(var.staging_id), "prod")
    error_message = "staging_id must not collide with production hostnames or names."
  }
}

variable "domain_name" {
  description = "Base Cloudflare domain. Local staging derives staging-chatbot-* hostnames from this domain."
  type        = string
  default     = "artesolutions.com.co"

  validation {
    condition     = var.domain_name == "artesolutions.com.co"
    error_message = "Local staging must use the Arte Cloudflare domain artesolutions.com.co."
  }
}

variable "vpc_id" {
  description = "VPC id used by local staging ECS tasks."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet ids for local staging ECS tasks. These need NAT or VPC endpoints for outbound access."
  type        = list(string)
}

variable "assign_public_ip" {
  description = "Assign public IPs to local staging tasks. Prefer false when private subnets have NAT or VPC endpoints."
  type        = bool
  default     = false
}

variable "cloudflare_account_id" {
  description = "Cloudflare account id."
  type        = string
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone id for domain_name."
  type        = string
}

variable "backend_tunnel_secret" {
  description = "Local-staging-only backend tunnel secret. Do not reuse production tunnel material."
  type        = string
  sensitive   = true
}

variable "frontend_tunnel_secret" {
  description = "Local-staging-only frontend tunnel secret. Do not reuse production tunnel material."
  type        = string
  sensitive   = true
}

variable "admin_tunnel_secret" {
  description = "Local-staging-only admin tunnel secret. Do not reuse production tunnel material."
  type        = string
  sensitive   = true
}

variable "backend_ecr_repository_url" {
  description = "Existing backend ECR repository URL that contains the explicit candidate tag."
  type        = string
}

variable "frontend_ecr_repository_url" {
  description = "Existing frontend ECR repository URL that contains the explicit candidate tag."
  type        = string
}

variable "admin_ecr_repository_url" {
  description = "Existing admin ECR repository URL that contains the explicit candidate tag."
  type        = string
}

variable "backend_ecr_repository_arn" {
  description = "Backend ECR repository ARN allowed for task execution pulls."
  type        = string
}

variable "frontend_ecr_repository_arn" {
  description = "Frontend ECR repository ARN allowed for task execution pulls."
  type        = string
}

variable "admin_ecr_repository_arn" {
  description = "Admin ECR repository ARN allowed for task execution pulls."
  type        = string
}

variable "backend_image_tag" {
  description = "Explicit immutable backend ECR tag for this local staging environment."
  type        = string

  validation {
    condition     = can(regex("^(sha-[0-9a-fA-F]{7,40}|pr-[0-9]+-sha-[0-9a-fA-F]{7,40}|local-[a-zA-Z0-9._-]+)$", var.backend_image_tag))
    error_message = "backend_image_tag must be an explicit immutable candidate tag."
  }
}

variable "frontend_image_tag" {
  description = "Explicit immutable frontend ECR tag for this local staging environment."
  type        = string

  validation {
    condition     = can(regex("^(sha-[0-9a-fA-F]{7,40}|pr-[0-9]+-sha-[0-9a-fA-F]{7,40}|local-[a-zA-Z0-9._-]+)$", var.frontend_image_tag))
    error_message = "frontend_image_tag must be an explicit immutable candidate tag."
  }
}

variable "admin_image_tag" {
  description = "Explicit immutable admin ECR tag for this local staging environment."
  type        = string

  validation {
    condition     = can(regex("^(sha-[0-9a-fA-F]{7,40}|pr-[0-9]+-sha-[0-9a-fA-F]{7,40}|local-[a-zA-Z0-9._-]+)$", var.admin_image_tag))
    error_message = "admin_image_tag must be an explicit immutable candidate tag."
  }
}

variable "expiration_at" {
  description = "UTC expiration timestamp for cleanup visibility, format YYYY-MM-DDTHH:MM:SSZ. The deploy script enforces <= 3 days."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", var.expiration_at))
    error_message = "expiration_at must use YYYY-MM-DDTHH:MM:SSZ UTC format."
  }
}

variable "aws_bucket_name" {
  description = "Non-production or explicitly approved S3 bucket for local staging catalog/PDF reads."
  type        = string

  validation {
    condition     = !contains(["arte-chatbot-fichas-tecnicas", "arte-chatbot-prod"], lower(var.aws_bucket_name))
    error_message = "Local staging rejects production S3 buckets by default. Use a staging/test bucket or document an exception outside this root."
  }
}

variable "backend_runtime_secret_arns" {
  description = "Local-staging-only app secret ARNs, such as OPENAI_API_KEY and CHAT_API_KEY. Do not pass production secret ARNs."
  type        = map(string)
  default     = {}

  validation {
    condition = alltrue([
      for arn in values(var.backend_runtime_secret_arns) : strcontains(lower(arn), "local-staging") || strcontains(lower(arn), "staging")
    ])
    error_message = "Local staging secret ARNs must be staging/local-staging scoped."
  }
}

variable "cloudflared_image" {
  description = "cloudflared sidecar image."
  type        = string
  default     = "cloudflare/cloudflared:latest"
}

variable "task_cpu" {
  description = "Default Fargate CPU units for local staging services."
  type        = number
  default     = 512
}

variable "task_memory" {
  description = "Default Fargate memory MiB for local staging services."
  type        = number
  default     = 1024
}

variable "desired_count" {
  description = "Desired local staging task count."
  type        = number
  default     = 1
}
