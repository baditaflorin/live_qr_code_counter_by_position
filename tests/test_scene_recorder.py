"""Scene recorder + replay tests."""
import asyncio
import time

import pytest

from backend.scene_recorder import SceneRecorder, stream_for_playback, delete_recording


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _scene(i):
    return {
        "world_frame": {"floor_w_m": 5.0, "floor_h_m": 4.0, "camera_position_world_m": None},
        "markers": [{"aruco_id": i, "world_xyz_m": [i, 0, 0]}],
        "people": [],
        "cameras": [],
    }


def test_record_then_playback_yields_same_frames():
    async def t():
        rec = SceneRecorder()
        info = await rec.start("test-record")
        rid = info["id"]
        for i in range(5):
            rec.write(_scene(i))
            await asyncio.sleep(0.02)
        stop_info = await rec.stop()
        assert stop_info["frames"] == 5
        assert stop_info["bytes"] > 0

        rows = []
        async for row in stream_for_playback(rid, speed=20.0):
            rows.append(row)
        assert len(rows) == 5
        # Recovered marker IDs should match what we wrote.
        assert [r["scene_world"]["markers"][0]["aruco_id"] for r in rows] == [0, 1, 2, 3, 4]
        # rel_t is monotonic and starts at ~0.
        assert all(rows[i]["rel_t"] <= rows[i + 1]["rel_t"] for i in range(len(rows) - 1))
        assert rows[0]["rel_t"] >= 0.0
        delete_recording(rid)
    _run(t())


def test_double_start_raises():
    async def t():
        rec = SceneRecorder()
        info = await rec.start("first")
        with pytest.raises(RuntimeError):
            await rec.start("second")
        await rec.stop()
        delete_recording(info["id"])
    _run(t())


def test_stop_without_active_returns_none():
    async def t():
        rec = SceneRecorder()
        result = await rec.stop()
        assert result is None
    _run(t())


def test_write_when_inactive_is_a_noop():
    async def t():
        rec = SceneRecorder()
        # Must not raise.
        rec.write(_scene(0))
    _run(t())


def test_playback_speed_compresses_real_time():
    """A 1 s recording at 10× should replay in ~0.1 s, not 1 s."""
    async def t():
        rec = SceneRecorder()
        info = await rec.start("speed-test")
        rid = info["id"]
        for _ in range(10):
            rec.write(_scene(0))
            await asyncio.sleep(0.05)  # ~0.5 s total
        await rec.stop()

        start = time.monotonic()
        rows = []
        async for row in stream_for_playback(rid, speed=20.0):
            rows.append(row)
        elapsed = time.monotonic() - start
        assert elapsed < 0.3, f"replay took {elapsed:.2f}s; expected <0.3s at 20×"
        assert len(rows) == 10
        delete_recording(rid)
    _run(t())


def test_delete_removes_file_and_db_row():
    async def t():
        rec = SceneRecorder()
        info = await rec.start("delete-test")
        rid = info["id"]
        rec.write(_scene(0))
        await rec.stop()

        # Delete should succeed.
        ok = delete_recording(rid)
        assert ok is True

        # Re-deleting returns False (nothing to remove).
        assert delete_recording(rid) is False
    _run(t())
