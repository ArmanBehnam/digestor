# Digestor v2.0

Intelligent document analysis platform for structural engineering. Upload PDF documents and automatically extract answers to 25 critical engineering questions across 6 categories using AI-powered processing.

## Features

- **AI-Powered PDF Analysis**: Extracts text via PDF.js in the browser, then processes through GPT-4o with automatic quality-based fallback to AWS Textract deep analysis
- **25 Engineering Questions**: Covers Building Code, Deflection Criteria, Wind Load, Gravity Loads, Snow Load, and Seismic Load
- **Role-Based Access Control**: Admin, Supervisor, and Engineer roles with Cognito authentication
- **Supervisor Approval Workflow**: Engineers submit projects for supervisor review and approval
- **Inline Editing & Feedback**: Edit extracted answers and provide thumbs up/down feedback per result
- **Project Management**: Organize documents into projects, track status, and manage submissions
- **Real-Time Processing Status**: Live polling with progress indicators during document analysis
- **Analytics Dashboard**: Overview metrics for document processing, user activity, and project status

## Architecture

```
Browser (React + PDF.js)
    |
    v
ALB (Application Load Balancer)
    |
    v
ECS Fargate
    |- Web Service (FastAPI + static frontend)
    |- Worker Service (RQ background jobs)
    |
    +-- RDS PostgreSQL (async SQLAlchemy + Alembic)
    +-- ElastiCache Redis (job queue)
    +-- S3 (document uploads)
    +-- Cognito (authentication)
    +-- OpenAI GPT-4o (primary LLM)
    +-- Azure Cognitive Services (OCR fallback)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui |
| Backend | Python 3.12, FastAPI, async SQLAlchemy, Alembic |
| Auth | AWS Cognito (JWT verification) |
| Database | PostgreSQL (RDS) with asyncpg driver |
| Queue | Redis (ElastiCache) + RQ workers |
| Storage | AWS S3 |
| LLM | OpenAI GPT-4o (primary), Anthropic Claude (fallback), DeepSeek (fallback) |
| OCR | PDF.js (fast path), AWS Textract + Azure OCR (deep analysis) |
| Infrastructure | ECS Fargate, ALB, Terraform |
| CI/CD | GitHub Actions |

## Project Structure

```
digestor-unified/
  backend/
    api/                  # FastAPI endpoints
      endpoints/
        auth.py           # Login, register, token refresh
        upload.py         # Document upload to S3
        process.py        # Document processing orchestrator
        process_pdfjs.py  # PDF.js fast path with LLM
        process_aws.py    # AWS deep analysis fallback
        results.py        # Results, feedback, inline editing
        projects.py       # Project CRUD + supervisor review
        tickets.py        # Support tickets
        analytics.py      # Dashboard metrics
        chat.py           # RAG chatbot
    auth/                 # Cognito JWT verification, RBAC
    db/                   # SQLAlchemy models, migrations
    llm/                  # LLM engines (OpenAI, Anthropic, DeepSeek)
    ocr/                  # OCR engines (Textract, Azure, Tesseract)
    services/             # S3, email, fallback detection
  frontend/
    src/
      components/         # React components
      pages/              # Page-level components
      hooks/              # Custom React hooks (useAuth, etc.)
      lib/                # API client, utilities
  infrastructure/
    docker/               # Multi-stage Dockerfile
    ecs/                  # ECS task definition templates
    terraform/            # IaC modules (RDS, Cognito, S3, ALB, ECS)
  .github/
    workflows/
      deploy.yml          # Build + deploy on push to main
      test.yml            # Lint + build on PR
```

## Processing Pipeline

```
1. Browser extracts text from PDF via PDF.js
2. POST /api/upload-document  ->  S3 upload + DB record
3. POST /api/process-document ->  LLM answers 25 questions
4. FallbackDetector evaluates quality:
   - Garbage ratio > 15%?  -> AWS deep analysis
   - Missing answers > 5?  -> AWS deep analysis
   - Avg confidence < 70%? -> AWS deep analysis
5. Results saved immediately (PDF.js path ~20s)
6. GET /api/results/{id}    ->  Poll for status + results
```

## Local Development

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker Desktop
- AWS CLI configured

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Set environment variables (see .env.example)
uvicorn api.main:app --reload --port 8080
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Docker (Full Stack)

```bash
docker build -f infrastructure/docker/Dockerfile -t digestor-unified .
docker run -p 8080:8080 --env-file .env digestor-unified
```

## Deployment

### Automated (CI/CD)

Push to `main` triggers GitHub Actions:
1. Builds Docker image (multi-stage: Node frontend + Python backend)
2. Pushes to Amazon ECR
3. Registers new ECS task definitions
4. Deploys to ECS Fargate (web + worker services)
5. Runs health check

See [CICD_SETUP.md](CICD_SETUP.md) for initial setup instructions.

### Manual

```bash
# Build and push
docker build -t digestor-unified -f infrastructure/docker/Dockerfile .
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ECR_REGISTRY>
docker tag digestor-unified:latest <ECR_REGISTRY>/digetor:latest
docker push <ECR_REGISTRY>/digetor:latest

# Deploy
aws ecs update-service --cluster digestor-dev --service digestor-web-dev --force-new-deployment
aws ecs update-service --cluster digestor-dev --service digestor-worker-dev --force-new-deployment
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/login` | Authenticate user |
| POST | `/api/auth/register` | Register new user |
| POST | `/api/auth/refresh` | Refresh access token |
| GET | `/api/auth/me` | Get current user profile |
| POST | `/api/upload-document` | Upload PDF to S3 |
| POST | `/api/process-document` | Process document with AI |
| GET | `/api/results/{id}` | Get processing results |
| POST | `/api/results/feedback` | Submit feedback on answer |
| PUT | `/api/results/update` | Edit an extracted answer |
| GET | `/api/projects` | List projects |
| POST | `/api/projects` | Create project |
| GET | `/api/projects/{id}` | Get project details |
| POST | `/api/submit-project` | Submit for supervisor review |
| POST | `/api/approve-project` | Approve or reject project |
| GET | `/api/analytics/overview` | Dashboard metrics |
| GET | `/api/health` | Health check |

## Testing

```bash
# Run E2E tests against deployed environment
python test_phase5.py

# Run unit tests
pytest tests/
```

## License

Proprietary - ClarkDietrich Building Systems
