terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.30"
    }
  }

  backend "s3" {
    bucket = "digestor-terraform-state"
    key    = "digestor-unified/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "digestor-unified"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# --- Variables ---

variable "aws_region" {
  default = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev or prod)"
  type        = string
}

variable "vpc_id" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "private_subnet_ids" { type = list(string) }
variable "redis_endpoint" { type = string }

variable "acm_certificate_arn" {
  description = "ARN of the ACM TLS certificate for the ALB HTTPS listener"
  type        = string
}

# --- Modules ---

module "ecr" {
  source      = "./modules/ecr"
  environment = var.environment
}

module "rds" {
  source      = "./modules/rds"
  environment = var.environment
  vpc_id      = var.vpc_id
  subnet_ids  = var.private_subnet_ids
}

module "cognito" {
  source      = "./modules/cognito"
  environment = var.environment
}

module "s3" {
  source      = "./modules/s3"
  environment = var.environment
}

module "alb" {
  source              = "./modules/alb"
  environment         = var.environment
  vpc_id              = var.vpc_id
  public_subnet_ids   = var.public_subnet_ids
  acm_certificate_arn = var.acm_certificate_arn
}

module "ecs" {
  source             = "./modules/ecs"
  environment        = var.environment
  vpc_id             = var.vpc_id
  private_subnet_ids = var.private_subnet_ids
  alb_target_group   = module.alb.target_group_arn
  ecr_image          = "${module.ecr.repository_url}:latest"
  rds_endpoint       = module.rds.endpoint
  redis_endpoint     = var.redis_endpoint
  cognito_pool_id    = module.cognito.user_pool_id
  cognito_client_id  = module.cognito.client_id
  s3_bucket          = module.s3.bucket_name
}

# --- Outputs ---

output "alb_dns" {
  value = module.alb.dns_name
}

output "ecr_repository_url" {
  value = module.ecr.repository_url
}

output "rds_endpoint" {
  value = module.rds.endpoint
}

output "cognito_pool_id" {
  value = module.cognito.user_pool_id
}

output "s3_bucket" {
  value = module.s3.bucket_name
}
