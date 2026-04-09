"""
scan2pdf CLI - Command-line interface for converting scanned PDFs.

Usage:
    python -m scan2pdf input.pdf [-o output.pdf] [options]
"""

import argparse
import logging
import sys
import time
from pathlib import Path

from . import __version__
from .pipeline import ConversionConfig, convert_pdf, default_workers


def parse_page_range(spec: str) -> set[int]:
    """
    Parse a printer-style page range specification into a set of page numbers.

    Supports formats like: "1,2,3-8", "1-5,10,20-25", "3", "1-100"
    """
    pages = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            start = int(start_str.strip())
            end = int(end_str.strip())
            if start > end:
                raise argparse.ArgumentTypeError(
                    f"Invalid page range: {part} (start > end)"
                )
            pages.update(range(start, end + 1))
        else:
            pages.add(int(part.strip()))
    if not pages:
        raise argparse.ArgumentTypeError(f"Empty page specification: {spec!r}")
    return pages


def format_page_set(pages: set[int]) -> str:
    """
    Format a set of page numbers into a compact printer-style string.

    Example: {1, 2, 3, 5, 7, 8, 9} -> "1-3,5,7-9"
    """
    if not pages:
        return ""
    sorted_pages = sorted(pages)
    ranges = []
    start = prev = sorted_pages[0]
    for p in sorted_pages[1:]:
        if p == prev + 1:
            prev = p
        else:
            ranges.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = p
    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(ranges)


def _progress_bar(current: int, total: int, message: str, bar_width: int = 40):
    """Display a simple progress bar in the terminal."""
    pct = current / total if total > 0 else 0
    filled = int(bar_width * pct)
    bar = "█" * filled + "░" * (bar_width - filled)
    sys.stderr.write(f"\r[{bar}] {current}/{total} ({pct:.0%}) {message}")
    sys.stderr.flush()
    if current >= total:
        sys.stderr.write("\n")


def main():
    parser = argparse.ArgumentParser(
        prog="scan2pdf",
        description="Convert scanned PDF books to compact text PDFs with OCR.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m scan2pdf book.pdf
  python -m scan2pdf book.pdf -o output.pdf --lang eng
  python -m scan2pdf book.pdf --cover 1 --workers 8
  python -m scan2pdf book.pdf --cover 1 2 3 --dpi 200
  python -m scan2pdf book.pdf -n 1-10        # test with pages 1 to 10
  python -m scan2pdf book.pdf -n 1,5,10-20   # specific pages
        """,
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Input scanned PDF file",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output PDF file (default: <input>-text.pdf)",
    )
    parser.add_argument(
        "--cover",
        type=int,
        nargs="+",
        default=[1],
        help="Page numbers to treat as cover/image pages (default: 1)",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default="eng",
        help="OCR language (default: eng)",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="DPI for rendering pages (default: 300)",
    )
    parser.add_argument(
        "--cover-quality",
        type=int,
        default=60,
        help="JPEG quality for cover pages (default: 60)",
    )
    parser.add_argument(
        "--cover-max-width",
        type=int,
        default=1200,
        help="Max width in pixels for cover images (default: 1200)",
    )
    parser.add_argument(
        "-n", "--pages",
        type=str,
        default=None,
        help="Page range to process, e.g. '1-10', '1,2,5-20' (default: all)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help=f"Number of parallel OCR workers (default: {default_workers()}, physical cores)",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary files for debugging",
    )
    parser.add_argument(
        "--tesseract",
        type=str,
        default="tesseract",
        help="Path to tesseract executable (default: tesseract)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v for INFO, -vv for DEBUG)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.WARNING
    if args.verbose >= 2:
        log_level = logging.DEBUG
    elif args.verbose >= 1:
        log_level = logging.INFO

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Validate input
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Default output name
    if args.output is None:
        args.output = args.input.with_stem(args.input.stem + "-text")

    # Build config
    # Parse page range
    page_set = None
    if args.pages is not None:
        try:
            page_set = parse_page_range(args.pages)
        except (ValueError, argparse.ArgumentTypeError) as e:
            print(f"Error: Invalid page range '{args.pages}': {e}", file=sys.stderr)
            sys.exit(1)

    config = ConversionConfig(
        cover_pages=args.cover,
        ocr_lang=args.lang,
        dpi=args.dpi,
        cover_quality=args.cover_quality,
        cover_max_width=args.cover_max_width,
        workers=args.workers,
        keep_temp=args.keep_temp,
        tesseract_cmd=args.tesseract,
        page_set=page_set,
    )

    # Run conversion
    print(f"scan2pdf v{__version__}")
    print(f"Input:  {args.input}")
    print(f"Output: {args.output}")
    print(f"Cover pages: {config.cover_pages}")
    print(f"OCR language: {config.ocr_lang}")
    print(f"Workers: {config.workers}")
    if config.page_set:
        print(f"Pages: {format_page_set(config.page_set)}")
    print()

    start_time = time.time()

    try:
        convert_pdf(
            args.input,
            args.output,
            config=config,
            progress_callback=_progress_bar,
        )
    except KeyboardInterrupt:
        print("\n\nAborted by user.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        logging.getLogger(__name__).debug("Full traceback:", exc_info=True)
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)

    elapsed = time.time() - start_time
    output_size = args.output.stat().st_size / 1024 / 1024
    input_size = args.input.stat().st_size / 1024 / 1024

    print()
    print(f"Done in {elapsed:.1f}s")
    print(f"Input:  {input_size:.2f} MB")
    print(f"Output: {output_size:.2f} MB")
    print(f"Compression: {(1 - output_size / input_size) * 100:.1f}%")


if __name__ == "__main__":
    main()
