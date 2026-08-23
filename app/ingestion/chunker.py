import logfire
from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings
from app.ingestion.models import DocumentElement, Chunk


class MultimodalChunker:
    """
    Structure-aware multimodal chunker.
    Keeps tables, images, charts, and diagrams intact as discrete single chunks.
    Splits text elements using RecursiveCharacterTextSplitter with configurable target size & overlap.
    """
    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size * 4,  # ~600 tokens approx 2400 chars
            chunk_overlap=self.chunk_overlap * 4,  # ~80 tokens approx 320 chars
            separators=["\n\n", "\n", ". ", " ", ""]
        )

    def create_chunks(self, elements: List[DocumentElement], source_path: str) -> List[Chunk]:
        chunks: List[Chunk] = []

        with logfire.span("✂️ Multimodal Chunking", total_elements=len(elements)):
            for elem_idx, elem in enumerate(elements):
                # Tables, Images, Charts, Diagrams, Figures are kept intact as single discrete chunks
                if elem.content_type in ("table", "image", "chart", "diagram", "figure"):
                    doc_short = elem.document_id[:8]
                    page_str = f"P{elem.page_number:03d}" if elem.page_number else f"S{elem.slide_number:03d}" if elem.slide_number else "P001"
                    chunk_id = f"{doc_short}-{page_str}-C{elem_idx:03d}"

                    c = Chunk(
                        chunk_id=chunk_id,
                        document_id=elem.document_id,
                        document_name=elem.document_name,
                        content_type=elem.content_type,
                        text=elem.text,
                        page_number=elem.page_number,
                        slide_number=elem.slide_number,
                        section=elem.section,
                        subsection=elem.subsection,
                        source_path=source_path,
                        source_status="synthetic",
                        parent_element_id=elem.element_id,
                        visual_reference=elem.image_path,
                        table_data=elem.table_data,
                        metadata=elem.metadata
                    )
                    chunks.append(c)

                else:
                    # Text elements split using structure-aware text splitter
                    if not elem.text or not elem.text.strip():
                        continue

                    split_texts = self.splitter.split_text(elem.text)
                    for split_idx, text_part in enumerate(split_texts):
                        doc_short = elem.document_id[:8]
                        page_str = f"P{elem.page_number:03d}" if elem.page_number else f"S{elem.slide_number:03d}" if elem.slide_number else "P001"
                        chunk_id = f"{doc_short}-{page_str}-C{elem_idx:03d}-{split_idx:02d}"

                        c = Chunk(
                            chunk_id=chunk_id,
                            document_id=elem.document_id,
                            document_name=elem.document_name,
                            content_type=elem.content_type,
                            text=text_part,
                            page_number=elem.page_number,
                            slide_number=elem.slide_number,
                            section=elem.section,
                            subsection=elem.subsection,
                            source_path=source_path,
                            source_status="synthetic",
                            parent_element_id=elem.element_id,
                            table_data=None,
                            metadata=elem.metadata
                        )
                        chunks.append(c)

            logfire.info(f"✅ Chunking complete: Generated {len(chunks)} multimodal chunks.")
            return chunks
