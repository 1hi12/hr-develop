from abc import ABC, abstractmethod


class IEmbedder(ABC):

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts in batch. Returns list of float vectors."""
        ...

    @abstractmethod
    async def embed_single(self, text: str) -> list[float]:
        """Embed a single text string."""
        ...

    @abstractmethod
    def get_dimension(self) -> int:
        """Return the vector dimension for this embedding model."""
        ...
