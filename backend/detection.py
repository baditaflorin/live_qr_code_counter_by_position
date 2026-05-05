"""Detector abstraction with runtime-tunable configuration.

Detection has two layers:

1. **2D detection** — `detect()` returns `Detection` (corners + center) for
   every visible marker.  Always runs.
2. **6-DOF pose** (ADR 0048) — `estimate_pose()` adds `(rvec, tvec)` per
   detection when intrinsics are available.  Returned as a `PoseDetection`.

`estimate_pose()` optionally accepts a per-marker `PoseFilter` dict that
resolves the IPPE_SQUARE flip ambiguity using temporal continuity and
applies a quaternion-slerp smoother — see `pose_filter.py`.

The pose layer is intentionally separate so the live overlay (which only
needs 2D corners) doesn't pay the calibration-required tax, and so the
WS payload can fall through gracefully on uncalibrated cameras.

Detectors (AprilTag, ArUco) are created via factory pattern with
runtime-configurable parameters (see detector_config.py, detector_factory.py).
"""
import os
import threading
import time as _time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from . import pose_filter as _pose_filter
from .detector_config import DetectorConfig, ConfigManager
from .detector_factory import BaseDetector, create_detector

# Module-level state for detector and config (thread-safe)
_config_manager: Optional[ConfigManager] = None
_active_detector: Optional[BaseDetector] = None
_detector_lock = threading.RLock()


def _init_detector() -> None:
    """Initialize detector configuration and instance on module import."""
    global _config_manager, _active_detector

    if _config_manager is not None:
        return  # Already initialized

    # Load configuration: env → disk → defaults
    config = DetectorConfig.load_from_env()
    data_dir = os.environ.get("DATA_DIR", "./data")

    # Try to load from disk (overrides env if file exists)
    disk_config = DetectorConfig.load_from_disk(data_dir)
    if disk_config is not None:
        config = disk_config

    _config_manager = ConfigManager(config)
    _active_detector = create_detector(config)
    print(f"Detector initialized: {config.detector_type.value} (marker_size={config.marker_size_m}m)")


def get_config() -> DetectorConfig:
    """Get current detector configuration."""
    _init_detector()
    return _config_manager.get_config()  # type: ignore


def set_config(config: DetectorConfig, data_dir: str = "./data") -> None:
    """Update detector configuration and recreate detector instance (thread-safe)."""
    global _active_detector
    _init_detector()

    with _detector_lock:
        _config_manager.set_config(config)  # type: ignore
        _active_detector = create_detector(config)
        config.save_to_disk(data_dir)
        print(f"Detector reconfigured: {config.detector_type.value}")


def get_detector() -> BaseDetector:
    """Get the active detector instance."""
    _init_detector()
    return _active_detector  # type: ignore


def get_dictionary_name() -> str:
    """Get the name of the active detector's marker dictionary."""
    return get_detector().get_dictionary_name()


def dictionary_size() -> int:
    """Get the number of unique markers in the active detector's dictionary."""
    return get_detector().dictionary_size()


def get_dictionary():
    """Get the active detector instance (for backwards compatibility)."""
    return get_detector()


@dataclass
class Detection:
    tag_id: int
    corners: list[list[float]]  # 4 corners as [[x,y]...] in TL, TR, BR, BL order
    center: list[float]
    # Raw 4x2 numpy corners — kept around for pose estimation downstream.
    _raw_corners: np.ndarray = None  # type: ignore[assignment]
    # Legacy field for backwards compatibility with code using aruco_id
    @property
    def aruco_id(self) -> int:
        return self.tag_id


@dataclass
class PoseDetection:
    tag_id: int
    rvec: np.ndarray  # (3,) Rodrigues rotation in camera frame
    tvec: np.ndarray  # (3,) translation in camera frame, metres
    reproj_error_px: float
    # Legacy field for backwards compatibility
    @property
    def aruco_id(self) -> int:
        return self.tag_id


def detect(frame_bgr: np.ndarray) -> list[Detection]:
    """Detect markers in frame using the active detector."""
    with _detector_lock:
        detector = get_detector()
        return detector.detect(frame_bgr)


# ---------- ADR 0048 pose helpers -----------------------------------------------

# Standard marker corner template in marker frame, X-right Y-down Z-out
# (matches OpenCV's solvePnP convention).  Ordered TL, TR, BR, BL — same as
# what `detectMarkers` returns.
def _marker_object_points(side_m: float) -> np.ndarray:
    half = side_m / 2.0
    return np.array(
        [
            [-half,  half, 0.0],
            [ half,  half, 0.0],
            [ half, -half, 0.0],
            [-half, -half, 0.0],
        ],
        dtype=np.float32,
    )


def estimate_pose_apriltag(
    detections: list[Detection],
    K: np.ndarray,
    dist: np.ndarray,
    marker_size_m: float,
    *,
    filters: Optional[dict[int, "_pose_filter.PoseFilter"]] = None,
    ts: Optional[float] = None,
) -> dict[int, PoseDetection]:
    """AprilTag-specific pose estimation using IPPE (Internal Parameters Projection Error).

    Uses `cv2.solvePnPGeneric(SOLVEPNP_IPPE_SQUARE)` to obtain *both* candidate
    solutions for the planar 4-point case, then resolves the flip ambiguity
    via the per-marker `PoseFilter` (closest-to-previous on rotation) and
    applies temporal smoothing.  Without `filters`, falls back to the
    lower-reprojection candidate per frame (legacy behaviour).
    """
    if not detections:
        return {}
    K = np.asarray(K, dtype=np.float64)
    dist = np.asarray(dist, dtype=np.float64).reshape(-1)
    obj_pts = _marker_object_points(marker_size_m)
    ts = ts if ts is not None else _time.time()

    out: dict[int, PoseDetection] = {}
    for d in detections:
        img_pts = d._raw_corners.reshape(-1, 1, 2).astype(np.float32)
        candidates = _pose_filter.solve_pose_ippe(img_pts, obj_pts, K, dist)
        if not candidates:
            continue

        if filters is not None:
            f = filters.setdefault(d.tag_id, _pose_filter.PoseFilter())
            res = f.update(candidates, ts)
            if res is None:
                continue
            rvec, tvec, err = res
        else:
            best = min(candidates, key=lambda c: c.reproj_error_px)
            rvec, tvec, err = best.rvec, best.tvec, best.reproj_error_px

        out[d.tag_id] = PoseDetection(
            tag_id=d.tag_id,
            rvec=np.asarray(rvec).reshape(3),
            tvec=np.asarray(tvec).reshape(3),
            reproj_error_px=err,
        )
    return out


def estimate_pose(
    detections: list[Detection],
    K: np.ndarray,
    dist: np.ndarray,
    marker_size_m: float,
    *,
    filters: Optional[dict[int, "_pose_filter.PoseFilter"]] = None,
    ts: Optional[float] = None,
) -> dict[int, PoseDetection]:
    """6-DOF pose per detected marker (ADR 0048).

    Delegates to active detector. For AprilTag: uses `cv2.solvePnPGeneric(SOLVEPNP_IPPE_SQUARE)`
    to obtain *both* candidate solutions for the planar 4-point case, then resolves the flip
    ambiguity via the per-marker `PoseFilter` (closest-to-previous on rotation) and
    applies temporal smoothing.  Without `filters`, falls back to the lower-reprojection
    candidate per frame (legacy behaviour).
    """
    with _detector_lock:
        detector = get_detector()
        return detector.estimate_pose(detections, K, dist, marker_size_m, filters=filters, ts=ts)


# ---------- zone helpers (unchanged) ---------------------------------------

def point_in_polygon(point: tuple[float, float], polygon: list[list[float]]) -> bool:
    """Ray-casting test. polygon is list of [x,y] in same coord system as point."""
    if len(polygon) < 3:
        return False
    x, y = point
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersect = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
        )
        if intersect:
            inside = not inside
        j = i
    return inside


def assign_zone(
    center_norm: tuple[float, float],
    zones: list[dict],
) -> Optional[int]:
    """Return zone id for first matching zone (zones are tested in order)."""
    for z in zones:
        if point_in_polygon(center_norm, z["polygon"]):
            return z["id"]
    return None
