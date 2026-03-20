variable "environment" { type = string }
variable "ecr_repository_url" { type = string }
variable "ecs_cluster_name" { type = string }
variable "web_service_name" { type = string }
variable "worker_service_name" { type = string }
variable "github_repo" { type = string }
variable "github_branch" { type = string }

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ──────────────────────────────────────────────
# CodeStar Connection to GitHub
# NOTE: After `terraform apply`, this will be in PENDING state.
# You must go to AWS Console → Developer Tools → Connections
# and click "Update pending connection" to complete the GitHub OAuth.
# ──────────────────────────────────────────────

resource "aws_codestarconnections_connection" "github" {
  name          = "digestor-w33-github-${var.environment}"
  provider_type = "GitHub"

  tags = {
    Name        = "digestor-w33-github-${var.environment}"
    Environment = var.environment
  }
}

# ──────────────────────────────────────────────
# S3 Artifact Bucket
# ──────────────────────────────────────────────

resource "aws_s3_bucket" "artifacts" {
  bucket        = "digestor-w33-pipeline-artifacts-${var.environment}"
  force_destroy = true

  tags = {
    Name        = "digestor-w33-pipeline-artifacts-${var.environment}"
    Environment = var.environment
  }
}

# ──────────────────────────────────────────────
# CodeBuild IAM Role
# ──────────────────────────────────────────────

resource "aws_iam_role" "codebuild" {
  name = "digestor-w33-codebuild-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "codebuild.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "codebuild" {
  name = "digestor-w33-codebuild-${var.environment}"
  role = aws_iam_role.codebuild.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:CompleteLayerUpload",
          "ecr:GetAuthorizationToken",
          "ecr:InitiateLayerUpload",
          "ecr:PutImage",
          "ecr:UploadLayerPart",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:GetBucketLocation"
        ]
        Resource = [
          aws_s3_bucket.artifacts.arn,
          "${aws_s3_bucket.artifacts.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:*"
      }
    ]
  })
}

# ──────────────────────────────────────────────
# CodeBuild Project
# ──────────────────────────────────────────────

resource "aws_codebuild_project" "build" {
  name         = "digestor-w33-build-${var.environment}"
  service_role = aws_iam_role.codebuild.arn

  artifacts {
    type = "CODEPIPELINE"
  }

  environment {
    compute_type                = "BUILD_GENERAL1_MEDIUM"
    image                       = "aws/codebuild/amazonlinux2-x86_64-standard:5.0"
    type                        = "LINUX_CONTAINER"
    privileged_mode             = true
    image_pull_credentials_type = "CODEBUILD"

    environment_variable {
      name  = "ECR_REPO"
      value = var.ecr_repository_url
    }

    environment_variable {
      name  = "AWS_DEFAULT_REGION"
      value = data.aws_region.current.name
    }

    environment_variable {
      name  = "AWS_ACCOUNT_ID"
      value = data.aws_caller_identity.current.account_id
    }
  }

  source {
    type = "CODEPIPELINE"
  }

  tags = {
    Name        = "digestor-w33-build-${var.environment}"
    Environment = var.environment
  }
}

# ──────────────────────────────────────────────
# CodePipeline IAM Role
# ──────────────────────────────────────────────

resource "aws_iam_role" "codepipeline" {
  name = "digestor-w33-pipeline-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "codepipeline.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "codepipeline" {
  name = "digestor-w33-pipeline-${var.environment}"
  role = aws_iam_role.codepipeline.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:GetBucketVersioning",
          "s3:GetBucketLocation"
        ]
        Resource = [
          aws_s3_bucket.artifacts.arn,
          "${aws_s3_bucket.artifacts.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "codebuild:BatchGetBuilds",
          "codebuild:StartBuild"
        ]
        Resource = aws_codebuild_project.build.arn
      },
      {
        Effect = "Allow"
        Action = [
          "ecs:DescribeServices",
          "ecs:DescribeTaskDefinition",
          "ecs:DescribeTasks",
          "ecs:ListTasks",
          "ecs:RegisterTaskDefinition",
          "ecs:UpdateService",
          "ecs:TagResource"
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "codestar-connections:UseConnection"
        ]
        Resource = aws_codestarconnections_connection.github.arn
      }
    ]
  })
}

# ──────────────────────────────────────────────
# CodePipeline
# ──────────────────────────────────────────────

resource "aws_codepipeline" "pipeline" {
  name     = "digestor-w33-${var.environment}"
  role_arn = aws_iam_role.codepipeline.arn

  artifact_store {
    location = aws_s3_bucket.artifacts.bucket
    type     = "S3"
  }

  # Stage 1 – Source
  stage {
    name = "Source"

    action {
      name             = "Source"
      category         = "Source"
      owner            = "AWS"
      provider         = "CodeStarSourceConnection"
      version          = "1"
      output_artifacts = ["source_output"]

      configuration = {
        ConnectionArn    = aws_codestarconnections_connection.github.arn
        FullRepositoryId = var.github_repo
        BranchName       = var.github_branch
      }
    }
  }

  # Stage 2 – Build
  stage {
    name = "Build"

    action {
      name             = "Build"
      category         = "Build"
      owner            = "AWS"
      provider         = "CodeBuild"
      version          = "1"
      input_artifacts  = ["source_output"]
      output_artifacts = ["build_output"]

      configuration = {
        ProjectName = aws_codebuild_project.build.name
      }
    }
  }

  # Stage 3 – Deploy (web + worker in parallel)
  stage {
    name = "Deploy"

    action {
      name            = "Deploy-Web"
      category        = "Deploy"
      owner           = "AWS"
      provider        = "ECS"
      version         = "1"
      input_artifacts = ["build_output"]
      run_order       = 1

      configuration = {
        ClusterName = var.ecs_cluster_name
        ServiceName = var.web_service_name
        FileName    = "imagedefinitions-web.json"
      }
    }

    action {
      name            = "Deploy-Worker"
      category        = "Deploy"
      owner           = "AWS"
      provider        = "ECS"
      version         = "1"
      input_artifacts = ["build_output"]
      run_order       = 1

      configuration = {
        ClusterName = var.ecs_cluster_name
        ServiceName = var.worker_service_name
        FileName    = "imagedefinitions-worker.json"
      }
    }
  }

  tags = {
    Name        = "digestor-w33-${var.environment}"
    Environment = var.environment
  }
}

output "pipeline_name" {
  value = aws_codepipeline.pipeline.name
}
