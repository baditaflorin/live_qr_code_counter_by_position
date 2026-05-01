"""Server-side RTSP / IP-camera ingest workers.

For installations with permanently-mounted cameras (rooftop, hallway, etc.)
the browser-publishes-frames model isn't ergonomic.  This module spawns one
asyncio task per camera with `rtsp_enabled=True`; each task:

  - opens the URL with `cv2.VideoCapture`
  - reads frames in a thread (blocking call wrapped in `run_in_executor`)
  - runs the same detection → pose → world-fusion pipeline that
    /ws/detect runs, then publishes to the SceneAggregator
  - reports liveness (last frame ts, fps, errors) so admin can see status

Workers self-restart with exponential backoff when the connection drops.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from . import detection as detection_mod
from . import pose as pose_mod
from . import pose_filter as pose_filter_mod
from . import scene as scene_mod
from . import scene_state as scene_state_mod
from . import control as control_mod


@dataclass
class WorkerStatus:
    camera_id: int
    url: str
    state: str = "stopped"        # stopped | connecting | running | error
    last_frame_ts: Optional[float] = None
    frames_processed: int = 0
    last_error: Optional[str] = None
    fps: float = 0.0


class _Worker:
    def __init__(self, camera_id: int, url: str, marker_meta_loader):
        self.status = WorkerStatus(camera_id=camera_id, url=url)
        self._marker_meta_loader = marker_meta_loader
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._frame_times: list[float] = []
        self._pose_filters: dict[int, pose_filter_mod.PoseFilter] = {}

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._task, timeout=2.0)
            self._task = None
        self.status.state = "stopped"

    async def _run(self) -> None:
        loop = asyncio.get_event_loop()
        backoff = 1.0
        cam_loader = _load_camera_or_none
        while not self._stop.is_set():
            self.status.state = "connecting"
            cap = await loop.run_in_executor(None, lambda: cv2.VideoCapture(self.status.url))
            if not cap.isOpened():
                self.status.state = "error"
                self.status.last_error = "VideoCapture failed to open URL"
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
                continue

            self.status.state = "running"
            self.status.last_error = None
            backoff = 1.0
            aggregator = scene_state_mod.get_aggregator()

            try:
                while not self._stop.is_set():
                    ok, frame = await loop.run_in_executor(None, cap.read)
                    if not ok or frame is None:
                        self.status.state = "error"
                        self.status.last_error = "frame read failed"
                        break
                    now = time.time()
                    self._frame_times.append(now)
                    cutoff = now - 2.0
                    while self._frame_times and self._frame_times[0] < cutoff:
                        self._frame_times.pop(0)
                    if len(self._frame_times) >= 2:
                        self.status.fps = (len(self._frame_times) - 1) / max(0.1,
                            self._frame_times[-1] - self._frame_times[0])

                    cam = cam_loader(self.status.camera_id)
                    if cam is None or cam.get("K") is None:
                        # Not yet calibrated — just count the frame, skip pose.
                        self.status.last_frame_ts = now
                        self.status.frames_processed += 1
                        continue

                    results = detection_mod.detect(frame)
                    person_results = [d for d in results
                                      if not control_mod.is_control_id(d.aruco_id)]
                    poses = detection_mod.estimate_pose(
                        person_results,
                        np.array(cam["K"], dtype=np.float64),
                        np.array(cam["dist"], dtype=np.float64),
                        cam["marker_size_m"],
                        filters=self._pose_filters,
                        ts=now,
                    )

                    if cam.get("R") is not None and poses:
                        extrinsic = pose_mod.Extrinsic(
                            R=np.array(cam["R"], dtype=np.float64),
                            t=np.array(cam["t"], dtype=np.float64),
                        )
                        marker_meta = self._marker_meta_loader(
                            {d.aruco_id for d in person_results}
                        )
                        marker_obs = scene_mod.build_marker_observations(
                            person_results, poses, extrinsic, marker_meta,
                        )
                        coverage = round(100.0 * len(poses) / max(1, len(person_results)), 1)
                        await aggregator.update_camera(
                            camera_id=cam["id"],
                            camera_name=cam.get("name") or f"camera-{cam['id']}",
                            markers=marker_obs,
                            world_frame={
                                "floor_w_m": cam["floor_w_m"],
                                "floor_h_m": cam["floor_h_m"],
                                "camera_position_world_m": cam.get("camera_pos_world"),
                            },
                            fps=self.status.fps,
                            intrinsic_calibrated=True,
                            extrinsic_calibrated=True,
                            coverage_pct=coverage,
                        )

                    self.status.last_frame_ts = now
                    self.status.frames_processed += 1
            finally:
                cap.release()
                await aggregator.remove_camera(self.status.camera_id)


def _load_camera_or_none(camera_id: int) -> Optional[dict]:
    """Local copy of main._load_active_camera so we don't import main (cycle)."""
    from .db import Camera, SessionLocal
    db = SessionLocal()
    try:
        c = db.get(Camera, camera_id)
        if c is None:
            return None
        cam_pos = None
        if c.has_extrinsic():
            try:
                ext = pose_mod.Extrinsic(
                    R=np.array(c.R(), dtype=np.float64),
                    t=np.array(c.t(), dtype=np.float64),
                )
                cam_pos = ext.camera_position_world().tolist()
            except Exception:
                cam_pos = None
        return {
            "id": c.id,
            "name": c.name,
            "marker_size_m": c.marker_size_m,
            "K": c.K(), "dist": c.dist(),
            "R": c.R(), "t": c.t(),
            "floor_w_m": c.floor_rect_w_m,
            "floor_h_m": c.floor_rect_h_m,
            "corner_ids": c.corner_ids() or {},
            "camera_pos_world": cam_pos,
        }
    finally:
        db.close()


# ---------- registry --------------------------------------------------------

class WorkerRegistry:
    """Manages the lifecycle of every per-camera RTSP worker."""

    def __init__(self):
        self._workers: dict[int, _Worker] = {}
        self._lock = asyncio.Lock()
        self._marker_meta_loader = lambda ids: {}

    def set_marker_meta_loader(self, loader) -> None:
        """Inject the function that maps a set of aruco_ids to per-marker
        person/placement metadata.  Kept injectable so this module doesn't
        import main and create a cycle."""
        self._marker_meta_loader = loader

    async def reconcile(self) -> None:
        """Compare DB state to running workers, start/stop to match."""
        from .db import Camera, SessionLocal
        db = SessionLocal()
        try:
            cams = db.query(Camera).filter(Camera.rtsp_enabled.is_(True)).all()
            wanted = {c.id: c.rtsp_url for c in cams if c.rtsp_url}
        finally:
            db.close()

        async with self._lock:
            # Stop workers no longer wanted (disabled or url cleared).
            for cid in list(self._workers.keys()):
                if cid not in wanted or self._workers[cid].status.url != wanted[cid]:
                    await self._workers[cid].stop()
                    del self._workers[cid]
            # Start workers that should be running.
            for cid, url in wanted.items():
                if cid not in self._workers:
                    w = _Worker(cid, url, self._marker_meta_loader)
                    w.start()
                    self._workers[cid] = w

    def status(self) -> list[dict]:
        return [
            {
                "camera_id": w.status.camera_id,
                "url": w.status.url,
                "state": w.status.state,
                "fps": round(w.status.fps, 1),
                "frames_processed": w.status.frames_processed,
                "last_frame_ts": w.status.last_frame_ts,
                "last_error": w.status.last_error,
            }
            for w in self._workers.values()
        ]


_registry: Optional[WorkerRegistry] = None


def get_registry() -> WorkerRegistry:
    global _registry
    if _registry is None:
        _registry = WorkerRegistry()
    return _registry
