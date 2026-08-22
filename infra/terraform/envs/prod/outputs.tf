output "public_urls" {
  description = "Production public URLs derived from externally supplied hostnames."
  value = {
    api   = local.public_api_url
    app   = local.public_frontend_url
    admin = local.public_admin_url
  }
  sensitive = true
}

output "ecr_repository_urls" {
  description = "ECR repositories for independently built service images."
  value = {
    backend  = module.backend_ecr.repository_url
    frontend = module.frontend_ecr.repository_url
    admin    = module.admin_ecr.repository_url
  }
}

output "lambda_backend" {
  description = "Production Lambda backend metadata for direct smoke checks, promotion, and rollback."
  value = {
    function_name     = module.lambda_backend.function_name
    alias_name        = module.lambda_backend.alias_name
    published_version = module.lambda_backend.published_version
    http_api_id       = module.lambda_backend.http_api_id
    invoke_url        = module.lambda_backend.invoke_url
    state_table_name  = module.lambda_backend.state_table_name
    role_arn          = module.lambda_backend.role_arn
  }
}

output "backend_custom_domain" {
  description = "Production backend custom-domain metadata for DNS and smoke checks."
  value = var.enable_backend_custom_domain ? {
    hostname                    = nonsensitive(var.backend_hostname)
    public_url                  = nonsensitive(local.public_api_url)
    api_gateway_target_hostname = aws_apigatewayv2_domain_name.backend[0].domain_name_configuration[0].target_domain_name
    cloudflare_record_name      = nonsensitive(cloudflare_dns_record.backend[0].name)
    certificate_arn             = aws_acm_certificate.backend[0].arn
  } : null
}

output "github_deploy_role_arn" {
  description = "Optional GitHub Actions production deploy role ARN."
  value       = var.create_github_oidc_role ? module.github_oidc[0].role_arn : null
}

output "github_preview_deploy_role_arn" {
  description = "Optional GitHub Actions PR preview deploy role ARN."
  value       = var.create_github_oidc_role ? module.github_oidc[0].preview_role_arn : null
}

output "preview_lambda_permissions_boundary_arn" {
  description = "Optional permissions boundary ARN required by PR preview Lambda execution roles."
  value       = var.create_github_oidc_role ? module.github_oidc[0].preview_lambda_permissions_boundary_arn : null
}

output "preview_lambda_execution_role_arn" {
  description = "Optional foundation-managed execution role ARN shared by PR preview Lambdas."
  value       = var.create_github_oidc_role ? module.github_oidc[0].preview_lambda_execution_role_arn : null
}
