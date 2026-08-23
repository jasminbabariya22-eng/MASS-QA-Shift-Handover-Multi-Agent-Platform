import os
from app.ingestion.hash_utils import compute_file_hash

from app.ingestion.models import DocumentElement, Chunk
from app.ingestion.chunker import MultimodalChunker
from app.ingestion.parsers import FallbackDocumentParser, DoclingDocumentParser
from app.ingestion.vision.analyzer import StubVisionAnalyzer


def test_document_hashing():
    """Verify deterministic SHA-256 hash generation."""
    sample_path = "DATA/noisy_data/5.1_petroleum_refining.pdf"
    if os.path.exists(sample_path):
        h1 = compute_file_hash(sample_path)
        h2 = compute_file_hash(sample_path)
        assert h1 == h2
        assert len(h1) == 64


def test_multimodal_models():
    """Verify DocumentElement and Chunk schema validation."""
    elem = DocumentElement(
        element_id="DOC1-E001",
        document_id="DOC1",
        document_name="test.pdf",
        file_type="pdf",
        content_type="text",
        page_number=1,
        text="Sample petroleum refining text"
    )
    assert elem.content_type == "text"
    assert elem.page_number == 1

    chunk = Chunk(
        chunk_id="DOC1-P001-C001",
        document_id="DOC1",
        document_name="test.pdf",
        content_type="table",
        text="Table text summary",
        page_number=1,
        source_path="DATA/noisy_data/test.pdf",
        table_data={"headers": ["Year", "Cost"], "rows": [["2023", "500"]]}
    )
    assert chunk.content_type == "table"
    assert chunk.table_data["headers"] == ["Year", "Cost"]


def test_chunker_structure_preservation():
    """Verify structure-aware chunking keeps tables and visual elements intact."""
    chunker = MultimodalChunker(chunk_size=100, chunk_overlap=20)
    elements = [
        DocumentElement(
            element_id="E1",
            document_id="DOC1",
            document_name="refining.pdf",
            file_type="pdf",
            content_type="text",
            page_number=1,
            text="Header text paragraph for petroleum refining overview."
        ),
        DocumentElement(
            element_id="E2",
            document_id="DOC1",
            document_name="refining.pdf",
            file_type="pdf",
            content_type="table",
            page_number=1,
            text="Refinery Yield Table: Gasoline 45%, Diesel 30%, Jet Fuel 15%.",
            table_data={"headers": ["Product", "Yield"], "rows": [["Gasoline", "45%"]]}
        ),
        DocumentElement(
            element_id="E3",
            document_id="DOC1",
            document_name="refining.pdf",
            file_type="pdf",
            content_type="diagram",
            page_number=2,
            text="Crude Distillation Unit Flowchart showing atmospheric tower and vacuum column."
        )
    ]

    chunks = chunker.create_chunks(elements, "DATA/noisy_data/refining.pdf")
    assert len(chunks) == 3
    # Verify table element remained intact as discrete chunk
    tbl_chunk = [c for c in chunks if c.content_type == "table"][0]
    assert tbl_chunk.table_data is not None
    assert tbl_chunk.page_number == 1

    # Verify diagram element remained intact
    diag_chunk = [c for c in chunks if c.content_type == "diagram"][0]
    assert diag_chunk.page_number == 2


def test_fallback_pdf_pptx_parsing():
    """Verify FallbackDocumentParser on PDF and PPTX files."""
    parser = FallbackDocumentParser(vision_analyzer=StubVisionAnalyzer())
    
    pdf_path = "DATA/noisy_data/5.1_petroleum_refining.pdf"
    if os.path.exists(pdf_path):
        elements = parser.parse_document(pdf_path, "DOC-PDF-TEST", "5.1_petroleum_refining.pdf")
        assert len(elements) > 0
        assert any(e.page_number is not None for e in elements)

    pptx_path = "DATA/noisy_data/Oil and Natural Gas Sector.pptx"
    if os.path.exists(pptx_path):
        pptx_elements = parser.parse_document(pptx_path, "DOC-PPTX-TEST", "Oil and Natural Gas Sector.pptx")
        assert len(pptx_elements) > 0
        assert any(e.slide_number is not None for e in pptx_elements)


def test_fastapi_app_import():
    """Verify FastAPI application imports successfully without side effects."""
    from app.main import app
    assert app is not None
