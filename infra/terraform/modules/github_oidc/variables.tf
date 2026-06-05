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

variable "ssm_instance_arns" {
  description = "EC2 instance ARNs that Actions can target with SSM Run Command."
  type        = list(string)
}

variable "ssm_document_arns" {
  description = "SSM document ARNs Actions can invoke for deployment commands."
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
