import json
from typing import List, Tuple, Dict, Any, Optional
import logfire

from app.services.retrieval.models import RetrievalCandidate
from app.services.generation.models import SourceCitation


class ContextBuilder:
    """
    Production Context Builder that converts retrieved candidates into structured,
    provenance-rich prompt contexts and mapped citation objects.
    """

    @staticmethod
    def format_table(table_data: Any, fallback_text: str = "") -> str:
        """
        Formats structured table data into a clean Markdown table representation.
        Preserves header-to-row column relationships.
        """
        if not table_data:
            return fallback_text

        if isinstance(table_data, dict):
            headers = table_data.get("headers", [])
            rows = table_data.get("rows", [])
            caption = table_data.get("caption") or table_data.get("title", "")

            lines = []
            if caption:
                lines.append(f"**Table Caption:** {caption}")

            if headers and isinstance(headers, list):
                header_line = "| " + " | ".join(str(h) for h in headers) + " |"
                sep_line = "| " + " | ".join("---" for _ in headers) + " |"
                lines.append(header_line)
                lines.append(sep_line)

                if rows and isinstance(rows, list):
                    for row in rows:
                        if isinstance(row, list):
                            # Align row length with headers
                            row_cells = [str(cell) for cell in row]
                            while len(row_cells) < len(headers):
                                row_cells.append("")
                            lines.append("| " + " | ".join(row_cells[:len(headers)]) + " |")
                        elif isinstance(row, dict):
                            row_cells = [str(row.get(h, "")) for h in headers]
                            lines.append("| " + " | ".join(row_cells) + " |")
                return "\n".join(lines)
            
            elif rows and isinstance(rows, list):
                # Dict-based rows without explicit header array
                if isinstance(rows[0], dict):
                    keys = list(rows[0].keys())
                    header_line = "| " + " | ".join(keys) + " |"
                    sep_line = "| " + " | ".join("---" for _ in keys) + " |"
                    lines.append(header_line)
                    lines.append(sep_line)
                    for row in rows:
                        lines.append("| " + " | ".join(str(row.get(k, "")) for k in keys) + " |")
                    return "\n".join(lines)

        elif isinstance(table_data, str):
            return table_data.strip()

        return fallback_text

    @staticmethod
    def format_candidate_content(cand: RetrievalCandidate) -> str:
        """
        Renders candidate content according to its modality / content_type.
        """
        ctype = (cand.content_type or "text").lower()

        if ctype == "table":
            table_md = ContextBuilder.format_table(cand.table_data, fallback_text=cand.text)
            if cand.text and cand.text.strip() != table_md.strip():
                return f"{cand.text}\n\n[Structured Table Data]:\n{table_md}"
            return f"[Structured Table Data]:\n{table_md}"

        elif ctype in ("image", "diagram"):
            vis_info = cand.visual_reference or {}
            caption = ""
            if isinstance(vis_info, dict):
                caption = vis_info.get("caption") or vis_info.get("description") or ""
            desc = caption or cand.text
            return f"[Visual / Diagram Description]:\n{desc}"

        elif ctype == "chart":
            vis_info = cand.visual_reference or {}
            desc = ""
            if isinstance(vis_info, dict):
                desc = vis_info.get("chart_summary") or vis_info.get("caption") or ""
            chart_text = desc or cand.text
            return f"[Chart Description & Extracted Trends]:\n{chart_text}"

        elif ctype == "slide":
            return f"[Presentation Slide Content]:\n{cand.text}"

        # Standard text
        return cand.text

    @classmethod
    def build_context(
        cls,
        candidates: List[RetrievalCandidate],
        max_tokens_budget: int = 12000
    ) -> Tuple[str, List[SourceCitation]]:
        """
        Converts a list of RetrievalCandidate objects into a structured prompt context
        with numbered [SOURCE {idx}] headers and extracts matching SourceCitation models.
        """
        if not candidates:
            return "No evidence retrieved from the knowledge base.", []

        context_blocks: List[str] = []
        citations: List[SourceCitation] = []

        total_chars = 0
        # rough char limit corresponding to max token budget
        max_chars = max_tokens_budget * 4

        for idx, cand in enumerate(candidates, start=1):
            doc_label = cand.document_name or "Unknown Document"
            loc_parts = []
            if cand.page_number is not None:
                loc_parts.append(f"Page {cand.page_number}")
            if cand.slide_number is not None:
                loc_parts.append(f"Slide {cand.slide_number}")
            if cand.section:
                loc_parts.append(f"Section: {cand.section}")
            
            loc_str = ", ".join(loc_parts) if loc_parts else "General"
            content_rendered = cls.format_candidate_content(cand)

            header_lines = [
                f"SOURCE [{idx}]",
                f"Document: {doc_label}",
                f"Location: {loc_str}",
                f"Content Type: {cand.content_type or 'text'}"
            ]
            if cand.score:
                header_lines.append(f"Relevance Score: {cand.score:.4f}")

            block = "\n".join(header_lines) + f"\n\nContent:\n{content_rendered}"

            if total_chars + len(block) > max_chars and context_blocks:
                logfire.warning(f"Context truncated at source {idx} to adhere to token limits.")
                break

            context_blocks.append(block)
            total_chars += len(block)

            # Create traceable citation model
            snippet = cand.text[:200].replace("\n", " ").strip() if cand.text else ""
            citation = SourceCitation(
                source_number=idx,
                document_name=cand.document_name,
                document_id=cand.document_id,
                chunk_id=cand.chunk_id,
                page_number=cand.page_number,
                slide_number=cand.slide_number,
                section=cand.section,
                content_type=cand.content_type or "text",
                score=cand.score,
                snippet=snippet
            )
            citations.append(citation)

        full_context = "\n\n" + ("=" * 50) + "\n\n".join([""] + context_blocks) + "\n\n" + ("=" * 50)
        return full_context.strip(), citations
