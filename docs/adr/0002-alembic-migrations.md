# ADR 0002 — Adopt Alembic for schema migrations

## Status
Proposed.

## Context
Schema has changed three times in the same week:
- `Question` gained `block`, `formation`, `position`.
- `Zone` gained `formation`, then `locked`.
- New tables `tracking_sessions`, `tracking_samples` were added.

Each change is currently applied by the hand-rolled `_migrate_questions()` helper in [`backend/db.py`](../../backend/db.py), which does `PRAGMA table_info(...)` followed by `ALTER TABLE ... ADD COLUMN ...`. This works for additive columns on SQLite, but breaks the moment we need to:

- Rename a column (SQLite needs a table copy + rename).
- Drop a column (same; only supported in modern SQLite with `ALTER TABLE ... DROP COLUMN`).
- Change a type or a default.
- Add or drop an index.
- Backfill data alongside a structural change.

The schema is going to keep evolving (ADR 0005 adds `cameras`, ADR 0009 adds `audit_log`, ADR 0010 adds `workshops`) so the cost of fixing this grows monotonically.

## Decision
Add Alembic.

- Generate an initial revision that captures the *current* prod schema verbatim.
- Container startup runs `alembic upgrade head` instead of `init_db()`.
- `_migrate_questions()` is deleted — its logic becomes a single migration with `batch_op.add_column(...)`.
- For prod databases that already have the migrated columns, the bootstrap script does `alembic stamp <rev-of-current-state>` once, then future `upgrade head` runs are no-ops until the next migration.

## Consequences

**Positive:**
- Real history: every schema change is a tracked, reversible Python file.
- SQLite-friendly today; swappable to Postgres tomorrow without code change.
- `alembic downgrade -1` is a first-class rollback.

**Negative:**
- One more dependency.
- `Base.metadata.create_all()` + autogenerate can produce noisy diffs that need pruning.

**Risks:**
- Stamping the existing prod DB to the right revision must happen exactly once. Mitigation: a `migrate.sh` script that detects "no alembic_version table + tables already exist" and stamps before upgrading.

## Alternatives considered
- **SQLModel auto-migrations** — lossy, not production-grade.
- **Continue hand-rolled migrations** — debt accelerates; rename or backfill needs ad-hoc SQL.
- **`atlasgo` schema-as-source** — requires an external CLI in the deploy path.
