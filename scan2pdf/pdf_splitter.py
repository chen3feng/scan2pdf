"""
PDF splitter - Extract pages from PDF as images.

Uses pikepdf to split pages and Pillow/pdf2image to render pages as images
for OCR processing.
"""

import logging
import subprocess
import tempfile
from pathlib import Path

import pikepdf
from PIL import Image

log = logging.getLogger(__name__)


def get_page_count(pdf_path: Path) -> int:
    """Get the total number of pages in a PDF."""
    with pikepdf.open(pdf_path) as pdf:
        return len(pdf.pages)


def extract_page_as_pdf(pdf_path: Path, page_num: int, output_path: Path) -> Path:
    """
    Extract a single page from a PDF file.

    Args:
        pdf_path: Source PDF file.
        page_num: 1-based page number.
        output_path: Where to save the single-page PDF.

    Returns:
        Path to the extracted single-page PDF.
    """
    with pikepdf.open(pdf_path) as pdf:
        dst = pikepdf.Pdf.new()
        dst.pages.append(pdf.pages[page_num - 1])
        dst.save(output_path)
    return output_path


def _render_single_page_pdf(single_page_pdf: Path, output_path: Path,
                            dpi: int = 300) -> Path:
    """
    Render a single-page PDF to a PNG image.

    Tries pdf2image (poppler), Ghostscript, and ImageMagick in order.

    Args:
        single_page_pdf: Path to a single-page PDF file.
        output_path: Where to save the PNG image.
        dpi: Resolution for rendering.

    Returns:
        Path to the rendered image.

    Raises:
        RuntimeError: If no rendering backend is available.
    """
    errors = []

    # Try pdftoppm directly (poppler) – avoids pdf2image's pdfinfo call
    # which can fail intermittently under concurrent access.
    try:
        # pdftoppm outputs <prefix>-01.png for single-page PDFs
        prefix = str(output_path.with_suffix(""))
        subprocess.run(
            [
                "pdftoppm", "-png", "-r", str(dpi),
                "-singlefile",  # output just <prefix>.png, no page suffix
                str(single_page_pdf),
                prefix,
            ],
            check=True,
            capture_output=True,
        )
        # -singlefile produces <prefix>.png
        expected = Path(f"{prefix}.png")
        if expected.exists():
            if expected != output_path:
                expected.rename(output_path)
            return output_path
    except FileNotFoundError:
        errors.append("pdftoppm (poppler) not found")
    except subprocess.CalledProcessError as e:
        errors.append(
            f"pdftoppm: {e.stderr.decode('utf-8', errors='replace')[:200] if e.stderr else e}"
        )

    # Try Ghostscript
    for gs_cmd in ["gswin64c", "gswin32c", "gs"]:
        try:
            subprocess.run(
                [
                    gs_cmd, "-dNOPAUSE", "-dBATCH", "-dSAFER",
                    "-sDEVICE=png16m",
                    f"-r{dpi}",
                    f"-sOutputFile={output_path}",
                    str(single_page_pdf),
                ],
                check=True,
                capture_output=True,
            )
            if output_path.exists():
                return output_path
        except FileNotFoundError:
            continue
        except subprocess.CalledProcessError as e:
            errors.append(f"gs ({gs_cmd}): {e.stderr[:200] if e.stderr else e}")

    # Try magick (ImageMagick)
    try:
        subprocess.run(
            [
                "magick", "-density", str(dpi),
                str(single_page_pdf),
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )
        if output_path.exists():
            return output_path
    except FileNotFoundError:
        errors.append("ImageMagick not found")
    except subprocess.CalledProcessError as e:
        errors.append(f"magick: {e.stderr[:200] if e.stderr else e}")

    raise RuntimeError(
        f"Cannot render PDF page to image. Tried backends:\n"
        + "\n".join(f"  - {err}" for err in errors)
        + "\nInstall one of: pdf2image+poppler, Ghostscript, or ImageMagick."
    )


def extract_page_as_image(pdf_path: Path, page_num: int, output_path: Path,
                          dpi: int = 300, max_retries: int = 3) -> Path:
    """
    Render a single PDF page as a PNG image.

    First extracts the page into a lightweight single-page PDF (via pikepdf),
    then renders that small PDF to an image. This avoids concurrency issues
    when multiple threads try to render from the same large PDF file.

    Args:
        pdf_path: Source PDF file.
        page_num: 1-based page number.
        output_path: Where to save the PNG image.
        dpi: Resolution for rendering.
        max_retries: Number of retry attempts on failure.

    Returns:
        Path to the rendered image.
    """
    import time

    # Extract single page to a temp PDF first (lightweight, thread-safe)
    single_pdf = output_path.with_suffix(".tmp.pdf")
    try:
        extract_page_as_pdf(pdf_path, page_num, single_pdf)

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                result = _render_single_page_pdf(single_pdf, output_path, dpi=dpi)
                return result
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    wait = attempt * 2
                    log.warning(
                        f"Page {page_num}: render attempt {attempt}/{max_retries} "
                        f"failed ({e}), retrying in {wait}s..."
                    )
                    time.sleep(wait)

        raise RuntimeError(
            f"Failed to render page {page_num} after {max_retries} attempts: "
            f"{last_error}"
        )
    finally:
        # Clean up temp single-page PDF
        single_pdf.unlink(missing_ok=True)


def compress_cover_page(pdf_path: Path, page_num: int, output_path: Path,
                        quality: int = 60, max_width: int = 1200) -> Path:
    """
    Extract cover page and compress its image.

    Renders the page as JPEG with reduced quality and size,
    then wraps it back into a PDF.

    Args:
        pdf_path: Source PDF file.
        page_num: 1-based page number (usually 1).
        output_path: Where to save the compressed cover PDF.
        quality: JPEG quality (1-100).
        max_width: Maximum width in pixels for the cover image.

    Returns:
        Path to the compressed cover PDF.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        img_path = tmp / "cover.png"

        # Render page as image
        extract_page_as_image(pdf_path, page_num, img_path, dpi=150)

        # Open and compress
        img = Image.open(img_path)

        # Resize if too large
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)

        # Convert to RGB (remove alpha if present)
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Save as compressed JPEG
        jpg_path = tmp / "cover.jpg"
        img.save(str(jpg_path), "JPEG", quality=quality, optimize=True)

        # Wrap JPEG into a PDF using Pillow
        # Calculate page size in points (72 dpi)
        # Original page is Letter size (8.5 x 11 inches)
        page_w_pt = 612  # 8.5 * 72
        page_h_pt = 792  # 11 * 72

        img_for_pdf = Image.open(jpg_path)
        img_for_pdf.save(
            str(output_path), "PDF",
            resolution=72.0,
        )

        log.info(f"Cover compressed: {output_path.stat().st_size / 1024:.1f} KB")

    return output_path
