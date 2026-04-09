"""Tests for the hocr_parser module."""

from scan2pdf.hocr_parser import (
    ContentArea,
    Line,
    Page,
    Paragraph,
    Word,
    _is_header_footer_text,
    _parse_bbox,
    _parse_confidence,
    _parse_scan_res,
    filter_header_footer,
)


class TestParseBbox:
    """Tests for _parse_bbox."""

    def test_valid_bbox(self):
        assert _parse_bbox("bbox 100 200 300 400") == (100, 200, 300, 400)

    def test_bbox_in_longer_title(self):
        title = "bbox 0 0 2550 3300; image /tmp/page.png; ppageno 0"
        assert _parse_bbox(title) == (0, 0, 2550, 3300)

    def test_empty_title(self):
        assert _parse_bbox("") == (0, 0, 0, 0)

    def test_none_title(self):
        assert _parse_bbox(None) == (0, 0, 0, 0)

    def test_no_bbox(self):
        assert _parse_bbox("x_wconf 95") == (0, 0, 0, 0)


class TestParseConfidence:
    """Tests for _parse_confidence."""

    def test_valid_confidence(self):
        assert _parse_confidence("bbox 0 0 100 100; x_wconf 95") == 95

    def test_no_confidence(self):
        assert _parse_confidence("bbox 0 0 100 100") == 0

    def test_empty_string(self):
        assert _parse_confidence("") == 0


class TestParseScanRes:
    """Tests for _parse_scan_res."""

    def test_valid_scan_res(self):
        assert _parse_scan_res("scan_res 300 300") == 300

    def test_no_scan_res(self):
        assert _parse_scan_res("bbox 0 0 100 100") == 300  # default

    def test_empty_string(self):
        assert _parse_scan_res("") == 300  # default


class TestIsHeaderFooterText:
    """Tests for _is_header_footer_text."""

    def test_url(self):
        assert _is_header_footer_text("https://example.com") is True

    def test_page_number_fraction(self):
        assert _is_header_footer_text("5/381") is True

    def test_page_number_simple(self):
        assert _is_header_footer_text("42") is True

    def test_long_number_not_page(self):
        assert _is_header_footer_text("12345") is False

    def test_date_time(self):
        assert _is_header_footer_text("5/29/25, 10:23 AM") is True

    def test_normal_text(self):
        assert _is_header_footer_text("This is a normal paragraph.") is False

    def test_empty_text(self):
        assert _is_header_footer_text("") is False


class TestDataClasses:
    """Tests for data class properties."""

    def test_word(self):
        w = Word(text="hello", bbox=(0, 0, 50, 20), confidence=95)
        assert w.text == "hello"

    def test_line_text(self):
        line = Line(
            words=[Word("hello", (0, 0, 50, 20)), Word("world", (55, 0, 100, 20))],
            bbox=(0, 0, 100, 20),
        )
        assert line.text == "hello world"

    def test_line_height(self):
        line = Line(bbox=(0, 10, 100, 30))
        assert line.height_px == 20

    def test_paragraph_text(self):
        para = Paragraph(
            lines=[
                Line(words=[Word("line1", (0, 0, 50, 10))], bbox=(0, 0, 50, 10)),
                Line(words=[Word("line2", (0, 15, 50, 25))], bbox=(0, 15, 50, 25)),
            ]
        )
        assert para.text == "line1\nline2"

    def test_paragraph_estimated_font_size(self):
        para = Paragraph(
            lines=[
                Line(words=[Word("a", (0, 0, 10, 10))], bbox=(0, 0, 10, 10), font_size_pt=12.0),
                Line(words=[Word("b", (0, 15, 10, 25))], bbox=(0, 15, 10, 25), font_size_pt=14.0),
                Line(words=[Word("c", (0, 30, 10, 40))], bbox=(0, 30, 10, 40), font_size_pt=11.0),
            ]
        )
        assert para.estimated_font_size == 12.0  # median

    def test_content_area_text(self):
        area = ContentArea(
            paragraphs=[
                Paragraph(lines=[Line(words=[Word("p1", (0, 0, 10, 10))], bbox=(0, 0, 10, 10))]),
                Paragraph(lines=[Line(words=[Word("p2", (0, 20, 10, 30))], bbox=(0, 20, 10, 30))]),
            ]
        )
        assert area.text == "p1\n\np2"

    def test_page_text_areas(self):
        page = Page(
            page_num=1,
            width=100,
            height=100,
            dpi=300,
            areas=[
                ContentArea(is_photo=True),
                ContentArea(
                    paragraphs=[Paragraph(lines=[Line(words=[Word("text", (0, 0, 10, 10))])])],
                ),
            ],
        )
        assert len(page.text_areas) == 1


class TestFilterHeaderFooter:
    """Tests for filter_header_footer."""

    def test_empty_page(self):
        page = Page(page_num=1, width=100, height=1000, dpi=300)
        assert filter_header_footer(page) == []

    def test_keeps_body_content(self):
        area = ContentArea(
            paragraphs=[Paragraph(lines=[Line(words=[Word("body", (10, 200, 90, 220))])])],
            bbox=(10, 200, 90, 220),
        )
        page = Page(page_num=1, width=100, height=1000, dpi=300, areas=[area])
        result = filter_header_footer(page)
        assert len(result) == 1

    def test_removes_header(self):
        area = ContentArea(
            paragraphs=[Paragraph(lines=[Line(words=[Word("42", (10, 0, 90, 20))])])],
            bbox=(10, 0, 90, 20),  # top of page
        )
        page = Page(page_num=1, width=100, height=1000, dpi=300, areas=[area])
        result = filter_header_footer(page)
        assert len(result) == 0

    def test_removes_footer(self):
        area = ContentArea(
            paragraphs=[Paragraph(lines=[Line(words=[Word("99", (10, 960, 90, 980))])])],
            bbox=(10, 960, 90, 1000),  # bottom of page
        )
        page = Page(page_num=1, width=100, height=1000, dpi=300, areas=[area])
        result = filter_header_footer(page)
        assert len(result) == 0

    def test_keeps_photo(self):
        area = ContentArea(is_photo=True, bbox=(10, 0, 90, 20))
        page = Page(page_num=1, width=100, height=1000, dpi=300, areas=[area])
        result = filter_header_footer(page)
        assert len(result) == 1
