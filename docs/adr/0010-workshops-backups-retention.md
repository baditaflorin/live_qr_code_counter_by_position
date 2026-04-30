# ADR 0010 — Workshop scoping, backups, and retention

## Status
Proposed (depends on ADR 0002 for migrations, ADR 0001 for auth).

## Context
One SQLite file at `/opt/live_qr_wemeshup_com/data/app.db` holds **everything** for **every event ever run** with this server: people, markers, zones, questions, votes, tracking sessions, samples, and the ADR 0009 audit log. Three problems compound:

1. **No backups.** A bad `docker compose down -v`, an SSD failure, or a botched deploy loses the entire history.
2. **Mixed-tenant blob.** Last month's workshop people show up in this month's dropdowns. Reusing a marker id across workshops accidentally cross-attributes data.
3. **Unbounded growth.** Tracking samples grow at ~50 markers × 2 Hz × 3600 s = 360 k rows per session-hour. Audit log grows with operator activity. Nothing is ever pruned.

## Decision
Three coordinated changes.

1. **Backup**: install Litestream in the production container; replicate `app.db` continuously to a Tailscale-attached node and to a second target (S3-compatible bucket on Hetzner Object Storage). Add a `litestream restore` runbook entry to [`deploy/DEPLOY.md`](../../deploy/DEPLOY.md).

2. **Workshop scoping**: introduce a `Workshop` table (`id`, `name`, `slug`, `started_at`, `default_proximity_m`). Every Person / Question / Zone / Vote / TrackingSession / TrackingSample / AuditLog row gets a `workshop_id` FK. The active workshop is selected on `/admin` (cookie-stickied). Existing data is back-filled into a `default` workshop on migration.

3. **Retention**: each Workshop carries `tracking_retention_days` (default 90) and `audit_retention_days` (default 365). A nightly job (`docker compose exec app python -m backend.maintenance prune`) deletes expired rows. Person/Question/Zone data is **never** auto-deleted — only logs and samples.

## Consequences

**Positive:**
- Recoverable from a VM loss within minutes.
- Data isolation: no cross-workshop bleed, deletions are bounded blast-radius.
- Predictable storage growth — `tracking_samples` stops being a slow leak.

**Negative:**
- Migration to add `workshop_id` everywhere is non-trivial (Alembic, ADR 0002, mandatory).
- One more knob in the UI (workshop switcher).

**Risks:**
- Retention prunes are irreversible. Mitigation: requires `confirm=true` and is audit-logged; default schedule emails the operator a "I'm about to delete N rows" preview 24 h before.
- Litestream replicating to S3 means raw position data leaves the host. Consent + agreed retention with the workshop sponsor must precede this; configurable via env (`BACKUP_OFFSITE=false` disables it).

## Alternatives considered
- **Just back up nightly with `sqlite3 .backup`** — works for backup, doesn't solve mixing or growth.
- **One SQLite file per workshop** — operationally messy (which file is "live"? what about cross-workshop reports?).
- **Move to Postgres + per-workshop schemas** — best long-term, but a much bigger change; defer until justified by load.
