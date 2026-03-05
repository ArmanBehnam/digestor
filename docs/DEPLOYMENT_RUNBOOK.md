# Digestor Unified — Deployment Runbook

## Prerequisites

Before first deployment, ensure you have:

- [ ] AWS CLI configured (`aws sts get-caller-identity` works)
- [ ] Docker installed and running
- [ ] Terraform >= 1.5 installed
- [ ] ACM certificate provisioned and validated for your domain
- [ ] VPC with public + private subnets (at least 2 AZs)
- [ ] ElastiCache Redis cluster provisioned (or use `redis_endpoint` variable)
- [ ] S3 bucket for Terraform state: `digestor-terraform-state`

---

## 1. First-Time Infrastructure Setup

### 1a. Fill in environment variables

```bash
cp infrastructure/terraform/environments/dev.tfvars.example \
   infrastructure/terraform/environments/dev.tfvars

# Edit dev.tfvars — fill in all CHANGEME values:
#   vpc_id, subnet IDs, redis_endpoint, acm_certificate_arn
```

### 1b. Initialize and apply Terraform

```bash
cd infrastructure/terraform

terraform init
terraform plan -var-file=environments/dev.tfvars
terraform apply -var-file=environments/dev.tfvars
```

This creates: ECR repository, RDS PostgreSQL, Cognito user pool, S3 bucket, ALB, ECS cluster + services.

### 1c. Note the outputs

```bash
terraform output
# alb_dns            = "digestor-dev-XXXXX.us-east-1.elb.amazonaws.com"
# ecr_repository_url = "800712212732.dkr.ecr.us-east-1.amazonaws.com/digetor"
# rds_endpoint       = "digestor-dev.XXXXX.us-east-1.rds.amazonaws.com"
# cognito_pool_id    = "us-east-1_XXXXX"
# s3_bucket          = "digestor-unified-uploads-dev"
```

---

## 2. Build & Deploy

### Option A: Automated deploy script

```bash
./scripts/deploy.sh dev
```

This builds the Docker image, pushes to ECR, and triggers an ECS rolling deployment.

### Option B: Manual steps

```bash
# 1. Build
docker build -t digestor-unified -f infrastructure/docker/Dockerfile .

# 2. Tag
ECR_REPO=$(terraform -chdir=infrastructure/terraform output -raw ecr_repository_url)
docker tag digestor-unified "$ECR_REPO:latest"

# 3. Push
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin "$ECR_REPO"
docker push "$ECR_REPO:latest"

# 4. Force new ECS deployment
aws ecs update-service --cluster digestor-dev --service digestor-web-dev --force-new-deployment
aws ecs update-service --cluster digestor-dev --service digestor-worker-dev --force-new-deployment
```

### Option C: CodeBuild (CI/CD)

Push to the connected branch. CodeBuild runs `buildspec.yml` which builds, tags, and pushes to ECR. The `imagedefinitions.json` artifact can be used by a CodePipeline deploy stage to update ECS automatically.

---

## 3. Database Migrations

Migrations run automatically on container startup (`entrypoint.py` runs `alembic upgrade head` before starting uvicorn). For manual migration:

```bash
# Inside the container or locally with DATABASE_URL set
cd backend
python -m alembic upgrade head

# Create a new migration after model changes
python -m alembic revision --autogenerate -m "description of changes"
```

---

## 4. Data Migration (Supabase → RDS + Cognito)

For migrating existing users and data from the Supabase-based system:

```bash
# Set environment variables
export DATABASE_URL="postgresql+asyncpg://digestor:PASSWORD@RDS_ENDPOINT:5432/digestor_dev"
export COGNITO_USER_POOL_ID="us-east-1_XXXXX"
export COGNITO_APP_CLIENT_ID="XXXXX"

# Run migration script
cd backend
python scripts/migrate_supabase_to_rds.py
```

Migrated Cognito users will have `FORCE_CHANGE_PASSWORD` status. On first login, the frontend presents the "New Password Required" challenge flow.

---

## 5. Post-Deployment Smoke Test

```bash
# Automated
./scripts/smoke-test.sh https://YOUR-ALB-DNS

# Manual quick checks
curl https://YOUR-ALB-DNS/api/health
# Expected: {"status":"healthy","version":"2.0.0",...}
```

---

## 6. Local Development

```bash
# Start local stack (postgres, redis, migrate, web, worker)
cd infrastructure/docker
docker compose up --build

# Access:
#   Web app:  http://localhost:8080
#   API:      http://localhost:8080/api/health
#   Postgres: localhost:5432  (digestor / digestor_dev_password)
#   Redis:    localhost:6379
```

---

## 7. Rollback

```bash
# Find previous image tag
aws ecr list-images --repository-name digetor --query 'imageIds[*].imageTag'

# Update ECS task definition to use the previous tag
# Then force new deployment
aws ecs update-service --cluster digestor-dev --service digestor-web-dev --force-new-deployment
```

---

## Architecture Reference

```
Client → ALB (HTTPS:443) → ECS Fargate (web:8080)
                                  ├── FastAPI REST API (/api/*)
                                  ├── WebSocket (/ws/*)
                                  ├── React SPA (/*) — served from /static
                                  └── Alembic migrations (on startup)

         ECS Fargate (worker) → Redis Queue → tasks.process_pdfs
                                  ├── S3 (document storage)
                                  ├── Textract (OCR)
                                  └── LLM (GPT-4o / Claude)

         RDS PostgreSQL ← async SQLAlchemy (asyncpg) + RDS Proxy
         Cognito ← JWT auth (verify in FastAPI middleware)
         SES ← Email notifications
```

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `PROCESS_TYPE` | Yes | `web` or `worker` |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `S3_BUCKET` | Yes | S3 bucket name for uploads |
| `COGNITO_USER_POOL_ID` | Yes | Cognito user pool ID |
| `COGNITO_APP_CLIENT_ID` | Yes | Cognito app client ID |
| `AWS_REGION` | Yes | AWS region (default: us-east-1) |
| `OPENAI_API_KEY` | Yes* | For PDF.js LLM processing |
| `ANTHROPIC_API_KEY` | No | Alternative LLM provider |
| `DEEPSEEK_API_KEY` | No | Alternative LLM provider |
| `SES_FROM_EMAIL` | No | SES sender email |
| `ADMIN_EMAIL` | No | Admin notification email |
| `ALLOWED_ORIGINS` | No | CORS origins (comma-separated) |
| `ENVIRONMENT` | No | `development` / `production` |
| `SQL_ECHO` | No | `true` to log SQL queries |
| `USE_SECRETS_MANAGER` | No | `true` to load from Secrets Manager |

---

## 8. Monitoring & Alerting

### CloudWatch Dashboard

View live metrics at: **CloudWatch > Dashboards > digestor-dev**

The dashboard includes:
- ALB request count (2xx, 4xx, 5xx breakdown)
- ALB response time (average + p99)
- ECS Web service CPU & memory utilization
- ECS Worker service CPU & memory utilization
- Healthy/unhealthy target count
- RDS CPU & active connections
- Alarm status panel

### CloudWatch Alarms

| Alarm | Metric | Threshold | Evaluation |
|-------|--------|-----------|------------|
| `digestor-dev-5xx-errors` | ALB 5xx count | >10 in 5 min | 1 period |
| `digestor-dev-unhealthy-targets` | Unhealthy host count | >=1 | 3 x 1 min |
| `digestor-dev-web-cpu-high` | Web CPU utilization | >80% | 2 x 5 min |
| `digestor-dev-web-memory-high` | Web memory utilization | >85% | 2 x 5 min |
| `digestor-dev-worker-cpu-high` | Worker CPU utilization | >80% | 2 x 5 min |
| `digestor-dev-response-time-high` | Avg response time | >5 seconds | 2 x 5 min |

Check alarm status:
```bash
aws cloudwatch describe-alarms --alarm-name-prefix digestor-dev \
  --query "MetricAlarms[].[AlarmName,StateValue]" --output table
```

### Logs

All application logs are in CloudWatch Logs group `/ecs/digestor-dev`:
```bash
# View recent web logs
aws logs tail /ecs/digestor-dev --filter-pattern "web" --since 1h

# View recent worker logs
aws logs tail /ecs/digestor-dev --filter-pattern "worker" --since 1h

# Search for errors
aws logs filter-log-events --log-group-name /ecs/digestor-dev \
  --filter-pattern "ERROR" --start-time $(date -d '1 hour ago' +%s000)
```

---

## 9. Auto-Scaling

ECS services auto-scale based on CPU utilization:

| Service | Min Tasks | Max Tasks | CPU Target | Scale Out | Scale In |
|---------|-----------|-----------|------------|-----------|----------|
| Web | 1 | 4 | 70% | 60s cooldown | 300s cooldown |
| Worker | 1 | 3 | 70% | 60s cooldown | 300s cooldown |

Check current scaling status:
```bash
aws application-autoscaling describe-scalable-targets \
  --service-namespace ecs \
  --query "ScalableTargets[].[ResourceId,MinCapacity,MaxCapacity]" --output table
```

---

## 10. WAF (Web Application Firewall)

The ALB is protected by AWS WAF v2 (`digestor-dev-waf`) with these rules:

| Rule | Priority | Action | Description |
|------|----------|--------|-------------|
| AWSManagedRulesCommonRuleSet | 1 | Block | XSS, path traversal, file inclusion |
| AWSManagedRulesSQLiRuleSet | 2 | Block | SQL injection attacks |
| AWSManagedRulesKnownBadInputsRuleSet | 3 | Block | Log4j, SSRF, known exploits |
| RateLimitRule | 4 | Block | >2000 requests per IP per 5 min |

Check WAF metrics:
```bash
aws wafv2 get-sampled-requests --web-acl-arn "YOUR_WAF_ARN" \
  --rule-metric-name RateLimit --scope REGIONAL \
  --time-window StartTime=$(date -d '1 hour ago' +%s),EndTime=$(date +%s) --max-items 10
```

---

## 11. E2E Testing

Run the comprehensive test suite against the deployed environment:

```bash
python test_phase5.py
```

This runs 43 tests covering:
- Authentication (all 3 roles: admin, supervisor, engineer)
- Document upload, processing, and result retrieval
- Feedback (thumbs up/down) and inline answer editing
- Project CRUD, submission, and supervisor approval/rejection
- Ticket creation and listing
- Analytics dashboard endpoint

---

## 12. Troubleshooting

### Container won't start
```bash
# Check ECS service events
aws ecs describe-services --cluster digestor-dev --services digestor-web-dev \
  --query "services[0].events[:5]" --output table

# Check container logs
aws logs tail /ecs/digestor-dev --since 10m
```

### Processing stuck (infinite polling)
- Backend must set `status = "complete"` (not `"completed"`)
- Check if the document processing record exists in RDS
- Check worker logs for Redis connection issues

### Worker crash loop
- Verify Redis is reachable from ECS security group
- Check `socket_timeout` setting (should be 600, not 10)

### Login succeeds but page doesn't redirect
- Frontend must use `useAuth().login()`, not `apiClient.login()` directly

### Upload returns 500
- Check S3 bucket permissions (ECS task role needs s3:PutObject)
- Verify `content_type` fallback handles None values

### ECS keeps using old image after push
- `:latest` tag doesn't force pull. Must register new task definition with `@sha256:DIGEST`
- The CI/CD pipeline handles this automatically

### Windows / Git Bash path issues
- Always prefix AWS CLI commands with `MSYS_NO_PATHCONV=1` to prevent path expansion
