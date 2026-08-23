from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class RetrievalCandidate(BaseModel):
    """
    Standardized candidate representation across all retrievers and rerankers.
    """
    point_id: str
    chunk_id: str
    document_id: str
    document_name: str
    content_type: str = "text"  # 'text', 'table', 'image', 'chart', 'diagram', 'slide'
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    section: Optional[str] = None
    subsection: Optional[str] = None
    score: float = 0.0
    retrieval_source: str = "dense"  # 'dense', 'bm25', 'hybrid', 'cross_document'
    dense_score: Optional[float] = None
    bm25_score: Optional[float] = None
    rrf_score: Optional[float] = None
    rerank_score: Optional[float] = None
    text: str = ""
    table_data: Optional[Dict[str, Any]] = None
    visual_reference: Optional[Any] = None
    source_path: Optional[str] = None
    source_status: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
