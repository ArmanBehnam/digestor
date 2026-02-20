"""Add extracted_text column to document_processing for combined multi-PDF processing

Revision ID: 003_extracted_text
Revises: 002_review_tables
Create Date: 2026-02-20
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003_extracted_text"
down_revision: Union[str, None] = "002_review_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("document_processing", sa.Column("extracted_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("document_processing", "extracted_text")
