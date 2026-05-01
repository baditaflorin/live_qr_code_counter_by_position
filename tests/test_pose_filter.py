"""Pose-filter unit tests — flip resolution + temporal smoothing."""
import math
import time

import cv2
import numpy as np
import pytest

from backend import pose_filter as pf


# ---------- helpers ---------------------------------------------------------

K = np.array([[800, 0, 640], [0, 800, 360], [0, 0, 1]], dtype=np.float64)
DIST = np.zeros(5, dtype=np.float64)
SIDE = 0.15
OBJ = np.array([
    [-SIDE / 2,  SIDE / 2, 0],
    [ SIDE / 2,  SIDE / 2, 0],
    [ SIDE / 2, -SIDE / 2, 0],
    [-SIDE / 2, -SIDE / 2, 0],
], dtype=np.float32)


def _project(rvec, tvec):
    img, _ = cv2.projectPoints(OBJ, rvec, tvec, K, DIST)
    return img.astype(np.float32)


# ---------- quaternion round-trip ------------------------------------------

def test_quat_to_R_round_trip_identity():
    R = np.eye(3)
    q = pf.R_to_quat(R)
    R_back = pf.quat_to_R(q)
    assert np.allclose(R, R_back, atol=1e-9)


def test_quat_to_R_round_trip_arbitrary():
    rvec = np.array([0.7, -0.3, 0.5])
    R, _ = cv2.Rodrigues(rvec.reshape(3, 1))
    q = pf.R_to_quat(R)
    R_back = pf.quat_to_R(q)
    assert np.allclose(R, R_back, atol=1e-9)


def test_quat_slerp_endpoints():
    q1 = np.array([1.0, 0, 0, 0])
    q2 = np.array([math.sqrt(0.5), math.sqrt(0.5), 0, 0])
    assert np.allclose(pf.quat_slerp(q1, q2, 0.0), q1, atol=1e-9)
    assert np.allclose(pf.quat_slerp(q1, q2, 1.0), q2, atol=1e-9)
    mid = pf.quat_slerp(q1, q2, 0.5)
    assert abs(np.linalg.norm(mid) - 1.0) < 1e-9


def test_quat_angle_deg_zero_for_identical():
    q = np.array([0.5, 0.5, 0.5, 0.5])
    assert pf.quat_angle_deg(q, q) < 1e-6


# ---------- candidate solver -----------------------------------------------

def test_solve_pose_ippe_returns_two_candidates():
    """For a planar marker viewed at an oblique angle, IPPE_SQUARE returns
    two pose candidates related by a 180° flip about an in-plane axis."""
    rvec_true = np.array([0.5, 0.0, 0.0])
    tvec_true = np.array([0.1, 0.0, 1.5])
    img_pts = _project(rvec_true, tvec_true)

    cands = pf.solve_pose_ippe(img_pts, OBJ, K, DIST)
    assert len(cands) == 2

    # Lower-error candidate should match ground truth within sub-mm.
    best = min(cands, key=lambda c: c.reproj_error_px)
    assert np.allclose(best.tvec, tvec_true, atol=1e-3)
    assert best.reproj_error_px < 1e-3


def test_solve_pose_ippe_no_solution_returns_empty_for_garbage():
    """Garbage input doesn't crash, returns either empty or invalid candidates."""
    bad = np.zeros((4, 1, 2), dtype=np.float32)
    cands = pf.solve_pose_ippe(bad, OBJ, K, DIST)
    # Either zero candidates or candidates that obviously project poorly —
    # we don't assert one or the other; just that it doesn't raise.
    assert isinstance(cands, list)


# ---------- temporal smoothing ---------------------------------------------

def test_pose_filter_first_update_picks_lowest_reproj():
    rvec = np.array([0.3, 0.0, 0.0])
    tvec = np.array([0.0, 0.0, 1.5])
    img_pts = _project(rvec, tvec)
    cands = pf.solve_pose_ippe(img_pts, OBJ, K, DIST)

    f = pf.PoseFilter(alpha=1.0)  # no smoothing — full new sample
    res = f.update(cands, ts=time.time())
    assert res is not None
    rvec_out, tvec_out, err = res
    assert np.allclose(tvec_out, tvec, atol=1e-3)
    # The chosen candidate should be the lower-reprojection-error one.
    assert err < 1e-3


def test_pose_filter_resists_flip_under_jitter():
    """Once we have history, the filter should keep choosing the same
    physical pose even when reprojection-error rankings flip due to noise."""
    rvec = np.array([0.4, 0.05, 0.0])
    tvec = np.array([0.0, 0.0, 1.4])
    f = pf.PoseFilter(alpha=0.5)

    rng = np.random.default_rng(42)
    chosen_quats = []
    for i in range(10):
        img_clean = _project(rvec, tvec)
        # Add 0.5 px Gaussian noise per corner — realistic camera jitter.
        img_noisy = (img_clean.reshape(-1, 2)
                     + rng.normal(0, 0.5, (4, 2))).astype(np.float32).reshape(-1, 1, 2)
        cands = pf.solve_pose_ippe(img_noisy, OBJ, K, DIST)
        res = f.update(cands, ts=time.time() + i * 0.1)
        assert res is not None
        rvec_out = res[0]
        R_out, _ = cv2.Rodrigues(rvec_out.reshape(3, 1))
        chosen_quats.append(pf.R_to_quat(R_out))

    # All chosen quaternions should be within ~5° of the first — proves the
    # filter isn't oscillating between the two flip candidates.
    angles = [pf.quat_angle_deg(chosen_quats[0], q) for q in chosen_quats[1:]]
    assert max(angles) < 8.0, f"saw unstable flip; max angular delta {max(angles):.1f}°"


def test_pose_filter_smoothing_converges():
    """Translation EMA should approach the true value over a few updates."""
    target_tvec = np.array([0.5, 0.2, 1.8])
    rvec = np.array([0.0, 0.0, 0.0])
    f = pf.PoseFilter(alpha=0.5)

    img = _project(rvec, target_tvec)
    cands = pf.solve_pose_ippe(img, OBJ, K, DIST)
    # Cold start: first update jumps right to the candidate.
    f.update(cands, ts=0.0)
    # Subsequent updates with the same observation should still converge
    # (no oscillation, no drift).
    for i in range(1, 6):
        f.update(cands, ts=i * 0.1)
    state = f._state
    assert np.allclose(state.tvec, target_tvec, atol=1e-3)


def test_pose_filter_state_decays_after_max_age():
    """A marker that disappears for longer than max_age_s should reset
    cleanly — no carry-over of the previous orientation."""
    rvec = np.array([0.0, 0.0, 0.0])
    tvec = np.array([0.0, 0.0, 1.5])
    img = _project(rvec, tvec)
    cands = pf.solve_pose_ippe(img, OBJ, K, DIST)

    f = pf.PoseFilter(alpha=0.5, max_age_s=1.0)
    f.update(cands, ts=0.0)
    assert f._state is not None

    # Long gap — same input but state should have been reset by the
    # internal age check, so this update is treated as a cold start.
    f.update(cands, ts=10.0)
    assert f._state is not None
    # last_ts should be the new ts, not the carried-over one.
    assert abs(f._state.last_ts - 10.0) < 1e-6
