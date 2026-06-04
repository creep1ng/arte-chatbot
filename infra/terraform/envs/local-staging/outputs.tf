output "cluster_name" {
  description = "Local staging ECS cluster name."
  value       = aws_ecs_cluster.this.name
}

output "public_urls" {
  description = "Unique local staging Cloudflare public URLs."
  value = {
    api   = local.public_api_url
    app   = local.public_frontend_url
    admin = local.public_admin_url
  }
}

output "expiration_at" {
  description = "UTC cleanup deadline for this local staging environment."
  value       = var.expiration_at
}

output "ecs_services" {
  description = "Local staging ECS service names."
  value = {
    backend  = module.backend_service.service_name
    frontend = module.frontend_service.service_name
    admin    = module.admin_service.service_name
  }
}
