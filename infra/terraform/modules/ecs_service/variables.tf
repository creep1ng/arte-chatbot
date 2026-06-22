variable "name" {
  description = "ECS service/task family name."
  type        = string
}

variable "environment" {
  description = "Deployment environment label."
  type        = string
}

variable "cluster_arn" {
  description = "ECS cluster ARN."
  type        = string
}

variable "cluster_name" {
  description = "ECS cluster name."
  type        = string
}

variable "vpc_id" {
  description = "VPC id used by the Fargate service."
  type        = string
}

variable "subnet_ids" {
  description = "Subnet ids for awsvpc networking."
  type        = list(string)
}

variable "assign_public_ip" {
  description = "Assign a public IP to Fargate tasks. Prefer false when NAT or VPC endpoints exist."
  type        = bool
  default     = false
}

variable "desired_count" {
  description = "Desired ECS service task count."
  type        = number
  default     = 1
}

variable "cpu" {
  description = "Fargate task CPU units."
  type        = number
}

variable "memory" {
  description = "Fargate task memory MiB."
  type        = number
}

variable "image_uri" {
  description = "Application image URI including immutable tag."
  type        = string
}

variable "container_name" {
  description = "Application container name."
  type        = string
}

variable "container_port" {
  description = "Application container port exposed to the same-task tunnel sidecar."
  type        = number
}

variable "environment_variables" {
  description = "Non-sensitive app environment variables."
  type        = map(string)
  default     = {}
}

variable "app_secrets" {
  description = "Application secret environment variables mapped to SSM/Secrets Manager ARNs."
  type        = map(string)
  default     = {}
}

variable "sidecar_containers" {
  description = "Sidecars colocated with the app container, such as cloudflared."
  type = list(object({
    name        = string
    image       = string
    essential   = optional(bool, true)
    command     = optional(list(string), [])
    environment = optional(map(string), {})
    secrets     = optional(map(string), {})
  }))
  default = []
}

variable "health_check_command" {
  description = "Optional ECS container health check command."
  type        = list(string)
  default     = []
}

variable "task_role_policy_json" {
  description = "Optional inline policy JSON attached only to the app task role."
  type        = string
  default     = null
}

variable "ecr_repository_arns" {
  description = "ECR repository ARNs the execution role can pull from."
  type        = list(string)
}

variable "kms_key_arns" {
  description = "Optional KMS keys needed for secret decryption."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags applied to resources."
  type        = map(string)
  default     = {}
}
