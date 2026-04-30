# ADR 0015 — Anchor markers for drift detection and self-recalibration

## Status
Proposed (depends on ADR 0011 control markers, ADR 0012 calibration).

## Context
ADR 0003 + ADR 0012 produce a per-camera floor homography. That homography is exactly correct *the moment it's computed* and approximately correct for as long as the camera sits where it was. In a real venue:

- Gallery floors flex. A 50-person workshop has people walking on them.
- Operators bump tripods on the way to coffee.
- Phones used as cameras (per the demo flow) get repositioned constantly.

When the camera moves, every cluster proximity, every zone hit-test, every tracking sample becomes silently wrong. The system has no idea anything has changed.

## Decision
The four corner markers from ADR 0012 are kept visible throughout the session and treated as **anchors**. The system continuously checks them.

- After calibration, the four anchor markers' image-space centers are stored as `anchor_baseline` on the Camera record.
- Every WS frame, the detection pipeline records each visible anchor's current image-space center.
- A rolling 5-second median is compared to the baseline. If any anchor's median drifts by **more than 2 % of frame width**, an alert fires:
  - Live overlay shows a non-blocking yellow banner: "Camera moved. Re-anchor or recalibrate."
  - Live page emits a `camera_drift` event in the WS payload so `/present` and `/track` can mirror the warning.
- Optionally — gated by a per-camera `auto_recalibrate` flag — if **all four** anchors are visible and have shifted **rigidly** (i.e. the relative geometry between them is preserved within 1 %), the system recomputes the homography on the fly. Soft self-correction without operator intervention.
- If **fewer than two anchors** are visible for >10 seconds, a separate alert: "Camera blocked or repointed." This doubles as a passive health check.

## Consequences

**Positive:**
- The "silent drift" failure mode goes from invisible to loud-and-correctable.
- Self-recalibration handles the most common drift (small camera shifts) without operator input.
- "Camera lost" detection catches a class of bug that today only shows as the live counter going to zero.

**Negative:**
- Anchors must be visible — the operator can't stage the floor with anchors hidden behind people. Mitigation: anchors are placed on the *edge* of the floor area, where people don't tend to stand; the threshold for "visible enough" is "at least 2 of 4".
- Self-recalibration could mask a camera that's slowly drifting in a weird direction. Mitigation: log every auto-recalibration with `before/after` homographies in the audit log (ADR 0009); the operator can review post-event.

**Risks:**
- Anchor markers themselves get bumped (someone kicks the corner card). Mitigation: rigid-shift check (4-anchor recalibration only fires if the pattern moved together; if one anchor moves alone, that's flagged as a kicked card and ignored for recalibration).
- Aggressive auto-recalibration in a session with active tracking could change recorded sample positions mid-stream. Mitigation: tracking samples carry the homography version they were recorded with; reports recompute against that version.

## Alternatives considered
- **No drift detection** — current state. The proximity quietly degrades; nobody notices until a debrief shows weird never-met pairs.
- **Periodic operator-triggered re-calibration only** — works if the operator remembers, but ADR 0012 already makes that easy; the value here is *automatic*.
- **IMU on the camera (phone)** — real signal but only for phone cameras and adds platform-specific code.
