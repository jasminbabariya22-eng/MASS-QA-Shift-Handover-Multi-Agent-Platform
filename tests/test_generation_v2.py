import pytest
from app.services.retrieval.models import RetrievalCandidate
from app.services.retrieval.query_router import QueryRouter, QueryAnalysisResult, QueryType
from app.services.generation.models import SourceCitation, RAGResponse
from app.services.generation.context_builder import ContextBuilder
from app.services.generation.evidence_checker import EvidenceChecker, EvidenceAssessment
from app.services.generation.generator import RAGAnswerGenerator, SYSTEM_GROUNDING_PROMPT
from app.guardrails.colang_rules import RAIL_INDICATORS


def test_response_schema_serialization():
    citation = SourceCitation(
        source_number=1,
        document_name="5.1_petroleum_refining.pdf",
        chunk_id="chunk_001",
        page_number=3,
        content_type="text",
        score=0.985
    )
    resp = RAGResponse(
        question="What is distillation?",
        answer="Distillation separates fractions [Source 1: 5.1_petroleum_refining.pdf, Page 3].",
        sources=[citation],
        query_type="normal",
        retrieval_count=1,
        grounded=True,
        confidence="high",
        latency_breakdown={"retrieval": 0.5, "llm_generation": 1.2, "total": 1.7},
        status="success"
    )
    d = resp.model_dump()
    assert d["question"] == "What is distillation?"
    assert len(d["sources"]) == 1
    assert d["sources"][0]["document_name"] == "5.1_petroleum_refining.pdf"
    assert d["grounded"] is True
    assert d["confidence"] == "high"


def test_context_builder_text_candidate():
    cands = [
        RetrievalCandidate(
            point_id="1",
            chunk_id="chk_1",
            document_id="doc_1",
            document_name="5.1_petroleum_refining.pdf",
            content_type="text",
            page_number=3,
            section="Refining Units",
            score=0.95,
            text="Atmospheric distillation operates at 350-380 C."
        )
    ]
    context_str, citations = ContextBuilder.build_context(cands)
    assert "SOURCE [1]" in context_str
    assert "5.1_petroleum_refining.pdf" in context_str
    assert "Page 3" in context_str
    assert "Atmospheric distillation operates at 350-380 C." in context_str
    assert len(citations) == 1
    assert citations[0].source_number == 1
    assert citations[0].page_number == 3


def test_context_builder_table_preservation():
    table_data = {
        "headers": ["Unit", "Capacity (BPD)", "Yield %"],
        "rows": [
            ["CDU", "150,000", "45%"],
            ["VDU", "80,000", "30%"]
        ],
        "caption": "Refining Capacity Breakdown"
    }
    cand = RetrievalCandidate(
        point_id="2",
        chunk_id="chk_2",
        document_id="doc_2",
        document_name="5.1_petroleum_refining.pdf",
        content_type="table",
        page_number=5,
        table_data=table_data,
        text="Refining capacities summary",
        score=0.92
    )
    context_str, citations = ContextBuilder.build_context([cand])
    assert "| Unit | Capacity (BPD) | Yield % |" in context_str
    assert "| CDU | 150,000 | 45% |" in context_str
    assert "| VDU | 80,000 | 30% |" in context_str
    assert "Refining Capacity Breakdown" in context_str
    assert citations[0].content_type == "table"


def test_context_builder_multimodal_caption():
    vis_ref = {
        "caption": "Process flow diagram showing crude distillation column and sidestreams.",
        "type": "diagram"
    }
    cand = RetrievalCandidate(
        point_id="3",
        chunk_id="chk_3",
        document_id="doc_3",
        document_name="5.1_petroleum_refining.pdf",
        content_type="diagram",
        page_number=2,
        visual_reference=vis_ref,
        text="Crude distillation unit diagram",
        score=0.88
    )
    context_str, citations = ContextBuilder.build_context([cand])
    assert "[Visual / Diagram Description]:" in context_str
    assert "Process flow diagram showing crude distillation column" in context_str
    assert citations[0].content_type == "diagram"


def test_evidence_checker_high_confidence():
    cands = [
        RetrievalCandidate(
            point_id="1",
            chunk_id="chk_1",
            document_id="doc_1",
            document_name="5.1_petroleum_refining.pdf",
            content_type="text",
            page_number=3,
            score=0.98,
            text="Detailed operational procedures for crude oil fractionation units."
        ),
        RetrievalCandidate(
            point_id="2",
            chunk_id="chk_2",
            document_id="doc_1",
            document_name="5.1_petroleum_refining.pdf",
            content_type="text",
            page_number=4,
            score=0.91,
            text="Operating temperatures and reflux ratios."
        )
    ]
    assessment = EvidenceChecker.evaluate_evidence("What are refinery distillation parameters?", cands)
    assert assessment.is_sufficient is True
    assert assessment.confidence_level == "high"
    assert assessment.top_score >= 0.50
    assert assessment.num_candidates == 2


def test_evidence_checker_insufficient_empty():
    assessment = EvidenceChecker.evaluate_evidence("What is quantum computing?", [])
    assert assessment.is_sufficient is False
    assert assessment.confidence_level == "insufficient"
    assert assessment.num_candidates == 0


def test_evidence_checker_low_score_abstention():
    cands = [
        RetrievalCandidate(
            point_id="1",
            chunk_id="chk_1",
            document_id="doc_1",
            document_name="5.1_petroleum_refining.pdf",
            content_type="text",
            page_number=3,
            score=0.005,  # Below MINIMUM_SUFFICIENCY_THRESHOLD
            text="General background introductory statement on industrial equipment."
        )
    ]
    assessment = EvidenceChecker.evaluate_evidence("What is the recipe for chocolate cake?", cands)
    assert assessment.is_sufficient is False
    assert assessment.confidence_level == "insufficient"


def test_grounding_prompt_rules_presence():
    assert "Answer ONLY using the facts directly stated" in SYSTEM_GROUNDING_PROMPT
    assert "I don't have enough information in the available knowledge base" in SYSTEM_GROUNDING_PROMPT
    assert "In-Text Citations:" in SYSTEM_GROUNDING_PROMPT
    assert "Cross-Document Comparative Questions" in SYSTEM_GROUNDING_PROMPT


def test_filter_used_citations():
    generator = RAGAnswerGenerator()
    citations = [
        SourceCitation(source_number=1, document_name="Doc1.pdf", page_number=2, content_type="text"),
        SourceCitation(source_number=2, document_name="Doc2.pdf", page_number=10, content_type="text"),
        SourceCitation(source_number=3, document_name="Doc3.pdf", page_number=15, content_type="text"),
    ]
    answer_text = "According to [Source 1: Doc1.pdf, Page 2] and [Source 3: Doc3.pdf, Page 15], the value is 42."
    filtered = generator._filter_used_citations(answer_text, citations)
    assert len(filtered) == 2
    assert {c.source_number for c in filtered} == {1, 3}


def test_guardrail_indicators_coverage():
    assert any("knowledge base" in ind.lower() for ind in RAIL_INDICATORS)
