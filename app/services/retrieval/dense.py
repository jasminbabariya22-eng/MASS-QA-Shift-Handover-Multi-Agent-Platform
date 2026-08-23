import logfire
from typing import List, Optional
from qdrant_client import QdrantClient

from app.config import settings
from app.services.retrieval.base import BaseRetriever
from app.services.retrieval.models import RetrievalCandidate
from app.services.retrieval.embedding import embed_query, get_embedding_dim


class DenseRetriever(BaseRetriever):
    """
    Production dense vector retriever using Google Gemini embeddings and Qdrant Cloud.
    """
    def __init__(self, collection_name: Optional[str] = None, client: Optional[QdrantClient] = None):
        self.collection_name = collection_name or settings.MULTIMODAL_QDRANT_COLLECTION
        self.client = client or QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=60.0
        )
        self.expected_dim = get_embedding_dim()

    def retrieve(self, query: str, top_k: int = 20) -> List[RetrievalCandidate]:
        """
        Embeds the query text and retrieves top_k vector candidates from Qdrant.
        """
        if not query or not query.strip():
            return []

        with logfire.span("🔍 Dense Vector Retrieval", query=query, top_k=top_k, collection=self.collection_name):
            query_vec = embed_query(query)
            if len(query_vec) != self.expected_dim:
                logfire.error(f"Dimension mismatch: expected {self.expected_dim}, got {len(query_vec)}")
                raise ValueError(f"Query vector dimension ({len(query_vec)}) != expected collection dimension ({self.expected_dim})")

            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vec,
                limit=top_k,
                with_payload=True
            )

            candidates: List[RetrievalCandidate] = []
            for point in response.points:
                payload = point.payload or {}
                chunk_id = payload.get("chunk_id", str(point.id))
                doc_name = payload.get("document_name", "Unknown")
                doc_id = payload.get("document_id", "")
                ctype = payload.get("content_type", "text")
                page_num = payload.get("page_number")
                slide_num = payload.get("slide_number")
                section = payload.get("section")
                subsection = payload.get("subsection")
                text = payload.get("text", "")
                table_data = payload.get("table_data")
                visual_ref = payload.get("visual_reference")
                src_path = payload.get("source_path")
                src_status = payload.get("source_status", "synthetic")

                cand = RetrievalCandidate(
                    point_id=str(point.id),
                    chunk_id=chunk_id,
                    document_id=doc_id,
                    document_name=doc_name,
                    content_type=ctype,
                    page_number=page_num,
                    slide_number=slide_num,
                    section=section,
                    subsection=subsection,
                    score=float(point.score),
                    dense_score=float(point.score),
                    retrieval_source="dense",
                    text=text,
                    table_data=table_data,
                    visual_reference=visual_ref,
                    source_path=src_path,
                    source_status=src_status,
                    metadata=payload
                )
                candidates.append(cand)

            logfire.info(f"Retrieved {len(candidates)} dense candidates from '{self.collection_name}'.")
            return candidates
