# ADR 0004 — Stateful marker tracker with temporal smoothing

## Status
Proposed.

## Context
`backend/detection.py` is purely per-frame. Each WS frame is decoded, ArUco-detected, and the result is sent back without any memory of what happened in the previous frame. In practice this means:

- A marker that drops detection for one frame (motion blur, partial occlusion, momentary glare) flickers in/out of the live overlay and the cluster list.
- Tracking samples skip rows for that frame, which under-counts contact time.
- Cluster identities are not stable across frames — a 5-person cluster can appear to "split and reform" once a frame.
- Per-zone counts in the live page jitter visibly even when nobody is moving.

The data is fine on average, but the perceived stability of the tool degrades in real workshop conditions (where marker prints curl, lights flare, and people lean their heads).

## Decision
Add a `MarkerTracker` class in `backend/tracking_realtime.py` (separate from the report-time analysis in `backend/tracking.py`).

- Per marker id, hold a state `{x_ema, y_ema, last_seen_t, alive_until_t}`.
- On each WS frame:
  - For markers detected this frame: blend new (x, y) into the EMA (`alpha = 0.6`), refresh `last_seen_t`, set `alive_until_t = now + 1.0s`.
  - For markers in tracker but not detected this frame: keep their last EMA position; if `now > alive_until_t`, drop them.
- The WS payload's `detections` reflects the tracker, not raw detection. Tracking samples are written from the tracker too.
- The tracker is per-WS-connection (so two clients don't fight); cross-camera fusion in ADR 0005 layers on top.

## Consequences

**Positive:**
- Live overlay stops blinking. Counts visibly settle.
- Contact-time accuracy improves measurably for typical 1-second occlusions.
- Cluster membership is stable across short occlusions, so the live cluster list doesn't churn.

**Negative:**
- A marker that has actually left the frame is reported "alive" for up to 1 second after departure.
- Adds a small per-connection state object.

**Risks:**
- A marker leaves the room and a different person walks past where it was within 1 s → clusters wrongly attribute that person. Mitigation: shrink `alive_until_t` to 500 ms by default, configurable per `TrackingSession`.
- EMA introduces lag; rapid movement shows a slightly trailed position. Acceptable for cluster detection (which works on aggregates), not great for precise zone-edge cases.

## Alternatives considered
- **Hungarian-algorithm assignment between consecutive frames** — overkill because each ArUco id is already unique; we don't need to *re-identify* markers.
- **Median-of-last-N positions** — equivalent to EMA with stronger filter, but harder to tune.
- **Pure per-frame (status quo)** — works but the visible jitter erodes operator trust.
