terraform {
  required_version = ">= 1.5.0"

  backend "s3" {
    bucket       = "arte-chatbot-terraform-state"
    key          = "fargate-cloudflare-cd-iac/prod/terraform.tfstate"
    region       = "us-east-2"
    encrypt      = true
    use_lockfile = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.19"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

provider "cloudflare" {}
