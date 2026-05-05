"""Generate AprilTag marker images and printable PDFs."""
import io
import struct
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
from pupil_apriltags import Detector

MARKER_PIXEL_SIZE = 600  # high-res so prints stay crisp
_detector_for_tags = Detector(families="tag36h11", nthreads=1, quad_decimate=2.0)


def _render_apriltag_bitmap(tag_id: int) -> Image.Image:
    """Render AprilTag bitmap for tag36h11 family as PIL Image (black & white).

    tag36h11 is an 8x8 grid with:
    - Outer 1-bit border (always white/1)
    - Inner 6x6 payload area with tag data
    """
    tag_size = 8
    tag_grid = [[1] * tag_size for _ in range(tag_size)]  # Start with white border

    # Fill in the 6x6 payload area in the center with bits from the tag ID
    # We distribute the tag ID bits across the 6x6 center area
    payload_size = 6
    for i in range(payload_size):
        for j in range(payload_size):
            bit_index = i * payload_size + j
            # Extract the bit at this position from the tag ID
            bit = (tag_id >> bit_index) & 1
            tag_grid[i + 1][j + 1] = bit

    # Create PIL image with proper scaling
    pixels_per_bit = MARKER_PIXEL_SIZE // tag_size
    img_size = pixels_per_bit * tag_size
    img = Image.new("L", (img_size, img_size), color=255)
    pixels = img.load()

    for i in range(tag_size):
        for j in range(tag_size):
            color = 0 if tag_grid[i][j] == 0 else 255  # 0=black, 1=white
            for di in range(pixels_per_bit):
                for dj in range(pixels_per_bit):
                    x = j * pixels_per_bit + dj
                    y = i * pixels_per_bit + di
                    pixels[x, y] = color

    return img


def render_marker_png(tag_id: int, size: int = MARKER_PIXEL_SIZE) -> bytes:
    """Generate AprilTag image as PNG with quiet zone."""
    # Render the tag bitmap
    raw_img = _render_apriltag_bitmap(tag_id)

    # Resize to requested size if needed
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

    # Render the AprilTag
    raw_img = _render_apriltag_bitmap(tag_id)
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
