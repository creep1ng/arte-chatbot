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
  description = "AWS role name for GitHub Actions production deployment."
  type        = string
}

variable "preview_role_name" {
  description = "AWS role name for GitHub Actions pull-request preview deployment."
  type        = string
}

variable "preview_resource_prefix" {
  description = "Required name prefix for resources managed by the preview deployment role."
  type        = string
  default     = "arte-chatbot-preview"
}



variable "preview_catalog_bucket_names" {
  description = "S3 catalog buckets that preview Lambda runtimes may read."
  type        = list(string)
}

variable "preview_kms_key_arns" {
  description = "Optional KMS keys used only for preview-scoped runtime secrets."
  type        = list(string)
  default     = []
}

variable "ecr_repository_arns" {
  description = "ECR repositories Actions can push/pull."
  type        = list(string)
}

variable "ssm_instance_arns" {
  description = "EC2 instance ARNs that Actions can target with SSM Run Command."
  type        = list(string)
  default     = []
}

variable "ssm_document_arns" {
  description = "SSM document ARNs Actions can invoke for deployment commands."
  type        = list(string)
  default     = []
}

variable "lambda_function_arns" {
  description = "Lambda function ARNs Actions can update and publish during production deployment."
  type        = list(string)
  default     = []
}

variable "lambda_alias_arns" {
  description = "Lambda alias ARNs Actions can inspect and update during production deployment."
  type        = list(string)
  default     = []
}

variable "state_table_arns" {
  description = "DynamoDB state table ARNs Actions can read during production smoke validation."
  type        = list(string)
  default     = []
}

variable "secret_arns" {
  description = "Secret/parameter ARNs Actions can describe during production deployment."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags applied to role resources."
  type        = map(string)
  default     = {}
}
