"""Anchor drift detection (ADR 0015).

Once a camera is extrinsically calibrated against the four floor-corner
markers, those four markers' image-space positions are *known* (the
calibration captured them). Any persistent shift in their detected positions
means the camera moved — small bumps, tripod creep, gallery flexing under
weight, kicked corner cards.

This module wraps that logic in a per-connection state so the WS handler can
emit `camera_drift` events when an anchor's rolling-median position has
drifted more than 2% of frame width from its baseline. A separate "camera
lost" event fires when fewer than 2 anchors are visible for >10 seconds.

The auto-recalibration path described in ADR 0015 is *not* implemented here
— this module surfaces the warning; recalibration stays operator-driven for
now.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional


# ---------- thresholds ----------

# Drift threshold as a fraction of the frame's smaller dimension. 2% of 1080
# pixels ≈ 22 px — well above sub-pixel detection noise, well below an
# accidentally-bumped tripod.
DRIFT_FRAC = 0.02
# Median window — how long we average the anchor's image position before
# comparing to baseline. Short enough to react in seconds; long enough that
# a single mis-detection doesn't fire a false alert.
WINDOW_FRAMES = 30  # at 10 fps that's ~3 seconds of smoothing
# Minimum anchors required to call the camera "alive". Below this we emit
# a camera_lost warning instead.
MIN_VISIBLE_ANCHORS = 2
LOST_TIMEOUT_S = 10.0


@dataclass
class _AnchorState:
    """Per-anchor rolling history."""
    name: str           # 'tl' | 'tr' | 'br' | 'bl'
    aruco_id: int
    history: deque = field(default_factory=lambda: deque(maxlen=WINDOW_FRAMES))


@dataclass
class DriftEvent:
    kind: str             # 'drift' | 'camera_lost' | 'recovered'
    severity: str         # 'info' | 'warning' | 'error'
    message: str
    details: dict


class AnchorDriftMonitor:
    """Per-WS-connection state. Cheap to construct, cheap to tick.

    Tracks one camera's anchors. Multi-camera scenarios use one monitor per
    WS connection — the state isn't shared.
    """

    def __init__(self) -> None:
        self._anchors: dict[str, _AnchorState] = {}
        self._baseline: dict[str, tuple[float, float]] = {}
        self._frame_size: Optional[tuple[int, int]] = None
        self._last_visible: float = 0.0
        self._currently_lost: bool = False
        self._currently_drifted: dict[str, bool] = {}
        self._last_alert_t: dict[str, float] = {}  # alert-key → last-emit time

    def configure(
        self,
        baseline_corners_px: dict[str, tuple[float, float]],
        corner_ids: dict[str, int],
        frame_size_px: tuple[int, int],
    ) -> None:
        """Set the calibrated baseline + which marker id is which corner.

        Called whenever the operator (re-)calibrates extrinsic — replays of
        ADR 0012's auto-calibration write a new baseline through here.
        """
        self._baseline = dict(baseline_corners_px)
        self._frame_size = frame_size_px
        self._anchors = {
            name: _AnchorState(name=name, aruco_id=int(aid))
            for name, aid in corner_ids.items()
        }
        self._currently_lost = False
        self._currently_drifted = {}
        self._last_alert_t = {}

    def update(
        self,
        corner_centers_px: dict[str, list[float]],
        now: float,
    ) -> list[DriftEvent]:
        """Advance state for one frame. Returns any newly-fired events.

        `corner_centers_px`: subset of {'tl','tr','br','bl'} → [px, py] for
        the corners detected this frame, supplied by main.py's WS handler.
        """
        events: list[DriftEvent] = []

        if not self._baseline or not self._frame_size:
            return events  # not configured yet, nothing to compare against

        # Update per-anchor rolling history.
        for name, st in self._anchors.items():
            pt = corner_centers_px.get(name)
            if pt is not None:
                st.history.append((float(pt[0]), float(pt[1]), now))

        visible_now = sum(
            1 for st in self._anchors.values()
            if st.history and now - st.history[-1][2] < 1.0
        )
        if visible_now >= MIN_VISIBLE_ANCHORS:
            self._last_visible = now
            if self._currently_lost:
                self._currently_lost = False
                events.append(DriftEvent(
                    kind="recovered",
                    severity="info",
                    message="Camera back in view.",
                    details={"visible_now": visible_now},
                ))
        else:
            # Camera lost? Only fire after the timeout to avoid flapping
            # during natural occlusion (someone walks in front).
            if (now - self._last_visible) > LOST_TIMEOUT_S and not self._currently_lost:
                self._currently_lost = True
                if not self._rate_limit_ok("lost", now, 30.0):
                    return events
                events.append(DriftEvent(
                    kind="camera_lost",
                    severity="warning",
                    message=f"Fewer than {MIN_VISIBLE_ANCHORS} anchors visible "
                            f"for {LOST_TIMEOUT_S:.0f}+ seconds.",
                    details={"visible_now": visible_now, "since_s": round(now - self._last_visible, 1)},
                ))
            return events  # don't run the drift check when the camera is lost

        # Per-anchor drift check.
        w, h = self._frame_size
        thresh_px = DRIFT_FRAC * min(w, h)
        for name, st in self._anchors.items():
            base = self._baseline.get(name)
            if not base or not st.history:
                continue
            # Median of recent observations — robust to a single bad frame.
            xs = sorted([p[0] for p in st.history])
            ys = sorted([p[1] for p in st.history])
            mx = xs[len(xs) // 2]
            my = ys[len(ys) // 2]
            dx = mx - base[0]
            dy = my - base[1]
            d_px = (dx * dx + dy * dy) ** 0.5
            previously_drifted = self._currently_drifted.get(name, False)
            now_drifted = d_px > thresh_px
            self._currently_drifted[name] = now_drifted
            if now_drifted and not previously_drifted:
                if not self._rate_limit_ok(f"drift:{name}", now, 30.0):
                    continue
                events.append(DriftEvent(
                    kind="drift",
                    severity="warning",
                    message=f"Anchor '{name}' has drifted {d_px:.0f} px from "
                            f"its calibrated position — camera may have moved.",
                    details={
                        "anchor": name,
                        "drift_px": round(d_px, 1),
                        "threshold_px": round(thresh_px, 1),
                        "baseline_px": [round(base[0], 1), round(base[1], 1)],
                        "current_median_px": [round(mx, 1), round(my, 1)],
                    },
                ))
            elif previously_drifted and not now_drifted:
                events.append(DriftEvent(
                    kind="recovered",
                    severity="info",
                    message=f"Anchor '{name}' returned to its calibrated position.",
                    details={"anchor": name},
                ))

        return events

    def _rate_limit_ok(self, key: str, now: float, min_interval_s: float) -> bool:
        last = self._last_alert_t.get(key, 0.0)
        if now - last < min_interval_s:
            return False
        self._last_alert_t[key] = now
        return True
