"""ArUco detection helpers."""
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


@dataclass
class Detection:
    aruco_id: int
    corners: list[list[float]]  # 4 corners as [[x,y]...]
    center: list[float]


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
            )
        )
    return out


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
