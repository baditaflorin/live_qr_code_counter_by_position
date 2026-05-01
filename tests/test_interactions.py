"""Encounter detector tests."""
import time

import pytest

from backend.interactions import InteractionTracker


def _person(pid, name, x, y):
    return {"person_id": pid, "person_name": name, "body_xyz_m": [x, y, 0]}


def test_no_event_under_dwell_threshold():
    t = InteractionTracker(min_dwell_s=2.0, cooldown_s=0.5)
    p = [_person(1, "Anna", 0, 0), _person(2, "Bob", 0.3, 0)]
    events = t.update(p, 100.0)
    assert events == []
    # Even 1 s in, still no event because dwell is 2 s.
    events = t.update(p, 101.0)
    assert events == []


def test_encounter_started_after_dwell():
    t = InteractionTracker(min_dwell_s=1.0, cooldown_s=0.5)
    p = [_person(1, "Anna", 0, 0), _person(2, "Bob", 0.3, 0)]
    t.update(p, 100.0)
    events = t.update(p, 101.5)
    assert len(events) == 1
    assert events[0].kind == "encounter_started"
    assert {events[0].a_id, events[0].b_id} == {1, 2}
    live = t.live_encounters(101.5)
    assert len(live) == 1


def test_encounter_ends_after_cooldown_apart():
    t = InteractionTracker(min_dwell_s=0.5, cooldown_s=1.0)
    close = [_person(1, "Anna", 0, 0), _person(2, "Bob", 0.3, 0)]
    far   = [_person(1, "Anna", 0, 0), _person(2, "Bob", 5.0, 5.0)]
    t.update(close, 100.0)
    t.update(close, 100.6)         # encounter_started
    t.update(far,   101.0)         # apart (within cooldown)
    events = t.update(far, 102.5)  # cooldown expired
    kinds = [e.kind for e in events]
    assert "encounter_ended" in kinds
    ended = next(e for e in events if e.kind == "encounter_ended")
    assert ended.duration_s > 0


def test_brief_drift_apart_does_not_end_encounter():
    """A pair that briefly drifts >radius_m for less than cooldown_s should
    keep the same encounter (not split into two)."""
    t = InteractionTracker(min_dwell_s=0.5, cooldown_s=2.0, radius_m=1.0)
    close = [_person(1, "A", 0, 0), _person(2, "B", 0.5, 0)]
    far   = [_person(1, "A", 0, 0), _person(2, "B", 3.0, 0)]

    t.update(close, 100.0)
    started = t.update(close, 100.6)
    assert any(e.kind == "encounter_started" for e in started)
    # Drift apart for 0.5 s — under cooldown.
    t.update(far, 100.9)
    # Come back close.
    events = t.update(close, 101.4)
    assert all(e.kind != "encounter_ended" for e in events)


def test_unassigned_markers_are_ignored():
    """Encounters require both ends to have person_id (not None)."""
    t = InteractionTracker(min_dwell_s=0.5, cooldown_s=1.0)
    p = [
        _person(None, None, 0, 0),
        _person(None, None, 0.3, 0),
    ]
    events = t.update(p, 100.0)
    assert events == []


def test_multiple_pairs_tracked_independently():
    t = InteractionTracker(min_dwell_s=0.5, cooldown_s=1.0)
    p = [
        _person(1, "A", 0, 0),
        _person(2, "B", 0.4, 0),
        _person(3, "C", 5, 0),
        _person(4, "D", 5.4, 0),
    ]
    t.update(p, 100.0)
    events = t.update(p, 100.7)
    pairs = sorted([(e.a_id, e.b_id) for e in events if e.kind == "encounter_started"])
    assert pairs == [(1, 2), (3, 4)]
