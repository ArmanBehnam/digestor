"""
Tests for authentication endpoints.
Cognito calls are mocked; only the FastAPI layer is tested.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestAuthRegister:
    """POST /api/auth/register"""

    @pytest.mark.asyncio
    async def test_register_success(self, app_client):
        mock_cognito = MagicMock()
        mock_cognito.sign_up.return_value = {"UserSub": "new-sub-123"}
        mock_cognito.admin_add_user_to_group.return_value = {}
        mock_cognito.exceptions = MagicMock()

        with patch("api.endpoints.auth._cognito_client", return_value=mock_cognito):
            resp = await app_client.post("/api/auth/register", json={
                "email": "newuser@test.com",
                "password": "StrongPass1!",
                "full_name": "New User",
                "organization": "TestCorp",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["user_sub"] == "new-sub-123"
        assert "registration successful" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, app_client):
        mock_cognito = MagicMock()
        mock_cognito.exceptions.UsernameExistsException = type("UsernameExistsException", (Exception,), {})
        mock_cognito.sign_up.side_effect = mock_cognito.exceptions.UsernameExistsException("exists")

        with patch("api.endpoints.auth._cognito_client", return_value=mock_cognito):
            resp = await app_client.post("/api/auth/register", json={
                "email": "dup@test.com",
                "password": "StrongPass1!",
                "full_name": "Dup User",
            })

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_register_invalid_password(self, app_client):
        mock_cognito = MagicMock()
        mock_cognito.exceptions.UsernameExistsException = type("UsernameExistsException", (Exception,), {})
        mock_cognito.exceptions.InvalidPasswordException = type("InvalidPasswordException", (Exception,), {})
        mock_cognito.sign_up.side_effect = mock_cognito.exceptions.InvalidPasswordException("too weak")

        with patch("api.endpoints.auth._cognito_client", return_value=mock_cognito):
            resp = await app_client.post("/api/auth/register", json={
                "email": "weak@test.com",
                "password": "123",
                "full_name": "Weak Pass User",
            })

        assert resp.status_code == 400


class TestAuthLogin:
    """POST /api/auth/login"""

    @pytest.mark.asyncio
    async def test_login_success(self, app_client):
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.return_value = {
            "AuthenticationResult": {
                "AccessToken": "access-tok",
                "IdToken": "id-tok",
                "RefreshToken": "refresh-tok",
                "ExpiresIn": 3600,
            }
        }
        mock_cognito.exceptions = MagicMock()

        with patch("api.endpoints.auth._cognito_client", return_value=mock_cognito):
            resp = await app_client.post("/api/auth/login", json={
                "email": "testuser@digestor.test",
                "password": "GoodPass1!",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "access-tok"
        assert data["token_type"] == "Bearer"
        assert data["expires_in"] == 3600

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, app_client):
        mock_cognito = MagicMock()
        mock_cognito.exceptions.NotAuthorizedException = type("NotAuthorizedException", (Exception,), {})
        mock_cognito.exceptions.UserNotConfirmedException = type("UserNotConfirmedException", (Exception,), {})
        mock_cognito.initiate_auth.side_effect = mock_cognito.exceptions.NotAuthorizedException("bad creds")

        with patch("api.endpoints.auth._cognito_client", return_value=mock_cognito):
            resp = await app_client.post("/api/auth/login", json={
                "email": "testuser@digestor.test",
                "password": "WrongPass!",
            })

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_returns_challenge_for_migrated_user(self, app_client):
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.return_value = {
            "ChallengeName": "NEW_PASSWORD_REQUIRED",
            "Session": "session-tok-123",
        }
        mock_cognito.exceptions = MagicMock()

        with patch("api.endpoints.auth._cognito_client", return_value=mock_cognito):
            resp = await app_client.post("/api/auth/login", json={
                "email": "migrated@test.com",
                "password": "TempPass!",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["challenge"] == "NEW_PASSWORD_REQUIRED"
        assert data["session"] == "session-tok-123"


class TestAuthRefresh:
    """POST /api/auth/refresh"""

    @pytest.mark.asyncio
    async def test_refresh_success(self, app_client):
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.return_value = {
            "AuthenticationResult": {
                "AccessToken": "new-access-tok",
                "IdToken": "new-id-tok",
                "ExpiresIn": 3600,
            }
        }

        with patch("api.endpoints.auth._cognito_client", return_value=mock_cognito):
            resp = await app_client.post("/api/auth/refresh", json={
                "refresh_token": "valid-refresh-token",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "new-access-tok"

    @pytest.mark.asyncio
    async def test_refresh_expired_token(self, app_client):
        mock_cognito = MagicMock()
        mock_cognito.initiate_auth.side_effect = Exception("Token expired")

        with patch("api.endpoints.auth._cognito_client", return_value=mock_cognito):
            resp = await app_client.post("/api/auth/refresh", json={
                "refresh_token": "expired-token",
            })

        assert resp.status_code == 401


class TestAuthMe:
    """GET /api/auth/me"""

    @pytest.mark.asyncio
    async def test_get_current_user_profile(self, app_client):
        resp = await app_client.get("/api/auth/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "testuser@digestor.test"
        assert data["role"] == "engineer"
        assert data["full_name"] == "Test User"
        assert "id" in data


class TestAuthResetPassword:
    """POST /api/auth/reset-password and /api/auth/confirm-reset"""

    @pytest.mark.asyncio
    async def test_reset_password_sends_code(self, app_client):
        mock_cognito = MagicMock()
        mock_cognito.forgot_password.return_value = {}
        mock_cognito.exceptions = MagicMock()

        with patch("api.endpoints.auth._cognito_client", return_value=mock_cognito):
            resp = await app_client.post("/api/auth/reset-password", json={
                "email": "testuser@digestor.test",
            })

        assert resp.status_code == 200
        assert "reset code sent" in resp.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_confirm_reset_success(self, app_client):
        mock_cognito = MagicMock()
        mock_cognito.confirm_forgot_password.return_value = {}
        mock_cognito.exceptions = MagicMock()

        with patch("api.endpoints.auth._cognito_client", return_value=mock_cognito):
            resp = await app_client.post("/api/auth/confirm-reset", json={
                "email": "testuser@digestor.test",
                "confirmation_code": "123456",
                "new_password": "NewStrongPass1!",
            })

        assert resp.status_code == 200
        assert "successful" in resp.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_confirm_reset_invalid_code(self, app_client):
        mock_cognito = MagicMock()
        mock_cognito.exceptions.CodeMismatchException = type("CodeMismatchException", (Exception,), {})
        mock_cognito.confirm_forgot_password.side_effect = mock_cognito.exceptions.CodeMismatchException("bad code")

        with patch("api.endpoints.auth._cognito_client", return_value=mock_cognito):
            resp = await app_client.post("/api/auth/confirm-reset", json={
                "email": "testuser@digestor.test",
                "confirmation_code": "000000",
                "new_password": "NewPass1!",
            })

        assert resp.status_code == 400
