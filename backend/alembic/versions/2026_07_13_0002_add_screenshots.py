"""add device_screenshots table

Revision ID: 2026_07_13_0002
Revises: 2026_07_12_0001
Create Date: 2026-07-13 00:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "2026_07_13_0002"
down_revision: str | Sequence[str] | None = "2026_07_12_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "device_screenshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "family_id",
            sa.Integer(),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column(
            "taken_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("trigger_type", sa.String(length=16), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("bytes_size", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("sha256_hex", sa.String(length=64), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_device_screenshots_family_id", "device_screenshots", ["family_id"]
    )
    op.create_index(
        "ix_device_screenshots_device_id", "device_screenshots", ["device_id"]
    )
    op.create_index(
        "ix_device_screenshots_taken_at", "device_screenshots", ["taken_at"]
    )
    op.create_index(
        "ix_device_screenshots_sha256_hex", "device_screenshots", ["sha256_hex"]
    )


def downgrade() -> None:
    op.drop_index("ix_device_screenshots_sha256_hex", table_name="device_screenshots")
    op.drop_index("ix_device_screenshots_taken_at", table_name="device_screenshots")
    op.drop_index("ix_device_screenshots_device_id", table_name="device_screenshots")
    op.drop_index("ix_device_screenshots_family_id", table_name="device_screenshots")
    op.drop_table("device_screenshots")
