from abc import ABC, abstractmethod
from app.core.entities.job import JobDescription


class ILLMRanker(ABC):

    @abstractmethod
    async def rank(
        self,
        job_description: JobDescription,
        cv_ids: list[str],
        job_title: str = "",
    ) -> tuple[list[dict], list[str]]:
        """
        Rank CVs against a job description using an LLM.

        Returns:
            (selected_candidates, thinking_log)
            selected_candidates: list of dicts with cv_id, relevance_score,
                                 similarity_score, explanation.
            thinking_log: human-readable steps for debugging.
        """
        ...
