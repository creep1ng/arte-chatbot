locals {
  environment = "prod"

  public_api_url      = "https://${var.backend_hostname}"
  public_frontend_url = "https://${var.frontend_hostname}"
  public_admin_url    = "https://${var.admin_hostname}"

  allowed_cors_origins = join(",", [
    local.public_frontend_url,
    local.public_admin_url,
  ])

  lambda_name = "${var.name_prefix}-backend-lambda"

  common_tags = {
    Project     = "arte-chatbot"
    Environment = local.environment
    ManagedBy   = "terraform"
  }
}

module "backend_ecr" {
  source = "../../modules/ecr"

  repository_name = "${var.name_prefix}-backend"
  tags            = local.common_tags
}

module "frontend_ecr" {
  source = "../../modules/ecr"

  repository_name = "${var.name_prefix}-frontend"
  tags            = local.common_tags
}

module "admin_ecr" {
  source = "../../modules/ecr"

  repository_name = "${var.name_prefix}-admin"
  tags            = local.common_tags
}

module "lambda_backend" {
  source = "../../modules/lambda_backend"

  name                = local.lambda_name
  environment         = local.environment
  lambda_package_path = var.lambda_package_path
  aws_region          = var.aws_region
  aws_bucket_name     = var.aws_bucket_name

  state_key_prefix                           = "prod"
  state_table_deletion_protection_enabled    = true
  state_table_point_in_time_recovery_enabled = true
  session_ttl_seconds                        = var.lambda_session_ttl_seconds
  buffer_ttl_seconds                         = var.lambda_buffer_ttl_seconds
  rate_limit_ttl_seconds                     = var.lambda_rate_limit_ttl_seconds

  public_api_url       = local.public_api_url
  public_frontend_url  = local.public_frontend_url
  public_admin_url     = local.public_admin_url
  allowed_cors_origins = local.allowed_cors_origins
  timeout_seconds      = var.lambda_timeout_seconds
  memory_size          = var.lambda_memory_size
  api_stage_name       = "$default"
  alias_name           = "live"

  runtime_environment_variables = var.backend_runtime_environment_variables
  runtime_secret_arns           = var.backend_runtime_secret_arns
  kms_key_arns                  = var.kms_key_arns

  tags = merge(local.common_tags, { Service = "lambda-backend" })
}

resource "aws_acm_certificate" "backend" {
  count = var.enable_backend_custom_domain ? 1 : 0

  domain_name       = var.backend_hostname
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = merge(local.common_tags, { Service = "lambda-backend-api-domain" })
}

resource "cloudflare_dns_record" "backend_certificate_validation" {
  count = var.enable_backend_custom_domain ? 1 : 0

  zone_id = var.cloudflare_zone_id
  name = trimsuffix(
    tolist(aws_acm_certificate.backend[0].domain_validation_options)[0].resource_record_name,
    ".",
  )
  type = tolist(aws_acm_certificate.backend[0].domain_validation_options)[0].resource_record_type
  content = trimsuffix(
    tolist(aws_acm_certificate.backend[0].domain_validation_options)[0].resource_record_value,
    ".",
  )
  proxied = false
  ttl     = 60
}

resource "aws_acm_certificate_validation" "backend" {
  count = var.enable_backend_custom_domain ? 1 : 0

  certificate_arn = aws_acm_certificate.backend[0].arn
  validation_record_fqdns = [
    cloudflare_dns_record.backend_certificate_validation[0].name,
  ]
}

resource "aws_apigatewayv2_domain_name" "backend" {
  count = var.enable_backend_custom_domain ? 1 : 0

  domain_name = var.backend_hostname

  domain_name_configuration {
    certificate_arn = aws_acm_certificate_validation.backend[0].certificate_arn
    endpoint_type   = "REGIONAL"
    security_policy = "TLS_1_2"
  }

  tags = merge(local.common_tags, { Service = "lambda-backend-api-domain" })
}

resource "aws_apigatewayv2_api_mapping" "backend" {
  count = var.enable_backend_custom_domain ? 1 : 0

  api_id      = module.lambda_backend.http_api_id
  domain_name = aws_apigatewayv2_domain_name.backend[0].id
  stage       = "$default"
}

resource "cloudflare_dns_record" "backend" {
  count = var.enable_backend_custom_domain ? 1 : 0

  zone_id = var.cloudflare_zone_id
  name    = var.backend_hostname
  type    = "CNAME"
  content = aws_apigatewayv2_domain_name.backend[0].domain_name_configuration[0].target_domain_name
  proxied = true
  ttl     = 1
}

module "github_oidc" {
  count  = var.create_github_oidc_role ? 1 : 0
  source = "../../modules/github_oidc"

  github_owner      = var.github_owner
  github_repository = var.github_repository
  branch            = "main"
  role_name         = "${var.name_prefix}-github-deploy"
  preview_role_name = var.github_preview_role_name

  preview_resource_prefix      = "arte-chatbot-preview"
  preview_state_bucket_name    = var.preview_state_bucket_name
  preview_state_key_prefix     = var.preview_state_key_prefix
  preview_catalog_bucket_names = [var.aws_bucket_name]
  preview_kms_key_arns         = var.preview_kms_key_arns

  ecr_repository_arns = [
    module.backend_ecr.repository_arn,
    module.frontend_ecr.repository_arn,
    module.admin_ecr.repository_arn,
  ]

  lambda_function_arns = [module.lambda_backend.function_arn]
  lambda_alias_arns    = [module.lambda_backend.alias_arn]
  state_table_arns     = [module.lambda_backend.state_table_arn]
  secret_arns          = values(var.backend_runtime_secret_arns)
  tags                 = local.common_tags
}
