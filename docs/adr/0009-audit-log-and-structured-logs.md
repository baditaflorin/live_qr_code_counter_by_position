# ADR 0009 — Audit log + structured request logs

## Status
Proposed (depends on ADR 0001 for actor identity).

## Context
The container's logs today are uvicorn's defaults:

```
INFO: 192.168.65.1:36095 - "GET /api/system HTTP/1.1" 200 OK
```

Useful for "is the server up". Useless for:

- "Who deleted question 17 during the workshop, and when?"
- "Why did the active question switch mid-exercise?"
- "Were there double-active tracking sessions briefly?"
- "Why is the DB much bigger than expected — did someone reseed?"

State-mutating actions (`DELETE`, `PUT`, `PATCH`, `POST` for non-GETs) leave no record beyond the row's `created_at`/`updated_at` if it has one. After-incident review requires guessing.

## Decision
Two changes, applied together.

1. Switch the app to `structlog` with JSON output. Every log line gains `request_id` (assigned in middleware, returned as `X-Request-Id`), `actor_token_hash` (last 8 chars of SHA-256 of the bearer token from ADR 0001), `route`, `method`, `status`, and `duration_ms`.
2. New `audit_log` table. A FastAPI middleware writes one row for every successful `POST/PUT/PATCH/DELETE` under `/api/*`:
   - `t`, `actor_token_hash`, `method`, `path`, `query`, `body_summary` (first 1 KB of redacted JSON), `status_code`, `request_id`.
   - `GET /api/audit?since=...&actor=...&path=...` returns paginated rows, locked behind the same auth.

## Consequences

**Positive:**
- Forensic answers: "who did what, when, from which token".
- Structured logs ship to any aggregator (Loki, Datadog, plain `jq` over a file).
- `request_id` correlates a user-facing error with the exact log line that produced it.

**Negative:**
- Audit table grows; pair with ADR 0010 retention (default 365 days for audit, longer than tracking samples).
- Middleware adds a small overhead per request (one row write).

**Risks:**
- Sensitive bodies (full marker lists, person names) ending up in the audit. Mitigation: `body_summary` redacts known PII fields by name; configurable allowlist.
- Audit-log write failure shouldn't block the request. Mitigation: write best-effort, log to stderr if the audit DB is wedged.

## Alternatives considered
- **Postgres `pg_audit` extension** — overkill for SQLite; back-burner for if/when we move to Postgres.
- **External logging service only (no audit table)** — fine for ops, but the operator can't view it from the admin UI.
- **Trigger-based DB audit** — SQLite triggers are clunky and lose application context (token, request id).
