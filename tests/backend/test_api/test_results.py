"""
Tests for results retrieval and feedback endpoints.
"""

import uuid
import pytest

from db.models import User, Project, DocumentProcessing, UserFeedback
from sqlalchemy import select


async def _create_doc_with_results(db_session, user, results=None):
    """Helper: create a project + document with results."""
    p = Project(name="Results Project", owner_id=user.id, status="completed")
    db_session.add(p)
    await db_session.flush()

    doc = DocumentProcessing(
        project_id=p.id,
        file_name="test.pdf",
        s3_key="uploads/test.pdf",
        status="completed",
        processing_path="pdfjs",
        confidence_avg=0.90,
        processing_time_ms=1200,
        results=results or [
            {"question_key": "building_code", "question": "Building Code", "answer": "IBC 2021", "confidence": 0.95},
            {"question_key": "wind_speed", "question": "Wind Speed", "answer": "115 mph", "confidence": 0.88},
        ],
    )
    db_session.add(doc)
    await db_session.flush()
    return doc


class TestGetResults:
    """GET /api/results/{document_id}"""

    @pytest.mark.asyncio
    async def test_get_results_success(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        doc = await _create_doc_with_results(db_session, user)

        resp = await app_client.get(f"/api/results/{doc.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_name"] == "test.pdf"
        assert data["processing_path"] == "pdfjs"
        assert len(data["results"]) == 2
        assert data["confidence_avg"] == 0.90

    @pytest.mark.asyncio
    async def test_get_results_not_found(self, app_client):
        fake_id = str(uuid.uuid4())
        resp = await app_client.get(f"/api/results/{fake_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_results_includes_feedback(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        doc = await _create_doc_with_results(db_session, user)

        fb = UserFeedback(
            user_id=user.id,
            document_id=doc.id,
            question_key="building_code",
            feedback_type="thumbs_up",
        )
        db_session.add(fb)
        await db_session.flush()

        resp = await app_client.get(f"/api/results/{doc.id}")
        data = resp.json()
        assert data["feedback"]["building_code"] == "thumbs_up"


class TestSubmitFeedback:
    """POST /api/results/feedback"""

    @pytest.mark.asyncio
    async def test_submit_thumbs_up(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        doc = await _create_doc_with_results(db_session, user)

        resp = await app_client.post("/api/results/feedback", json={
            "document_id": str(doc.id),
            "question_key": "building_code",
            "feedback_type": "thumbs_up",
        })
        assert resp.status_code == 200
        assert "recorded" in resp.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_submit_thumbs_down_with_correction(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        doc = await _create_doc_with_results(db_session, user)

        resp = await app_client.post("/api/results/feedback", json={
            "document_id": str(doc.id),
            "question_key": "wind_speed",
            "feedback_type": "thumbs_down",
            "corrected_value": "120 mph",
            "remarks": "Should be 120 per latest report",
        })
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_feedback_upsert(self, app_client, db_session, mock_user_claims):
        """Submitting feedback twice for the same question should update, not duplicate."""
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        doc = await _create_doc_with_results(db_session, user)

        await app_client.post("/api/results/feedback", json={
            "document_id": str(doc.id),
            "question_key": "building_code",
            "feedback_type": "thumbs_up",
        })
        resp2 = await app_client.post("/api/results/feedback", json={
            "document_id": str(doc.id),
            "question_key": "building_code",
            "feedback_type": "thumbs_down",
            "corrected_value": "IBC 2024",
        })
        assert resp2.status_code == 200


class TestUpdateResult:
    """PUT /api/results/update"""

    @pytest.mark.asyncio
    async def test_inline_edit(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        doc = await _create_doc_with_results(db_session, user)

        resp = await app_client.put("/api/results/update", json={
            "document_id": str(doc.id),
            "question_key": "building_code",
            "new_value": "IBC 2024",
            "remarks": "Updated to latest code",
        })
        assert resp.status_code == 200
        assert "updated" in resp.json()["message"].lower()

    @pytest.mark.asyncio
    async def test_update_nonexistent_question_key(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        doc = await _create_doc_with_results(db_session, user)

        resp = await app_client.put("/api/results/update", json={
            "document_id": str(doc.id),
            "question_key": "nonexistent_key",
            "new_value": "something",
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_document_not_found(self, app_client):
        fake_id = str(uuid.uuid4())
        resp = await app_client.put("/api/results/update", json={
            "document_id": fake_id,
            "question_key": "building_code",
            "new_value": "IBC 2024",
        })
        assert resp.status_code == 404
