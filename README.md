English | [简体中文](README-zh.md)

# scan2pdf

Convert scanned PDF books to compact text PDFs with OCR.

Takes a large scanned PDF (image-based), runs OCR on each page, and produces a lightweight text-based PDF with clean typography — typically achieving **99%+ compression**.

## Features

- **OCR-powered conversion** — Uses Tesseract to extract text from scanned pages
- **Font-size aware rendering** — Detects heading/body sizes from OCR data and preserves relative typography
- **Single-page guarantee** — Each scanned page maps to exactly one output page (auto-shrinks font if content overflows)
- **Even vertical distribution** — Text fills the full page height instead of bunching at the top
- **Cover page preservation** — Keeps cover pages as compressed images
- **Parallel processing** — Multi-threaded OCR for faster conversion
- **Printer-style page selection** — Process specific pages with syntax like `1,3-5,10-20`

## scan2pdf vs ocrmypdf

Both tools use Tesseract OCR, but they serve **fundamentally different purposes**:

| | **ocrmypdf** | **scan2pdf** |
|---|---|---|
| **Goal** | Add an invisible text layer to scanned PDFs (searchable/copyable) | **Re-generate** scanned PDFs as pure text PDFs |
| **Output** | Original images + transparent text overlay | Clean typeset text, images discarded |
| **File size** | Roughly the same as input (images retained) | **99%+ compression** (text only) |
| **Appearance** | Identical to the original scan | Re-typeset text pages |

**What makes scan2pdf unique:**

- **Extreme compression** — A 190 MB scanned book becomes a few hundred KB
- **Intelligent re-typesetting** — Infers font sizes from hOCR bounding boxes, distinguishes headings from body text, and evenly distributes text to fill each page
- **Strict page correspondence** — Every input page maps to exactly one output page; auto-shrinks font (down to 6 pt) if content overflows
- **Cover page handling** — Cover pages are kept as compressed images while text pages are converted to pure text
- **OCR text cleaning pipeline** — Fixes OCR artifacts, merges broken lines, and filters headers/footers for clean, readable output

**When to use which:**

| Scenario | Recommendation |
|----------|----------------|
| Preserve original scan appearance, just need search/copy | **ocrmypdf** |
| Extreme compression for reading on phone/Kindle | **scan2pdf** |
| Archival with legal fidelity | **ocrmypdf** |
| Bulk scanned novels/textbooks, only care about text | **scan2pdf** |

> **TL;DR** — ocrmypdf adds "invisible subtitles" to scans; scan2pdf turns scans into e-books.

## Prerequisites

- **Python** ≥ 3.10
- **uv** — [Installation guide](https://docs.astral.sh/uv/getting-started/installation/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Tesseract OCR** — [Installation guide](https://github.com/tesseract-ocr/tesseract)
- **Poppler** (for `pdftoppm`) — [Windows](https://github.com/oschwartz10612/poppler-windows/releases), [macOS](https://formulae.brew.sh/formula/poppler) (`brew install poppler`), [Linux](https://poppler.freedesktop.org/) (`apt install poppler-utils`)

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd scan2pdf

# Install dependencies (including dev tools)
uv sync

# Or install with optional fast rendering
uv sync --extra fast
```

## Usage

### Basic

```bash
# Convert entire book (output: book-text.pdf)
uv run scan2pdf book.pdf

# Specify output file
uv run scan2pdf book.pdf -o output.pdf
```

### Quick Testing

```bash
# Convert only pages 3 to 10
uv run scan2pdf book.pdf -n 3-10

# Convert specific pages
uv run scan2pdf book.pdf -n 1,5,10-20
```

### Advanced Options

```bash
# Custom cover pages, language, and workers
uv run scan2pdf book.pdf --cover 1 2 3 --lang eng --workers 8

# Lower DPI for faster processing
uv run scan2pdf book.pdf --dpi 200

# Verbose output
uv run scan2pdf book.pdf -v      # INFO level
uv run scan2pdf book.pdf -vv     # DEBUG level

# Keep temporary files for debugging
uv run scan2pdf book.pdf --keep-temp
```

### All Options

| Option | Default | Description |
|--------|---------|-------------|
| `input` | *(required)* | Input scanned PDF file |
| `-o, --output` | `<input>-text.pdf` | Output PDF file |
| `-n, --pages` | all | Page range (e.g. `1-10`, `1,3,5-20`) |
| `--cover` | `1` | Page numbers to treat as cover/image pages |
| `--lang` | `eng` | OCR language |
| `--dpi` | `300` | DPI for rendering pages |
| `--cover-quality` | `60` | JPEG quality for cover pages |
| `--cover-max-width` | `1200` | Max width in pixels for cover images |
| `--workers` | `4` | Number of parallel OCR workers |
| `--tesseract` | `tesseract` | Path to Tesseract executable |
| `--keep-temp` | off | Keep temporary files for debugging |
| `-v, --verbose` | off | Increase verbosity (`-v` INFO, `-vv` DEBUG) |

## Development

### Setup

```bash
# Clone and install in editable mode with all dev dependencies
git clone https://github.com/chen3feng/scan2pdf.git
cd scan2pdf
uv sync
```

### Code Style

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Check for lint errors
uv run ruff check .

# Auto-fix lint errors
uv run ruff check . --fix

# Check formatting
uv run ruff format --check .

# Auto-format code
uv run ruff format .
```

### Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/test_text_cleaner.py -v

# Run tests with short traceback
uv run pytest tests/ --tb=short
```

### CI

Every push and pull request to `master` triggers [GitHub Actions](.github/workflows/ci.yml):

1. **Lint** — `ruff check` + `ruff format --check`
2. **Test** — `pytest` across Python 3.10 / 3.11 / 3.12 / 3.13

## Architecture

```
scan2pdf/
├── cli.py            # Command-line interface & argument parsing
├── pipeline.py       # Orchestrates the full conversion process
├── pdf_splitter.py   # Extracts pages as images (pikepdf + poppler)
├── ocr_engine.py     # Runs Tesseract OCR, produces hOCR
├── hocr_parser.py    # Parses hOCR output, extracts text & font sizes
├── text_cleaner.py   # Cleans OCR artifacts, merges lines into paragraphs
├── pdf_generator.py  # Generates formatted text PDFs (ReportLab)
└── pdf_merger.py     # Merges individual page PDFs into final output
```

### Processing Pipeline

```
Scanned PDF
    │
    ├─ Cover pages ──→ Render as image ──→ Compress JPEG ──→ Wrap in PDF
    │
    └─ Text pages ──→ Render as image ──→ Tesseract OCR ──→ Parse hOCR
                                                                │
                       Merge into final PDF ←── Generate PDF ←── Clean text
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `pikepdf` | PDF page extraction |
| `pypdf` | PDF reading & merging |
| `reportlab` | Text PDF generation |
| `lxml` | hOCR (HTML/XML) parsing |
| `Pillow` | Image processing |

## License

MIT
