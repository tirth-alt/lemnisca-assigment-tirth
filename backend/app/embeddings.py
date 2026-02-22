"""
Embeddings — Sentence-Transformer embeddings + FAISS index management.
Uses multi-qa-MiniLM-L6-cos-v1 (384 dimensions).
"""

import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from pathlib import Path
from app.config import (
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    FAISS_INDEX_PATH,
    CHUNKS_PATH,
    INDEX_DIR,
)
import logging

logger = logging.getLogger(__name__)

# Global model instance (loaded once)
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Lazy-load the embedding model."""
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    """
    Embed a list of texts into normalised vectors.
    Returns: np.ndarray of shape (len(texts), EMBEDDING_DIM), L2-normalised.
    """
    model = _get_model()
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    # L2 normalise so inner-product == cosine similarity
    faiss.normalize_L2(embeddings)
    return embeddings


def embed_query(text: str) -> np.ndarray:
    """Embed a single query string, returns shape (1, EMBEDDING_DIM)."""
    model = _get_model()
    vec = model.encode([text], convert_to_numpy=True)
    faiss.normalize_L2(vec)
    return vec


def build_index(chunks: list[dict]) -> faiss.Index:
    """
    Create a FAISS inner-product index from chunk texts.
    Also saves both the index and chunks metadata to disk.
    """
    texts = [c["text"] for c in chunks]
    logger.info("Embedding %d chunks...", len(texts))
    embeddings = embed_texts(texts)

    # Inner-product index (with normalised vectors, IP == cosine)
    index = faiss.IndexFlatIP(EMBEDDING_DIM)
    index.add(embeddings)

    # Persist
    save_index(index, chunks)
    logger.info("FAISS index built with %d vectors", index.ntotal)
    return index


def save_index(index: faiss.Index, chunks: list[dict]) -> None:
    """Save FAISS index and chunks metadata to disk."""
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(FAISS_INDEX_PATH))
    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    logger.info("Index saved to %s", FAISS_INDEX_PATH)


def load_index() -> tuple[faiss.Index | None, list[dict] | None]:
    """Load FAISS index and chunks from disk. Returns (None, None) if missing."""
    if not FAISS_INDEX_PATH.exists() or not CHUNKS_PATH.exists():
        return None, None
    try:
        index = faiss.read_index(str(FAISS_INDEX_PATH))
        with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
            chunks = json.load(f)
        logger.info("Loaded existing index with %d vectors", index.ntotal)
        return index, chunks
    except Exception as e:
        logger.error("Failed to load index: %s", e)
        return None, None


def index_exists() -> bool:
    """Check whether a saved index already exists on disk."""
    return FAISS_INDEX_PATH.exists() and CHUNKS_PATH.exists()
