"""
Database session management using async SQLAlchemy + RDS Proxy.

Supports two modes:
  1. DATABASE_URL env var (local dev, CI/CD task defs)
  2. RDS_SECRET_ARN + RDS_ENDPOINT + RDS_DB_NAME (Terraform-managed ECS tasks)
     Fetches credentials from AWS Secrets Manager at startup.
"""

import json
import os
import structlog
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = structlog.get_logger()


def _build_database_url() -> str:
    """Build DATABASE_URL, resolving from Secrets Manager if needed."""
    # Priority 1: Explicit DATABASE_URL (from CI/CD inject or local dev)
    url = os.getenv("DATABASE_URL")
    if url and "PLACEHOLDER" not in url:
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    # Priority 2: Resolve from Secrets Manager (Terraform-managed ECS)
    secret_arn = os.getenv("RDS_SECRET_ARN")
    endpoint = os.getenv("RDS_ENDPOINT")
    db_name = os.getenv("RDS_DB_NAME")

    if secret_arn and endpoint and db_name:
        try:
            import boto3
            client = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION", "us-east-1"))
            response = client.get_secret_value(SecretId=secret_arn)
            secret = json.loads(response["SecretString"])
            username = secret.get("username", "digestor")
            password = secret.get("password", "")
            built_url = f"postgresql+asyncpg://{username}:{password}@{endpoint}:5432/{db_name}"
            logger.info("database_url_resolved_from_secrets_manager", endpoint=endpoint, db=db_name)
            return built_url
        except Exception as e:
            logger.error("failed_to_resolve_db_secret", error=str(e))

    # Fallback: local dev default
    return "postgresql+asyncpg://digestor:digestor@localhost:5432/digestor_dev"


DATABASE_URL = _build_database_url()

engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,  # Recycle connections every 30 min (RDS Proxy friendly)
    pool_pre_ping=True,  # Verify connections before use
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session():
    """FastAPI dependency that yields an async session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database connection pool."""
    logger.info("database_pool_initialized", url=DATABASE_URL.split("@")[-1])


async def close_db():
    """Close database connection pool."""
    await engine.dispose()
    logger.info("database_pool_closed")
