# ADR 0054 — Cross-camera self-calibration via shared marker observations

## Status
Proposed (depends on ADR 0012 corner anchors, ADR 0048 pose estimation, ADR 0049 multi-placement, ADR 0050 fusion).

## Context
Calibration is the gatekeeper for everything. Without good `K`/`dist` (intrinsic, ADR 0048) and good extrinsic (where-is-this-camera-in-the-room, ADR 0012), a camera's observations are pure noise to the fusion model.

The current calibration paths assume *time and a printed board*:

- ADR 0048 needs a ChArUco board waved in front of the lens for ~10 s.
- ADR 0012 needs four corner-anchor markers visible to the camera and stable for ~2 s.

Neither works for a phone that joins mid-session. The participant doesn't have a ChArUco board. The corner anchors are taped to the floor and the participant might be standing in a position where they can't see all four. The system needs **calibration that converges from whatever the phone happens to see**.

The room is *full of fiducials*. Every participant marker (per ADR 0049) is a known-size square at a (somewhat) known body height. Every corner anchor is in a known world position. Every other camera's fused-world view of those markers gives the new phone a *target*: *"this is where these markers are; figure out where you must be to see them like this."*

That's a Perspective-n-Point (PnP) problem — exactly what `cv2.solvePnP` is for.

## Decision
Self-calibrate every joining camera from whatever fiducials it can see, using the rest of the system as ground truth.

**Three calibration tiers, applied in order.**

### Tier 1 — Corner anchors (best case, ~3 s)

If the phone can see ≥ 3 of the 4 corner markers from ADR 0012:

```python
rvec, tvec = cv2.solvePnP(
    object_points=[anchor.world_xy + (0, 0) for anchor in seen_anchors],
    image_points=[anchor.image_corners for anchor in seen_anchors],
    cameraMatrix=phone_default_K,
    distCoeffs=phone_default_dist,
    flags=cv2.SOLVEPNP_IPPE,
)
```

Anchor world positions are known; the solve gives extrinsic immediately. **Convergence time: 1–3 seconds.**

### Tier 2 — Person markers cross-observed by other cameras (~5 s)

The new phone sees N participant markers. The fusion module (ADR 0050) reports world positions for those markers from the other cameras' observations. Solve PnP against those:

- Need ≥ 4 simultaneously-visible person markers whose world positions are *currently* known by fusion.
- Per-marker world position uncertainty is propagated into PnP weights.
- Convergence is *iterative* — the phone improves its pose every few frames as more markers become commonly observed.

This handles the case where corner anchors are blocked by a body but ten participant markers are visible.

### Tier 3 — Bootstrap from a single anchor + IMU (~8 s)

If the phone sees only **one** anchor marker, fall back to:

- Single-marker PnP gives a constrained pose (correct ray, ambiguous distance / rotation).
- Phone's gyroscope (via `DeviceOrientationEvent`) constrains rotation rate.
- Over a few seconds of phone movement, the pose ambiguity resolves.

Less accurate than tiers 1 / 2; flagged `low_confidence: true` until ≥ 1 frame from a higher tier succeeds.

### Phone intrinsics: profile-based with online refinement

Phones don't get ChArUco-calibrated. Instead:

- A small lookup of **default intrinsic profiles** by user-agent. *iPhone 14 Pro main camera ≈ 1280px focal length at 1080p*; *generic Android ≈ 1100px*; *unknown ≈ 1000px*. ~80 % accurate out of the gate.
- Once the phone is pose-tracked, run online refinement: minimise reprojection error of all visible markers across the last N frames, jointly optimising `K` and pose. After ~100 frames the intrinsic is workshop-grade.
- Refined intrinsics are cached against the phone's user-agent for next time it joins.

### Continuous re-calibration

The fusion model continuously checks each camera's observed-vs-predicted marker positions. When a single camera's median reprojection error drifts > 2 px over a 30 s window, the system silently re-runs PnP using the latest fused world model. Drift detection (ADR 0015) becomes auto-correction.

## Consequences

**Positive:**
- A phone joining mid-session is fully calibrated within **3–8 seconds of pointing at the room** — comparable to a fixed-camera operator-led calibration, but zero operator effort.
- Re-calibration when something shifts (phone re-grabbed, slight bump) is invisible — the system re-solves PnP on the fly.
- Heterogeneous phones are accommodated. The default-intrinsic table covers the long tail; refinement catches anything weird.

**Negative:**
- Tier 3 (single anchor + IMU) is the weakest path. A phone stuck on Tier 3 contributes only weakly to fusion. Mitigation: ADR 0055 weights it down; the participant gets a soft hint to point at more anchors.
- Online intrinsic refinement is non-trivial to implement correctly — joint optimisation of `K` and pose has well-known numerical pitfalls. Mitigation: lean on `cv2.calibrateCamera` with frame batches, not gradient descent from scratch.

**Risks:**
- Default phone intrinsics are *wrong* enough to hurt quality during the warming-up window. Mitigation: clearly mark the phone as `warming_up` for the first ~5 s; observations are accepted but de-weighted.
- A camera in tier-3-only state for a long time (only one anchor visible) silently produces noisy data. Mitigation: ADR 0055's quality scoring catches this; the camera goes `low_quality` and contributes minimally.
- Calibration depends on the *rest* of the fusion model being right. Cold-start (first camera, no fusion exists yet) needs Tier 1 (anchors) to bootstrap. Mitigation: the first camera in any session is always operator-anchored or anchor-visible by design; phones join after.

## Alternatives considered
- **ChArUco-style explicit calibration on every phone.** Operationally impractical — workshop participants aren't holding boards.
- **Skip phone intrinsic refinement; trust default profiles.** Loses 5–15 % accuracy. Acceptable for cluster detection, painful for body-orientation inference.
- **Rely on phone IMUs alone.** IMUs drift; visual fiducials don't. Fiducials are the right anchor.

## Postscript
This is the ADR that makes ADR 0051's premise actually work. Without self-calibration, the phone-as-camera idea collapses on the first join. With it, a participant pulling out their phone *is* a calibrated camera within seconds — no training, no boards, no operator involvement. The room becomes the calibration target.
