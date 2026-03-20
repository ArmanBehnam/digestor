# Digestor Week33 - Dev Environment Variables
# Usage: terraform apply -var-file=environments/dev.tfvars
#
# VPC, subnets, Redis, and CodeStar connection are all auto-created by Terraform.

environment = "dev"
aws_region  = "us-east-1"

# --- CodePipeline ---
github_repo   = "ArmanBehnam/digestor"
github_branch = "aws-deployment"
