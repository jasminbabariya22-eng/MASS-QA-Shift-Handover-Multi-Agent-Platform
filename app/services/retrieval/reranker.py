import time
import logfire
from typing import List, Optional
from flashrank import Ranker, RerankRequest

from app.services.retrieval.models import RetrievalCandidate

_ranker_instance: Optional[Ranker] = None


def get_flashrank_ranker() -> Ranker:
    global _ranker_instance
    if _ranker_instance is None:
        logfire.info("Initializing FlashRank Cross-Encoder (ms-marco-MiniLM-L-6-v2)...")
        try:
            _ranker_instance = Ranker(model_name="ms-marco-MiniLM-L-6-v2", cache_dir="./data/cache/flashrank")
        except Exception:
            _ranker_instance = Ranker()
    return _ranker_instance


class FlashRankReranker:
    """
    Semantic Cross-Encoder Reranker using FlashRank.
    Reranks a candidate pool of RetrievalCandidates while fully preserving all metadata.
    """
    def __init__(self, ranker: Optional[Ranker] = None):
        self.ranker = ranker or get_flashrank_ranker()

    def rerank(
        self,
        query: str,
        candidates: List[RetrievalCandidate],
        top_k: int = 5
    ) -> List[RetrievalCandidate]:
        """
        Reranks a list of RetrievalCandidate objects against the query.
        Returns top_k re-scored candidates.
        """
        if not candidates:
            return []

        if len(candidates) <= 1:
            return candidates[:top_k]

        with logfire.span("⚖️ FlashRank Reranking", query=query, num_candidates=len(candidates), top_k=top_k):
            start_time = time.time()
            try:
                # Prepare passages for FlashRank with document context
                passages = []
                for idx, cand in enumerate(candidates):
                    # Combine document name, section, table headers, and text to give cross-encoder complete context
                    context_prefix = f"[{cand.document_name}]"
                    if cand.section:
                        context_prefix += f" [{cand.section}]"
                    if cand.table_data and isinstance(cand.table_data, dict):
                        headers = cand.table_data.get("headers", [])
                        if headers:
                            context_prefix += f" [Table: {' | '.join(str(h) for h in headers[:8])}]"
                    passage_text = f"{context_prefix}\n{cand.text}"
                    passages.append({
                        "id": idx,
                        "text": passage_text
                    })

                rerank_request = RerankRequest(query=query, passages=passages)
                reranked_results = self.ranker.rerank(rerank_request)

                # Map back to RetrievalCandidate objects
                reranked_candidates: List[RetrievalCandidate] = []
                for res in reranked_results:
                    orig_idx = res["id"]
                    score = float(res["score"])
                    cand = candidates[orig_idx].model_copy(deep=True)
                    cand.rerank_score = score
                    cand.score = score
                    reranked_candidates.append(cand)

                duration = time.time() - start_time
                top_score = reranked_candidates[0].score if reranked_candidates else 0.0
                logfire.info(f"FlashRank reranking done in {duration:.3f}s. Kept top {min(top_k, len(reranked_candidates))}. Top score: {top_score:.4f}")

                return reranked_candidates[:top_k]

            except Exception as e:
                logfire.error(f"FlashRank reranking failed: {e}. Falling back to pre-rerank order.")
                return candidates[:top_k]
