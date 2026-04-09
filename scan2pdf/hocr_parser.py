"""
hOCR parser - Extract structured text from Tesseract hOCR files.

Parses hOCR HTML to extract text blocks with positional information,
filtering out headers, footers, and noise.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree


@dataclass
class Word:
    """A single recognized word with bounding box and confidence."""

    text: str
    bbox: tuple[int, int, int, int]  # x0, y0, x1, y1
    confidence: int = 0


@dataclass
class Line:
    """A line of text composed of words."""

    words: list[Word] = field(default_factory=list)
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    font_size_pt: float = 0.0  # Estimated font size in points

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def height_px(self) -> int:
        return self.bbox[3] - self.bbox[1]


@dataclass
class Paragraph:
    """A paragraph composed of lines."""

    lines: list[Line] = field(default_factory=list)
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)

    @property
    def text(self) -> str:
        return "\n".join(ln.text for ln in self.lines)

    @property
    def estimated_font_size(self) -> float:
        """Median font size of all lines in this paragraph (in points)."""
        sizes = [ln.font_size_pt for ln in self.lines if ln.font_size_pt > 0]
        if not sizes:
            return 0.0
        sizes.sort()
        mid = len(sizes) // 2
        return sizes[mid] if len(sizes) % 2 else (sizes[mid - 1] + sizes[mid]) / 2


@dataclass
class ContentArea:
    """A content area (block) on the page."""

    paragraphs: list[Paragraph] = field(default_factory=list)
    bbox: tuple[int, int, int, int] = (0, 0, 0, 0)
    is_photo: bool = False

    @property
    def text(self) -> str:
        return "\n\n".join(p.text for p in self.paragraphs)


@dataclass
class Page:
    """A parsed hOCR page."""

    page_num: int
    width: int
    height: int
    dpi: int
    areas: list[ContentArea] = field(default_factory=list)
    has_photo: bool = False

    @property
    def text_areas(self) -> list[ContentArea]:
        return [a for a in self.areas if not a.is_photo]


def _parse_bbox(title: str) -> tuple[int, int, int, int]:
    """Extract bbox from hOCR title attribute."""
    m = re.search(r"bbox\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", title or "")
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
    return (0, 0, 0, 0)


def _parse_confidence(title: str) -> int:
    """Extract word confidence from hOCR title attribute."""
    m = re.search(r"x_wconf\s+(\d+)", title or "")
    return int(m.group(1)) if m else 0


def _parse_scan_res(title: str) -> int:
    """Extract scan resolution from hOCR page title."""
    m = re.search(r"scan_res\s+(\d+)", title or "")
    return int(m.group(1)) if m else 300


def parse_hocr(hocr_path: Path) -> Page:
    """Parse an hOCR file and return a structured Page object."""
    tree = etree.parse(str(hocr_path))
    root = tree.getroot()
    ns = {"x": "http://www.w3.org/1999/xhtml"}

    # Find the page div
    page_div = root.xpath("//x:div[@class='ocr_page']", namespaces=ns)
    if not page_div:
        # Try without namespace
        page_div = root.xpath("//*[@class='ocr_page']")
    if not page_div:
        raise ValueError(f"No ocr_page found in {hocr_path}")

    page_div = page_div[0]
    page_title = page_div.get("title", "")
    page_bbox = _parse_bbox(page_title)
    page_dpi = _parse_scan_res(page_title)

    # Extract page number from filename
    page_num = int(re.search(r"(\d+)", hocr_path.stem).group(1))

    page = Page(
        page_num=page_num,
        width=page_bbox[2],
        height=page_bbox[3],
        dpi=page_dpi,
        areas=[],
        has_photo=False,
    )

    # Process each content area
    for area_div in page_div:
        area_class = area_div.get("class", "")
        area_title = area_div.get("title", "")
        area_bbox = _parse_bbox(area_title)

        if "ocr_photo" in area_class:
            page.has_photo = True
            page.areas.append(
                ContentArea(
                    bbox=area_bbox,
                    is_photo=True,
                )
            )
            continue

        if "ocr_carea" not in area_class:
            continue

        area = ContentArea(bbox=area_bbox)

        # Process paragraphs
        for par_elem in area_div.iter():
            if par_elem.get("class") != "ocr_par":
                continue

            par_bbox = _parse_bbox(par_elem.get("title", ""))
            paragraph = Paragraph(bbox=par_bbox)

            for line_elem in par_elem:
                if line_elem.get("class") != "ocr_line":
                    continue

                line_bbox = _parse_bbox(line_elem.get("title", ""))
                line_height_px = line_bbox[3] - line_bbox[1]
                line_font_pt = line_height_px / page_dpi * 72 * 0.70 if line_height_px > 0 else 0.0
                line = Line(bbox=line_bbox, font_size_pt=round(line_font_pt, 1))

                for word_elem in line_elem:
                    if word_elem.get("class") != "ocrx_word":
                        continue
                    word_title = word_elem.get("title", "")
                    word_text = (word_elem.text or "").strip()
                    if word_text:
                        line.words.append(
                            Word(
                                text=word_text,
                                bbox=_parse_bbox(word_title),
                                confidence=_parse_confidence(word_title),
                            )
                        )

                if line.words:
                    paragraph.lines.append(line)

            if paragraph.lines:
                area.paragraphs.append(paragraph)

        if area.paragraphs:
            page.areas.append(area)

    return page


def filter_header_footer(page: Page, margin_ratio: float = 0.05) -> list[ContentArea]:
    """
    Filter out header and footer areas from a page.

    Removes content areas that are in the top or bottom margin of the page.
    Also removes areas that look like page numbers or URLs.
    """
    if not page.areas:
        return []

    top_margin = int(page.height * margin_ratio)
    bottom_margin = int(page.height * (1 - margin_ratio))

    filtered = []
    for area in page.areas:
        if area.is_photo:
            filtered.append(area)
            continue

        # Skip areas entirely in header zone
        if area.bbox[3] <= top_margin:
            continue

        # Skip areas entirely in footer zone
        if area.bbox[1] >= bottom_margin:
            continue

        # Check if content looks like header/footer noise
        text = area.text.strip()
        if _is_header_footer_text(text):
            continue

        filtered.append(area)

    return filtered


def _is_header_footer_text(text: str) -> bool:
    """Check if text looks like header/footer content to be removed."""
    text_lower = text.lower().strip()

    # URL patterns
    if re.match(r"https?://", text_lower):
        return True

    # Page number patterns like "5/381" or just a number
    if re.match(r"^\d+/\d+$", text_lower):
        return True
    if re.match(r"^\d+$", text_lower) and len(text_lower) <= 4:
        return True

    # Date + time patterns like "5/29/25, 10:23 AM"
    if re.match(r"\d+/\d+/\d+,?\s+\d+:\d+\s*(am|pm)", text_lower):
        return True

    # Combined header line: "5/29/25, 10:23 AM | Capture the Castle..."
    if re.search(r"\d+/\d+/\d+.*\|.*capture.*castle", text_lower):
        return True

    # Just the title reference "| Capture the Castle (PDFDrive )"
    if re.match(r"\|?\s*capture\s+the\s+castle", text_lower):
        return True

    # URL + page number on same line
    return bool(re.search(r"https?://.*\d+/\d+$", text_lower))
