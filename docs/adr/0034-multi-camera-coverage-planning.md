# ADR 0034 — Multi-camera coverage planning

## Status
Proposed (depends on ADR 0003 homography, ADR 0005 fusion, ADR 0031 resolution math).

## Context
ADR 0005 makes the system *capable* of running with multiple cameras. ADR 0031 establishes that one camera at the gallery cannot reliably resolve 15 cm markers across the whole 20 × 12 m floor of Sala Rycerska at 1080p. So multiple cameras are not optional; they're load-bearing.

The slide deck specifies six cameras: *"Two operators on each long side, one at each end. They shoot straight down — patterns, drift, the geometry of belief."* That's a rough placement; what we don't have is a **coverage plan**:

- Which camera covers which floor square?
- How much overlap is needed for handoff between cameras?
- Where are the blind spots if one operator's camera dies?
- Are all four corners of the floor covered by at least two cameras (for ADR 0005 redundancy)?

Without an answer, the team shows up on the day, mounts six cameras roughly, and finds at runtime that the back-left corner sees zero cameras and the centre sees four — wasted overlap, real gap.

## Decision
Add a **coverage planner** to `/admin`.

Inputs:
- Floor dimensions (default 20 × 12 m for Sala Rycerska; configurable per workshop).
- Per-camera mount profile: `(name, mount_x, mount_y, mount_height, tilt_deg, fov_h_deg, fov_v_deg, resolution)`.
- Configured `min_marker_px_side` from ADR 0031.

Outputs:
- A 2D top-down floor diagram (SVG) shaded by **how many cameras cover each square** at ≥ `min_marker_px_side` resolution. Green = ≥2 cameras (redundant), yellow = 1 camera (no failover), red = 0 cameras (blind spot).
- Per-camera overlap matrix: a table of "camera A and camera B both cover X m² of floor".
- A short narrative: *"Coverage 92 %. Single-camera blind spots: 0. Single-camera-only zones: 4 m² in the back-left corner. Camera 3 has the most redundancy partners (4)."*

The planner is a pre-event tool — operators feed it intended camera positions on the venue's floor plan and iterate until the diagram is mostly green. For ad-hoc setups it can also *consume* the live homographies (ADR 0003): once each camera is calibrated, the planner reads their floor projections from the homographies and produces the same diagram from real data.

A **`/admin/coverage` route** renders the diagram live. A `/api/cameras/coverage.svg` endpoint exports it for documentation.

## Consequences

**Positive:**
- Camera positioning becomes a planned activity, not a ritual. The planner says "move camera 4 two metres toward the door and the back-left blind spot disappears."
- Pre-event planning is decoupled from on-site setup — the planner can run on a laptop with the floor plan in hand.
- After ADR 0005's fusion lands, redundancy becomes visible: operators can see at a glance "we lose camera 2, are we still covered everywhere?"

**Negative:**
- The planner is a non-trivial UI; another route. Mitigation: it's only relevant for multi-camera setups; single-camera workshops don't need it.
- Camera mount-profile data is required, which means each camera model needs FOV constants. We'll ship a small library of webcam profiles (Logitech C920, MacBook FaceTime, iPhone, etc.) and let the operator override.

**Risks:**
- The planner trusts user-input camera positions; if the mounts are off in reality, the diagram lies. Mitigation: once cameras are calibrated for real (ADR 0012), the live mode supersedes the planning mode.
- Coverage at calibration time is not coverage with people in the room — moving bodies occlude. Mitigation: the planner's "green" colouring is computed for static markers; an "occlusion budget" overlay simulates partial blockage, with a configurable density.

## Alternatives considered
- **No planner.** Current state. Operators eyeball it and live with the gaps.
- **3D model with full ray-tracing.** Beautiful, expensive to build, irrelevant to whether a marker is detectable.
- **Just print a checklist** ("place a camera every 5 m"). Works for one venue; doesn't generalise.
