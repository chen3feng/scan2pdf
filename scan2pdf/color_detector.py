"""
Color detector - Detect text foreground color from scanned page images.

Samples pixel colors within OCR word bounding boxes to determine whether
text is truly colored or just black with scan noise/artifacts.
Uses HSV color space to robustly distinguish genuine color from
near-black/near-gray tones caused by scanner imperfections.
"""

import logging
from collections import Counter
from pathlib import Path

from PIL import Image

log = logging.getLogger(__name__)

# --- Thresholds for distinguishing "true color" from scan noise -----------

# Minimum saturation (0-255) in HSV to consider a pixel as "colored".
# Scan artifacts on black text typically have S < 30.
MIN_SATURATION = 40

# Maximum luminance for a pixel to be considered "dark text" foreground.
# Pixels brighter than this are likely background — unless they are
# highly saturated (colored text can be bright).
MAX_TEXT_LUMINANCE = 180

# Minimum saturation (0-255) for a bright pixel to still count as foreground.
# Bright but highly saturated pixels (e.g. vivid red/blue/green text) are
# not background even though their luminance is high.
# Must be <= MIN_SATURATION so that any pixel considered "colored" by
# _is_colored_pixel is also considered foreground by _is_foreground_pixel.
MIN_BRIGHT_FG_SATURATION = 40

# Maximum luminance for bright-but-saturated pixels to be foreground.
# Even saturated pixels that are nearly white (e.g. very pale yellow) are
# background, not text.
MAX_BRIGHT_FG_LUMINANCE = 220

# Minimum value (brightness) for a colored pixel to be considered visible.
# Very dark pixels (V < 30) are essentially black regardless of hue.
MIN_COLOR_VALUE = 30

# Fraction of sampled foreground pixels that must be colored to classify
# the word as colored.  Lowered from 0.40 because text strokes are thin
# and anti-aliased edges produce gray (non-colored) foreground pixels.
COLOR_PIXEL_RATIO = 0.25

# When aggregating paragraph color, minimum fraction of *valid* (non-None)
# words that must share the same non-black color to assign it to the paragraph.
# Lowered to 0.20 because short words (e.g. "TO", "A") in large-font titles
# may return None (too few foreground pixels), reducing the effective count.
PARAGRAPH_COLOR_RATIO = 0.20

# Hue quantization bucket size (0-179 in OpenCV convention, but we use
# Pillow's 0-255 range). We bucket hues to group similar colors.
HUE_BUCKET_SIZE = 15

# Standard "black" sentinel — used when text is not colored.
BLACK = (0, 0, 0)


def _rgb_to_hsv(r: int, g: int, b: int) -> tuple[int, int, int]:
    """
    Convert RGB (0-255 each) to HSV (H: 0-360, S: 0-255, V: 0-255).

    Pure Python implementation to avoid numpy/OpenCV dependency.
    """
    r_f, g_f, b_f = r / 255.0, g / 255.0, b / 255.0
    mx = max(r_f, g_f, b_f)
    mn = min(r_f, g_f, b_f)
    diff = mx - mn

    # Hue
    if diff == 0:
        h = 0
    elif mx == r_f:
        h = (60 * ((g_f - b_f) / diff) + 360) % 360
    elif mx == g_f:
        h = (60 * ((b_f - r_f) / diff) + 120) % 360
    else:
        h = (60 * ((r_f - g_f) / diff) + 240) % 360

    # Saturation
    s = 0 if mx == 0 else (diff / mx) * 255

    # Value
    v = mx * 255

    return (int(h), int(s), int(v))


def _is_foreground_pixel(r: int, g: int, b: int) -> bool:
    """Check if a pixel is text foreground (not background).

    A pixel is foreground if:
    - It is dark (luminance < MAX_TEXT_LUMINANCE), OR
    - It is bright but highly saturated (colored text like red/blue/green
      can have luminance above the dark threshold but is clearly not
      white background).
    """
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    if luminance < MAX_TEXT_LUMINANCE:
        return True
    # Bright pixel — check if it's saturated enough to be colored text
    if luminance < MAX_BRIGHT_FG_LUMINANCE:
        _, s, _ = _rgb_to_hsv(r, g, b)
        if s >= MIN_BRIGHT_FG_SATURATION:
            return True
    return False


def _is_colored_pixel(h: int, s: int, v: int) -> bool:
    """
    Determine if an HSV pixel represents a genuine color (not black/gray).

    Returns False for:
    - Very dark pixels (V < MIN_COLOR_VALUE) — essentially black
    - Low saturation pixels (S < MIN_SATURATION) — gray/near-black
    """
    return s >= MIN_SATURATION and v >= MIN_COLOR_VALUE


def _quantize_hue(h: int) -> int:
    """Quantize hue to a bucket for grouping similar colors."""
    return (h // HUE_BUCKET_SIZE) * HUE_BUCKET_SIZE


def detect_word_color(
    img: Image.Image,
    bbox: tuple[int, int, int, int],
    sample_step: int = 2,
) -> tuple[int, int, int] | None:
    """
    Detect the foreground text color for a word given its bounding box.

    Samples pixels within the bbox, identifies foreground (dark) pixels,
    and determines if they are genuinely colored or just black with noise.

    Args:
        img: The page image (RGB mode).
        bbox: Word bounding box (x0, y0, x1, y1) in pixels.
        sample_step: Step size for pixel sampling (higher = faster but less accurate).

    Returns:
        RGB tuple if the word is colored, BLACK if it's black text,
        or None if no foreground pixels were found.
    """
    x0, y0, x1, y1 = bbox

    # Clamp to image bounds
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(img.width, x1)
    y1 = min(img.height, y1)

    if x1 <= x0 or y1 <= y0:
        return None

    # Shrink bbox slightly to avoid edge artifacts (borders, underlines)
    # Use a smaller margin to avoid losing too many pixels on small words
    box_h = y1 - y0
    h_margin = max(1, box_h // 8) if box_h > 10 else 0
    y0_inner = y0 + h_margin
    y1_inner = y1 - h_margin
    if y1_inner <= y0_inner:
        y0_inner, y1_inner = y0, y1

    # Collect foreground pixel data in a single pass.
    # Use getpixel for correctness; for large bboxes switch to crop+getdata
    # to avoid per-pixel Python overhead.
    fg_pixels: list[tuple[int, int, int, int, int, int]] = []  # (R, G, B, H, S, V)
    fg_count = 0

    box_w = x1 - x0
    inner_h = y1_inner - y0_inner
    use_crop = (box_w * inner_h) > 400  # Crop is faster for larger regions

    if use_crop:
        region = img.crop((x0, y0_inner, x1, y1_inner))
        rw, rh = region.size
        _get = getattr(region, "get_flattened_data", None) or region.getdata
        pixels = list(_get())
        for ry in range(0, rh, sample_step):
            row_offset = ry * rw
            for rx in range(0, rw, sample_step):
                px = pixels[row_offset + rx]
                r, g, b = px[0], px[1], px[2]
                if not _is_foreground_pixel(r, g, b):
                    continue
                fg_count += 1
                h, s, v = _rgb_to_hsv(r, g, b)
                fg_pixels.append((r, g, b, h, s, v))
    else:
        for y in range(y0_inner, y1_inner, sample_step):
            for x in range(x0, x1, sample_step):
                r, g, b = img.getpixel((x, y))[:3]
                if not _is_foreground_pixel(r, g, b):
                    continue
                fg_count += 1
                h, s, v = _rgb_to_hsv(r, g, b)
                fg_pixels.append((r, g, b, h, s, v))

    if fg_count == 0:
        return None

    # Separate colored vs non-colored foreground pixels
    colored_pixels = [(r, g, b, h, s, v) for r, g, b, h, s, v in fg_pixels if _is_colored_pixel(h, s, v)]

    # Check if enough foreground pixels are colored
    color_ratio = len(colored_pixels) / fg_count
    log.debug(
        "word bbox=%s fg=%d colored=%d ratio=%.2f (threshold=%.2f)",
        bbox,
        fg_count,
        len(colored_pixels),
        color_ratio,
        COLOR_PIXEL_RATIO,
    )
    if color_ratio < COLOR_PIXEL_RATIO:
        return BLACK

    # Find the dominant hue among colored pixels
    hue_buckets: Counter[int] = Counter()
    for _r, _g, _b, h, _s, _v in colored_pixels:
        hue_buckets[_quantize_hue(h)] += 1

    if not hue_buckets:
        return BLACK

    dominant_hue_bucket = hue_buckets.most_common(1)[0][0]

    # Average the RGB of colored pixels in the dominant hue bucket
    r_sum, g_sum, b_sum, count = 0, 0, 0, 0
    for r, g, b, h, _s, _v in colored_pixels:
        if _quantize_hue(h) == dominant_hue_bucket:
            r_sum += r
            g_sum += g
            b_sum += b
            count += 1

    if count == 0:
        return BLACK

    return (r_sum // count, g_sum // count, b_sum // count)


def detect_paragraph_color(
    word_colors: list[tuple[int, int, int] | None],
) -> tuple[int, int, int]:
    """
    Determine the dominant color for a paragraph from its word colors.

    If enough words share the same non-black color, use that color.
    Otherwise, return BLACK.

    Args:
        word_colors: List of detected colors for each word (may contain None).

    Returns:
        RGB tuple representing the paragraph's text color.
    """
    if not word_colors:
        return BLACK

    # Filter out None values
    valid_colors = [c for c in word_colors if c is not None]
    if not valid_colors:
        return BLACK

    # Count non-black colors by hue bucket
    non_black = [(c, _rgb_to_hsv(*c)) for c in valid_colors if c != BLACK]
    if not non_black:
        return BLACK

    # Check if enough words are colored
    color_ratio = len(non_black) / len(valid_colors)
    if color_ratio < PARAGRAPH_COLOR_RATIO:
        return BLACK

    # Group by hue bucket and find dominant
    hue_groups: dict[int, list[tuple[int, int, int]]] = {}
    for rgb, (h, _s, _v) in non_black:
        bucket = _quantize_hue(h)
        hue_groups.setdefault(bucket, []).append(rgb)

    # Find the largest hue group
    largest_group = max(hue_groups.values(), key=len)

    # Average the colors in the largest group
    r_avg = sum(c[0] for c in largest_group) // len(largest_group)
    g_avg = sum(c[1] for c in largest_group) // len(largest_group)
    b_avg = sum(c[2] for c in largest_group) // len(largest_group)

    return (r_avg, g_avg, b_avg)


def detect_colors_for_page(
    image_path: Path,
    paragraphs_with_bboxes: list[dict],
) -> list[tuple[int, int, int]]:
    """
    Detect text colors for all paragraphs on a page.

    Args:
        image_path: Path to the rendered page image (PNG).
        paragraphs_with_bboxes: List of dicts, each with:
            - 'word_bboxes': list of (x0, y0, x1, y1) tuples for each word.

    Returns:
        List of RGB tuples, one per paragraph.
    """
    img = Image.open(image_path).convert("RGB")

    # Determine sampling step based on image size (larger images → coarser sampling)
    step = max(1, min(img.width, img.height) // 1000)

    colors = []
    for pi, para_info in enumerate(paragraphs_with_bboxes):
        word_bboxes = para_info.get("word_bboxes", [])
        word_colors = []
        for bbox in word_bboxes:
            wc = detect_word_color(img, bbox, sample_step=step)
            word_colors.append(wc)

        para_color = detect_paragraph_color(word_colors)
        if para_color != BLACK:
            log.debug("para[%d] -> COLOR %s", pi, rgb_to_hex(para_color))
        else:
            # Log summary for debugging
            n_none = sum(1 for c in word_colors if c is None)
            n_black = sum(1 for c in word_colors if c == BLACK)
            n_color = sum(1 for c in word_colors if c is not None and c != BLACK)
            log.debug(
                "para[%d] -> BLACK (words: %d total, %d colored, %d black, %d none)",
                pi,
                len(word_colors),
                n_color,
                n_black,
                n_none,
            )
        colors.append(para_color)

    return colors


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    """Convert an RGB tuple to a hex color string like '#FF0000'."""
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"
