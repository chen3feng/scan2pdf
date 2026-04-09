"""Tests for the text_cleaner module."""

from scan2pdf.text_cleaner import (
    clean_text,
    fix_common_ocr_errors,
    fix_hyphenation,
    fix_quotes,
    merge_lines_to_paragraphs,
    normalize_whitespace,
)


class TestFixHyphenation:
    """Tests for fix_hyphenation."""

    def test_basic_hyphenation(self):
        assert fix_hyphenation("some-\nthing") == "something"

    def test_hyphenation_with_spaces(self):
        assert fix_hyphenation("some- \n thing") == "something"

    def test_preserves_real_hyphens(self):
        assert fix_hyphenation("well-known") == "well-known"

    def test_no_hyphenation(self):
        assert fix_hyphenation("hello world") == "hello world"


class TestFixCommonOcrErrors:
    """Tests for fix_common_ocr_errors."""

    def test_smart_quotes_replaced(self):
        result = fix_common_ocr_errors("\u201chello\u201d")
        assert result == '"hello"'

    def test_single_smart_quotes_replaced(self):
        result = fix_common_ocr_errors("\u2018hello\u2019")
        assert result == "'hello'"


class TestNormalizeWhitespace:
    """Tests for normalize_whitespace."""

    def test_multiple_spaces(self):
        assert normalize_whitespace("hello   world") == "hello world"

    def test_tabs_to_space(self):
        assert normalize_whitespace("hello\tworld") == "hello world"

    def test_collapse_newlines(self):
        assert normalize_whitespace("a\n\n\n\nb") == "a\n\nb"

    def test_trailing_whitespace(self):
        assert normalize_whitespace("hello \nworld") == "hello\nworld"

    def test_crlf_to_lf(self):
        assert normalize_whitespace("hello\r\nworld") == "hello\nworld"


class TestFixQuotes:
    """Tests for fix_quotes."""

    def test_left_double_quote(self):
        assert fix_quotes("\u201c") == '"'

    def test_right_double_quote(self):
        assert fix_quotes("\u201d") == '"'

    def test_left_single_quote(self):
        assert fix_quotes("\u2018") == "'"

    def test_right_single_quote(self):
        assert fix_quotes("\u2019") == "'"


class TestCleanText:
    """Tests for the combined clean_text function."""

    def test_combined_cleaning(self):
        text = "some-\nthing   \u201chello\u201d"
        result = clean_text(text)
        assert "something" in result
        assert '"hello"' in result

    def test_empty_string(self):
        assert clean_text("") == ""

    def test_already_clean(self):
        assert clean_text("Hello world.") == "Hello world."


class TestMergeLinesToParagraphs:
    """Tests for merge_lines_to_paragraphs."""

    def test_single_paragraph(self):
        lines = ["Hello", "world"]
        assert merge_lines_to_paragraphs(lines) == "Hello world"

    def test_two_paragraphs(self):
        lines = ["First para.", "", "Second para."]
        assert merge_lines_to_paragraphs(lines) == "First para.\n\nSecond para."

    def test_empty_input(self):
        assert merge_lines_to_paragraphs([]) == ""

    def test_multiple_blank_lines(self):
        lines = ["A", "", "", "B"]
        assert merge_lines_to_paragraphs(lines) == "A\n\nB"

    def test_leading_trailing_blanks(self):
        lines = ["", "Hello", ""]
        assert merge_lines_to_paragraphs(lines) == "Hello"
