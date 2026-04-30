# ADR 0036 — 🤍 White Hat · Telemetry of the system itself

> *White Hat: focus on facts, data, information. What do we know? What don't we know?*

## Status
Proposed.

## Context
There are 35 ADRs of design intent and **zero metrics** on whether any of it works. We argue from intuition: "the live overlay is jittery"; "tracking samples drop in long sessions"; "cluster proximity is noisy at the back of the room". Each is plausible and unfalsifiable.

The system itself emits next-to-nothing measurable. uvicorn's access log says the request happened. The DB records what the user did. Neither says how *long* it took, how often it failed, how many of last quarter's tracking sessions ended in a viewable report. We can't tell whether ADR 0004 (smoothing) reduced jitter by 30 % or by 0 % because we never measured baseline jitter.

Without telemetry, every future ADR is also a guess. With telemetry, every claim a future ADR makes becomes testable.

## Decision
Add a system-self-telemetry layer that captures facts about the system, not just about its users.

A new `Metric` table — `(t, kind, name, value, tags_json)` — written from a single `record(name, value, **tags)` helper. Hot-path callers (the WS detection loop, the tracking sample writer) batch-insert.

The starting metric set:

| Metric                              | Where it's recorded                         |
| ----------------------------------- | ------------------------------------------- |
| `detection.latency_ms`              | `ws_detect`, per frame                      |
| `detection.markers_seen`            | `ws_detect`, per frame                      |
| `detection.markers_smoothed_only`   | After ADR 0004 lands; how often the tracker is filling for an absent detection |
| `tracking.sample_writes_per_minute` | `_record_tracking_samples`                  |
| `tracking.session_aborted`          | If a session has zero samples or `stopped_at = NULL` for >24h |
| `cluster.events_per_minute`         | `tracking.compute_report` and live cluster code |
| `ws.upload_buffer_frames`           | `lib/camera.js` reports back over the WS    |
| `ws.bandwidth_mbps`                 | Same                                        |
| `ws.jpeg_quality`                   | Same                                        |
| `db.report_compute_ms`              | `tracking_report` endpoint                  |
| `pdf.markers_render_ms`             | `markers_pdf` endpoint                      |
| `calibration.median_corner_error_m` | After ADR 0012 lands                        |

Two surfaces:

- `GET /api/metrics` — Prometheus-text by default, `?format=json` for the admin UI.
- A "What we know" tab in `/admin` that renders sparklines for the last 30 days and tables for per-camera/per-session aggregates.

Once a quarter, write a **"the data says" memo** — a one-pager that picks three surprising patterns from the telemetry and feeds them into the next round of ADRs.

## Consequences

**Positive:**
- Every claim becomes testable. ADR 0004's smoothing either does measurably reduce jitter, or it doesn't.
- Performance regressions are caught at deploy time, not at workshop time.
- The "What we know" tab gives operators a quiet, honest read of "is the system healthy today?"

**Negative:**
- Modest hot-path overhead — measurement itself has a cost. Mitigation: batched inserts, sampling every Nth frame for high-frequency metrics.
- A `Metric` table grows unbounded without retention. Tied to ADR 0010.

**Risks:**
- Decisions become metrics-driven and miss the qualitative signal — the room felt cold even though every metric was green. Mitigation: pair this with the Red Hat's vibe channel (ADR 0037). Both readings, equally weighted.
- Metric volume drowns the signal. Mitigation: start with the 12 above; add more only when an ADR demands a specific measurement.

## Alternatives considered
- **No telemetry** — current state. Comfortable for solo development, untenable as the system scales beyond one operator.
- **Third-party APM (Datadog, Honeycomb).** Right answer for a multi-tenant SaaS; overkill and privacy-fraught for a self-hosted facilitation tool.
- **Logs only.** Logs answer "did it happen". Metrics answer "how often and how long". Different question.
