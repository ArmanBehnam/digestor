"""
Integration tests: Auth → Protected routes access control.
Tests that unauthenticated requests are rejected and role-based
access control (engineer/supervisor/admin) works correctly.
"""

import uuid
import pytest
from unittest.mock import patch, AsyncMock

from httpx import AsyncClient, ASGITransport
from db.models import User, Project
from sqlalchemy import select


class TestUnauthenticatedAccess:
    """
    Tests that protected endpoints reject requests without valid auth.
    Uses a raw client with NO dependency overrides (no auth mock).
    """

    @pytest.mark.asyncio
    async def test_projects_requires_auth(self, db_session):
        """GET /api/projects should 401/403 without a token."""
        from api.main import app
        from api.dependencies import get_db

        async def override_get_db():
            yield db_session

        # Only override DB — leave auth dependency intact (will require Bearer token)
        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/projects")

        app.dependency_overrides.clear()
        # Without Bearer token, HTTPBearer dependency returns 403
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_tickets_requires_auth(self, db_session):
        from api.main import app
        from api.dependencies import get_db

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/tickets")

        app.dependency_overrides.clear()
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_auth_me_requires_auth(self, db_session):
        from api.main import app
        from api.dependencies import get_db

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/auth/me")

        app.dependency_overrides.clear()
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_health_is_public(self, db_session):
        """Health check should NOT require auth."""
        from api.main import app
        from api.dependencies import get_db

        async def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")

        app.dependency_overrides.clear()
        assert resp.status_code == 200


class TestRoleBasedAccessControl:
    """Tests that supervisor/admin-only endpoints enforce role restrictions."""

    @pytest.mark.asyncio
    async def test_engineer_cannot_approve_project(self, app_client, db_session, mock_user_claims):
        """Engineers (non-supervisor) should get 403 on approve-project."""
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        p = Project(name="Needs Approval", owner_id=user.id, status="submitted")
        db_session.add(p)
        await db_session.flush()

        resp = await app_client.post("/api/approve-project", json={
            "project_id": str(p.id),
            "approved": True,
        })
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_supervisor_can_approve_project(self, supervisor_client, db_session, mock_supervisor_claims):
        supervisor = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_supervisor_claims["sub"])
        )).scalar_one()

        p = Project(name="Approve This", owner_id=supervisor.id, status="submitted")
        db_session.add(p)
        await db_session.flush()

        with patch("api.endpoints.projects.notify_project_decision", new_callable=AsyncMock):
            resp = await supervisor_client.post("/api/approve-project", json={
                "project_id": str(p.id),
                "approved": True,
            })
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    @pytest.mark.asyncio
    async def test_admin_can_approve_project(self, admin_client, db_session, mock_admin_claims):
        admin = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_admin_claims["sub"])
        )).scalar_one()

        p = Project(name="Admin Approve", owner_id=admin.id, status="submitted")
        db_session.add(p)
        await db_session.flush()

        with patch("api.endpoints.projects.notify_project_decision", new_callable=AsyncMock):
            resp = await admin_client.post("/api/approve-project", json={
                "project_id": str(p.id),
                "approved": True,
            })
        assert resp.status_code == 200


class TestProjectSubmissionWorkflow:
    """Tests the full project lifecycle: create → submit → approve/reject."""

    @pytest.mark.asyncio
    async def test_create_submit_approve_lifecycle(
        self, app_client, supervisor_client, db_session,
        mock_user_claims, mock_supervisor_claims,
    ):
        # Step 1: Engineer creates a project
        create_resp = await app_client.post("/api/projects", json={
            "name": "Lifecycle Test",
            "description": "Testing the full workflow",
        })
        assert create_resp.status_code == 200
        project_id = create_resp.json()["id"]

        # Step 2: Engineer submits for review
        with patch("api.endpoints.projects.notify_supervisors_new_submission", new_callable=AsyncMock):
            submit_resp = await app_client.post("/api/submit-project", json={
                "project_id": project_id,
            })
        assert submit_resp.status_code == 200
        assert submit_resp.json()["status"] == "submitted"

        # Step 3: Supervisor approves
        with patch("api.endpoints.projects.notify_project_decision", new_callable=AsyncMock):
            approve_resp = await supervisor_client.post("/api/approve-project", json={
                "project_id": project_id,
                "approved": True,
            })
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "approved"

        # Step 4: Verify final state
        detail_resp = await app_client.get(f"/api/projects/{project_id}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["status"] == "approved"

    @pytest.mark.asyncio
    async def test_create_submit_reject_resubmit_lifecycle(
        self, app_client, supervisor_client, db_session,
        mock_user_claims, mock_supervisor_claims,
    ):
        # Step 1: Create
        create_resp = await app_client.post("/api/projects", json={
            "name": "Reject-Resubmit Test",
        })
        project_id = create_resp.json()["id"]

        # Step 2: Submit
        with patch("api.endpoints.projects.notify_supervisors_new_submission", new_callable=AsyncMock):
            await app_client.post("/api/submit-project", json={
                "project_id": project_id,
            })

        # Step 3: Supervisor rejects
        with patch("api.endpoints.projects.notify_project_decision", new_callable=AsyncMock):
            reject_resp = await supervisor_client.post("/api/approve-project", json={
                "project_id": project_id,
                "approved": False,
                "remarks": "Missing seismic calculations",
            })
        assert reject_resp.json()["status"] == "rejected"

        # Step 4: Engineer re-submits (rejected projects can be resubmitted)
        with patch("api.endpoints.projects.notify_supervisors_new_submission", new_callable=AsyncMock):
            resubmit_resp = await app_client.post("/api/submit-project", json={
                "project_id": project_id,
            })
        assert resubmit_resp.status_code == 200
        assert resubmit_resp.json()["status"] == "submitted"


class TestTicketWorkflow:
    """Tests the ticket lifecycle: create → list → resolve."""

    @pytest.mark.asyncio
    async def test_create_list_resolve_ticket(self, app_client, db_session, mock_user_claims):
        # Step 1: Create a ticket
        with patch("api.endpoints.tickets.notify_new_ticket", new_callable=AsyncMock):
            create_resp = await app_client.post("/api/tickets", json={
                "subject": "Integration Test Bug",
                "description": "Upload button not working on mobile",
                "category": "bug",
                "priority": "high",
            })
        assert create_resp.status_code == 200
        ticket_id = create_resp.json()["id"]

        # Step 2: List tickets — should contain the new ticket
        list_resp = await app_client.get("/api/tickets")
        assert list_resp.status_code == 200
        tickets = list_resp.json()["tickets"]
        assert any(t["id"] == ticket_id for t in tickets)

        # Step 3: Resolve the ticket
        resolve_resp = await app_client.put(f"/api/tickets/{ticket_id}", json={
            "status": "resolved",
            "resolution": "Fixed viewport scaling on mobile",
        })
        assert resolve_resp.status_code == 200

        # Step 4: Filter for resolved
        filtered_resp = await app_client.get("/api/tickets?status=resolved")
        resolved = filtered_resp.json()["tickets"]
        assert any(t["id"] == ticket_id for t in resolved)
