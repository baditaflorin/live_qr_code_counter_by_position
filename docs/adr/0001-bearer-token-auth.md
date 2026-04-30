# ADR 0001 — Bearer-token auth for state-mutating routes

## Status
Proposed.

## Context
The app is reachable at <https://live-qr.wemeshup.com> with no authentication. Anyone who guesses or learns the URL can:

- Delete every person, marker, zone, question, and tracking session (`DELETE /api/...`).
- Stop an in-flight tracking session mid-workshop (`PUT /api/tracking/sessions/{id}/stop`).
- Reseed the Czocha deck and wipe the operator's customised zones (`POST /api/questions/seed/czocha-day-1?replace=true`).

The Live page (`/`) and the per-marker phone-share page (`/m/{aruco_id}`) must stay open — phones on conference Wi-Fi need to load them without configuring credentials, and the projection display can't survive an auth prompt mid-exercise.

## Decision
Introduce a single shared secret in env (`APP_TOKEN`).

- All `POST/PUT/PATCH/DELETE` requests under `/api/*` require `Authorization: Bearer <APP_TOKEN>`.
- The HTML routes `/admin` and `/track` require a `live_qr_session` cookie set by a new `/login` form that takes the same token; the cookie is `Secure; HttpOnly; SameSite=Strict`.
- Read-only routes (`GET /`, `GET /m/{id}`, `GET /api/markers/{id}/image`, `GET /api/qr`) stay unauthenticated.
- `/ws/detect` accepts the token via a `?token=` query string at handshake (WebSockets can't carry the `Authorization` header from `getUserMedia` clients reliably).

## Consequences

**Positive:**
- One env var rotates per workshop. No user database, no email, no password recovery.
- Phone share + projection still work without credentials.

**Negative:**
- Single shared secret means every operator is the same identity for ADR 0009's audit log.
- Breaks any external automation that hits the API today (none exists yet, so cost is zero now).

**Risks:**
- Token leak = full takeover. Mitigation: rotate per workshop; pair with ADR 0010's per-workshop scoping so a leak only exposes the active workshop.
- WS query-string token shows up in nginx access logs. Mitigation: drop `Set $request_uri` from the access-log format on `/ws/detect` only.

## Alternatives considered
- **OIDC / OAuth via a third-party** — overkill for a single-operator self-hosted tool.
- **IP allowlist** — breaks for facilitators on cellular and venue Wi-Fi NAT.
- **HTTP Basic auth on nginx** — loses route-level granularity (can't exempt `/m/{id}`).
