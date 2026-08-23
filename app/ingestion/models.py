from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class DocumentElement(BaseModel):
    """
    Normalized internal representation of an extracted document element.
    Content types: 'text', 'table', 'image', 'chart', 'diagram', 'figure', 'slide', 'mixed'.
    """
    element_id: str
    document_id: str
    document_name: str
    file_type: str  # 'pdf' or 'pptx'
    content_type: str  # 'text', 'table', 'image', 'chart', 'diagram', 'figure', 'slide', 'mixed'
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    section: Optional[str] = None
    subsection: Optional[str] = None
    text: str = ""
    bbox: Optional[List[float]] = None
    image_path: Optional[str] = None
    table_data: Optional[Dict[str, Any]] = None  # {"headers": [...], "rows": [...]}
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """
    Normalized multimodal chunk model prepared for vector embedding and Qdrant indexing.
    """
    chunk_id: str  # e.g., 'DOC001-P12-C03'
    document_id: str
    document_name: str
    content_type: str
    text: str
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    section: Optional[str] = None
    subsection: Optional[str] = None
    source_path: str
    source_status: str = "synthetic"  # 'synthetic' or 'official'
    parent_element_id: Optional[str] = None
    visual_reference: Optional[str] = None
    table_data: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
