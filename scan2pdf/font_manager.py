"""
Font manager - Detect and register CJK fonts for ReportLab.

Handles automatic font selection based on OCR language, searching for
system-installed CJK fonts on macOS, Linux, and Windows.
"""

import logging
import platform
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

log = logging.getLogger(__name__)

# CJK language codes used by Tesseract
_CJK_LANGS = frozenset(
    {
        "chi_sim",
        "chi_tra",
        "chi_sim_vert",
        "chi_tra_vert",
        "jpn",
        "jpn_vert",
        "kor",
        "kor_vert",
    }
)

# Font search paths per platform
_FONT_SEARCH_PATHS: dict[str, list[str]] = {
    "Darwin": [
        "/System/Library/Fonts",
        "/System/Library/Fonts/Supplemental",
        "/Library/Fonts",
        str(Path.home() / "Library/Fonts"),
    ],
    "Linux": [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        str(Path.home() / ".local/share/fonts"),
        str(Path.home() / ".fonts"),
    ],
    "Windows": [
        r"C:\Windows\Fonts",
    ],
}

# Candidate CJK font files, ordered by preference.
# Each entry: (filename_pattern, subfontIndex_for_ttc_or_None)
# We try these in order and use the first one found.
_CJK_FONT_CANDIDATES: list[tuple[str, int | None]] = [
    # macOS fonts
    ("Songti.ttc", 0),  # STSong (宋体) - serif, good for body text
    ("STHeiti Medium.ttc", 0),  # STHeiti (黑体) - sans-serif
    ("STHeiti Light.ttc", 0),  # STHeiti Light
    ("Hiragino Sans GB.ttc", 0),  # Hiragino Sans GB
    # Linux fonts (Noto CJK)
    ("NotoSansCJKsc-Regular.ttf", None),
    ("NotoSansCJKsc-Regular.otf", None),
    ("NotoSerifCJKsc-Regular.ttf", None),
    ("NotoSerifCJKsc-Regular.otf", None),
    ("NotoSansSC-Regular.ttf", None),
    ("NotoSansSC-Regular.otf", None),
    # WenQuanYi (common on Linux)
    ("wqy-microhei.ttc", 0),
    ("wqy-zenhei.ttc", 0),
    # Windows fonts
    ("simsun.ttc", 0),
    ("simhei.ttf", None),
    ("msyh.ttc", 0),
    ("msyhbd.ttc", 0),
]

_CJK_BOLD_CANDIDATES: list[tuple[str, int | None]] = [
    # macOS
    ("Songti.ttc", 1),  # STSong Bold
    ("STHeiti Medium.ttc", 0),  # STHeiti Medium as bold fallback
    ("Hiragino Sans GB.ttc", 0),
    # Linux
    ("NotoSansCJKsc-Bold.ttf", None),
    ("NotoSansCJKsc-Bold.otf", None),
    ("NotoSerifCJKsc-Bold.ttf", None),
    ("NotoSerifCJKsc-Bold.otf", None),
    ("NotoSansSC-Bold.ttf", None),
    ("NotoSansSC-Bold.otf", None),
    ("wqy-microhei.ttc", 0),
    ("wqy-zenhei.ttc", 0),
    # Windows
    ("simhei.ttf", None),
    ("msyhbd.ttc", 0),
]

# Registered font names (module-level cache)
_registered_regular: str | None = None
_registered_bold: str | None = None


def _find_font(candidates: list[tuple[str, int | None]]) -> tuple[Path, int | None] | None:
    """Search system font directories for the first matching candidate."""
    system = platform.system()
    search_dirs = _FONT_SEARCH_PATHS.get(system, [])

    for font_file, subfont_idx in candidates:
        for font_dir in search_dirs:
            font_path = Path(font_dir) / font_file
            if font_path.exists():
                return (font_path, subfont_idx)
            # Also search subdirectories (Linux fonts are often nested)
            if system == "Linux":
                for match in Path(font_dir).rglob(font_file):
                    return (match, subfont_idx)

    return None


def _register_font(name: str, font_path: Path, subfont_idx: int | None) -> bool:
    """Register a TrueType font with ReportLab."""
    try:
        kwargs = {"name": name, "filename": str(font_path)}
        if subfont_idx is not None and font_path.suffix.lower() == ".ttc":
            kwargs["subfontIndex"] = subfont_idx
        pdfmetrics.registerFont(TTFont(**kwargs))
        log.info("Registered CJK font '%s' from %s", name, font_path)
        return True
    except Exception as e:
        log.debug("Failed to register font '%s' from %s: %s", name, font_path, e)
        return False


def is_cjk_lang(lang: str) -> bool:
    """Check if the given Tesseract language code is a CJK language."""
    # Handle multi-language specs like "chi_sim+eng"
    return any(part.strip() in _CJK_LANGS for part in lang.split("+"))


def get_cjk_fonts() -> tuple[str, str]:
    """
    Find and register CJK fonts, returning (regular_name, bold_name).

    Returns the ReportLab font names for regular and bold CJK fonts.
    Falls back to ("Times-Roman", "Times-Bold") if no CJK font is found.

    The result is cached so fonts are only registered once.
    """
    global _registered_regular, _registered_bold

    if _registered_regular is not None:
        return (_registered_regular, _registered_bold or _registered_regular)

    # Find and register regular font
    result = _find_font(_CJK_FONT_CANDIDATES)
    if result is None:
        log.warning(
            "No CJK font found on this system. "
            "Chinese/Japanese/Korean text will not render correctly. "
            "Install Noto CJK fonts: https://github.com/googlefonts/noto-cjk"
        )
        _registered_regular = "Times-Roman"
        _registered_bold = "Times-Bold"
        return (_registered_regular, _registered_bold)

    font_path, subfont_idx = result
    cjk_regular = "CJK-Regular"
    if not _register_font(cjk_regular, font_path, subfont_idx):
        _registered_regular = "Times-Roman"
        _registered_bold = "Times-Bold"
        return (_registered_regular, _registered_bold)

    _registered_regular = cjk_regular

    # Find and register bold font
    bold_result = _find_font(_CJK_BOLD_CANDIDATES)
    cjk_bold = "CJK-Bold"
    if bold_result is not None:
        bold_path, bold_subfont = bold_result
        _registered_bold = cjk_bold if _register_font(cjk_bold, bold_path, bold_subfont) else cjk_regular
    else:
        _registered_bold = cjk_regular  # Fall back to regular

    return (_registered_regular, _registered_bold)
