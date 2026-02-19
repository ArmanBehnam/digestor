"""
Tests for the health check endpoint.
"""

import pytest


class TestHealthEndpoint:
    """GET /api/health"""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, app_client):
        resp = await app_client.get("/api/health")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_health_response_fields(self, app_client):
        resp = await app_client.get("/api/health")
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["version"] == "2.0.0"
        assert "timestamp" in data
        assert "environment" in data

    @pytest.mark.asyncio
    async def test_health_shows_test_environment(self, app_client):
        resp = await app_client.get("/api/health")
        data = resp.json()
        assert data["environment"] == "test"
