# ADR 0031 — Resolution, marker size, and detectable count per camera

## Status
Proposed (informs ADR 0034 multi-camera planning).

## Context
The first question every new operator asks is *"how many people can this thing see at once?"*. There's a real answer rooted in physics, not vibes.

ArUco detection needs roughly **40 pixels per marker side** for reliable decoding under typical lighting (OpenCV's docs cite a minimum of 4× the inner-cell count plus border; for `DICT_4X4_*` that's 6 cells × 6–8 px = 36–48 px). Below 30 pixels per side detection becomes noisy and tilt-sensitive. Above 60 pixels there are diminishing returns.

That fixes the relationship:

```
pixels_per_marker_side = (marker_print_size_m / floor_width_m_in_view) × image_width_px
```

For Sala Rycerska from the gallery (single camera, ~8 m mount height, 45–60° tilt, ~72° horizontal FOV) the camera's view of the floor at center range is ~9 m wide. A typical chest-mounted marker is 15 cm. Run the math:

| Camera resolution    | Image width px | px / 15 cm marker | Verdict                                 |
| -------------------- | -------------- | ----------------- | --------------------------------------- |
| 720p  (1280 × 720)   | 1280           | **21**            | Below floor; flickers, mis-decodes      |
| 1080p (1920 × 1080)  | 1920           | **32**            | Marginal; works centre, fails corners   |
| 4K    (3840 × 2160)  | 3840           | **64**            | Comfortable across the whole frame      |
| 8K    (7680 × 4320)  | 7680           | **128**           | Wasteful — same accuracy as 4K          |

The *count* of markers in frame is **not** the binding constraint. 100 markers of 15 cm each on a 4K frame occupy ~3 % of the pixel budget; the detector's per-frame cost stays roughly constant whether 1 or 100 markers are visible (the contour pass dominates).

The constraint is **pixels-per-marker**, set by frame resolution × physical marker size × camera FOV × distance.

## Decision
Codify the operating envelope as a small inline calculator + a per-Camera `min_marker_px_side` field (default 40). The check runs on calibration (ADR 0012):

1. After homography is computed, the system knows pixels per real-world meter at the centre and edges of the floor.
2. For the configured `marker_print_size_m` (default 0.15 m) we compute `pixels_per_marker_side` at the four floor corners.
3. If any corner drops below `min_marker_px_side`, the calibration UI surfaces a yellow "this corner is below detection threshold" badge, with three suggested fixes:
   - Increase camera resolution.
   - Increase `marker_print_size_m` (print bigger markers).
   - Reduce floor coverage (zoom in, or add a second camera per ADR 0034).

We **default the prod camera profile to 1920 × 1080 with 20 cm markers**, which gives ~42 px per marker side at floor centre and ~28 px at the far corners — usable, but the operator should know the corners are weak.

For a 100-person workshop in a 20 × 12 m hall covered by one camera, the only working configuration is **4K + 15 cm markers** *or* **1080p + 25 cm markers** *or* **1080p + multi-camera with each camera covering ~10 m of floor width**. The tool tells the operator which they're in.

## Consequences

**Positive:**
- The operator stops guessing. The calibration page tells them whether their setup will work *before* the workshop starts.
- Reproducible bug reports: "this corner detects 28 px markers" beats "detection is flaky".
- Concrete sourcing guide: print markers bigger, or buy a 4K webcam, or add cameras. Every fix is bounded.

**Negative:**
- Computing `pixels_per_marker_side` accurately requires the homography (ADR 0003), so this check only fires *after* calibration. Operators who skip calibration get no warning.
- The `40 px` threshold is a heuristic, not a guarantee — bad lighting can require 50+, perfect lighting works at 25.

**Risks:**
- A workshop sets up at 1080p + 15 cm markers (32 px), it mostly works in dev with good light, fails on the day under harsher light. Mitigation: the calibration warning is loud, not silent; the operator must explicitly acknowledge to dismiss.

## Alternatives considered
- **No advisory; let it fail in production.** Current state. The operator finds out the hard way.
- **Hardcode minimum resolution to 4K.** Excludes anyone with a laptop webcam from running the system at all.
- **Adaptive marker size estimation** — measure detected marker size in pixels in real time, warn when it drops too low. Useful as an *additional* check (ADR 0035), not as a replacement for the calibration-time advisory.
