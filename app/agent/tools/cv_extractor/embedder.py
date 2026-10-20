import logging

logger = logging.getLogger(__name__)

# Global variable to cache embedder
_cached_embedder = None


def _get_embedder():
    """Embeddings always go through the Orange LiteLLM proxy (OpenAIEmbedder)."""
    global _cached_embedder
    if _cached_embedder is not None:
        return _cached_embedder

    from app.config.settings import settings
    from app.infrastructure.embeddings.openai_embedder import OpenAIEmbedder
    _cached_embedder = OpenAIEmbedder()
    logger.info("[Embedder] Using Orange LiteLLM proxy for model '%s'", settings.embedding_model)

    return _cached_embedder


def get_model():
    """For backward compatibility - returns the embedder."""
    return _get_embedder()

_get_model = get_model


async def embed_single_query(query: str) -> list[float]:
    """Embed une query (job description)."""
    embedder = _get_embedder()
    return await embedder.embed_single(query, is_query=True)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed une liste de passages CV."""
    embedder = _get_embedder()
    return await embedder.embed_texts(texts)


def get_embedding_dimension() -> int:
    """Get embedding dimension from settings."""
    from app.config.settings import settings
    return settings.embedding_dim
