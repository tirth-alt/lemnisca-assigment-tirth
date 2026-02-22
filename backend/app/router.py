"""
Router — Deterministic, rule-based query classifier.
Classifies each query as 'simple' or 'complex' using additive signal scoring.
"""

import re
from app.config import (
    COMPLEXITY_THRESHOLD,
    MULTI_DOC_THRESHOLD,
    SIMPLE_MODEL,
    COMPLEX_MODEL,
)
import logging

logger = logging.getLogger(__name__)

# ── Keywords & Patterns ──────────────────────────────────────────────
_COMPLEX_KEYWORDS = re.compile(
    r"\b(compare|comparison|explain|difference|differences|why|how does|how do|"
    r"analyze|analyse|pros and cons|trade-?off|versus|implications|impact|"
    r"advantages|disadvantages|recommend|suggest|evaluate|assessment|"
    r"relationship between|what happens if|describe in detail)\b",
    re.IGNORECASE,
)

_COMPARISON_WORDS = re.compile(
    r"\b(vs\.?|versus|better|worse|or|compared to|differ)\b",
    re.IGNORECASE,
)

_NEGATION_QUESTION = re.compile(
    r"\b(not|don't|doesn't|can't|cannot|won't|shouldn't|isn't|aren't)\b",
    re.IGNORECASE,
)

_SUBCLAUSE_INDICATORS = re.compile(
    r"(;|—|--|however|but\b|although|whereas|nevertheless|furthermore|moreover|on the other hand)",
    re.IGNORECASE,
)

_MULTI_ENTITY = re.compile(
    r"\b(and|both|all|each|every|multiple|several)\b",
    re.IGNORECASE,
)


def classify_query(query: str) -> dict:
    """
    Score a query using additive signals and classify as simple/complex.

    Returns:
    {
        "classification": "simple" | "complex",
        "score": int,
        "signals": list[str],   # which signals fired
        "model": str,           # model to use
    }
    """
    score = 0
    signals: list[str] = []
    words = query.split()
    word_count = len(words)

    # Signal 1: Query length (≥ 15 words → +2)
    if word_count >= 15:
        score += 2
        signals.append(f"long_query({word_count} words)")

    # Signal 2: Complex keywords (+2)
    if _COMPLEX_KEYWORDS.search(query):
        score += 2
        signals.append("complex_keyword")

    # Signal 3: Multiple question marks (+1)
    if query.count("?") >= 2:
        score += 1
        signals.append("multi_question_mark")

    # Signal 4: Comparison words (+1)
    if _COMPARISON_WORDS.search(query):
        score += 1
        signals.append("comparison_words")

    # Signal 5: Negation in a question (+1)
    if "?" in query and _NEGATION_QUESTION.search(query):
        score += 1
        signals.append("negation_question")

    # Signal 6: Sub-clause indicators (+1)
    if _SUBCLAUSE_INDICATORS.search(query):
        score += 1
        signals.append("subclause_indicator")

    # Signal 7: Multiple entities / topics (+1)
    if _MULTI_ENTITY.search(query) and word_count >= 8:
        score += 1
        signals.append("multi_entity")

    classification = "complex" if score >= COMPLEXITY_THRESHOLD else "simple"
    model = COMPLEX_MODEL if classification == "complex" else SIMPLE_MODEL

    logger.info(
        "Router: query=%r → score=%d, classification=%s, signals=%s",
        query[:60], score, classification, signals,
    )

    return {
        "classification": classification,
        "score": score,
        "signals": signals,
        "model": model,
    }


def maybe_upgrade_after_retrieval(
    route_result: dict,
    retrieved_chunks: list[dict],
) -> dict:
    """
    Post-retrieval override: if initially classified as 'simple' but
    retrieved chunks come from >= MULTI_DOC_THRESHOLD distinct documents,
    upgrade to 'complex'.
    """
    if route_result["classification"] == "complex":
        return route_result

    unique_docs = set()
    for item in retrieved_chunks:
        chunk = item.get("chunk", item)
        unique_docs.add(chunk.get("source_file", ""))

    if len(unique_docs) >= MULTI_DOC_THRESHOLD:
        logger.info(
            "Router upgrade: simple→complex (chunks from %d docs: %s)",
            len(unique_docs), unique_docs,
        )
        route_result = route_result.copy()
        route_result["classification"] = "complex"
        route_result["model"] = COMPLEX_MODEL
        route_result["signals"].append(f"multi_doc_upgrade({len(unique_docs)} docs)")

    return route_result
