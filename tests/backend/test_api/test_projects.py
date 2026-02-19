"""
Tests for project CRUD and approval workflow endpoints.
"""

import uuid
import pytest
from unittest.mock import patch, AsyncMock

from db.models import Project, User
from sqlalchemy import select


class TestListProjects:
    """GET /api/projects"""

    @pytest.mark.asyncio
    async def test_list_empty(self, app_client):
        resp = await app_client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert data["projects"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_with_projects(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        p = Project(name="Test Project", owner_id=user.id, status="draft")
        db_session.add(p)
        await db_session.flush()

        resp = await app_client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["projects"][0]["name"] == "Test Project"

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        db_session.add(Project(name="Draft", owner_id=user.id, status="draft"))
        db_session.add(Project(name="Completed", owner_id=user.id, status="completed"))
        await db_session.flush()

        resp = await app_client.get("/api/projects?status=completed")
        data = resp.json()
        assert data["total"] == 1
        assert data["projects"][0]["name"] == "Completed"


class TestCreateProject:
    """POST /api/projects"""

    @pytest.mark.asyncio
    async def test_create_project(self, app_client):
        resp = await app_client.post("/api/projects", json={
            "name": "New Project",
            "description": "A test project",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Project"
        assert data["status"] == "draft"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_project_minimal(self, app_client):
        resp = await app_client.post("/api/projects", json={"name": "Minimal"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Minimal"


class TestGetProject:
    """GET /api/projects/{project_id}"""

    @pytest.mark.asyncio
    async def test_get_existing_project(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        p = Project(name="Detail Project", owner_id=user.id, status="draft")
        db_session.add(p)
        await db_session.flush()

        resp = await app_client.get(f"/api/projects/{p.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Detail Project"
        assert "documents" in data

    @pytest.mark.asyncio
    async def test_get_nonexistent_project(self, app_client):
        fake_id = str(uuid.uuid4())
        resp = await app_client.get(f"/api/projects/{fake_id}")
        assert resp.status_code == 404


class TestUpdateProject:
    """PUT /api/projects/{project_id}"""

    @pytest.mark.asyncio
    async def test_update_project_name(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        p = Project(name="Old Name", owner_id=user.id, status="draft")
        db_session.add(p)
        await db_session.flush()

        resp = await app_client.put(f"/api/projects/{p.id}", json={"name": "New Name"})
        assert resp.status_code == 200
        assert "updated" in resp.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_update_nonexistent_project(self, app_client):
        fake_id = str(uuid.uuid4())
        resp = await app_client.put(f"/api/projects/{fake_id}", json={"name": "X"})
        assert resp.status_code == 404


class TestSubmitProject:
    """POST /api/submit-project"""

    @pytest.mark.asyncio
    async def test_submit_draft_project(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        p = Project(name="Submit Me", owner_id=user.id, status="draft")
        db_session.add(p)
        await db_session.flush()

        with patch("api.endpoints.projects.notify_supervisors_new_submission", new_callable=AsyncMock):
            resp = await app_client.post("/api/submit-project", json={
                "project_id": str(p.id),
            })

        assert resp.status_code == 200
        assert resp.json()["status"] == "submitted"

    @pytest.mark.asyncio
    async def test_cannot_submit_already_submitted(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        p = Project(name="Already Submitted", owner_id=user.id, status="submitted")
        db_session.add(p)
        await db_session.flush()

        resp = await app_client.post("/api/submit-project", json={
            "project_id": str(p.id),
        })
        assert resp.status_code == 400


class TestApproveProject:
    """POST /api/approve-project"""

    @pytest.mark.asyncio
    async def test_supervisor_can_approve(self, supervisor_client, db_session, mock_supervisor_claims):
        supervisor = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_supervisor_claims["sub"])
        )).scalar_one()

        p = Project(name="Approve Me", owner_id=supervisor.id, status="submitted")
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
    async def test_engineer_cannot_approve(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        p = Project(name="No Approve", owner_id=user.id, status="submitted")
        db_session.add(p)
        await db_session.flush()

        resp = await app_client.post("/api/approve-project", json={
            "project_id": str(p.id),
            "approved": True,
        })
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_reject_with_remarks(self, supervisor_client, db_session, mock_supervisor_claims):
        supervisor = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_supervisor_claims["sub"])
        )).scalar_one()

        p = Project(name="Reject Me", owner_id=supervisor.id, status="submitted")
        db_session.add(p)
        await db_session.flush()

        with patch("api.endpoints.projects.notify_project_decision", new_callable=AsyncMock):
            resp = await supervisor_client.post("/api/approve-project", json={
                "project_id": str(p.id),
                "approved": False,
                "remarks": "Needs more detail",
            })

        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"
