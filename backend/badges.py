"""Badge rendering — composition, palettes, cell ornaments, generative frames.

Implements ADRs 0068 (composition), 0069 (cell ornaments), 0070 (palette),
0071 (generative frame). Material kit (0072) is documentation, not code.

The marker has to detect; everything else is design surface. Each layer is
optional and composes with the others — call `render_badge(...)` with whatever
combination of params you want.

Implementation notes:
- Pure PIL — no SVG, no cairo, no new system deps.
- The ArUco cell pattern is read from `cv2.aruco.generateImageMarker` and
  re-rendered with the chosen ornament; quiet zone is preserved.
- Detection-rate is verified by re-running `cv2.aruco.detectMarkers` on the
  rendered output — see `verify_detection()` for tests.
"""
from __future__ import annotations

import hashlib
import io
import math
import random
from dataclasses import dataclass
from typing import Callable, Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import detection
from .markers import _load_font


# ---------- palettes (ADR 0070) ----------

@dataclass(frozen=True)
class Palette:
    name: str
    ink: tuple[int, int, int]      # RGB
    paper: tuple[int, int, int]    # RGB
    accent: tuple[int, int, int]   # RGB — used by frame / sigil

    def contrast_ratio(self) -> float:
        """WCAG relative-luminance contrast ratio between ink and paper."""
        return _wcag_contrast(self.ink, self.paper)


PALETTES: dict[str, Palette] = {
    "default":    Palette("default",    (0x00, 0x00, 0x00), (0xff, 0xff, 0xff), (0x57, 0x57, 0x57)),
    "czocha":     Palette("czocha",     (0x1a, 0x28, 0x40), (0xf7, 0xec, 0xd2), (0xa9, 0x6c, 0x2a)),
    "forest":     Palette("forest",     (0x2d, 0x4a, 0x2d), (0xeb, 0xe2, 0xcf), (0x8b, 0x6a, 0x3a)),
    "noir":       Palette("noir",       (0x16, 0x16, 0x16), (0xe8, 0xe4, 0xd8), (0x9a, 0x6a, 0x2a)),
    "terracotta": Palette("terracotta", (0x5c, 0x28, 0x18), (0xf4, 0xdd, 0xc4), (0x8b, 0x4a, 0x32)),
}

WCAG_AA_MIN = 4.5


def _rel_luminance(rgb: tuple[int, int, int]) -> float:
    def chan(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def _wcag_contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = _rel_luminance(a), _rel_luminance(b)
    light, dark = max(la, lb), min(la, lb)
    return (light + 0.05) / (dark + 0.05)


# ---------- cell ornaments (ADR 0069) ----------

CELL_STYLES = ("square", "circle", "hexagon", "six_star", "leaf", "rosette")

# Minimum recommended pixels per marker side per style. Surfaced in the
# calibration warning per ADR 0031.
CELL_MIN_PX_PER_SIDE = {
    "square": 30,
    "circle": 35,
    "hexagon": 50,
    "six_star": 50,
    "leaf": 60,
    "rosette": 60,
}


def _aruco_cell_grid(aruco_id: int) -> np.ndarray:
    """Get the binary cell grid for a marker id — 0 = filled (ink), 1 = empty (paper).

    The dictionary's `bytesList` encodes each marker as packed bits; we render at
    a known small size and downsample to read the cell grid back. Robust across
    OpenCV versions without poking at the internals.
    """
    dict_ = detection.get_dictionary()
    cells_per_side = int(np.sqrt(dict_.markerSize ** 2)) if hasattr(dict_, "markerSize") else None
    # Render at exactly cells_per_side*1 px isn't reliable across versions; use
    # a generous size and threshold.
    img = cv2.aruco.generateImageMarker(dict_, aruco_id, 80)  # 80x80, 1px border + inner cells
    # The marker has a 1-cell black border. Inner pattern is (n-2) cells each side
    # for some encodings. Easiest: just read the inner part by sampling per cell.
    # Detect cells_per_side from image: ArUco markers are (N+2)x(N+2) cells where
    # the outer ring is solid black. For DICT_4X4_*, total = 6x6 cells; inner = 4x4.
    n_total = 6  # works for DICT_4X4_*; 7 for 5x5, 8 for 6x6, 9 for 7x7
    name = detection.get_dictionary_name()
    if "5X5" in name: n_total = 7
    elif "6X6" in name: n_total = 8
    elif "7X7" in name: n_total = 9
    cell_px = img.shape[0] // n_total
    grid = np.zeros((n_total, n_total), dtype=np.uint8)
    for r in range(n_total):
        for c in range(n_total):
            patch = img[r*cell_px:(r+1)*cell_px, c*cell_px:(c+1)*cell_px]
            # 1 if mostly white, 0 if mostly black
            grid[r, c] = 1 if patch.mean() > 127 else 0
    return grid


def _draw_cell(draw: ImageDraw.ImageDraw, x0: float, y0: float, size: float,
               filled: bool, ink: tuple, paper: tuple, style: str) -> None:
    """Draw one cell with the chosen ornament. Uses ink color when filled."""
    if not filled:
        # Empty cell stays paper-colored (already painted on background).
        return
    color = ink
    cx, cy = x0 + size / 2, y0 + size / 2
    r = size * 0.45  # radius for ornaments; leaves a small gap between cells

    if style == "square":
        # Fill the whole cell — same as stock ArUco when ornament radius == size/2
        draw.rectangle([(x0, y0), (x0 + size, y0 + size)], fill=color)
        return

    if style == "circle":
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=color)
        return

    if style == "hexagon":
        pts = [(cx + r * math.cos(math.pi / 6 + i * math.pi / 3),
                cy + r * math.sin(math.pi / 6 + i * math.pi / 3)) for i in range(6)]
        draw.polygon(pts, fill=color)
        return

    if style == "six_star":
        # Chubbier star — outer reaches to cell edge, inner is 0.7× outer so the
        # concave dips are shallow. Detector's center-sample reads as filled.
        outer = size * 0.5
        inner = outer * 0.7
        pts = []
        for i in range(12):
            radius = outer if i % 2 == 0 else inner
            angle = -math.pi / 2 + i * math.pi / 6
            pts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        draw.polygon(pts, fill=color)
        return

    if style == "leaf":
        # Pointed oval — fat in the middle, pointed top + bottom. Fills more
        # cell area than the two-arc almond so the cell-center samples filled.
        rx = size * 0.40
        ry = size * 0.50
        # Build 16-point oval with pointed ends.
        pts = []
        for i in range(16):
            a = -math.pi / 2 + 2 * math.pi * i / 16
            # Stretch endpoints to make the top/bottom pointed.
            scale = 1.0 + 0.15 * abs(math.cos(a))
            pts.append((cx + rx * math.cos(a) * scale * 0.85,
                        cy + ry * math.sin(a) * scale))
        draw.polygon(pts, fill=color)
        return

    if style == "rosette":
        # Four overlapping discs forming a four-petal rosette WITH a center
        # disc so the cell-center always samples filled.
        petal_r = size * 0.32
        petal_offset = size * 0.18
        for i in range(4):
            a = i * math.pi / 2
            pcx = cx + petal_offset * math.cos(a)
            pcy = cy + petal_offset * math.sin(a)
            draw.ellipse([(pcx - petal_r, pcy - petal_r),
                          (pcx + petal_r, pcy + petal_r)], fill=color)
        # Central disc to guarantee center-sample reads filled.
        center_r = size * 0.22
        draw.ellipse([(cx - center_r, cy - center_r),
                      (cx + center_r, cy + center_r)], fill=color)
        return

    # Fallback to square if unknown
    draw.rectangle([(x0, y0), (x0 + size, y0 + size)], fill=color)


def render_styled_marker(
    aruco_id: int,
    size_px: int,
    palette: Palette,
    cell_style: str = "square",
) -> Image.Image:
    """Render a marker as an RGB PIL image with the given palette and cell ornament.

    Includes a paper-colored quiet-zone border at ~10% of size on each side.
    """
    grid = _aruco_cell_grid(aruco_id)
    n = grid.shape[0]
    inner_px = size_px
    quiet_px = max(int(round(inner_px * 0.10)), 8)
    total_px = inner_px + 2 * quiet_px
    img = Image.new("RGB", (total_px, total_px), palette.paper)
    draw = ImageDraw.Draw(img)
    cell_px = inner_px / n
    for r in range(n):
        for c in range(n):
            filled = grid[r, c] == 0  # 0 means filled in our grid convention
            # ArUco markers have a 1-cell solid border around the inner data
            # cells. The detector finds the marker by that square contour, so
            # the border MUST stay rendered as solid squares regardless of the
            # ornament style. Only the inner data cells get the ornament.
            on_border = (r == 0 or r == n - 1 or c == 0 or c == n - 1)
            style_for_cell = "square" if on_border else cell_style
            _draw_cell(
                draw,
                quiet_px + c * cell_px,
                quiet_px + r * cell_px,
                cell_px,
                filled,
                palette.ink,
                palette.paper,
                style_for_cell,
            )
    return img


# ---------- generative frames (ADR 0071) ----------

def _seeded_rng(marker_id: int, salt: str = "") -> random.Random:
    digest = hashlib.sha256(f"{marker_id}:{salt}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _frame_voronoi(canvas: Image.Image, frame_bbox: tuple, marker_id: int, palette: Palette) -> None:
    """Voronoi-cell frame inside `frame_bbox`, decorating outside the marker."""
    x0, y0, x1, y1 = frame_bbox
    rng = _seeded_rng(marker_id, "voronoi")
    n_seeds = 28
    seeds = [(rng.uniform(x0, x1), rng.uniform(y0, y1)) for _ in range(n_seeds)]
    draw = ImageDraw.Draw(canvas)

    # Cheap approximation: for a sparse grid of points in the band, find the
    # closest seed and stipple the boundary regions.
    step = 4
    boundaries: list[tuple[int, int]] = []
    last_owner: dict[int, int] = {}
    for py in range(int(y0), int(y1), step):
        for px in range(int(x0), int(x1), step):
            best, best_d = -1, 1e18
            for i, (sx, sy) in enumerate(seeds):
                d = (sx - px) ** 2 + (sy - py) ** 2
                if d < best_d:
                    best_d = d
                    best = i
            owner_left = last_owner.get(py, best)
            if owner_left != best:
                boundaries.append((px, py))
            last_owner[py] = best
    for (px, py) in boundaries:
        draw.ellipse([(px - 1, py - 1), (px + 1, py + 1)], fill=palette.accent)


def _frame_mandala(canvas: Image.Image, frame_bbox: tuple, marker_id: int, palette: Palette) -> None:
    """Radial mandala — concentric arcs, petal counts derived from id."""
    x0, y0, x1, y1 = frame_bbox
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    max_r = min(x1 - x0, y1 - y0) / 2 - 4
    rng = _seeded_rng(marker_id, "mandala")
    petals = rng.choice([6, 8, 10, 12])
    rings = rng.choice([3, 4, 5])
    draw = ImageDraw.Draw(canvas)

    for ring in range(rings):
        ring_r = max_r * (0.55 + 0.45 * (ring + 1) / rings)
        for k in range(petals):
            a = 2 * math.pi * k / petals + ring * 0.1
            px = cx + ring_r * math.cos(a)
            py = cy + ring_r * math.sin(a)
            r = max_r * 0.04 * (1 - ring / rings * 0.5)
            draw.ellipse([(px - r, py - r), (px + r, py + r)], outline=palette.accent, width=2)


def _frame_flow_field(canvas: Image.Image, frame_bbox: tuple, marker_id: int, palette: Palette) -> None:
    """Curling flow-field strokes around the marker."""
    x0, y0, x1, y1 = frame_bbox
    rng = _seeded_rng(marker_id, "flow")
    draw = ImageDraw.Draw(canvas)
    n_strokes = 30
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2

    def field(x: float, y: float) -> tuple[float, float]:
        t = (x - cx) * 0.01 + (y - cy) * 0.01
        return math.cos(t * 1.7), math.sin(t * 1.3)

    for _ in range(n_strokes):
        # Start on the perimeter of the bbox so strokes wrap around the marker.
        side = rng.randint(0, 3)
        if side == 0:   x, y = rng.uniform(x0, x1), y0
        elif side == 1: x, y = x1, rng.uniform(y0, y1)
        elif side == 2: x, y = rng.uniform(x0, x1), y1
        else:           x, y = x0, rng.uniform(y0, y1)
        path: list[tuple[float, float]] = [(x, y)]
        for _ in range(50):
            dx, dy = field(x, y)
            x += dx * 3
            y += dy * 3
            if not (x0 - 4 <= x <= x1 + 4 and y0 - 4 <= y <= y1 + 4):
                break
            path.append((x, y))
        if len(path) > 2:
            draw.line(path, fill=palette.accent, width=1)


def _frame_constellation(canvas: Image.Image, frame_bbox: tuple, marker_id: int, palette: Palette) -> None:
    """Stars + connecting lines."""
    x0, y0, x1, y1 = frame_bbox
    rng = _seeded_rng(marker_id, "stars")
    draw = ImageDraw.Draw(canvas)
    n_stars = 18
    points = [(rng.uniform(x0, x1), rng.uniform(y0, y1)) for _ in range(n_stars)]
    # Pair each star with its 1–2 nearest neighbours.
    for i, (px, py) in enumerate(points):
        dists = sorted(
            ((j, (qx - px) ** 2 + (qy - py) ** 2) for j, (qx, qy) in enumerate(points) if j != i),
            key=lambda kv: kv[1],
        )
        for j, _ in dists[:2]:
            draw.line([(px, py), points[j]], fill=palette.accent, width=1)
    for px, py in points:
        r = 2.5
        draw.ellipse([(px - r, py - r), (px + r, py + r)], fill=palette.accent)


FRAME_GENERATORS: dict[str, Callable] = {
    "none":         lambda *a, **k: None,
    "voronoi":      _frame_voronoi,
    "mandala":      _frame_mandala,
    "flow_field":   _frame_flow_field,
    "constellation": _frame_constellation,
}


# ---------- composition (ADR 0068) ----------

@dataclass
class BadgeOptions:
    template: str = "default"      # default | czocha | craft
    palette: str = "default"
    cell_style: str = "square"
    frame: str = "none"            # none | voronoi | mandala | flow_field | constellation
    sigil: Optional[str] = None    # short text or emoji shown in a corner
    badge_w: int = 800
    badge_h: int = 1000


def render_badge(aruco_id: int, name: str, opts: BadgeOptions) -> Image.Image:
    """Compose a full badge image. Marker stays detectable regardless of options."""
    palette = PALETTES.get(opts.palette, PALETTES["default"])
    if palette.contrast_ratio() < WCAG_AA_MIN:
        # Refuse low-contrast palettes — would silently break detection.
        raise ValueError(
            f"Palette '{palette.name}' has contrast {palette.contrast_ratio():.2f}:1; "
            f"WCAG-AA minimum is {WCAG_AA_MIN}:1."
        )

    canvas = Image.new("RGB", (opts.badge_w, opts.badge_h), palette.paper)
    draw = ImageDraw.Draw(canvas)

    # 1. Outer frame (template-specific). We support a small set of inline templates.
    _draw_template_frame(draw, opts, palette)

    # 2. Marker block — the only thing that must detect.
    marker_size = int(min(opts.badge_w, opts.badge_h) * 0.55)
    marker_img = render_styled_marker(aruco_id, marker_size, palette, opts.cell_style)
    mx = (opts.badge_w - marker_img.width) // 2
    my = int(opts.badge_h * 0.18)
    canvas.paste(marker_img, (mx, my))

    # 3. Generative frame inside the band between marker and badge edge.
    frame_fn = FRAME_GENERATORS.get(opts.frame, FRAME_GENERATORS["none"])
    if frame_fn is not None and opts.frame != "none":
        # Draw in the upper band above the marker, where decoration won't crowd
        # the quiet zone (already padded inside render_styled_marker).
        band_y0 = int(opts.badge_h * 0.04)
        band_y1 = my - 6
        if band_y1 - band_y0 > 30:
            frame_fn(canvas, (40, band_y0, opts.badge_w - 40, band_y1), aruco_id, palette)

    # 4. Identity strip — name + id.
    big = _load_font(int(opts.badge_h * 0.045))
    small = _load_font(int(opts.badge_h * 0.022))
    name_y = my + marker_img.height + int(opts.badge_h * 0.04)

    if name:
        line = name if len(name) < 28 else name[:27] + "…"
        bbox = draw.textbbox((0, 0), line, font=big)
        tw = bbox[2] - bbox[0]
        draw.text(((opts.badge_w - tw) // 2, name_y), line, fill=palette.ink, font=big)

    id_text = f"#{aruco_id}"
    bbox = draw.textbbox((0, 0), id_text, font=small)
    tw = bbox[2] - bbox[0]
    draw.text(((opts.badge_w - tw) // 2, name_y + int(opts.badge_h * 0.06)),
              id_text, fill=palette.accent, font=small)

    if opts.sigil:
        sigil_font = _load_font(int(opts.badge_h * 0.03))
        draw.text((opts.badge_w - 60, 30), opts.sigil, fill=palette.accent, font=sigil_font)

    return canvas


def _draw_template_frame(draw: ImageDraw.ImageDraw, opts: BadgeOptions, palette: Palette) -> None:
    """Outer ornamental frame per template."""
    w, h = opts.badge_w, opts.badge_h

    if opts.template == "czocha":
        # Heraldic double-line border with inner corner brackets.
        for inset, width in ((10, 3), (24, 1)):
            draw.rectangle([(inset, inset), (w - inset - 1, h - inset - 1)],
                           outline=palette.accent, width=width)
        # Corner brackets (decorative L's).
        bracket = 30
        for cx, cy, dx, dy in [(40, 40, 1, 1), (w - 40, 40, -1, 1),
                               (40, h - 40, 1, -1), (w - 40, h - 40, -1, -1)]:
            draw.line([(cx, cy), (cx + bracket * dx, cy)], fill=palette.accent, width=2)
            draw.line([(cx, cy), (cx, cy + bracket * dy)], fill=palette.accent, width=2)

    elif opts.template == "craft":
        # Off-register two-stroke: deliberate slight offset for handmade feel.
        draw.rectangle([(20, 20), (w - 21, h - 21)], outline=palette.accent, width=2)
        draw.rectangle([(24, 24), (w - 25, h - 25)], outline=palette.ink, width=1)

    else:  # default
        draw.rectangle([(16, 16), (w - 17, h - 17)], outline=palette.accent, width=1)


def render_badge_png(aruco_id: int, name: str, opts: BadgeOptions) -> bytes:
    img = render_badge(aruco_id, name, opts)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------- detection verification ----------

def verify_detection(aruco_id: int, opts: BadgeOptions) -> dict:
    """Render a badge, re-detect the marker, return success + confidence info.

    Used by the build / by the badge preview to assert stylising hasn't broken
    detection. Returns {ok, detected_id, n_corners}.
    """
    img = render_badge(aruco_id, "Test Person", opts)
    arr = np.array(img.convert("RGB"))[:, :, ::-1]  # PIL → BGR for OpenCV
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    dictionary = detection.get_dictionary()
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(dictionary, params)
    corners, ids, _ = detector.detectMarkers(gray)
    if ids is None:
        return {"ok": False, "detected_id": None, "reason": "no markers"}
    detected_ids = [int(x) for x in ids.flatten().tolist()]
    return {
        "ok": aruco_id in detected_ids,
        "detected_id": detected_ids[0] if detected_ids else None,
        "n_detected": len(detected_ids),
    }
