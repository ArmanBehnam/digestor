"""Add processing_tier column to document_processing for 3-tier pipeline tracking

Revision ID: 004_processing_tier
Revises: 003_extracted_text
Create Date: 2026-03-07
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "004_processing_tier"
down_revision: Union[str, None] = "003_extracted_text"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("document_processing", sa.Column("processing_tier", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("document_processing", "processing_tier")
