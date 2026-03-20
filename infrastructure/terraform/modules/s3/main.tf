variable "environment" { type = string }

locals {
  bucket_name = var.environment == "prod" ? "digestor-w33-uploads-prod" : "digestor-w33-uploads-dev"
}

resource "aws_s3_bucket" "main" {
  bucket = local.bucket_name
}

resource "aws_s3_bucket_versioning" "main" {
  bucket = aws_s3_bucket.main.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  bucket = aws_s3_bucket.main.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "main" {
  bucket                  = aws_s3_bucket.main.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle rules
resource "aws_s3_bucket_lifecycle_configuration" "main" {
  bucket = aws_s3_bucket.main.id

  # Delete temp files after 24 hours
  rule {
    id     = "cleanup-temp"
    status = "Enabled"
    filter {
      prefix = "temp/"
    }
    expiration {
      days = 1
    }
  }

  # Delete uploads after 7 days
  rule {
    id     = "cleanup-uploads"
    status = "Enabled"
    filter {
      prefix = "uploads/"
    }
    expiration {
      days = 7
    }
  }
}

# CORS for frontend uploads
resource "aws_s3_bucket_cors_configuration" "main" {
  bucket = aws_s3_bucket.main.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST"]
    allowed_origins = var.environment == "prod" ? [
      "https://digestor.yourdomain.com"
    ] : [
      "http://localhost:5173",
      "http://localhost:8080",
      "https://*.us-east-1.elb.amazonaws.com"
    ]
    max_age_seconds = 3600
  }
}

output "bucket_name" {
  value = aws_s3_bucket.main.id
}

output "bucket_arn" {
  value = aws_s3_bucket.main.arn
}
