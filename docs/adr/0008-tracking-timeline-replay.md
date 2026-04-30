# ADR 0008 — Tracking-session timeline replay

## Status
Proposed.

## Context
`backend/tracking.compute_report` and the `/track` report panel surface aggregates: total contact time per pair, per-person totals, never-met list. None of these answer the post-workshop question that facilitators most often ask:

> When did the conversation between Alice and Bob actually happen, and who else was around?

The raw data already supports this. Every snapshot's positions are in `tracking_samples`, indexed on `(session_id, t)`. The gap is purely UI — there's no way to scrub through time and see what the room looked like.

## Decision
Add a timeline-replay surface.

- Backend: `GET /api/tracking/sessions/{id}/timeline?bucket_ms=500` returns NDJSON, one frame per line: `{"t": "...", "frame": [{"id": int, "x": float, "y": float, "name": str?}, ...]}`. Streaming response so a 1-hour session at 2 Hz (7200 frames) doesn't blow memory.
- Frontend: report panel grows a "Replay" tab with a `<canvas>` and a `<input type="range">` slider scrubber. Slider drives a frame index; canvas redraws the cluster hulls (using `track/clusters.js`) for that frame. Play/pause + 0.5×/1×/2×/4× speed buttons.
- A "highlight pair" affordance: pick two people from the dropdown, the canvas dims everyone else and traces both selected markers' paths.

## Consequences

**Positive:**
- Powerful debrief tool. The "key moments" of a workshop become visible.
- Same cluster code path (`track/clusters.js`) renders live and replay — no duplication.
- Once timeline is a stream, it's also exportable as a video via offline rendering.

**Negative:**
- Memory cost on the client: a long session's NDJSON can be tens of MB. Mitigation: the slider lazy-loads the next 60 s on demand.
- Re-computing clusters at every frame in JS is the right call (cheap, transparent), but if proximity threshold (ADR 0003) is tuned post-recording, the replay must re-stream.

**Risks:**
- Multi-camera (ADR 0005) forces the timeline endpoint to merge per-camera samples; bucketing must be precise to avoid duplicate observations of the same marker.
- Privacy in the raw position stream is real; a leaked timeline reveals who was where for the whole session. Pair with ADR 0010 retention.

## Alternatives considered
- **Render a static heatmap** — loses temporal nuance; can't answer "when did X happen?".
- **Export raw samples to a notebook** — fine for analysts, not for facilitators in a debrief room.
- **Build a timeline plot of pair contact** (gantt-style) — useful, but no spatial context.
