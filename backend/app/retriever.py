"""
Retriever — Query the FAISS index and return top-K relevant chunks.
"""

import faiss
import numpy as np
from app.embeddings import embed_query
from app.config import TOP_K
import logging

logger = logging.getLogger(__name__)


def retrieve(
    query: str,
    index: faiss.Index,
    chunks: list[dict],
    top_k: int = TOP_K,
) -> list[dict]:
    """
    Embed the user query and search the FAISS index.

    Returns a list of dicts, each containing:
    {
        "chunk": { ...original chunk metadata... },
        "score": float  # cosine similarity
    }
    Sorted by score descending.
    """
    if index is None or not chunks:
        logger.warning("Retriever called with empty index or chunks")
        return []

    query_vec = embed_query(query)                      # shape (1, 384)
    scores, indices = index.search(query_vec, top_k)    # both shape (1, top_k)

    results: list[dict] = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(chunks):
            continue
        results.append({
            "chunk": chunks[idx],
            "score": float(score),
        })

    logger.info("Retrieved %d chunks for query (top score: %.3f)",
                len(results), results[0]["score"] if results else 0.0)
    return results
