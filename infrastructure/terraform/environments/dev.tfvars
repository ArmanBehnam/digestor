# Digestor Unified - Dev Environment Variables
# Usage: terraform apply -var-file=environments/dev.tfvars

environment         = "dev"
aws_region          = "us-east-1"

# --- Networking (fill in from your VPC) ---
vpc_id              = "vpc-CHANGEME"
public_subnet_ids   = ["subnet-CHANGEME-pub-1", "subnet-CHANGEME-pub-2"]
private_subnet_ids  = ["subnet-CHANGEME-priv-1", "subnet-CHANGEME-priv-2"]

# --- Redis (ElastiCache or local) ---
redis_endpoint      = "CHANGEME.cache.amazonaws.com"

# --- TLS Certificate ---
acm_certificate_arn = "arn:aws:acm:us-east-1:800712212732:certificate/CHANGEME"
