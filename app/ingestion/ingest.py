import os
import sys
import argparse
import time
import json
import uuid
import logfire
from datetime import datetime
from typing import List, Dict, Any

from app.config import settings
from app.ingestion.hash_utils import compute_file_hash
from app.ingestion.parsers import DoclingDocumentParser, FallbackDocumentParser
from app.ingestion.chunker import MultimodalChunker
from app.ingestion.indexer import MultimodalQdrantIndexer

ERROR_LOG_PATH = "logs/ingestion_errors.jsonl"
MANIFEST_PATH = "data/ingestion_manifest.json"


def log_error(document_name: str, page_or_slide: Any, error_type: str, message: str):
    """Appends an error record to logs/ingestion_errors.jsonl."""
    os.makedirs(os.path.dirname(ERROR_LOG_PATH), exist_ok=True)
    record = {
        "timestamp": datetime.now().isoformat(),
        "document": document_name,
        "page_or_slide": page_or_slide,
        "error_type": error_type,
        "error_message": str(message)
    }
    with open(ERROR_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def scan_directory(input_dir: str) -> List[str]:
    """Recursively scans input_dir for supported PDF and PPTX files."""
    supported_files = []
    for root, _, files in os.walk(input_dir):
        for f in files:
            ext = f.lower().rsplit(".", 1)[-1]
            if ext in ("pdf", "pptx"):
                supported_files.append(os.path.join(root, f))
    return supported_files


def run_ingestion(
    input_dir: str,
    collection_name: str = None,
    wipe: bool = False,
    force: bool = False
):
    start_time = time.time()
    run_id = f"run-{uuid.uuid4().hex[:8]}"

    target_collection = collection_name or settings.MULTIMODAL_QDRANT_COLLECTION
    indexer = MultimodalQdrantIndexer(collection_name=target_collection)
    indexer.prepare_collection(wipe=wipe)

    files = scan_directory(input_dir)
    if not files:
        print(f"No supported PDF or PPTX files found in directory: '{input_dir}'")
        return

    # Choose parser: Docling primary with Fallback parser backup
    try:
        parser = DoclingDocumentParser()
    except Exception as e:
        logfire.warning(f"Could not load DoclingDocumentParser: {e}. Using FallbackDocumentParser.")
        parser = FallbackDocumentParser()

    fallback_parser = FallbackDocumentParser()
    chunker = MultimodalChunker()

    stats = {
        "documents": len(files),
        "pdf_count": 0,
        "pptx_count": 0,
        "pages": 0,
        "slides": 0,
        "text_elements": 0,
        "tables": 0,
        "images": 0,
        "charts": 0,
        "diagrams": 0,
        "chunks": 0,
        "indexed_vectors": 0,
        "failed_documents": 0
    }

    manifest_docs = []

    with logfire.span("🚀 Multimodal Ingestion Pipeline", run_id=run_id, total_files=len(files)):
        for file_path in files:
            filename = os.path.basename(file_path)
            ext = filename.lower().rsplit(".", 1)[-1]

            if ext == "pdf":
                stats["pdf_count"] += 1
            else:
                stats["pptx_count"] += 1

            doc_hash = compute_file_hash(file_path)
            document_id = f"DOC-{doc_hash[:12]}"

            # Check duplicate / idempotent ingestion
            if not force and not wipe and indexer.is_document_indexed(document_id):
                logfire.info(f"Skipping duplicate document '{filename}' (hash={doc_hash[:8]}). Use --force to re-index.")
                manifest_docs.append({
                    "document_name": filename,
                    "document_id": document_id,
                    "status": "skipped_duplicate"
                })
                continue

            # Parse document elements
            elements = []
            try:
                elements = parser.parse_document(file_path, document_id, filename)
            except Exception as parse_err:
                log_error(filename, None, "DoclingParseError", parse_err)
                logfire.warning(f"Docling parse failed for {filename}: {parse_err}. Retrying with FallbackParser...")
                try:
                    elements = fallback_parser.parse_document(file_path, document_id, filename)
                except Exception as fb_err:
                    log_error(filename, None, "FallbackParseError", fb_err)
                    stats["failed_documents"] += 1
                    continue

            # Accumulate element counts
            max_page = max([e.page_number for e in elements if e.page_number] or [0])
            max_slide = max([e.slide_number for e in elements if e.slide_number] or [0])
            stats["pages"] += max_page
            stats["slides"] += max_slide

            for elem in elements:
                if elem.content_type == "text":
                    stats["text_elements"] += 1
                elif elem.content_type == "table":
                    stats["tables"] += 1
                elif elem.content_type == "image":
                    stats["images"] += 1
                elif elem.content_type == "chart":
                    stats["charts"] += 1
                elif elem.content_type == "diagram":
                    stats["diagrams"] += 1

            # Chunk document elements
            chunks = chunker.create_chunks(elements, file_path)
            stats["chunks"] += len(chunks)

            # Index chunks in Qdrant
            try:
                count = indexer.index_chunks(chunks)
                stats["indexed_vectors"] += count
                manifest_docs.append({
                    "document_name": filename,
                    "document_id": document_id,
                    "document_hash": doc_hash,
                    "elements": len(elements),
                    "chunks": len(chunks),
                    "indexed": count,
                    "status": "success"
                })
            except Exception as index_err:
                log_error(filename, None, "QdrantIndexError", index_err)
                manifest_docs.append({
                    "document_name": filename,
                    "document_id": document_id,
                    "status": "failed_indexing",
                    "error": str(index_err)
                })

    duration = time.time() - start_time

    # Save Ingestion Manifest
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    manifest_data = {
        "run_id": run_id,
        "started_at": datetime.fromtimestamp(start_time).isoformat(),
        "completed_at": datetime.now().isoformat(),
        "duration_seconds": round(duration, 2),
        "collection": target_collection,
        "statistics": stats,
        "documents": manifest_docs
    }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    # Print Summary Report
    print("\n" + "=" * 50)
    print("MASS QA MULTIMODAL INGESTION SUMMARY")
    print("=" * 50)
    print(f"Documents discovered: {stats['documents']}")
    print(f"  PDF:  {stats['pdf_count']}")
    print(f"  PPTX: {stats['pptx_count']}")
    print(f"Pages processed:  {stats['pages']}")
    print(f"Slides processed: {stats['slides']}\n")
    print(f"Text elements: {stats['text_elements']}")
    print(f"Tables:        {stats['tables']}")
    print(f"Images:        {stats['images']}")
    print(f"Charts:        {stats['charts']}")
    print(f"Diagrams:      {stats['diagrams']}\n")
    print(f"Total Chunks:  {stats['chunks']}")
    print(f"\nQdrant Indexing:")
    print(f"  Collection: {target_collection}")
    print(f"  Indexed:    {stats['indexed_vectors']}")
    print(f"  Failed:     {stats['failed_documents']}")
    print("=" * 50)
    print("INGESTION COMPLETE")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MASS QA Multimodal Data Ingestion CLI")
    parser.add_argument("--input", required=True, help="Path to input documents directory")
    parser.add_argument("--collection", help="Target Qdrant collection name")
    parser.add_argument("--wipe", action="store_true", help="Wipe existing Qdrant collection before ingestion")
    parser.add_argument("--force", action="store_true", help="Force re-indexing of duplicate documents")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: Input directory '{args.input}' does not exist.")
        sys.exit(1)

    run_ingestion(
        input_dir=args.input,
        collection_name=args.collection,
        wipe=args.wipe,
        force=args.force
    )
