"""
Role-Based Access Control (RBAC) utilities.
"""

from functools import wraps
from fastapi import HTTPException, status


# Role hierarchy: admin > supervisor > engineer
ROLE_HIERARCHY = {
    "admin": 3,
    "supervisor": 2,
    "engineer": 1,
}


def has_role(user_claims: dict, required_role: str) -> bool:
    """Check if user has the required role or higher."""
    user_groups = user_claims.get("cognito:groups", [])
    required_level = ROLE_HIERARCHY.get(required_role, 0)

    for group in user_groups:
        if ROLE_HIERARCHY.get(group, 0) >= required_level:
            return True
    return False


def require_role(required_role: str):
    """Decorator to enforce role-based access on endpoint handlers."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, current_user: dict = None, **kwargs):
            if current_user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )
            if not has_role(current_user, required_role):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role '{required_role}' or higher required",
                )
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator
