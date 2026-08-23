import uuid
import logfire
from typing import List
from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.config import settings
from app.ingestion.models import Chunk
from app.services.retrieval.embedding import embed_texts, get_embedding_dim


class MultimodalQdrantIndexer:
    """
    Multimodal Qdrant Indexer.
    Embeds chunks and indexes points with rich payload provenance into Qdrant.
    """
    def __init__(self, collection_name: str = None):
        self.collection_name = collection_name or settings.MULTIMODAL_QDRANT_COLLECTION
        self.qdrant_client = QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=60.0
        )

    def prepare_collection(self, wipe: bool = False) -> None:
        """
        Creates or clears the Qdrant collection and builds payload field indexes.
        """
        with logfire.span("Qdrant Collection Setup", collection=self.collection_name):
            if wipe and self.qdrant_client.collection_exists(self.collection_name):
                self.qdrant_client.delete_collection(self.collection_name)
                logfire.info(f"Deleted collection '{self.collection_name}'.")

            if not self.qdrant_client.collection_exists(self.collection_name):
                dim = get_embedding_dim()
                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=dim,
                        distance=models.Distance.COSINE
                    )
                )
                logfire.info(f"Created collection '{self.collection_name}' ({dim}-dim, Cosine).")

                # Create Payload Indexes for fast filtered retrieval
                for field in ["document_id", "content_type", "page_number", "slide_number", "source_status"]:
                    try:
                        schema_type = models.PayloadSchemaType.INTEGER if "number" in field else models.PayloadSchemaType.KEYWORD
                        self.qdrant_client.create_payload_index(
                            collection_name=self.collection_name,
                            field_name=field,
                            field_schema=schema_type
                        )
                    except Exception as e:
                        logfire.warning(f"Payload index creation for {field} failed: {e}")

    def is_document_indexed(self, document_id: str) -> bool:
        """
        Checks if vectors for a given document_id already exist in Qdrant (for idempotent ingestion).
        """
        if not self.qdrant_client.collection_exists(self.collection_name):
            return False

        res = self.qdrant_client.scroll(
            collection_name=self.collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=document_id)
                    )
                ]
            ),
            limit=1
        )
        return len(res[0]) > 0

    def index_chunks(self, chunks: List[Chunk]) -> int:
        """
        Embeds chunk texts and upserts points to Qdrant.
        Returns the count of successfully indexed vectors.
        """
        valid_chunks = [c for c in chunks if c.text and c.text.strip()]
        if not valid_chunks:
            return 0

        with logfire.span("Vectorizing & Indexing Chunks", total_chunks=len(valid_chunks)):
            texts = [c.text for c in valid_chunks]
            embeddings = embed_texts(texts)

            points = []
            for chunk, vector in zip(valid_chunks, embeddings):
                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.chunk_id))
                payload = {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "document_name": chunk.document_name,
                    "content_type": chunk.content_type,
                    "page_number": chunk.page_number,
                    "slide_number": chunk.slide_number,
                    "section": chunk.section,
                    "subsection": chunk.subsection,
                    "source_path": chunk.source_path,
                    "source_status": chunk.source_status,
                    "parent_element_id": chunk.parent_element_id,
                    "visual_reference": chunk.visual_reference,
                    "text": chunk.text,
                    "table_data": chunk.table_data
                }

                points.append(
                    models.PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=payload
                    )
                )

            # Upsert points in smaller batches of 25 with retry for network resilience
            for i in range(0, len(points), 25):
                batch_points = points[i:i + 25]
                for attempt in range(3):
                    try:
                        self.qdrant_client.upsert(
                            collection_name=self.collection_name,
                            points=batch_points
                        )
                        break
                    except Exception as upsert_err:
                        if attempt == 2:
                            logfire.error(f"Qdrant batch upsert failed: {upsert_err}")
                            raise upsert_err
                        import time
                        time.sleep(2)

            logfire.info(f"Indexed {len(points)} points to Qdrant collection '{self.collection_name}'.")
            return len(points)

