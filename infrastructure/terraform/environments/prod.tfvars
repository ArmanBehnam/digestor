# Digestor Week33 - Prod Environment Variables
# Usage: terraform apply -var-file=environments/prod.tfvars

environment = "prod"
aws_region  = "us-east-1"

# --- CodePipeline ---
github_repo   = "ArmanBehnam/digestor"
github_branch = "main"
