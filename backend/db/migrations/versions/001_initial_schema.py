"""Initial schema - all tables for Digestor Unified v2.0

Revision ID: 001_initial
Revises: None
Create Date: 2026-02-13
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Users ---
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("cognito_sub", sa.String(128), unique=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="engineer"),
        sa.Column("organization", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_cognito_sub", "users", ["cognito_sub"])

    # --- Projects ---
    op.create_table(
        "projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), server_default=sa.text("1")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_projects_owner_status", "projects", ["owner_id", "status"])

    # --- Document Processing ---
    op.create_table(
        "document_processing",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("file_name", sa.String(512), nullable=False),
        sa.Column("s3_key", sa.String(1024), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="uploading"),
        sa.Column("processing_mode", sa.String(20), nullable=False, server_default="auto"),
        sa.Column("processing_path", sa.String(20), nullable=True),
        sa.Column("job_id", sa.String(255), nullable=True),
        sa.Column("results", JSONB(), nullable=True),
        sa.Column("confidence_avg", sa.Float(), nullable=True),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_docproc_project_status", "document_processing", ["project_id", "status"])
    op.create_index("ix_docproc_job", "document_processing", ["job_id"])

    # --- Document Chunks ---
    op.create_table(
        "document_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("document_processing.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("page_numbers", ARRAY(sa.Integer()), nullable=True),
        sa.Column("embedding", ARRAY(sa.Float()), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_chunks_document", "document_chunks", ["document_id"])
    op.create_unique_constraint("uq_chunk_doc_index", "document_chunks", ["document_id", "chunk_index"])

    # --- User Feedback ---
    op.create_table(
        "user_feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("document_processing.id"), nullable=False),
        sa.Column("question_key", sa.String(100), nullable=False),
        sa.Column("answer_value", sa.Text(), nullable=True),
        sa.Column("feedback_type", sa.String(20), nullable=False),
        sa.Column("corrected_value", sa.Text(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_feedback_document", "user_feedback", ["document_id"])
    op.create_unique_constraint("uq_feedback_user_doc_q", "user_feedback", ["user_id", "document_id", "question_key"])

    # --- Tickets ---
    op.create_table(
        "tickets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("priority", sa.String(20), server_default="medium"),
        sa.Column("status", sa.String(20), server_default="open"),
        sa.Column("assigned_to", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- Analytics Events ---
    op.create_table(
        "analytics_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("event_data", JSONB(), nullable=True),
        sa.Column("document_id", UUID(as_uuid=True), sa.ForeignKey("document_processing.id"), nullable=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("processing_path", sa.String(20), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_analytics_event_type", "analytics_events", ["event_type"])
    op.create_index("ix_analytics_created", "analytics_events", ["created_at"])
    op.create_index("ix_analytics_user", "analytics_events", ["user_id"])


def downgrade() -> None:
    op.drop_table("analytics_events")
    op.drop_table("tickets")
    op.drop_table("user_feedback")
    op.drop_table("document_chunks")
    op.drop_table("document_processing")
    op.drop_table("projects")
    op.drop_table("users")
