variable "name" {
  description = "Name used for EC2 Compose host resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment label."
  type        = string
}

variable "vpc_id" {
  description = "VPC id for the EC2 Compose host security group."
  type        = string
}

variable "subnet_id" {
  description = "Public subnet id where the EC2 Compose host runs."
  type        = string
}

variable "ami_id" {
  description = "AMI id selected by the caller, normally from the latest Ubuntu LTS data source."
  type        = string
}

variable "ami_id_override" {
  description = "Optional emergency AMI override recorded at the module boundary."
  type        = string
  default     = null
}

variable "instance_type" {
  description = "EC2 instance size for the Compose host."
  type        = string
  default     = "t3.small"
}

variable "backend_image_uri" {
  description = "Backend ECR image URI without tag."
  type        = string
}

variable "frontend_image_uri" {
  description = "Frontend ECR image URI without tag."
  type        = string
}

variable "admin_image_uri" {
  description = "Admin ECR image URI without tag."
  type        = string
}

variable "cloudflared_image" {
  description = "Cloudflared connector image."
  type        = string
  default     = "cloudflare/cloudflared:latest"
}

variable "initial_image_tag" {
  description = "Initial immutable image tag written before the first SSM deploy."
  type        = string
  default     = "bootstrap"
}

variable "public_api_url" {
  description = "Public Cloudflare API URL passed to runtime config."
  type        = string
}

variable "public_frontend_url" {
  description = "Public Cloudflare frontend URL passed to runtime config."
  type        = string
}

variable "public_admin_url" {
  description = "Public Cloudflare admin URL passed to runtime config."
  type        = string
}

variable "allowed_cors_origins" {
  description = "Comma-separated backend CORS origins."
  type        = string
}

variable "aws_region" {
  description = "AWS region used by application runtime and ECR login."
  type        = string
}

variable "aws_bucket_name" {
  description = "S3 bucket used by backend catalog and PDF access."
  type        = string
}

variable "backend_runtime_environment_variables" {
  description = "Additional non-sensitive backend environment variables. Values must remain strings."
  type        = map(string)
  default     = {}
}

variable "backend_runtime_secret_arns" {
  description = "Backend secret environment variables mapped to Secrets Manager or SSM ARNs."
  type        = map(string)
  default     = {}
}

variable "cloudflare_tunnel_token_secret_arn" {
  description = "Secrets Manager or SSM ARN containing the Cloudflare Tunnel connector token."
  type        = string
  sensitive   = true
}

variable "kms_key_arns" {
  description = "Optional KMS keys needed to decrypt runtime secrets."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags applied to resources."
  type        = map(string)
  default     = {}
}
