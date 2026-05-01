"""Participant card + event tables (ADR 0021 + 0022 + 0073).

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-01

Lands the participant routing layer: `participant_cards` is the row-per-card
config (kit, action, fire_model, params_json) that ADRs 0021–0030 build on,
and `participant_events` is the audit trail every activation writes (ADR 0021
"every emergent action has a row"). ADR 0073 graduates from env-var-only to
reading orientation buckets out of `participant_cards.params_json`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = set(insp.get_table_names())

    if "participant_cards" not in existing:
        op.create_table(
            "participant_cards",
            sa.Column("aruco_id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=100), nullable=False, server_default=""),
            sa.Column("kit", sa.String(length=40), nullable=False, server_default="reaction", index=True),
            sa.Column("action", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("fire_model", sa.String(length=20), nullable=False, server_default="pulse", index=True),
            sa.Column("params_json", sa.Text(), nullable=True),
            sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        )

    if "participant_events" not in existing:
        op.create_table(
            "participant_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("t", sa.DateTime(), nullable=False, index=True, server_default=sa.func.current_timestamp()),
            sa.Column("marker_aruco_id", sa.Integer(), nullable=False, index=True),
            sa.Column("held_by_aruco_id", sa.Integer(), nullable=True),
            sa.Column("kit", sa.String(length=40), nullable=False, server_default="", index=True),
            sa.Column("action", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("fire_model", sa.String(length=20), nullable=False, server_default="pulse"),
            sa.Column("kind", sa.String(length=40), nullable=False),
            sa.Column("value", sa.String(length=80), nullable=True),
            sa.Column("attribution_confidence", sa.Float(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    op.drop_table("participant_events")
    op.drop_table("participant_cards")
