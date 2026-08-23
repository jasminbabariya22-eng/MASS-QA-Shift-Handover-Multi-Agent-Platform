import math
import logfire
from typing import List, Dict, Any, Optional, Tuple

from app.config import settings
from app.services.retrieval.base import BaseRetriever
from app.services.retrieval.models import RetrievalCandidate
from app.services.retrieval.dense import DenseRetriever
from app.services.retrieval.bm25 import BM25Retriever
from app.services.retrieval.reranker import FlashRankReranker
from app.services.retrieval.query_router import QueryRouter, QueryType, QueryAnalysisResult


def reciprocal_rank_fusion(
    ranked_lists: List[Tuple[List[RetrievalCandidate], float]],
    rrf_k: int = 60
) -> List[RetrievalCandidate]:
    """
    Computes standard Reciprocal Rank Fusion (RRF) across multiple ranked lists:
    RRF_score(d) = sum_i ( weight_i / (rrf_k + rank_i(d)) )

    Deduplicates strictly by chunk_id and preserves candidate metadata.
    """
    # chunk_id -> { "candidate": RetrievalCandidate, "rrf_score": float, "sources": set() }
    fused: Dict[str, Dict[str, Any]] = {}

    for candidates, weight in ranked_lists:
        for rank_idx, cand in enumerate(candidates, start=1):
            cid = cand.chunk_id
            score_contrib = weight / (rrf_k + rank_idx)

            if cid not in fused:
                cand_copy = cand.model_copy(deep=True)
                fused[cid] = {
                    "candidate": cand_copy,
                    "rrf_score": score_contrib,
                    "sources": {cand.retrieval_source}
                }
            else:
                existing = fused[cid]["candidate"]
                fused[cid]["rrf_score"] += score_contrib
                fused[cid]["sources"].add(cand.retrieval_source)

                # Merge dense and bm25 scores
                if cand.dense_score is not None and existing.dense_score is None:
                    existing.dense_score = cand.dense_score
                if cand.bm25_score is not None and existing.bm25_score is None:
                    existing.bm25_score = cand.bm25_score

    # Construct final fused candidates list
    fused_candidates: List[RetrievalCandidate] = []
    for cid, entry in fused.items():
        cand = entry["candidate"]
        cand.rrf_score = entry["rrf_score"]
        cand.score = entry["rrf_score"]
        sources = entry["sources"]
        if "dense" in sources and "bm25" in sources:
            cand.retrieval_source = "hybrid"
        elif "dense" in sources:
            cand.retrieval_source = "dense"
        elif "bm25" in sources:
            cand.retrieval_source = "bm25"
        else:
            cand.retrieval_source = "hybrid"
        fused_candidates.append(cand)

    fused_candidates.sort(key=lambda c: c.rrf_score or 0.0, reverse=True)
    return fused_candidates


def apply_document_diversity(
    candidates: List[RetrievalCandidate],
    max_per_doc: int = 3,
    top_k: int = 5
) -> List[RetrievalCandidate]:
    """
    Applies document diversity capping for cross-document questions.
    Ensures no single document dominates all top_k slots when multiple sources are relevant.
    """
    doc_counts: Dict[str, int] = {}
    selected: List[RetrievalCandidate] = []
    overflow: List[RetrievalCandidate] = []

    for cand in candidates:
        dname = cand.document_name.lower()
        cnt = doc_counts.get(dname, 0)
        if cnt < max_per_doc:
            doc_counts[dname] = cnt + 1
            selected.append(cand)
            if len(selected) >= top_k:
                break
        else:
            overflow.append(cand)

    # Fill remaining slots from overflow if needed
    if len(selected) < top_k and overflow:
        needed = top_k - len(selected)
        selected.extend(overflow[:needed])

    return selected


class HybridRetriever(BaseRetriever):
    """
    Production Hybrid Retrieval V2 engine combining:
    - Dense Qdrant Vector Retrieval
    - BM25 Lexical Retrieval
    - Reciprocal Rank Fusion (RRF)
    - Deterministic Query Routing
    - Cross-Document Sub-Query Decomposition & Diversity Control
    - FlashRank Semantic Reranking
    """
    def __init__(
        self,
        dense_retriever: Optional[DenseRetriever] = None,
        bm25_retriever: Optional[BM25Retriever] = None,
        reranker: Optional[FlashRankReranker] = None,
        dense_weight: Optional[float] = None,
        bm25_weight: Optional[float] = None,
        rrf_k: Optional[int] = None,
        candidate_k: Optional[int] = None
    ):
        self.dense_retriever = dense_retriever or DenseRetriever()
        self.bm25_retriever = bm25_retriever or BM25Retriever()
        self.reranker = reranker or FlashRankReranker()
        self.dense_weight = dense_weight if dense_weight is not None else settings.HYBRID_DENSE_WEIGHT
        self.bm25_weight = bm25_weight if bm25_weight is not None else settings.HYBRID_BM25_WEIGHT
        self.rrf_k = rrf_k if rrf_k is not None else settings.HYBRID_RRF_K
        self.candidate_k = candidate_k if candidate_k is not None else settings.RETRIEVAL_CANDIDATE_K

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        mode: str = "auto",
        debug: bool = False
    ) -> List[RetrievalCandidate]:
        """
        Main retrieval interface supporting modes: 'auto', 'dense', 'bm25', 'hybrid', 'rrf_only'.
        """
        if not query or not query.strip():
            return []

        # 1. Direct Single-Retriever Modes
        if mode == "dense":
            return self.dense_retriever.retrieve(query, top_k=top_k)

        if mode == "bm25":
            return self.bm25_retriever.retrieve(query, top_k=top_k)

        # 2. Query Routing in Auto Mode
        analysis = QueryRouter.analyze(query) if mode == "auto" else QueryAnalysisResult(
            query=query,
            query_type=QueryType.NORMAL,
            detected_signals=["mode_override"]
        )

        with logfire.span("🚀 Production Hybrid Retrieval V2", query=query, query_type=analysis.query_type.value, mode=mode):
            
            # --- CROSS-DOCUMENT HANDLING ---
            if analysis.query_type == QueryType.CROSS_DOCUMENT and analysis.sub_queries and len(analysis.sub_queries) >= 2:
                logfire.info(f"Cross-document sub-queries: {analysis.sub_queries}")
                sub_reranked_lists: List[List[RetrievalCandidate]] = []

                for sub_q in analysis.sub_queries:
                    dense_cands = self.dense_retriever.retrieve(sub_q, top_k=self.candidate_k)
                    bm25_cands = self.bm25_retriever.retrieve(sub_q, top_k=self.candidate_k)
                    sub_fused = reciprocal_rank_fusion(
                        [(dense_cands, self.dense_weight), (bm25_cands, self.bm25_weight)],
                        rrf_k=self.rrf_k
                    )
                    
                    if mode == "rrf_only":
                        sub_reranked_lists.append(sub_fused[:10])
                    else:
                        sub_pool = sub_fused[:20]
                        sub_ranked = self.reranker.rerank(sub_q, sub_pool, top_k=10)
                        sub_reranked_lists.append(sub_ranked)

                # Interleave and merge candidates from both sides of the comparison
                interleaved: List[RetrievalCandidate] = []
                seen_chunk_ids = set()
                max_sub_len = max(len(sl) for sl in sub_reranked_lists)

                for idx in range(max_sub_len):
                    for sub_list in sub_reranked_lists:
                        if idx < len(sub_list):
                            cand = sub_list[idx]
                            if cand.chunk_id not in seen_chunk_ids:
                                seen_chunk_ids.add(cand.chunk_id)
                                cand.retrieval_source = "cross_document"
                                interleaved.append(cand)

                # Apply document diversity (max 3 chunks per document in top-5)
                final_results = apply_document_diversity(interleaved, max_per_doc=3, top_k=top_k)
                return final_results

            # --- STANDARD & MULTIMODAL PIPELINE ---
            dense_candidates = self.dense_retriever.retrieve(query, top_k=self.candidate_k)
            bm25_candidates = self.bm25_retriever.retrieve(query, top_k=self.candidate_k)

            # Reciprocal Rank Fusion
            fused_candidates = reciprocal_rank_fusion(
                [
                    (dense_candidates, self.dense_weight),
                    (bm25_candidates, self.bm25_weight)
                ],
                rrf_k=self.rrf_k
            )

            if mode == "rrf_only":
                return fused_candidates[:top_k]

            # FlashRank Rerank Candidate Pool (up to 35 candidates)
            candidate_pool = fused_candidates[:35]
            reranked_candidates = self.reranker.rerank(query, candidate_pool, top_k=top_k)

            return reranked_candidates


# Module-level singleton instance & helper function
_global_hybrid_retriever: Optional[HybridRetriever] = None


def get_hybrid_retriever() -> HybridRetriever:
    global _global_hybrid_retriever
    if _global_hybrid_retriever is None:
        _global_hybrid_retriever = HybridRetriever()
    return _global_hybrid_retriever


def retrieve(
    query: str,
    top_k: int = 5,
    mode: str = "auto",
    debug: bool = False
) -> List[RetrievalCandidate]:
    """
    Production-facing single entrypoint for MASS QA Hybrid Retrieval V2.
    """
    retriever = get_hybrid_retriever()
    return retriever.retrieve(query=query, top_k=top_k, mode=mode, debug=debug)
