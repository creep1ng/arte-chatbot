locals {
  project_dir = "/opt/arte-chatbot"

  backend_environment = merge(
    {
      APP_ENV              = "production"
      AWS_BUCKET_NAME      = var.aws_bucket_name
      AWS_REGION           = var.aws_region
      PUBLIC_API_URL       = var.public_api_url
      PUBLIC_FRONTEND_URL  = var.public_frontend_url
      PUBLIC_ADMIN_URL     = var.public_admin_url
      ALLOWED_CORS_ORIGINS = var.allowed_cors_origins
      PORT                 = "8000"
    },
    var.backend_runtime_environment_variables,
  )

  compose_yaml = templatefile("${path.module}/templates/docker-compose.yml.tftpl", {
    backend_image_uri   = var.backend_image_uri
    frontend_image_uri  = var.frontend_image_uri
    admin_image_uri     = var.admin_image_uri
    cloudflared_image   = var.cloudflared_image
    initial_image_tag   = "bootstrap"
    backend_environment = local.backend_environment
    public_api_url      = var.public_api_url
    public_frontend_url = var.public_frontend_url
    public_admin_url    = var.public_admin_url
  })

  deploy_script = templatefile("${path.module}/templates/deploy.sh.tftpl", {
    aws_region                         = var.aws_region
    project_dir                        = local.project_dir
    backend_image_uri                  = var.backend_image_uri
    frontend_image_uri                 = var.frontend_image_uri
    admin_image_uri                    = var.admin_image_uri
    backend_runtime_secret_arns        = var.backend_runtime_secret_arns
    cloudflare_tunnel_token_secret_arn = var.cloudflare_tunnel_token_secret_arn
  })

  runtime_secret_arns = compact(distinct(concat(
    values(var.backend_runtime_secret_arns),
    [var.cloudflare_tunnel_token_secret_arn],
  )))
}

data "aws_iam_policy_document" "assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = "${var.name}-compose-host"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "host" {
  statement {
    sid       = "EcrAuthorization"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "EcrPull"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = ["*"]
  }

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

  dynamic "statement" {
    for_each = length(local.runtime_secret_arns) > 0 ? [1] : []

    content {
      sid = "ReadRuntimeSecrets"
      actions = [
        "secretsmanager:GetSecretValue",
        "ssm:GetParameter",
        "ssm:GetParameters",
      ]
      resources = local.runtime_secret_arns
    }
  }

  dynamic "statement" {
    for_each = length(var.kms_key_arns) > 0 ? [1] : []

    content {
      sid       = "DecryptRuntimeSecrets"
      actions   = ["kms:Decrypt"]
      resources = var.kms_key_arns
    }
  }
}

resource "aws_iam_role_policy" "host" {
  name   = "${var.name}-compose-host"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.host.json
}

resource "aws_iam_instance_profile" "this" {
  name = "${var.name}-compose-host"
  role = aws_iam_role.this.name
  tags = var.tags
}

resource "aws_security_group" "this" {
  name        = "${var.name}-compose-host"
  description = "Outbound-only security group for the EC2 Compose host."
  vpc_id      = var.vpc_id

  egress {
    description = "Allow outbound HTTPS to AWS APIs and Cloudflare."
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Allow outbound HTTP for Ubuntu package repositories during bootstrap."
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Allow outbound Cloudflare Tunnel QUIC."
    from_port   = 7844
    to_port     = 7844
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Allow outbound Cloudflare Tunnel TCP fallback."
    from_port   = 7844
    to_port     = 7844
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.tags
}

resource "aws_instance" "this" {
  ami                         = coalesce(var.ami_id_override, var.ami_id)
  instance_type               = var.instance_type
  subnet_id                   = var.subnet_id
  vpc_security_group_ids      = [aws_security_group.this.id]
  iam_instance_profile        = aws_iam_instance_profile.this.name
  associate_public_ip_address = true

  user_data = <<-USERDATA
    #!/usr/bin/env bash
    set -Eeuo pipefail

    install -d -m 0755 ${local.project_dir}
    cat > ${local.project_dir}/docker-compose.yml <<'COMPOSE'
    ${indent(4, local.compose_yaml)}
    COMPOSE
    cat > ${local.project_dir}/deploy.sh <<'DEPLOY'
    ${indent(4, local.deploy_script)}
    DEPLOY
    chmod 0755 ${local.project_dir}/deploy.sh
    printf '%s\n' 'bootstrap' > ${local.project_dir}/current-image-tag

    apt-get update
    apt-get install -y awscli ca-certificates curl docker.io docker-compose-v2 unzip
    systemctl enable --now docker
    usermod -aG docker ubuntu || true
  USERDATA

  user_data_replace_on_change = true

  tags = merge(var.tags, {
    Name        = var.name
    Environment = var.environment
  })
}
