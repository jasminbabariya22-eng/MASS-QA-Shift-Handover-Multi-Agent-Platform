import os
import uuid
import logfire
from typing import List, Optional
from PIL import Image

# Disable PyTorch Inductor C++ compilation check on Windows
os.environ["TORCH_INDUCTOR_DISABLE"] = "1"
os.environ["TORCHDYNAMO_DISABLE"] = "1"
try:
    import torch
    torch._dynamo.config.disable = True
    torch._dynamo.config.suppress_errors = True
except Exception:
    pass

from app.config import settings
from app.ingestion.models import DocumentElement
from app.ingestion.parsers.base import DocumentParser
from app.ingestion.vision.analyzer import VisionAnalyzer, GeminiVisionAnalyzer, StubVisionAnalyzer




class DoclingDocumentParser(DocumentParser):
    """
    Docling-based Multimodal Document Parser.
    Extracts text, headings, tables, pictures, charts, diagrams, page and slide boundaries.
    """
    def __init__(self, vision_analyzer: Optional[VisionAnalyzer] = None):
        self.vision_analyzer = vision_analyzer or (
            GeminiVisionAnalyzer() if settings.VISION_ENABLED else StubVisionAnalyzer()
        )
        self.artifact_dir = settings.ARTIFACT_DIR

    def parse_document(
        self,
        file_path: str,
        document_id: str,
        document_name: str
    ) -> List[DocumentElement]:
        with logfire.span("📄 Docling Parsing", file=document_name, doc_id=document_id):
            elements: List[DocumentElement] = []
            ext = document_name.lower().rsplit(".", 1)[-1]
            file_type = "pptx" if ext == "pptx" else "pdf"

            try:
                from docling.document_converter import DocumentConverter, PdfFormatOption
                from docling.datamodel.base_models import InputFormat
                from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice

                pipeline_options = PdfPipelineOptions()
                pipeline_options.do_ocr = False
                pipeline_options.accelerator_options = AcceleratorOptions(
                    num_threads=4,
                    device=AcceleratorDevice.CPU
                )

                converter = DocumentConverter(
                    format_options={
                        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                    }
                )
                conversion_result = converter.convert(file_path)
                doc = conversion_result.document
            except Exception as e:
                logfire.warning(f"Docling conversion failed for {document_name}: {e}. Falling back...")
                raise e

            doc_artifact_path = os.path.join(self.artifact_dir, document_id)
            os.makedirs(doc_artifact_path, exist_ok=True)

            current_section = None
            current_subsection = None

            # Process Docling document nodes
            if hasattr(doc, "texts") and doc.texts:
                for idx, item in enumerate(doc.texts):
                    text_content = item.text.strip() if hasattr(item, "text") and item.text else ""
                    if not text_content:
                        continue

                    label = getattr(item, "label", "text").lower() if hasattr(item, "label") else "text"
                    
                    if "heading" in label or "title" in label:
                        if "1" in label or "title" in label:
                            current_section = text_content
                            current_subsection = None
                        else:
                            current_subsection = text_content

                    page_no = None
                    if hasattr(item, "prov") and item.prov:
                        page_no = getattr(item.prov[0], "page_no", None)

                    elem = DocumentElement(
                        element_id=f"{document_id}-E{idx:04d}",
                        document_id=document_id,
                        document_name=document_name,
                        file_type=file_type,
                        content_type="text",
                        page_number=page_no if file_type == "pdf" else None,
                        slide_number=page_no if file_type == "pptx" else None,
                        section=current_section,
                        subsection=current_subsection,
                        text=text_content,
                        metadata={"label": label}
                    )
                    elements.append(elem)

            # Process Docling Tables
            if hasattr(doc, "tables") and doc.tables:
                for idx, table_item in enumerate(doc.tables):
                    page_no = None
                    if hasattr(table_item, "prov") and table_item.prov:
                        page_no = getattr(table_item.prov[0], "page_no", None)

                    try:
                        df = table_item.export_to_dataframe(doc)
                        headers = [str(c) for c in df.columns]

                        rows = [[str(val) for val in row] for row in df.values]
                        table_dict = {"headers": headers, "rows": rows}

                        # Generate structured semantic representation for table
                        semantic_lines = [f"Table Title/Section: {current_section or 'Data Table'}"]
                        for r in rows[:15]:  # include first 15 rows in semantic text
                            row_str = ", ".join([f"{h}: {val}" for h, val in zip(headers, r)])
                            semantic_lines.append(row_str)
                        semantic_text = "\n".join(semantic_lines)

                    except Exception:
                        semantic_text = "Table data"
                        table_dict = {"headers": [], "rows": []}

                    elem = DocumentElement(
                        element_id=f"{document_id}-TBL{idx:03d}",
                        document_id=document_id,
                        document_name=document_name,
                        file_type=file_type,
                        content_type="table",
                        page_number=page_no if file_type == "pdf" else None,
                        slide_number=page_no if file_type == "pptx" else None,
                        section=current_section,
                        subsection=current_subsection,
                        text=semantic_text,
                        table_data=table_dict,
                        metadata={"is_table": True}
                    )
                    elements.append(elem)

            # Process Docling Pictures / Images / Charts
            if hasattr(doc, "pictures") and doc.pictures:
                for idx, pic_item in enumerate(doc.pictures):
                    page_no = None
                    if hasattr(pic_item, "prov") and pic_item.prov:
                        page_no = getattr(pic_item.prov[0], "page_no", None)

                    img_filename = f"image_p{page_no or 1}_{idx+1}.png"
                    img_dest_path = os.path.join(doc_artifact_path, img_filename)

                    try:
                        if hasattr(pic_item, "get_image"):
                            pil_img = pic_item.get_image(doc)
                            if pil_img:
                                pil_img.save(img_dest_path)
                    except Exception as img_err:
                        logfire.warning(f"Could not save image artifact {img_dest_path}: {img_err}")

                    # Determine visual sub-type (chart, diagram, image)
                    content_type = "image"
                    analysis_res = self.vision_analyzer.analyze_image(img_dest_path)

                    elem = DocumentElement(
                        element_id=f"{document_id}-IMG{idx:03d}",
                        document_id=document_id,
                        document_name=document_name,
                        file_type=file_type,
                        content_type=content_type,
                        page_number=page_no if file_type == "pdf" else None,
                        slide_number=page_no if file_type == "pptx" else None,
                        section=current_section,
                        subsection=current_subsection,
                        text=analysis_res,
                        image_path=img_dest_path if os.path.exists(img_dest_path) else None,
                        metadata={"visual_reference": img_dest_path}
                    )
                    elements.append(elem)

            logfire.info(f"✅ Docling parsed {len(elements)} elements from {document_name}.")
            return elements
