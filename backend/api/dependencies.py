"""
Shared FastAPI dependencies for authentication, database sessions, and rate limiting.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from auth.cognito import verify_cognito_token
from db.session import get_async_session

security = HTTPBearer(auto_error=False)


async def get_db() -> AsyncSession:
    """Yield an async database session."""
    async for session in get_async_session():
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Validate Cognito JWT and return user claims."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    try:
        claims = await verify_cognito_token(token)
        return claims
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_with_role(*allowed_roles: str):
    """Factory for role-based access control."""
    async def role_checker(
        current_user: dict = Depends(get_current_user),
    ) -> dict:
        user_groups = current_user.get("cognito:groups", [])
        if not any(role in user_groups for role in allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(allowed_roles)}",
            )
        return current_user
    return role_checker


# Pre-built role dependencies
require_engineer = get_current_user_with_role("engineer", "supervisor", "admin")
require_supervisor = get_current_user_with_role("supervisor", "admin")
require_admin = get_current_user_with_role("admin")
