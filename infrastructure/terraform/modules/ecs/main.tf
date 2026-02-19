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

locals {
  is_prod    = var.environment == "prod"
  web_cpu    = local.is_prod ? 1024 : 512   # 1 vCPU prod, 0.5 vCPU dev
  web_memory = local.is_prod ? 2048 : 1024  # 2GB prod, 1GB dev
  wrk_cpu    = local.is_prod ? 1024 : 512
  wrk_memory = local.is_prod ? 4096 : 2048  # 4GB prod, 2GB dev
}

resource "aws_ecs_cluster" "main" {
  name = "digestor-${var.environment}"

  setting {
    name  = "containerInsights"
    value = local.is_prod ? "enabled" : "disabled"
  }
}

resource "aws_security_group" "ecs" {
  name_prefix = "digestor-ecs-${var.environment}-"
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
  name = "digestor-ecs-task-${var.environment}"

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
  name = "digestor-ecs-execution-${var.environment}"

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

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "main" {
  name              = "/ecs/digestor-${var.environment}"
  retention_in_days = local.is_prod ? 30 : 7
}

# --- Web Service Task Definition ---
resource "aws_ecs_task_definition" "web" {
  family                   = "digestor-web-${var.environment}"
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
      { name = "DATABASE_URL", value = "postgresql+asyncpg://digestor:CHANGE_ME@${var.rds_endpoint}:5432/digestor_${var.environment}" },
      { name = "REDIS_URL", value = "redis://${var.redis_endpoint}:6379" },
      { name = "S3_BUCKET", value = var.s3_bucket },
      { name = "COGNITO_USER_POOL_ID", value = var.cognito_pool_id },
      { name = "COGNITO_APP_CLIENT_ID", value = var.cognito_client_id },
      { name = "USE_SECRETS_MANAGER", value = "true" },
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
  family                   = "digestor-worker-${var.environment}"
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
      { name = "DATABASE_URL", value = "postgresql+asyncpg://digestor:CHANGE_ME@${var.rds_endpoint}:5432/digestor_${var.environment}" },
      { name = "REDIS_URL", value = "redis://${var.redis_endpoint}:6379" },
      { name = "S3_BUCKET", value = var.s3_bucket },
      { name = "USE_SECRETS_MANAGER", value = "true" },
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
  name            = "digestor-web-${var.environment}"
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
  name            = "digestor-worker-${var.environment}"
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
