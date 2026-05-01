"""Geometry helpers for ADR 0048 (per-marker 6-DOF pose) and ADR 0050 (world-frame fusion).

Conventions used everywhere:

* Camera frame: OpenCV — X right, Y down, Z forward (out of the camera).
* World frame:  X right, Y forward (along the long edge of the floor rectangle),
                Z up.  This matches how a person standing in the room expects
                to read coordinates.
* `(R_wc, t_wc)` is **world->camera** — the convention `solvePnP` returns and
  the convention OpenCV uses internally.  Inverting it gives the camera's
  position in world coordinates: `cam_pos_world = -R_wc.T @ t_wc`.
* Yaw / pitch / roll are intrinsic Z-Y-X Euler angles in the world frame,
  in degrees, with yaw measured CCW around world Z (so a marker rotating
  toward +X has yaw 0°; toward +Y, yaw 90°).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np


# ---------- ChArUco board (ADR 0048) ----------------------------------------

# A 5x7 board with 4cm squares + 3cm markers prints nicely on a single A4
# page and gives ~24 ChArUco corners per fully visible view, which is
# generous for `calibrateCameraCharuco`.
CHARUCO_SQUARES_X = 5
CHARUCO_SQUARES_Y = 7
CHARUCO_SQUARE_LEN_M = 0.04
CHARUCO_MARKER_LEN_M = 0.03


def make_charuco_board(dictionary):
    """Build the ChArUco board used for intrinsic calibration.

    Uses the project's active ArUco dictionary so the same detector pipeline
    can decode it without a second dictionary.
    """
    return cv2.aruco.CharucoBoard(
        (CHARUCO_SQUARES_X, CHARUCO_SQUARES_Y),
        CHARUCO_SQUARE_LEN_M,
        CHARUCO_MARKER_LEN_M,
        dictionary,
    )


def render_charuco_board_png(dictionary, size_px: int = 1500) -> bytes:
    """Render the calibration board as a printable PNG."""
    board = make_charuco_board(dictionary)
    aspect = CHARUCO_SQUARES_X / CHARUCO_SQUARES_Y
    h = size_px
    w = max(1, int(round(h * aspect)))
    img = board.generateImage((w, h), marginSize=20, borderBits=1)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("Failed to encode ChArUco board PNG")
    return bytes(buf)


# ---------- rvec / tvec / Euler --------------------------------------------

def rvec_to_R(rvec: np.ndarray) -> np.ndarray:
    """OpenCV Rodrigues rotation vector → 3x3 rotation matrix."""
    R, _ = cv2.Rodrigues(np.asarray(rvec, dtype=np.float64).reshape(3, 1))
    return R


def R_to_euler_zyx_deg(R: np.ndarray) -> tuple[float, float, float]:
    """3x3 rotation matrix → intrinsic Z-Y-X Euler angles (yaw, pitch, roll) in degrees.

    yaw   = rotation around Z (up)        — heading
    pitch = rotation around Y (forward)   — nodding
    roll  = rotation around X (right)     — tilting
    Singular near pitch = ±90°; we fall back to roll = 0 there.
    """
    R = np.asarray(R, dtype=np.float64)
    sy = math.hypot(R[0, 0], R[1, 0])
    if sy > 1e-6:
        yaw   = math.atan2(R[1, 0], R[0, 0])
        pitch = math.atan2(-R[2, 0], sy)
        roll  = math.atan2(R[2, 1], R[2, 2])
    else:
        yaw   = math.atan2(-R[1, 2], R[1, 1])
        pitch = math.atan2(-R[2, 0], sy)
        roll  = 0.0
    return math.degrees(yaw), math.degrees(pitch), math.degrees(roll)


# ---------- world / camera transforms (ADR 0012 + 0050) --------------------

@dataclass
class Extrinsic:
    """world->camera rigid transform.  `R @ p_world + t = p_camera`."""
    R: np.ndarray  # (3,3)
    t: np.ndarray  # (3,)

    @classmethod
    def from_rvec_tvec(cls, rvec: np.ndarray, tvec: np.ndarray) -> "Extrinsic":
        return cls(R=rvec_to_R(rvec), t=np.asarray(tvec, dtype=np.float64).reshape(3))

    def camera_position_world(self) -> np.ndarray:
        """Where the camera sits in world coords."""
        return -self.R.T @ self.t

    def world_from_camera_point(self, p_cam: np.ndarray) -> np.ndarray:
        """Lift a point from camera frame into world frame."""
        return self.R.T @ (np.asarray(p_cam, dtype=np.float64).reshape(3) - self.t)

    def world_from_camera_rotation(self, R_cam: np.ndarray) -> np.ndarray:
        """Lift a rotation from camera frame into world frame."""
        return self.R.T @ R_cam


def marker_pose_world(
    rvec_cam: np.ndarray,
    tvec_cam: np.ndarray,
    extrinsic: Extrinsic,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-marker rvec/tvec in *camera* frame → (xyz_world, R_world).

    `estimatePoseSingleMarkers` returns the marker's pose in the camera frame
    (`R_cm`, `t_cm`).  Combined with the camera's world->camera extrinsic
    (`R_wc`, `t_wc`) this gives the marker's pose in the world frame:

        R_wm = R_wc.T @ R_cm
        t_wm = R_wc.T @ (t_cm - t_wc)

    so a stationary marker on the floor reports a constant world position
    regardless of which camera saw it.
    """
    R_cm = rvec_to_R(rvec_cam)
    t_cm = np.asarray(tvec_cam, dtype=np.float64).reshape(3)
    xyz_world = extrinsic.world_from_camera_point(t_cm)
    R_world = extrinsic.world_from_camera_rotation(R_cm)
    return xyz_world, R_world


# ---------- extrinsic from four floor-corner markers (ADR 0012) -------------

def solve_extrinsic_from_corners(
    corner_image_pts: dict[str, tuple[float, float]],
    floor_w_m: float,
    floor_h_m: float,
    K: np.ndarray,
    dist: np.ndarray,
) -> Optional[tuple[Extrinsic, float]]:
    """Compute world->camera extrinsic from the four floor-corner markers.

    `corner_image_pts` keys are 'tl' / 'tr' / 'br' / 'bl'.  World coordinates
    are assigned by ADR 0012 as:

        tl = (0, 0, 0)            tr = (W, 0, 0)
        bl = (0, H, 0)            br = (W, H, 0)

    All four corners lie on the floor (z=0).  `solvePnP` with `SOLVEPNP_IPPE`
    (planar 4-point) gives the unique pose.

    Returns (extrinsic, mean_reprojection_error_px) or None if unsolvable.
    """
    needed = ("tl", "tr", "br", "bl")
    if not all(k in corner_image_pts for k in needed):
        return None
    image_pts = np.array(
        [corner_image_pts[k] for k in needed], dtype=np.float32
    ).reshape(-1, 1, 2)
    world_pts = np.array(
        [
            [0.0, 0.0, 0.0],
            [floor_w_m, 0.0, 0.0],
            [floor_w_m, floor_h_m, 0.0],
            [0.0, floor_h_m, 0.0],
        ],
        dtype=np.float32,
    ).reshape(-1, 1, 3)
    K = np.asarray(K, dtype=np.float64)
    dist = np.asarray(dist, dtype=np.float64).reshape(-1)
    ok, rvec, tvec = cv2.solvePnP(
        world_pts, image_pts, K, dist, flags=cv2.SOLVEPNP_IPPE
    )
    if not ok:
        return None
    proj, _ = cv2.projectPoints(world_pts, rvec, tvec, K, dist)
    err = float(np.mean(np.linalg.norm(proj.reshape(-1, 2) - image_pts.reshape(-1, 2), axis=1)))
    return Extrinsic.from_rvec_tvec(rvec, tvec), err
