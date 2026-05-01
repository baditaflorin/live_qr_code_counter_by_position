"""Live encounter detector — tracks when two named people stay within a
configurable radius for at least `min_dwell_s` seconds.

Runs against the multi-camera fused scene (`scene_state.fused_scene().people`)
on each aggregator tick.  Emits two event kinds:

  - `encounter_started` — pair just crossed `min_dwell_s` of staying close
  - `encounter_ended`   — pair drifted apart for more than `cooldown_s`

The detector is process-local (one instance, sharing state across observers)
because the encounter state is a property of the room, not of a viewer.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional


# Defaults tuned for a 5×4 m room and chest-height markers.  Adjust via
# environment variables if the venue is dramatically different.
RADIUS_M = 1.2          # within 1.2 m centre-to-centre = "having a conversation"
MIN_DWELL_S = 3.0       # must stay close this long before counting as an encounter
COOLDOWN_S = 2.5        # may drift apart briefly without ending the encounter


@dataclass
class _PairState:
    a: int                  # smaller person_id
    b: int                  # larger person_id
    a_name: Optional[str]
    b_name: Optional[str]
    started_proximity_ts: float
    last_close_ts: float
    encounter_active: bool = False
    encounter_started_at: float = 0.0


@dataclass
class EncounterEvent:
    kind: str               # "encounter_started" | "encounter_ended"
    a_id: int
    b_id: int
    a_name: Optional[str]
    b_name: Optional[str]
    t: float
    duration_s: float = 0.0   # populated for `_ended`


@dataclass
class LiveEncounter:
    """A currently-active encounter, for the "Live encounters" panel."""
    a_id: int
    b_id: int
    a_name: Optional[str]
    b_name: Optional[str]
    started_at: float
    distance_m: float


class InteractionTracker:
    def __init__(
        self,
        radius_m: float = RADIUS_M,
        min_dwell_s: float = MIN_DWELL_S,
        cooldown_s: float = COOLDOWN_S,
    ):
        self.radius_m = float(radius_m)
        self.min_dwell_s = float(min_dwell_s)
        self.cooldown_s = float(cooldown_s)
        self._pairs: dict[tuple[int, int], _PairState] = {}
        self._recent_events: list[EncounterEvent] = []
        self._max_recent = 50

    def update(self, people: list[dict], now: float) -> list[EncounterEvent]:
        """Feed the latest fused people list, return events fired this tick.

        `people` is the `scene_world.people` payload — only person_id-bearing
        entries are considered (unassigned markers don't form encounters).
        """
        named = [p for p in people if p.get("person_id") is not None]
        events: list[EncounterEvent] = []

        # Mark every pair that is currently close.
        seen_close: set[tuple[int, int]] = set()
        for i, p in enumerate(named):
            for q in named[i + 1:]:
                pid_a, pid_b = sorted((int(p["person_id"]), int(q["person_id"])))
                xa, ya = p["body_xyz_m"][0], p["body_xyz_m"][1]
                xb, yb = q["body_xyz_m"][0], q["body_xyz_m"][1]
                d = math.hypot(xa - xb, ya - yb)
                if d > self.radius_m:
                    continue
                seen_close.add((pid_a, pid_b))
                state = self._pairs.get((pid_a, pid_b))
                if state is None:
                    state = _PairState(
                        a=pid_a, b=pid_b,
                        a_name=p["person_name"] if pid_a == int(p["person_id"]) else q["person_name"],
                        b_name=q["person_name"] if pid_b == int(q["person_id"]) else p["person_name"],
                        started_proximity_ts=now,
                        last_close_ts=now,
                    )
                    self._pairs[(pid_a, pid_b)] = state
                else:
                    state.last_close_ts = now
                # Fire encounter_started once dwell threshold is crossed.
                if not state.encounter_active and (now - state.started_proximity_ts) >= self.min_dwell_s:
                    state.encounter_active = True
                    state.encounter_started_at = state.started_proximity_ts
                    events.append(EncounterEvent(
                        kind="encounter_started",
                        a_id=state.a, b_id=state.b,
                        a_name=state.a_name, b_name=state.b_name,
                        t=now,
                    ))

        # Sweep stale pairs: drifted apart for longer than cooldown_s.
        for key in list(self._pairs.keys()):
            state = self._pairs[key]
            if (now - state.last_close_ts) > self.cooldown_s:
                if state.encounter_active:
                    events.append(EncounterEvent(
                        kind="encounter_ended",
                        a_id=state.a, b_id=state.b,
                        a_name=state.a_name, b_name=state.b_name,
                        t=now,
                        duration_s=round(state.last_close_ts - state.encounter_started_at, 2),
                    ))
                del self._pairs[key]

        if events:
            self._recent_events.extend(events)
            if len(self._recent_events) > self._max_recent:
                self._recent_events = self._recent_events[-self._max_recent:]
        return events

    def live_encounters(self, now: float) -> list[LiveEncounter]:
        out: list[LiveEncounter] = []
        for state in self._pairs.values():
            if not state.encounter_active:
                continue
            out.append(LiveEncounter(
                a_id=state.a, b_id=state.b,
                a_name=state.a_name, b_name=state.b_name,
                started_at=state.encounter_started_at,
                distance_m=0.0,  # filled in by caller if needed
            ))
        return out

    def recent_events(self, limit: int = 20) -> list[EncounterEvent]:
        return self._recent_events[-limit:]


# Module-level singleton so all observer WS connections see the same room state.
_tracker: Optional[InteractionTracker] = None


def get_tracker() -> InteractionTracker:
    global _tracker
    if _tracker is None:
        _tracker = InteractionTracker()
    return _tracker
