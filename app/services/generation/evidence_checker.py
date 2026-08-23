from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logfire

from app.services.retrieval.models import RetrievalCandidate
from app.services.retrieval.query_router import QueryAnalysisResult, QueryType


@dataclass
class EvidenceAssessment:
    is_sufficient: bool
    confidence_level: str  # "high", "medium", "low", "insufficient"
    top_score: float
    avg_top3_score: float
    num_candidates: int
    unique_documents: int
    reason: str


class EvidenceChecker:
    """
    Evaluates the quality, density, and relevance of retrieved candidates
    prior to LLM generation to prevent hallucinations and enforce abstention when appropriate.
    """

    # Scoring thresholds for FlashRank / RRF normalized scores
    HIGH_CONFIDENCE_THRESHOLD = 0.50
    MEDIUM_CONFIDENCE_THRESHOLD = 0.15
    MINIMUM_SUFFICIENCY_THRESHOLD = 0.01

    @classmethod
    def evaluate_evidence(
        cls,
        query: str,
        candidates: List[RetrievalCandidate],
        analysis: Optional[QueryAnalysisResult] = None
    ) -> EvidenceAssessment:
        if not candidates:
            return EvidenceAssessment(
                is_sufficient=False,
                confidence_level="insufficient",
                top_score=0.0,
                avg_top3_score=0.0,
                num_candidates=0,
                unique_documents=0,
                reason="No candidate passages were retrieved from the knowledge base."
            )

        # Check for non-empty text content
        valid_candidates = [c for c in candidates if c.text and len(c.text.strip()) > 10]
        if not valid_candidates:
            return EvidenceAssessment(
                is_sufficient=False,
                confidence_level="insufficient",
                top_score=0.0,
                avg_top3_score=0.0,
                num_candidates=len(candidates),
                unique_documents=0,
                reason="Retrieved candidates contain no readable textual or tabular content."
            )

        top_cand = valid_candidates[0]
        top_score = top_cand.score if top_cand.score is not None else 0.0

        top3 = valid_candidates[:3]
        scores_top3 = [c.score for c in top3 if c.score is not None]
        avg_top3 = sum(scores_top3) / len(scores_top3) if scores_top3 else top_score

        unique_docs = len(set(c.document_name for c in valid_candidates if c.document_name))

        # Check cross-document balance if query is CROSS_DOCUMENT
        if analysis and analysis.query_type == QueryType.CROSS_DOCUMENT and analysis.sub_queries:
            # Check coverage of sub-queries across documents
            if len(analysis.sub_queries) >= 2 and unique_docs < 2:
                logfire.warning(f"Cross-document query missing multi-document coverage | found {unique_docs} docs.")
                confidence = "low"
            else:
                confidence = "high" if top_score >= cls.HIGH_CONFIDENCE_THRESHOLD else "medium"
        else:
            if top_score >= cls.HIGH_CONFIDENCE_THRESHOLD:
                confidence = "high"
            elif top_score >= cls.MEDIUM_CONFIDENCE_THRESHOLD:
                confidence = "medium"
            elif top_score >= cls.MINIMUM_SUFFICIENCY_THRESHOLD:
                confidence = "low"
            else:
                confidence = "insufficient"

        is_sufficient = (confidence != "insufficient")
        reason = f"Top score: {top_score:.4f} across {len(valid_candidates)} passages in {unique_docs} document(s)."

        return EvidenceAssessment(
            is_sufficient=is_sufficient,
            confidence_level=confidence,
            top_score=top_score,
            avg_top3_score=avg_top3,
            num_candidates=len(valid_candidates),
            unique_documents=unique_docs,
            reason=reason
        )
