variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }

locals {
  is_prod       = var.environment == "prod"
  instance_class = local.is_prod ? "db.t3.small" : "db.t3.micro"
  db_name       = "digestor_${var.environment}"
}

resource "aws_db_subnet_group" "main" {
  name       = "digestor-${var.environment}"
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "rds" {
  name_prefix = "digestor-rds-${var.environment}-"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    description = "PostgreSQL from VPC"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "main" {
  identifier     = "digestor-${var.environment}"
  engine         = "postgres"
  engine_version = "15.4"
  instance_class = local.instance_class

  db_name                     = local.db_name
  username                    = "digestor"
  manage_master_user_password = true  # AWS manages password via Secrets Manager

  allocated_storage     = local.is_prod ? 50 : 20
  max_allocated_storage = local.is_prod ? 200 : 50
  storage_encrypted     = true
  storage_type          = "gp3"

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  multi_az               = local.is_prod
  publicly_accessible    = false

  backup_retention_period = local.is_prod ? 7 : 1
  skip_final_snapshot     = !local.is_prod
  deletion_protection     = local.is_prod

  performance_insights_enabled = local.is_prod
}

# RDS Proxy for connection pooling
resource "aws_db_proxy" "main" {
  name                   = "digestor-${var.environment}"
  debug_logging          = !local.is_prod
  engine_family          = "POSTGRESQL"
  idle_client_timeout    = 1800
  require_tls            = true
  role_arn               = aws_iam_role.rds_proxy.arn
  vpc_security_group_ids = [aws_security_group.rds.id]
  vpc_subnet_ids         = var.subnet_ids

  auth {
    auth_scheme = "SECRETS"
    iam_auth    = "DISABLED"
    secret_arn  = aws_db_instance.main.master_user_secret[0].secret_arn
  }
}

resource "aws_db_proxy_default_target_group" "main" {
  db_proxy_name = aws_db_proxy.main.name

  connection_pool_config {
    max_connections_percent      = 90
    max_idle_connections_percent = 50
    connection_borrow_timeout    = 120
  }
}

resource "aws_db_proxy_target" "main" {
  db_proxy_name          = aws_db_proxy.main.name
  target_group_name      = aws_db_proxy_default_target_group.main.name
  db_instance_identifier = aws_db_instance.main.identifier
}

resource "aws_iam_role" "rds_proxy" {
  name = "digestor-rds-proxy-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "rds.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "rds_proxy" {
  name = "secrets-access"
  role = aws_iam_role.rds_proxy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [aws_db_instance.main.master_user_secret[0].secret_arn]
    }]
  })
}

output "endpoint" {
  value = aws_db_proxy.main.endpoint
}

output "db_name" {
  value = local.db_name
}

output "master_user_secret_arn" {
  value = aws_db_instance.main.master_user_secret[0].secret_arn
}
