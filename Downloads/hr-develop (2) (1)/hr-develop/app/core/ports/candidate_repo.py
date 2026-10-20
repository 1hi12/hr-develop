from abc import ABC, abstractmethod
from typing import Optional
from app.core.entities.candidate import Candidate


class ICandidateRepository(ABC):

    @abstractmethod
    async def save(self, candidate: Candidate) -> None:
        """Persist structured candidate data."""
        ...

    @abstractmethod
    async def get_by_id(self, candidate_id: str) -> Optional[Candidate]:
        """Retrieve a candidate by ID. Returns None if not found."""
        ...

    @abstractmethod
    async def delete(self, candidate_id: str) -> None:
        """Delete all structured data for a candidate (GDPR)."""
        ...
