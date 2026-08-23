from abc import ABC, abstractmethod
from typing import List
from app.ingestion.models import DocumentElement


class DocumentParser(ABC):
    """
    Abstract Document Parser interface.
    Extracts text, headings, tables, images, charts, and diagrams into a normalized list of DocumentElement objects.
    """
    @abstractmethod
    def parse_document(
        self,
        file_path: str,
        document_id: str,
        document_name: str
    ) -> List[DocumentElement]:
        """
        Parses a PDF or PPTX document and returns structured DocumentElement items.
        """
        pass
