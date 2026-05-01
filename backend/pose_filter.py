"""Per-marker pose smoothing + IPPE flip-ambiguity resolution.

`cv2.solvePnP(SOLVEPNP_IPPE_SQUARE)` returns one solution but the underlying
solver computes two; `cv2.solvePnPGeneric` exposes both.  For a planar
4-point marker the second solution is related to the first by a ~180°
rotation about an axis lying *in* the marker plane.  At oblique viewing
angles (or partial occlusion) the wrong one can win on reprojection error
alone, producing a frame where the marker appears to flip 180°.

This module:
  - returns both candidate solutions (`solve_pose_ippe`)
  - keeps a per-marker history (`PoseFilter`) and picks whichever candidate is
    closest in rotation to the smoothed previous pose
  - applies a quaternion-slerp + tvec-EMA smoother to suppress single-frame
    jitter; state decays out after `max_age_s` so a marker that reappears
    doesn't snap to stale orientation
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np


# ---------- quaternion helpers ---------------------------------------------

def R_to_quat(R: np.ndarray) -> np.ndarray:
    """3x3 rotation matrix → unit quaternion [w, x, y, z] (Shepperd's method)."""
    R = np.asarray(R, dtype=np.float64)
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0:
        S = math.sqrt(tr + 1.0) * 2
        qw = 0.25 * S
        qx = (R[2, 1] - R[1, 2]) / S
        qy = (R[0, 2] - R[2, 0]) / S
        qz = (R[1, 0] - R[0, 1]) / S
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        S = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        qw = (R[2, 1] - R[1, 2]) / S
        qx = 0.25 * S
        qy = (R[0, 1] + R[1, 0]) / S
        qz = (R[0, 2] + R[2, 0]) / S
    elif R[1, 1] > R[2, 2]:
        S = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        qw = (R[0, 2] - R[2, 0]) / S
        qx = (R[0, 1] + R[1, 0]) / S
        qy = 0.25 * S
        qz = (R[1, 2] + R[2, 1]) / S
    else:
        S = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        qw = (R[1, 0] - R[0, 1]) / S
        qx = (R[0, 2] + R[2, 0]) / S
        qy = (R[1, 2] + R[2, 1]) / S
        qz = 0.25 * S
    q = np.array([qw, qx, qy, qz], dtype=np.float64)
    return q / np.linalg.norm(q)


def quat_to_R(q: np.ndarray) -> np.ndarray:
    qw, qx, qy, qz = q
    return np.array([
        [1 - 2*(qy*qy + qz*qz),  2*(qx*qy - qz*qw),     2*(qx*qz + qy*qw)],
        [2*(qx*qy + qz*qw),      1 - 2*(qx*qx + qz*qz), 2*(qy*qz - qx*qw)],
        [2*(qx*qz - qy*qw),      2*(qy*qz + qx*qw),     1 - 2*(qx*qx + qy*qy)],
    ], dtype=np.float64)


def quat_slerp(q1: np.ndarray, q2: np.ndarray, t: float) -> np.ndarray:
    """Spherical lerp from q1 to q2 by t ∈ [0,1]."""
    dot = float(np.dot(q1, q2))
    if dot < 0.0:
        q2 = -q2
        dot = -dot
    if dot > 0.9995:
        out = q1 + t * (q2 - q1)
        return out / np.linalg.norm(out)
    theta_0 = math.acos(min(1.0, dot))
    theta = theta_0 * t
    sin_t0 = math.sin(theta_0)
    s1 = math.sin(theta_0 - theta) / sin_t0
    s2 = math.sin(theta) / sin_t0
    return s1 * q1 + s2 * q2


def quat_angle_deg(q1: np.ndarray, q2: np.ndarray) -> float:
    """Geodesic angle between two unit quaternions, in degrees."""
    dot = abs(float(np.dot(q1, q2)))
    return math.degrees(2.0 * math.acos(min(1.0, dot)))


# ---------- candidate solver ------------------------------------------------

@dataclass
class PoseCandidate:
    rvec: np.ndarray          # (3,) Rodrigues
    tvec: np.ndarray          # (3,)
    reproj_error_px: float


def solve_pose_ippe(
    img_pts: np.ndarray,
    obj_pts: np.ndarray,
    K: np.ndarray,
    dist: np.ndarray,
) -> list[PoseCandidate]:
    """All valid IPPE_SQUARE solutions for one marker.

    `cv2.solvePnPGeneric` returns up to two solutions for SOLVEPNP_IPPE_SQUARE;
    we recompute reprojection error consistently with the same projection
    pipeline used elsewhere in the codebase.
    """
    try:
        ok, rvecs, tvecs, _solver_errors = cv2.solvePnPGeneric(
            obj_pts, img_pts, K, dist, flags=cv2.SOLVEPNP_IPPE_SQUARE
        )
    except cv2.error:
        return []
    if not ok:
        return []
    out: list[PoseCandidate] = []
    img_flat = img_pts.reshape(-1, 2)
    for rv, tv in zip(rvecs, tvecs):
        proj, _ = cv2.projectPoints(obj_pts, rv, tv, K, dist)
        err = float(np.mean(np.linalg.norm(proj.reshape(-1, 2) - img_flat, axis=1)))
        out.append(PoseCandidate(
            rvec=np.asarray(rv, dtype=np.float64).reshape(3),
            tvec=np.asarray(tv, dtype=np.float64).reshape(3),
            reproj_error_px=err,
        ))
    return out


# ---------- per-marker filter -----------------------------------------------

@dataclass
class _State:
    quat: np.ndarray  # smoothed unit quaternion (w, x, y, z)
    tvec: np.ndarray  # smoothed translation
    reproj_error_px: float
    last_ts: float


class PoseFilter:
    """One instance per (connection, marker_id).

    `update(candidates, ts)` picks the candidate closest in rotation to the
    previous smoothed orientation (ties → lowest reproj), applies quaternion
    slerp + translation EMA, and returns smoothed `(rvec, tvec, reproj_err)`
    suitable as a drop-in replacement for the raw solver output.

    State decays out after `max_age_s` seconds of no updates.
    """

    def __init__(self, alpha: float = 0.4, max_age_s: float = 1.5):
        self.alpha = float(alpha)
        self.max_age_s = float(max_age_s)
        self._state: Optional[_State] = None

    def update(
        self,
        candidates: list[PoseCandidate],
        ts: float,
    ) -> Optional[tuple[np.ndarray, np.ndarray, float]]:
        if not candidates:
            return None
        prev = self._state
        if prev is not None and (ts - prev.last_ts) > self.max_age_s:
            prev = None
            self._state = None

        # Disambiguate flip: prefer candidate closest in rotation to prev.
        # Without history, fall back to lowest reprojection error.
        cand_quats = []
        for c in candidates:
            R, _ = cv2.Rodrigues(c.rvec.reshape(3, 1))
            cand_quats.append(R_to_quat(R))

        if prev is None:
            best_i = min(range(len(candidates)), key=lambda i: candidates[i].reproj_error_px)
        else:
            best_i = min(
                range(len(candidates)),
                key=lambda i: quat_angle_deg(cand_quats[i], prev.quat),
            )
        chosen = candidates[best_i]
        chosen_quat = cand_quats[best_i]

        if prev is None:
            new_quat = chosen_quat
            new_tvec = chosen.tvec.copy()
            new_err  = chosen.reproj_error_px
        else:
            new_quat = quat_slerp(prev.quat, chosen_quat, self.alpha)
            new_tvec = (1 - self.alpha) * prev.tvec + self.alpha * chosen.tvec
            new_err  = (1 - self.alpha) * prev.reproj_error_px + self.alpha * chosen.reproj_error_px

        self._state = _State(
            quat=new_quat,
            tvec=new_tvec.copy(),
            reproj_error_px=new_err,
            last_ts=ts,
        )

        R = quat_to_R(new_quat)
        rvec, _ = cv2.Rodrigues(R)
        return rvec.reshape(3), new_tvec, new_err
