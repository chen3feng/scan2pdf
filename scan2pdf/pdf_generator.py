"""
PDF generator - Create text PDF pages using ReportLab.

Generates clean, well-formatted PDF pages from OCR text,
with proper typography, margins, and page layout.
Supports font-size-aware rendering when structured paragraph data is provided.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

log = logging.getLogger(__name__)

# Module-level font names (can be overridden by configure_fonts)
_FONT_REGULAR = "Times-Roman"
_FONT_BOLD = "Times-Bold"


def configure_fonts(regular: str, bold: str) -> None:
    """Override the default fonts used for PDF generation."""
    global _FONT_REGULAR, _FONT_BOLD
    _FONT_REGULAR = regular
    _FONT_BOLD = bold
    log.info("PDF fonts configured: regular=%s, bold=%s", regular, bold)


@dataclass
class StyledParagraph:
    """A paragraph with associated font size from OCR analysis."""

    text: str
    font_size_pt: float = 0.0  # 0 means use default
    is_bold: bool = False
    is_centered: bool = False
    color: tuple[int, int, int] | None = None  # RGB text color (None = default black)


# Page dimensions
PAGE_WIDTH, PAGE_HEIGHT = letter  # 612 x 792 points
MARGIN_TOP = 0.8 * inch
MARGIN_BOTTOM = 0.8 * inch
MARGIN_LEFT = 0.9 * inch
MARGIN_RIGHT = 0.9 * inch


# Default body font size
DEFAULT_BODY_SIZE = 11.0
# Threshold: if a paragraph's font size exceeds body size by this ratio,
# treat it as a heading
HEADING_SIZE_RATIO = 1.3


def _create_styles(extra_spacing: float = 0.0, body_font_size: float = 0.0, text_color: str | None = None) -> dict:
    """
    Create paragraph styles for the book layout.

    Args:
        extra_spacing: Additional spaceAfter to add to each paragraph
                       for distributing text evenly across the page.
        body_font_size: Override body font size (0 = use default 11pt).
    """
    styles = getSampleStyleSheet()

    fs = body_font_size if body_font_size > 0 else DEFAULT_BODY_SIZE
    leading = fs * 1.35

    body_style = ParagraphStyle(
        "BookBody",
        parent=styles["Normal"],
        fontName=_FONT_REGULAR,
        fontSize=fs,
        leading=leading,
        alignment=TA_JUSTIFY,
        firstLineIndent=0,
        spaceBefore=0,
        spaceAfter=4 + extra_spacing,
    )

    # First paragraph after a chapter heading (no indent)
    body_first = ParagraphStyle(
        "BookBodyFirst",
        parent=body_style,
        firstLineIndent=0,
    )

    chapter_style = ParagraphStyle(
        "ChapterTitle",
        parent=styles["Heading1"],
        fontName=_FONT_BOLD,
        fontSize=18,
        leading=24,
        alignment=TA_CENTER,
        spaceBefore=36 + extra_spacing,
        spaceAfter=24 + extra_spacing,
        textColor=text_color or "#333333",
    )

    section_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading2"],
        fontName=_FONT_BOLD,
        fontSize=14,
        leading=18,
        alignment=TA_LEFT,
        spaceBefore=18 + extra_spacing,
        spaceAfter=12 + extra_spacing,
    )

    return {
        "body": body_style,
        "body_first": body_first,
        "chapter": chapter_style,
        "section": section_style,
    }


def _make_style_for_size(
    font_size_pt: float,
    is_bold: bool = False,
    is_centered: bool = False,
    extra_spacing: float = 0.0,
    base_styles: dict | None = None,
    text_color: str | None = None,
) -> ParagraphStyle:
    """
    Create a ParagraphStyle matching the given font size.

    Uses the base body style as a template and adjusts fontSize, leading,
    fontName, and alignment based on the detected properties.
    """
    if base_styles is None:
        base_styles = _create_styles(extra_spacing)

    base = base_styles["body"]
    leading = font_size_pt * 1.35  # Comfortable line spacing

    font_name = _FONT_BOLD if is_bold else _FONT_REGULAR
    alignment = TA_CENTER if is_centered else TA_JUSTIFY
    first_indent = 0

    # Larger text gets more space around it
    size_ratio = font_size_pt / DEFAULT_BODY_SIZE
    space_before = max(0, (size_ratio - 1) * 12) if size_ratio > 1.1 else 0
    space_after = 4 * size_ratio + extra_spacing

    style_kwargs = {
        "parent": base,
        "fontName": font_name,
        "fontSize": font_size_pt,
        "leading": leading,
        "alignment": alignment,
        "firstLineIndent": first_indent,
        "spaceBefore": space_before,
        "spaceAfter": space_after,
    }
    if text_color:
        style_kwargs["textColor"] = text_color

    return ParagraphStyle(
        f"Dynamic_{font_size_pt:.0f}pt",
        **style_kwargs,
    )


def _escape_xml(text: str) -> str:
    """Escape text for ReportLab XML paragraphs."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def _fit_heading_font_size(
    text: str,
    desired_fs: float,
    font_name: str,
    avail_width: float,
    min_fs: float = 9.0,
) -> float:
    """
    Shrink heading font size so the text fits on a single line.

    Returns the largest font size <= desired_fs that keeps the text
    within avail_width.  Never goes below min_fs.
    """
    from reportlab.lib.utils import simpleSplit

    log.debug(
        "_fit_heading_font_size: desired=%.1f font=%s width=%.1f text='%s'",
        desired_fs,
        font_name,
        avail_width,
        text[:60],
    )
    fs = desired_fs
    while fs >= min_fs:
        parts = simpleSplit(text, font_name, fs, avail_width)
        if len(parts) <= 1:
            if fs < desired_fs:
                log.debug(
                    "Heading font shrunk %.1f -> %.1f to fit: '%s'",
                    desired_fs,
                    fs,
                    text[:60],
                )
            return fs
        fs -= 0.5
    log.debug(
        "Heading font at minimum %.1f for: '%s'",
        min_fs,
        text[:60],
    )
    return min_fs


def _detect_chapter(text: str) -> bool:
    """Check if text looks like a chapter heading."""
    text_stripped = text.strip()
    # Match patterns like "CHAPTER 1", "Chapter One", "CHAPTER I", "I", "II", etc.
    if re.match(r"^(CHAPTER|Chapter)\s+", text_stripped):
        return True
    # Roman numeral only lines (for chapter dividers)
    return bool(re.match(r"^[IVXLC]+\.?$", text_stripped))


def _build_story(text: str, styles: dict) -> list:
    """Build a list of flowables from plain text using the given styles."""
    story = []
    paragraphs = text.split("\n\n")
    after_chapter = False

    for para_text in paragraphs:
        para_text = para_text.strip()
        if not para_text:
            continue

        escaped = _escape_xml(para_text)

        if _detect_chapter(para_text):
            story.append(Paragraph(escaped, styles["chapter"]))
            after_chapter = True
        elif after_chapter:
            story.append(Paragraph(escaped, styles["body_first"]))
            after_chapter = False
        else:
            story.append(Paragraph(escaped, styles["body"]))

    return story


def _build_story_styled(
    styled_paragraphs: list[StyledParagraph],
    extra_spacing: float = 0.0,
    body_font_override: float = 0.0,
    avail_width: float = 0.0,
) -> list:
    """
    Build a list of flowables from StyledParagraph objects.

    Uses the font_size_pt from each paragraph to determine relative sizes
    (headings vs body), then renders body text at the given size and
    scales headings proportionally.

    Args:
        styled_paragraphs: Paragraphs with detected font sizes.
        extra_spacing: Extra spaceAfter per paragraph for vertical fill.
        body_font_override: Render body text at this size (0 = DEFAULT).
    """
    story = []
    after_chapter = False

    # Determine the dominant (body) font size from the paragraphs
    sizes = [sp.font_size_pt for sp in styled_paragraphs if sp.font_size_pt > 0]
    if sizes:
        sizes.sort()
        detected_body = sizes[len(sizes) // 2]  # Median = most common body size
    else:
        detected_body = DEFAULT_BODY_SIZE

    # Use the override (or default) for rendering; scale headings proportionally
    render_body = body_font_override if body_font_override > 0 else DEFAULT_BODY_SIZE
    base_styles = _create_styles(extra_spacing, body_font_size=render_body)
    _avail_w = avail_width if avail_width > 0 else (PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT)
    # SimpleDocTemplate's Frame has default padding of 6pt on each side
    _avail_w -= 12

    for sp in styled_paragraphs:
        text = sp.text.strip()
        if not text:
            continue

        escaped = _escape_xml(text)
        fs = sp.font_size_pt

        # Convert paragraph color to hex string for ReportLab
        _color_hex = None
        if sp.color is not None and sp.color != (0, 0, 0):
            from .color_detector import rgb_to_hex

            _color_hex = rgb_to_hex(sp.color)

        # Detect chapter headings by text pattern OR by large font size
        is_chapter = _detect_chapter(text)
        is_large = fs > detected_body * HEADING_SIZE_RATIO if fs > 0 else False

        if is_chapter or (is_large and sp.is_centered):
            # Scale heading font size proportionally to the body size
            scaled_fs = render_body * (fs / detected_body) if fs > 0 and detected_body > 0 else render_body * 1.6
            scaled_fs = _fit_heading_font_size(text, scaled_fs, _FONT_BOLD, _avail_w)
            style = _make_style_for_size(
                scaled_fs,
                is_bold=True,
                is_centered=True,
                extra_spacing=extra_spacing,
                base_styles=base_styles,
                text_color=_color_hex,
            )
            story.append(Paragraph(escaped, style))
            after_chapter = True
        elif is_large:
            # Section heading - scale proportionally
            scaled_fs = render_body * (fs / detected_body) if fs > 0 and detected_body > 0 else render_body * 1.3
            font_name = _FONT_BOLD
            scaled_fs = _fit_heading_font_size(text, scaled_fs, font_name, _avail_w)
            style = _make_style_for_size(
                scaled_fs,
                is_bold=True,
                is_centered=sp.is_centered,
                extra_spacing=extra_spacing,
                base_styles=base_styles,
                text_color=_color_hex,
            )
            story.append(Paragraph(escaped, style))
            after_chapter = True
        elif after_chapter:
            if _color_hex:
                style = _make_style_for_size(
                    render_body,
                    extra_spacing=extra_spacing,
                    base_styles=base_styles,
                    text_color=_color_hex,
                )
                style.firstLineIndent = 0
                story.append(Paragraph(escaped, style))
            else:
                story.append(Paragraph(escaped, base_styles["body_first"]))
            after_chapter = False
        else:
            # Normal body paragraph - use default body style or colored style
            if _color_hex:
                style = _make_style_for_size(
                    render_body,
                    extra_spacing=extra_spacing,
                    base_styles=base_styles,
                    text_color=_color_hex,
                )
                story.append(Paragraph(escaped, style))
            else:
                story.append(Paragraph(escaped, base_styles["body"]))

    return story


def _calc_story_height(story: list, avail_width: float) -> float:
    """Calculate the total height of flowables given available width."""
    total = 0.0
    for flowable in story:
        w, h = flowable.wrap(avail_width, 99999)
        total += h
    return total


# Minimum font size to prevent text from becoming unreadable
_MIN_FONT_SIZE = 6.0
# Font size shrink step when content overflows a single page
_SHRINK_STEP = 0.5


def _build_story_for_page(
    text: str,
    styled_paragraphs: list[StyledParagraph] | None,
    avail_width: float,
    avail_height: float,
    body_font_size: float = 0.0,
) -> list:
    """
    Build a story that is guaranteed to fit within one page.

    If the content overflows at the default font size, progressively
    shrink the body font until it fits.  Then distribute any remaining
    vertical space as extra paragraph spacing (capped at 15 pt).

    Args:
        text: Plain-text fallback.
        styled_paragraphs: Optional structured paragraphs with font sizes.
        avail_width: Usable page width in points.
        avail_height: Usable page height in points.
        body_font_size: Override body font size (0 = use DEFAULT_BODY_SIZE).

    Returns:
        A list of ReportLab flowables that fit in one page.
    """
    use_styled = styled_paragraphs is not None and len(styled_paragraphs) > 0
    fs = body_font_size if body_font_size > 0 else DEFAULT_BODY_SIZE

    # --- Phase 1: shrink font until content fits one page ---------------
    while fs >= _MIN_FONT_SIZE:
        if use_styled:
            story = _build_story_styled(styled_paragraphs, body_font_override=fs, avail_width=avail_width)
        else:
            styles = _create_styles(body_font_size=fs)
            story = _build_story(text, styles)

        if not story:
            return story

        content_height = _calc_story_height(story, avail_width)
        if content_height <= avail_height:
            break  # Fits!
        fs -= _SHRINK_STEP
        log.debug(f"Content overflows ({content_height:.0f} > {avail_height:.0f}), shrinking body font to {fs:.1f}pt")
    else:
        # Even at minimum size it overflows – use minimum and accept overflow
        log.warning(f"Content still overflows at {_MIN_FONT_SIZE}pt; page may not fit perfectly.")

    if fs < DEFAULT_BODY_SIZE:
        log.info(f"Body font shrunk to {fs:.1f}pt to fit page")

    # --- Phase 2: distribute leftover space as paragraph spacing --------
    content_height = _calc_story_height(story, avail_width)
    para_count = len(story)

    if 0 < content_height < avail_height * 0.95 and para_count > 1:
        extra_space = avail_height - content_height
        extra_per_para = min(extra_space / para_count, 15.0)

        if use_styled:
            story = _build_story_styled(
                styled_paragraphs,
                extra_spacing=extra_per_para,
                body_font_override=fs,
                avail_width=avail_width,
            )
        else:
            adjusted_styles = _create_styles(
                extra_spacing=extra_per_para,
                body_font_size=fs,
            )
            story = _build_story(text, adjusted_styles)

    return story


def text_to_pdf_page(
    text: str,
    output_path: Path,
    styled_paragraphs: list[StyledParagraph] | None = None,
) -> Path:
    """
    Convert cleaned text into a **single-page** PDF.

    Guarantees that one scanned page produces exactly one output page by
    shrinking the font when content overflows, and distributing extra
    vertical space when content is shorter than the page.

    Args:
        text: Cleaned text content for this page (used as fallback).
        output_path: Where to save the generated PDF.
        styled_paragraphs: Optional list of StyledParagraph with font sizes.

    Returns:
        Path to the generated PDF.
    """
    avail_width = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
    avail_height = PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM

    story = _build_story_for_page(
        text,
        styled_paragraphs,
        avail_width,
        avail_height,
    )

    if not story:
        # Empty page – produce a blank page
        story = [Spacer(1, avail_height)]

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        leftMargin=MARGIN_LEFT,
        rightMargin=MARGIN_RIGHT,
    )
    doc.build(story)
    return output_path


def texts_to_pdf(page_texts: list[str], output_path: Path) -> Path:
    """
    Convert multiple pages of text into a single PDF.

    Each string in page_texts represents one original page's content.
    Page breaks are inserted between them.

    Args:
        page_texts: List of text content, one per original page.
        output_path: Where to save the generated PDF.

    Returns:
        Path to the generated PDF.
    """
    avail_width = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
    avail_height = PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        leftMargin=MARGIN_LEFT,
        rightMargin=MARGIN_RIGHT,
    )

    story = []

    for page_idx, text in enumerate(page_texts):
        if page_idx > 0:
            story.append(PageBreak())

        page_story = _build_story_for_page(
            text,
            None,
            avail_width,
            avail_height,
        )

        if not page_story:
            # Blank page
            story.append(Spacer(1, 1))
            continue

        story.extend(page_story)

    if not story:
        story.append(Spacer(1, 1))

    doc.build(story)
    return output_path
