"""
Output Evaluator — Post-generation quality checks.
Flags issues without blocking the response.
"""

import re
import numpy as np
from app.embeddings import embed_texts
from app.config import GROUNDING_THRESHOLD
import logging

logger = logging.getLogger(__name__)

# ── Refusal phrase patterns ──────────────────────────────────────────
_REFUSAL_PATTERNS = re.compile(
    r"(I don'?t have|not mentioned|cannot find|no information|"
    r"I'?m unable|not available in the provided|I couldn'?t find|"
    r"does not (contain|mention|provide|include)|"
    r"no relevant (information|data|context)|"
    r"beyond the scope|outside (of )?the (provided|available)|"
    r"isn'?t covered|not covered|I don'?t know|"
    r"unable to (find|locate|determine)|"
    r"the (documents?|context) (does|do) not)",
    re.IGNORECASE,
)


def evaluate(
    answer: str,
    retrieved_chunks: list[dict],
    chunks_retrieved_count: int,
) -> list[str]:
    """
    Run all evaluator checks on the LLM response.

    Returns a list of flag strings (empty if everything looks good).
    """
    flags: list[str] = []

    # ── Check 1: no_context ──────────────────────────────────────────
    if _check_no_context(answer, chunks_retrieved_count):
        flags.append("no_context")

    # ── Check 2: refusal ─────────────────────────────────────────────
    if _check_refusal(answer):
        flags.append("refusal")

    # ── Check 3: low_grounding (custom) ──────────────────────────────
    if chunks_retrieved_count > 0 and not _check_refusal(answer):
        if _check_low_grounding(answer, retrieved_chunks):
            flags.append("low_grounding")

    logger.info("Evaluator flags: %s", flags if flags else "none")
    return flags


def _check_no_context(answer: str, chunks_count: int) -> bool:
    """Flag if the LLM produced an answer but no chunks were retrieved."""
    if chunks_count > 0:
        return False
    # If it's a refusal, that's a separate flag
    if _REFUSAL_PATTERNS.search(answer):
        return False
    # LLM answered without any context — suspicious
    return len(answer.strip()) > 20


def _check_refusal(answer: str) -> bool:
    """Flag if the LLM explicitly refused to answer."""
    return bool(_REFUSAL_PATTERNS.search(answer))


def _check_low_grounding(answer: str, retrieved_chunks: list[dict]) -> bool:
    """
    Compare the LLM response embedding against the concatenated retrieved
    chunk embeddings via cosine similarity. Low similarity → possible hallucination.
    """
    try:
        # Build context text from chunks
        context_texts = []
        for item in retrieved_chunks:
            chunk = item.get("chunk", item)
            context_texts.append(chunk.get("text", ""))

        if not context_texts:
            return False

        combined_context = " ".join(context_texts)

        # Embed both answer and context
        embeddings = embed_texts([answer, combined_context])
        answer_vec = embeddings[0]
        context_vec = embeddings[1]

        # Cosine similarity (vectors are already L2-normalised)
        similarity = float(np.dot(answer_vec, context_vec))

        logger.info("Grounding cosine similarity: %.4f (threshold: %.2f)",
                    similarity, GROUNDING_THRESHOLD)

        return similarity < GROUNDING_THRESHOLD

    except Exception as e:
        logger.error("Grounding check failed: %s", e)
        return False
