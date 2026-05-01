"""SceneAggregator unit tests — multi-camera fusion + agreement metric."""
import asyncio
import math

import pytest

from backend.scene import MarkerObservation
from backend.scene_state import SceneAggregator


def _wf(cam_pos=None):
    return {
        "floor_w_m": 5.0, "floor_h_m": 4.0,
        "camera_position_world_m": cam_pos,
    }


def _obs(aruco_id, x, y, z, yaw=0.0, pitch=0.0, roll=0.0, err=0.5,
         placement="hat", person_id=1, person_name="Anna"):
    return MarkerObservation(
        aruco_id=aruco_id, placement=placement,
        person_id=person_id, person_name=person_name,
        world_xyz=(float(x), float(y), float(z)),
        yaw_deg=yaw, pitch_deg=pitch, roll_deg=roll,
        reproj_error_px=err,
    )


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_single_camera_passthrough():
    """One camera, one marker — fused output should match input within rounding."""
    async def t():
        agg = SceneAggregator()
        await agg.update_camera(1, "cam-A", [_obs(5, 2.5, 2.0, 1.2, yaw=15)],
                                _wf([2.5, -1, 3]), 10.0, True, True, 100.0)
        s = await agg.fused_scene()
        assert len(s["markers"]) == 1
        m = s["markers"][0]
        assert m["aruco_id"] == 5
        assert m["world_xyz_m"] == pytest.approx([2.5, 2.0, 1.2], abs=1e-3)
        assert abs(m["yaw_deg"] - 15.0) < 0.5
        assert m["disagreement_cm"] is None
        assert m["witness_camera_ids"] == [1]
    _run(t())


def test_two_cameras_position_weighted_average():
    """Two cameras with equal reproj should fuse to the midpoint."""
    async def t():
        agg = SceneAggregator()
        await agg.update_camera(1, "cam-A",
                                [_obs(5, 2.0, 2.0, 1.2, err=0.5)], _wf(), 10, True, True, 100)
        await agg.update_camera(2, "cam-B",
                                [_obs(5, 3.0, 2.0, 1.2, err=0.5)], _wf(), 10, True, True, 100)
        s = await agg.fused_scene()
        m = s["markers"][0]
        assert m["world_xyz_m"][0] == pytest.approx(2.5, abs=1e-3)
        # Disagreement: 1m apart in x → 100 cm.
        assert m["disagreement_cm"] == pytest.approx(100.0, abs=0.1)
        assert sorted(m["witness_camera_ids"]) == [1, 2]
    _run(t())


def test_lower_reproj_dominates_in_weighted_average():
    """A confident camera (reproj 0.2) should drag the fused position toward
    its estimate over an uncertain one (reproj 2.0)."""
    async def t():
        agg = SceneAggregator()
        await agg.update_camera(1, "cam-A",
                                [_obs(5, 2.0, 0, 0, err=0.2)], _wf(), 10, True, True, 100)
        await agg.update_camera(2, "cam-B",
                                [_obs(5, 3.0, 0, 0, err=2.0)], _wf(), 10, True, True, 100)
        s = await agg.fused_scene()
        # Weight ratio (1/0.29) : (1/4.25) ≈ 14.7 : 1, so fused x sits much
        # closer to 2.0 than 3.0.
        x = s["markers"][0]["world_xyz_m"][0]
        assert x < 2.1, f"expected x near 2.0, got {x}"
    _run(t())


def test_yaw_circular_mean_handles_wrap():
    """Two yaws straddling ±180° should average to ±180°, not 0°."""
    async def t():
        agg = SceneAggregator()
        await agg.update_camera(1, "cam-A",
                                [_obs(5, 0, 0, 0, yaw=170, err=0.5)], _wf(), 10, True, True, 100)
        await agg.update_camera(2, "cam-B",
                                [_obs(5, 0, 0, 0, yaw=-170, err=0.5)], _wf(), 10, True, True, 100)
        s = await agg.fused_scene()
        yaw = s["markers"][0]["yaw_deg"]
        # Should be ~±180°, not the linear average ~0°.
        assert abs(yaw) > 170, f"expected ~±180°, got {yaw}"
    _run(t())


def test_per_camera_mean_reproj_error():
    """Each camera summary reports the mean reproj across its markers."""
    async def t():
        agg = SceneAggregator()
        await agg.update_camera(7, "cam-X",
                                [_obs(1, 0, 0, 0, err=0.4),
                                 _obs(2, 1, 0, 0, err=0.6)],
                                _wf(), 12.0, True, True, 100)
        s = await agg.fused_scene()
        cam = next(c for c in s["cameras"] if c["camera_id"] == 7)
        assert cam["mean_reproj_error_px"] == pytest.approx(0.5, abs=1e-9)
        assert cam["marker_count"] == 2
    _run(t())


def test_stale_camera_drops_after_max_age():
    """A camera that hasn't published within max_age_s shouldn't appear in
    the fused scene."""
    async def t():
        agg = SceneAggregator(max_age_s=0.01)
        await agg.update_camera(1, "cam-A",
                                [_obs(5, 0, 0, 0)], _wf(), 10, True, True, 100)
        # Sleep past max_age then ask for fused scene.
        await asyncio.sleep(0.05)
        s = await agg.fused_scene()
        assert s["cameras"] == []
        assert s["markers"] == []
    _run(t())


def test_remove_camera_cleans_up_immediately():
    async def t():
        agg = SceneAggregator()
        await agg.update_camera(1, "cam-A",
                                [_obs(5, 0, 0, 0)], _wf(), 10, True, True, 100)
        await agg.remove_camera(1)
        s = await agg.fused_scene()
        assert s["cameras"] == []
    _run(t())
