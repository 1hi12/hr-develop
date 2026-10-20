from abc import ABC, abstractmethod
from app.core.entities.candidate import EmbeddedChunk
from app.core.entities.matching import VectorSearchResult


class IVectorStore(ABC):

    @abstractmethod
    async def store_candidate(
        self,
        candidate_id: str,
        filename: str,
        chunks: list[EmbeddedChunk],
        skills_json: str,
    ) -> None:
        """Persist a candidate's embedded chunks into the vector store."""
        ...

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        top_k: int,
        min_score: float,
    ) -> list[VectorSearchResult]:
        """Vector similarity search. Returns best chunk per candidate."""
        ...

    @abstractmethod
    async def fetch_chunks_by_candidate_ids(
        self, candidate_ids: list[str]
    ) -> list[dict]:
        """Retrieve all chunks for given candidate_ids (for reranking)."""
        ...

    @abstractmethod
    async def delete_candidate(self, candidate_id: str) -> None:
        """Remove all chunks for a candidate (GDPR delete)."""
        ...

    @abstractmethod
    async def candidate_exists(self, candidate_id: str) -> bool:
        """Check whether a candidate has any indexed chunks."""
        ...
