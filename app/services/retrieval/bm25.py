import os
import pickle
import re
import logfire
from typing import List, Dict, Any, Optional

from rank_bm25 import BM25Okapi
from app.config import settings
from app.services.retrieval.base import BaseRetriever
from app.services.retrieval.models import RetrievalCandidate


def tokenize(text: str) -> List[str]:
    """
    Tokenizes text for BM25 lexical search while preserving acronyms,
    alphanumeric IDs, hyphenated terms, and numbers.
    """
    if not text:
        return []
    tokens = re.findall(r"[a-zA-Z0-9_\-\.]+", text.lower())
    cleaned_tokens = [t.strip(".") for t in tokens if len(t.strip(".")) > 0]
    return cleaned_tokens


class BM25Retriever(BaseRetriever):
    """
    Production BM25 lexical retriever operating over local persistent index.
    """
    _cached_index: Optional[Dict[str, Any]] = None

    def __init__(self, index_dir: Optional[str] = None):
        self.index_dir = index_dir or settings.BM25_INDEX_DIR
        self._ensure_index_loaded()

    def _ensure_index_loaded(self):
        """Loads persistent BM25 index lazily or builds if missing."""
        if BM25Retriever._cached_index is not None:
            self.index_data = BM25Retriever._cached_index
            self.bm25_model: BM25Okapi = self.index_data["bm25_model"]
            self.doc_entries: List[Dict[str, Any]] = self.index_data["doc_entries"]
            return

        pkl_path = os.path.join(self.index_dir, "index.pkl")
        if not os.path.exists(pkl_path):
            logfire.info(f"BM25 index not found at {pkl_path}. Building index now...")
            from scripts.build_bm25_index import build_bm25_index
            self.index_data = build_bm25_index(output_dir=self.index_dir)
        else:
            with open(pkl_path, "rb") as f:
                self.index_data = pickle.load(f)

        BM25Retriever._cached_index = self.index_data
        self.bm25_model = self.index_data["bm25_model"]
        self.doc_entries = self.index_data["doc_entries"]
        logfire.info(f"Loaded BM25 index with {len(self.doc_entries)} documents.")

    def retrieve(self, query: str, top_k: int = 20) -> List[RetrievalCandidate]:
        """
        Tokenizes query, computes BM25Okapi scores, and returns Top-K candidates.
        """
        if not query or not query.strip():
            return []

        with logfire.span("📖 BM25 Lexical Retrieval", query=query, top_k=top_k):
            query_tokens = tokenize(query)
            if not query_tokens:
                return []

            scores = self.bm25_model.get_scores(query_tokens)

            # Get top_k indices sorted by descending score
            indexed_scores = [(idx, float(score)) for idx, score in enumerate(scores)]
            indexed_scores.sort(key=lambda x: x[1], reverse=True)
            top_ranked = indexed_scores[:top_k]

            candidates: List[RetrievalCandidate] = []
            max_score = top_ranked[0][1] if top_ranked and top_ranked[0][1] > 0 else 1.0

            for rank_pos, (doc_idx, raw_score) in enumerate(top_ranked):
                entry = self.doc_entries[doc_idx]
                norm_score = raw_score / max_score if max_score > 0 else 0.0

                cand = RetrievalCandidate(
                    point_id=entry["point_id"],
                    chunk_id=entry["chunk_id"],
                    document_id=entry["document_id"],
                    document_name=entry["document_name"],
                    content_type=entry.get("content_type", "text"),
                    page_number=entry.get("page_number"),
                    slide_number=entry.get("slide_number"),
                    section=entry.get("section"),
                    subsection=entry.get("subsection"),
                    score=raw_score,
                    bm25_score=raw_score,
                    retrieval_source="bm25",
                    text=entry.get("text", ""),
                    table_data=entry.get("table_data"),
                    visual_reference=entry.get("visual_reference"),
                    source_path=entry.get("source_path"),
                    source_status=entry.get("source_status", "synthetic"),
                    metadata=entry.get("metadata", {})
                )
                candidates.append(cand)

            logfire.info(f"Retrieved {len(candidates)} BM25 candidates.")
            return candidates
