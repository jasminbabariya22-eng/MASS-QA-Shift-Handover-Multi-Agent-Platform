#!/usr/bin/env python
"""
Phase 2 — MASS QA Production RAG Answer Generation Benchmark Suite.
Evaluates 50 questions across 6 categories:
  - 10 Basic Factual
  - 10 Operational Process
  - 10 Multimodal (Tables, Visuals, Charts)
  - 10 Cross-Document Comparative
  - 5 Troubleshooting
  - 5 Out-of-Domain / Refusal
"""
import sys
import os
import json
import time
import argparse
from typing import List, Dict, Any, Optional

# Ensure UTF-8 console output for Windows cp1252 compatibility
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv()

from app.guardrails import initialize_rails, guard
from app.services.generation import answer_query, RAGResponse


def evaluate_generation_suite(
    dataset_path: str = "data/evaluation/generation_questions.json",
    output_path: str = "data/evaluation/generation_results.json",
    top_k: int = 5,
    category_filter: Optional[str] = None
) -> Dict[str, Any]:
    print("=" * 60)
    print("MASS QA PHASE 2 — PRODUCTION RAG ANSWER GENERATION BENCHMARK")
    print("=" * 60)

    # Initialize guardrails
    initialize_rails()

    # Load dataset
    with open(dataset_path, "r", encoding="utf-8") as f:
        questions: List[Dict[str, Any]] = json.load(f)

    if category_filter:
        questions = [q for q in questions if q.get("category") == category_filter]
        print(f"Filtered to category '{category_filter}': {len(questions)} questions.")

    print(f"Total Questions to Evaluate: {len(questions)}\n")

    results_list = []
    category_stats: Dict[str, Dict[str, Any]] = {}
    latencies_all: Dict[str, List[float]] = {
        "routing": [],
        "retrieval": [],
        "context_building": [],
        "llm_generation": [],
        "total": []
    }

    total_grounded = 0
    total_citations_correct = 0
    total_refusals_correct = 0
    total_refusals_expected = 0
    total_non_refusal_evaluated = 0

    for idx, item in enumerate(questions, start=1):
        qid = item["id"]
        qtext = item["question"]
        cat = item.get("category", "general")
        expected_doc = item.get("expected_document")
        expected_page = item.get("expected_page")
        key_facts = item.get("key_grounding_facts", [])
        should_refuse = item.get("should_refuse", False)

        if cat not in category_stats:
            category_stats[cat] = {
                "total": 0,
                "grounded_count": 0,
                "citation_match_count": 0,
                "refusal_correct_count": 0,
                "latencies": []
            }
        category_stats[cat]["total"] += 1

        t_start = time.time()

        # Step 1: Guardrails check
        rail_fired, rail_response = guard(qtext)

        if should_refuse:
            total_refusals_expected += 1
            if rail_fired or "cannot help" in (rail_response or "").lower() or "knowledge base" in (rail_response or "").lower():
                refusal_ok = True
                total_refusals_correct += 1
                category_stats[cat]["refusal_correct_count"] += 1
            else:
                refusal_ok = False

            t_total = time.time() - t_start
            latencies_all["total"].append(t_total)
            category_stats[cat]["latencies"].append(t_total)

            print(f"[{qid}] [REFUSAL: {'PASS' if refusal_ok else 'FAIL'}] {cat.upper()} | {qtext[:65]}...", flush=True)
            results_list.append({
                "id": qid,
                "category": cat,
                "question": qtext,
                "should_refuse": True,
                "refusal_passed": refusal_ok,
                "rail_fired": rail_fired,
                "answer": rail_response,
                "latency_total": round(t_total, 4)
            })
            continue

        # Step 2: RAG Answer Generation
        total_non_refusal_evaluated += 1
        rag_resp: RAGResponse = answer_query(qtext, top_k=top_k)
        t_total = rag_resp.latency_breakdown.get("total", time.time() - t_start)

        for k in latencies_all.keys():
            if k in rag_resp.latency_breakdown:
                latencies_all[k].append(rag_resp.latency_breakdown[k])
        category_stats[cat]["latencies"].append(t_total)

        # Groundedness Check (no hallucination / key facts presence)
        answer_lower = rag_resp.answer.lower()
        matched_facts = [fact for fact in key_facts if fact.lower() in answer_lower]
        is_grounded = (len(matched_facts) >= max(1, len(key_facts) // 2)) if key_facts else rag_resp.grounded
        if is_grounded:
            total_grounded += 1
            category_stats[cat]["grounded_count"] += 1

        # Citation Correctness Check
        cited_docs = [s.document_name.lower() for s in rag_resp.sources if s.document_name]
        is_citation_correct = False
        if expected_doc:
            is_citation_correct = any(expected_doc.lower() in d or d in expected_doc.lower() for d in cited_docs)
        else:
            is_citation_correct = (len(rag_resp.sources) > 0)

        if is_citation_correct:
            total_citations_correct += 1
            category_stats[cat]["citation_match_count"] += 1

        status_tag = "PASS" if (is_grounded and is_citation_correct) else "PARTIAL"
        print(f"[{qid}] [{status_tag}] {cat.upper()} | {qtext[:65]}...", flush=True)
        print(f"      Grounded: {is_grounded} ({len(matched_facts)}/{len(key_facts)} facts) | Citation Correct: {is_citation_correct} | Sources: {len(rag_resp.sources)} | Latency: {t_total:.3f}s", flush=True)

        results_list.append({
            "id": qid,
            "category": cat,
            "question": qtext,
            "answer": rag_resp.answer,
            "sources": [s.model_dump() for s in rag_resp.sources],
            "query_type": rag_resp.query_type,
            "confidence": rag_resp.confidence,
            "grounded": is_grounded,
            "citation_correct": is_citation_correct,
            "matched_facts": matched_facts,
            "latencies": rag_resp.latency_breakdown
        })
        time.sleep(2.0)

    # Summary Metrics Calculation
    overall_groundedness_rate = total_grounded / total_non_refusal_evaluated if total_non_refusal_evaluated else 1.0
    overall_citation_rate = total_citations_correct / total_non_refusal_evaluated if total_non_refusal_evaluated else 1.0
    overall_refusal_accuracy = total_refusals_correct / total_refusals_expected if total_refusals_expected else 1.0

    totals = latencies_all["total"]
    totals_sorted = sorted(totals) if totals else [0.0]
    p50_idx = int(len(totals_sorted) * 0.5)
    p95_idx = int(len(totals_sorted) * 0.95)

    avg_total_lat = sum(totals) / len(totals) if totals else 0.0
    p50_total_lat = totals_sorted[p50_idx]
    p95_total_lat = totals_sorted[min(p95_idx, len(totals_sorted) - 1)]

    avg_llm_lat = sum(latencies_all["llm_generation"]) / len(latencies_all["llm_generation"]) if latencies_all["llm_generation"] else 0.0
    avg_ret_lat = sum(latencies_all["retrieval"]) / len(latencies_all["retrieval"]) if latencies_all["retrieval"] else 0.0

    print("\n" + "=" * 60)
    print("PHASE 2 GENERATION BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Total Evaluated:              {len(questions)}")
    print(f"Groundedness Rate:            {overall_groundedness_rate:.4f} ({total_grounded}/{total_non_refusal_evaluated})")
    print(f"Citation Correctness Rate:    {overall_citation_rate:.4f} ({total_citations_correct}/{total_non_refusal_evaluated})")
    print(f"Refusal / Guardrail Accuracy: {overall_refusal_accuracy:.4f} ({total_refusals_correct}/{total_refusals_expected})")
    print("-" * 60)
    print(f"Latency (Total): Avg={avg_total_lat:.4f}s | P50={p50_total_lat:.4f}s | P95={p95_total_lat:.4f}s")
    print(f"Latency (Retrieval V2 Avg):   {avg_ret_lat:.4f}s")
    print(f"Latency (LLM Generation Avg): {avg_llm_lat:.4f}s")
    print("=" * 60 + "\n")

    print(f"{'Category':<25} | {'Count':<5} | {'Grounded':<8} | {'Citation':<8} | {'Avg Latency'}")
    print("-" * 65)
    for cat, data in category_stats.items():
        cnt = data["total"]
        g_rate = (data["grounded_count"] / cnt) if cnt else 0.0
        c_rate = (data["citation_match_count"] / cnt) if cnt else 0.0
        avg_l = sum(data["latencies"]) / len(data["latencies"]) if data["latencies"] else 0.0
        if cat == "out_of_domain":
            ref_rate = data["refusal_correct_count"] / cnt if cnt else 0.0
            print(f"{cat:<25} | {cnt:<5} | {'Refusal: ' + str(round(ref_rate, 2)):<18} | {avg_l:.3f} s")
        else:
            print(f"{cat:<25} | {cnt:<5} | {g_rate:<8.2f} | {c_rate:<8.2f} | {avg_l:.3f} s")
    print("=" * 65 + "\n")

    final_report = {
        "summary": {
            "total_questions": len(questions),
            "groundedness_rate": round(overall_groundedness_rate, 4),
            "citation_correctness_rate": round(overall_citation_rate, 4),
            "refusal_accuracy": round(overall_refusal_accuracy, 4),
            "latency": {
                "avg_total_s": round(avg_total_lat, 4),
                "p50_total_s": round(p50_total_lat, 4),
                "p95_total_s": round(p95_total_lat, 4),
                "avg_retrieval_s": round(avg_ret_lat, 4),
                "avg_llm_s": round(avg_llm_lat, 4)
            }
        },
        "category_breakdown": category_stats,
        "detailed_results": results_list
    }

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_report, f, indent=2, ensure_ascii=False)

    print(f"[SAVE] Evaluation results saved -> {output_path}")
    return final_report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Phase 2 RAG Answer Generation")
    parser.add_argument("--dataset", type=str, default="data/evaluation/generation_questions.json")
    parser.add_argument("--output", type=str, default="data/evaluation/generation_results.json")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--category", type=str, default=None)
    args = parser.parse_args()

    evaluate_generation_suite(
        dataset_path=args.dataset,
        output_path=args.output,
        top_k=args.top_k,
        category_filter=args.category
    )
