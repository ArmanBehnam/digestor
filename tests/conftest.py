"""
Digestor Unified - Test Configuration
Shared fixtures for all backend tests.

Uses SQLite in-memory DB with type compilation to handle PostgreSQL-specific
column types (UUID, JSONB, ARRAY) that the ORM models use.
"""

import os
import sys
import uuid
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import String, Text, JSON, event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Set test environment before importing app
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test.db"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["S3_BUCKET"] = "test-bucket"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["COGNITO_USER_POOL_ID"] = "us-east-1_TestPool"
os.environ["COGNITO_APP_CLIENT_ID"] = "test-client-id"
os.environ["SES_FROM_EMAIL"] = "test@digestor.test"
os.environ["ADMIN_EMAIL"] = "admin@digestor.test"
os.environ["OPENAI_API_KEY"] = "test-key"

# Ensure backend is on the Python path
backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(backend_dir))

# --- SQLite type compatibility for PostgreSQL column types ---
# Register type compilation rules so that PostgreSQL-specific types
# (UUID, JSONB, ARRAY) get compiled to SQLite-compatible types.
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB, ARRAY
from sqlalchemy.ext.compiler import compiles


@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "VARCHAR(36)"


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    return "JSON"


from db.models import Base


# ---------------------------------------------------------------------------
# Event loop
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop():
    """Create a shared event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Create an in-memory SQLite async engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine):
    """Create an async session for testing."""
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Auth fixtures (mock Cognito)
# ---------------------------------------------------------------------------
_user_sub = str(uuid.uuid4())
_admin_sub = str(uuid.uuid4())
_supervisor_sub = str(uuid.uuid4())


@pytest.fixture
def mock_user_claims():
    """Standard test user claims mimicking Cognito JWT payload."""
    return {
        "sub": _user_sub,
        "email": "testuser@digestor.test",
        "cognito:groups": ["engineer"],
        "cognito:username": "testuser@digestor.test",
        "custom:full_name": "Test User",
        "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TestPool",
    }


@pytest.fixture
def mock_admin_claims():
    """Admin user claims."""
    return {
        "sub": _admin_sub,
        "email": "admin@digestor.test",
        "cognito:groups": ["admin"],
        "cognito:username": "admin@digestor.test",
        "custom:full_name": "Admin User",
        "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TestPool",
    }


@pytest.fixture
def mock_supervisor_claims():
    """Supervisor user claims."""
    return {
        "sub": _supervisor_sub,
        "email": "supervisor@digestor.test",
        "cognito:groups": ["supervisor"],
        "cognito:username": "supervisor@digestor.test",
        "custom:full_name": "Supervisor User",
        "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TestPool",
    }


# ---------------------------------------------------------------------------
# Helper: seed a test user in the DB so endpoint lookups succeed
# ---------------------------------------------------------------------------
async def _seed_user(session, claims, role="engineer"):
    """Insert a User row matching the given Cognito claims."""
    from db.models import User
    user = User(
        cognito_sub=claims["sub"],
        email=claims["email"],
        full_name=claims.get("custom:full_name", "Test User"),
        role=role,
        organization="TestOrg",
    )
    session.add(user)
    await session.flush()
    return user


# ---------------------------------------------------------------------------
# FastAPI test client with dependency overrides
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def app_client(db_session, mock_user_claims):
    """
    Async HTTP client for testing FastAPI endpoints.
    Overrides auth + DB dependencies with test mocks.
    Seeds a matching user row so that DB lookups by cognito_sub succeed.
    """
    from api.main import app
    from api.dependencies import get_db, get_current_user

    # Seed the test user so endpoints that look up User by sub find a row
    await _seed_user(db_session, mock_user_claims, role="engineer")

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return mock_user_claims

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(db_session, mock_admin_claims):
    """HTTP client authenticated as admin."""
    from api.main import app
    from api.dependencies import get_db, get_current_user

    await _seed_user(db_session, mock_admin_claims, role="admin")

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return mock_admin_claims

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def supervisor_client(db_session, mock_supervisor_claims):
    """HTTP client authenticated as supervisor."""
    from api.main import app
    from api.dependencies import get_db, get_current_user

    await _seed_user(db_session, mock_supervisor_claims, role="supervisor")

    async def override_get_db():
        yield db_session

    async def override_get_current_user():
        return mock_supervisor_claims

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_pdf_text():
    """Sample engineering document text for PDF.js processing tests."""
    return """
    STRUCTURAL ENGINEERING REPORT
    Project: Office Building - 123 Main St
    Building Code: IBC 2021
    ASCE Reference: ASCE 7-22

    Wind Design Parameters:
    Basic Wind Speed (Vult): 115 mph
    Risk Category: II
    Exposure Category: B
    Internal Pressure Coefficient (GCpi): +/- 0.18

    Snow Load Parameters:
    Ground Snow Load (Pg): 30 psf
    Importance Factor (Is): 1.0
    Exposure Factor (Ce): 0.9
    Thermal Factor (Ct): 1.0
    Flat Roof Snow Load (Pf): 21.6 psf

    Seismic Design Parameters:
    Seismic Design Category: D
    Importance Factor (Ie): 1.0
    Component Importance Factor (Ip): 1.0
    Site Class: D
    SDS: 0.75g
    SD1: 0.45g

    Deflection Criteria:
    Walls: L/240
    Floors: L/360
    Roof: L/240
    Joists: L/360

    Gravity Loads:
    Live Load: 50 psf (office)
    Dead Load: 15 psf (typical floor)
    """


@pytest.fixture
def sample_pdfjs_results():
    """Sample results from PDF.js processing."""
    return [
        {
            "question": "Building Code and Version",
            "answer": "IBC 2021",
            "confidence": 0.95,
            "reference": "Page 1, line 3",
        },
        {
            "question": "ASCE Reference",
            "answer": "ASCE 7-22",
            "confidence": 0.92,
            "reference": "Page 1, line 4",
        },
        {
            "question": "Basic Wind Speed (Vult)",
            "answer": "115 mph",
            "confidence": 0.88,
            "reference": "Page 1, line 7",
        },
        {
            "question": "Risk Category",
            "answer": "II",
            "confidence": 0.90,
            "reference": "Page 1, line 8",
        },
        {
            "question": "Ground Snow Load (Pg)",
            "answer": "30 psf",
            "confidence": 0.85,
            "reference": "Page 1, line 13",
        },
    ]


@pytest.fixture
def sample_text_quality_good():
    """Good quality text extraction metadata."""
    return {
        "is_empty": False,
        "garbage_ratio": 0.02,
        "is_scanned": False,
        "has_complex_tables": False,
        "word_count": 150,
        "char_count": 900,
    }


@pytest.fixture
def sample_text_quality_poor():
    """Poor quality text extraction (should trigger fallback)."""
    return {
        "is_empty": False,
        "garbage_ratio": 0.25,
        "is_scanned": True,
        "has_complex_tables": True,
        "word_count": 30,
        "char_count": 180,
    }
