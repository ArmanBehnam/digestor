"""Add review workflow tables and project columns

Revision ID: 002_review_tables
Revises: 001_initial
Create Date: 2026-02-19
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "002_review_tables"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Add new columns to projects table ---
    op.add_column("projects", sa.Column("approval_status", sa.String(50), nullable=True))
    op.add_column("projects", sa.Column("files_metadata", JSONB(), nullable=True))
    op.add_column("projects", sa.Column("pending_snapshot_json", JSONB(), nullable=True))
    op.add_column("projects", sa.Column("pending_snapshot_html", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("assigned_supervisor_id", UUID(as_uuid=True), nullable=True))
    op.add_column("projects", sa.Column("review_note", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_projects_assigned_supervisor",
        "projects", "users",
        ["assigned_supervisor_id"], ["id"],
    )

    # --- Project Notes ---
    op.create_table(
        "project_notes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_project_notes_project", "project_notes", ["project_id"])

    # --- Project Remarks ---
    op.create_table(
        "project_remarks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("project_hash", sa.String(255), nullable=False),
        sa.Column("row_id", sa.String(255), nullable=False),
        sa.Column("remark_text", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_by_full_name", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_remarks_project_hash", "project_remarks", ["project_hash"])
    op.create_index("ix_remarks_row", "project_remarks", ["project_hash", "row_id"])

    # --- Result Edits (Audit Trail) ---
    op.create_table(
        "result_edits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("project_hash", sa.String(255), nullable=False),
        sa.Column("row_id", sa.String(255), nullable=False),
        sa.Column("column_name", sa.String(255), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("edited_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("edited_by_full_name", sa.String(255), nullable=True),
        sa.Column("question_id", sa.Integer(), nullable=True),
        sa.Column("question_text", sa.Text(), nullable=True),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_result_edits_project_hash", "result_edits", ["project_hash"])
    op.create_index("ix_result_edits_row", "result_edits", ["project_hash", "row_id"])

    # --- Feedback Surveys ---
    op.create_table(
        "feedback_surveys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("data", JSONB(), nullable=True),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_feedback_surveys_user", "feedback_surveys", ["user_id"])


def downgrade() -> None:
    op.drop_table("feedback_surveys")
    op.drop_table("result_edits")
    op.drop_table("project_remarks")
    op.drop_table("project_notes")
    op.drop_constraint("fk_projects_assigned_supervisor", "projects", type_="foreignkey")
    op.drop_column("projects", "review_note")
    op.drop_column("projects", "assigned_supervisor_id")
    op.drop_column("projects", "pending_snapshot_html")
    op.drop_column("projects", "pending_snapshot_json")
    op.drop_column("projects", "files_metadata")
    op.drop_column("projects", "approval_status")
