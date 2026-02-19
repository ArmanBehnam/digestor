"""
Tests for the ticket system endpoints.
"""

import uuid
import pytest

from db.models import User, Ticket
from sqlalchemy import select
from unittest.mock import patch, AsyncMock


class TestCreateTicket:
    """POST /api/tickets"""

    @pytest.mark.asyncio
    async def test_create_ticket(self, app_client):
        with patch("api.endpoints.tickets.notify_new_ticket", new_callable=AsyncMock):
            resp = await app_client.post("/api/tickets", json={
                "subject": "Bug Report",
                "description": "The PDF upload fails for large files",
                "category": "bug",
                "priority": "high",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["subject"] == "Bug Report"
        assert data["status"] == "open"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_ticket_minimal(self, app_client):
        with patch("api.endpoints.tickets.notify_new_ticket", new_callable=AsyncMock):
            resp = await app_client.post("/api/tickets", json={
                "subject": "Question",
                "description": "How do I export results?",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "open"

    @pytest.mark.asyncio
    async def test_create_ticket_missing_fields(self, app_client):
        resp = await app_client.post("/api/tickets", json={
            "subject": "Missing description",
        })
        assert resp.status_code == 422  # Pydantic validation


class TestListTickets:
    """GET /api/tickets"""

    @pytest.mark.asyncio
    async def test_list_empty(self, app_client):
        resp = await app_client.get("/api/tickets")
        assert resp.status_code == 200
        assert resp.json()["tickets"] == []

    @pytest.mark.asyncio
    async def test_list_own_tickets(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        db_session.add(Ticket(
            user_id=user.id,
            subject="My Ticket",
            description="Test",
            status="open",
        ))
        await db_session.flush()

        resp = await app_client.get("/api/tickets")
        data = resp.json()
        assert len(data["tickets"]) == 1
        assert data["tickets"][0]["subject"] == "My Ticket"

    @pytest.mark.asyncio
    async def test_filter_by_status(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        db_session.add(Ticket(user_id=user.id, subject="Open", description="t", status="open"))
        db_session.add(Ticket(user_id=user.id, subject="Resolved", description="t", status="resolved"))
        await db_session.flush()

        resp = await app_client.get("/api/tickets?status=resolved")
        data = resp.json()
        assert len(data["tickets"]) == 1
        assert data["tickets"][0]["subject"] == "Resolved"


class TestUpdateTicket:
    """PUT /api/tickets/{ticket_id}"""

    @pytest.mark.asyncio
    async def test_update_ticket_status(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        t = Ticket(user_id=user.id, subject="Update Me", description="test", status="open")
        db_session.add(t)
        await db_session.flush()

        resp = await app_client.put(f"/api/tickets/{t.id}", json={
            "status": "resolved",
            "resolution": "Fixed in v2.0.1",
        })
        assert resp.status_code == 200
        assert "updated" in resp.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_update_nonexistent_ticket(self, app_client):
        fake_id = str(uuid.uuid4())
        resp = await app_client.put(f"/api/tickets/{fake_id}", json={"status": "closed"})
        assert resp.status_code == 404
