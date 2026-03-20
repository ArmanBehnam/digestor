"""
Authentication endpoints - wraps AWS Cognito operations.
Handles registration, login, logout, token refresh, password reset.
"""

import os
import json
import base64
import structlog
import boto3
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db, get_current_user
from db.models import User

logger = structlog.get_logger()
router = APIRouter()

COGNITO_REGION = os.getenv("AWS_REGION", "us-east-1")
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "")
COGNITO_APP_CLIENT_ID = os.getenv("COGNITO_APP_CLIENT_ID", "")


def _cognito_client():
    return boto3.client("cognito-idp", region_name=COGNITO_REGION)


def _decode_id_token_claims(id_token: str) -> dict:
    """Decode ID token payload without verification (already authenticated via access token).
    ID tokens contain email, name, and other user profile claims."""
    try:
        payload = id_token.split(".")[1]
        # Add padding
        payload += "=" * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return {}


# --- Request Models ---

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    organization: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class ConfirmResetRequest(BaseModel):
    email: EmailStr
    confirmation_code: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    session: str
    new_password: str
    email: str


# --- Endpoints ---

@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user via Cognito and create local profile."""
    client = _cognito_client()

    try:
        # Create user in Cognito
        response = client.sign_up(
            ClientId=COGNITO_APP_CLIENT_ID,
            Username=req.email,
            Password=req.password,
            UserAttributes=[
                {"Name": "email", "Value": req.email},
                {"Name": "name", "Value": req.full_name},
            ],
        )

        cognito_sub = response["UserSub"]

        # Add to default group (engineer)
        client.admin_add_user_to_group(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=req.email,
            GroupName="engineer",
        )

        # Create local user profile
        user = User(
            cognito_sub=cognito_sub,
            email=req.email,
            full_name=req.full_name,
            role="engineer",
            organization=req.organization,
        )
        db.add(user)
        await db.flush()

        logger.info("user_registered", email=req.email, sub=cognito_sub)
        return {
            "message": "Registration successful. Please check your email to verify.",
            "user_sub": cognito_sub,
        }

    except client.exceptions.UsernameExistsException:
        raise HTTPException(status_code=409, detail="Email already registered")
    except client.exceptions.InvalidPasswordException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("registration_failed", email=req.email, error=str(e))
        raise HTTPException(status_code=500, detail="Registration failed")


@router.post("/login")
async def login(req: LoginRequest):
    """Authenticate user and return Cognito tokens."""
    client = _cognito_client()

    try:
        response = client.initiate_auth(
            ClientId=COGNITO_APP_CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": req.email,
                "PASSWORD": req.password,
            },
        )

        # Handle NEW_PASSWORD_REQUIRED challenge (migrated users)
        if response.get("ChallengeName") == "NEW_PASSWORD_REQUIRED":
            return {
                "challenge": "NEW_PASSWORD_REQUIRED",
                "session": response["Session"],
                "message": "Please set a new password",
            }

        auth_result = response["AuthenticationResult"]
        return {
            "access_token": auth_result["AccessToken"],
            "id_token": auth_result["IdToken"],
            "refresh_token": auth_result["RefreshToken"],
            "expires_in": auth_result["ExpiresIn"],
            "token_type": "Bearer",
        }

    except client.exceptions.NotAuthorizedException:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    except client.exceptions.UserNotConfirmedException:
        raise HTTPException(status_code=403, detail="Email not verified")
    except Exception as e:
        logger.error("login_failed", email=req.email, error=str(e))
        raise HTTPException(status_code=500, detail="Login failed")


@router.post("/respond-challenge")
async def respond_to_challenge(req: ChangePasswordRequest):
    """Handle NEW_PASSWORD_REQUIRED challenge for migrated users."""
    client = _cognito_client()

    try:
        response = client.respond_to_auth_challenge(
            ClientId=COGNITO_APP_CLIENT_ID,
            ChallengeName="NEW_PASSWORD_REQUIRED",
            Session=req.session,
            ChallengeResponses={
                "USERNAME": req.email,
                "NEW_PASSWORD": req.new_password,
            },
        )

        auth_result = response["AuthenticationResult"]
        return {
            "access_token": auth_result["AccessToken"],
            "id_token": auth_result["IdToken"],
            "refresh_token": auth_result["RefreshToken"],
            "expires_in": auth_result["ExpiresIn"],
            "token_type": "Bearer",
        }
    except Exception as e:
        logger.error("challenge_response_failed", error=str(e))
        raise HTTPException(status_code=400, detail="Password change failed")


@router.post("/refresh")
async def refresh_token(req: RefreshRequest):
    """Refresh access token using refresh token."""
    client = _cognito_client()

    try:
        response = client.initiate_auth(
            ClientId=COGNITO_APP_CLIENT_ID,
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={"REFRESH_TOKEN": req.refresh_token},
        )

        auth_result = response["AuthenticationResult"]
        return {
            "access_token": auth_result["AccessToken"],
            "id_token": auth_result["IdToken"],
            "expires_in": auth_result["ExpiresIn"],
            "token_type": "Bearer",
        }
    except Exception as e:
        logger.error("token_refresh_failed", error=str(e))
        raise HTTPException(status_code=401, detail="Token refresh failed")


@router.post("/reset-password")
async def reset_password(req: PasswordResetRequest):
    """Initiate password reset flow (sends code via email)."""
    client = _cognito_client()

    try:
        client.forgot_password(
            ClientId=COGNITO_APP_CLIENT_ID,
            Username=req.email,
        )
        return {"message": "Password reset code sent to your email"}
    except client.exceptions.UserNotFoundException:
        # Don't reveal if email exists
        return {"message": "If the email is registered, a reset code has been sent"}
    except Exception as e:
        logger.error("password_reset_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Password reset failed")


@router.post("/confirm-reset")
async def confirm_reset(req: ConfirmResetRequest):
    """Confirm password reset with code."""
    client = _cognito_client()

    try:
        client.confirm_forgot_password(
            ClientId=COGNITO_APP_CLIENT_ID,
            Username=req.email,
            ConfirmationCode=req.confirmation_code,
            Password=req.new_password,
        )
        return {"message": "Password reset successful. You can now log in."}
    except client.exceptions.CodeMismatchException:
        raise HTTPException(status_code=400, detail="Invalid confirmation code")
    except Exception as e:
        logger.error("confirm_reset_failed", error=str(e))
        raise HTTPException(status_code=500, detail="Password reset confirmation failed")


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """Sign out user (invalidate tokens server-side)."""
    client = _cognito_client()

    try:
        client.admin_user_global_sign_out(
            UserPoolId=COGNITO_USER_POOL_ID,
            Username=current_user.get("username", current_user.get("sub")),
        )
        return {"message": "Logged out successfully"}
    except Exception as e:
        logger.error("logout_failed", error=str(e))
        return {"message": "Logged out (client-side)"}


@router.get("/me")
async def get_current_user_profile(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's profile. Auto-provisions local record if missing."""
    from sqlalchemy import select

    # Extract user claims from ID token (has email/name; access token does not)
    id_token = request.headers.get("x-id-token", "")
    id_claims = _decode_id_token_claims(id_token) if id_token else {}

    stmt = select(User).where(User.cognito_sub == current_user["sub"])
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    # Repair: if existing user has UUID as name/email, fix from ID token claims
    if user and (user.full_name == user.cognito_sub or user.email == user.cognito_sub):
        repaired = False
        # Try ID token first (reliable, no AWS API call needed)
        if user.email == user.cognito_sub and id_claims.get("email"):
            user.email = id_claims["email"]
            repaired = True
        if user.full_name == user.cognito_sub and id_claims.get("name"):
            user.full_name = id_claims["name"]
            repaired = True
        elif user.full_name == user.cognito_sub and id_claims.get("email"):
            user.full_name = id_claims["email"]
            repaired = True

        # Fall back to Cognito admin API if ID token didn't help
        if not repaired:
            try:
                cognito = _cognito_client()
                cognito_user = cognito.admin_get_user(
                    UserPoolId=COGNITO_USER_POOL_ID,
                    Username=current_user.get("username", current_user["sub"]),
                )
                attrs = {a["Name"]: a["Value"] for a in cognito_user.get("UserAttributes", [])}
                if user.email == user.cognito_sub and attrs.get("email"):
                    user.email = attrs["email"]
                if user.full_name == user.cognito_sub and attrs.get("name"):
                    user.full_name = attrs["name"]
                elif user.full_name == user.cognito_sub and attrs.get("email"):
                    user.full_name = attrs["email"]
            except Exception as e:
                logger.warning("user_repair_failed", sub=current_user["sub"], error=str(e))

        if user.full_name != user.cognito_sub or user.email != user.cognito_sub:
            await db.flush()
            logger.info("user_profile_repaired", email=user.email, full_name=user.full_name)

    if not user:
        # Auto-provision: user exists in Cognito but not in local DB
        # Use ID token claims first (access tokens lack email/name)
        email = id_claims.get("email", "") or current_user.get("email", "")
        full_name = id_claims.get("name", "") or current_user.get("name", "")

        if not email or not full_name:
            try:
                cognito = _cognito_client()
                cognito_user = cognito.admin_get_user(
                    UserPoolId=COGNITO_USER_POOL_ID,
                    Username=current_user.get("username", current_user["sub"]),
                )
                attrs = {a["Name"]: a["Value"] for a in cognito_user.get("UserAttributes", [])}
                email = email or attrs.get("email", current_user.get("username", ""))
                full_name = full_name or attrs.get("name", email)
            except Exception as e:
                logger.warning("cognito_user_lookup_failed", sub=current_user["sub"], error=str(e))
                email = email or current_user.get("username", current_user["sub"])
                full_name = full_name or email

        groups = current_user.get("cognito:groups", [])
        role = "admin" if "admin" in groups else "supervisor" if "supervisor" in groups else "engineer"
        user = User(
            cognito_sub=current_user["sub"],
            email=email,
            full_name=full_name,
            role=role,
        )
        db.add(user)
        await db.flush()
        logger.info("user_auto_provisioned", email=user.email, full_name=user.full_name, sub=current_user["sub"])

    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "organization": user.organization,
        "groups": current_user.get("cognito:groups", []),
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
