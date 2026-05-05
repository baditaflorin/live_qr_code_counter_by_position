"""AprilTag detection helpers (migrated from ArUco).

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

Uses AprilTag family tag36h11 (587 unique IDs).
"""
import time as _time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from pupil_apriltags import Detector

from . import pose_filter as _pose_filter

FAMILY = "tag36h11"
MARKER_SIZE_M = 0.05  # Default physical size in metres (can be overridden per-camera)

_detector = Detector(families=FAMILY, nthreads=1, quad_decimate=2.0, quad_sigma=0.0, refine_edges=True, decode_sharpening=0.25, debug=False)


def get_dictionary_name() -> str:
    return FAMILY


def get_dictionary():
    return _detector


def dictionary_size() -> int:
    """Number of unique markers in tag36h11 family."""
    return 587


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
    if frame_bgr is None or frame_bgr.size == 0:
        return []
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    detections = _detector.detect(gray, estimate_tag_pose=False)
    out: list[Detection] = []
    for detection in detections:
        tag_id = detection.tag_id
        # AprilTag corners come as [[x,y], [x,y], [x,y], [x,y]] in order TL, TR, BR, BL
        corners_array = np.array(detection.corners, dtype=np.float32)  # Shape (4, 2)
        center = corners_array.mean(axis=0)
        out.append(
            Detection(
                tag_id=int(tag_id),
                corners=[[float(p[0]), float(p[1])] for p in corners_array],
                center=[float(center[0]), float(center[1])],
                _raw_corners=corners_array,
            )
        )
    return out


# ---------- ADR 0048 pose ---------------------------------------------------

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
