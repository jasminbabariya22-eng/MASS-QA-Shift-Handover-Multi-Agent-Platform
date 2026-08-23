from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SourceCitation(BaseModel):
    """
    Structured citation reference with full provenance from retrieved evidence.
    """
    source_number: int = Field(..., description="1-indexed source number referenced in text")
    document_name: str = Field(..., description="Target document file name")
    document_id: Optional[str] = Field(None, description="Document unique identifier")
    chunk_id: Optional[str] = Field(None, description="Chunk unique identifier")
    page_number: Optional[int] = Field(None, description="Page number if applicable")
    slide_number: Optional[int] = Field(None, description="Slide number if applicable")
    section: Optional[str] = Field(None, description="Document section header")
    content_type: str = Field("text", description="Modality type (text, table, slide, image, chart)")
    score: Optional[float] = Field(None, description="Rerank or retrieval score")
    snippet: Optional[str] = Field(None, description="Brief snippet of referenced content")


class RAGResponse(BaseModel):
    """
    Standard production response model for RAG question answering.
    """
    question: str = Field(..., description="User input question")
    answer: str = Field(..., description="Synthesized grounded answer")
    sources: List[SourceCitation] = Field(default_factory=list, description="Traceable source citations")
    query_type: str = Field("normal", description="Query routing classification (normal, multimodal, cross_document, out_of_domain)")
    retrieval_count: int = Field(0, description="Total candidate passages retrieved and evaluated")
    grounded: bool = Field(True, description="Whether answer is grounded in retrieved knowledge base")
    confidence: str = Field("high", description="Confidence level: high, medium, low, insufficient, refused")
    thought_process: Optional[List[str]] = Field(default_factory=list, description="Reasoning / pipeline step logs for telemetry")
    latency_breakdown: Optional[Dict[str, float]] = Field(default_factory=dict, description="Latency per pipeline stage in seconds")
    status: str = Field("success", description="Execution status message")
