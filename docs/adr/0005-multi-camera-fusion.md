# ADR 0005 — Multi-camera fusion via floor-plane merge

## Status
Proposed (depends on ADR 0003 and ADR 0004).

## Context
Sala Rycerska is **20 m × 12 m** with an 8 m ceiling. The Czocha slide deck (`SLIDE 11 · FILMING FROM THE GALLERY`) explicitly plans for **six cameras** distributed around the gallery perimeter:

> Two operators on each long side, one at each end. They shoot straight down — patterns, drift, the geometry of belief.

Today the system is single-camera. With one webcam from the gallery there are blind spots near the wall directly under the camera, occlusion by people standing close together, and a single point of failure if the operator's laptop crashes mid-exercise.

## Decision
Allow many concurrent cameras to feed the same backend.

- Add `Camera` table (`id`, `name`, `homography_json` from ADR 0003, `last_seen_at`).
- The WS handshake takes a `camera_id` query param. The first WS frame from a previously-unknown camera registers it.
- Each detection is annotated server-side with its source camera and converted to **floor meters** via that camera's homography.
- A short-window deduplicator keeps a sliding 200 ms buffer of (camera_id, marker_id, floor_xy) tuples. When the same marker is reported by ≥2 cameras within the window, the median floor position is taken as authoritative; that's what flows into the marker tracker (ADR 0004) and the WS broadcast.
- `TrackingSample` gains a `camera_id` column for forensics, but reports merge across cameras.

## Consequences

**Positive:**
- No blind spots in a 20 m hall.
- Redundancy: any one operator's laptop can drop without losing the session.
- Better proximity accuracy where two cameras overlap (median of two views beats one).

**Negative:**
- All cameras must be calibrated (ADR 0003) before they're useful. Setup time scales with camera count.
- Backend must reconcile clock skew between operator laptops; we replace client `t` with server-arrival `t`.

**Risks:**
- A miscalibrated camera reports floor positions that are wildly off, polluting the median. Mitigation: per-camera "trust" toggle in admin; outlier rejection via 3-sigma filter on per-marker position spread.
- WS bandwidth scales linearly with cameras. At 6 × 1280×720 @ 10 fps × 50 KB ≈ 18 MB/s — fine on LAN, problematic over Wi-Fi. Mitigation: per-camera frame-rate cap; consider WebTransport or peer-to-peer relay later.

## Alternatives considered
- **Operator picks one camera at a time** — loses the redundancy this ADR exists to provide.
- **Stitch frames into a panorama then run a single detection pass** — high CPU; loses the "raw quality" of each camera's near-zone.
- **Edge detection (one Pi per camera)** — best long-term but moves us off Mac dev.
