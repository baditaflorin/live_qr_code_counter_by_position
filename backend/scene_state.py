"""Multi-camera scene aggregator (process-local singleton).

Each `/ws/detect` connection publishes its per-camera marker observations
here after computing pose; observers (`/ws/scene`, the /track3d viewer) read
the *fused* world-frame scene at a fixed cadence.

Fusion rules per `aruco_id` (within `max_age_s` of `now`):
  - position is a quality-weighted average of world XYZ across cameras
    (weight = 1 / (0.25 + reproj_err²); same shape as `scene._quality_weight`)
  - orientation is the unit-quaternion-weighted mean (then renormalised),
    which gives correct circular-mean behaviour for yaw and a numerically
    well-behaved blend for pitch/roll
  - placement / person metadata are taken from the most recent observation
    (they are properties of the marker, not the camera)

After per-marker fusion the existing `scene.fuse_person_observations` runs
unchanged, so the multi-camera path collapses to identity when only one
camera is publishing — exactly the same payload as before, just produced
through the aggregator.
"""
from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from . import pose_filter
from . import scene as scene_mod
from .scene import MarkerObservation


@dataclass
class _CameraSnapshot:
    camera_id: int
    camera_name: str
    markers: dict[int, MarkerObservation]   # aruco_id → latest observation
    world_frame: dict                        # floor dimensions + cam world pos
    last_update_ts: float
    fps: float = 0.0
    intrinsic_calibrated: bool = True
    extrinsic_calibrated: bool = True
    coverage_pct: float = 0.0


def _R_from_yaw_pitch_roll_deg(yaw: float, pitch: float, roll: float) -> np.ndarray:
    """Inverse of pose.R_to_euler_zyx_deg — intrinsic ZYX → R."""
    cy, sy = math.cos(math.radians(yaw)),   math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    cr, sr = math.cos(math.radians(roll)),  math.sin(math.radians(roll))
    Rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]], dtype=np.float64)
    Ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]], dtype=np.float64)
    Rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]], dtype=np.float64)
    return Rz @ Ry @ Rx


def _avg_quaternion(quats: list[np.ndarray], weights: list[float]) -> np.ndarray:
    """Weighted unit-quaternion mean.  Sign-flips so all q lie in same hemisphere."""
    if not quats:
        return np.array([1.0, 0.0, 0.0, 0.0])
    ref = quats[0]
    accum = np.zeros(4, dtype=np.float64)
    for q, w in zip(quats, weights):
        if np.dot(q, ref) < 0:
            q = -q
        accum += w * q
    n = float(np.linalg.norm(accum))
    if n < 1e-9:
        return ref / np.linalg.norm(ref)
    return accum / n


def _quality_weight(reproj_err_px: float) -> float:
    return 1.0 / (0.25 + reproj_err_px * reproj_err_px)


class SceneAggregator:
    """Process-local singleton.  All access is async via `lock`."""

    def __init__(self, max_age_s: float = 2.0):
        self.max_age_s = float(max_age_s)
        self._cameras: dict[int, _CameraSnapshot] = {}
        self.lock = asyncio.Lock()
        # Publish counter so observer loops can poll-on-change.
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    async def update_camera(
        self,
        camera_id: int,
        camera_name: str,
        markers: list[MarkerObservation],
        world_frame: dict,
        fps: float,
        intrinsic_calibrated: bool,
        extrinsic_calibrated: bool,
        coverage_pct: float,
    ) -> None:
        async with self.lock:
            self._cameras[camera_id] = _CameraSnapshot(
                camera_id=camera_id,
                camera_name=camera_name,
                markers={m.aruco_id: m for m in markers},
                world_frame=world_frame,
                last_update_ts=time.time(),
                fps=fps,
                intrinsic_calibrated=intrinsic_calibrated,
                extrinsic_calibrated=extrinsic_calibrated,
                coverage_pct=coverage_pct,
            )
            self._version += 1

    async def remove_camera(self, camera_id: int) -> None:
        async with self.lock:
            self._cameras.pop(camera_id, None)
            self._version += 1

    async def fused_scene(self) -> dict:
        """Build a `scene_world`-shaped dict combining all live cameras."""
        async with self.lock:
            now = time.time()
            live = [
                snap for snap in self._cameras.values()
                if (now - snap.last_update_ts) <= self.max_age_s
            ]

            # Pick a "primary" world_frame — first calibrated camera with
            # extrinsic.  Floor dims should match across cameras anyway, but
            # use the first one as canonical.
            primary_frame = None
            for snap in live:
                if snap.extrinsic_calibrated:
                    primary_frame = snap.world_frame
                    break
            if primary_frame is None and live:
                primary_frame = live[0].world_frame

            # Camera summary list for the observer panel — includes the mean
            # reprojection error this camera is currently reporting (a live
            # signal of intrinsic-calibration health and focus).
            cameras_summary = []
            for s in live:
                errs = [m.reproj_error_px for m in s.markers.values()]
                mean_err = float(sum(errs) / len(errs)) if errs else None
                cameras_summary.append({
                    "camera_id": s.camera_id,
                    "name": s.camera_name,
                    "fps": round(s.fps, 1),
                    "age_ms": int((now - s.last_update_ts) * 1000),
                    "marker_count": len(s.markers),
                    "intrinsic_calibrated": s.intrinsic_calibrated,
                    "extrinsic_calibrated": s.extrinsic_calibrated,
                    "coverage_pct": s.coverage_pct,
                    "mean_reproj_error_px": round(mean_err, 3) if mean_err is not None else None,
                    "camera_position_world_m": s.world_frame.get("camera_position_world_m"),
                })

            # Group observations by marker id across cameras.
            per_marker: dict[int, list[tuple[int, MarkerObservation]]] = {}
            for snap in live:
                if not snap.extrinsic_calibrated:
                    continue
                for aruco_id, obs in snap.markers.items():
                    per_marker.setdefault(aruco_id, []).append((snap.camera_id, obs))

            fused_markers: list[MarkerObservation] = []
            marker_witnesses: dict[int, list[int]] = {}
            marker_disagreement_cm: dict[int, Optional[float]] = {}
            for aruco_id, observations in per_marker.items():
                obs_list = [o for _, o in observations]
                cam_ids = [cid for cid, _ in observations]
                weights = np.array([_quality_weight(o.reproj_error_px) for o in obs_list])
                wsum = float(weights.sum())
                if wsum <= 0:
                    continue

                positions = np.array([o.world_xyz for o in obs_list])
                fused_xyz = (positions.T * weights).sum(axis=1) / wsum

                # Cross-camera agreement: max pairwise distance (cm) between
                # any two cameras' world-frame estimates of this marker.
                # Tight (<5 cm) = extrinsic is solid; loose (>20 cm) = at
                # least one camera's calibration drifted or was wrong.
                if len(positions) > 1:
                    diffs = positions[:, None, :] - positions[None, :, :]
                    dists_m = np.linalg.norm(diffs, axis=2)
                    marker_disagreement_cm[aruco_id] = float(dists_m.max() * 100.0)
                else:
                    marker_disagreement_cm[aruco_id] = None

                quats = []
                for o in obs_list:
                    R = _R_from_yaw_pitch_roll_deg(o.yaw_deg, o.pitch_deg, o.roll_deg)
                    quats.append(pose_filter.R_to_quat(R))
                fused_quat = _avg_quaternion(quats, list(weights))
                fused_R = pose_filter.quat_to_R(fused_quat)
                from . import pose as pose_mod  # local import avoids cycle on init
                yaw, pitch, roll = pose_mod.R_to_euler_zyx_deg(fused_R)

                # Use most-recent observation's metadata (placement, person).
                latest = max(obs_list, key=lambda o: weights[obs_list.index(o)])
                fused_err = float((np.array([o.reproj_error_px for o in obs_list]) * weights).sum() / wsum)

                fused_markers.append(MarkerObservation(
                    aruco_id=aruco_id,
                    placement=latest.placement,
                    person_id=latest.person_id,
                    person_name=latest.person_name,
                    world_xyz=(float(fused_xyz[0]), float(fused_xyz[1]), float(fused_xyz[2])),
                    yaw_deg=yaw,
                    pitch_deg=pitch,
                    roll_deg=roll,
                    reproj_error_px=fused_err,
                ))
                marker_witnesses[aruco_id] = sorted(cam_ids)

            people = scene_mod.fuse_person_observations(fused_markers)

            return {
                "world_frame": primary_frame or {
                    "floor_w_m": 5.0, "floor_h_m": 4.0,
                    "camera_position_world_m": None,
                },
                "markers": [
                    {
                        **scene_mod.serialize_marker(m),
                        "witness_camera_ids": marker_witnesses.get(m.aruco_id, []),
                        "disagreement_cm": (
                            round(marker_disagreement_cm.get(m.aruco_id), 2)
                            if marker_disagreement_cm.get(m.aruco_id) is not None
                            else None
                        ),
                    }
                    for m in fused_markers
                ],
                "people": [scene_mod.serialize_person(p) for p in people],
                "cameras": cameras_summary,
                "max_age_s": self.max_age_s,
                "ts": now,
            }


# Module-level singleton.  Created lazily so importing this module from a
# test harness without an event loop doesn't blow up.
_aggregator: Optional[SceneAggregator] = None


def get_aggregator() -> SceneAggregator:
    global _aggregator
    if _aggregator is None:
        _aggregator = SceneAggregator()
    return _aggregator
