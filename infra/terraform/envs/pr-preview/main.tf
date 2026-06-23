locals {
  environment = "pr-preview"
  preview_id  = "pr-${var.pr_number}"
  lambda_name = "${var.name_prefix}-${local.preview_id}-backend-lambda"

  common_tags = {
    Project      = "arte-chatbot"
    Environment  = local.environment
    ManagedBy    = "terraform"
    PreviewId    = local.preview_id
    PullRequest  = tostring(var.pr_number)
    GitSha       = var.pr_sha
    GitRef       = var.pr_head_ref
    ExpiresAt    = var.expiration_at
    CleanupAfter = var.expiration_at
  }
}

resource "terraform_data" "preview_guard" {
  input = local.preview_id

  lifecycle {
    precondition {
      condition     = !strcontains(lower(local.lambda_name), "prod") && !strcontains(lower(local.lambda_name), "production")
      error_message = "PR preview Lambda names must not contain production identifiers."
    }

    precondition {
      condition     = local.preview_id == "pr-${var.pr_number}"
      error_message = "PR preview ids must be derived from the pull request number."
    }
  }
}

module "lambda_backend" {
  source = "../../modules/lambda_backend"

  name                = local.lambda_name
  environment         = local.environment
  lambda_package_path = var.lambda_package_path
  aws_region          = var.aws_region
  aws_bucket_name     = var.aws_bucket_name

  state_key_prefix                           = local.preview_id
  state_table_deletion_protection_enabled    = false
  state_table_point_in_time_recovery_enabled = false
  session_ttl_seconds                        = var.lambda_session_ttl_seconds
  buffer_ttl_seconds                         = var.lambda_buffer_ttl_seconds
  rate_limit_ttl_seconds                     = var.lambda_rate_limit_ttl_seconds

  public_api_url       = null
  public_frontend_url  = var.public_frontend_url
  public_admin_url     = var.public_admin_url
  allowed_cors_origins = var.allowed_cors_origins
  timeout_seconds      = var.lambda_timeout_seconds
  memory_size          = var.lambda_memory_size
  api_stage_name       = "$default"
  alias_name           = "preview"

  runtime_environment_variables = merge(
    var.backend_runtime_environment_variables,
    {
      SECRET_NAMESPACE    = "/arte-chatbot/pr-preview/${local.preview_id}/"
      CLEANUP_AFTER       = var.expiration_at
      PREVIEW_ID          = local.preview_id
      PULL_REQUEST_NUMBER = tostring(var.pr_number)
      GIT_SHA             = var.pr_sha
    },
  )
  runtime_secret_arns = var.backend_runtime_secret_arns
  kms_key_arns        = var.kms_key_arns

  tags = merge(local.common_tags, { Service = "lambda-backend" })

  depends_on = [terraform_data.preview_guard]
}
