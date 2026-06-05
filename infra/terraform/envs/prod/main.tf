locals {
  environment = "prod"

  public_api_url      = "https://${var.backend_hostname}"
  public_frontend_url = "https://${var.frontend_hostname}"
  public_admin_url    = "https://${var.admin_hostname}"

  allowed_cors_origins = join(",", [
    local.public_frontend_url,
    local.public_admin_url,
  ])

  compose_host_ami_id = coalesce(var.ami_id_override, data.aws_ami.ubuntu_lts.id)

  common_tags = {
    Project     = "arte-chatbot"
    Environment = local.environment
    ManagedBy   = "terraform"
  }
}

data "aws_partition" "current" {}

data "aws_caller_identity" "current" {}

data "aws_ami" "ubuntu_lts" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-*-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "root-device-type"
    values = ["ebs"]
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

module "edge_tunnel" {
  source = "../../modules/cloudflare_tunnel"

  account_id             = var.cloudflare_account_id
  zone_id                = var.cloudflare_zone_id
  tunnel_name            = "${var.name_prefix}-edge"
  tunnel_secret          = var.edge_tunnel_secret
  central_connector_mode = true

  public_hostnames = [
    {
      hostname         = var.backend_hostname
      local_origin_url = "http://backend:8000"
    },
    {
      hostname         = var.frontend_hostname
      local_origin_url = "http://frontend:3000"
    },
    {
      hostname         = var.admin_hostname
      local_origin_url = "http://admin:3000"
    },
  ]

  tags = ["project:arte-chatbot", "environment:prod", "mode:central-compose"]
}

module "cloudflare_tunnel_secrets" {
  source = "../../modules/ssm_secrets"

  name_prefix = var.name_prefix
  environment = local.environment

  secrets = {
    edge_cloudflare_tunnel_token = {
      description = "cloudflared connector token for the production EC2 Compose edge tunnel"
      value       = module.edge_tunnel.tunnel_token
    }
  }

  tags = local.common_tags
}

locals {
  tunnel_token_secret_arns = nonsensitive(module.cloudflare_tunnel_secrets.secret_arns)
}

module "compose_host" {
  source = "../../modules/ec2_compose_host"

  name        = "${var.name_prefix}-compose"
  environment = local.environment
  vpc_id      = var.vpc_id
  subnet_id   = var.public_subnet_id

  ami_id            = local.compose_host_ami_id
  ami_id_override   = var.ami_id_override
  instance_type     = var.ec2_compose_instance_type
  cloudflared_image = var.cloudflared_image
  initial_image_tag = var.initial_image_tag

  backend_image_uri  = module.backend_ecr.repository_url
  frontend_image_uri = module.frontend_ecr.repository_url
  admin_image_uri    = module.admin_ecr.repository_url

  public_api_url       = local.public_api_url
  public_frontend_url  = local.public_frontend_url
  public_admin_url     = local.public_admin_url
  allowed_cors_origins = local.allowed_cors_origins

  aws_region      = var.aws_region
  aws_bucket_name = var.aws_bucket_name

  backend_runtime_environment_variables = var.backend_runtime_environment_variables
  backend_runtime_secret_arns           = var.backend_runtime_secret_arns
  cloudflare_tunnel_token_secret_arn    = local.tunnel_token_secret_arns["edge_cloudflare_tunnel_token"]
  kms_key_arns                          = var.kms_key_arns

  tags = merge(local.common_tags, { Service = "compose-host" })
}

locals {
  compose_host_instance_arn = "arn:${data.aws_partition.current.partition}:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:instance/${module.compose_host.instance_id}"
  ssm_run_shell_script_arn  = "arn:${data.aws_partition.current.partition}:ssm:${var.aws_region}::document/AWS-RunShellScript"
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

  ssm_instance_arns = [local.compose_host_instance_arn]
  ssm_document_arns = [local.ssm_run_shell_script_arn]
  secret_arns       = concat(values(local.tunnel_token_secret_arns), values(var.backend_runtime_secret_arns))
  tags              = local.common_tags
}
