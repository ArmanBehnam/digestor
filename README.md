# Digestor v2.0

Intelligent document analysis platform for structural engineering. Upload PDF documents and automatically extract answers to 25 critical engineering questions across 6 categories using AI-powered processing with a dual-path architecture.

## Features

- **Dual-Path AI Processing**: PDF.js fast path (~20s) with automatic quality-based fallback to AWS Textract deep analysis (~3-5 min)
- **Multi-Agent Deep Analysis**: 4-agent pipeline (OCR, Engineering QA, Validation, Orchestrator) for complex/scanned documents
- **25 Engineering Questions**: Covers Building Code, Deflection Criteria, Wind Load, Gravity Loads, Snow Load, and Seismic Load
- **Role-Based Access Control**: Admin, Supervisor, and Engineer roles with AWS Cognito authentication
- **Supervisor Approval Workflow**: Engineers submit projects for supervisor review, with notes, remarks, and snapshot tracking
- **Inline Editing & Feedback**: Edit extracted answers with full audit trail, provide thumbs up/down feedback per result
- **Project Management**: Organize documents into projects, track status, manage submissions with hash-based lookups
- **Real-Time Processing Status**: Live polling with progress indicators during document analysis
- **Analytics Dashboard**: Overview metrics, edit history, and processing trends
- **Admin Panel**: User management, role assignment, supervisor assignment, system settings

## Architecture

```
                        +------------------+
                        |   Browser (React |
                        |   + PDF.js)      |
                        +--------+---------+
                                 |
                        +--------v---------+
                        |  ALB (HTTP:80)   |
                        +--------+---------+
                                 |
                   +-------------+-------------+
                   |                           |
          +--------v---------+       +--------v---------+
          |  ECS Web Service |       | ECS Worker Service|
          |  (FastAPI +      |       | (RQ Consumer)     |
          |   React static)  |       |                   |
          +--+----+----+---+-+       +---+----+----+----+
             |    |    |   |             |    |    |    |
     +-------+  +-+  +-+  +-----+  +---+  +-+  +-+  +-+
     |          |     |          |  |       |    |      |
  +--v---+ +---v-+ +-v----+ +---v--v-+ +--v--+ |  +---v----+
  |Cognito| | RDS | |Redis | |   S3   | |OpenAI| |  |Textract|
  | (Auth)| |(PG) | |(Queue| |(Uploads| |GPT-4o| |  |  (OCR) |
  +-------+ +-----+ |)     | |)       | +------+ |  +--------+
                     +------+ +--------+       +--v-----+
                                               | Azure  |
                                               |Cognitive|
                                               |(OCR)    |
                                               +---------+
```

## Processing Pipeline

### Dual-Path Architecture

The system uses a two-tier processing approach optimized for speed and accuracy:

```
                     +---------------------+
                     | Browser uploads PDF  |
                     | PDF.js extracts text |
                     +----------+----------+
                                |
                     +----------v----------+
                     | POST /upload-document|
                     | (S3 + DB record)     |
                     +----------+----------+
                                |
                     +----------v----------+
                     | POST /process-document|
                     +----------+----------+
                                |
                     +----------v----------+
                     |  Processing Mode?    |
                     +--+------+--------+--+
                        |      |        |
                   auto |  quick|   deep |
                        |      |        |
               +--------v--+   |   +----v--------+
               | PDF.js     |  |   | AWS Deep     |
               | Fast Path  |<-+   | Analysis     |
               | (~20 sec)  |      | (~3-5 min)   |
               +-----+------+      +------+-------+
                     |                     |
              +------v------+              |
              | FallbackDet.|              |
              | evaluates:  |              |
              | - garbage%  |              |
              | - missing#  |              |
              | - confidence|              |
              +--+-------+--+              |
                 |       |                 |
              PASS    FAIL                 |
                 |       |                 |
                 |  +----v----+            |
                 |  | Enqueue |------->----+
                 |  | AWS job |
                 |  +---------+
                 |
          +------v------+
          | Results saved|
          | status=complete|
          +--------------+
```

### Path 1: PDF.js Fast Path (Default)
1. **Browser-side extraction**: PDF.js extracts text directly in the browser
2. **Upload**: `POST /api/upload-document` sends file to S3 + creates DB record
3. **Process**: `POST /api/process-document` with `extracted_text`
4. **LLM Processing**: Text chunked at 40K chars (2K overlap), sent to LLM
5. **LLM Hierarchy**: OpenAI GPT-4o (primary) -> Anthropic Claude (fallback) -> DeepSeek (fallback)
6. **Quality Check**: FallbackDetector evaluates results
7. **Results**: Saved immediately (~20 seconds total)

### Path 2: AWS Deep Analysis (Fallback or Manual)
1. **Triggered by**: FallbackDetector failure OR `mode=deep` OR `POST /api/process-aws`
2. **Queued**: Job enqueued to Redis, picked up by RQ Worker service
3. **4-Agent Pipeline**:
   - **OCRAgent**: AWS Textract for high-fidelity text extraction (handles scanned docs, tables)
   - **EngineeringQAAgent**: LLM-powered Q&A with coordinate mapping to source pages
   - **ValidationAgent**: Rules-based validation of extracted answers
   - **OrchestratorAgent**: Coordinates the pipeline, manages retries and aggregation
4. **Results**: Saved when complete (~3-5 minutes)

### FallbackDetector Criteria
The FallbackDetector automatically escalates to AWS deep analysis when:
- Garbage character ratio > 15% (indicates scanned/image PDF)
- Missing answers > 5 out of 25 questions
- Average confidence score < 70%
- Complex tables detected that PDF.js can't parse
- Document identified as scanned (no extractable text layer)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui |
| Backend | Python 3.12, FastAPI, async SQLAlchemy, Alembic |
| Auth | AWS Cognito (JWT verification, RBAC) |
| Database | PostgreSQL (RDS) with asyncpg driver, RDS Proxy |
| Queue | Redis (ElastiCache) + RQ workers |
| Storage | AWS S3 (presigned URLs for upload/download) |
| LLM | OpenAI GPT-4o (primary), Anthropic Claude (fallback), DeepSeek (fallback) |
| OCR | PDF.js (browser-side), AWS Textract (deep), Azure Cognitive Services (fallback) |
| Agents | Custom multi-agent system built on LangChain base class |
| Infrastructure | ECS Fargate, ALB, Terraform, CloudWatch, WAF v2 |
| CI/CD | GitHub Actions (build, test, deploy on push to main) |

## Project Structure

```
digestor-unified/
  backend/
    api/                      # FastAPI application
      endpoints/
        auth.py               # Login, register, token refresh, password reset
        upload.py              # Document upload to S3 + auto-project creation
        process.py             # Document processing orchestrator
        process_pdfjs.py       # PDF.js fast path with LLM chunking
        process_aws.py         # AWS deep analysis fallback
        results.py             # Results polling, feedback, inline editing
        projects.py            # Full project CRUD, review workflow, notes, remarks
        files.py               # S3 presigned URL generation (single + batch)
        admin.py               # User management, role assignment, settings
        feedback_survey.py     # Feedback survey CRUD
        tickets.py             # Support tickets
        analytics.py           # Dashboard metrics, edit history, trends
        chat.py                # RAG chatbot for document Q&A
      main.py                 # FastAPI app factory, router registration
    auth/                     # Cognito JWT verification, RBAC middleware
    db/
      models.py               # SQLAlchemy ORM models (8 tables)
      migrations/             # Alembic migrations (auto-run on startup)
    llm/
      registry.py             # LLM engine registry with fallback chain
      engines/                # OpenAI, Anthropic, DeepSeek adapters
    ocr/
      engines/                # Textract, Azure, Tesseract adapters
      agents/                 # Multi-agent pipeline for deep analysis
        base_agent.py         # Talk2DrawingsBaseAgent (LangChain-based)
        ocr_agent.py          # OCRAgent - AWS Textract extraction
        qa_agent.py           # EngineeringQAAgent - LLM question answering
        validation_agent.py   # ValidationAgent - rules-based checking
        orchestrator.py       # OrchestratorAgent - pipeline coordinator
      config/settings.py      # Processing configuration
    services/
      s3_service.py           # S3 upload/download/presigned URLs
      fallback_detector.py    # Quality evaluation + AWS escalation
    tasks.py                  # RQ worker task definitions
    worker.py                 # RQ worker entry point
    entrypoint.py             # Container startup (migrations + uvicorn)
  frontend/
    src/
      components/             # React UI components (shadcn/ui based)
      pages/                  # Page-level components
      hooks/                  # Custom hooks (useAuth, useProjects, etc.)
      lib/
        apiClient.ts          # Typed API client for all endpoints
        auth.ts               # Cognito token management
  infrastructure/
    docker/
      Dockerfile              # Multi-stage (Node build -> Python runtime)
    ecs/                      # ECS task definition templates
    terraform/                # IaC modules (VPC, RDS, Cognito, S3, ALB, ECS)
  .github/
    workflows/
      deploy.yml              # Build + push ECR + deploy ECS on push to main
      test.yml                # Lint + build validation on PR
  docs/
    DEPLOYMENT_RUNBOOK.md     # Operations, monitoring, troubleshooting guide
  CICD_SETUP.md               # CI/CD initial setup instructions
```

## Database Models

| Table | Purpose |
|-------|---------|
| `users` | User accounts (linked to Cognito via `cognito_sub`) |
| `projects` | Engineering projects with approval workflow |
| `document_processings` | Upload + processing records with results JSON |
| `project_notes` | Notes attached to projects by users |
| `project_remarks` | Row-level remarks on project data (by hash + row_id) |
| `result_edits` | Audit trail of inline answer edits |
| `feedback_surveys` | User feedback surveys (draft/submitted) |
| `tickets` | Support tickets |

## API Endpoints

### Authentication (`/api/auth/*`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Register new user (Cognito + DB) |
| POST | `/api/auth/login` | Authenticate (returns tokens or challenge) |
| POST | `/api/auth/respond-challenge` | Handle NEW_PASSWORD_REQUIRED for migrated users |
| POST | `/api/auth/refresh` | Refresh access token |
| POST | `/api/auth/reset-password` | Initiate password reset (sends code) |
| POST | `/api/auth/confirm-reset` | Confirm reset with code + new password |
| POST | `/api/auth/logout` | Global sign-out |
| GET | `/api/auth/me` | Get current user profile |

### Document Upload & Processing (`/api/*`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/upload-document` | Upload PDF to S3, auto-create project, returns `processingId` |
| POST | `/api/process-document` | Process with PDF.js fast path (auto-fallback to AWS) |
| POST | `/api/process-aws` | Force AWS deep analysis pipeline |
| GET | `/api/results/{document_id}` | Poll processing status and results |
| POST | `/api/results/feedback` | Submit thumbs up/down for an answer |
| PUT | `/api/results/update` | Inline edit an extracted answer |

### Projects (`/api/projects/*`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects` | List projects (filterable by status, paginated) |
| POST | `/api/projects` | Create new project |
| GET | `/api/projects/pending` | List projects pending supervisor review |
| GET | `/api/projects/finalized` | Get finalized project by `project_key` |
| POST | `/api/projects/repair` | Repair project data |
| POST | `/api/projects/update-approved` | Update an already-approved project |
| POST | `/api/projects/result-edits` | Record an inline edit on project results |
| GET | `/api/projects/{id}` | Get project with documents |
| PUT | `/api/projects/{id}` | Update project metadata |
| DELETE | `/api/projects/{id}` | Delete project |
| GET | `/api/projects/by-hash/{hash}` | Look up project by hash |
| PUT | `/api/projects/by-hash/{hash}` | Update project by hash |
| GET | `/api/projects/by-hash/{hash}/records` | Get processing records by hash |
| GET | `/api/projects/by-hash/{hash}/edits` | Get edit history by hash |

### Project Notes (`/api/projects/{id}/notes`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects/{id}/notes` | List notes for a project |
| POST | `/api/projects/{id}/notes` | Add a note to a project |
| PUT | `/api/projects/{id}/notes/{noteId}` | Update a note |
| DELETE | `/api/projects/{id}/notes/{noteId}` | Delete a note |

### Project Remarks (`/api/projects/remarks/*`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/projects/remarks/{hash}` | Get all remarks for a project hash |
| POST | `/api/projects/remarks` | Create a remark on a specific row |
| PUT | `/api/projects/remarks/{id}` | Update a remark |
| DELETE | `/api/projects/remarks/{id}` | Delete a remark |

### Processing Records (`/api/projects/records/*`)

| Method | Path | Description |
|--------|------|-------------|
| PUT | `/api/projects/records/{id}` | Update a processing record |
| DELETE | `/api/projects/records/{id}` | Delete a processing record |
| GET | `/api/projects/records/{id}/text` | Get extracted text for a record |
| GET | `/api/projects/records/{id}/metrics` | Get processing metrics for a record |

### Submission & Approval (`/api/*`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/submit-project` | Submit project for supervisor review (saves snapshot) |
| POST | `/api/approve-project` | Approve or reject a submitted project |

### Files (`/api/files/*`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/files/presigned-url` | Get presigned S3 URL for a single file |
| POST | `/api/files/presigned-urls` | Get presigned S3 URLs for multiple files (batch) |

### Admin (`/api/admin/*`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/users` | List all users (admin only) |
| PUT | `/api/admin/users/{user_id}/role` | Update user role |
| GET | `/api/admin/users/for-assignment` | Get users available for supervisor assignment |
| GET | `/api/admin/settings` | Get system settings |
| PUT | `/api/admin/settings` | Update system settings |
| GET | `/api/admin/feedback` | Get all feedback entries |

### Feedback Surveys (`/api/feedback/*`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/feedback/survey` | Get current user's survey |
| POST | `/api/feedback/survey` | Save survey draft |
| POST | `/api/feedback/survey/submit` | Submit completed survey |

### Analytics (`/api/analytics/*`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/analytics/overview` | Dashboard metrics (counts, averages) |
| GET | `/api/analytics/edits` | Edit history across all projects |
| GET | `/api/analytics/trends` | Processing trends over time |

### Other

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | RAG chatbot for document Q&A |
| POST | `/api/tickets` | Create support ticket |
| GET | `/api/tickets` | List support tickets |
| GET | `/api/health` | Health check |

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
3. Registers new ECS task definitions with image digest
4. Deploys to ECS Fargate (web + worker services)
5. Runs health check verification

See [CICD_SETUP.md](CICD_SETUP.md) for initial setup instructions.

### Manual

```bash
# Build and push
docker build -t digestor-unified -f infrastructure/docker/Dockerfile .
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ECR_REGISTRY>
docker tag digestor-unified:latest <ECR_REGISTRY>/digetor:latest
docker push <ECR_REGISTRY>/digetor:latest

# Get image digest and register new task definition with @sha256:DIGEST
# (Required - :latest tag alone won't force ECS to pull new image)

# Deploy
aws ecs update-service --cluster digestor-dev --service digestor-web-dev --force-new-deployment
aws ecs update-service --cluster digestor-dev --service digestor-worker-dev --force-new-deployment
```

## Monitoring & Security

- **CloudWatch Dashboard**: Real-time metrics (requests, response time, CPU/memory, RDS connections)
- **CloudWatch Alarms**: 6 alarms for 5xx errors, unhealthy targets, CPU, memory, response time
- **Auto-scaling**: Web (1-4 tasks) and Worker (1-3 tasks) scale on CPU at 70%
- **WAF v2**: SQL injection, XSS, known exploits, IP rate limiting (2000 req/5 min)
- **Structured Logging**: JSON logs via structlog, shipped to CloudWatch Logs
- **Rate Limiting**: slowapi on all API endpoints

See [docs/DEPLOYMENT_RUNBOOK.md](docs/DEPLOYMENT_RUNBOOK.md) for full monitoring, troubleshooting, and operations guide.

## Testing

```bash
# Run E2E tests against deployed environment (43 tests)
python test_phase5.py

# Run unit tests
pytest tests/
```

## License

Proprietary - ClarkDietrich Building Systems
