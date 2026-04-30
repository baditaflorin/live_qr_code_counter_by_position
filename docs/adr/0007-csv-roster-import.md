# ADR 0007 — CSV roster import + bulk marker assignment

## Status
Proposed.

## Context
The People tab takes one row per HTTP request. For a typical Czocha workshop the roster is **80–120 people** and arrives as a Google Sheets export — one row per attendee, name + sometimes email + sometimes table assignment. Today the operator types each name into the Admin → People form, picks how many markers to attach, clicks Add. That's:

- ~30 minutes of manual entry per workshop.
- Error-prone (typos, double-entries).
- No way to roll back a partial import.

`POST /api/markers/batch` already supports bulk-creating markers per person, but the people themselves still come in one at a time.

## Decision
Add `POST /api/people/import` accepting `multipart/form-data` with a CSV file.

- Required column: `name`.
- Optional columns: `notes`, `marker_count` (defaults to 1), `tags` (semicolon-separated, picked up when ADR 0008-style tagging lands).
- The endpoint runs in a single transaction. By default an existing-name match aborts the import and rolls back; `?on_conflict=skip|merge|create` is configurable.
- Response is a per-row outcome list `[{row, name, status: created|skipped|merged|error, person_id?, marker_ids?, error?}]`.
- Frontend gets a file picker + a dry-run preview table on the People tab. The preview hits `/api/people/import?dry_run=true`.

## Consequences

**Positive:**
- 30-minute setup → 30 seconds plus a 5-second sanity scan.
- Dry-run + transaction means no partial-state messes.
- Roster CSVs become reproducible artefacts of the workshop.

**Negative:**
- New endpoint with non-trivial conflict semantics; needs explicit operator choice.
- Markers allocated for failed rows must be reclaimed cleanly (transaction handles it).

**Risks:**
- Encoding bugs (Google Sheets exports as UTF-8 with BOM; Excel exports as UTF-16 sometimes). Mitigation: detect encoding via `chardet`, normalize on read.
- Privacy: a CSV with names and emails sits in browser memory. Mitigation: stream upload, never persist the raw file server-side.

## Alternatives considered
- **Bulk-JSON endpoint** — same data, worse UX for organisers who live in spreadsheets.
- **Google Sheets API integration** — adds OAuth, fragile to schema changes in the sheet.
- **Manual CLI script** — works for the developer but not for a non-technical workshop assistant.
