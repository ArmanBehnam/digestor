#!/usr/bin/env bash
# =============================================================================
# Digestor Unified - Deployment Script
# Usage: ./scripts/deploy.sh <environment>
#   e.g. ./scripts/deploy.sh dev
#        ./scripts/deploy.sh prod
# =============================================================================
set -euo pipefail

ENV="${1:-dev}"
AWS_REGION="${AWS_REGION:-us-east-1}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
TF_DIR="$ROOT_DIR/infrastructure/terraform"
DOCKER_DIR="$ROOT_DIR/infrastructure/docker"

echo "============================================"
echo " Digestor Unified - Deploy to: $ENV"
echo "============================================"

# --- 1. Get ECR repository URL from Terraform ---
echo ""
echo "[1/5] Reading Terraform outputs..."
cd "$TF_DIR"

ECR_REPO=$(terraform output -raw ecr_repository_url 2>/dev/null || echo "")
if [ -z "$ECR_REPO" ]; then
    echo "ERROR: Could not read ecr_repository_url from Terraform."
    echo "       Run 'terraform apply' first to provision ECR."
    exit 1
fi
echo "  ECR: $ECR_REPO"

# --- 2. Build Docker image ---
echo ""
echo "[2/5] Building Docker image..."
cd "$ROOT_DIR"

COMMIT_HASH=$(git rev-parse --short HEAD 2>/dev/null || echo "manual")
IMAGE_TAG="${ENV}-${COMMIT_HASH}"

docker build \
    -t "$ECR_REPO:$IMAGE_TAG" \
    -t "$ECR_REPO:latest" \
    -f infrastructure/docker/Dockerfile \
    .

echo "  Built: $ECR_REPO:$IMAGE_TAG"

# --- 3. Push to ECR ---
echo ""
echo "[3/5] Pushing to ECR..."
aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "$ECR_REPO"

docker push "$ECR_REPO:$IMAGE_TAG"
docker push "$ECR_REPO:latest"
echo "  Pushed: $IMAGE_TAG + latest"

# --- 4. Update ECS service (force new deployment) ---
echo ""
echo "[4/5] Updating ECS services..."
CLUSTER="digestor-${ENV}"

aws ecs update-service \
    --cluster "$CLUSTER" \
    --service "digestor-web-${ENV}" \
    --force-new-deployment \
    --region "$AWS_REGION" \
    --no-cli-pager > /dev/null

aws ecs update-service \
    --cluster "$CLUSTER" \
    --service "digestor-worker-${ENV}" \
    --force-new-deployment \
    --region "$AWS_REGION" \
    --no-cli-pager > /dev/null

echo "  Web + Worker services updated"

# --- 5. Wait for deployment to stabilize ---
echo ""
echo "[5/5] Waiting for web service to stabilize..."
aws ecs wait services-stable \
    --cluster "$CLUSTER" \
    --services "digestor-web-${ENV}" \
    --region "$AWS_REGION"

# --- Health check ---
echo ""
ALB_DNS=$(cd "$TF_DIR" && terraform output -raw alb_dns 2>/dev/null || echo "")
if [ -n "$ALB_DNS" ]; then
    echo "Running health check..."
    HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' "https://$ALB_DNS/api/health" 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "  ✓ Health check passed (HTTP $HTTP_CODE)"
    else
        echo "  ⚠ Health check returned HTTP $HTTP_CODE"
        echo "  URL: https://$ALB_DNS/api/health"
    fi
fi

echo ""
echo "============================================"
echo " Deploy complete: $ENV ($IMAGE_TAG)"
echo "============================================"
