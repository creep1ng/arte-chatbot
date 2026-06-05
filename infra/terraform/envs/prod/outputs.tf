output "public_urls" {
  description = "Production Cloudflare public URLs derived from externally supplied hostnames."
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

output "ec2_compose_host" {
  description = "Production EC2 Compose host metadata for SSM deploys."
  value = {
    instance_id               = module.compose_host.instance_id
    security_group_id         = module.compose_host.security_group_id
    deploy_script_path        = module.compose_host.deploy_script_path
    compose_project_directory = module.compose_host.compose_project_directory
  }
}

output "edge_tunnel" {
  description = "Central production Cloudflare tunnel metadata."
  value = {
    tunnel_id   = module.edge_tunnel.tunnel_id
    tunnel_name = module.edge_tunnel.tunnel_name
    hostnames   = module.edge_tunnel.hostnames
  }
  sensitive = true
}

output "github_deploy_role_arn" {
  description = "Optional GitHub Actions deploy role ARN."
  value       = var.create_github_oidc_role ? module.github_oidc[0].role_arn : null
}
