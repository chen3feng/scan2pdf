"""
PDF merger - Combine individual page PDFs into a final output.

Uses pypdf to merge cover page and text pages into a single PDF.
"""

import logging
from pathlib import Path

from pypdf import PdfReader, PdfWriter

log = logging.getLogger(__name__)


def merge_pdfs(pdf_paths: list[Path], output_path: Path) -> Path:
    """
    Merge multiple PDF files into one.

    Args:
        pdf_paths: Ordered list of PDF files to merge.
        output_path: Where to save the merged PDF.

    Returns:
        Path to the merged PDF.
    """
    writer = PdfWriter()

    for pdf_path in pdf_paths:
        if not pdf_path.exists():
            log.warning(f"Skipping missing file: {pdf_path}")
            continue

        reader = PdfReader(str(pdf_path))
        for page in reader.pages:
            writer.add_page(page)

    with open(output_path, "wb") as f:
        writer.write(f)

    log.info(
        f"Merged {len(pdf_paths)} PDFs -> {output_path} "
        f"({output_path.stat().st_size / 1024 / 1024:.2f} MB)"
    )
    return output_path
