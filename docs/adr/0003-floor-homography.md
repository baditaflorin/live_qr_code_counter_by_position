# ADR 0003 — Calibrate a floor homography per camera

## Status
Proposed.

## Context
Proximity in `tracking.compute_report` and the live cluster overlay is computed in normalized **image** coordinates:

```python
threshold_sq = session.proximity_norm ** 2
if (xi - xj) ** 2 + (yi - yj) ** 2 <= threshold_sq:
    union(mi, mj)
```

This is wrong for a 45–60° camera. Two markers 1 m apart at the back of the hall are roughly 0.04 frame-units apart; the same two markers 1 m apart at the front are 0.10 frame-units apart. The same physical "talking distance" registers as 6 different image distances depending on where in the frame the people stand. Cluster detection systematically over-counts pairs near the camera and under-counts pairs near the back wall.

Zones are already drawn as floor trapezoids (ADR 0003-precursor in [`backend/seeds/default_zones.py`](../../backend/seeds/default_zones.py)) so the geometry to project image → floor exists; we just don't use it for tracking.

## Decision
Add a per-camera floor homography.

- New `Camera` table (`id`, `name`, `homography_json`).
- Calibration UI: operator places 4 ArUco markers at known positions of a 2 m × 2 m square on the floor, clicks "calibrate", system records the four image-space marker centers and computes the 3×3 homography (`cv2.findHomography`).
- `proximity_norm` becomes `proximity_m` on `TrackingSession`. Default 1.5 m (typical talking distance).
- `tracking.compute_report` projects each (x, y) image point through the camera's inverse homography to floor coords (meters), then computes Euclidean distance.

## Consequences

**Positive:**
- Cluster proximity is in real meters. Operators tune in human units, not pixels.
- Same threshold gives consistent results across the frame and across rooms.
- Foundation for ADR 0005 multi-camera fusion — homographies map every camera into a shared floor coordinate frame.

**Negative:**
- One-time calibration step adds setup friction.
- Schema change: `proximity_norm` → `proximity_m` (handle via Alembic, ADR 0002).

**Risks:**
- Camera moves or zooms during a session → homography invalid; symptoms quietly skew.
- Calibration markers placed inaccurately → all distances biased.
- Mitigation: store the four calibration points and a "calibrated_at" timestamp; warn if camera resolution changes after calibration; recompute trivially.

## Alternatives considered
- **Use marker bounding-box size as a depth cue** — noisy because marker-print sizes vary; tilted markers shrink; requires marker tilt estimation.
- **Skip calibration, ship image-space proximity** — current state, broken at scale.
- **Manually annotate floor corners on the image and assume rectangular floor** — what `default_zones.py` already does for zone drawing; works for zones but not for arbitrary marker positions.
