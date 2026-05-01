"""Baseline — stamp existing prod or create-all on a fresh DB.

Revision ID: 0001
Revises:
Create Date: 2026-05-01

This migration is idempotent: on a fresh database it creates every table
SQLAlchemy currently knows about. On an existing database that already has
the tables (because the app was previously running with the hand-rolled
init_db()), the create_all is a no-op.

Future migrations are real Alembic revisions on top of this baseline.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from backend.db import Base  # late import: app code is on sys.path
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    from backend.db import Base
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind, checkfirst=True)
