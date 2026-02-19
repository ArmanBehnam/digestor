"""
AWS Cognito integration for authentication and user management.
"""

import os
import json
import time
import structlog
import httpx
from typing import Optional
from jose import jwt, JWTError, jwk
from jose.utils import base64url_decode

logger = structlog.get_logger()

# Cognito configuration
COGNITO_REGION = os.getenv("AWS_REGION", "us-east-1")
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "")
COGNITO_APP_CLIENT_ID = os.getenv("COGNITO_APP_CLIENT_ID", "")
COGNITO_ISSUER = f"https://cognito-idp.{COGNITO_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
COGNITO_JWKS_URL = f"{COGNITO_ISSUER}/.well-known/jwks.json"

# Cache for JWKS keys
_jwks_cache: Optional[dict] = None
_jwks_cache_time: float = 0
JWKS_CACHE_TTL = 3600  # 1 hour


async def _get_jwks() -> dict:
    """Fetch and cache Cognito JWKS public keys."""
    global _jwks_cache, _jwks_cache_time

    if _jwks_cache and (time.time() - _jwks_cache_time) < JWKS_CACHE_TTL:
        return _jwks_cache

    async with httpx.AsyncClient() as client:
        response = await client.get(COGNITO_JWKS_URL)
        response.raise_for_status()
        _jwks_cache = response.json()
        _jwks_cache_time = time.time()
        logger.info("cognito_jwks_refreshed", key_count=len(_jwks_cache.get("keys", [])))
        return _jwks_cache


async def verify_cognito_token(token: str) -> dict:
    """
    Verify a Cognito JWT access token and return decoded claims.

    Returns dict with keys: sub, email, cognito:groups, exp, iat, etc.
    """
    # Decode header to get key ID
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise ValueError(f"Invalid token header: {e}")

    kid = unverified_header.get("kid")
    if not kid:
        raise ValueError("Token missing key ID (kid)")

    # Find matching key in JWKS
    jwks = await _get_jwks()
    key = None
    for k in jwks.get("keys", []):
        if k["kid"] == kid:
            key = k
            break

    if not key:
        # Key not found — refresh cache and retry once
        global _jwks_cache_time
        _jwks_cache_time = 0
        jwks = await _get_jwks()
        for k in jwks.get("keys", []):
            if k["kid"] == kid:
                key = k
                break

    if not key:
        raise ValueError(f"Public key not found for kid: {kid}")

    # Verify token
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=COGNITO_APP_CLIENT_ID,
            issuer=COGNITO_ISSUER,
            options={"verify_at_hash": False},
        )
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except JWTError as e:
        raise ValueError(f"Token verification failed: {e}")

    # Validate token_use claim
    token_use = claims.get("token_use")
    if token_use not in ("access", "id"):
        raise ValueError(f"Invalid token_use: {token_use}")

    return claims


# --- Cognito Admin Operations (for user management) ---

import boto3

def _get_cognito_client():
    return boto3.client("cognito-idp", region_name=COGNITO_REGION)


async def admin_create_user(email: str, full_name: str, role: str = "engineer") -> dict:
    """Create a user in Cognito with FORCE_CHANGE_PASSWORD state."""
    client = _get_cognito_client()

    response = client.admin_create_user(
        UserPoolId=COGNITO_USER_POOL_ID,
        Username=email,
        UserAttributes=[
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
            {"Name": "name", "Value": full_name},
            {"Name": "custom:role", "Value": role},
        ],
        MessageAction="SUPPRESS",  # Don't send welcome email yet
    )

    # Add to group
    client.admin_add_user_to_group(
        UserPoolId=COGNITO_USER_POOL_ID,
        Username=email,
        GroupName=role,
    )

    user = response["User"]
    logger.info("cognito_user_created", email=email, role=role, sub=user["Username"])
    return {
        "sub": user["Username"],
        "email": email,
        "status": user["UserStatus"],
    }


async def admin_set_temp_password(email: str, temp_password: str):
    """Set a temporary password for a migrated user."""
    client = _get_cognito_client()
    client.admin_set_user_password(
        UserPoolId=COGNITO_USER_POOL_ID,
        Username=email,
        Password=temp_password,
        Permanent=False,  # Forces password change on first login
    )
    logger.info("cognito_temp_password_set", email=email)
