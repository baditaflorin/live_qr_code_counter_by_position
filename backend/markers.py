"""Generate ArUco marker images and printable PDFs."""
import io
import math
from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .detection import get_dictionary

MARKER_PIXEL_SIZE = 600  # high-res so prints stay crisp


def render_marker_png(aruco_id: int, size: int = MARKER_PIXEL_SIZE) -> bytes:
    img = cv2.aruco.generateImageMarker(get_dictionary(), aruco_id, size)
    # Add quiet-zone border (white) — this is required for reliable detection.
    pad = max(size // 12, 20)
    bordered = cv2.copyMakeBorder(
        img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255
    )
    ok, buf = cv2.imencode(".png", bordered)
    if not ok:
        raise RuntimeError("Failed to encode marker PNG")
    return buf.tobytes()


def _load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _marker_tile(
    aruco_id: int,
    label: str,
    tile_w: int,
    tile_h: int,
    marker_px: int,
) -> Image.Image:
    """One printable marker with caption underneath."""
    tile = Image.new("RGB", (tile_w, tile_h), "white")

    raw = cv2.aruco.generateImageMarker(get_dictionary(), aruco_id, marker_px)
    pad = max(marker_px // 10, 10)
    framed = cv2.copyMakeBorder(raw, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
    pil_marker = Image.fromarray(framed).convert("RGB")

    # Center marker horizontally, top-aligned.
    mx = (tile_w - pil_marker.width) // 2
    tile.paste(pil_marker, (mx, 10))

    draw = ImageDraw.Draw(tile)
    # Bold ID + smaller name.
    big = _load_font(38)
    small = _load_font(24)

    id_text = f"#{aruco_id}"
    bbox = draw.textbbox((0, 0), id_text, font=big)
    tw = bbox[2] - bbox[0]
    draw.text(((tile_w - tw) // 2, pil_marker.height + 18), id_text, fill="black", font=big)

    if label:
        # truncate long names
        line = label if len(label) < 28 else label[:27] + "…"
        bbox = draw.textbbox((0, 0), line, font=small)
        tw = bbox[2] - bbox[0]
        draw.text(
            ((tile_w - tw) // 2, pil_marker.height + 60),
            line,
            fill="#333333",
            font=small,
        )

    # crop marks
    draw.rectangle([(2, 2), (tile_w - 3, tile_h - 3)], outline="#cccccc", width=1)
    return tile


def render_pdf(markers: list[dict], cols: int = 3, rows: int = 3) -> bytes:
    """
    `markers` = list of {"aruco_id": int, "label": str}.
    Output: multi-page PDF (A4-ish at 200 DPI) with markers laid out in a grid.
    """
    # A4 at 200 DPI: 1654 x 2339
    page_w, page_h = 1654, 2339
    margin = 80
    grid_w = page_w - 2 * margin
    grid_h = page_h - 2 * margin
    tile_w = grid_w // cols
    tile_h = grid_h // rows
    marker_px = min(tile_w, tile_h) - 120  # leave room for caption

    pages: list[Image.Image] = []
    if not markers:
        page = Image.new("RGB", (page_w, page_h), "white")
        pages.append(page)
    else:
        per_page = cols * rows
        for start in range(0, len(markers), per_page):
            page = Image.new("RGB", (page_w, page_h), "white")
            chunk = markers[start : start + per_page]
            for i, m in enumerate(chunk):
                r = i // cols
                c = i % cols
                tile = _marker_tile(
                    aruco_id=m["aruco_id"],
                    label=m.get("label", ""),
                    tile_w=tile_w,
                    tile_h=tile_h,
                    marker_px=marker_px,
                )
                px = margin + c * tile_w
                py = margin + r * tile_h
                page.paste(tile, (px, py))
            pages.append(page)

    buf = io.BytesIO()
    pages[0].save(
        buf,
        format="PDF",
        save_all=True,
        append_images=pages[1:],
        resolution=200.0,
    )
    return buf.getvalue()
