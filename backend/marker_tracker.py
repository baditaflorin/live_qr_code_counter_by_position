"""Stateful marker tracker (ADR 0004).

Per WS connection, tracks each marker's smoothed position and an alive-window
so a one-frame missed detection doesn't drop the marker from the live overlay
or the tracking samples. The two effects this fixes:

- The live count for a zone stops jittering when a marker briefly fails
  detection (motion blur, partial occlusion).
- A marker that disappears for 200 ms and reappears doesn't produce a "left
  the cluster, came back" pair of events in the contact-time data.

The tracker is intentionally per-connection rather than process-global
because two concurrent WS clients shouldn't share smoothing state — they
might be looking at different cameras.

Constants:
- ALPHA = 0.6: EMA blend on each new observation. 1.0 = no smoothing,
  0.0 = positions never update.
- ALIVE_S = 1.0: how long a marker stays "alive" after its last observation.
  Lower = less ghost trail when a marker leaves the frame; higher = more
  resilience to flickering detections.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class _MarkerState:
    aruco_id: int
    cx: float
    cy: float
    last_corners_norm: list[list[float]]
    last_seen: float
    last_detected: float                # last time a real detection landed (vs. ghost frames)
    alive_until: float
    last_meta: dict = field(default_factory=dict)  # person_name, placement, pose etc.
    detect_count: int = 0
    ghost_count: int = 0


class MarkerTracker:
    ALPHA = 0.6
    ALIVE_S = 1.0

    def __init__(self) -> None:
        self._state: dict[int, _MarkerState] = {}

    # ---- update path ------------------------------------------------------

    def update_with_detections(
        self,
        detections_payload: list[dict],
        now: float,
    ) -> tuple[list[dict], int]:
        """Blend in this frame's detections.

        `detections_payload` is the post-processed dict list (the same shape
        the WS sends to the client). We mutate centre + corners onto the EMA
        and refresh the alive timer. Returns the updated list (smoothed) plus
        how many ghost markers (alive but not detected this frame) were merged
        in. Ghost markers are appended to the returned list with the same
        meta as their last sighting.
        """
        seen_ids: set[int] = set()
        # 1. Smooth detected markers.
        for d in detections_payload:
            mid = int(d["aruco_id"])
            seen_ids.add(mid)
            cx, cy = d["center_norm"]
            corners = d.get("corners_norm", [])
            st = self._state.get(mid)
            if st is None:
                st = _MarkerState(
                    aruco_id=mid, cx=cx, cy=cy, last_corners_norm=corners,
                    last_seen=now, last_detected=now, alive_until=now + self.ALIVE_S,
                    last_meta=_marker_meta(d), detect_count=1,
                )
                self._state[mid] = st
            else:
                st.cx = self.ALPHA * cx + (1 - self.ALPHA) * st.cx
                st.cy = self.ALPHA * cy + (1 - self.ALPHA) * st.cy
                if corners:
                    st.last_corners_norm = corners
                st.last_seen = now
                st.last_detected = now
                st.alive_until = now + self.ALIVE_S
                st.last_meta = _marker_meta(d)
                st.detect_count += 1
            # Patch the dict in place with the smoothed centre so downstream
            # consumers see a stable trajectory.
            d["center_norm"] = [st.cx, st.cy]

        # 2. Emit ghost markers for alive entries we didn't see this frame.
        ghosts = 0
        for mid, st in list(self._state.items()):
            if mid in seen_ids:
                continue
            if now > st.alive_until:
                # Genuinely gone. Drop.
                del self._state[mid]
                continue
            # Still alive — append a synthetic detection at the last smoothed
            # position. Marked is_ghost=True so consumers can ignore if needed.
            ghosts += 1
            st.ghost_count += 1
            ghost_entry = {
                "aruco_id": mid,
                "center_norm": [st.cx, st.cy],
                "corners_norm": st.last_corners_norm,
                "is_ghost": True,
                "ghost_age_s": round(now - st.last_detected, 3),
                **st.last_meta,
            }
            detections_payload.append(ghost_entry)

        return detections_payload, ghosts

    # ---- observability ----------------------------------------------------

    def stats(self) -> dict:
        return {
            "alive_markers": len(self._state),
            "ghosts_total": sum(s.ghost_count for s in self._state.values()),
            "detections_total": sum(s.detect_count for s in self._state.values()),
        }


def _marker_meta(d: dict) -> dict:
    """Extract the metadata fields we want to preserve for ghost frames."""
    keep = {}
    for k in ("person_name", "placement", "zone_id", "zone_label", "pose"):
        if k in d:
            keep[k] = d[k]
    return keep
