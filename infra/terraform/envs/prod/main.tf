locals {
  environment = "prod"

  hostname_labels = {
    api   = "chatbot"
    app   = "app"
    admin = "admin"
  }

  backend_hostname  = "${local.hostname_labels.api}.${var.domain_name}"
  frontend_hostname = "${local.hostname_labels.app}.${var.domain_name}"
  admin_hostname    = "${local.hostname_labels.admin}.${var.domain_name}"

  public_api_url      = "https://${local.backend_hostname}"
  public_frontend_url = "https://${local.frontend_hostname}"
  public_admin_url    = "https://${local.admin_hostname}"

  allowed_cors_origins = join(",", [
    local.public_frontend_url,
    local.public_admin_url,
  ])

  common_tags = {
    Project     = "arte-chatbot"
    Environment = local.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_ecs_cluster" "this" {
  name = var.name_prefix

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = local.common_tags
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

module "backend_cloudflare_tunnel" {
  source = "../../modules/cloudflare_tunnel"

  account_id    = var.cloudflare_account_id
  zone_id       = var.cloudflare_zone_id
  tunnel_name   = "${var.name_prefix}-backend"
  tunnel_secret = var.backend_tunnel_secret

  public_hostnames = [
    {
      hostname         = local.backend_hostname
      local_origin_url = "http://localhost:8000"
    }
  ]

  tags = ["project:arte-chatbot", "environment:prod", "service:backend"]
}

module "frontend_cloudflare_tunnel" {
  source = "../../modules/cloudflare_tunnel"

  account_id    = var.cloudflare_account_id
  zone_id       = var.cloudflare_zone_id
  tunnel_name   = "${var.name_prefix}-frontend"
  tunnel_secret = var.frontend_tunnel_secret

  public_hostnames = [
    {
      hostname         = local.frontend_hostname
      local_origin_url = "http://localhost:3000"
    }
  ]

  tags = ["project:arte-chatbot", "environment:prod", "service:frontend"]
}

module "admin_cloudflare_tunnel" {
  source = "../../modules/cloudflare_tunnel"

  account_id    = var.cloudflare_account_id
  zone_id       = var.cloudflare_zone_id
  tunnel_name   = "${var.name_prefix}-admin"
  tunnel_secret = var.admin_tunnel_secret

  public_hostnames = [
    {
      hostname         = local.admin_hostname
      local_origin_url = "http://localhost:3000"
    }
  ]

  tags = ["project:arte-chatbot", "environment:prod", "service:admin"]
}

module "cloudflare_tunnel_secrets" {
  source = "../../modules/ssm_secrets"

  name_prefix = var.name_prefix
  environment = local.environment

  secrets = {
    backend_cloudflare_tunnel_token = {
      description = "cloudflared connector token for backend production service"
      value       = module.backend_cloudflare_tunnel.tunnel_token
    }
    frontend_cloudflare_tunnel_token = {
      description = "cloudflared connector token for frontend production service"
      value       = module.frontend_cloudflare_tunnel.tunnel_token
    }
    admin_cloudflare_tunnel_token = {
      description = "cloudflared connector token for admin production service"
      value       = module.admin_cloudflare_tunnel.tunnel_token
    }
  }

  tags = local.common_tags
}

locals {
  tunnel_token_secret_arns = nonsensitive(module.cloudflare_tunnel_secrets.secret_arns)
}

data "aws_iam_policy_document" "backend_task_s3" {
  statement {
    sid = "ReadCatalogData"
    actions = [
      "s3:GetObject",
    ]
    resources = ["arn:aws:s3:::${var.aws_bucket_name}/*"]
  }

  statement {
    sid       = "ListCatalogBucket"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.aws_bucket_name}"]
  }
}

module "backend_service" {
  source = "../../modules/ecs_service"

  name             = "${var.name_prefix}-backend"
  environment      = local.environment
  cluster_arn      = aws_ecs_cluster.this.arn
  cluster_name     = aws_ecs_cluster.this.name
  vpc_id           = var.vpc_id
  subnet_ids       = var.private_subnet_ids
  assign_public_ip = var.assign_public_ip
  desired_count    = var.desired_count
  cpu              = var.task_cpu
  memory           = var.task_memory

  image_uri      = "${module.backend_ecr.repository_url}:${var.backend_image_tag}"
  container_name = "backend"
  container_port = 8000

  environment_variables = {
    APP_ENV              = "production"
    AWS_BUCKET_NAME      = var.aws_bucket_name
    AWS_REGION           = var.aws_region
    PUBLIC_API_URL       = local.public_api_url
    PUBLIC_FRONTEND_URL  = local.public_frontend_url
    PUBLIC_ADMIN_URL     = local.public_admin_url
    ALLOWED_CORS_ORIGINS = local.allowed_cors_origins
    PORT                 = "8000"
  }

  app_secrets = var.backend_runtime_secret_arns

  sidecar_containers = [
    {
      name      = "cloudflared"
      image     = var.cloudflared_image
      essential = true
      command   = ["tunnel", "--no-autoupdate", "run"]
      environment = {
        TUNNEL_ORIGIN_URL = "http://localhost:8000"
      }
      secrets = {
        TUNNEL_TOKEN = local.tunnel_token_secret_arns["backend_cloudflare_tunnel_token"]
      }
    }
  ]

  health_check_command  = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
  task_role_policy_json = data.aws_iam_policy_document.backend_task_s3.json
  ecr_repository_arns   = [module.backend_ecr.repository_arn]
  tags                  = merge(local.common_tags, { Service = "backend" })
}

module "frontend_service" {
  source = "../../modules/ecs_service"

  name             = "${var.name_prefix}-frontend"
  environment      = local.environment
  cluster_arn      = aws_ecs_cluster.this.arn
  cluster_name     = aws_ecs_cluster.this.name
  vpc_id           = var.vpc_id
  subnet_ids       = var.private_subnet_ids
  assign_public_ip = var.assign_public_ip
  desired_count    = var.desired_count
  cpu              = var.task_cpu
  memory           = var.task_memory

  image_uri      = "${module.frontend_ecr.repository_url}:${var.frontend_image_tag}"
  container_name = "frontend"
  container_port = 3000

  environment_variables = {
    API_URL = local.public_api_url
  }

  sidecar_containers = [
    {
      name      = "cloudflared"
      image     = var.cloudflared_image
      essential = true
      command   = ["tunnel", "--no-autoupdate", "run"]
      environment = {
        TUNNEL_ORIGIN_URL = "http://localhost:3000"
      }
      secrets = {
        TUNNEL_TOKEN = local.tunnel_token_secret_arns["frontend_cloudflare_tunnel_token"]
      }
    }
  ]

  health_check_command = ["CMD-SHELL", "wget -qO- http://localhost:3000/ >/dev/null || exit 1"]
  ecr_repository_arns  = [module.frontend_ecr.repository_arn]
  tags                 = merge(local.common_tags, { Service = "frontend" })
}

module "admin_service" {
  source = "../../modules/ecs_service"

  name             = "${var.name_prefix}-admin"
  environment      = local.environment
  cluster_arn      = aws_ecs_cluster.this.arn
  cluster_name     = aws_ecs_cluster.this.name
  vpc_id           = var.vpc_id
  subnet_ids       = var.private_subnet_ids
  assign_public_ip = var.assign_public_ip
  desired_count    = var.desired_count
  cpu              = var.task_cpu
  memory           = var.task_memory

  image_uri      = "${module.admin_ecr.repository_url}:${var.admin_image_tag}"
  container_name = "admin"
  container_port = 3000

  environment_variables = {
    API_URL = local.public_api_url
  }

  sidecar_containers = [
    {
      name      = "cloudflared"
      image     = var.cloudflared_image
      essential = true
      command   = ["tunnel", "--no-autoupdate", "run"]
      environment = {
        TUNNEL_ORIGIN_URL = "http://localhost:3000"
      }
      secrets = {
        TUNNEL_TOKEN = local.tunnel_token_secret_arns["admin_cloudflare_tunnel_token"]
      }
    }
  ]

  health_check_command = ["CMD-SHELL", "wget -qO- http://localhost:3000/ >/dev/null || exit 1"]
  ecr_repository_arns  = [module.admin_ecr.repository_arn]
  tags                 = merge(local.common_tags, { Service = "admin" })
}

module "github_oidc" {
  count  = var.create_github_oidc_role ? 1 : 0
  source = "../../modules/github_oidc"

  github_owner      = var.github_owner
  github_repository = var.github_repository
  branch            = "main"
  role_name         = "${var.name_prefix}-github-deploy"

  ecr_repository_arns = [
    module.backend_ecr.repository_arn,
    module.frontend_ecr.repository_arn,
    module.admin_ecr.repository_arn,
  ]
  ecs_cluster_arn = aws_ecs_cluster.this.arn
  ecs_service_arns = [
    module.backend_service.service_arn,
    module.frontend_service.service_arn,
    module.admin_service.service_arn,
  ]
  pass_role_arns = [
    module.backend_service.task_role_arn,
    module.backend_service.execution_role_arn,
    module.frontend_service.task_role_arn,
    module.frontend_service.execution_role_arn,
    module.admin_service.task_role_arn,
    module.admin_service.execution_role_arn,
  ]

  secret_arns = values(local.tunnel_token_secret_arns)
  tags        = local.common_tags
}
