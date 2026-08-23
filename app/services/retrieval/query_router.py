import re
from enum import Enum
from typing import List, Tuple, Optional
from pydantic import BaseModel


class QueryType(str, Enum):
    NORMAL = "normal"
    MULTIMODAL = "multimodal"
    CROSS_DOCUMENT = "cross_document"


class QueryAnalysisResult(BaseModel):
    query: str
    query_type: QueryType
    detected_signals: List[str]
    sub_queries: List[str] = []


class QueryRouter:
    """
    Lightweight, deterministic query classifier and sub-query generator.
    Does NOT invoke LLMs to keep latency ultra-low and deterministic.
    """

    CROSS_DOC_PATTERNS = [
        r"\bcompare\b",
        r"\bcomparison\b",
        r"\bversus\b",
        r"\bvs\.?\b",
        r"\bbetween\b.+\band\b",
        r"\bcontrast\b",
        r"\bdifference(s)?\b",
        r"\balign with\b",
        r"\brelate to\b",
        r"\bhow do(es)?\b.+\bcompare\b",
        r"\bhow do(es)?\b.+\balign\b",
    ]

    # Known multi-entity pairings in corpus
    CORPUS_ENTITIES = [
        "pngrb", "nep", "iea", "eia", "kpmg", "chatham house",
        "epa", "nsps", "good governance", "national electricity plan",
        "petroleum refining", "processing facilities"
    ]

    MULTIMODAL_PATTERNS = [
        r"\btable\b",
        r"\bchart\b",
        r"\bgraph\b",
        r"\bdiagram\b",
        r"\bimage\b",
        r"\bfigure\b",
        r"\bvisual\b",
        r"\bbranding\b",
        r"\blayout\b",
        r"\bheader\b",
        r"\bpercentage\b",
        r"\btrend(s)?\b",
        r"\bavailability\b",
        r"\bvalues shown\b",
        r"\bpledged\b",
        r"\bunit 4\b",
        r"\btps\b"
    ]

    @classmethod
    def analyze(cls, query: str) -> QueryAnalysisResult:
        query_lower = query.lower()
        signals = []

        # 1. Check Cross-Document Signals
        is_cross_doc = False
        for pattern in cls.CROSS_DOC_PATTERNS:
            if re.search(pattern, query_lower):
                signals.append(f"cross_pattern:{pattern}")
                is_cross_doc = True
                break

        # Check multiple corpus entities mention (e.g. PNGRB + NEP, KPMG + PNGRB, IEA + EIA, EPA + Good Governance)
        found_entities = [ent for ent in cls.CORPUS_ENTITIES if ent in query_lower]
        if len(found_entities) >= 2:
            signals.append(f"multi_entity:{','.join(found_entities)}")
            is_cross_doc = True

        if is_cross_doc:
            sub_queries = cls._extract_sub_queries(query, found_entities)
            return QueryAnalysisResult(
                query=query,
                query_type=QueryType.CROSS_DOCUMENT,
                detected_signals=signals,
                sub_queries=sub_queries
            )

        # 2. Check Multimodal Signals
        for pattern in cls.MULTIMODAL_PATTERNS:
            if re.search(pattern, query_lower):
                signals.append(f"multimodal_pattern:{pattern}")

        if signals:
            return QueryAnalysisResult(
                query=query,
                query_type=QueryType.MULTIMODAL,
                detected_signals=signals,
                sub_queries=[]
            )

        # 3. Default to Normal
        return QueryAnalysisResult(
            query=query,
            query_type=QueryType.NORMAL,
            detected_signals=["normal_factual_or_operational"],
            sub_queries=[]
        )

    @classmethod
    def _extract_sub_queries(cls, query: str, entities: List[str]) -> List[str]:
        """
        Decomposes comparative query into targeted sub-queries for each side of comparison.
        """
        sub_queries = []
        q = query.strip()

        # Try splitting on common comparative conjunctions
        patterns = [
            r"^(?:how\s+(?:does|do))?\s*(.*?)\s+(?:compare\s+(?:with|to)|align\s+with|relate\s+to)\s+(.*?)\??$",
            r"^(?:compare|comparison\s+of)\s+(.*?)\s+(?:with|and|versus|vs\.?)\s+(.*?)\??$",
            r"^(?:what\s+are\s+the\s+differences\s+between)\s+(.*?)\s+and\s+(.*?)\??$"
        ]

        for pat in patterns:
            m = re.search(pat, q, flags=re.IGNORECASE)
            if m:
                part_a = m.group(1).strip()
                part_b = m.group(2).strip()
                # Clean leading punctuation or stray words
                part_a = re.sub(r"^(?:es|s|the)\s+", "", part_a, flags=re.IGNORECASE).strip()
                part_b = re.sub(r"^(?:the)\s+", "", part_b, flags=re.IGNORECASE).strip()
                if part_a and part_b:
                    return [part_a, part_b]

        # If regex did not match clean parts, use detected entities or entity clauses
        if len(entities) >= 2:
            for ent in entities[:2]:
                sub_queries.append(f"{ent} {q}")
            return sub_queries

        # Fallback: return original query as single sub-query
        return [query]
