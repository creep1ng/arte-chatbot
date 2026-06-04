variable "repository_name" {
  description = "ECR repository name."
  type        = string

  validation {
    condition     = length(trimspace(var.repository_name)) > 0
    error_message = "repository_name is required."
  }
}

variable "image_tag_mutability" {
  description = "ECR image tag mutability."
  type        = string
  default     = "IMMUTABLE"

  validation {
    condition     = contains(["IMMUTABLE", "MUTABLE"], var.image_tag_mutability)
    error_message = "image_tag_mutability must be IMMUTABLE or MUTABLE."
  }
}

variable "scan_on_push" {
  description = "Enable ECR image scanning on push."
  type        = bool
  default     = true
}

variable "force_delete" {
  description = "Allow Terraform to delete repositories that still contain images."
  type        = bool
  default     = false
}

variable "lifecycle_policy_days" {
  description = "Number of days to retain untagged images."
  type        = number
  default     = 14
}

variable "tags" {
  description = "Tags applied to ECR resources."
  type        = map(string)
  default     = {}
}
