# ADR 0012 — Auto-calibration via four corner markers

## Status
Proposed (depends on ADR 0003 for the homography model and ADR 0011 for control-marker infrastructure).

## Context
ADR 0003 establishes that proximity must be computed in real meters via a per-camera floor homography. Implicit in that ADR is a manual UX: the operator clicks four points on the image and types the corresponding real-world coordinates. That ceremony is unwelcome in two ways:

- **Setup time.** A facilitator showing up an hour before doors-open does not want to be in a typing loop.
- **Re-calibration cost.** Camera position shifts during the day (the gallery is wooden, people lean on it). Re-doing the click-and-type ritual is expensive enough that operators won't, and the proximity metric quietly drifts.

The room itself, however, has very stable geometry. Once you mark out a known rectangle on the floor — say a 5 m × 4 m strip — that rectangle stays put for the whole event.

## Decision
Reserve four control-marker ids (per ADR 0011) — `CALIB_TL`, `CALIB_TR`, `CALIB_BR`, `CALIB_BL` — and treat them as **corners of a known floor rectangle**.

- The Camera record (ADR 0003) gains a `calibration_world_m` field: the rectangle dimensions in meters (default 5 × 4, configurable per camera). World coords for the four corners are then `(0, 0)`, `(W, 0)`, `(W, H)`, `(0, H)`.
- Operator places one printed corner-marker per floor corner of the rectangle (gaffer tape works).
- Detection pipeline notices when **all four corners are visible simultaneously, stable for 2 seconds**. It triggers `cv2.findHomography(image_pts, world_pts)` and stores the result on the active Camera plus a `calibrated_at` timestamp.
- A `CALIB_RECHECK` control marker (also reserved) forces re-calibration on demand.

## Consequences

**Positive:**
- Calibration becomes a 30-second floor-walk, not a typing loop.
- Re-calibration on the same room is one card-flash away; the operator can re-anchor any time.
- Same physical setup re-used between multiple workshops in the same hall: place the four cards once, the system knows the floor.

**Negative:**
- Operator has to print four extra cards and remember to bring tape. Mitigated by including all reserved control markers on the same printable PDF (ADR 0011).
- Calibration accuracy is bounded by how precisely the operator places the four markers on the floor. Off by 5 cm on a 5 m corner = 1 % skew, acceptable for clustering.

**Risks:**
- A participant kicks a corner marker mid-exercise, calibration silently degrades. Mitigation: after the first calibration, treat the four corner markers as **anchors** (ADR 0015) — the system continuously verifies their relative geometry and warns on drift.
- Corner markers occluded by people standing on them. Mitigation: only re-calibrate when at least three corners are unambiguously visible AND no person markers are detected within 0.3 m of any corner.

## Alternatives considered
- **Click-and-type calibration** — ADR 0003's default. Works once but operators won't repeat it.
- **Single Charuco board** — denser fiducial, more accurate, but bulky to print and place.
- **Auto-detect floor by tracking person motion over a few minutes** — no manual setup, but converges slowly and gives a worse fit than four points at known locations.
