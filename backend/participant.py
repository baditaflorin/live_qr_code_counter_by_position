"""Participant routing — ADR 0021 (foundation) + 0022 (semantics) + 0073 (orientation).

Distinct from the operator-side `CommandRouter` (ADR 0011 / 0014) in every
dimension that matters: faster activation gate (≥ 0.4 s in a 0.6 s sliding
window vs. operator's 1.5 s hold-still), attribution to a *holder*, and four
fire models — `pulse`, `level`, `gesture`, `orientation` — instead of the
operator's single fire-on-hold model.

Per-frame entry point is `ParticipantRouter.update(...)`. Inputs:

* `seen_card_ids` — the set of `participant_cards.aruco_id` values detected
  this frame.
* `marker_obs`  — ADR 0050's world-frame observations (`MarkerObservation`),
  used for both holder attribution and the orientation classifier.
* `now`         — monotonic timestamp, seconds.

Output is a list of `ParticipantFireEvent` records. The WS loop turns those
into payload entries and `ParticipantEvent` rows.

Co-occurrence bundling (ADR 0022's "two cards by same person within 1 s"
composite event for theme + intent grammar) is **deferred**: orientation
cards don't need it, and the activation kit (ADR 0067) replaced the
grammar layer that originally motivated bundling. A future ADR can add it
without touching the fire-model handlers.
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Iterable, Optional

from sqlalchemy import select

from . import orientation as orientation_mod
from .db import ParticipantCard, ParticipantEvent, SessionLocal


# ---------- ADR 0022 constants ---------------------------------------------

ACTIVATION_WINDOW_S = 0.6
ACTIVATION_HOLD_S = 0.4              # ≥ 0.4 s of detection inside the window
GESTURE_MAX_DURATION_S = 5.0
PER_MARKER_RATE_LIMIT_S = 1.5
PER_PERSON_EVENTS_PER_MIN = 6
HOLDER_ATTRIBUTION_RADIUS_M = 0.8

KNOWN_FIRE_MODELS: tuple[str, ...] = ("pulse", "level", "gesture", "orientation")
KNOWN_KITS: tuple[str, ...] = (
    "reaction", "theme", "intent", "composition",
    "witness", "memory", "promise", "activation", "custom",
)

# Cards live in the dictionary, but we only consider person markers (ADR 0021
# explicitly excludes operator markers from being the "holder" of a card —
# the operator is not part of the room being counted).


# ---------- event shape ----------------------------------------------------

@dataclass
class ParticipantFireEvent:
    aruco_id: int
    kit: str
    action: str
    fire_model: str           # pulse | level | gesture | orientation
    kind: str                 # pulse_on | pulse_off | level_active | level_inactive | gesture_complete | orientation_enter | orientation_exit | orientation_change
    value: Optional[str]      # bucket symbol (orientation), None otherwise
    held_by_aruco_id: Optional[int]
    attribution_confidence: float
    t: float

    def to_payload(self) -> dict:
        return {
            "aruco_id": self.aruco_id,
            "kit": self.kit,
            "action": self.action,
            "fire_model": self.fire_model,
            "kind": self.kind,
            "value": self.value,
            "held_by_aruco_id": self.held_by_aruco_id,
            "attribution_confidence": round(self.attribution_confidence, 3),
            "t": self.t,
        }


# ---------- per-card running state -----------------------------------------

@dataclass
class _CardState:
    """Shared state across fire models — sliding window of detection
    timestamps used by the activation gate."""
    detections: Deque[float] = field(default_factory=deque)
    is_active: bool = False
    # ``-inf`` so the first-ever fire is not rate-limited regardless of the
    # caller's clock origin (workshop time vs. test t=0).
    last_fired_at: float = float("-inf")
    # Gesture-specific: when the card became active and was still active.
    gesture_active_since: Optional[float] = None
    # Level-specific: most recent "level_active" tick we emitted.
    level_last_tick: float = 0.0
    # Orientation: delegated to OrientationRouter, keyed by aruco_id.
    # We hold one OrientationRouter per (aruco_id, params hash) pair so config
    # changes hot-reload cleanly.
    orientation_config_hash: Optional[int] = None
    orientation_router: Optional[orientation_mod.OrientationRouter] = None


# ---------- holder attribution ---------------------------------------------

def _attribute_holder(
    card_xyz: tuple[float, float, float],
    candidate_holders: list[tuple[int, tuple[float, float, float]]],
    radius_m: float,
) -> tuple[Optional[int], float]:
    """Find the nearest non-card marker within `radius_m` of the card's
    world position. Confidence is 1.0 at zero distance, linearly decaying
    to 0.0 at `radius_m`. Returns (holder_aruco_id, confidence)."""
    if not candidate_holders:
        return None, 0.0
    best_id = None
    best_d = math.inf
    cx, cy, cz = card_xyz
    for aid, (px, py, pz) in candidate_holders:
        d = math.sqrt((cx - px) ** 2 + (cy - py) ** 2 + (cz - pz) ** 2)
        if d < best_d:
            best_d = d
            best_id = aid
    if best_id is None or best_d > radius_m:
        return None, 0.0
    return best_id, max(0.0, 1.0 - (best_d / radius_m))


# ---------- main router ----------------------------------------------------

class ParticipantRouter:
    """Per-process router for participant cards. Singleton at module bottom."""

    def __init__(self) -> None:
        self._cards: dict[int, ParticipantCard] = {}
        self._cards_loaded_at: float = 0.0
        self._state: dict[int, _CardState] = {}
        # Per-holder rate limit (ADR 0022): timestamps of recent fires keyed
        # by held_by_aruco_id. Anonymous holders share the None bucket.
        self._holder_history: dict[Optional[int], Deque[float]] = {}

    # ---- card config -----------------------------------------------------

    def reload_cards(self) -> int:
        """Refresh the cached card config from the DB. Returns count."""
        db = SessionLocal()
        try:
            rows = db.execute(
                select(ParticipantCard).where(ParticipantCard.enabled == 1)
            ).scalars().all()
            self._cards = {row.aruco_id: row for row in rows}
            self._cards_loaded_at = time.time()
            return len(self._cards)
        finally:
            db.close()

    def card_ids(self) -> set[int]:
        return set(self._cards.keys())

    def is_participant_id(self, aruco_id: int) -> bool:
        return aruco_id in self._cards

    def get_card(self, aruco_id: int) -> Optional[ParticipantCard]:
        """Read-only access to the cached row, for callers that need
        kit/name/action without re-querying the DB."""
        return self._cards.get(aruco_id)

    @property
    def enabled(self) -> bool:
        return bool(self._cards)

    # ---- per-frame entry point -------------------------------------------

    def update(
        self,
        seen_card_ids: set[int],
        marker_obs_by_id: dict[int, "_MarkerObsLike"],
        candidate_holder_xyz: list[tuple[int, tuple[float, float, float]]],
        now: float,
    ) -> list[ParticipantFireEvent]:
        """One frame of card-routing work. Caller is responsible for
        partitioning detections into (person_results, control_ids,
        participant_card_ids)."""
        if not self.enabled:
            return []
        events: list[ParticipantFireEvent] = []
        # Activation-gate update for every known card (whether seen or not).
        for aid, card in self._cards.items():
            st = self._state.setdefault(aid, _CardState())
            self._tick_activation_window(st, aid in seen_card_ids, now)
            active_now = self._is_active(st, now)

            holder_id: Optional[int] = None
            holder_conf: float = 0.0
            if aid in seen_card_ids:
                obs = marker_obs_by_id.get(aid)
                if obs is not None:
                    candidates = [
                        (other_id, xyz) for other_id, xyz in candidate_holder_xyz
                        if other_id != aid and not self.is_participant_id(other_id)
                    ]
                    holder_id, holder_conf = _attribute_holder(
                        obs.world_xyz, candidates, HOLDER_ATTRIBUTION_RADIUS_M,
                    )

            fired = self._dispatch(card, st, active_now, holder_id, holder_conf,
                                   marker_obs_by_id.get(aid), now)
            for ev in fired:
                if self._holder_rate_limited(ev.held_by_aruco_id, now):
                    # Drop event silently rather than persisting it — ADR 0022
                    # rate limit is meant to be invisible to good-faith holders.
                    continue
                self._record_holder_fire(ev.held_by_aruco_id, now)
                events.append(ev)

        return events

    # ---- activation gate (shared by all fire models) ---------------------

    def _tick_activation_window(self, st: _CardState, seen_now: bool, now: float) -> None:
        cutoff = now - ACTIVATION_WINDOW_S
        while st.detections and st.detections[0] < cutoff:
            st.detections.popleft()
        if seen_now:
            st.detections.append(now)

    def _is_active(self, st: _CardState, now: float) -> bool:
        if not st.detections:
            return False
        # Fraction of the window in which the card was visible.
        if len(st.detections) < 2:
            return False
        # Gap-based duration estimate: span between first and last sample
        # within the window. Sufficient for the workshop's frame rate; not
        # a substitute for sample-by-sample integration if FPS drops < 5.
        span = st.detections[-1] - st.detections[0]
        return span >= ACTIVATION_HOLD_S

    # ---- per-card dispatch -----------------------------------------------

    def _dispatch(
        self,
        card: ParticipantCard,
        st: _CardState,
        active_now: bool,
        holder_id: Optional[int],
        holder_conf: float,
        obs: Optional["_MarkerObsLike"],
        now: float,
    ) -> list[ParticipantFireEvent]:
        fm = card.fire_model
        if fm == "pulse":
            return self._dispatch_pulse(card, st, active_now, holder_id, holder_conf, now)
        if fm == "level":
            return self._dispatch_level(card, st, active_now, holder_id, holder_conf, now)
        if fm == "gesture":
            return self._dispatch_gesture(card, st, active_now, holder_id, holder_conf, now)
        if fm == "orientation":
            return self._dispatch_orientation(card, st, active_now, holder_id, holder_conf, obs, now)
        return []

    # pulse: fires once on activation, once on deactivation.
    # ADR 0022 per-marker rate limit guards against *flicker* (a card
    # ping-ponging in/out of detection); it shouldn't suppress the legitimate
    # off-edge of a normal on-then-off cycle. So only the asserting edge is
    # rate-limited; the off-edge always emits so downstream counters
    # decrement correctly.
    def _dispatch_pulse(self, card, st, active_now, holder_id, holder_conf, now) -> list[ParticipantFireEvent]:
        events: list[ParticipantFireEvent] = []
        if active_now and not st.is_active:
            if (now - st.last_fired_at) >= PER_MARKER_RATE_LIMIT_S:
                events.append(self._mk_event(card, "pulse_on", None, holder_id, holder_conf, now))
                st.last_fired_at = now
                st.is_active = True
            # If rate-limited, leave is_active=False so the next genuine
            # activation can still fire once the cooldown elapses.
        elif not active_now and st.is_active:
            events.append(self._mk_event(card, "pulse_off", None, None, 0.0, now))
            st.is_active = False
        return events

    # level: one event on each transition. The asserting edge ("level_active")
    # is rate-limited; the de-asserting edge is unconditional, same reasoning
    # as pulse above.
    def _dispatch_level(self, card, st, active_now, holder_id, holder_conf, now) -> list[ParticipantFireEvent]:
        events: list[ParticipantFireEvent] = []
        if active_now and not st.is_active:
            if (now - st.last_fired_at) >= PER_MARKER_RATE_LIMIT_S:
                events.append(self._mk_event(card, "level_active", None, holder_id, holder_conf, now))
                st.last_fired_at = now
                st.is_active = True
        elif not active_now and st.is_active:
            events.append(self._mk_event(card, "level_inactive", None, None, 0.0, now))
            st.is_active = False
        return events

    # gesture: fires once when a card is raised AND lowered within
    # GESTURE_MAX_DURATION_S; otherwise no fire (a card held longer is "level"-ish).
    def _dispatch_gesture(self, card, st, active_now, holder_id, holder_conf, now) -> list[ParticipantFireEvent]:
        events: list[ParticipantFireEvent] = []
        if active_now and not st.is_active:
            st.gesture_active_since = now
            st.is_active = True
        elif not active_now and st.is_active:
            since = st.gesture_active_since or now
            duration = now - since
            st.gesture_active_since = None
            st.is_active = False
            if duration <= GESTURE_MAX_DURATION_S:
                if (now - st.last_fired_at) >= PER_MARKER_RATE_LIMIT_S:
                    events.append(self._mk_event(
                        card, "gesture_complete", None,
                        holder_id, holder_conf, now,
                    ))
                    st.last_fired_at = now
        return events

    # orientation (ADR 0073): delegate angle bucketing to OrientationRouter,
    # then re-wrap the events with kit / action / holder metadata.
    def _dispatch_orientation(self, card, st, active_now, holder_id, holder_conf, obs, now) -> list[ParticipantFireEvent]:
        if obs is None:
            return []
        params = card.params()
        buckets = params.get("orientation_buckets") or orientation_mod.DEFAULT_BUCKETS
        axis = (params.get("orientation_axis") or "yaw").lower()
        config_hash = hash((tuple(tuple(sorted(b.items())) for b in buckets), axis))
        if st.orientation_router is None or st.orientation_config_hash != config_hash:
            st.orientation_router = orientation_mod.OrientationRouter(
                watched_ids={card.aruco_id},
                buckets=list(buckets),
                axis=axis,
                stability_window_s=float(params.get("stability_window_s", orientation_mod.DEFAULT_STABILITY_WINDOW_S)),
                stability_tolerance_deg=float(params.get("stability_tolerance_deg", orientation_mod.DEFAULT_STABILITY_TOLERANCE_DEG)),
            )
            st.orientation_config_hash = config_hash

        angle = (
            obs.yaw_deg if axis == "yaw"
            else obs.pitch_deg if axis == "pitch"
            else obs.roll_deg
        )
        sub_events = st.orientation_router.update(
            [(card.aruco_id, angle, obs.reproj_error_px)], now,
        )
        out: list[ParticipantFireEvent] = []
        for ev in sub_events:
            holder_for_event = holder_id if ev.kind != "orientation_exit" else None
            holder_conf_for_event = holder_conf if ev.kind != "orientation_exit" else 0.0
            out.append(self._mk_event(
                card, ev.kind, ev.value,
                holder_for_event, holder_conf_for_event, now,
            ))
        return out

    # ---- per-holder rate limit (ADR 0022) --------------------------------

    def _holder_rate_limited(self, holder_id: Optional[int], now: float) -> bool:
        history = self._holder_history.get(holder_id)
        if history is None:
            return False
        cutoff = now - 60.0
        while history and history[0] < cutoff:
            history.popleft()
        return len(history) >= PER_PERSON_EVENTS_PER_MIN

    def _record_holder_fire(self, holder_id: Optional[int], now: float) -> None:
        history = self._holder_history.setdefault(holder_id, deque())
        history.append(now)
        cutoff = now - 60.0
        while history and history[0] < cutoff:
            history.popleft()

    # ---- helpers ---------------------------------------------------------

    def _mk_event(
        self,
        card: ParticipantCard,
        kind: str,
        value: Optional[str],
        holder_id: Optional[int],
        holder_conf: float,
        now: float,
    ) -> ParticipantFireEvent:
        return ParticipantFireEvent(
            aruco_id=card.aruco_id,
            kit=card.kit,
            action=card.action,
            fire_model=card.fire_model,
            kind=kind,
            value=value,
            held_by_aruco_id=holder_id,
            attribution_confidence=holder_conf,
            t=now,
        )


# ---------- duck-typed observation interface -------------------------------

@dataclass
class _MarkerObsLike:
    """The slice of `scene.MarkerObservation` the router actually reads.
    Keeps participant.py free of a hard dependency on scene.py — easier to
    test, and decouples ordering of pose pipeline upgrades."""
    world_xyz: tuple[float, float, float]
    yaw_deg: float
    pitch_deg: float
    roll_deg: float
    reproj_error_px: float


# ---------- persistence helper --------------------------------------------

def persist_events(events: list[ParticipantFireEvent]) -> None:
    """Write fire events to the `participant_events` audit table.

    Caller-owned: the router never touches the DB on the hot path; the WS
    loop calls this once per tick after assembling the WS payload, on the
    same buffered cadence as `record_metric` / `record_audit` would use.
    """
    if not events:
        return
    rows = [
        {
            "marker_aruco_id": e.aruco_id,
            "held_by_aruco_id": e.held_by_aruco_id,
            "kit": e.kit,
            "action": e.action,
            "fire_model": e.fire_model,
            "kind": e.kind,
            "value": e.value,
            "attribution_confidence": float(e.attribution_confidence),
        }
        for e in events
    ]
    db = SessionLocal()
    try:
        db.bulk_insert_mappings(ParticipantEvent, rows)
        db.commit()
    finally:
        db.close()


# ---------- env-var seed bridge --------------------------------------------

def seed_orientation_cards_from_env(db) -> int:
    """One-time seed for the legacy ``ORIENTATION_ROUTER_*`` env vars.

    Reads ``ORIENTATION_ROUTER_MARKERS`` / ``..._BUCKETS_JSON`` / ``..._AXIS``
    and creates one ``orientation``-fire-model row per ID, idempotent: only
    inserts rows whose ``aruco_id`` doesn't already exist. Returns the number
    of rows created.

    Lets a deployment that opted into the env-var experiment graduate to the
    DB-backed config without operator intervention. Once the rows exist,
    runtime config comes from them and the env vars are advisory only.
    """
    import json as _json
    ids = orientation_mod.parse_marker_ids_from_env()
    if not ids:
        return 0
    buckets = orientation_mod.parse_buckets_from_env()
    axis = orientation_mod.parse_axis_from_env()
    existing = set(db.execute(select(ParticipantCard.aruco_id)).scalars().all())
    created = 0
    params = {
        "orientation_axis": axis,
        "orientation_buckets": buckets,
    }
    for aid in sorted(ids):
        if aid in existing:
            continue
        db.add(ParticipantCard(
            aruco_id=aid,
            name=f"orientation-{aid}",
            kit="reaction",
            action="orient_vote",
            fire_model="orientation",
            params_json=_json.dumps(params),
            enabled=1,
        ))
        created += 1
    if created:
        db.commit()
    return created


# ---------- module-level singleton -----------------------------------------

router = ParticipantRouter()
