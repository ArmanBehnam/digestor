# =============================================================================
# Digestor Unified - Multi-Stage Dockerfile
# Stage 1: Build React frontend
# Stage 2: Python backend with frontend static files
# =============================================================================

# --- Stage 1: Build Frontend ---
FROM public.ecr.aws/docker/library/node:20-alpine AS frontend-builder

WORKDIR /frontend

# Install dependencies
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --production=false

# Copy source and build
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python Backend ---
FROM public.ecr.aws/docker/library/python:3.12-slim AS backend

# System dependencies for OCR and PDF processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ .

# Copy frontend build to static directory
COPY --from=frontend-builder /frontend/dist ./static/

# Copy shared config
COPY shared/ ./shared/

# Create local uploads directory for development fallback
RUN mkdir -p /app/local_uploads

# Set ownership
RUN chown -R appuser:appuser /app

USER appuser

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PROCESS_TYPE=web \
    PORT=8080 \
    HOST=0.0.0.0

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# Entrypoint routes to web or worker based on PROCESS_TYPE
ENTRYPOINT ["python", "entrypoint.py"]
