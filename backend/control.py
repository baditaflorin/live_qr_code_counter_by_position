"""Control-marker infrastructure (ADR 0011 + 0014).

The top 16 IDs of the active dictionary are reserved for *system commands*
rather than person identities. The detection pipeline splits each frame into
person markers and control markers; control markers feed a `CommandRouter`
that fires an action when a card is held still in frame for ~1.2 seconds,
debounced so the same card can't fire twice within 5 seconds.

Action set (the four hands-free cards from ADR 0014):
  TRACK_START, TRACK_STOP, Q_NEXT, Q_PREV
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from . import detection
from .db import ControlMarker, Question, SessionLocal, TrackingSession


# ---------- reserved range ----------

CONTROL_RESERVED_COUNT = 16


def control_id_range() -> tuple[int, int]:
    """Returns (first_inclusive, last_inclusive) of the reserved control range
    in the active dictionary. Top of the dictionary so the rest stays
    available for person markers."""
    size = detection.dictionary_size()
    return (size - CONTROL_RESERVED_COUNT, size - 1)


def is_control_id(aruco_id: int) -> bool:
    lo, hi = control_id_range()
    return lo <= aruco_id <= hi


# ---------- default seed ----------

DEFAULT_BINDINGS: list[tuple[int, str, str]] = [
    # (slot from end of dictionary, action, label)
    (0, "TRACK_START", "Start tracking"),
    (1, "TRACK_STOP",  "Stop tracking"),
    (2, "Q_NEXT",      "Next question"),
    (3, "Q_PREV",      "Previous question"),
]

KNOWN_ACTIONS: tuple[str, ...] = ("TRACK_START", "TRACK_STOP", "Q_NEXT", "Q_PREV")


def seed_default_control_markers(db) -> int:
    """Idempotent: ensures the 4 default action markers are bound to the top
    of the dictionary. Existing rows aren't modified."""
    size = detection.dictionary_size()
    existing = {cm.aruco_id: cm for cm in db.execute(select(ControlMarker)).scalars()}
    created = 0
    for offset, action, label in DEFAULT_BINDINGS:
        aid = size - 1 - offset
        if aid in existing:
            continue
        db.add(ControlMarker(aruco_id=aid, action=action, label=label, enabled=1))
        created += 1
    if created:
        db.commit()
    return created


# ---------- per-process command router ----------

@dataclass
class FiredEvent:
    aruco_id: int
    action: str
    label: str
    t: float


class CommandRouter:
    """Tracks control-card hold-still + debounce state for the running process."""
    HOLD_STILL_S = 1.2
    DEBOUNCE_S = 5.0

    def __init__(self) -> None:
        self.first_seen: dict[int, float] = {}
        self.last_fired: dict[int, float] = {}

    def update(self, control_aruco_ids: set[int], now: float) -> list[int]:
        """Returns marker_ids that *fire* on this frame."""
        fired: list[int] = []
        for mid in control_aruco_ids:
            first = self.first_seen.get(mid)
            if first is None:
                self.first_seen[mid] = now
                continue
            if now - first < self.HOLD_STILL_S:
                continue
            last = self.last_fired.get(mid, 0)
            if now - last < self.DEBOUNCE_S:
                continue
            self.last_fired[mid] = now
            # Reset hold-still — must leave + re-enter to fire again.
            self.first_seen.pop(mid, None)
            fired.append(mid)
        # Markers that left the frame this turn lose their hold-still timer.
        for mid in list(self.first_seen.keys()):
            if mid not in control_aruco_ids:
                del self.first_seen[mid]
        return fired


# Singleton — per-process state. Multiple WS clients share the same router so
# a card waved on one camera doesn't double-fire on another.
router = CommandRouter()


# ---------- action handlers ----------

def fire(aruco_id: int) -> Optional[FiredEvent]:
    """Execute the action bound to this control marker. Returns the FiredEvent
    record if anything fired, else None."""
    db = SessionLocal()
    try:
        cm = db.get(ControlMarker, aruco_id)
        if not cm or not cm.enabled:
            return None
        action = cm.action
        if action == "TRACK_START":
            _do_track_start(db)
        elif action == "TRACK_STOP":
            _do_track_stop(db)
        elif action == "Q_NEXT":
            _do_question_step(db, +1)
        elif action == "Q_PREV":
            _do_question_step(db, -1)
        else:
            return None
        return FiredEvent(aruco_id=aruco_id, action=action, label=cm.label, t=time.time())
    finally:
        db.close()


def _do_track_start(db) -> None:
    db.query(TrackingSession).filter(TrackingSession.stopped_at.is_(None)).update(
        {TrackingSession.stopped_at: datetime.utcnow()}, synchronize_session=False
    )
    s = TrackingSession(name=f"Hands-free {datetime.utcnow().strftime('%H:%M:%S')}")
    db.add(s)
    db.commit()


def _do_track_stop(db) -> None:
    db.query(TrackingSession).filter(TrackingSession.stopped_at.is_(None)).update(
        {TrackingSession.stopped_at: datetime.utcnow()}, synchronize_session=False
    )
    db.commit()


def _do_question_step(db, delta: int) -> None:
    qs = db.execute(
        select(Question).order_by(
            Question.block.is_(None).desc(),
            Question.block.asc(),
            Question.position.asc(),
            Question.id.asc(),
        )
    ).scalars().all()
    if not qs:
        return
    cur_idx = next((i for i, q in enumerate(qs) if q.is_active), -1)
    if cur_idx < 0:
        new_idx = 0 if delta > 0 else len(qs) - 1
    else:
        new_idx = max(0, min(len(qs) - 1, cur_idx + delta))
    if new_idx == cur_idx:
        return
    db.query(Question).update({Question.is_active: 0})
    qs[new_idx].is_active = 1
    db.commit()
