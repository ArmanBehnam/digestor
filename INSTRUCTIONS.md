# Digestor Unified - Setup & Configuration Instructions

## AWS Account & Region

| Item | Value |
|------|-------|
| AWS Account ID | `800712212732` |
| AWS Region | `us-east-1` |

---

## AWS Cognito (Authentication)

| Item | Value |
|------|-------|
| User Pool ID | `us-east-1_DGMrbW6Vw` |
| App Client ID | `6k00q57poml1uooj9aal7tga8c` |
| User Pool Console | `https://us-east-1.console.aws.amazon.com/cognito/v2/idp/user-pools/us-east-1_DGMrbW6Vw/users` |

**Roles (Cognito Groups):**

| Role | Group Name | Permissions |
|------|-----------|-------------|
| Engineer | `engineer` | Upload, process, view own projects |
| Supervisor | `supervisor` | Review, approve/reject, manage assigned engineers |
| Admin | `admin` | Full access: user management, role assignment, settings |

**Env vars used by backend:**
```
COGNITO_USER_POOL_ID=us-east-1_DGMrbW6Vw
COGNITO_APP_CLIENT_ID=6k00q57poml1uooj9aal7tga8c
```

---

## AWS S3 (File Storage)

| Item | Value |
|------|-------|
| Dev bucket | `digestor-dev-storage` |
| Prod bucket | `digestor-unified-storage` |
| Encryption | AES-256 (server-side) |
| Public access | Blocked (all 4 settings) |

**Lifecycle rules:**
- `temp/*` files deleted after 1 day
- `uploads/*` files deleted after 7 days

**Env var:**
```
S3_BUCKET=digestor-dev-storage
```

---

## AWS RDS (PostgreSQL Database)

| Item | Value |
|------|-------|
| Engine | PostgreSQL 15.4 |
| Instance ID | `digestor-dev` (dev), `digestor-prod` (prod) |
| DB name | `digestor_dev` (dev), `digestor_prod` (prod) |
| Username | `digestor` |
| Password | Managed by AWS Secrets Manager (`manage_master_user_password = true`) |
| Instance class | `db.t3.micro` (dev), `db.t3.small` (prod) |
| RDS Proxy | `digestor-dev` (endpoint used for connections) |

**Password retrieval:**
The DB password is auto-managed by AWS. The application resolves it at startup via:
```
RDS_SECRET_ARN=<auto-populated by Terraform>
RDS_ENDPOINT=<RDS Proxy endpoint>
RDS_DB_NAME=digestor_dev
```

Or via direct `DATABASE_URL` from CI/CD:
```
DATABASE_URL=postgresql+asyncpg://digestor:<password>@<rds-proxy-endpoint>:5432/digestor_dev
```

**Local dev default:**
```
DATABASE_URL=postgresql+asyncpg://digestor:digestor_dev_password@localhost:5432/digestor_dev
```

---

## AWS ElastiCache (Redis)

| Item | Value |
|------|-------|
| Engine | Redis 7.x |
| Dev endpoint | Set in `dev.tfvars` (fill in after provisioning) |

**Env var:**
```
REDIS_URL=redis://localhost:6379           # local dev
REDIS_URL=redis://<endpoint>:6379          # production
```

---

## AWS ECS (Container Hosting)

| Item | Value |
|------|-------|
| Cluster | `digestor-dev` |
| Web service | `digestor-web-dev` |
| Worker service | `digestor-worker-dev` |
| Launch type | Fargate |
| Web port | `8080` |

**IAM Roles:**

| Role | ARN | Purpose |
|------|-----|---------|
| Task role | `arn:aws:iam::800712212732:role/digestor-ecs-task-dev` | S3, Textract, SES, Secrets Manager, CloudWatch |
| Execution role | `arn:aws:iam::800712212732:role/digestor-ecs-execution-dev` | Pull ECR images, write logs |

**Container sizing:**

| Service | Dev | Prod |
|---------|-----|------|
| Web CPU | 512 (0.5 vCPU) | 1024 (1 vCPU) |
| Web memory | 1024 MB | 2048 MB |
| Worker CPU | 512 (0.5 vCPU) | 1024 (1 vCPU) |
| Worker memory | 2048 MB | 4096 MB |

**Auto-scaling:**

| Service | Min | Max | Target CPU |
|---------|-----|-----|------------|
| Web (dev) | 1 | 4 | 70% |
| Web (prod) | 2 | 8 | 70% |
| Worker (dev) | 1 | 3 | 70% |
| Worker (prod) | 1 | 4 | 70% |

---

## AWS ECR (Container Registry)

| Item | Value |
|------|-------|
| Repository | `digestor-unified-dev` |
| Full URI | `800712212732.dkr.ecr.us-east-1.amazonaws.com/digestor-unified-dev` |
| Scan on push | Enabled |

**Push commands:**
```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 800712212732.dkr.ecr.us-east-1.amazonaws.com
docker build -t digestor-unified-dev -f infrastructure/docker/Dockerfile .
docker tag digestor-unified-dev:latest 800712212732.dkr.ecr.us-east-1.amazonaws.com/digestor-unified-dev:latest
docker push 800712212732.dkr.ecr.us-east-1.amazonaws.com/digestor-unified-dev:latest
```

---

## AWS ALB (Load Balancer)

| Item | Value |
|------|-------|
| Name | `digestor-dev` |
| Type | Application (internet-facing) |
| HTTP (80) | Redirects to HTTPS (301) |
| HTTPS (443) | Forwards to ECS target group on port 8080 |
| TLS policy | `ELBSecurityPolicy-TLS13-1-2-2021-06` |
| Health check | `GET /api/health` (interval 30s, 2 healthy / 5 unhealthy) |
| Sticky sessions | Enabled (LB cookie, 24h) |

**ACM Certificate:**
```
arn:aws:acm:us-east-1:800712212732:certificate/<FILL_IN>
```

---

## AWS WAF (Web Application Firewall)

| Item | Value |
|------|-------|
| Web ACL name | `digestor-dev-waf` |
| WAF ARN | `arn:aws:wafv2:us-east-1:800712212732:regional/webacl/digestor-dev-waf/134e2bc9-acbe-415b-a05f-352828d44472` |
| Associated ALB ARN | `arn:aws:elasticloadbalancing:us-east-1:800712212732:loadbalancer/app/digestor-dev/1a0db011f0170ecd` |

**Rules:**
1. AWS Common Rule Set (priority 1)
2. SQL Injection protection (priority 2)
3. Known Bad Inputs (priority 3)
4. Rate limiting: 2000 requests per 5 minutes per IP (priority 4)

---

## AWS CloudWatch (Monitoring)

| Item | Value |
|------|-------|
| Log group | `/ecs/digestor-dev` |
| Log retention | 7 days (dev), 30 days (prod) |
| Dashboard | `https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=digestor-dev` |

**Alarms:**

| Alarm | Threshold |
|-------|-----------|
| 5xx errors | > 10 in 5 min |
| Unhealthy targets | >= 1 for 3 min |
| Web CPU | > 80% for 10 min |
| Web memory | > 85% for 10 min |
| Worker CPU | > 80% for 10 min |
| Response time | > 5s for 10 min |

---

## AWS Secrets Manager

| Secret | Path | Purpose |
|--------|------|---------|
| DB credentials | Auto-managed by RDS `manage_master_user_password` | RDS Proxy auth + app DB connection |
| App secrets | `digestor/production/secrets` | API keys (OpenAI, Azure, etc.) |

**Keys stored in `digestor/production/secrets`:**
```json
{
  "OPENAI_API_KEY": "sk-...",
  "ANTHROPIC_API_KEY": "sk-ant-...",
  "DEEPSEEK_API_KEY": "sk-...",
  "AZURE_ENDPOINT": "https://...",
  "AZURE_API_KEY": "..."
}
```

---

## LLM API Keys (Processing Engines)

| Provider | Env var | Role |
|----------|---------|------|
| OpenAI (GPT-4o) | `OPENAI_API_KEY` | Primary LLM |
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | Fallback LLM |
| DeepSeek | `DEEPSEEK_API_KEY` | Second fallback LLM |

**Fallback chain:** OpenAI -> Anthropic -> DeepSeek

---

## Azure (OCR Fallback)

| Item | Env var |
|------|---------|
| Endpoint | `AZURE_ENDPOINT` |
| API Key | `AZURE_API_KEY` |
| Service | Azure AI Form Recognizer (Document Intelligence) |

---

## CI/CD (GitHub Actions)

**Workflow files:**
- `.github/workflows/deploy.yml` - Build + push to ECR + deploy to ECS (on push to `main`)
- `.github/workflows/test.yml` - Lint + type check + build (on PR to `main`)

**Required GitHub Secrets:**

| Secret | Description |
|--------|-------------|
| `AWS_ACCESS_KEY_ID` | IAM user with ECR/ECS permissions |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret |
| `DATABASE_URL` | Full PostgreSQL connection string |
| `REDIS_URL` | Full Redis connection string |
| `OPENAI_API_KEY` | OpenAI API key |
| `AZURE_API_KEY` | Azure Form Recognizer key |
| `AZURE_ENDPOINT` | Azure Form Recognizer endpoint |

---

## Local Development

### Quick start with Docker Compose:
```bash
cd infrastructure/docker
docker compose up --build
```

This starts: PostgreSQL + Redis + Migrations + Web (8080) + Worker

### Manual start:
```bash
# Backend
cd backend
cp ../.env.example ../.env   # Fill in values
pip install -r requirements.txt
python -m alembic upgrade head
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload

# Worker (separate terminal)
cd backend
python -c "from worker import run_worker; run_worker()"

# Frontend (separate terminal)
cd frontend
npm install
npm run dev   # Vite dev server on :5173
```

### Frontend env vars:
```
VITE_API_URL=/api                          # API base (default: /api, proxied by Vite)
VITE_WS_HOST=<host>                        # WebSocket host (default: window.location.host)
```

---

## Terraform Deployment

### First-time setup:
```bash
cd infrastructure/terraform

# Initialize
terraform init

# Plan (dev)
terraform plan -var-file=environments/dev.tfvars

# Apply
terraform apply -var-file=environments/dev.tfvars
```

### Required manual inputs in `dev.tfvars`:
```hcl
vpc_id              = "vpc-<YOUR_VPC>"
public_subnet_ids   = ["subnet-<PUB1>", "subnet-<PUB2>"]
private_subnet_ids  = ["subnet-<PRIV1>", "subnet-<PRIV2>"]
redis_endpoint      = "<YOUR_ELASTICACHE_ENDPOINT>"
acm_certificate_arn = "arn:aws:acm:us-east-1:800712212732:certificate/<YOUR_CERT>"
```

### Terraform outputs:
```
alb_dns              -> ALB public DNS name
ecr_repository_url   -> ECR image URI
rds_endpoint         -> RDS Proxy endpoint
cognito_pool_id      -> Cognito User Pool ID
s3_bucket            -> S3 bucket name
waf_web_acl_arn      -> WAF Web ACL ARN
```

---

## Key URLs & Console Links

| Service | URL |
|---------|-----|
| Cognito User Pool | `https://us-east-1.console.aws.amazon.com/cognito/v2/idp/user-pools/us-east-1_DGMrbW6Vw/users` |
| ECS Cluster | `https://us-east-1.console.aws.amazon.com/ecs/v2/clusters/digestor-dev` |
| ECR Repository | `https://us-east-1.console.aws.amazon.com/ecr/repositories/private/800712212732/digestor-unified-dev` |
| S3 Bucket | `https://s3.console.aws.amazon.com/s3/buckets/digestor-dev-storage` |
| CloudWatch Logs | `https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/$252Fecs$252Fdigestor-dev` |
| RDS Instance | `https://us-east-1.console.aws.amazon.com/rds/home?region=us-east-1#database:id=digestor-dev` |
| WAF Console | `https://us-east-1.console.aws.amazon.com/wafv2/homev2/web-acls` |
| Secrets Manager | `https://us-east-1.console.aws.amazon.com/secretsmanager/listsecrets?region=us-east-1` |

---

## Environment Variable Reference (Complete)

| Variable | Where Used | Example Value |
|----------|-----------|---------------|
| `PROCESS_TYPE` | Entrypoint routing | `web` or `worker` |
| `ENVIRONMENT` | All services | `development` / `dev` / `prod` |
| `PORT` | Web server | `8080` |
| `AWS_REGION` | All AWS SDK calls | `us-east-1` |
| `AWS_DEFAULT_REGION` | Boto3 default | `us-east-1` |
| `DATABASE_URL` | DB connection (CI/CD path) | `postgresql+asyncpg://digestor:<pass>@<host>:5432/digestor_dev` |
| `RDS_ENDPOINT` | DB connection (Terraform path) | `digestor-dev.proxy-xxx.us-east-1.rds.amazonaws.com` |
| `RDS_DB_NAME` | DB connection (Terraform path) | `digestor_dev` |
| `RDS_SECRET_ARN` | DB password from Secrets Manager | `arn:aws:secretsmanager:...` |
| `REDIS_URL` | Redis/RQ connection | `redis://localhost:6379` |
| `S3_BUCKET` | S3 uploads | `digestor-dev-storage` |
| `COGNITO_USER_POOL_ID` | JWT verification | `us-east-1_DGMrbW6Vw` |
| `COGNITO_APP_CLIENT_ID` | Cognito auth flows | `6k00q57poml1uooj9aal7tga8c` |
| `OPENAI_API_KEY` | Primary LLM | `sk-...` |
| `ANTHROPIC_API_KEY` | Fallback LLM | `sk-ant-...` |
| `DEEPSEEK_API_KEY` | Second fallback LLM | `sk-...` |
| `AZURE_ENDPOINT` | Azure OCR fallback | `https://....cognitiveservices.azure.com/` |
| `AZURE_API_KEY` | Azure OCR fallback | `...` |
| `USE_SECRETS_MANAGER` | Enable SM resolution | `true` / `false` |
| `SECRETS_MANAGER_SECRET_NAME` | SM secret path | `digestor/production/secrets` |
| `ALLOWED_ORIGINS` | CORS origins | `http://localhost:8080,http://localhost:5173` |
| `SQL_ECHO` | Debug SQL queries | `false` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `WEB_WORKERS` | Uvicorn workers | `1` |
