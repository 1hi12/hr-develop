from abc import ABC, abstractmethod
from typing import Any


class ILLMExtractor(ABC):

    @abstractmethod
    async def extract(
        self, cv_text: str
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """
        Extract structured info from raw CV text.

        Returns:
            (general_info, skills_data, seniority_data) — three dicts.
            Each may be empty on failure; callers must handle that.
        """
        ...
