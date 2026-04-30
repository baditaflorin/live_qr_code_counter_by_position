# ADR 0048 — Real-time 6-DOF pose estimation per ArUco marker

## Status
Proposed (depends on ADR 0003 floor homography, ADR 0012 corner-anchor calibration).

## Context
The detection pipeline today extracts only the **2D image-space corners** of each marker. We then project the marker centre through the floor homography (ADR 0003) to get a floor `(x, y)` in metres, and that's it. The marker's *orientation* — the way it's facing — and its *height above the floor* are both information OpenCV could give us for free, but we're throwing them away.

Concretely, `cv2.aruco.estimatePoseSingleMarkers(corners, marker_size_m, K, dist)` computes full **6-DOF pose** (rotation vector + translation vector) per marker, given:

- The marker's known physical side length (a config value, e.g. 0.15 m).
- The camera's **intrinsic matrix** `K` (focal length + principal point).
- The camera's **distortion coefficients** (radial + tangential).

ADR 0012 already calibrates the camera-to-floor *extrinsic* (where the camera is in the room). What we don't have yet is the camera *intrinsic* — and `K`/`dist` are exactly what `estimatePoseSingleMarkers` needs to convert image-space marker corners into camera-frame 3D position + orientation.

Once 6-DOF pose is captured, downstream features unlock immediately: real height-above-floor (distinguishing a marker held *up* from one *worn on the head* from one *on the chest*), facing direction (which way the person is looking), and posture changes (head tilt, lean) — all without any new sensors.

## Decision
Capture and persist 6-DOF pose for every detected marker.

**Camera intrinsic calibration.** Add a one-time step:

- The operator prints a **ChArUco board** (a chessboard with ArUco markers in the white squares — `cv2.aruco.CharucoBoard`) and shows it to the camera at varied angles for ~10 seconds.
- The system collects ≥20 distinct views, runs `cv2.aruco.calibrateCameraCharuco`, and stores the resulting `K`, `dist`, and a per-pixel reprojection error on the `Camera` row.
- Reprojection error > 1 pixel triggers a "recalibration recommended" warning per ADR 0035 (limits & degradation).

**Detection pipeline change.** After `detector.detectMarkers(...)`:

```python
rvecs, tvecs, _ = cv2.aruco.estimatePoseSingleMarkers(
    corners, marker_size_m, camera.K, camera.dist
)
```

Each detection now carries `(rvec, tvec)` in **camera frame**. Combined with the camera's extrinsic from ADR 0012, every marker's pose is then expressible in **world frame** — i.e. floor `(x, y, z)` plus a rotation matrix giving body orientation.

**WS payload extension.** Each entry in `detections` gains:

```json
{
  "aruco_id": 47,
  "corners_norm": [...],
  "center_norm": [...],
  "pose": {
    "world_xyz_m": [3.21, 1.45, 1.62],
    "yaw_deg": 28.5,
    "pitch_deg": -3.1,
    "roll_deg": 0.7,
    "reprojection_error_px": 0.42
  }
}
```

**TrackingSample schema extension.** Adds `world_x_m`, `world_y_m`, `world_z_m`, `yaw_deg`, `pitch_deg`, `roll_deg`. Migrations per ADR 0002.

**Schema for `Camera`.** Adds `K_json`, `dist_json`, `marker_size_m` (default 0.15), `intrinsic_calibrated_at`, `intrinsic_reproj_error_px`.

## Consequences

**Positive:**
- **Body orientation** becomes a first-class signal. Witness inference (ADR 0027) gets vastly more reliable — direction of facing is now a real number, not a 2D-corner heuristic.
- **Vertical axis** disambiguates marker placement (hat ≈ 1.7 m, chest ≈ 1.2 m, marker held aloft ≈ 2 m). Foundation for ADR 0049's multi-placement strategy.
- The floor `(x, y)` derived from full pose is **more accurate** than the homography-projected center, because pose estimation accounts for marker tilt instead of assuming the marker lies flat on the floor.
- Cluster detection in ADR 0005 fusion gains a vertical filter: a marker at `z ≈ 2 m` is held aloft (likely a participant card) and shouldn't be clustered with a chest marker at `z ≈ 1.2 m` of the same person.

**Negative:**
- Adds a calibration step. ChArUco-board calibration takes ~5 minutes per camera, must be redone if the lens zoom changes. Mitigation: most webcams have fixed zoom; the calibration is one-time per physical camera.
- `estimatePoseSingleMarkers` is ~5–10 ms per frame for ~20 markers at 1080p — within ADR 0035's CPU envelope but not free.

**Risks:**
- Pose estimation degrades when markers are small in pixel terms (ADR 0031's threshold). At 30 px per side, position error can be ±10 cm and orientation ±15° — useful for "facing roughly that way" but not for fine pose. Mitigation: report `reprojection_error_px` per detection; downstream features filter on confidence.
- A bent or curled marker has wrong corners and produces wrong pose. The system can't tell. Mitigation: same as ADR 0031 — the briefing instructs participants to keep markers flat; bent markers degrade the same way as low-resolution markers.

## Alternatives considered
- **Skip pose; image-space-only.** Current state. Wastes free signal; locks us out of ADR 0049 / 0050.
- **Use marker bounding-box size as a depth cue.** Single-marker depth from one camera; works but poorly. `estimatePoseSingleMarkers` is strictly better when you've calibrated.
- **Train a small CNN on detected corners → 3D pose.** Replaces a closed-form OpenCV call with a black box. No win.

## Postscript
This is the "physics for free" ADR. We've been doing 2D inference all along even though every detected marker carries 3D information in its corner pixels. Calibration is the only thing standing between the current state and full 3D pose; everything downstream is just *using* what's already there.
