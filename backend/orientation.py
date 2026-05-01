"""ADR 0073 — Orientation as a semantic channel.

A *rotation* of a marker can carry meaning. ADR 0048 already gives every
detection a world-frame yaw / pitch / roll; this module reads that signal,
buckets it into discrete values (e.g. yes / no / unsure / tender), and
emits events when a marker settles in a bucket.

ADR 0073 *graduated* from env-var routing (experimental phase) to live
``participant_cards`` rows (ADR 0021 + 0022). This file now provides the
**primitives**:

* ``classify_yaw`` — pure function: angle → bucket symbol or None.
* ``OrientationRouter`` — stateful sliding-window classifier with stability
  gate, dead-zone, per-marker rate limit, and noisy-detection rejection.
* ``parse_*_from_env`` — helpers that read the legacy
  ``ORIENTATION_ROUTER_*`` env vars; ``participant`` uses these once on
  boot to seed default ``orientation``-fire-model cards when an operator
  wants to enable the channel without writing to the DB by hand.

The live per-frame routing now lives in ``participant.py``: each
``orientation``-fire-model card builds its own ``OrientationRouter`` from
``params_json`` and delegates angle bucketing here.

The classifier is pure (no DB, no HTTP, no env). The router holds per-marker
sliding-window state but is otherwise side-effect free.
"""
from __future__ import annotations

import json
import math
import os
from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable, Optional


# ---------- defaults -------------------------------------------------------

DEFAULT_BUCKETS: list[dict] = [
    {"center_deg":   0.0, "half_width_deg": 30.0, "value": "yes"},
    {"center_deg":  90.0, "half_width_deg": 30.0, "value": "unsure"},
    {"center_deg": 180.0, "half_width_deg": 30.0, "value": "no"},
    {"center_deg": 270.0, "half_width_deg": 30.0, "value": "tender"},
]

# ADR 0022 activation gate (≥ 0.4 s in a sliding 0.6 s window) plus an
# orientation-stability check (sample stddev within the window).
DEFAULT_STABILITY_WINDOW_S = 0.6
DEFAULT_STABILITY_TOLERANCE_DEG = 10.0
DEFAULT_MIN_FRACTION_IN_BUCKET = 0.8

# ADR 0022 per-marker rate limit — same number, different reason: prevents
# wrist-jitter at a bucket edge from generating a fire storm.
PER_MARKER_RATE_LIMIT_S = 1.5

# ADR 0073 risk note — refuse to fire on noisy detections so a bent / occluded
# / undersized marker doesn't pollute the event stream with random buckets.
MAX_REPROJ_ERROR_PX_FOR_FIRE = 1.5


# ---------- pure classifier ------------------------------------------------

def _wrap_to_180(deg: float) -> float:
    """Map any angle to the (-180, 180] half-open interval."""
    return ((deg + 180.0) % 360.0) - 180.0


def _angular_distance_deg(a: float, b: float) -> float:
    """Smallest signed → unsigned angular distance, in degrees."""
    return abs(_wrap_to_180(a - b))


def classify_yaw(yaw_deg: float, buckets: list[dict]) -> Optional[str]:
    """Return the symbolic value of the bucket containing ``yaw_deg``.

    Returns ``None`` for the **dead-zone** between buckets — by design,
    so a card mid-rotation does not flicker through every value on its
    way. Multiple bucket overlaps resolve to the nearest center.
    """
    best_value: Optional[str] = None
    best_dist = math.inf
    for b in buckets:
        center = float(b["center_deg"])
        half = float(b["half_width_deg"])
        d = _angular_distance_deg(yaw_deg, center)
        if d <= half and d < best_dist:
            best_value = str(b["value"])
            best_dist = d
    return best_value


def _stddev_circular(samples: Iterable[float]) -> float:
    """Stddev that wraps around 360°. The samples are converted to unit
    vectors; the angle of the mean vector defines the centre, and the
    deviation in degrees is computed from there.

    Robust enough for the wrist-jitter detection ADR 0073 cares about; not
    a substitute for proper directional statistics.
    """
    xs = []
    ys = []
    for s in samples:
        r = math.radians(s)
        xs.append(math.cos(r))
        ys.append(math.sin(r))
    if not xs:
        return 0.0
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    centre_deg = math.degrees(math.atan2(my, mx))
    diffs = [_angular_distance_deg(s, centre_deg) for s in samples]
    if len(diffs) < 2:
        return 0.0
    mean_d = sum(diffs) / len(diffs)
    var = sum((d - mean_d) ** 2 for d in diffs) / (len(diffs) - 1)
    return math.sqrt(var)


# ---------- router ---------------------------------------------------------

@dataclass
class OrientationEvent:
    """Mirrors ``control.FiredEvent`` — one per bucket entry / exit / change."""
    aruco_id: int
    kind: str            # "orientation_enter" | "orientation_exit" | "orientation_change"
    value: Optional[str] # bucket value being entered (or exited, on "exit" kind)
    prev_value: Optional[str]
    yaw_deg: float
    t: float


@dataclass
class _MarkerState:
    """Per-marker sliding-window history of (timestamp, yaw_deg) samples,
    plus the currently-active bucket and the last fire timestamp."""
    samples: Deque[tuple[float, float]]
    active_bucket: Optional[str] = None
    # ``-inf`` so the first-ever fire is not rate-limited regardless of the
    # caller's clock origin (workshop time vs. test t=0).
    last_fired_at: float = float("-inf")


class OrientationRouter:
    """ADR 0073 — emits events on stable bucket residency for the marker IDs
    in ``watched_ids``. State is per-process; a single instance is shared
    across all WS clients so a card seen on one camera doesn't double-fire
    on another (same shape as ``control.CommandRouter``).

    The router is intentionally tolerant of the data shape — its update()
    consumes a list of ``(aruco_id, yaw_deg, reproj_error_px)`` triples,
    which the WS loop already has on hand from ADR 0050's pose payload.
    """

    def __init__(
        self,
        watched_ids: set[int],
        buckets: list[dict],
        *,
        axis: str = "yaw",
        stability_window_s: float = DEFAULT_STABILITY_WINDOW_S,
        stability_tolerance_deg: float = DEFAULT_STABILITY_TOLERANCE_DEG,
        min_fraction_in_bucket: float = DEFAULT_MIN_FRACTION_IN_BUCKET,
        rate_limit_s: float = PER_MARKER_RATE_LIMIT_S,
        max_reproj_error_px: float = MAX_REPROJ_ERROR_PX_FOR_FIRE,
    ) -> None:
        if axis not in ("yaw", "pitch", "roll"):
            raise ValueError(f"axis must be yaw|pitch|roll; got {axis!r}")
        self.watched_ids = set(watched_ids)
        self.buckets = list(buckets)
        self.axis = axis
        self.stability_window_s = stability_window_s
        self.stability_tolerance_deg = stability_tolerance_deg
        self.min_fraction_in_bucket = min_fraction_in_bucket
        self.rate_limit_s = rate_limit_s
        self.max_reproj_error_px = max_reproj_error_px
        self._state: dict[int, _MarkerState] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.watched_ids) and bool(self.buckets)

    def update(
        self,
        observations: list[tuple[int, float, float]],
        now: float,
    ) -> list[OrientationEvent]:
        """One frame of input. Returns whatever events fired this turn.

        ``observations`` is a list of ``(aruco_id, angle_deg, reproj_err_px)``
        for the configured ``axis``.
        """
        if not self.enabled:
            return []
        events: list[OrientationEvent] = []
        seen_ids: set[int] = set()

        for aid, angle_deg, err_px in observations:
            if aid not in self.watched_ids:
                continue
            seen_ids.add(aid)
            if err_px > self.max_reproj_error_px:
                # Noisy detection — skip rather than fire on a wrong bucket.
                continue
            st = self._state.setdefault(
                aid, _MarkerState(samples=deque())
            )
            st.samples.append((now, float(angle_deg)))
            self._trim_window(st, now)

            new_bucket = self._stable_bucket(st)
            if new_bucket == st.active_bucket:
                continue

            # Bucket changed — but rate-limit fires per marker.
            if (now - st.last_fired_at) < self.rate_limit_s:
                continue

            prev = st.active_bucket
            st.active_bucket = new_bucket
            st.last_fired_at = now

            # Translate the transition into one or two events. Same shape
            # as a pulse-mode card: enter on activate, exit on deactivate.
            if prev is None and new_bucket is not None:
                events.append(OrientationEvent(
                    aruco_id=aid, kind="orientation_enter",
                    value=new_bucket, prev_value=None,
                    yaw_deg=float(angle_deg), t=now,
                ))
            elif prev is not None and new_bucket is None:
                events.append(OrientationEvent(
                    aruco_id=aid, kind="orientation_exit",
                    value=prev, prev_value=prev,
                    yaw_deg=float(angle_deg), t=now,
                ))
            else:
                # prev != new_bucket and both non-None.
                events.append(OrientationEvent(
                    aruco_id=aid, kind="orientation_change",
                    value=new_bucket, prev_value=prev,
                    yaw_deg=float(angle_deg), t=now,
                ))

        # A marker that left the frame loses its sliding window so it
        # resets cleanly when it re-enters.
        for stale in [k for k in self._state if k not in seen_ids]:
            st = self._state[stale]
            self._trim_window(st, now)
            if not st.samples:
                # If the active bucket "exits" because the marker disappeared,
                # surface that as an exit event so downstream counters
                # decrement.
                if st.active_bucket is not None and (now - st.last_fired_at) >= self.rate_limit_s:
                    events.append(OrientationEvent(
                        aruco_id=stale, kind="orientation_exit",
                        value=st.active_bucket, prev_value=st.active_bucket,
                        yaw_deg=float("nan"), t=now,
                    ))
                    st.last_fired_at = now
                    st.active_bucket = None

        return events

    # ---- internals -------------------------------------------------------

    def _trim_window(self, st: _MarkerState, now: float) -> None:
        cutoff = now - self.stability_window_s
        while st.samples and st.samples[0][0] < cutoff:
            st.samples.popleft()

    def _stable_bucket(self, st: _MarkerState) -> Optional[str]:
        """Return the bucket the marker is currently considered "in",
        or None if the dead-zone / instability rules say no."""
        if not st.samples:
            return None
        angles = [a for _, a in st.samples]
        # Need a populated window — ADR 0022's gate, expressed as samples.
        if len(angles) < 2:
            return None
        # Stability: angular stddev across the window must be tight.
        if _stddev_circular(angles) > self.stability_tolerance_deg:
            return None
        # Majority of samples must be in the same bucket.
        votes: dict[Optional[str], int] = {}
        for a in angles:
            votes[classify_yaw(a, self.buckets)] = votes.get(classify_yaw(a, self.buckets), 0) + 1
        winner, count = max(votes.items(), key=lambda kv: kv[1])
        if winner is None:
            return None
        if count / len(angles) < self.min_fraction_in_bucket:
            return None
        return winner


# ---------- legacy env-var parsing (used only at seed time) ---------------

def parse_marker_ids_from_env(raw: Optional[str] = None) -> set[int]:
    """Parse ``ORIENTATION_ROUTER_MARKERS`` (or an explicit string) into a
    set of integers. Bad entries are silently skipped — env-var typos
    shouldn't crash boot."""
    raw = raw if raw is not None else os.environ.get("ORIENTATION_ROUTER_MARKERS", "")
    out: set[int] = set()
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            out.add(int(piece))
        except ValueError:
            continue
    return out


def parse_buckets_from_env(raw: Optional[str] = None) -> list[dict]:
    """Parse ``ORIENTATION_ROUTER_BUCKETS_JSON`` into a bucket list, falling
    back to ``DEFAULT_BUCKETS`` on any failure."""
    raw = raw if raw is not None else os.environ.get("ORIENTATION_ROUTER_BUCKETS_JSON")
    if not raw:
        return list(DEFAULT_BUCKETS)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return list(DEFAULT_BUCKETS)
    if not isinstance(parsed, list):
        return list(DEFAULT_BUCKETS)
    out: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        try:
            out.append({
                "center_deg":     float(item["center_deg"]),
                "half_width_deg": float(item["half_width_deg"]),
                "value":          str(item["value"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return out or list(DEFAULT_BUCKETS)


def parse_axis_from_env(raw: Optional[str] = None) -> str:
    """Parse ``ORIENTATION_ROUTER_AXIS`` to one of yaw|pitch|roll."""
    raw = raw if raw is not None else os.environ.get("ORIENTATION_ROUTER_AXIS", "yaw")
    axis = (raw or "yaw").strip().lower()
    return axis if axis in ("yaw", "pitch", "roll") else "yaw"
