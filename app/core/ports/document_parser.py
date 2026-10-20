from abc import ABC, abstractmethod


class IDocumentParser(ABC):

    @abstractmethod
    def parse(self, file_bytes: bytes, filename: str) -> str:
        """Parse file bytes into raw text. Raises ValueError for unsupported/empty files."""
        ...
