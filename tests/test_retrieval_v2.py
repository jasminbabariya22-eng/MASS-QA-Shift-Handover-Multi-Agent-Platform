import pytest
from app.services.retrieval.models import RetrievalCandidate
from app.services.retrieval.query_router import QueryRouter, QueryType
from app.services.retrieval.hybrid import reciprocal_rank_fusion, apply_document_diversity
from app.services.retrieval.bm25 import BM25Retriever, tokenize
from app.services.retrieval.reranker import FlashRankReranker


def make_candidate(chunk_id: str, doc_name: str, score: float = 0.5, source: str = "dense", ctype: str = "text") -> RetrievalCandidate:
    return RetrievalCandidate(
        point_id=f"pt-{chunk_id}",
        chunk_id=chunk_id,
        document_id="DOC-12345",
        document_name=doc_name,
        content_type=ctype,
        page_number=1,
        slide_number=None,
        section="Overview",
        subsection="Summary",
        score=score,
        retrieval_source=source,
        text=f"Sample text content for {chunk_id} in {doc_name}",
        metadata={"custom_key": f"val-{chunk_id}"}
    )


# 1. Test RRF Calculation
def test_rrf_calculation():
    list1 = [make_candidate("c1", "docA", score=0.9), make_candidate("c2", "docA", score=0.8)]
    list2 = [make_candidate("c2", "docA", score=0.95), make_candidate("c3", "docB", score=0.7)]

    # c2 is rank 2 in list1 (score: 1/(60+2)) and rank 1 in list2 (score: 1/(60+1))
    fused = reciprocal_rank_fusion([(list1, 1.0), (list2, 1.0)], rrf_k=60)
    assert len(fused) == 3
    assert fused[0].chunk_id == "c2"  # Combined ranks should put c2 at top
    expected_c2_score = (1.0 / 62) + (1.0 / 61)
    assert pytest.approx(fused[0].rrf_score, 0.0001) == expected_c2_score


# 2. Test Duplicate Candidate Merging
def test_duplicate_candidate_merging():
    cand1 = make_candidate("c100", "docA", score=0.9, source="dense")
    cand1.dense_score = 0.9
    cand2 = make_candidate("c100", "docA", score=0.8, source="bm25")
    cand2.bm25_score = 0.8

    fused = reciprocal_rank_fusion([([cand1], 1.0), ([cand2], 1.0)], rrf_k=60)
    assert len(fused) == 1
    merged = fused[0]
    assert merged.chunk_id == "c100"
    assert merged.retrieval_source == "hybrid"
    assert merged.dense_score == 0.9
    assert merged.bm25_score == 0.8


# 3. Test BM25 Tokenizer & Retrieval
def test_bm25_tokenization():
    tokens = tokenize("PNGRB 2018 targets for NSPS-OOOO and U.S. EPA!")
    assert "pngrb" in tokens
    assert "2018" in tokens
    assert "targets" in tokens
    assert "nsps-oooo" in tokens or "nsps" in tokens
    assert "epa" in tokens


def test_bm25_retrieval_smoke():
    bm25 = BM25Retriever()
    results = bm25.retrieve("petroleum refining cooling towers", top_k=5)
    assert len(results) > 0
    assert all(isinstance(c, RetrievalCandidate) for c in results)
    assert results[0].retrieval_source == "bm25"


# 4. Test Dense Retrieval (interface & model structure)
def test_dense_retrieval_structure():
    c = make_candidate("dense-1", "test.pdf", score=0.88, source="dense")
    assert c.point_id == "pt-dense-1"
    assert c.dense_score is None  # initially None unless set
    assert c.retrieval_source == "dense"


# 5. Test Hybrid Retrieval Fusion
def test_hybrid_fusion():
    dense_list = [make_candidate("c1", "doc1", 0.9), make_candidate("c2", "doc2", 0.8)]
    bm25_list = [make_candidate("c3", "doc3", 0.85), make_candidate("c1", "doc1", 0.7)]
    fused = reciprocal_rank_fusion([(dense_list, 1.0), (bm25_list, 1.0)], rrf_k=60)
    assert len(fused) == 3
    assert fused[0].chunk_id == "c1"  # Present in both


# 6. Test Reranking Metadata Preservation
def test_reranking_metadata_preservation():
    reranker = FlashRankReranker()
    cands = [
        make_candidate("c1", "5.1_petroleum_refining.pdf", score=0.5),
        make_candidate("c2", "IEA INTERNATIONAL ENERGY AGENCY.pdf", score=0.6)
    ]
    cands[0].table_data = {"headers": ["A"], "rows": [["1"]]}
    cands[0].page_number = 3

    reranked = reranker.rerank("cooling towers and petroleum refining", cands, top_k=2)
    assert len(reranked) == 2
    assert reranked[0].table_data is not None or reranked[1].table_data is not None
    assert reranked[0].rerank_score is not None


# 7. Test Query Classification
def test_query_classification():
    # Cross-document
    q_cross = QueryRouter.analyze("How do Indian energy sector expansion plans in PNGRB overview compare with National Electricity Plan 2018 targets?")
    assert q_cross.query_type == QueryType.CROSS_DOCUMENT
    assert len(q_cross.sub_queries) >= 2

    # Multimodal
    q_multi = QueryRouter.analyze("What investment figures are pledged in the Indian energy sector table?")
    assert q_multi.query_type == QueryType.MULTIMODAL

    # Normal
    q_normal = QueryRouter.analyze("What are the primary auxiliary refinery processes including cooling towers?")
    assert q_normal.query_type == QueryType.NORMAL


# 8. Test Cross-Document Sub-Query Decomposition
def test_cross_document_sub_queries():
    res = QueryRouter.analyze("Compare PNGRB targets with NEP 2018 targets.")
    assert res.query_type == QueryType.CROSS_DOCUMENT
    assert len(res.sub_queries) == 2
    assert "pngrb" in res.sub_queries[0].lower() or "pngrb" in res.sub_queries[1].lower()


# 9. Test Document Diversity
def test_document_diversity():
    cands = [
        make_candidate("c1", "DocA"),
        make_candidate("c2", "DocA"),
        make_candidate("c3", "DocA"),
        make_candidate("c4", "DocA"),  # 4th from DocA
        make_candidate("c5", "DocB"),
        make_candidate("c6", "DocB"),
    ]
    diverse = apply_document_diversity(cands, max_per_doc=3, top_k=5)
    doc_counts = {}
    for c in diverse:
        doc_counts[c.document_name] = doc_counts.get(c.document_name, 0) + 1

    assert doc_counts["DocA"] <= 3
    assert len(diverse) == 5
    assert "DocB" in doc_counts


# 10. Test Full Metadata Preservation
def test_metadata_preservation():
    cand = make_candidate("meta-1", "doc.pdf", score=0.95)
    cand.visual_reference = "artifacts/DOC-1/image_1.png"
    cand.table_data = {"headers": ["H1", "H2"], "rows": [["R1", "R2"]]}
    cand.metadata = {"original_label": "table"}

    assert cand.visual_reference == "artifacts/DOC-1/image_1.png"
    assert cand.table_data["headers"] == ["H1", "H2"]
    assert cand.metadata["original_label"] == "table"
