#!/usr/bin/env python3
"""
BM25 Index Builder for MASS QA.
Scrolls all points from the existing Qdrant collection `mass_qa_multimodal` (WITHOUT modifying the collection),
constructs structured lexical documents, tokenizes them, builds a BM25Okapi index, and persists it locally.
"""

import os
import sys
import json
import pickle
import re
from datetime import datetime
from typing import List, Dict, Any

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from qdrant_client import QdrantClient
from rank_bm25 import BM25Okapi
from app.config import settings


def tokenize(text: str) -> List[str]:
    """
    Tokenizes text for BM25 lexical search while preserving acronyms,
    alphanumeric IDs, hyphenated terms, and numbers.
    """
    if not text:
        return []
    # Tokenize words, numbers, hyphenated terms, and acronyms
    tokens = re.findall(r"[a-zA-Z0-9_\-\.]+", text.lower())
    # Strip trailing periods from acronyms if any
    cleaned_tokens = [t.strip(".") for t in tokens if len(t.strip(".")) > 0]
    return cleaned_tokens


def build_searchable_text(payload: Dict[str, Any]) -> str:
    """
    Synthesizes a rich searchable text representation from chunk payload metadata.
    Combines text, document name, section, subsection, table data, and visual references.
    """
    parts = []
    
    doc_name = payload.get("document_name", "")
    if doc_name:
        doc_base = os.path.splitext(doc_name)[0].replace("_", " ").replace("-", " ")
        # Emphasize document name so explicit document mentions in queries (e.g. KPMG, PNGRB, IEA, EIA, NEP) match strongly
        parts.append(f"Document Name: {doc_name}")
        parts.append(f"Document Title: {doc_base}")
        parts.append(doc_base)
        parts.append(doc_base)

    section = payload.get("section", "")
    if section:
        parts.append(f"Section: {section}")

    subsection = payload.get("subsection", "")
    if subsection:
        parts.append(f"Subsection: {subsection}")

    ctype = payload.get("content_type", "")
    if ctype:
        parts.append(f"Content Type: {ctype}")

    p_num = payload.get("page_number")
    if p_num is not None:
        parts.append(f"Page {p_num}")

    s_num = payload.get("slide_number")
    if s_num is not None:
        parts.append(f"Slide {s_num}")

    text = payload.get("text", "")
    if text:
        parts.append(text)

    # Format table data into searchable key-value strings if present
    table_data = payload.get("table_data")
    if isinstance(table_data, dict):
        headers = table_data.get("headers", [])
        rows = table_data.get("rows", [])
        if headers:
            parts.append(f"Table Headers: {' | '.join(str(h) for h in headers)}")
        for row in rows:
            if isinstance(row, list):
                row_str = " | ".join(str(val) for val in row)
                parts.append(row_str)

    visual_ref = payload.get("visual_reference")
    if visual_ref:
        parts.append(f"Visual Reference: {visual_ref}")

    return "\n".join(parts)


def build_bm25_index(
    collection_name: str = None,
    output_dir: str = None
):
    target_collection = collection_name or settings.MULTIMODAL_QDRANT_COLLECTION
    out_dir = output_dir or settings.BM25_INDEX_DIR
    os.makedirs(out_dir, exist_ok=True)

    print("==================================================")
    print("BUILDING BM25 PERSISTENT INDEX")
    print("==================================================")
    print(f"Source Collection: {target_collection}")
    print(f"Target Directory:  {out_dir}")

    client = QdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
        timeout=60.0
    )

    if not client.collection_exists(target_collection):
        print(f"[ERROR] Collection '{target_collection}' does not exist in Qdrant!")
        sys.exit(1)

    print("[INFO] Scrolling all points from Qdrant...")
    all_points = []
    offset = None
    batch_size = 250

    while True:
        res, next_offset = client.scroll(
            collection_name=target_collection,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False
        )
        all_points.extend(res)
        if not next_offset:
            break
        offset = next_offset

    total_points = len(all_points)
    print(f"[OK] Successfully fetched {total_points} points.")

    doc_entries: List[Dict[str, Any]] = []
    tokenized_corpus: List[List[str]] = []

    print("[INFO] Processing payloads and tokenizing corpus...")
    for pt in all_points:
        payload = pt.payload or {}
        searchable_text = build_searchable_text(payload)
        tokens = tokenize(searchable_text)
        tokenized_corpus.append(tokens)

        doc_entries.append({
            "point_id": str(pt.id),
            "chunk_id": payload.get("chunk_id", str(pt.id)),
            "document_id": payload.get("document_id", ""),
            "document_name": payload.get("document_name", "Unknown"),
            "content_type": payload.get("content_type", "text"),
            "page_number": payload.get("page_number"),
            "slide_number": payload.get("slide_number"),
            "section": payload.get("section"),
            "subsection": payload.get("subsection"),
            "source_path": payload.get("source_path"),
            "source_status": payload.get("source_status", "synthetic"),
            "visual_reference": payload.get("visual_reference"),
            "table_data": payload.get("table_data"),
            "text": payload.get("text", ""),
            "searchable_text": searchable_text,
            "metadata": payload
        })

    print("[INFO] Fitting BM25Okapi model...")
    bm25_model = BM25Okapi(tokenized_corpus)

    index_data = {
        "bm25_model": bm25_model,
        "doc_entries": doc_entries,
        "collection_name": target_collection,
        "total_documents": len(doc_entries),
        "created_at": datetime.now().isoformat()
    }

    pkl_path = os.path.join(out_dir, "index.pkl")
    print(f"[SAVE] Saving serialized index -> {pkl_path}")
    with open(pkl_path, "wb") as f:
        pickle.dump(index_data, f, protocol=pickle.HIGHEST_PROTOCOL)

    manifest = {
        "collection_name": target_collection,
        "total_documents": len(doc_entries),
        "created_at": datetime.now().isoformat(),
        "index_file": "index.pkl",
        "corpus_version": "v2.0"
    }
    manifest_path = os.path.join(out_dir, "metadata.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"[SAVE] Saved index metadata -> {manifest_path}")
    print("==================================================")
    print("BM25 INDEX BUILD COMPLETE")
    print("==================================================\n")
    return index_data


if __name__ == "__main__":
    build_bm25_index()
