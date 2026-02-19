# CI/CD Setup Guide

## Overview

This project uses GitHub Actions for automated build, test, and deployment:

- **test.yml** - Runs on every push/PR to `main`: backend lint, frontend build, Docker build
- **deploy.yml** - Runs on push to `main` (or manual trigger): builds Docker image, pushes to ECR, deploys to ECS

## Prerequisites

1. A GitHub repository for this project
2. AWS IAM user with programmatic access (for GitHub Actions)
3. The following AWS resources already provisioned (see `infrastructure/terraform/`)

## Step 1: Create GitHub Repository

```bash
cd C:\Arman\Clark\Week30\digestor-unified

# Add remote (replace with your repo URL)
git remote add origin https://github.com/YOUR_ORG/digestor-unified.git

# Push
git push -u origin main
```

## Step 2: Create IAM User for CI/CD

Create an IAM user `digestor-cicd` with these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ecs:DescribeServices",
        "ecs:UpdateService",
        "ecs:DescribeTaskDefinition",
        "ecs:RegisterTaskDefinition",
        "ecs:ListTasks",
        "ecs:DescribeTasks"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": [
        "arn:aws:iam::800712212732:role/digestor-ecs-task-dev",
        "arn:aws:iam::800712212732:role/digestor-ecs-execution-dev"
      ]
    }
  ]
}
```

## Step 3: Configure GitHub Secrets

Go to **Settings > Secrets and variables > Actions** and add:

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `AWS_ACCESS_KEY_ID` | (from Step 2) | IAM user access key |
| `AWS_SECRET_ACCESS_KEY` | (from Step 2) | IAM user secret key |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/dbname` | RDS connection string |
| `REDIS_URL` | `redis://your-redis-host:6379` | ElastiCache Redis URL |
| `OPENAI_API_KEY` | `sk-proj-...` | OpenAI API key for LLM processing |
| `AZURE_API_KEY` | (your Azure key) | Azure Cognitive Services key |
| `AZURE_ENDPOINT` | `https://your-endpoint.cognitiveservices.azure.com/` | Azure OCR endpoint |

## Step 4: Test the Pipeline

### Manual trigger (deploy)
Go to **Actions > Build & Deploy to ECS > Run workflow** and select the `main` branch.

### Automatic trigger
Push a commit to `main`:
```bash
git add .
git commit -m "Add CI/CD pipeline"
git push origin main
```

## Workflow Details

### Deploy Pipeline (deploy.yml)

```
Push to main
    ├── Checkout code
    ├── Configure AWS credentials
    ├── Login to ECR
    ├── Build Docker image (multi-stage: frontend + backend)
    ├── Push to ECR (tagged with commit SHA + latest)
    ├── Inject secrets into task definition templates
    ├── Register web task definition → Deploy web service
    ├── Register worker task definition → Deploy worker service
    └── Health check (curl ALB /api/health)
```

### Test Pipeline (test.yml)

```
Push/PR to main
    ├── Backend lint (ruff)
    ├── Frontend build (npm ci + npm run build)
    └── Docker build (verify Dockerfile compiles)
```

## File Structure

```
.github/
  workflows/
    deploy.yml          # Build + deploy on push to main
    test.yml            # Lint + build on push/PR
infrastructure/
  ecs/
    taskdef-web.json    # Web task def template (secrets as placeholders)
    taskdef-worker.json # Worker task def template (secrets as placeholders)
  docker/
    Dockerfile          # Multi-stage build
```

## Troubleshooting

### Deploy fails at "Wait for service stability"
- Check ECS service events: `aws ecs describe-services --cluster digestor-dev --services digestor-web-dev`
- Check CloudWatch logs: `/ecs/digestor-dev`
- Common cause: health check failing (container not starting)

### ECR push fails
- Verify IAM user has ECR permissions
- Check if ECR repo exists: `aws ecr describe-repositories --repository-names digetor`

### Task definition registration fails
- Verify IAM user has `iam:PassRole` for both task and execution roles
- Check JSON syntax in task def templates
