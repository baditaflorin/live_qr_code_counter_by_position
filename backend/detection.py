"""ArUco detection helpers.

Detection has two layers:

1. **2D detection** — `detect()` returns `Detection` (corners + center) for
   every visible marker.  Always runs.
2. **6-DOF pose** (ADR 0048) — `estimate_pose()` adds `(rvec, tvec)` per
   detection when intrinsics are available.  Returned as a `PoseDetection`.

The pose layer is intentionally separate so the live overlay (which only
needs 2D corners) doesn't pay the calibration-required tax, and so the
WS payload can fall through gracefully on uncalibrated cameras.
"""
import os
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

DICT_NAME = os.environ.get("ARUCO_DICTIONARY", "DICT_4X4_100")


def _resolve_dictionary(name: str):
    attr = getattr(cv2.aruco, name, None)
    if attr is None:
        raise ValueError(f"Unknown ArUco dictionary: {name}")
    return cv2.aruco.getPredefinedDictionary(attr)


_dictionary = _resolve_dictionary(DICT_NAME)
_params = cv2.aruco.DetectorParameters()
# Tweaks that help at distance / oblique angles.
_params.adaptiveThreshWinSizeMin = 5
_params.adaptiveThreshWinSizeMax = 35
_params.adaptiveThreshWinSizeStep = 6
_params.minMarkerPerimeterRate = 0.02
_params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX

_detector = cv2.aruco.ArucoDetector(_dictionary, _params)


def get_dictionary_name() -> str:
    return DICT_NAME


def get_dictionary():
    return _dictionary


def dictionary_size() -> int:
    """Number of unique markers in the active dictionary."""
    return int(_dictionary.bytesList.shape[0])


@dataclass
class Detection:
    aruco_id: int
    corners: list[list[float]]  # 4 corners as [[x,y]...]
    center: list[float]
    # Raw 4x2 numpy corners — kept around for pose estimation downstream.
    _raw_corners: np.ndarray = None  # type: ignore[assignment]


@dataclass
class PoseDetection:
    aruco_id: int
    rvec: np.ndarray  # (3,) Rodrigues rotation in camera frame
    tvec: np.ndarray  # (3,) translation in camera frame, metres
    reproj_error_px: float


def detect(frame_bgr: np.ndarray) -> list[Detection]:
    if frame_bgr is None or frame_bgr.size == 0:
        return []
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = _detector.detectMarkers(gray)
    out: list[Detection] = []
    if ids is None:
        return out
    for i, mid in enumerate(ids.flatten().tolist()):
        c = corners[i].reshape(-1, 2)  # 4x2
        center = c.mean(axis=0)
        out.append(
            Detection(
                aruco_id=int(mid),
                corners=[[float(p[0]), float(p[1])] for p in c],
                center=[float(center[0]), float(center[1])],
                _raw_corners=c.astype(np.float32),
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
) -> dict[int, PoseDetection]:
    """6-DOF pose per detected marker (ADR 0048).

    `cv2.aruco.estimatePoseSingleMarkers` was deprecated in OpenCV 4.7 in
    favour of `solvePnP` per marker; this helper uses the recommended path
    so it works across OpenCV 4.7–4.10 without warnings.

    Returns a dict keyed by `aruco_id`.  Markers with degenerate corners
    (rare; happens at the image edge) are silently skipped.
    """
    if not detections:
        return {}
    K = np.asarray(K, dtype=np.float64)
    dist = np.asarray(dist, dtype=np.float64).reshape(-1)
    obj_pts = _marker_object_points(marker_size_m)

    out: dict[int, PoseDetection] = {}
    for d in detections:
        img_pts = d._raw_corners.reshape(-1, 1, 2).astype(np.float32)
        try:
            ok, rvec, tvec = cv2.solvePnP(
                obj_pts, img_pts, K, dist, flags=cv2.SOLVEPNP_IPPE_SQUARE
            )
        except cv2.error:
            continue
        if not ok:
            continue
        proj, _ = cv2.projectPoints(obj_pts, rvec, tvec, K, dist)
        err = float(
            np.mean(np.linalg.norm(proj.reshape(-1, 2) - img_pts.reshape(-1, 2), axis=1))
        )
        out[d.aruco_id] = PoseDetection(
            aruco_id=d.aruco_id,
            rvec=rvec.reshape(3),
            tvec=tvec.reshape(3),
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
