"""
OCR engine - Run Tesseract OCR on page images.

Provides a Python wrapper around Tesseract to produce hOCR output,
then parses it into structured text.
"""

import logging
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)


def ocr_image_to_hocr(image_path: Path, lang: str = "eng", tesseract_cmd: str = "tesseract") -> str:
    """
    Run Tesseract OCR on an image and return hOCR output as string.

    Args:
        image_path: Path to the input image (PNG, JPEG, TIFF).
        lang: Tesseract language code.
        tesseract_cmd: Path to tesseract executable.

    Returns:
        hOCR HTML content as string.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        output_base = Path(tmpdir) / "output"

        cmd = [
            tesseract_cmd,
            str(image_path),
            str(output_base),
            "-l",
            lang,
            "--dpi",
            "300",
            "hocr",
        ]

        log.debug(f"Running: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            log.warning(f"Tesseract stderr: {result.stderr}")

        hocr_file = output_base.with_suffix(".hocr")
        if not hocr_file.exists():
            raise RuntimeError(f"Tesseract failed to produce hOCR output.\nstderr: {result.stderr}")

        return hocr_file.read_text(encoding="utf-8")


def ocr_image_to_text(image_path: Path, lang: str = "eng", tesseract_cmd: str = "tesseract") -> str:
    """
    Run Tesseract OCR on an image and return plain text.

    Args:
        image_path: Path to the input image.
        lang: Tesseract language code.
        tesseract_cmd: Path to tesseract executable.

    Returns:
        Recognized text as string.
    """
    cmd = [
        tesseract_cmd,
        str(image_path),
        "stdout",
        "-l",
        lang,
        "--dpi",
        "300",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        log.warning(f"Tesseract stderr: {result.stderr}")

    return result.stdout
