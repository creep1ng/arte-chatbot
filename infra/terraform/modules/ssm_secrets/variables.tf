variable "name_prefix" {
  description = "Namespace prefix for secrets and parameters."
  type        = string
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
}

variable "secrets" {
  description = "Secrets Manager values to create. Values must come from sensitive Terraform expressions or variables."
  type = map(object({
    description = optional(string, "Managed by Terraform")
    value       = string
  }))
  default   = {}
  sensitive = true
}

variable "ssm_parameters" {
  description = "SSM parameters to create. Use secure=true for sensitive values."
  type = map(object({
    description = optional(string, "Managed by Terraform")
    value       = string
    secure      = optional(bool, false)
  }))
  default   = {}
  sensitive = true
}

variable "tags" {
  description = "Tags applied to created resources."
  type        = map(string)
  default     = {}
}
