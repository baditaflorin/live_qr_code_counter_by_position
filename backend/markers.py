"""Generate AprilTag marker images and printable PDFs using official precomputed markers."""
import io
import os
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

MARKER_PIXEL_SIZE = 600  # high-res so prints stay crisp

# Path to precomputed official AprilTag images
_APRILTAGS_DIR = Path(__file__).parent / "apriltags" / "tag36h11"


def _load_official_apriltag(tag_id: int) -> Image.Image:
    """Load the official AprilTag image from the precomputed library.

    Falls back to a simple placeholder if the image is not available.
    """
    filename = f"tag36_11_{tag_id:05d}.png"
    filepath = _APRILTAGS_DIR / filename

    if filepath.exists():
        try:
            img = Image.open(filepath)
            return img.convert("L")  # Convert to grayscale
        except Exception:
            pass

    # Fallback: create a simple placeholder if image not found
    # This is just for development; in production all 587 images should be present
    img = Image.new("L", (200, 200), color=255)
    pixels = img.load()
    # Draw a simple pattern based on tag ID
    for i in range(200):
        for j in range(200):
            if (i + j + tag_id) % 20 < 10:
                pixels[i, j] = 0
    return img


def render_marker_png(tag_id: int, size: int = MARKER_PIXEL_SIZE) -> bytes:
    """Generate AprilTag image as PNG with quiet zone.

    Uses official precomputed AprilTag images from the AprilRobotics repository.
    """
    # Load the official AprilTag image
    raw_img = _load_official_apriltag(tag_id)

    # Resize to requested size
    if raw_img.size[0] != size:
        raw_img = raw_img.resize((size, size), Image.Resampling.NEAREST)

    # Add quiet-zone border (white) — required for reliable detection
    pad = max(size // 12, 20)
    bordered = Image.new("L", (size + 2 * pad, size + 2 * pad), color=255)
    bordered.paste(raw_img, (pad, pad))

    # Convert to PNG bytes
    buf = io.BytesIO()
    bordered.save(buf, format="PNG")
    return buf.getvalue()


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
    tag_id: int,
    label: str,
    tile_w: int,
    tile_h: int,
    marker_px: int,
) -> Image.Image:
    """One printable marker with caption underneath."""
    tile = Image.new("RGB", (tile_w, tile_h), "white")

    # Load the official AprilTag
    raw_img = _load_official_apriltag(tag_id)
    if raw_img.size[0] != marker_px:
        raw_img = raw_img.resize((marker_px, marker_px), Image.Resampling.NEAREST)

    pad = max(marker_px // 10, 10)
    framed = Image.new("L", (marker_px + 2 * pad, marker_px + 2 * pad), color=255)
    framed.paste(raw_img, (pad, pad))

    pil_marker = framed.convert("RGB")

    # Center marker horizontally, top-aligned.
    mx = (tile_w - pil_marker.width) // 2
    tile.paste(pil_marker, (mx, 10))

    draw = ImageDraw.Draw(tile)
    # Bold ID + smaller name.
    big = _load_font(38)
    small = _load_font(24)

    id_text = f"#{tag_id}"
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
                # Support both aruco_id (old) and tag_id (new) keys
                tag_id = m.get("tag_id") or m.get("aruco_id", 0)
                tile = _marker_tile(
                    tag_id=tag_id,
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
