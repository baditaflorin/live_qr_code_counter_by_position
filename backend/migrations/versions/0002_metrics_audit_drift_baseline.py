"""Add metrics + audit_log tables and Camera.anchor_baseline_px_json column.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-01

ADRs 0009 (audit log), 0036 (telemetry), 0015 (anchor drift baseline).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = set(insp.get_table_names())

    if "metrics" not in existing:
        op.create_table(
            "metrics",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("t", sa.DateTime(), nullable=False, index=True),
            sa.Column("name", sa.String(length=80), nullable=False, index=True),
            sa.Column("value", sa.Float(), nullable=False),
            sa.Column("tags_json", sa.Text(), nullable=True),
        )

    if "audit_log" not in existing:
        op.create_table(
            "audit_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("t", sa.DateTime(), nullable=False, index=True),
            sa.Column("actor_token_hash", sa.String(length=16), nullable=True, index=True),
            sa.Column("method", sa.String(length=10), nullable=False),
            sa.Column("path", sa.String(length=400), nullable=False, index=True),
            sa.Column("query", sa.String(length=800), nullable=True),
            sa.Column("status_code", sa.Integer(), nullable=False),
            sa.Column("request_id", sa.String(length=36), nullable=True),
            sa.Column("body_summary", sa.Text(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
        )

    # Camera.anchor_baseline_px_json — additive, only if missing.
    if "cameras" in existing:
        cols = {c["name"] for c in insp.get_columns("cameras")}
        if "anchor_baseline_px_json" not in cols:
            with op.batch_alter_table("cameras") as batch:
                batch.add_column(sa.Column("anchor_baseline_px_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_table("metrics")
    op.drop_table("audit_log")
    with op.batch_alter_table("cameras") as batch:
        batch.drop_column("anchor_baseline_px_json")
