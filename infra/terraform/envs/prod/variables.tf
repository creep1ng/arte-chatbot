variable "aws_region" {
  description = "AWS region for production resources."
  type        = string
  default     = "us-east-1"
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

variable "domain_name" {
  description = "Base domain for production Cloudflare hostnames."
  type        = string
  default     = "artesolutions.com.co"
}

variable "vpc_id" {
  description = "Production VPC id."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet ids for ECS tasks. These need NAT or VPC endpoints for AWS and Cloudflare outbound access."
  type        = list(string)
}

variable "assign_public_ip" {
  description = "Assign public IPs to tasks. Prefer false when private subnets have NAT or VPC endpoints."
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
  description = "Secure base64 tunnel secret for the backend Cloudflare tunnel."
  type        = string
  sensitive   = true
}

variable "frontend_tunnel_secret" {
  description = "Secure base64 tunnel secret for the frontend Cloudflare tunnel."
  type        = string
  sensitive   = true
}

variable "admin_tunnel_secret" {
  description = "Secure base64 tunnel secret for the admin Cloudflare tunnel."
  type        = string
  sensitive   = true
}

variable "aws_bucket_name" {
  description = "S3 bucket used by the backend catalog and technical PDFs."
  type        = string
  default     = "arte-chatbot-data"
}

variable "backend_image_tag" {
  description = "Immutable backend image tag to deploy."
  type        = string
  default     = "bootstrap"
}

variable "frontend_image_tag" {
  description = "Immutable frontend image tag to deploy."
  type        = string
  default     = "bootstrap"
}

variable "admin_image_tag" {
  description = "Immutable admin image tag to deploy."
  type        = string
  default     = "bootstrap"
}

variable "cloudflared_image" {
  description = "cloudflared sidecar image."
  type        = string
  default     = "cloudflare/cloudflared:latest"
}

variable "backend_runtime_secret_arns" {
  description = "Backend app secret environment variables mapped to Secrets Manager or SSM ARNs, such as OPENAI_API_KEY and CHAT_API_KEY."
  type        = map(string)
  default     = {}
}

variable "task_cpu" {
  description = "Default Fargate CPU units for each service."
  type        = number
  default     = 512
}

variable "task_memory" {
  description = "Default Fargate memory MiB for each service."
  type        = number
  default     = 1024
}

variable "desired_count" {
  description = "Desired count for each production ECS service."
  type        = number
  default     = 1
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
