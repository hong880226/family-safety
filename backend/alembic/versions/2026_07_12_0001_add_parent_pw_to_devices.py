"""add parent password verifier columns to devices

Revision ID: 2026_07_12_0001
Revises:
Create Date: 2026-07-12 00:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "2026_07_12_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column("parent_pw_hash", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("parent_pw_salt", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("parent_pw_iterations", sa.Integer(), nullable=True),
    )
    op.add_column(
        "devices",
        sa.Column("parent_pw_synced_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("devices", "parent_pw_synced_at")
    op.drop_column("devices", "parent_pw_iterations")
    op.drop_column("devices", "parent_pw_salt")
    op.drop_column("devices", "parent_pw_hash")
