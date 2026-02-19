"""
Integration tests: Upload → Process → Results end-to-end flow.
Tests the complete document lifecycle with mocked S3 and LLM calls.
"""

import io
import uuid
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from db.models import User, Project, DocumentProcessing
from sqlalchemy import select


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

SAMPLE_PDFJS_ANSWERS = [
    {"question_key": "building_code", "question": "Building Code", "answer": "IBC 2021", "confidence": 0.95},
    {"question_key": "asce_reference", "question": "ASCE Reference", "answer": "ASCE 7-22", "confidence": 0.92},
    {"question_key": "wind_speed", "question": "Wind Speed (Vult)", "answer": "115 mph", "confidence": 0.88},
    {"question_key": "risk_category", "question": "Risk Category", "answer": "II", "confidence": 0.90},
    {"question_key": "snow_load", "question": "Ground Snow Load (Pg)", "answer": "30 psf", "confidence": 0.85},
]

GOOD_TEXT_QUALITY = {
    "is_empty": False,
    "garbage_ratio": 0.02,
    "is_scanned": False,
    "has_complex_tables": False,
    "word_count": 200,
    "char_count": 1200,
}


async def _setup_project_for_upload(db_session, user_claims):
    """Create a user-owned project for upload tests."""
    user = (await db_session.execute(
        select(User).where(User.cognito_sub == user_claims["sub"])
    )).scalar_one()

    p = Project(name="Upload Test Project", owner_id=user.id, status="draft")
    db_session.add(p)
    await db_session.flush()
    return user, p


# ---------------------------------------------------------------------------
# Upload tests
# ---------------------------------------------------------------------------


class TestUploadFlow:
    """POST /api/upload-document"""

    @pytest.mark.asyncio
    async def test_upload_pdf_success(self, app_client, db_session, mock_user_claims):
        user, project = await _setup_project_for_upload(db_session, mock_user_claims)

        # Mock S3 upload
        with patch("api.endpoints.upload.upload_file_to_s3", new_callable=AsyncMock):
            resp = await app_client.post(
                "/api/upload-document",
                data={"project_id": str(project.id)},
                files={"file": ("report.pdf", b"%PDF-1.4 test content", "application/pdf")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["file_name"] == "report.pdf"
        assert data["status"] == "uploading"
        assert data["file_size"] > 0
        assert "id" in data

    @pytest.mark.asyncio
    async def test_upload_rejected_for_unsupported_type(self, app_client, db_session, mock_user_claims):
        _, project = await _setup_project_for_upload(db_session, mock_user_claims)

        resp = await app_client.post(
            "/api/upload-document",
            data={"project_id": str(project.id)},
            files={"file": ("image.png", b"PNG fake", "image/png")},
        )
        assert resp.status_code == 400
        assert "unsupported" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_upload_rejected_for_empty_file(self, app_client, db_session, mock_user_claims):
        _, project = await _setup_project_for_upload(db_session, mock_user_claims)

        resp = await app_client.post(
            "/api/upload-document",
            data={"project_id": str(project.id)},
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_upload_rejected_for_nonexistent_project(self, app_client):
        fake_id = str(uuid.uuid4())

        resp = await app_client.post(
            "/api/upload-document",
            data={"project_id": fake_id},
            files={"file": ("report.pdf", b"%PDF-1.4 content", "application/pdf")},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Full flow: Upload → Process (PDF.js) → Results
# ---------------------------------------------------------------------------


class TestPDFjsProcessingFlow:
    """End-to-end: upload, process via PDF.js fast path, retrieve results."""

    @pytest.mark.asyncio
    async def test_upload_then_pdfjs_process_then_get_results(
        self, app_client, db_session, mock_user_claims
    ):
        user, project = await _setup_project_for_upload(db_session, mock_user_claims)

        # Step 1: Upload
        with patch("api.endpoints.upload.upload_file_to_s3", new_callable=AsyncMock):
            upload_resp = await app_client.post(
                "/api/upload-document",
                data={"project_id": str(project.id)},
                files={"file": ("report.pdf", b"%PDF-1.4 test content", "application/pdf")},
            )
        assert upload_resp.status_code == 200
        doc_id = upload_resp.json()["id"]

        # Step 2: Process via PDF.js fast path
        with patch(
            "api.endpoints.process_pdfjs.run_pdfjs_processing",
            new_callable=AsyncMock,
            return_value=(SAMPLE_PDFJS_ANSWERS, GOOD_TEXT_QUALITY),
        ):
            process_resp = await app_client.post("/api/process-document", json={
                "document_id": doc_id,
                "extracted_text": "STRUCTURAL ENGINEERING REPORT\nBuilding Code: IBC 2021\n...",
                "processing_mode": "auto",
                "page_count": 5,
            })

        assert process_resp.status_code == 200
        pdata = process_resp.json()
        assert pdata["processing_path"] == "pdfjs"
        assert len(pdata["results"]) == 5
        assert pdata["confidence_avg"] > 0.80
        assert pdata["message"] == "Processing complete"

        # Step 3: Retrieve results
        results_resp = await app_client.get(f"/api/results/{doc_id}")
        assert results_resp.status_code == 200
        rdata = results_resp.json()
        assert rdata["status"] == "completed"
        assert rdata["processing_path"] == "pdfjs"
        assert len(rdata["results"]) == 5

    @pytest.mark.asyncio
    async def test_quick_mode_skips_fallback(
        self, app_client, db_session, mock_user_claims
    ):
        """Quick mode should use PDF.js results even if quality is borderline."""
        user, project = await _setup_project_for_upload(db_session, mock_user_claims)

        # Upload
        with patch("api.endpoints.upload.upload_file_to_s3", new_callable=AsyncMock):
            upload_resp = await app_client.post(
                "/api/upload-document",
                data={"project_id": str(project.id)},
                files={"file": ("report.pdf", b"%PDF-1.4 content", "application/pdf")},
            )
        doc_id = upload_resp.json()["id"]

        # Process in quick mode — FallbackDetector is never called
        borderline_answers = [
            {"question_key": "building_code", "answer": "IBC 2021", "confidence": 0.65},
        ]
        with patch(
            "api.endpoints.process_pdfjs.run_pdfjs_processing",
            new_callable=AsyncMock,
            return_value=(borderline_answers, GOOD_TEXT_QUALITY),
        ):
            resp = await app_client.post("/api/process-document", json={
                "document_id": doc_id,
                "extracted_text": "Some text here...",
                "processing_mode": "quick",
            })

        assert resp.status_code == 200
        assert resp.json()["processing_path"] == "pdfjs"
        # In quick mode, fallback should NOT happen even with low confidence
        assert resp.json()["message"] == "Processing complete"


# ---------------------------------------------------------------------------
# AWS fallback flow
# ---------------------------------------------------------------------------


class TestAWSFallbackFlow:
    """Tests the auto-fallback path from PDF.js to AWS pipeline."""

    @pytest.mark.asyncio
    async def test_auto_fallback_on_poor_quality(
        self, app_client, db_session, mock_user_claims
    ):
        """Auto mode: if PDF.js results are poor, should enqueue AWS processing."""
        user, project = await _setup_project_for_upload(db_session, mock_user_claims)

        with patch("api.endpoints.upload.upload_file_to_s3", new_callable=AsyncMock):
            upload_resp = await app_client.post(
                "/api/upload-document",
                data={"project_id": str(project.id)},
                files={"file": ("scan.pdf", b"%PDF-1.4 scanned", "application/pdf")},
            )
        doc_id = upload_resp.json()["id"]

        # Mock PDF.js returning empty results (will trigger fallback)
        poor_quality = {
            "is_empty": False, "garbage_ratio": 0.30,
            "is_scanned": True, "has_complex_tables": False,
            "word_count": 20, "char_count": 100,
        }

        mock_job = MagicMock()
        mock_job.id = "rq-job-123"
        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = mock_job

        with patch(
            "api.endpoints.process_pdfjs.run_pdfjs_processing",
            new_callable=AsyncMock,
            return_value=([], poor_quality),
        ), patch(
            "api.endpoints.process_aws._get_rq_queue",
            return_value=mock_queue,
        ):
            resp = await app_client.post("/api/process-document", json={
                "document_id": doc_id,
                "extracted_text": "~ˆ garbled text ∂∑∫",
                "processing_mode": "auto",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["processing_path"] == "aws"
        assert "fallback_reason" in data

    @pytest.mark.asyncio
    async def test_deep_mode_goes_directly_to_aws(
        self, app_client, db_session, mock_user_claims
    ):
        """Deep mode should skip PDF.js entirely and enqueue AWS."""
        user, project = await _setup_project_for_upload(db_session, mock_user_claims)

        with patch("api.endpoints.upload.upload_file_to_s3", new_callable=AsyncMock):
            upload_resp = await app_client.post(
                "/api/upload-document",
                data={"project_id": str(project.id)},
                files={"file": ("complex.pdf", b"%PDF-1.4 complex", "application/pdf")},
            )
        doc_id = upload_resp.json()["id"]

        mock_job = MagicMock()
        mock_job.id = "rq-deep-456"
        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = mock_job

        with patch(
            "api.endpoints.process_aws._get_rq_queue",
            return_value=mock_queue,
        ):
            resp = await app_client.post("/api/process-document", json={
                "document_id": doc_id,
                "processing_mode": "deep",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["processing_path"] == "aws"
        assert data["job_id"] == "rq-deep-456"
        assert data["message"] == "Deep analysis queued"

    @pytest.mark.asyncio
    async def test_no_extracted_text_auto_falls_to_aws(
        self, app_client, db_session, mock_user_claims
    ):
        """Auto mode with no extracted_text (image PDF) → AWS."""
        user, project = await _setup_project_for_upload(db_session, mock_user_claims)

        with patch("api.endpoints.upload.upload_file_to_s3", new_callable=AsyncMock):
            upload_resp = await app_client.post(
                "/api/upload-document",
                data={"project_id": str(project.id)},
                files={"file": ("image.pdf", b"%PDF-1.4 image", "application/pdf")},
            )
        doc_id = upload_resp.json()["id"]

        mock_job = MagicMock()
        mock_job.id = "rq-notext-789"
        mock_queue = MagicMock()
        mock_queue.enqueue.return_value = mock_job

        with patch(
            "api.endpoints.process_aws._get_rq_queue",
            return_value=mock_queue,
        ):
            resp = await app_client.post("/api/process-document", json={
                "document_id": doc_id,
                # No extracted_text — simulates scanned PDF
                "processing_mode": "auto",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["processing_path"] == "aws"


# ---------------------------------------------------------------------------
# Full flow: Upload → Process → Feedback → Update result
# ---------------------------------------------------------------------------


class TestResultsFeedbackFlow:
    """End-to-end: process, then provide feedback and inline edits."""

    @pytest.mark.asyncio
    async def test_process_then_feedback_then_edit(
        self, app_client, db_session, mock_user_claims
    ):
        user, project = await _setup_project_for_upload(db_session, mock_user_claims)

        # Upload
        with patch("api.endpoints.upload.upload_file_to_s3", new_callable=AsyncMock):
            upload_resp = await app_client.post(
                "/api/upload-document",
                data={"project_id": str(project.id)},
                files={"file": ("report.pdf", b"%PDF-1.4 test", "application/pdf")},
            )
        doc_id = upload_resp.json()["id"]

        # Process
        with patch(
            "api.endpoints.process_pdfjs.run_pdfjs_processing",
            new_callable=AsyncMock,
            return_value=(SAMPLE_PDFJS_ANSWERS, GOOD_TEXT_QUALITY),
        ):
            await app_client.post("/api/process-document", json={
                "document_id": doc_id,
                "extracted_text": "STRUCTURAL ENGINEERING REPORT...",
                "processing_mode": "auto",
            })

        # Feedback: thumbs down on wind_speed
        fb_resp = await app_client.post("/api/results/feedback", json={
            "document_id": doc_id,
            "question_key": "wind_speed",
            "feedback_type": "thumbs_down",
            "corrected_value": "120 mph",
            "remarks": "Per 2024 wind map update",
        })
        assert fb_resp.status_code == 200

        # Inline edit: correct the answer
        edit_resp = await app_client.put("/api/results/update", json={
            "document_id": doc_id,
            "question_key": "wind_speed",
            "new_value": "120 mph",
            "remarks": "Corrected per reviewer feedback",
        })
        assert edit_resp.status_code == 200

        # Verify final state
        results_resp = await app_client.get(f"/api/results/{doc_id}")
        rdata = results_resp.json()

        assert rdata["feedback"]["wind_speed"] == "thumbs_down"

        wind_answer = next(
            r for r in rdata["results"] if r["question_key"] == "wind_speed"
        )
        assert wind_answer["answer"] == "120 mph"
        assert wind_answer["edited"] is True
