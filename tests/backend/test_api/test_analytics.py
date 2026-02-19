"""
Tests for analytics endpoints.
"""

import pytest
from datetime import datetime, timezone, timedelta

from db.models import User, Project, DocumentProcessing, UserFeedback
from sqlalchemy import select


async def _seed_analytics_data(db_session, user):
    """Seed document processing records and feedback for analytics queries."""
    p = Project(name="Analytics Project", owner_id=user.id, status="completed")
    db_session.add(p)
    await db_session.flush()

    now = datetime.now(timezone.utc)

    # PDF.js processed documents
    for i in range(3):
        doc = DocumentProcessing(
            project_id=p.id,
            file_name=f"pdfjs_{i}.pdf",
            s3_key=f"uploads/pdfjs_{i}.pdf",
            status="completed",
            processing_path="pdfjs",
            confidence_avg=0.90 + (i * 0.02),
            processing_time_ms=800 + (i * 100),
            created_at=now - timedelta(days=i),
        )
        db_session.add(doc)

    # AWS processed documents
    for i in range(2):
        doc = DocumentProcessing(
            project_id=p.id,
            file_name=f"aws_{i}.pdf",
            s3_key=f"uploads/aws_{i}.pdf",
            status="completed",
            processing_path="aws",
            confidence_avg=0.85,
            processing_time_ms=5000 + (i * 500),
            created_at=now - timedelta(days=i),
        )
        db_session.add(doc)

    await db_session.flush()

    # Get one doc for feedback
    result = await db_session.execute(
        select(DocumentProcessing).where(DocumentProcessing.project_id == p.id).limit(1)
    )
    doc = result.scalar_one()

    # Add feedback
    db_session.add(UserFeedback(
        user_id=user.id,
        document_id=doc.id,
        question_key="building_code",
        feedback_type="thumbs_up",
        created_at=now,
    ))
    db_session.add(UserFeedback(
        user_id=user.id,
        document_id=doc.id,
        question_key="wind_speed",
        feedback_type="thumbs_down",
        corrected_value="120 mph",
        created_at=now,
    ))
    await db_session.flush()


class TestAnalyticsOverview:
    """GET /api/analytics/overview"""

    @pytest.mark.asyncio
    async def test_overview_empty_db(self, app_client):
        resp = await app_client.get("/api/analytics/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_documents"] == 0
        assert data["pdfjs_count"] == 0
        assert data["aws_count"] == 0

    @pytest.mark.asyncio
    async def test_overview_with_data(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        await _seed_analytics_data(db_session, user)

        resp = await app_client.get("/api/analytics/overview?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_documents"] == 5
        assert data["pdfjs_count"] == 3
        assert data["aws_count"] == 2
        assert data["avg_confidence"] > 0
        assert data["avg_time_pdfjs_ms"] > 0
        assert data["avg_time_aws_ms"] > 0
        assert data["feedback_thumbs_up"] == 1
        assert data["feedback_thumbs_down"] == 1
        assert data["feedback_accuracy"] == 0.5

    @pytest.mark.asyncio
    async def test_overview_respects_days_param(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        p = Project(name="Old Data", owner_id=user.id, status="completed")
        db_session.add(p)
        await db_session.flush()

        # Add a document from 60 days ago
        old_doc = DocumentProcessing(
            project_id=p.id,
            file_name="old.pdf",
            s3_key="uploads/old.pdf",
            status="completed",
            processing_path="pdfjs",
            confidence_avg=0.80,
            processing_time_ms=900,
            created_at=datetime.now(timezone.utc) - timedelta(days=60),
        )
        db_session.add(old_doc)
        await db_session.flush()

        # With days=30, the old document should not appear
        resp = await app_client.get("/api/analytics/overview?days=30")
        data = resp.json()
        assert data["total_documents"] == 0

        # With days=90, it should appear
        resp2 = await app_client.get("/api/analytics/overview?days=90")
        data2 = resp2.json()
        assert data2["total_documents"] == 1


class TestAnalyticsTrends:
    """GET /api/analytics/trends"""

    @pytest.mark.asyncio
    async def test_trends_empty(self, app_client):
        resp = await app_client.get("/api/analytics/trends")
        assert resp.status_code == 200
        data = resp.json()
        assert data["trends"] == []

    @pytest.mark.asyncio
    async def test_trends_with_data(self, app_client, db_session, mock_user_claims):
        user = (await db_session.execute(
            select(User).where(User.cognito_sub == mock_user_claims["sub"])
        )).scalar_one()

        await _seed_analytics_data(db_session, user)

        resp = await app_client.get("/api/analytics/trends?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["trends"]) > 0
        for entry in data["trends"]:
            assert "date" in entry
            assert "count" in entry
            assert "avg_confidence" in entry
            assert "avg_time_ms" in entry
