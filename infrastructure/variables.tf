variable "aws_region" {
  description = "AWS region for resources deployment"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource naming"
  type        = string
  default     = "arte-chatbot"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "prod"
}

variable "frontend_bucket_name" {
  description = "S3 bucket name for frontend static files"
  type        = string
  default     = "arte-chatbot-frontend"
}

variable "ecr_repository_name" {
  description = "ECR repository name for backend image"
  type        = string
  default     = "arte-chatbot-backend"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones for the VPC"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24"]
}

variable "ecs_task_cpu" {
  description = "CPU units for ECS task"
  type        = number
  default     = 256
}

variable "ecs_task_memory" {
  description = "Memory (MB) for ECS task"
  type        = number
  default     = 512
}

variable "desired_count" {
  description = "Desired number of ECS tasks"
  type        = number
  default     = 1
}

variable "health_check_grace_period" {
  description = "Grace period for ECS health checks"
  type        = number
  default     = 30
}