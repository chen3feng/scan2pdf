"""
Pipeline - Orchestrate the full PDF conversion process.

Coordinates all steps: split PDF -> OCR -> parse -> clean -> generate -> merge.
"""

import logging
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .hocr_parser import filter_header_footer, parse_hocr
from .ocr_engine import ocr_image_to_hocr
from .pdf_generator import StyledParagraph, text_to_pdf_page
from .pdf_merger import merge_pdfs
from .pdf_splitter import (
    compress_cover_page,
    extract_page_as_image,
    get_page_count,
)
from .text_cleaner import clean_text, merge_lines_to_paragraphs

log = logging.getLogger(__name__)


def default_workers() -> int:
    """Return the number of physical CPU cores, capped at 32."""
    try:
        # os.sched_getaffinity is not available on Windows
        count = os.cpu_count() or 4
        # On systems with hyper-threading, physical cores ≈ logical / 2.
        # Try psutil first for an accurate count; fall back to halving.
        try:
            import psutil

            count = psutil.cpu_count(logical=False) or count
        except ImportError:
            count = max(1, count // 2)
    except Exception:
        count = 4
    return min(count, 32)


class ConversionConfig:
    """Configuration for the PDF conversion pipeline."""

    def __init__(
        self,
        cover_pages: list[int] | None = None,
        ocr_lang: str = "eng",
        dpi: int = 300,
        cover_quality: int = 60,
        cover_max_width: int = 1200,
        workers: int | None = None,
        keep_temp: bool = False,
        tesseract_cmd: str = "tesseract",
        page_set: set[int] | None = None,
    ):
        self.cover_pages = cover_pages or [1]
        self.ocr_lang = ocr_lang
        self.dpi = dpi
        self.cover_quality = cover_quality
        self.cover_max_width = cover_max_width
        self.workers = workers if workers is not None else default_workers()
        self.keep_temp = keep_temp
        self.tesseract_cmd = tesseract_cmd
        self.page_set = page_set


def _process_text_page(
    pdf_path: Path,
    page_num: int,
    tmp_dir: Path,
    config: ConversionConfig,
) -> tuple[int, Path]:
    """
    Process a single text page: render -> OCR -> parse -> clean -> generate PDF.

    Returns:
        Tuple of (page_num, path_to_generated_pdf).
    """
    log.info(f"Processing page {page_num}...")

    # Step 1: Render page as image
    img_path = tmp_dir / f"page-{page_num:04d}.png"
    extract_page_as_image(pdf_path, page_num, img_path, dpi=config.dpi)

    # Step 2: OCR the image
    hocr_content = ocr_image_to_hocr(img_path, lang=config.ocr_lang, tesseract_cmd=config.tesseract_cmd)

    # Save hOCR for parsing
    hocr_path = tmp_dir / f"page-{page_num:04d}.hocr"
    hocr_path.write_text(hocr_content, encoding="utf-8")

    # Step 3: Parse hOCR
    page = parse_hocr(hocr_path)

    # Step 4: Filter headers/footers and extract structured paragraphs
    filtered_areas = filter_header_footer(page)
    lines = []
    styled_paragraphs = []

    for area in filtered_areas:
        if area.is_photo:
            continue
        for para in area.paragraphs:
            # Collect lines for plain text fallback
            para_lines = []
            for line in para.lines:
                lines.append(line.text)
                para_lines.append(line.text)
            lines.append("")  # Paragraph break

            # Build styled paragraph with font size info
            para_text = " ".join(para_lines)
            font_size = para.estimated_font_size
            styled_paragraphs.append(
                StyledParagraph(
                    text=para_text,
                    font_size_pt=font_size,
                )
            )

    # Step 5: Clean text (both plain and styled)
    raw_text = "\n".join(lines)
    cleaned = clean_text(raw_text)
    merged = merge_lines_to_paragraphs(cleaned.split("\n"))

    # Also clean styled paragraph texts
    for sp in styled_paragraphs:
        sp.text = clean_text(sp.text)

    # Step 6: Generate text PDF with font size awareness
    page_pdf = tmp_dir / f"page-{page_num:04d}.pdf"
    text_to_pdf_page(merged, page_pdf, styled_paragraphs=styled_paragraphs)

    # Clean up large temp files
    if not config.keep_temp:
        img_path.unlink(missing_ok=True)
        hocr_path.unlink(missing_ok=True)

    log.info(f"Page {page_num} done ({page_pdf.stat().st_size / 1024:.1f} KB)")
    return (page_num, page_pdf)


def convert_pdf(
    input_path: Path,
    output_path: Path,
    config: ConversionConfig | None = None,
    progress_callback=None,
) -> Path:
    """
    Convert a scanned PDF to a compact text PDF.

    Args:
        input_path: Path to the input scanned PDF.
        output_path: Where to save the output PDF.
        config: Conversion configuration.
        progress_callback: Optional callback(current, total, message).

    Returns:
        Path to the output PDF.
    """
    if config is None:
        config = ConversionConfig()

    input_path = Path(input_path).resolve()
    output_path = Path(output_path).resolve()

    total_pages = get_page_count(input_path)
    log.info(f"Input: {input_path} ({total_pages} pages)")

    # Determine which pages to process
    if config.page_set is not None:
        # Filter out-of-range pages from the user-specified set
        selected_pages = sorted(p for p in config.page_set if 1 <= p <= total_pages)
        if not selected_pages:
            raise ValueError("No valid pages in the specified range")
        log.info(f"Page selection: {len(selected_pages)} of {total_pages} pages")
    else:
        selected_pages = list(range(1, total_pages + 1))

    # Create temp directory
    tmp_dir = Path(tempfile.mkdtemp(prefix="scan2pdf_"))
    log.info(f"Temp directory: {tmp_dir}")

    try:
        page_pdfs: dict[int, Path] = {}
        selected_set = set(selected_pages)
        effective_total = len(selected_pages)

        # Process cover pages (only those within selected pages)
        for cover_num in config.cover_pages:
            if cover_num not in selected_set:
                log.warning(f"Cover page {cover_num} out of range, skipping")
                continue

            if progress_callback:
                progress_callback(len(page_pdfs), effective_total, f"Compressing cover page {cover_num}")

            log.info(f"Processing cover page {cover_num}...")
            cover_pdf = tmp_dir / f"page-{cover_num:04d}.pdf"
            compress_cover_page(
                input_path,
                cover_num,
                cover_pdf,
                quality=config.cover_quality,
                max_width=config.cover_max_width,
            )
            page_pdfs[cover_num] = cover_pdf
            log.info(f"Cover page {cover_num} done ({cover_pdf.stat().st_size / 1024:.1f} KB)")

        # Process text pages (selected pages minus cover pages)
        text_pages = [p for p in selected_pages if p not in config.cover_pages]

        completed = len(page_pdfs)

        # Use thread pool for parallel OCR processing
        failed_pages = []
        with ThreadPoolExecutor(max_workers=config.workers) as executor:
            futures = {}
            for page_num in text_pages:
                future = executor.submit(
                    _process_text_page,
                    input_path,
                    page_num,
                    tmp_dir,
                    config,
                )
                futures[future] = page_num

            for future in as_completed(futures):
                page_num = futures[future]
                try:
                    num, pdf_path = future.result()
                    page_pdfs[num] = pdf_path
                    completed += 1

                    if progress_callback:
                        progress_callback(completed, effective_total, f"Page {num}/{effective_total} done")
                except Exception as e:
                    log.error(f"Failed to process page {page_num}: {e}")
                    failed_pages.append(page_num)
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, effective_total, f"Page {page_num} FAILED, skipping")

        if failed_pages:
            failed_pages.sort()
            log.warning(f"{len(failed_pages)} page(s) failed and were skipped: {failed_pages}")

        # Merge all pages in order
        log.info("Merging all pages...")
        if progress_callback:
            progress_callback(effective_total, effective_total, "Merging pages...")

        ordered_pdfs = [page_pdfs[i] for i in sorted(page_pdfs.keys())]
        merge_pdfs(ordered_pdfs, output_path)

        log.info(f"Output: {output_path} ({output_path.stat().st_size / 1024 / 1024:.2f} MB)")

    finally:
        if not config.keep_temp:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            log.debug(f"Cleaned up temp directory: {tmp_dir}")
        else:
            log.info(f"Temp files kept at: {tmp_dir}")

    return output_path
