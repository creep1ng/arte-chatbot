variable "github_owner" {
  description = "GitHub organization or user."
  type        = string
}

variable "github_repository" {
  description = "GitHub repository name."
  type        = string
}

variable "branch" {
  description = "Branch allowed to deploy production."
  type        = string
  default     = "main"
}

variable "role_name" {
  description = "AWS role name for GitHub Actions deployment."
  type        = string
}

variable "ecr_repository_arns" {
  description = "ECR repositories Actions can push/pull."
  type        = list(string)
}

variable "ecs_cluster_arn" {
  description = "ECS cluster Actions can deploy to."
  type        = string
}

variable "ecs_service_arns" {
  description = "ECS services Actions can update."
  type        = list(string)
}

variable "pass_role_arns" {
  description = "Task and execution roles Actions may pass to ECS."
  type        = list(string)
}

variable "secret_arns" {
  description = "Secret/parameter ARNs Actions can describe during deployment."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags applied to role resources."
  type        = map(string)
  default     = {}
}
