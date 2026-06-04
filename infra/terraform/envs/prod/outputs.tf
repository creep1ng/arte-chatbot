output "cluster_name" {
  description = "Production ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "public_urls" {
  description = "Production Cloudflare public URLs."
  value = {
    api   = local.public_api_url
    app   = local.public_frontend_url
    admin = local.public_admin_url
  }
}

output "ecr_repository_urls" {
  description = "ECR repositories for independently built service images."
  value = {
    backend  = module.backend_ecr.repository_url
    frontend = module.frontend_ecr.repository_url
    admin    = module.admin_ecr.repository_url
  }
}

output "ecs_services" {
  description = "ECS service names."
  value = {
    backend  = module.backend_service.service_name
    frontend = module.frontend_service.service_name
    admin    = module.admin_service.service_name
  }
}

output "github_deploy_role_arn" {
  description = "Optional GitHub Actions deploy role ARN."
  value       = var.create_github_oidc_role ? module.github_oidc[0].role_arn : null
}
