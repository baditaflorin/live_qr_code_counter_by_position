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
#
# Design philosophy: the marker is a *small element* of a deliberate
# composition, not the visual subject of the badge. The participant should
# read the badge as art-with-a-stamp-in-it, not as a QR-with-decoration.
#
# Each template specifies (relative to badge size):
#   - marker_size_frac: 0.30 means marker is 30% of min(W, H) — much smaller
#     than the original 0.55. Lots of room for the rest.
#   - marker_pos: (x_frac, y_frac) of the marker top-left.
#   - marker_rotation_deg: a slight rotation reads as handmade, not digital.
#   - bg_pattern: full-bleed background fill function.
#   - motif: a foreground illustration that frames or contains the marker.
#   - name_layout: (x_frac, y_frac, anchor, scale).
#   - border: a per-template border treatment, often subtle or absent.

@dataclass
class BadgeOptions:
    template: str = "minimal"
    palette: str = "default"
    cell_style: str = "square"
    frame: str = "none"
    sigil: Optional[str] = None
    badge_w: int = 1000
    badge_h: int = 1300


# ---------- background patterns ----------

def _bg_paper_grain(canvas: Image.Image, palette: Palette, seed: int) -> None:
    """Subtle pixel-noise paper-grain texture across the full surface."""
    rng = _seeded_rng(seed, "paper")
    arr = np.array(canvas).astype(np.int16)
    h, w = arr.shape[:2]
    # Generate seeded noise; ±6 RGB per pixel — invisible up close, gives the
    # surface a non-digital warmth.
    noise = (np.array([rng.gauss(0, 2) for _ in range(h * w * 3)])
             .reshape(h, w, 3))
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    canvas.paste(Image.fromarray(arr))


def _bg_parchment(canvas: Image.Image, palette: Palette, seed: int) -> None:
    """Warm radial gradient suggesting aged parchment + paper grain."""
    w, h = canvas.size
    cx, cy = w / 2, h / 2
    max_r = math.hypot(cx, cy)
    arr = np.array(canvas).astype(np.float32)
    yy, xx = np.indices((h, w), dtype=np.float32)
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / max_r
    # Edges darken ~12 %.
    falloff = 1.0 - dist * 0.12
    arr = arr * falloff[..., None]
    canvas.paste(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)))
    _bg_paper_grain(canvas, palette, seed)


def _bg_watermark_frame(canvas: Image.Image, palette: Palette, seed: int, frame_name: str) -> None:
    """A generative frame at low alpha across the whole surface."""
    if frame_name == "none":
        return
    overlay = Image.new("RGB", canvas.size, palette.paper)
    fn = FRAME_GENERATORS.get(frame_name)
    if fn is None:
        return
    fn(overlay, (0, 0, canvas.size[0], canvas.size[1]), seed, palette)
    # Blend at 25 % so the marker stays the contrast-dominant element.
    out = Image.blend(canvas, overlay, 0.25)
    canvas.paste(out)


# ---------- foreground motifs ----------

def _safe_quiet_box(marker_box: tuple, pad: int = 18) -> tuple:
    """The hands-off zone around the marker — motifs must not draw inside this."""
    mx0, my0, mx1, my1 = marker_box
    return (mx0 - pad, my0 - pad, mx1 + pad, my1 + pad)


def _motif_heraldic_scroll(canvas: Image.Image, opts: BadgeOptions, palette: Palette,
                           marker_box: tuple, name: str) -> None:
    """Full heraldic shield: laurel wreath ringing the marker, crown above,
    banner below carrying the name, ornamental corner fleurs. The marker reads
    as the *crest* of a coat of arms — small inside an illustrated scene."""
    draw = ImageDraw.Draw(canvas)
    mx0, my0, mx1, my1 = marker_box
    cx_m = (mx0 + mx1) / 2
    cy_m = (my0 + my1) / 2
    w, h = canvas.size
    qx0, qy0, qx1, qy1 = _safe_quiet_box(marker_box)

    # 1. Laurel wreath ringing the marker. Two arcs of leaves on left and right.
    wreath_r = (mx1 - mx0) * 0.85
    leaf_count = 9
    for sign in (-1, 1):
        for i in range(leaf_count):
            # Arc from bottom (-pi/2 - 0.6) up to top (-pi/2 + 0.6) on each side.
            t = i / (leaf_count - 1)
            angle = math.pi * (0.5 + sign * (0.55 - t * 1.1))
            lx = cx_m + wreath_r * math.cos(angle)
            ly = cy_m + wreath_r * math.sin(angle)
            # Each leaf is a tilted oval, pointing tangent to the wreath circle.
            tilt_deg = -math.degrees(angle) - sign * 90 + 90
            leaf_size = 38
            leaf = Image.new("RGBA", (leaf_size, int(leaf_size * 0.45)), (0, 0, 0, 0))
            ld = ImageDraw.Draw(leaf)
            ld.ellipse([(0, 0), (leaf_size - 1, int(leaf_size * 0.45) - 1)],
                       fill=palette.accent + (255,))
            ld.line([(2, leaf_size * 0.225), (leaf_size - 3, leaf_size * 0.225)],
                    fill=palette.ink + (255,), width=1)
            leaf = leaf.rotate(tilt_deg, expand=True, resample=Image.BICUBIC)
            # Skip leaves that would fall inside the marker's quiet zone.
            leaf_cx = int(lx); leaf_cy = int(ly)
            if qx0 <= leaf_cx <= qx1 and qy0 <= leaf_cy <= qy1:
                continue
            canvas.paste(leaf, (int(lx - leaf.width / 2), int(ly - leaf.height / 2)), leaf)
        # Subtle arc line through the leaves.
        for i in range(20):
            t = i / 19
            a = math.pi * (0.5 + sign * (0.55 - t * 1.1))
            ax = cx_m + wreath_r * math.cos(a)
            ay = cy_m + wreath_r * math.sin(a)
            draw.ellipse([(ax - 1, ay - 1), (ax + 1, ay + 1)], fill=palette.accent)

    # 2. Crown above the marker — three points + base.
    crown_w = (mx1 - mx0) * 0.85
    crown_h = (my1 - my0) * 0.22
    crown_y = my0 - crown_h - 8
    crown_x0 = cx_m - crown_w / 2
    crown_x1 = cx_m + crown_w / 2
    pts = [
        (crown_x0, crown_y + crown_h),
        (crown_x0 + crown_w * 0.10, crown_y + crown_h * 0.20),
        (crown_x0 + crown_w * 0.30, crown_y + crown_h * 0.65),
        (crown_x0 + crown_w * 0.50, crown_y + crown_h * 0.05),
        (crown_x0 + crown_w * 0.70, crown_y + crown_h * 0.65),
        (crown_x0 + crown_w * 0.90, crown_y + crown_h * 0.20),
        (crown_x1, crown_y + crown_h),
    ]
    draw.polygon(pts, fill=palette.accent, outline=palette.ink)
    # Three small jewels.
    for jx in (crown_x0 + crown_w * 0.10, cx_m, crown_x1 - crown_w * 0.10):
        draw.ellipse([(jx - 6, crown_y + crown_h * 0.30 - 6),
                      (jx + 6, crown_y + crown_h * 0.30 + 6)], fill=palette.ink)

    # 3. Banner ribbon below the marker — wide, with carved ends + pennant tails.
    band_y = my1 + int(wreath_r * 0.25) + 10
    band_h = int(h * 0.11)
    band_x0 = int(w * 0.08)
    band_x1 = int(w * 0.92)
    notch = 32
    pennant_drop = 18
    pts = [
        (band_x0 + 16, band_y + pennant_drop // 2),
        (band_x0, band_y),
        (band_x0 + notch, band_y - 6),
        (band_x1 - notch, band_y - 6),
        (band_x1, band_y),
        (band_x1 - 16, band_y + pennant_drop // 2),
        (band_x1, band_y + band_h),
        (band_x1 - notch, band_y + band_h + pennant_drop),
        (band_x0 + notch, band_y + band_h + pennant_drop),
        (band_x0, band_y + band_h),
    ]
    draw.polygon(pts, fill=palette.ink, outline=palette.accent)
    # Inner accent line.
    for x_pad, y_pad in ((10, 8),):
        draw.line([(band_x0 + x_pad, band_y + y_pad), (band_x1 - x_pad, band_y + y_pad)],
                  fill=palette.accent, width=1)
        draw.line([(band_x0 + x_pad, band_y + band_h - y_pad), (band_x1 - x_pad, band_y + band_h - y_pad)],
                  fill=palette.accent, width=1)

    # Name on the ribbon, paper-coloured, prominent.
    if name:
        font = _load_font(int(band_h * 0.55))
        line = name if len(name) < 26 else name[:25] + "…"
        bbox = draw.textbbox((0, 0), line, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        ty = band_y + (band_h - th) // 2 - 4
        draw.text((cx_m - tw / 2, ty), line, fill=palette.paper, font=font)

    # 4. Corner fleurs — small ornament at each badge corner.
    for cx, cy in [(50, 50), (w - 50, 50), (50, h - 50), (w - 50, h - 50)]:
        # Three-petal fleur-de-lis-ish mark.
        for a in (-math.pi / 2, -math.pi / 2 + math.pi * 0.45, -math.pi / 2 - math.pi * 0.45):
            tx = cx + 12 * math.cos(a)
            ty = cy + 12 * math.sin(a)
            draw.ellipse([(tx - 4, ty - 4), (tx + 4, ty + 4)], fill=palette.accent)
        draw.ellipse([(cx - 3, cy - 3), (cx + 3, cy + 3)], fill=palette.ink)


def _motif_botanical_vines(canvas: Image.Image, opts: BadgeOptions, palette: Palette,
                           marker_box: tuple, name: str) -> None:
    """A circular wreath of leaves around the marker, plus vines growing
    up from the bottom corners with leaves and small flowers. The marker
    sits like a stone in a garden, not as the subject of the badge."""
    draw = ImageDraw.Draw(canvas)
    w, h = canvas.size
    mx0, my0, mx1, my1 = marker_box
    cx_m = (mx0 + mx1) / 2
    cy_m = (my0 + my1) / 2
    rng = _seeded_rng(opts.badge_w * 7919 + opts.badge_h, "vines")

    # 1. Wreath ringing the marker — placed well outside the quiet zone.
    qx0, qy0, qx1, qy1 = _safe_quiet_box(marker_box, pad=20)
    wreath_r = max(mx1 - mx0, my1 - my0) * 0.95
    n_leaves = 28
    for i in range(n_leaves):
        angle = -math.pi / 2 + 2 * math.pi * i / n_leaves
        # Skip the top arc so the marker has a "view" upward.
        if -math.pi * 0.85 < angle < -math.pi * 0.15:
            continue
        lx = cx_m + wreath_r * math.cos(angle)
        ly = cy_m + wreath_r * math.sin(angle)
        tilt_deg = -math.degrees(angle) - 90 + rng.uniform(-15, 15)
        leaf_size = int(rng.uniform(38, 48))
        leaf = Image.new("RGBA", (leaf_size, int(leaf_size * 0.42)), (0, 0, 0, 0))
        ld = ImageDraw.Draw(leaf)
        ld.ellipse([(0, 0), (leaf_size - 1, int(leaf_size * 0.42) - 1)],
                   fill=palette.accent + (255,))
        ld.line([(3, leaf_size * 0.21), (leaf_size - 3, leaf_size * 0.21)],
                fill=palette.ink + (255,), width=1)
        leaf = leaf.rotate(tilt_deg, expand=True, resample=Image.BICUBIC)
        leaf_cx, leaf_cy = int(lx), int(ly)
        # Skip leaves that would overlap the quiet zone.
        if qx0 <= leaf_cx <= qx1 and qy0 <= leaf_cy <= qy1:
            continue
        canvas.paste(leaf, (int(lx - leaf.width / 2), int(ly - leaf.height / 2)), leaf)

    # 2. Long vines climbing from the two bottom corners with multiple leaves.
    for side in (-1, 1):
        sx = 50 if side < 0 else w - 50
        sy = h - 50
        # Stronger vine path — sweeps inward and upward.
        pts = []
        for t in [i / 60 for i in range(61)]:
            tx = sx + side * (-1) * t * (w * 0.34) + math.sin(t * 5) * 22
            ty = sy - t * (h * 0.65) + math.cos(t * 4) * 14
            pts.append((tx, ty))
        # Draw vine as 3 parallel strokes for a thicker organic look.
        draw.line(pts, fill=palette.accent, width=4)
        draw.line([(p[0] + 1, p[1] + 1) for p in pts], fill=palette.ink, width=1)
        # Lots of leaves along the vine.
        for i in range(6, len(pts), 5):
            px, py = pts[i]
            leaf_size = int(rng.uniform(28, 42))
            leaf_h = int(leaf_size * 0.42)
            leaf = Image.new("RGBA", (leaf_size, leaf_h), (0, 0, 0, 0))
            ld = ImageDraw.Draw(leaf)
            ld.ellipse([(0, 0), (leaf_size - 1, leaf_h - 1)], fill=palette.accent + (255,))
            ld.line([(3, leaf_h // 2), (leaf_size - 3, leaf_h // 2)], fill=palette.ink + (255,), width=1)
            tilt = side * 60 + rng.uniform(-30, 30)
            leaf = leaf.rotate(tilt, expand=True, resample=Image.BICUBIC)
            offset_dx = side * int(leaf.width * 0.4)
            canvas.paste(leaf, (int(px - leaf.width / 2 + offset_dx),
                                int(py - leaf.height / 2)), leaf)
        # Small flowers near the top of each vine.
        for i in (len(pts) - 5, len(pts) - 15):
            if i < 0:
                continue
            fx, fy = pts[i]
            for petal_a in [k * math.pi / 3 for k in range(6)]:
                ppx = fx + 9 * math.cos(petal_a)
                ppy = fy + 9 * math.sin(petal_a)
                draw.ellipse([(ppx - 5, ppy - 5), (ppx + 5, ppy + 5)],
                             fill=palette.paper, outline=palette.accent)
            draw.ellipse([(fx - 4, fy - 4), (fx + 4, fy + 4)], fill=palette.accent)


def _motif_postage_perforation(canvas: Image.Image, opts: BadgeOptions, palette: Palette,
                               marker_box: tuple, name: str) -> None:
    """Postage-stamp aesthetic — scalloped perforated edge, marginal text,
    a denomination cartouche, decorative cross-hatched fill in the body."""
    draw = ImageDraw.Draw(canvas)
    w, h = canvas.size
    mx0, my0, mx1, my1 = marker_box

    # 1. Cross-hatch background in the body of the stamp (not over the marker).
    hatch_step = 12
    inset = 50
    for d in range(-h, w, hatch_step):
        draw.line([(d, inset), (d + h, inset + h)], fill=palette.accent, width=1)
    # Erase hatching over the marker quiet zone with a generous safe box.
    qx0, qy0, qx1, qy1 = _safe_quiet_box(marker_box, pad=24)
    draw.rectangle([(qx0, qy0), (qx1, qy1)], fill=palette.paper)

    # 2. Perforated edge — paper-coloured circles eating into the boundary.
    teeth_dia = 26
    step = 40
    for x in range(step // 2, w, step):
        draw.ellipse([(x - teeth_dia / 2, -teeth_dia / 2),
                      (x + teeth_dia / 2, teeth_dia / 2)], fill=palette.paper)
        draw.ellipse([(x - teeth_dia / 2, h - teeth_dia / 2),
                      (x + teeth_dia / 2, h + teeth_dia / 2)], fill=palette.paper)
    for y in range(step // 2, h, step):
        draw.ellipse([(-teeth_dia / 2, y - teeth_dia / 2),
                      (teeth_dia / 2, y + teeth_dia / 2)], fill=palette.paper)
        draw.ellipse([(w - teeth_dia / 2, y - teeth_dia / 2),
                      (w + teeth_dia / 2, y + teeth_dia / 2)], fill=palette.paper)

    # 3. Inner border framing the stamp body.
    draw.rectangle([(36, 36), (w - 36, h - 36)], outline=palette.ink, width=3)
    draw.rectangle([(44, 44), (w - 44, h - 44)], outline=palette.accent, width=1)

    # 4. Marginal text — top and bottom inscriptions.
    margin_font = _load_font(int(h * 0.028))
    top_text = "  ·  ".join(["WEMESHUP", "CZOCHA", "WITNESS"])
    bbox = draw.textbbox((0, 0), top_text, font=margin_font)
    tw = bbox[2] - bbox[0]
    draw.text(((w - tw) / 2, 60), top_text, fill=palette.ink, font=margin_font)

    if name:
        bottom_font = _load_font(int(h * 0.05))
        line = name if len(name) < 22 else name[:21] + "…"
        bbox = draw.textbbox((0, 0), line, font=bottom_font)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) / 2, h - 130), line, fill=palette.ink, font=bottom_font)

    # 5. Denomination cartouche in the lower-right — a small medallion.
    den_cx, den_cy = w - 110, h - 200
    den_r = 50
    draw.ellipse([(den_cx - den_r, den_cy - den_r), (den_cx + den_r, den_cy + den_r)],
                 fill=palette.ink, outline=palette.accent, width=2)
    draw.ellipse([(den_cx - den_r + 8, den_cy - den_r + 8),
                  (den_cx + den_r - 8, den_cy + den_r - 8)],
                 outline=palette.accent, width=1)
    val_font = _load_font(36)
    val_text = "I"  # "first" — generic Roman one
    bbox = draw.textbbox((0, 0), val_text, font=val_font)
    tw_v, th_v = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((den_cx - tw_v / 2, den_cy - th_v / 2 - 4), val_text,
              fill=palette.paper, font=val_font)


def _motif_poster_panel(canvas: Image.Image, opts: BadgeOptions, palette: Palette,
                        marker_box: tuple, name: str) -> None:
    """Inverted color: badge body is ink, with a small paper 'panel' framing
    the marker. Big paper-coloured typography fills the rest. Reads as a
    poster with a tiny stamp, not as an ID card."""
    draw = ImageDraw.Draw(canvas)
    w, h = canvas.size
    mx0, my0, mx1, my1 = marker_box
    cx_m = (mx0 + mx1) / 2

    # 1. Repaint the entire canvas in ink color (the bg_pattern handler set
    #    paper; the poster motif inverts to dark).
    draw.rectangle([(0, 0), (w, h)], fill=palette.ink)

    # 2. Draw a paper-coloured panel slightly larger than the marker — gives
    #    the marker a clean white quiet zone surrounded by ink. Detection
    #    needs the marker's outer black ring to have a sharp white border.
    pad = 36
    panel = (mx0 - pad, my0 - pad, mx1 + pad, my1 + pad)
    draw.rectangle(panel, fill=palette.paper)
    # Thin accent line around the panel.
    draw.rectangle(panel, outline=palette.accent, width=2)

    # 3. Above the marker — a workshop label in small caps, paper colour.
    label_font = _load_font(int(h * 0.022))
    label_text = "·  WITNESS  ·  CZOCHA  ·  WEMESHUP  ·"
    bbox = draw.textbbox((0, 0), label_text, font=label_font)
    tw = bbox[2] - bbox[0]
    draw.text(((w - tw) / 2, int(h * 0.05)), label_text, fill=palette.paper, font=label_font)

    # 4. Big participant name across the lower half — paper colour, monumental.
    if name:
        # Aim for ~70% of badge width.
        target_w = w * 0.78
        font_px = int(h * 0.10)
        name_font = _load_font(font_px)
        line = name if len(name) < 22 else name[:21] + "…"
        bbox = draw.textbbox((0, 0), line, font=name_font)
        tw = bbox[2] - bbox[0]
        # Reduce font size if the name is too wide.
        while tw > target_w and font_px > 24:
            font_px -= 4
            name_font = _load_font(font_px)
            bbox = draw.textbbox((0, 0), line, font=name_font)
            tw = bbox[2] - bbox[0]
        draw.text(((w - tw) / 2, my1 + pad + int(h * 0.10)), line, fill=palette.paper, font=name_font)

    # 5. Decorative dingbats above and below the name.
    deco_y_top = my1 + pad + int(h * 0.07)
    deco_y_bot = h - int(h * 0.10)
    for y in (deco_y_top, deco_y_bot):
        # Three diamond ornaments in the centre.
        for offset in (-w * 0.08, 0, w * 0.08):
            x = cx_m + offset
            for r, fill in ((10, palette.accent), (5, palette.paper)):
                draw.polygon([(x, y - r), (x + r, y), (x, y + r), (x - r, y)], fill=fill)

    # 6. Corner pin marks — small cream dots at all four corners.
    for cx, cy in [(40, 40), (w - 40, 40), (40, h - 40), (w - 40, h - 40)]:
        draw.ellipse([(cx - 4, cy - 4), (cx + 4, cy + 4)], fill=palette.paper)


# ---------- per-template layout ----------

# Each layout dict specifies how the badge composes itself.
TEMPLATE_LAYOUTS: dict[str, dict] = {
    # Modern, generous whitespace. Marker is a small block, name dominates.
    # Position accounts for the marker's quiet-zone padding (~10% on each side)
    # so the right edge lands inside the badge.
    "minimal": {
        "marker_size_frac": 0.30,
        "marker_pos_frac": (0.58, 0.08),  # upper-right with margin
        "marker_rotation_deg": 0,
        "bg_pattern": "paper_grain",
        "motif": None,
        "name_pos_frac": (0.08, 0.55),
        "name_anchor": "left",
        "name_size_frac": 0.085,
        "id_pos_frac": (0.08, 0.66),
        "border": "none",
    },
    # Coat-of-arms feel. Marker sits as the crest at top; banner with name below.
    "heraldic": {
        "marker_size_frac": 0.36,
        "marker_pos_frac": (0.32, 0.10),  # centred horizontally, top portion
        "marker_rotation_deg": 0,
        "bg_pattern": "parchment",
        "motif": "heraldic_scroll",
        "name_pos_frac": None,  # name is drawn inside the ribbon by the motif
        "name_anchor": "center",
        "name_size_frac": 0,
        "id_pos_frac": (0.50, 0.92),
        "border": "double_brackets",
    },
    # Hand-pressed feel. Marker slightly off-axis. Paper grain + ink bleed.
    "craft": {
        "marker_size_frac": 0.34,
        "marker_pos_frac": (0.33, 0.18),
        "marker_rotation_deg": -3,
        "bg_pattern": "paper_grain",
        "motif": None,
        "name_pos_frac": (0.5, 0.65),
        "name_anchor": "center",
        "name_size_frac": 0.075,
        "id_pos_frac": (0.5, 0.80),
        "border": "off_register",
    },
    # Botanical / organic. Vines around a small centred marker.
    "botanical": {
        "marker_size_frac": 0.30,
        "marker_pos_frac": (0.35, 0.18),
        "marker_rotation_deg": 0,
        "bg_pattern": "parchment",
        "motif": "botanical_vines",
        "name_pos_frac": (0.5, 0.78),
        "name_anchor": "center",
        "name_size_frac": 0.078,
        "id_pos_frac": (0.5, 0.88),
        "border": "thin_inner",
    },
    # Postage stamp. Tall, scalloped edge, marker small in upper-left.
    "postage": {
        "marker_size_frac": 0.28,
        "marker_pos_frac": (0.10, 0.10),
        "marker_rotation_deg": 0,
        "bg_pattern": "parchment",
        "motif": "postage_perforation",
        "name_pos_frac": (0.5, 0.70),
        "name_anchor": "center",
        "name_size_frac": 0.068,
        "id_pos_frac": (0.5, 0.82),
        "border": "none",
    },
    # Inverted color scheme — badge is ink-color all over, marker sits in a
    # small paper panel, big paper-coloured typography dominates. The marker
    # stops being "the dark thing" — it becomes a small window in a dark poster.
    "poster": {
        "marker_size_frac": 0.26,
        "marker_pos_frac": (0.37, 0.18),
        "marker_rotation_deg": 0,
        "bg_pattern": None,  # poster motif handles its own background
        "motif": "poster_panel",
        "name_pos_frac": None,  # name is rendered by the motif itself
        "name_anchor": "center",
        "name_size_frac": 0,
        "id_pos_frac": None,
        "border": "none",
    },
    # Old default — kept for backward-compat with the very-first call shape.
    "default": {
        "marker_size_frac": 0.40,
        "marker_pos_frac": (0.30, 0.10),
        "marker_rotation_deg": 0,
        "bg_pattern": None,
        "motif": None,
        "name_pos_frac": (0.5, 0.62),
        "name_anchor": "center",
        "name_size_frac": 0.06,
        "id_pos_frac": (0.5, 0.72),
        "border": "thin_inner",
    },
}


def render_badge(aruco_id: int, name: str, opts: BadgeOptions) -> Image.Image:
    """Compose a badge as a layered scene — bg pattern, generative watermark,
    motif, marker, identity strip, border. The marker stays detectable
    regardless of how loud the rest of the composition is.
    """
    palette = PALETTES.get(opts.palette, PALETTES["default"])
    if palette.contrast_ratio() < WCAG_AA_MIN:
        raise ValueError(
            f"Palette '{palette.name}' has contrast {palette.contrast_ratio():.2f}:1; "
            f"WCAG-AA minimum is {WCAG_AA_MIN}:1."
        )

    layout = TEMPLATE_LAYOUTS.get(opts.template, TEMPLATE_LAYOUTS["minimal"])

    canvas = Image.new("RGB", (opts.badge_w, opts.badge_h), palette.paper)
    seed = aruco_id * 9973 + opts.badge_w + opts.badge_h

    # 1. Background pattern (full bleed).
    bg = layout["bg_pattern"]
    if bg == "paper_grain":
        _bg_paper_grain(canvas, palette, seed)
    elif bg == "parchment":
        _bg_parchment(canvas, palette, seed)

    # 2. Generative frame (full-bleed watermark) — much subtler than before.
    if opts.frame and opts.frame != "none":
        _bg_watermark_frame(canvas, palette, aruco_id, opts.frame)

    # 3. Marker — sized + positioned per template.
    marker_size = int(min(opts.badge_w, opts.badge_h) * layout["marker_size_frac"])
    marker_img = render_styled_marker(aruco_id, marker_size, palette, opts.cell_style)
    if layout["marker_rotation_deg"]:
        marker_img = marker_img.rotate(
            layout["marker_rotation_deg"],
            resample=Image.BICUBIC,
            expand=True,
            fillcolor=palette.paper,
        )
    mx = int(opts.badge_w * layout["marker_pos_frac"][0])
    my = int(opts.badge_h * layout["marker_pos_frac"][1])
    # Clamp so the marker stays fully inside the badge regardless of template
    # mistakes — a clipped marker can't be detected.
    mx = max(8, min(mx, opts.badge_w - marker_img.width - 8))
    my = max(8, min(my, opts.badge_h - marker_img.height - 8))
    canvas.paste(marker_img, (mx, my))

    # 4. Foreground motif (drawn on top of the marker layer's surroundings;
    #    motifs themselves do not cross the marker's quiet zone).
    motif_name = layout.get("motif")
    if motif_name:
        marker_box = (mx, my, mx + marker_img.width, my + marker_img.height)
        if motif_name == "heraldic_scroll":
            _motif_heraldic_scroll(canvas, opts, palette, marker_box, name)
        elif motif_name == "botanical_vines":
            _motif_botanical_vines(canvas, opts, palette, marker_box, name)
        elif motif_name == "postage_perforation":
            _motif_postage_perforation(canvas, opts, palette, marker_box, name)
        elif motif_name == "poster_panel":
            # Poster repaints the whole canvas; do this BEFORE the marker is on it.
            # We need to redo the marker paste since poster_panel paints over it.
            _motif_poster_panel(canvas, opts, palette, marker_box, name)
            canvas.paste(marker_img, (mx, my))

    # 5. Identity strip — name + id (unless the motif handled the name itself).
    draw = ImageDraw.Draw(canvas)
    if layout.get("name_pos_frac") and layout.get("name_size_frac", 0) > 0 and name:
        font_px = int(opts.badge_h * layout["name_size_frac"])
        name_font = _load_font(font_px)
        line = name if len(name) < 26 else name[:25] + "…"
        bbox = draw.textbbox((0, 0), line, font=name_font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        nx = int(opts.badge_w * layout["name_pos_frac"][0])
        ny = int(opts.badge_h * layout["name_pos_frac"][1])
        if layout["name_anchor"] == "center":
            nx -= tw // 2
        elif layout["name_anchor"] == "right":
            nx -= tw
        draw.text((nx, ny), line, fill=palette.ink, font=name_font)

    if layout.get("id_pos_frac"):
        id_font = _load_font(int(opts.badge_h * 0.025))
        id_text = f"#{aruco_id}"
        bbox = draw.textbbox((0, 0), id_text, font=id_font)
        tw = bbox[2] - bbox[0]
        ix = int(opts.badge_w * layout["id_pos_frac"][0])
        iy = int(opts.badge_h * layout["id_pos_frac"][1])
        if layout["name_anchor"] == "center":
            ix -= tw // 2
        elif layout["name_anchor"] == "right":
            ix -= tw
        draw.text((ix, iy), id_text, fill=palette.accent, font=id_font)

    # 6. Border treatment.
    _draw_border(draw, opts, palette, layout["border"])

    # 7. Optional sigil in the corner opposite the marker.
    if opts.sigil:
        sigil_font = _load_font(int(opts.badge_h * 0.035))
        # Place it diagonally opposite the marker.
        is_left = layout["marker_pos_frac"][0] < 0.5
        sx = opts.badge_w - 60 if is_left else 30
        sy = opts.badge_h - 60 if layout["marker_pos_frac"][1] < 0.5 else 30
        draw.text((sx, sy), opts.sigil, fill=palette.accent, font=sigil_font)

    return canvas


def _draw_border(draw: ImageDraw.ImageDraw, opts: BadgeOptions, palette: Palette, kind: str) -> None:
    w, h = opts.badge_w, opts.badge_h
    if kind == "thin_inner":
        draw.rectangle([(20, 20), (w - 21, h - 21)], outline=palette.accent, width=1)
    elif kind == "double_brackets":
        for inset, width in ((14, 3), (28, 1)):
            draw.rectangle([(inset, inset), (w - inset - 1, h - inset - 1)],
                           outline=palette.accent, width=width)
        bracket = 36
        for cx, cy, dx, dy in [(46, 46, 1, 1), (w - 46, 46, -1, 1),
                               (46, h - 46, 1, -1), (w - 46, h - 46, -1, -1)]:
            draw.line([(cx, cy), (cx + bracket * dx, cy)], fill=palette.accent, width=2)
            draw.line([(cx, cy), (cx, cy + bracket * dy)], fill=palette.accent, width=2)
    elif kind == "off_register":
        draw.rectangle([(24, 24), (w - 25, h - 25)], outline=palette.accent, width=2)
        draw.rectangle([(28, 28), (w - 29, h - 29)], outline=palette.ink, width=1)
    # "none" → no border drawn.


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
