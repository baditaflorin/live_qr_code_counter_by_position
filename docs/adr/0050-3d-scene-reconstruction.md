# ADR 0050 — 3D scene reconstruction by fusing pose-estimated observations across cameras

## Status
Proposed (depends on ADR 0005 multi-camera fusion, ADR 0048 pose estimation, ADR 0049 multi-placement).

## Context
ADR 0048 gives every camera per-marker 6-DOF pose in *its own* camera frame.
ADR 0012 gives every camera its *extrinsic* pose in the world frame.
ADR 0049 puts multiple markers on each person.
ADR 0005 lets multiple cameras report observations of the same room.

Each piece on its own is partial. **Fused together** they're enough to reconstruct a full 3D scene of the workshop in real time:

- Where every participant is (x, y, z) in metres of room space.
- Which way each participant is facing (yaw, body posture).
- How each cluster is shaped (3D convex hull, not 2D blob).
- Where camera blind spots are (which markers were *not* observed by any camera, but were observed last frame).

The current "world model" is a flat 2D top-down. It's good for cluster counting and zone hits. It's wrong for *witness inference* (yaw matters), wrong for *crowd density* (vertical posture differs between standing and sitting), and wrong for *dance / movement workshops* (pure 2D loses everything interesting).

This ADR is the culmination of the geometry layer. After this, *every spatial question the system might be asked* has an answer in metres-and-degrees, not in pixels-and-image-coords.

## Decision
A new `SceneReconstruction` module in `backend/scene.py` that runs once per detection cycle (per ADR 0032 frame-router rate, default 10 Hz).

**Inputs.** From each connected camera, every frame:
- The list of `(marker_id, world_xyz, world_yaw_pitch_roll, reproj_error)` from ADR 0048.
- The camera's extrinsic and confidence weight from ADR 0012.

**Per-marker fusion.** When the same `marker_id` is reported by multiple cameras within a 200 ms window:

- World position is the **inverse-variance-weighted average** of the per-camera world `(x, y, z)`. Variance per camera is derived from reprojection error — high error → low weight.
- Orientation is fused via **quaternion averaging** (Markley method) over the per-camera rotations.
- An observation seen by ≥ 2 cameras is flagged `triangulated: true` and gets an order-of-magnitude lower position uncertainty than a single-camera observation.

**Per-person fusion.** All fused marker observations are then grouped by `person_id` (per ADR 0049):

```
Person {
  person_id, name,
  body_pos_world: (x, y, z),     # weighted average of detected markers, hat=1.7m, chest=1.2m, back=1.2m
  body_yaw_deg: 28.5,            # primarily from chest↔back vector when both seen, fallback to single-marker pose
  observed_markers: [hat, chest],# which placements contributed this frame
  confidence: 0.86,
}
```

**Output: World snapshot.** Replaces the per-frame 2D detections payload on the WS:

```json
{
  "scene_world": {
    "people": [{ ... Person ... }, ...],
    "clusters_3d": [{ id, members: [...], hull_xyz: [...], centroid: [x,y,z] }, ...],
    "blind_spots": [{ person_id, last_seen_t, last_pos: [...] }, ...]
  }
}
```

**Persistence.** `TrackingSample` (per ADR 0048's earlier extension) holds the fused world `(x, y, z, yaw)`. We *also* keep the raw per-camera observations in a new `RawObservation` table — small, fast-rotating, retention-pruned per ADR 0010 (default 7 days). Reports compute against `TrackingSample`; debugging and re-fusion-with-different-parameters use `RawObservation`.

**Rendering.** `/project` (ADR 0018) and `/track` gain a 3D top-down render with body avatars and orientation arrows, drawn directly from `scene_world.people`. The same data drives the timeline replay (ADR 0008).

**Quality metrics** (per ADR 0036):
- `scene.coverage_pct` — what fraction of the active person markers are seen *by at least one camera* this frame.
- `scene.triangulated_pct` — what fraction are seen by ≥2 cameras (i.e., have low position uncertainty).
- `scene.median_position_uncertainty_m` — typical fused-position 1σ across the room.

## Consequences

**Positive:**
- **Real 3D**. Witness yaw is correct. Cluster hulls are 3D. Blind spots are *known*. Trail lines are in metres of room. Pose data feeds future research uses (ADR 0039 destination #3, peer-reviewed papers).
- **Robustness.** Multi-camera triangulation means losing one operator's laptop doesn't break the model — the remaining cameras keep producing world-frame observations that the fusion layer averages just fine.
- **Composes with everything.** Reflection cards (ADR 0017), the highlight reel (ADR 0019), the projection mode (ADR 0018), the timeline replay (ADR 0008) all consume the same `scene_world` representation. One world model, many consumers.
- **Replayable.** Stored `TrackingSample` in metres + yaw means the report can re-render the scene weeks later, including answering "which way was Bob facing at 14:32?".

**Negative:**
- Real complexity. Pose estimation, multi-camera extrinsic calibration, time-window fusion, quaternion averaging — none of it is hard, all of it has to be right.
- The single-camera fallback path must keep working (one operator, one laptop, no fusion). Code-wise this is a lower-effort path of the same module — at any given fusion step, one camera reduces to "passthrough".

**Risks:**
- **Time skew between cameras.** Two operator laptops are not clock-synchronised. Mitigation: use *server-side arrival time* (per ADR 0005) as the canonical timestamp; the 200 ms fusion window absorbs ~50–100 ms of skew comfortably.
- **Cumulative calibration error.** Each camera's intrinsic (ADR 0048) + extrinsic (ADR 0012) carries some error; the fused world position propagates them. Mitigation: report `position_uncertainty_m` per person; downstream features filter on confidence; ADR 0015's drift detection catches gross failures.
- **Compute cost** scales with cameras × markers × Hz. At 6 cameras × 50 markers × 10 Hz = 3000 pose-estimations per second. Mitigation: per-camera pose estimation is each laptop's local cost (the WS uploader runs on the camera's host); the backend only does the lightweight fusion. The bottleneck is the operator-laptop CPU, which is per-laptop, not centralised.

## Alternatives considered
- **Stay 2D forever.** Current state. Sufficient for cluster counting; everything richer (orientation, posture, 3D clusters, blind-spot detection) is foreclosed.
- **External SLAM library** (ORB-SLAM3, Open3D's ICP). Powerful and overkill — fiducial markers give all the constraints SLAM normally has to discover. Re-using SLAM machinery means more dependency for less reliability.
- **Render 3D but persist 2D.** Cheap mid-step; loses post-event re-rendering at higher fidelity. Better to persist the richer representation.

## Postscript
This is the geometry-layer's terminal ADR. After it lands, the question "*where is Anna right now?*" has the same answer everywhere in the system — a 4-tuple `(x_m, y_m, z_m, yaw_deg)` in shared world frame, with a confidence — and every other ADR above this one feeds from that single source of truth. The first 47 ADRs designed the workshop's *features*; ADRs 0048–0050 give them all a *physics*.
