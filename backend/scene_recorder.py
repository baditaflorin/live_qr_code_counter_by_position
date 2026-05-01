"""Append-only scene recorder.  At most one recording active at a time.

When active, the /ws/scene loop calls `recorder.write(scene_world)` on every
fused tick.  The recorder stamps each line with `rel_t` (seconds since
recording start) and writes JSONL to `{DATA_DIR}/recordings/{id}.jsonl`.

Replay (`stream_for_playback`) reads the file back and yields lines at the
original cadence, modulated by a `speed` multiplier.  The same Three.js
scene viewer can render either the live aggregator or a replayed file.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional

from .db import DATA_DIR, SceneRecording, SessionLocal


REC_DIR = Path(DATA_DIR) / "recordings"
REC_DIR.mkdir(parents=True, exist_ok=True)


def _path_for(recording_id: int) -> Path:
    return REC_DIR / f"{recording_id}.jsonl"


@dataclass
class _ActiveRecording:
    recording_id: int
    name: str
    started_wall_ts: float
    file_handle: object         # open file
    frames_written: int = 0
    bytes_written: int = 0


class SceneRecorder:
    """Process-local singleton.  At most one active recording at a time."""

    def __init__(self):
        self._active: Optional[_ActiveRecording] = None
        self._lock = asyncio.Lock()

    @property
    def active(self) -> bool:
        return self._active is not None

    @property
    def active_info(self) -> Optional[dict]:
        a = self._active
        if a is None:
            return None
        return {
            "recording_id": a.recording_id,
            "name": a.name,
            "started_at": a.started_wall_ts,
            "frames_written": a.frames_written,
            "bytes_written": a.bytes_written,
            "elapsed_s": round(time.time() - a.started_wall_ts, 1),
        }

    async def start(self, name: str) -> dict:
        async with self._lock:
            if self._active is not None:
                raise RuntimeError("a recording is already active; stop it first")
            db = SessionLocal()
            try:
                rec = SceneRecording(name=name.strip() or f"rec-{int(time.time())}")
                db.add(rec)
                db.commit()
                db.refresh(rec)
                fh = open(_path_for(rec.id), "w", encoding="utf-8")
                self._active = _ActiveRecording(
                    recording_id=rec.id,
                    name=rec.name,
                    started_wall_ts=time.time(),
                    file_handle=fh,
                )
                return {
                    "id": rec.id, "name": rec.name,
                    "started_at": rec.started_at.isoformat(),
                }
            finally:
                db.close()

    async def stop(self) -> Optional[dict]:
        async with self._lock:
            a = self._active
            if a is None:
                return None
            try:
                a.file_handle.flush()
                a.file_handle.close()
            except Exception:
                pass
            self._active = None
            db = SessionLocal()
            try:
                rec = db.get(SceneRecording, a.recording_id)
                if rec is not None:
                    rec.stopped_at = datetime.utcnow()
                    rec.frame_count = a.frames_written
                    rec.file_size_bytes = a.bytes_written
                    db.commit()
            finally:
                db.close()
            return {
                "id": a.recording_id, "frames": a.frames_written,
                "bytes": a.bytes_written,
                "elapsed_s": round(time.time() - a.started_wall_ts, 1),
            }

    def write(self, scene_world: dict) -> None:
        """Called from the /ws/scene loop on every fused tick."""
        a = self._active
        if a is None:
            return
        rel_t = round(time.time() - a.started_wall_ts, 4)
        line = json.dumps({"rel_t": rel_t, "scene_world": scene_world},
                          separators=(",", ":")) + "\n"
        try:
            a.file_handle.write(line)
            a.frames_written += 1
            a.bytes_written += len(line)
            # Flush every ~100 frames so a crash loses at most ~10 s.
            if a.frames_written % 100 == 0:
                a.file_handle.flush()
        except Exception:
            pass


async def stream_for_playback(
    recording_id: int,
    speed: float = 1.0,
) -> AsyncIterator[dict]:
    """Yield {rel_t, scene_world} dicts at original cadence × `speed`."""
    path = _path_for(recording_id)
    if not path.exists():
        return
    speed = max(0.1, min(10.0, float(speed)))
    start_wall = None
    start_rel  = None
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            try:
                row = json.loads(raw)
            except Exception:
                continue
            rel_t = float(row.get("rel_t", 0))
            if start_wall is None:
                start_wall = time.monotonic()
                start_rel = rel_t
            target_wall = start_wall + (rel_t - start_rel) / speed
            wait = target_wall - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            yield row


def delete_recording(recording_id: int) -> bool:
    """Remove the JSONL file + DB row.  Returns True if anything was removed."""
    path = _path_for(recording_id)
    db_removed = False
    db = SessionLocal()
    try:
        rec = db.get(SceneRecording, recording_id)
        if rec is not None:
            db.delete(rec)
            db.commit()
            db_removed = True
    finally:
        db.close()
    file_removed = False
    if path.exists():
        try:
            path.unlink()
            file_removed = True
        except OSError:
            pass
    return db_removed or file_removed


# Module-level singleton.
_recorder: Optional[SceneRecorder] = None


def get_recorder() -> SceneRecorder:
    global _recorder
    if _recorder is None:
        _recorder = SceneRecorder()
    return _recorder
