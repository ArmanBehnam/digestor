"""
Database session management using async SQLAlchemy + RDS Proxy.
"""

import os
import structlog
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = structlog.get_logger()

# Build database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://digestor:digestor@localhost:5432/digestor_dev",
)

# Ensure we use asyncpg driver
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

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
