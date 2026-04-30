"""Default zone polygons per formation, in normalized [0..1] camera coords.

Coordinate system: top-left of the camera view is (0, 0); bottom-right is (1, 1).
The hall is filmed from the gallery (above), so X is across the long wall and Y
is into the room. Templates favour generous polygons with small gaps between them
so people standing on the line don't double-count.
"""
from typing import Iterable


def _rect(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _octagon(cx: float, cy: float, rx: float, ry: float) -> list[list[float]]:
    """Octagon as a circle approximation."""
    import math
    return [
        [cx + rx * math.cos(a), cy + ry * math.sin(a)]
        for a in (math.pi * 2 * i / 8 for i in range(8))
    ]


# Each entry: (name, label, color, polygon)
LINE = [
    ("line-a", "Strongly agree",     "#22c55e", _rect(0.00, 0.05, 0.18, 0.95)),
    ("line-b", "Agree",              "#84cc16", _rect(0.20, 0.05, 0.38, 0.95)),
    ("line-c", "Middle",             "#eab308", _rect(0.40, 0.05, 0.60, 0.95)),
    ("line-d", "Disagree",           "#f97316", _rect(0.62, 0.05, 0.80, 0.95)),
    ("line-e", "Strongly disagree",  "#ef4444", _rect(0.82, 0.05, 1.00, 0.95)),
]

# Same polygons as LINE — spectrum is just a five-step line. The frontend
# treats them identically; we keep them as a separate set so the labels can
# read "first option" / "second option" which fits Block 2 better.
SPECTRUM = [
    ("spectrum-1", "First option (very)",  "#22c55e", _rect(0.00, 0.05, 0.18, 0.95)),
    ("spectrum-2", "First option",         "#84cc16", _rect(0.20, 0.05, 0.38, 0.95)),
    ("spectrum-3", "In-between",           "#eab308", _rect(0.40, 0.05, 0.60, 0.95)),
    ("spectrum-4", "Second option",        "#f97316", _rect(0.62, 0.05, 0.80, 0.95)),
    ("spectrum-5", "Second option (very)", "#ef4444", _rect(0.82, 0.05, 1.00, 0.95)),
]

TWO_CAMPS = [
    ("camp-yes", "Yes · True for me",     "#22c55e", _rect(0.00, 0.05, 0.48, 0.95)),
    ("camp-no",  "No · Not true for me",  "#ef4444", _rect(0.52, 0.05, 1.00, 0.95)),
]

MATRIX_2X2 = [
    # Two axes: create-vs-maintain (top vs bottom) and inward-vs-outward (left vs right).
    ("matrix-builders",   "Builders (create · inward)",    "#22c55e", _rect(0.00, 0.00, 0.48, 0.48)),
    ("matrix-dreamers",   "Dreamers (create · outward)",   "#38bdf8", _rect(0.52, 0.00, 1.00, 0.48)),
    ("matrix-fixers",     "Fixers (maintain · inward)",    "#a855f7", _rect(0.00, 0.52, 0.48, 1.00)),
    ("matrix-connectors", "Connectors (maintain · outward)", "#f59e0b", _rect(0.52, 0.52, 1.00, 1.00)),
]

CIRCLE = [
    # One inside-the-circle zone; everyone outside is implicitly "stayed where they were".
    ("circle-in", "Stepped in", "#38bdf8", _octagon(0.5, 0.5, 0.28, 0.36)),
]

# Five depth bands for the privilege walk. Y=0 is the front wall (where the
# line started); answering "yes" moves people toward Y=1.
PRIVILEGE_WALK = [
    ("pw-row-1", "Start line",         "#ef4444", _rect(0.05, 0.00, 0.95, 0.18)),
    ("pw-row-2", "Two steps forward",  "#f97316", _rect(0.05, 0.20, 0.95, 0.38)),
    ("pw-row-3", "Four steps forward", "#eab308", _rect(0.05, 0.40, 0.95, 0.58)),
    ("pw-row-4", "Six steps forward",  "#84cc16", _rect(0.05, 0.60, 0.95, 0.78)),
    ("pw-row-5", "Furthest forward",   "#22c55e", _rect(0.05, 0.80, 0.95, 1.00)),
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
