import logging
from typing import List, Optional
import numpy as np
from sentence_transformers import SentenceTransformer
from app.core.config import settings

logger = logging.getLogger("trip_planner.services.embedding")

_model: Optional[SentenceTransformer] = None


def get_embedding_model() -> SentenceTransformer:
    """
    Lazy-load the sentence-transformers model on first use.
    Keeps application startup fast.
    """
    global _model
    if _model is None:
        logger.info("Loading embedding model: %s", settings.EMBEDDING_MODEL)
        _model = SentenceTransformer(settings.EMBEDDING_MODEL)
        logger.info("Embedding model loaded successfully")
    return _model


def encode_text(text: str) -> List[float]:
    """
    Encode a single text string into a dense vector embedding.

    Args:
        text: Input string to embed.

    Returns:
        List of floats (384-dimensional vector for all-MiniLM-L6-v2).
    """
    model = get_embedding_model()
    embedding = model.encode(text, normalize_embeddings=True)
    if hasattr(embedding, "tolist"):
        return embedding.tolist()
    return list(embedding)


def encode_batch(texts: List[str], batch_size: int = 32) -> List[List[float]]:
    """
    Encode a batch of text strings efficiently.

    Args:
        texts: List of strings to embed.
        batch_size: Batch size for encoding.

    Returns:
        List of float vectors.
    """
    if not texts:
        return []
    model = get_embedding_model()
    embeddings = model.encode(texts, batch_size=batch_size, normalize_embeddings=True)
    results = []
    for e in embeddings:
        if hasattr(e, "tolist"):
            results.append(e.tolist())
        else:
            results.append(list(e))
    return results


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Compute cosine similarity between two normalized vectors.
    Since embeddings are normalized, this is simply the dot product.

    Args:
        vec_a: First vector.
        vec_b: Second vector.

    Returns:
        Cosine similarity score between -1.0 and 1.0 (typically 0.0 to 1.0).
    """
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    dot = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))
