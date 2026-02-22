"""
PDF Parser — Extracts text page-by-page from all PDFs in clearpath_docs/
with metadata: source_file, page_number, section_heading.
"""

import re
import pdfplumber
from pathlib import Path
from app.config import DOCS_DIR
import logging

logger = logging.getLogger(__name__)

# Heuristic: a line is likely a heading if it's short, ends without period,
# and is either all-caps or title-case.
_HEADING_RE = re.compile(
    r"^(?:[A-Z][A-Za-z0-9 &/\-:–—]{2,80}|[A-Z][A-Z0-9 &/\-:–—]{2,80})$"
)


def _detect_heading(line: str) -> bool:
    """Return True if *line* looks like a section heading."""
    stripped = line.strip()
    if not stripped or len(stripped) > 100:
        return False
    if stripped.endswith((".","!","?")):
        return False
    if _HEADING_RE.match(stripped):
        return True
    # Also treat lines that are title-case and short as headings
    if stripped.istitle() and len(stripped.split()) <= 10:
        return True
    return False


def parse_all_pdfs() -> list[dict]:
    """
    Parse every PDF in DOCS_DIR.

    Returns a flat list of blocks, each being a dict:
    {
        "text": str,
        "source_file": str,      # filename only
        "page_number": int,       # 1-indexed
        "section_heading": str,   # closest detected heading or ""
        "chunk_index": int        # sequential within the file
    }
    """
    all_blocks: list[dict] = []

    pdf_files = sorted(DOCS_DIR.glob("*.pdf"))
    if not pdf_files:
        logger.warning("No PDF files found in %s", DOCS_DIR)
        return all_blocks

    for pdf_path in pdf_files:
        logger.info("Parsing: %s", pdf_path.name)
        try:
            file_blocks = _parse_single_pdf(pdf_path)
            all_blocks.extend(file_blocks)
        except Exception as e:
            logger.error("Failed to parse %s: %s", pdf_path.name, e)

    logger.info("Total blocks extracted: %d from %d PDFs", len(all_blocks), len(pdf_files))
    return all_blocks


def _parse_single_pdf(pdf_path: Path) -> list[dict]:
    """Extract text from a single PDF file, page by page."""
    blocks: list[dict] = []
    chunk_index = 0

    with pdfplumber.open(pdf_path) as pdf:
        current_heading = ""

        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text()
            if not text or not text.strip():
                continue

            # Split page into paragraphs (double newline or heading transitions)
            paragraphs = _split_into_paragraphs(text)

            for para in paragraphs:
                para_stripped = para.strip()
                if not para_stripped:
                    continue

                # Check if the first line is a heading
                first_line = para_stripped.split("\n")[0].strip()
                if _detect_heading(first_line):
                    current_heading = first_line

                blocks.append({
                    "text": para_stripped,
                    "source_file": pdf_path.name,
                    "page_number": page_num,
                    "section_heading": current_heading,
                    "chunk_index": chunk_index,
                })
                chunk_index += 1

    return blocks


def _split_into_paragraphs(text: str) -> list[str]:
    """
    Split extracted page text into paragraphs.
    Uses double newlines as primary separator, falls back to single
    newlines when paragraphs seem to end with sentence-terminal punctuation.
    """
    # First try double newlines
    parts = re.split(r"\n\s*\n", text)
    if len(parts) > 1:
        return parts

    # Fallback: split on single newlines that follow sentence-end punctuation
    lines = text.split("\n")
    paragraphs: list[str] = []
    current: list[str] = []

    for line in lines:
        current.append(line)
        stripped = line.strip()
        if stripped and (stripped.endswith((".", "!", "?", ":")) or _detect_heading(stripped)):
            paragraphs.append("\n".join(current))
            current = []

    if current:
        paragraphs.append("\n".join(current))

    return paragraphs
