variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }

data "aws_vpc" "selected" {
  id = var.vpc_id
}

resource "aws_security_group" "redis" {
  name        = "digestor-w33-redis-${var.environment}"
  description = "Allow Redis access from within the VPC"
  vpc_id      = var.vpc_id

  ingress {
    description = "Redis from VPC"
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.selected.cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "digestor-w33-redis-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_elasticache_subnet_group" "redis" {
  name       = "digestor-w33-redis-${var.environment}"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name        = "digestor-w33-redis-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "digestor-w33-${var.environment}"
  engine               = "redis"
  engine_version       = "7.0"
  node_type            = var.environment == "prod" ? "cache.r6g.large" : "cache.t3.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.redis.name
  security_group_ids   = [aws_security_group.redis.id]

  tags = {
    Name        = "digestor-w33-${var.environment}"
    Environment = var.environment
  }
}

output "redis_endpoint" {
  value = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:6379"
}
