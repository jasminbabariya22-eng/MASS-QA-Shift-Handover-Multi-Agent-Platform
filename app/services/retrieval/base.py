from abc import ABC, abstractmethod
from typing import List
from app.services.retrieval.models import RetrievalCandidate


class BaseRetriever(ABC):
    """
    Abstract base retriever interface.
    """
    @abstractmethod
    def retrieve(self, query: str, top_k: int = 20) -> List[RetrievalCandidate]:
        """
        Retrieves top_k candidates for a given query string.
        """
        pass
