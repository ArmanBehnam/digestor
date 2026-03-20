variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "alb_target_group" { type = string }
variable "ecr_image" { type = string }
variable "rds_endpoint" { type = string }
variable "redis_endpoint" { type = string }
variable "cognito_pool_id" { type = string }
variable "cognito_client_id" { type = string }
variable "s3_bucket" { type = string }
variable "rds_secret_arn" {
  type        = string
  description = "ARN of the RDS master user secret in Secrets Manager"
}
variable "secrets_arn" {
  type        = string
  description = "ARN of the Secrets Manager secret containing API keys"
}

locals {
  is_prod    = var.environment == "prod"
  web_cpu    = local.is_prod ? 1024 : 512   # 1 vCPU prod, 0.5 vCPU dev
  web_memory = local.is_prod ? 2048 : 1024  # 2GB prod, 1GB dev
  wrk_cpu    = local.is_prod ? 1024 : 2048
  wrk_memory = local.is_prod ? 4096 : 8192  # 8GB dev, 4GB prod
}

resource "aws_ecs_cluster" "main" {
  name = "digestor-w33-${var.environment}"

  setting {
    name  = "containerInsights"
    value = local.is_prod ? "enabled" : "disabled"
  }
}

resource "aws_security_group" "ecs" {
  name_prefix = "digestor-w33-ecs-${var.environment}-"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# IAM Role for ECS Tasks
resource "aws_iam_role" "ecs_task" {
  name = "digestor-w33-ecs-task-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "ecs_task" {
  name = "task-permissions"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:DeleteObject"]
        Resource = ["arn:aws:s3:::${var.s3_bucket}", "arn:aws:s3:::${var.s3_bucket}/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["textract:*"]
        Resource = ["*"]
      },
      {
        Effect   = "Allow"
        Action   = ["ses:SendEmail", "ses:SendRawEmail"]
        Resource = ["*"]
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = ["*"]
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = ["*"]
      },
    ]
  })
}

resource "aws_iam_role" "ecs_execution" {
  name = "digestor-w33-ecs-execution-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "secrets-manager-access"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [var.secrets_arn, var.rds_secret_arn]
    }]
  })
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "main" {
  name              = "/ecs/digestor-w33-${var.environment}"
  retention_in_days = local.is_prod ? 30 : 7
}

# --- Web Service Task Definition ---
resource "aws_ecs_task_definition" "web" {
  family                   = "digestor-w33-web-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = local.web_cpu
  memory                   = local.web_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = "web"
    image = var.ecr_image
    portMappings = [{ containerPort = 8080, protocol = "tcp" }]
    environment = [
      { name = "PROCESS_TYPE", value = "web" },
      { name = "ENVIRONMENT", value = var.environment },
      { name = "RDS_ENDPOINT", value = var.rds_endpoint },
      { name = "RDS_DB_NAME", value = "digestor_w33_${var.environment}" },
      { name = "RDS_SECRET_ARN", value = var.rds_secret_arn },
      { name = "REDIS_URL", value = "redis://${var.redis_endpoint}:6379" },
      { name = "S3_BUCKET", value = var.s3_bucket },
      { name = "COGNITO_USER_POOL_ID", value = var.cognito_pool_id },
      { name = "COGNITO_APP_CLIENT_ID", value = var.cognito_client_id },
      { name = "USE_SECRETS_MANAGER", value = "true" },
      { name = "AGENTIC_ENABLED", value = "true" },
    ]
    secrets = [
      { name = "OPENAI_API_KEY", valueFrom = "${var.secrets_arn}:OPENAI_API_KEY::" },
      { name = "GEMINI_API_KEY", valueFrom = "${var.secrets_arn}:GEMINI_API_KEY::" },
      { name = "ANTHROPIC_API_KEY", valueFrom = "${var.secrets_arn}:ANTHROPIC_API_KEY::" },
      { name = "AZURE_API_KEY", valueFrom = "${var.secrets_arn}:AZURE_API_KEY::" },
      { name = "AZURE_ENDPOINT", valueFrom = "${var.secrets_arn}:AZURE_ENDPOINT::" },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.main.name
        "awslogs-region"        = "us-east-1"
        "awslogs-stream-prefix" = "web"
      }
    }
  }])
}

# --- Worker Service Task Definition ---
resource "aws_ecs_task_definition" "worker" {
  family                   = "digestor-w33-worker-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = local.wrk_cpu
  memory                   = local.wrk_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = "worker"
    image = var.ecr_image
    environment = [
      { name = "PROCESS_TYPE", value = "worker" },
      { name = "ENVIRONMENT", value = var.environment },
      { name = "RDS_ENDPOINT", value = var.rds_endpoint },
      { name = "RDS_DB_NAME", value = "digestor_w33_${var.environment}" },
      { name = "RDS_SECRET_ARN", value = var.rds_secret_arn },
      { name = "REDIS_URL", value = "redis://${var.redis_endpoint}:6379" },
      { name = "S3_BUCKET", value = var.s3_bucket },
      { name = "USE_SECRETS_MANAGER", value = "true" },
      { name = "AGENTIC_ENABLED", value = "true" },
    ]
    secrets = [
      { name = "OPENAI_API_KEY", valueFrom = "${var.secrets_arn}:OPENAI_API_KEY::" },
      { name = "GEMINI_API_KEY", valueFrom = "${var.secrets_arn}:GEMINI_API_KEY::" },
      { name = "ANTHROPIC_API_KEY", valueFrom = "${var.secrets_arn}:ANTHROPIC_API_KEY::" },
      { name = "AZURE_API_KEY", valueFrom = "${var.secrets_arn}:AZURE_API_KEY::" },
      { name = "AZURE_ENDPOINT", valueFrom = "${var.secrets_arn}:AZURE_ENDPOINT::" },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.main.name
        "awslogs-region"        = "us-east-1"
        "awslogs-stream-prefix" = "worker"
      }
    }
  }])
}

# --- Web Service ---
resource "aws_ecs_service" "web" {
  name            = "digestor-w33-web-${var.environment}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = local.is_prod ? 2 : 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.alb_target_group
    container_name   = "web"
    container_port   = 8080
  }
}

# --- Worker Service ---
resource "aws_ecs_service" "worker" {
  name            = "digestor-w33-worker-${var.environment}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = false
  }
}

# --- Outputs ---

output "cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "web_service_name" {
  value = aws_ecs_service.web.name
}

output "worker_service_name" {
  value = aws_ecs_service.worker.name
}
