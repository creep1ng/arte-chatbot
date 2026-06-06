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

variable "vpc_id" {
  description = "Production VPC id."
  type        = string
}

variable "public_subnet_id" {
  description = "Public subnet id for the low-cost EC2 Compose host. The host exposes no public app ports and uses Cloudflare Tunnel for ingress."
  type        = string
}

variable "ec2_compose_instance_type" {
  description = "EC2 instance type for the production Docker Compose host."
  type        = string
  default     = "t3.small"
}

variable "ami_id_override" {
  description = "Optional emergency AMI id override. Leave null to use the latest Ubuntu LTS AMI data source."
  type        = string
  default     = null
}

variable "cloudflare_account_id" {
  description = "Cloudflare account id."
  type        = string
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone id for production DNS records."
  type        = string
}

variable "backend_hostname" {
  description = "Externally supplied production backend/API hostname. DNS may become public, but source defaults must not expose it."
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

variable "edge_tunnel_secret" {
  description = "Secure base64 tunnel secret for the central production Cloudflare tunnel."
  type        = string
  sensitive   = true
}

variable "aws_bucket_name" {
  description = "S3 bucket used by the backend catalog and technical PDFs."
  type        = string
  default     = "arte-chatbot-fichas-tecnicas"
}

variable "initial_image_tag" {
  description = "Initial immutable image tag written before the first SSM deploy."
  type        = string
  default     = "bootstrap"
}

variable "cloudflared_image" {
  description = "cloudflared connector image."
  type        = string
  default     = "cloudflare/cloudflared:latest"
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

variable "kms_key_arns" {
  description = "Optional KMS keys needed by the EC2 host to decrypt runtime secrets."
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
  description = "Create the GitHub Actions OIDC deployment role for main-branch production deploys."
  type        = bool
  default     = false
}
