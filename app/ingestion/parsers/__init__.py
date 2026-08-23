from .base import DocumentParser
from .docling_parser import DoclingDocumentParser
from .fallback_parser import FallbackDocumentParser

__all__ = ["DocumentParser", "DoclingDocumentParser", "FallbackDocumentParser"]
