"""Camera-intrinsic calibration via ChArUco views (ADR 0048).

The flow:

1. Operator hits "Start" on the admin page.  Backend creates an in-memory
   `IntrinsicSession` keyed by id.
2. Browser POSTs JPEG frames as the operator waves the printed ChArUco board
   in front of the camera.  Each frame is decoded; only views with
   sufficient ChArUco corners *and* enough pose-novelty vs. previously
   accepted views are kept.
3. After ≥ MIN_VIEWS frames are collected, operator hits "Finish".
   We run `cv2.aruco.calibrateCameraCharuco` and persist `K`, `dist`, and
   the mean reprojection error onto the Camera row.

In-memory state is fine here: calibration is a foreground operator task
(< 1 minute), the result lives in the DB, and a server restart simply
forces the operator to redo it — preferable to half-committed state.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import cv2
import numpy as np
from sqlalchemy.orm import Session

from . import detection, pose
from .db import Camera


# Number of accepted views required before `finish` will compute calibration.
# OpenCV's planar calibration converges sloppily under 15 views; 20 is a
# robust floor that fits inside ~30s of waving the board around.
MIN_VIEWS = 20
# A view is "novel" if its ChArUco corner centroid moved at least this many
# pixels from every previously accepted view's centroid OR the average angle
# of the marker rotated by this many degrees.  Cheap-and-cheerful diversity
# filter that prevents a static board from accidentally producing 50 copies
# of the same view.
MIN_CENTROID_DELTA_PX = 40.0
MIN_ANGLE_DELTA_DEG = 8.0
# Calibration auto-fails (and surfaces an error to the operator) above this
# reprojection error.  ADR 0048 calls 1 px the warn-threshold; 3 px is the
# point where the calibration is junk and the user should redo it.
MAX_ACCEPTABLE_REPROJ_PX = 3.0


@dataclass
class _AcceptedView:
    charuco_corners: np.ndarray  # (N,1,2)
    charuco_ids: np.ndarray      # (N,1)
    image_size: tuple[int, int]
    centroid: tuple[float, float]
    mean_angle_deg: float


@dataclass
class IntrinsicSession:
    id: str
    camera_id: int
    created_at: float
    views: list[_AcceptedView] = field(default_factory=list)
    last_message: str = "Show the ChArUco board to the camera at varied angles."

    def status(self) -> dict:
        return {
            "session_id": self.id,
            "camera_id": self.camera_id,
            "views_accepted": len(self.views),
            "views_required": MIN_VIEWS,
            "ready": len(self.views) >= MIN_VIEWS,
            "message": self.last_message,
        }


_sessions: dict[str, IntrinsicSession] = {}
_sessions_lock = threading.Lock()


def start_session(camera_id: int) -> IntrinsicSession:
    sid = uuid.uuid4().hex[:12]
    sess = IntrinsicSession(id=sid, camera_id=camera_id, created_at=time.time())
    with _sessions_lock:
        # Garbage-collect sessions older than 30 minutes.
        cutoff = time.time() - 30 * 60
        for k in list(_sessions):
            if _sessions[k].created_at < cutoff:
                _sessions.pop(k, None)
        _sessions[sid] = sess
    return sess


def get_session(session_id: str) -> Optional[IntrinsicSession]:
    with _sessions_lock:
        return _sessions.get(session_id)


def discard_session(session_id: str) -> None:
    with _sessions_lock:
        _sessions.pop(session_id, None)


def _detect_charuco(frame_bgr: np.ndarray) -> Optional[_AcceptedView]:
    """Detect the ChArUco board in one frame.  Returns view metadata on success."""
    if frame_bgr is None or frame_bgr.size == 0:
        return None
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    dictionary = detection.get_dictionary()
    board = pose.make_charuco_board(dictionary)

    # detectMarkers is the same call the live pipeline uses; the board's
    # markers are in the same dictionary so they're picked up "for free".
    corners, ids, _ = cv2.aruco.ArucoDetector(dictionary).detectMarkers(gray)
    if ids is None or len(ids) < 4:
        return None
    n_corners, ch_corners, ch_ids = cv2.aruco.interpolateCornersCharuco(
        corners, ids, gray, board
    )
    if n_corners is None or n_corners < 8:
        return None

    pts = ch_corners.reshape(-1, 2)
    cx = float(pts[:, 0].mean())
    cy = float(pts[:, 1].mean())

    # Approximate the board's in-plane angle from the first few marker corners
    # — gives "rotated vs. last view" without needing a full pose solve.
    first = corners[0].reshape(-1, 2)
    dx = first[1, 0] - first[0, 0]
    dy = first[1, 1] - first[0, 1]
    angle = float(np.degrees(np.arctan2(dy, dx)))

    return _AcceptedView(
        charuco_corners=ch_corners,
        charuco_ids=ch_ids,
        image_size=(w, h),
        centroid=(cx, cy),
        mean_angle_deg=angle,
    )


def add_frame(session_id: str, frame_bgr: np.ndarray) -> dict:
    """Returns the session's status dict after attempting to add this frame."""
    sess = get_session(session_id)
    if sess is None:
        return {"error": "Unknown calibration session"}

    view = _detect_charuco(frame_bgr)
    if view is None:
        sess.last_message = "Board not detected — fill more of the frame and hold steady."
        return sess.status()

    # Reject if too similar to an existing view.
    for prev in sess.views:
        dx = view.centroid[0] - prev.centroid[0]
        dy = view.centroid[1] - prev.centroid[1]
        d_px = (dx * dx + dy * dy) ** 0.5
        d_ang = abs((view.mean_angle_deg - prev.mean_angle_deg + 180) % 360 - 180)
        if d_px < MIN_CENTROID_DELTA_PX and d_ang < MIN_ANGLE_DELTA_DEG:
            sess.last_message = "Move or tilt the board — that pose was already captured."
            return sess.status()

    sess.views.append(view)
    if len(sess.views) >= MIN_VIEWS:
        sess.last_message = "Enough views — press Finish to compute calibration."
    else:
        sess.last_message = (
            f"Captured view {len(sess.views)} of {MIN_VIEWS}. "
            "Vary tilt and distance for the best calibration."
        )
    return sess.status()


def finish(session_id: str, db: Session) -> dict:
    """Run `calibrateCameraCharuco` over the accepted views and persist the result."""
    sess = get_session(session_id)
    if sess is None:
        return {"error": "Unknown calibration session"}
    if len(sess.views) < MIN_VIEWS:
        return {
            "error": f"Need at least {MIN_VIEWS} views (have {len(sess.views)}). "
            "Capture more before finishing."
        }

    cam = db.get(Camera, sess.camera_id)
    if cam is None:
        return {"error": f"Camera {sess.camera_id} not found"}

    image_size = sess.views[0].image_size  # (w, h)
    board = pose.make_charuco_board(detection.get_dictionary())
    all_corners = [v.charuco_corners for v in sess.views]
    all_ids = [v.charuco_ids for v in sess.views]

    try:
        rms, K, dist, _, _ = cv2.aruco.calibrateCameraCharuco(
            charucoCorners=all_corners,
            charucoIds=all_ids,
            board=board,
            imageSize=image_size,
            cameraMatrix=None,
            distCoeffs=None,
        )
    except cv2.error as e:
        return {"error": f"OpenCV calibration failed: {e}"}

    rms = float(rms)
    if not np.isfinite(rms) or rms > MAX_ACCEPTABLE_REPROJ_PX:
        return {
            "error": (
                f"Reprojection error {rms:.2f}px is above the {MAX_ACCEPTABLE_REPROJ_PX}px "
                "limit — recapture with the board filling more of the frame."
            ),
            "reproj_error_px": rms,
        }

    cam.K_json = json.dumps(K.tolist())
    cam.dist_json = json.dumps(dist.flatten().tolist())
    cam.intrinsic_calibrated_at = datetime.utcnow()
    cam.intrinsic_reproj_error_px = rms
    cam.intrinsic_image_w = int(image_size[0])
    cam.intrinsic_image_h = int(image_size[1])
    db.commit()
    discard_session(session_id)
    return {
        "ok": True,
        "camera_id": cam.id,
        "reproj_error_px": rms,
        "image_w": cam.intrinsic_image_w,
        "image_h": cam.intrinsic_image_h,
        "views_used": len(sess.views),
    }


# ---------- extrinsic via four floor-corner markers (ADR 0012) -------------

def calibrate_extrinsic(
    db: Session,
    camera_id: int,
    detected_corner_centers: dict[str, tuple[float, float]],
) -> dict:
    """Solve world->camera extrinsic from the four floor-corner markers.

    `detected_corner_centers` maps 'tl'/'tr'/'br'/'bl' -> (px_x, px_y) in the
    most recent frame.  Persists R, t on the Camera row.
    """
    cam = db.get(Camera, camera_id)
    if cam is None:
        return {"error": f"Camera {camera_id} not found"}
    if not cam.has_intrinsic():
        return {
            "error": "Camera has no intrinsic calibration yet — run that first."
        }
    needed = ("tl", "tr", "br", "bl")
    missing = [k for k in needed if k not in detected_corner_centers]
    if missing:
        return {
            "error": f"Need all four floor-corner markers visible; missing: {', '.join(missing)}."
        }
    K = np.array(cam.K(), dtype=np.float64)
    dist = np.array(cam.dist(), dtype=np.float64)
    result = pose.solve_extrinsic_from_corners(
        detected_corner_centers,
        cam.floor_rect_w_m,
        cam.floor_rect_h_m,
        K,
        dist,
    )
    if result is None:
        return {"error": "solvePnP failed; check that the four corners form a sensible rectangle."}
    extrinsic, err = result
    cam.extrinsic_R_json = json.dumps(extrinsic.R.tolist())
    cam.extrinsic_t_json = json.dumps(extrinsic.t.tolist())
    cam.extrinsic_calibrated_at = datetime.utcnow()
    cam.extrinsic_reproj_error_px = err
    db.commit()
    return {
        "ok": True,
        "camera_id": cam.id,
        "reproj_error_px": err,
        "floor_rect_w_m": cam.floor_rect_w_m,
        "floor_rect_h_m": cam.floor_rect_h_m,
    }
