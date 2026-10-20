import logging
import os
import ssl
import warnings

import httpx
from openai import AsyncOpenAI

from app.config.settings import settings
from app.core.ports.embedder import IEmbedder

logger = logging.getLogger(__name__)

# SSL override for corporate / proxy network (same as LLM clients)
os.environ["PYTHONHTTPSVERIFY"]  = "0"
os.environ["REQUESTS_CA_BUNDLE"] = ""
os.environ["SSL_CERT_FILE"]      = ""
warnings.filterwarnings("ignore")
ssl._create_default_https_context = ssl._create_unverified_context  # type: ignore[attr-defined]
ssl.create_default_context = lambda *a, **kw: ssl._create_unverified_context(*a, **kw)  # type: ignore[attr-defined]


class OpenAIEmbedder(IEmbedder):
    """Embeds texts via text-embedding-3-large through the LiteLLM proxy."""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.litellm_api_key,
            base_url=settings.litellm_base_url,
            http_client=httpx.AsyncClient(verify=False),
        )
        self._model = settings.embedding_model
        self._dim   = settings.embedding_dim
        logger.info("[OpenAIEmbedder] model=%s  dim=%d", self._model, self._dim)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        all_embeddings: list[list[float]] = []
        batch_size = settings.embedding_batch_size
        for i in range(0, len(texts), batch_size):
            batch    = texts[i : i + batch_size]
            response = await self._client.embeddings.create(
                model=self._model,
                input=batch,
            )
            # API guarantees same order, but sort by index to be safe
            ordered = sorted(response.data, key=lambda x: x.index)
            all_embeddings.extend(item.embedding for item in ordered)
        return all_embeddings

    async def embed_single(self, text: str, is_query: bool = False) -> list[float]:
        response = await self._client.embeddings.create(
            model=self._model,
            input=[text],
        )
        return response.data[0].embedding

    def get_dimension(self) -> int:
        return self._dim
