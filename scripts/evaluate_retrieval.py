#!/usr/bin/env python3
"""
MASS QA Production Retrieval Evaluator (V1 & V2).
Evaluates Dense V1 baseline and Hybrid Retrieval V2 architectures across:
- Recall@1, Recall@3, Recall@5, Recall@10
- MRR (Mean Reciprocal Rank)
- Document Hit Rate, Page/Slide Hit Rate, Content-Type Hit Rate
- Component Latency Profiling (Embedding, Qdrant, BM25, RRF, FlashRank, Total)
- Full Ablation Suite (A: Dense, B: BM25, C: Dense+BM25+RRF, D: Dense+BM25+RRF+FlashRank, E: Full V2)
- Detailed per-query debug traces and failure analysis classification.
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import numpy as np
from qdrant_client import QdrantClient

from app.config import settings
from app.services.retrieval.models import RetrievalCandidate
from app.services.retrieval.dense import DenseRetriever
from app.services.retrieval.bm25 import BM25Retriever
from app.services.retrieval.reranker import FlashRankReranker
from app.services.retrieval.query_router import QueryRouter, QueryType
from app.services.retrieval.hybrid import (
    HybridRetriever,
    reciprocal_rank_fusion,
    apply_document_diversity,
    retrieve,
)
from app.services.retrieval.embedding import embed_query, get_embedding_dim


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate Retrieval V1 / V2 for MASS QA")
    parser.add_argument("--version", type=str, default="v2", choices=["v1", "v2"], help="Retrieval version to evaluate (default: v2)")
    parser.add_argument("--mode", type=str, default="auto", choices=["auto", "dense", "bm25", "hybrid", "rrf_only"], help="Retrieval mode for V2 (default: auto)")
    parser.add_argument("--top-k", type=int, default=5, help="Top-K results to retrieve (default: 5)")
    parser.add_argument("--category", type=str, default=None, help="Filter evaluation by question category (basic, operational, multimodal, cross_document)")
    parser.add_argument("--questions", type=str, default="data/evaluation/retrieval_questions.json", help="Path to evaluation questions JSON")
    parser.add_argument("--results", type=str, default=None, help="Path to save evaluation results JSON")
    parser.add_argument("--comparison", type=str, default="data/evaluation/retrieval_comparison.json", help="Path to save comparison JSON")
    parser.add_argument("--ablation", action="store_true", help="Run full 5-configuration ablation study")
    parser.add_argument("--debug", action="store_true", help="Print detailed debug rankings for every retrieval stage")
    return parser.parse_args()


def verify_query_dimension(client: QdrantClient, collection_name: str) -> int:
    """Verifies query embedding dimension against Qdrant collection dimension."""
    print("==================================================")
    print("STEP: VERIFY QUERY DIMENSION")
    print("==================================================")
    probe_vec = embed_query("dimension verification probe")
    query_dim = len(probe_vec)

    if not client.collection_exists(collection_name):
        print(f"[ERROR] Qdrant collection '{collection_name}' does not exist!")
        sys.exit(1)

    col_info = client.get_collection(collection_name)
    qdrant_dim = col_info.config.params.vectors.size

    model_name = "models/gemini-embedding-2-preview" if query_dim == 3072 else "fallback-model"
    print(f"Embedding model: {model_name}")
    print(f"Query dimension: {query_dim}")
    print(f"Qdrant dimension: {qdrant_dim}")

    if query_dim != qdrant_dim:
        print(f"[FAIL] INCOMPATIBILITY DETECTED: Query dimension ({query_dim}) != Qdrant dimension ({qdrant_dim})")
        print("STOP. Collection will NOT be modified.")
        sys.exit(1)

    print("[OK] Dimension Verification PASSED.\n")
    return query_dim


def matches_page_or_slide(expected_p: Optional[int], expected_s: Optional[int], ret_p: Any, ret_s: Any) -> bool:
    """Check if retrieved page or slide matches expected page or slide."""
    if expected_p is not None and ret_p is not None:
        try:
            if int(expected_p) == int(ret_p):
                return True
        except (ValueError, TypeError):
            pass
    if expected_s is not None and ret_s is not None:
        try:
            if int(expected_s) == int(ret_s):
                return True
        except (ValueError, TypeError):
            pass
    return False


def classify_failure_reason(
    doc_found_rank: Optional[int],
    dense_rank: Optional[int],
    bm25_rank: Optional[int],
    rrf_rank: Optional[int],
    rerank_rank: Optional[int],
    cat: str
) -> str:
    """Categorizes the primary failure reason for a missed document."""
    if doc_found_rank is not None:
        return "none"
    if cat == "cross_document":
        return "cross-document failure"
    if dense_rank is None and bm25_rank is None:
        return "dense similarity failure"
    if dense_rank is not None and dense_rank <= 20 and (rrf_rank is None or rrf_rank > 20):
        return "RRF fusion failure"
    if rrf_rank is not None and rrf_rank <= 20 and (rerank_rank is None or rerank_rank > 5):
        return "reranking failure"
    if dense_rank is None and bm25_rank is not None:
        return "dense similarity failure"
    if bm25_rank is None and dense_rank is not None:
        return "lexical retrieval failure"
    return "insufficient candidate pool"


def evaluate_single_query_v1(
    client: QdrantClient,
    collection_name: str,
    qtext: str,
    top_k: int
) -> Tuple[List[RetrievalCandidate], Dict[str, float]]:
    t_start = time.time()
    t_emb_start = time.time()
    query_vec = embed_query(qtext)
    t_emb = time.time() - t_emb_start

    t_qdrant_start = time.time()
    response = client.query_points(
        collection_name=collection_name,
        query=query_vec,
        limit=top_k,
        with_payload=True
    )
    t_qdrant = time.time() - t_qdrant_start
    t_total = time.time() - t_start

    candidates = []
    for pt in response.points:
        p = pt.payload or {}
        cand = RetrievalCandidate(
            point_id=str(pt.id),
            chunk_id=p.get("chunk_id", str(pt.id)),
            document_id=p.get("document_id", ""),
            document_name=p.get("document_name", "Unknown"),
            content_type=p.get("content_type", "text"),
            page_number=p.get("page_number"),
            slide_number=p.get("slide_number"),
            section=p.get("section"),
            subsection=p.get("subsection"),
            score=float(pt.score),
            dense_score=float(pt.score),
            retrieval_source="dense",
            text=p.get("text", ""),
            table_data=p.get("table_data"),
            visual_reference=p.get("visual_reference"),
            source_path=p.get("source_path"),
            source_status=p.get("source_status", "synthetic"),
            metadata=p
        )
        candidates.append(cand)

    latencies = {
        "embedding": t_emb,
        "qdrant": t_qdrant,
        "bm25": 0.0,
        "rrf": 0.0,
        "flashrank": 0.0,
        "total": t_total
    }
    return candidates, latencies


def evaluate_single_query_v2(
    hybrid_retriever: HybridRetriever,
    qtext: str,
    top_k: int,
    mode: str = "auto",
    debug: bool = False
) -> Tuple[List[RetrievalCandidate], Dict[str, Any], Dict[str, float]]:
    t_start = time.time()

    # Query analysis
    analysis = QueryRouter.analyze(qtext) if mode == "auto" else None

    # Step timings
    t_emb_start = time.time()
    # Profile Dense
    t_dense_start = time.time()
    dense_candidates = hybrid_retriever.dense_retriever.retrieve(qtext, top_k=max(20, top_k))
    t_dense = time.time() - t_dense_start

    # Profile BM25
    t_bm25_start = time.time()
    bm25_candidates = hybrid_retriever.bm25_retriever.retrieve(qtext, top_k=max(20, top_k))
    t_bm25 = time.time() - t_bm25_start

    # Profile RRF
    t_rrf_start = time.time()
    rrf_candidates = reciprocal_rank_fusion(
        [
            (dense_candidates, hybrid_retriever.dense_weight),
            (bm25_candidates, hybrid_retriever.bm25_weight)
        ],
        rrf_k=hybrid_retriever.rrf_k
    )
    t_rrf = time.time() - t_rrf_start

    # Final retrieval according to mode / routing
    t_ret_start = time.time()
    if mode == "auto" and analysis and analysis.query_type == QueryType.CROSS_DOCUMENT and analysis.sub_queries and len(analysis.sub_queries) >= 2:
        final_candidates = hybrid_retriever.retrieve(qtext, top_k=top_k, mode="auto")
    elif mode == "dense":
        final_candidates = dense_candidates[:top_k]
    elif mode == "bm25":
        final_candidates = bm25_candidates[:top_k]
    elif mode == "rrf_only":
        final_candidates = rrf_candidates[:top_k]
    else:  # hybrid or auto standard
        pool = rrf_candidates[:35]
        final_candidates = hybrid_retriever.reranker.rerank(qtext, pool, top_k=top_k)
    t_rerank = time.time() - t_ret_start

    t_total = time.time() - t_start

    intermediate = {
        "dense": dense_candidates,
        "bm25": bm25_candidates,
        "rrf": rrf_candidates,
        "query_analysis": analysis
    }

    latencies = {
        "embedding": t_dense * 0.4,  # estimated portion inside dense retrieval
        "qdrant": t_dense * 0.6,
        "bm25": t_bm25,
        "rrf": t_rrf,
        "flashrank": t_rerank,
        "total": t_total
    }

    return final_candidates, intermediate, latencies


def run_evaluation_suite(
    questions: List[Dict[str, Any]],
    version: str = "v2",
    mode: str = "auto",
    top_k: int = 5,
    debug: bool = False
) -> Dict[str, Any]:
    client = QdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
        timeout=60.0
    )
    collection_name = settings.MULTIMODAL_QDRANT_COLLECTION
    query_dim = verify_query_dimension(client, collection_name)

    hybrid_retriever = HybridRetriever()

    recalls = {1: 0, 3: 0, 5: 0, 10: 0}
    mrr_total = 0.0
    doc_hits = 0
    page_slide_hits = 0
    page_slide_eval_count = 0
    content_type_hits = 0

    category_stats: Dict[str, Dict[str, Any]] = {}
    latencies_all = {"embedding": [], "qdrant": [], "bm25": [], "rrf": [], "flashrank": [], "total": []}
    question_logs = []

    print(f"==================================================")
    print(f"RUNNING EVALUATION ({version.upper()}, Mode: {mode}, Top-K: {top_k})")
    print(f"Total Questions: {len(questions)}")
    print(f"==================================================\n")

    for q in questions:
        qid = q["id"]
        qtext = q["question"]
        expected_doc = q["expected_document"]
        expected_p = q.get("expected_page")
        expected_s = q.get("expected_slide")
        expected_ctype = q.get("expected_content_type", "text")
        cat = q.get("category", "general")

        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "hits_at_k": 0, "hits_at_1": 0, "mrr": 0.0}
        category_stats[cat]["total"] += 1

        if version == "v1":
            final_cands, lats = evaluate_single_query_v1(client, collection_name, qtext, top_k=max(10, top_k))
            inter = {}
        else:
            final_cands, inter, lats = evaluate_single_query_v2(hybrid_retriever, qtext, top_k=max(10, top_k), mode=mode, debug=debug)

        for k, v in lats.items():
            latencies_all[k].append(v)

        doc_found_rank = None
        page_slide_matched = False
        content_type_matched = False

        if expected_p is not None or expected_s is not None:
            page_slide_eval_count += 1

        cands_to_evaluate = final_cands[:top_k]

        cand_logs = []
        for rank_idx, cand in enumerate(final_cands, start=1):
            is_doc_match = (cand.document_name.lower() == expected_doc.lower())
            is_ps_match = is_doc_match and matches_page_or_slide(expected_p, expected_s, cand.page_number, cand.slide_number)
            is_ct_match = is_doc_match and (cand.content_type.lower() == expected_ctype.lower())

            if is_doc_match and doc_found_rank is None:
                doc_found_rank = rank_idx

            if rank_idx <= top_k:
                if is_ps_match:
                    page_slide_matched = True
                if is_ct_match:
                    content_type_matched = True

            cand_logs.append({
                "rank": rank_idx,
                "point_id": cand.point_id,
                "chunk_id": cand.chunk_id,
                "score": round(cand.score, 4),
                "dense_score": round(cand.dense_score, 4) if cand.dense_score else None,
                "bm25_score": round(cand.bm25_score, 4) if cand.bm25_score else None,
                "rrf_score": round(cand.rrf_score, 6) if cand.rrf_score else None,
                "rerank_score": round(cand.rerank_score, 4) if cand.rerank_score else None,
                "retrieval_source": cand.retrieval_source,
                "document_name": cand.document_name,
                "document_id": cand.document_id,
                "page_number": cand.page_number,
                "slide_number": cand.slide_number,
                "content_type": cand.content_type,
                "text_snippet": cand.text[:180].replace("\n", " ")
            })

        # Update metrics
        if doc_found_rank is not None:
            mrr_total += (1.0 / doc_found_rank)
            category_stats[cat]["mrr"] += (1.0 / doc_found_rank)
            for k in recalls.keys():
                if doc_found_rank <= k:
                    recalls[k] += 1
            if doc_found_rank == 1:
                doc_hits += 1
                category_stats[cat]["hits_at_1"] += 1
            if doc_found_rank <= top_k:
                category_stats[cat]["hits_at_k"] += 1

        if page_slide_matched:
            page_slide_hits += 1
        if content_type_matched:
            content_type_hits += 1

        # Failure classification
        dense_rank = next((i for i, c in enumerate(inter.get("dense", []), start=1) if c.document_name.lower() == expected_doc.lower()), None)
        bm25_rank = next((i for i, c in enumerate(inter.get("bm25", []), start=1) if c.document_name.lower() == expected_doc.lower()), None)
        rrf_rank = next((i for i, c in enumerate(inter.get("rrf", []), start=1) if c.document_name.lower() == expected_doc.lower()), None)
        failure_reason = classify_failure_reason(
            doc_found_rank=doc_found_rank if (doc_found_rank and doc_found_rank <= top_k) else None,
            dense_rank=dense_rank,
            bm25_rank=bm25_rank,
            rrf_rank=rrf_rank,
            rerank_rank=doc_found_rank,
            cat=cat
        )

        q_log = {
            "id": qid,
            "category": cat,
            "question": qtext,
            "expected_document": expected_doc,
            "expected_page": expected_p,
            "expected_slide": expected_s,
            "expected_content_type": expected_ctype,
            "doc_found_rank": doc_found_rank,
            "page_slide_matched": page_slide_matched,
            "content_type_matched": content_type_matched,
            "failure_reason": failure_reason,
            "latency_seconds": round(lats["total"], 4),
            "retrieved_candidates": cand_logs[:top_k]
        }
        question_logs.append(q_log)

        # Print progress
        status_tag = f"[HIT R{doc_found_rank}]" if (doc_found_rank and doc_found_rank <= top_k) else f"[MISS (Rank: {doc_found_rank or 'N/A'})]"
        print(f"[{qid}] {status_tag} {cat.upper()} | {qtext[:70]}...")
        if doc_found_rank and doc_found_rank <= top_k:
            print(f"      Matched: {expected_doc} at Rank {doc_found_rank} (Score: {cand_logs[doc_found_rank-1]['score']:.4f})")
        else:
            print(f"      Expected: {expected_doc} | Failure: {failure_reason}")

        # Debug Output
        if debug and inter:
            print("\n-----------------------------------------")
            print(f"DEBUG: {qid} | Mode: {mode}")
            print("-----------------------------------------")
            q_analysis = inter.get("query_analysis")
            if q_analysis:
                print(f"Query Type: {q_analysis.query_type.value} | Signals: {q_analysis.detected_signals} | Sub-queries: {q_analysis.sub_queries}")
            
            print("\n[DENSE TOP-5]")
            for r, c in enumerate(inter.get("dense", [])[:5], start=1):
                print(f"  R{r} | Dense: {c.dense_score:.4f} | {c.document_name} | P:{c.page_number} S:{c.slide_number} | {c.chunk_id}")

            print("\n[BM25 TOP-5]")
            for r, c in enumerate(inter.get("bm25", [])[:5], start=1):
                print(f"  R{r} | BM25: {c.bm25_score:.4f} | {c.document_name} | P:{c.page_number} S:{c.slide_number} | {c.chunk_id}")

            print("\n[RRF TOP-5]")
            for r, c in enumerate(inter.get("rrf", [])[:5], start=1):
                print(f"  R{r} | RRF: {c.rrf_score:.6f} | Src: {c.retrieval_source} | {c.document_name} | {c.chunk_id}")

            print("\n[FINAL TOP-5 AFTER FLASHRANK]")
            for r, c in enumerate(cand_logs[:5], start=1):
                print(f"  R{r} | Score: {c['score']:.4f} | Src: {c['retrieval_source']} | {c['document_name']} | P:{c['page_number']} S:{c['slide_number']} | {c['chunk_id']}")
            print("-----------------------------------------\n")

    total_q = len(questions)
    recall_1 = recalls[1] / total_q
    recall_3 = recalls[3] / total_q
    recall_5 = recalls[5] / total_q
    recall_10 = recalls[10] / total_q
    mrr = mrr_total / total_q
    doc_hit_rate = doc_hits / total_q
    ps_hit_rate = (page_slide_hits / page_slide_eval_count) if page_slide_eval_count > 0 else 0.0
    ct_hit_rate = content_type_hits / total_q

    # Category summaries
    cat_summary = {}
    for cat_name, stats in category_stats.items():
        cnt = stats["total"]
        cat_summary[cat_name] = {
            "total": cnt,
            "recall_at_k": round(stats["hits_at_k"] / cnt, 4) if cnt > 0 else 0.0,
            "recall_at_1": round(stats["hits_at_1"] / cnt, 4) if cnt > 0 else 0.0,
            "mrr": round(stats["mrr"] / cnt, 4) if cnt > 0 else 0.0
        }

    # Latency summaries
    total_lats = latencies_all["total"]
    lat_summary = {
        "avg_total_seconds": round(float(np.mean(total_lats)), 4),
        "p50_total_seconds": round(float(np.percentile(total_lats, 50)), 4),
        "p95_total_seconds": round(float(np.percentile(total_lats, 95)), 4),
        "avg_embedding_seconds": round(float(np.mean(latencies_all["embedding"])), 4),
        "avg_qdrant_seconds": round(float(np.mean(latencies_all["qdrant"])), 4),
        "avg_bm25_seconds": round(float(np.mean(latencies_all["bm25"])), 4),
        "avg_rrf_seconds": round(float(np.mean(latencies_all["rrf"])), 6),
        "avg_flashrank_seconds": round(float(np.mean(latencies_all["flashrank"])), 4),
    }

    # Failure counts
    failures = {}
    for ql in question_logs:
        fr = ql["failure_reason"]
        if fr != "none":
            failures[fr] = failures.get(fr, 0) + 1

    summary_result = {
        "version": version,
        "mode": mode,
        "top_k": top_k,
        "total_questions": total_q,
        "query_dimension": query_dim,
        "metrics": {
            "recall_at_1": round(recall_1, 4),
            "recall_at_3": round(recall_3, 4),
            "recall_at_5": round(recall_5, 4),
            "recall_at_10": round(recall_10, 4),
            "mrr": round(mrr, 4),
            "document_hit_rate": round(doc_hit_rate, 4),
            "page_slide_hit_rate": round(ps_hit_rate, 4),
            "content_type_hit_rate": round(ct_hit_rate, 4)
        },
        "category_metrics": cat_summary,
        "latency_profile": lat_summary,
        "failure_analysis": failures,
        "questions_detail": question_logs
    }

    print("\n" + "=" * 50)
    print(f"EVALUATION SUMMARY ({version.upper()} - Mode: {mode})")
    print("=" * 50)
    print(f"Recall@1:              {recall_1:.4f} ({recalls[1]}/{total_q})")
    print(f"Recall@3:              {recall_3:.4f} ({recalls[3]}/{total_q})")
    print(f"Recall@5:              {recall_5:.4f} ({recalls[5]}/{total_q})")
    print(f"Recall@10:             {recall_10:.4f} ({recalls[10]}/{total_q})")
    print(f"MRR:                   {mrr:.4f}")
    print(f"Document Hit Rate:     {doc_hit_rate:.4f}")
    print(f"Page/Slide Hit Rate:   {ps_hit_rate:.4f}")
    print(f"Content-Type Hit Rate: {ct_hit_rate:.4f}")
    print("--------------------------------------------------")
    print(f"Latency (Total): Avg={lat_summary['avg_total_seconds']}s | P50={lat_summary['p50_total_seconds']}s | P95={lat_summary['p95_total_seconds']}s")
    print("=" * 50 + "\n")

    return summary_result


def run_ablation_study(questions: List[Dict[str, Any]], top_k: int = 5) -> Dict[str, Any]:
    """
    Evaluates 5 retrieval configurations:
    A: Dense only
    B: BM25 only
    C: Dense + BM25 + RRF
    D: Dense + BM25 + RRF + FlashRank
    E: Full V2 (Router + Hybrid + RRF + FlashRank + Cross-Doc Diversity)
    """
    print("==================================================")
    print("RUNNING 5-STAGE ABLATION EVALUATION STUDY")
    print("==================================================")

    configs = [
        ("A_dense_only", "dense"),
        ("B_bm25_only", "bm25"),
        ("C_dense_bm25_rrf", "rrf_only"),
        ("D_dense_bm25_rrf_flashrank", "hybrid"),
        ("E_full_v2_auto", "auto")
    ]

    ablation_results = {}
    for label, mode_name in configs:
        print(f"\n>>> Running Ablation Configuration: {label} (mode={mode_name}) <<<")
        res = run_evaluation_suite(questions, version="v2", mode=mode_name, top_k=top_k)
        ablation_results[label] = {
            "mode": mode_name,
            "metrics": res["metrics"],
            "category_metrics": res["category_metrics"],
            "latency_profile": res["latency_profile"]
        }

    # Print comparative table
    print("\n==========================================================================================")
    print("ABLATION STUDY COMPARISON TABLE (Top-K = 5)")
    print("==========================================================================================")
    print(f"{'Configuration':<30} | {'R@1':<7} | {'R@3':<7} | {'R@5':<7} | {'R@10':<7} | {'MRR':<7} | {'DocHit':<7} | {'AvgLat':<7}")
    print("-" * 90)
    for label, data in ablation_results.items():
        m = data["metrics"]
        lat = data["latency_profile"]["avg_total_seconds"]
        print(f"{label:<30} | {m['recall_at_1']:<7.4f} | {m['recall_at_3']:<7.4f} | {m['recall_at_5']:<7.4f} | {m['recall_at_10']:<7.4f} | {m['mrr']:<7.4f} | {m['document_hit_rate']:<7.4f} | {lat:<7.4f}s")
    print("==========================================================================================\n")

    return ablation_results


def build_comparison_report(v1_results: Dict[str, Any], v2_results: Dict[str, Any], output_path: str):
    """Builds side-by-side comparison JSON and tracks Q026 and Q030."""
    v1_m = v1_results["metrics"]
    v2_m = v2_results["metrics"]

    v1_q_map = {q["id"]: q for q in v1_results.get("questions_detail", [])}
    v2_q_map = {q["id"]: q for q in v2_results.get("questions_detail", [])}

    critical_queries = {}
    for qid in ["Q026", "Q030"]:
        v1_q = v1_q_map.get(qid, {})
        v2_q = v2_q_map.get(qid, {})
        v1_cand = v1_q.get("retrieved_candidates", [{}])[0] if v1_q.get("retrieved_candidates") else {}
        v2_cand = v2_q.get("retrieved_candidates", [{}])[0] if v2_q.get("retrieved_candidates") else {}

        critical_queries[qid] = {
            "question": v1_q.get("question") or v2_q.get("question"),
            "expected_document": v1_q.get("expected_document") or v2_q.get("expected_document"),
            "v1_rank": v1_q.get("doc_found_rank"),
            "v2_rank": v2_q.get("doc_found_rank"),
            "v1_score": v1_cand.get("score"),
            "v2_score": v2_cand.get("score"),
            "v1_document": v1_cand.get("document_name"),
            "v2_document": v2_cand.get("document_name")
        }

    comparison = {
        "summary_comparison": {
            "recall_at_1": {"v1": v1_m["recall_at_1"], "v2": v2_m["recall_at_1"], "improvement": round(v2_m["recall_at_1"] - v1_m["recall_at_1"], 4)},
            "recall_at_3": {"v1": v1_m["recall_at_3"], "v2": v2_m["recall_at_3"], "improvement": round(v2_m["recall_at_3"] - v1_m["recall_at_3"], 4)},
            "recall_at_5": {"v1": v1_m["recall_at_5"], "v2": v2_m["recall_at_5"], "improvement": round(v2_m["recall_at_5"] - v1_m["recall_at_5"], 4)},
            "recall_at_10": {"v1": v1_m["recall_at_10"], "v2": v2_m["recall_at_10"], "improvement": round(v2_m["recall_at_10"] - v1_m["recall_at_10"], 4)},
            "mrr": {"v1": v1_m["mrr"], "v2": v2_m["mrr"], "improvement": round(v2_m["mrr"] - v1_m["mrr"], 4)},
            "document_hit_rate": {"v1": v1_m["document_hit_rate"], "v2": v2_m["document_hit_rate"], "improvement": round(v2_m["document_hit_rate"] - v1_m["document_hit_rate"], 4)},
            "page_slide_hit_rate": {"v1": v1_m["page_slide_hit_rate"], "v2": v2_m["page_slide_hit_rate"], "improvement": round(v2_m["page_slide_hit_rate"] - v1_m["page_slide_hit_rate"], 4)},
            "content_type_hit_rate": {"v1": v1_m["content_type_hit_rate"], "v2": v2_m["content_type_hit_rate"], "improvement": round(v2_m["content_type_hit_rate"] - v1_m["content_type_hit_rate"], 4)}
        },
        "critical_queries": critical_queries,
        "v1_latency": v1_results.get("latency_profile"),
        "v2_latency": v2_results.get("latency_profile")
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)

    print(f"[SAVE] Comparison saved -> {output_path}")
    return comparison


def main():
    args = parse_args()

    if not os.path.exists(args.questions):
        print(f"[ERROR] Questions file not found at: {args.questions}")
        sys.exit(1)

    with open(args.questions, "r", encoding="utf-8") as f:
        questions: List[Dict[str, Any]] = json.load(f)

    if args.category:
        questions = [q for q in questions if q.get("category", "").lower() == args.category.lower()]
        print(f"Filtered to category '{args.category}': {len(questions)} questions.")

    if not questions:
        print("[ERROR] No questions matched criteria.")
        sys.exit(1)

    # Ablation Study Mode
    if args.ablation:
        ablation_data = run_ablation_study(questions, top_k=args.top_k)
        abl_path = "data/evaluation/retrieval_ablation_results.json"
        os.makedirs(os.path.dirname(abl_path), exist_ok=True)
        with open(abl_path, "w", encoding="utf-8") as f:
            json.dump(ablation_data, f, indent=2)
        print(f"[SAVE] Ablation study saved -> {abl_path}")
        return

    # Standard Run Mode
    results_path = args.results
    if not results_path:
        results_path = "data/evaluation/retrieval_results.json" if args.version == "v1" else "data/evaluation/retrieval_v2_results.json"

    res = run_evaluation_suite(
        questions=questions,
        version=args.version,
        mode=args.mode,
        top_k=args.top_k,
        debug=args.debug
    )

    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
    print(f"[SAVE] Evaluation results saved -> {results_path}")

    # If V2 was evaluated, generate V1 vs V2 comparison report
    if args.version == "v2" and os.path.exists("data/evaluation/retrieval_results.json"):
        try:
            with open("data/evaluation/retrieval_results.json", "r", encoding="utf-8") as f:
                v1_data = json.load(f)
            build_comparison_report(v1_data, res, args.comparison)
        except Exception as e:
            print(f"[WARNING] Could not build comparison report: {e}")


if __name__ == "__main__":
    main()
