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
    key    = "week33-digestor/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "digestor-week33"
      Environment = var.environment
      ManagedBy   = "terraform"
      Week        = "33"
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

# CodePipeline variables
variable "github_repo" {
  description = "GitHub repository (org/repo format)"
  type        = string
}

variable "github_branch" {
  description = "Branch to watch for deployments"
  type        = string
  default     = "aws-deployment"
}


# --- Networking (auto-created) ---

module "vpc" {
  source      = "./modules/vpc"
  environment = var.environment
  aws_region  = var.aws_region
}

# --- Modules ---

module "ecr" {
  source      = "./modules/ecr"
  environment = var.environment
}

module "secrets" {
  source      = "./modules/secrets"
  environment = var.environment
}

module "elasticache" {
  source             = "./modules/elasticache"
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
}

module "rds" {
  source      = "./modules/rds"
  environment = var.environment
  vpc_id      = module.vpc.vpc_id
  subnet_ids  = module.vpc.private_subnet_ids
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
  source            = "./modules/alb"
  environment       = var.environment
  vpc_id            = module.vpc.vpc_id
  public_subnet_ids = module.vpc.public_subnet_ids
}

module "ecs" {
  source             = "./modules/ecs"
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  alb_target_group   = module.alb.target_group_arn
  ecr_image          = "${module.ecr.repository_url}:latest"
  rds_endpoint       = module.rds.endpoint
  redis_endpoint     = module.elasticache.redis_endpoint
  cognito_pool_id    = module.cognito.user_pool_id
  cognito_client_id  = module.cognito.client_id
  s3_bucket          = module.s3.bucket_name
  rds_secret_arn     = module.rds.master_user_secret_arn
  secrets_arn        = module.secrets.secret_arn
}

module "monitoring" {
  source                  = "./modules/monitoring"
  environment             = var.environment
  ecs_cluster_name        = module.ecs.cluster_name
  web_service_name        = module.ecs.web_service_name
  worker_service_name     = module.ecs.worker_service_name
  alb_arn_suffix          = module.alb.arn_suffix
  target_group_arn_suffix = module.alb.target_group_arn_suffix
  alb_arn                 = module.alb.arn
}

module "codepipeline" {
  source                  = "./modules/codepipeline"
  environment             = var.environment
  ecr_repository_url      = module.ecr.repository_url
  ecs_cluster_name        = module.ecs.cluster_name
  web_service_name        = module.ecs.web_service_name
  worker_service_name     = module.ecs.worker_service_name
  github_repo   = var.github_repo
  github_branch = var.github_branch
}

# --- Outputs ---

output "alb_dns" {
  description = "ALB DNS name — access your app here"
  value       = module.alb.dns_name
}

output "vpc_id" {
  value = module.vpc.vpc_id
}

output "waf_web_acl_arn" {
  value = module.monitoring.waf_web_acl_arn
}

output "ecr_repository_url" {
  value = module.ecr.repository_url
}

output "rds_endpoint" {
  value = module.rds.endpoint
}

output "redis_endpoint" {
  value = module.elasticache.redis_endpoint
}

output "cognito_pool_id" {
  value = module.cognito.user_pool_id
}

output "s3_bucket" {
  value = module.s3.bucket_name
}

output "codepipeline_name" {
  value = module.codepipeline.pipeline_name
}
