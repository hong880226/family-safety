"""add time_windows + device_commands tables

Revision ID: 2026_07_13_0003
Revises: 2026_07_13_0002
Create Date: 2026-07-13 02:00:00

PR-A wires two new tables:

* ``time_windows`` — per-rule weekly schedule (allow / deny / cap_minutes)
* ``device_commands`` — parent-issued remote actions queued for next heartbeat

These tables back the schedule service, the lock-screen/shutdown/reboot web
endpoints, and the LLM toxicity gating.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "2026_07_13_0003"
down_revision: str | Sequence[str] | None = "2026_07_13_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- time_windows ----
    op.create_table(
        "time_windows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "rule_id",
            sa.Integer(),
            sa.ForeignKey("rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("weekday_mask", sa.Integer(), nullable=False, server_default="127"),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("action", sa.String(length=8), nullable=False, server_default="allow"),
        sa.Column("cap_minutes", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_time_windows_rule_id", "time_windows", ["rule_id"])

    # Add ``default_action`` to the rules table for the schedule's fallback.
    op.add_column(
        "rules",
        sa.Column(
            "default_action",
            sa.String(length=8),
            nullable=False,
            server_default="allow",
        ),
    )

    # ---- device_commands ----
    op.create_table(
        "device_commands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "device_id",
            sa.Integer(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "family_id",
            sa.Integer(),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("members.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_device_commands_device_id", "device_commands", ["device_id"])
    op.create_index("ix_device_commands_family_id", "device_commands", ["family_id"])
    op.create_index(
        "ix_device_commands_consumed_at", "device_commands", ["consumed_at"]
    )
    op.create_index("ix_device_commands_created_by", "device_commands", ["created_by"])


def downgrade() -> None:
    op.drop_index("ix_device_commands_created_by", table_name="device_commands")
    op.drop_index("ix_device_commands_consumed_at", table_name="device_commands")
    op.drop_index("ix_device_commands_family_id", table_name="device_commands")
    op.drop_index("ix_device_commands_device_id", table_name="device_commands")
    op.drop_table("device_commands")

    op.drop_column("rules", "default_action")

    op.drop_index("ix_time_windows_rule_id", table_name="time_windows")
    op.drop_table("time_windows")
