"""
Text cleaner - Fix OCR artifacts and improve text quality.

Handles hyphenation, broken words, paragraph merging, and common OCR errors.
"""

import re


def clean_text(text: str) -> str:
    """Apply all text cleaning steps."""
    text = fix_hyphenation(text)
    text = fix_common_ocr_errors(text)
    text = normalize_whitespace(text)
    text = fix_quotes(text)
    return text.strip()


def fix_hyphenation(text: str) -> str:
    """
    Fix words broken across lines with hyphens.

    E.g., "some-\\nthing" -> "something"
    But preserve real hyphens like "well-known".
    """
    # Fix hyphenated line breaks: word- \n word -> merged word
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    return text


def fix_common_ocr_errors(text: str) -> str:
    """Fix common OCR misrecognitions."""
    # Ligature substitutions (regex)
    ligatures = [
        (r"\bﬁ\b", "fi"),
        (r"\bﬂ\b", "fl"),
        (r"\bﬀ\b", "ff"),
        (r"\bﬃ\b", "ffi"),
        (r"\bﬄ\b", "ffl"),
    ]
    for pattern, replacement in ligatures:
        text = re.sub(pattern, replacement, text)

    # Direct character replacements (no regex needed)
    char_replacements = {
        "\u2018": "'",  # left single quote
        "\u2019": "'",  # right single quote
        "\u201c": '"',  # left double quote
        "\u201d": '"',  # right double quote
    }
    for old, new in char_replacements.items():
        text = text.replace(old, new)

    return text


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace while preserving paragraph breaks."""
    # Replace multiple spaces with single space
    text = re.sub(r"[ \t]+", " ", text)
    # Normalize line endings
    text = re.sub(r"\r\n", "\n", text)
    # Remove trailing whitespace on each line
    text = re.sub(r" +\n", "\n", text)
    # Collapse 3+ newlines to 2 (paragraph break)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def fix_quotes(text: str) -> str:
    """Normalize quotation marks."""
    # Smart quotes to straight quotes (for consistency)
    text = text.replace("\u2018", "'")  # left single
    text = text.replace("\u2019", "'")  # right single
    text = text.replace("\u201c", '"')  # left double
    text = text.replace("\u201d", '"')  # right double
    return text


def merge_lines_to_paragraphs(lines: list[str]) -> str:
    """
    Merge lines into paragraphs intelligently.

    Lines that are part of the same paragraph get joined with spaces.
    Paragraph breaks are preserved as double newlines.
    """
    if not lines:
        return ""

    paragraphs = []
    current_para = []

    for line in lines:
        line = line.strip()
        if not line:
            # Empty line = paragraph break
            if current_para:
                paragraphs.append(" ".join(current_para))
                current_para = []
            continue

        current_para.append(line)

    if current_para:
        paragraphs.append(" ".join(current_para))

    return "\n\n".join(paragraphs)
