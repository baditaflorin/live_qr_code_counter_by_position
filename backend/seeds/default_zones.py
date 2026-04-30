"""Default zone polygons per formation, in normalized [0..1] camera coords.

Camera POV: 45-60° angled shot from the gallery, looking down at the floor.
Under that projection the rectangular floor of the hall becomes a trapezoid
in the image — wider at the bottom (close to camera, larger pixels) and
narrower at the top (far from camera, smaller pixels). Drawing zones as
axis-aligned rectangles only works for an exact bird's-eye view, which the
real setup never is, so all defaults below are constructed as quads on this
floor trapezoid.

The trapezoid is parameterised in (u, v) where:
  - u ∈ [0, 1] runs left → right across the room as you look at it
  - v ∈ [0, 1] runs back → front (v=0 = far / top of frame, v=1 = near / bottom)

floor_pt(u, v) does bilinear interpolation between the four floor corners,
giving a normalized image coordinate. Zones are then defined in (u, v) space
and converted on the way out, so adjusting the four corners changes every
default zone consistently.
"""
import math
from typing import Iterable

# Floor trapezoid corners in normalized image coords. Tweak these to match
# your camera angle: bring the top corners closer together for a steeper
# (more bird's-eye) view, or push them outward for a flatter (more 45°) view.
FLOOR_TL = (0.25, 0.20)  # back-left  (far from camera)
FLOOR_TR = (0.75, 0.20)  # back-right
FLOOR_BR = (0.95, 0.95)  # front-right (close to camera)
FLOOR_BL = (0.05, 0.95)  # front-left


def _lerp(p1: tuple, p2: tuple, t: float) -> tuple:
    return (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)


def floor_pt(u: float, v: float) -> list[float]:
    """Bilinear-interpolate a point on the floor trapezoid."""
    top = _lerp(FLOOR_TL, FLOOR_TR, u)
    bot = _lerp(FLOOR_BL, FLOOR_BR, u)
    p = _lerp(top, bot, v)
    return [p[0], p[1]]


def _floor_quad(u0: float, u1: float, v0: float, v1: float) -> list[list[float]]:
    """Quad spanning a sub-rectangle of (u, v) space, traced clockwise.

    Order: back-left → back-right → front-right → front-left so the resulting
    polygon is convex when projected back onto the trapezoid.
    """
    return [
        floor_pt(u0, v0),
        floor_pt(u1, v0),
        floor_pt(u1, v1),
        floor_pt(u0, v1),
    ]


def _floor_ellipse(cu: float, cv: float, ru: float, rv: float, n: int = 12) -> list[list[float]]:
    """Approximate an ellipse on the floor (circle in floor coords appears
    foreshortened in the image, which is what we want for the 'circle' zone)."""
    return [floor_pt(cu + ru * math.cos(2 * math.pi * i / n),
                     cv + rv * math.sin(2 * math.pi * i / n)) for i in range(n)]


# ---------- formation templates ----------

# Five strips left-to-right across the floor. Each strip is a trapezoid that
# narrows toward the back of the room — same perspective as the floor itself.
LINE = [
    ("line-a", "Far left",  "#22c55e", _floor_quad(0.00, 0.20, 0.00, 1.00)),
    ("line-b", "Mid-left",  "#84cc16", _floor_quad(0.20, 0.40, 0.00, 1.00)),
    ("line-c", "Centre",    "#eab308", _floor_quad(0.40, 0.60, 0.00, 1.00)),
    ("line-d", "Mid-right", "#f97316", _floor_quad(0.60, 0.80, 0.00, 1.00)),
    ("line-e", "Far right", "#ef4444", _floor_quad(0.80, 1.00, 0.00, 1.00)),
]

# Spectrum is geometrically the same as line — kept separate so users can
# customise one without affecting the other.
SPECTRUM = [
    ("spectrum-1", "Far left",  "#22c55e", _floor_quad(0.00, 0.20, 0.00, 1.00)),
    ("spectrum-2", "Mid-left",  "#84cc16", _floor_quad(0.20, 0.40, 0.00, 1.00)),
    ("spectrum-3", "Centre",    "#eab308", _floor_quad(0.40, 0.60, 0.00, 1.00)),
    ("spectrum-4", "Mid-right", "#f97316", _floor_quad(0.60, 0.80, 0.00, 1.00)),
    ("spectrum-5", "Far right", "#ef4444", _floor_quad(0.80, 1.00, 0.00, 1.00)),
]

TWO_CAMPS = [
    ("camp-left",  "Left side",  "#22c55e", _floor_quad(0.00, 0.50, 0.00, 1.00)),
    ("camp-right", "Right side", "#ef4444", _floor_quad(0.50, 1.00, 0.00, 1.00)),
]

# Four quadrants on the floor. "Back" = top of frame (far from camera);
# "Front" = bottom of frame (close to camera).
MATRIX_2X2 = [
    ("matrix-builders",   "Builders (create · inward)",      "#22c55e", _floor_quad(0.00, 0.50, 0.00, 0.50)),
    ("matrix-dreamers",   "Dreamers (create · outward)",     "#38bdf8", _floor_quad(0.50, 1.00, 0.00, 0.50)),
    ("matrix-fixers",     "Fixers (maintain · inward)",      "#a855f7", _floor_quad(0.00, 0.50, 0.50, 1.00)),
    ("matrix-connectors", "Connectors (maintain · outward)", "#f59e0b", _floor_quad(0.50, 1.00, 0.50, 1.00)),
]

# Foreshortened circle in the centre of the floor.
CIRCLE = [
    ("circle-in", "Stepped in", "#38bdf8", _floor_ellipse(0.5, 0.5, 0.30, 0.30)),
]

# Five depth bands. Row 1 is the start line (back, far from camera); row 5
# is "furthest forward" (close to camera, large in frame).
PRIVILEGE_WALK = [
    ("pw-row-1", "Start line",         "#ef4444", _floor_quad(0.00, 1.00, 0.00, 0.20)),
    ("pw-row-2", "Two steps forward",  "#f97316", _floor_quad(0.00, 1.00, 0.20, 0.40)),
    ("pw-row-3", "Four steps forward", "#eab308", _floor_quad(0.00, 1.00, 0.40, 0.60)),
    ("pw-row-4", "Six steps forward",  "#84cc16", _floor_quad(0.00, 1.00, 0.60, 0.80)),
    ("pw-row-5", "Furthest forward",   "#22c55e", _floor_quad(0.00, 1.00, 0.80, 1.00)),
]

DEFAULTS_BY_FORMATION: dict[str, list[tuple]] = {
    "line": LINE,
    "spectrum": SPECTRUM,
    "two_camps": TWO_CAMPS,
    "matrix_2x2": MATRIX_2X2,
    "circle": CIRCLE,
    "privilege_walk": PRIVILEGE_WALK,
}


def records_for(formations: Iterable[str] | None = None) -> list[dict]:
    """Flat list of zone-create dicts for the requested formations (default: all)."""
    keys = list(formations) if formations else list(DEFAULTS_BY_FORMATION.keys())
    out: list[dict] = []
    for key in keys:
        for name, label, color, poly in DEFAULTS_BY_FORMATION.get(key, []):
            out.append({
                "name": name, "label": label, "color": color,
                "polygon": poly, "formation": key,
            })
    return out
