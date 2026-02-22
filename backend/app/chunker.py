"""
Chunker — Hierarchical paragraph-aware chunking with sentence overlap.
Takes raw blocks from the PDF parser and produces smaller, embedding-ready chunks.
"""

import re
from typing import Optional
from app.config import MAX_CHUNK_SIZE, OVERLAP_SENTENCES
import logging

logger = logging.getLogger(__name__)

# Sentence splitter: split on period/exclamation/question followed by space or EOL
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def chunk_blocks(blocks: list[dict]) -> list[dict]:
    """
    Take the raw blocks from pdf_parser and produce final chunks.

    Strategy:
    1. Group blocks by (source_file, page_number) to maintain page locality.
    2. If a block's text exceeds MAX_CHUNK_SIZE, split it on sentence boundaries.
    3. Add OVERLAP_SENTENCES boundary sentences from the end of one chunk
       to the beginning of the next chunk (within the same document).
    """
    if not blocks:
        return []

    # Step 1: split oversized blocks into sentence-level sub-chunks
    split_chunks = _split_oversized_blocks(blocks)

    # Step 2: add overlap between consecutive chunks of the same document
    final_chunks = _add_overlap(split_chunks)

    # Re-index chunk_index per file
    file_counters: dict[str, int] = {}
    for chunk in final_chunks:
        fname = chunk["source_file"]
        idx = file_counters.get(fname, 0)
        chunk["chunk_index"] = idx
        file_counters[fname] = idx + 1

    logger.info("Chunking complete: %d blocks → %d chunks", len(blocks), len(final_chunks))
    return final_chunks


def _split_oversized_blocks(blocks: list[dict]) -> list[dict]:
    """Split any block whose text exceeds MAX_CHUNK_SIZE on sentence boundaries."""
    result: list[dict] = []

    for block in blocks:
        text = block["text"]
        if len(text) <= MAX_CHUNK_SIZE:
            result.append(block.copy())
            continue

        # Split into sentences
        sentences = _SENTENCE_RE.split(text)
        current_text = ""
        for sent in sentences:
            if current_text and len(current_text) + len(sent) + 1 > MAX_CHUNK_SIZE:
                result.append({
                    **block,
                    "text": current_text.strip(),
                })
                current_text = sent
            else:
                current_text = (current_text + " " + sent).strip() if current_text else sent

        if current_text.strip():
            result.append({
                **block,
                "text": current_text.strip(),
            })

    return result


def _add_overlap(chunks: list[dict]) -> list[dict]:
    """
    For consecutive chunks from the same source file, prepend the last
    OVERLAP_SENTENCES sentences of the previous chunk to the current one.
    """
    if not chunks or OVERLAP_SENTENCES <= 0:
        return chunks

    result: list[dict] = [chunks[0].copy()]

    for i in range(1, len(chunks)):
        current = chunks[i].copy()
        prev = chunks[i - 1]

        # Only add overlap within the same document
        if current["source_file"] == prev["source_file"]:
            prev_sentences = _SENTENCE_RE.split(prev["text"])
            overlap = prev_sentences[-OVERLAP_SENTENCES:]
            if overlap:
                overlap_text = " ".join(overlap).strip()
                current["text"] = overlap_text + " " + current["text"]

        result.append(current)

    return result
