from typing import Optional, List, Dict, Any
import logfire

from app.services.generation import answer_query, RAGResponse


class LoopEngineeringRAGAdapter:
    """
    Adapter connecting Loop Engineering Agent to the existing frozen Multimodal RAG pipeline.
    Reuses existing Qdrant embeddings and retrieval without modifying mass_qa_multimodal.
    """

    def retrieve_engineering_evidence(
        self,
        query: str,
        top_k: int = 5,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute RAG retrieval over frozen collection and return grounded answer + structured citations.
        """
        try:
            rag_res: RAGResponse = answer_query(
                query=query,
                top_k=top_k,
                session_id=session_id
            )

            citations = [cit.model_dump() for cit in rag_res.citations]

            return {
                "answer": rag_res.answer,
                "citations": citations,
                "confidence": rag_res.confidence,
                "query_type": rag_res.query_type,
                "latency_breakdown": rag_res.latency_breakdown,
                "grounded": rag_res.grounded
            }
        except Exception as e:
            logfire.warning(f"[LoopRAGAdapter] Knowledge retrieval fallback on query '{query[:50]}': {e}")
            return {
                "answer": "No additional engineering documentation could be retrieved from the frozen knowledge base.",
                "citations": [],
                "confidence": "low",
                "query_type": "loop_engineering",
                "latency_breakdown": {},
                "grounded": False
            }


# Global Adapter Singleton
loop_rag_adapter = LoopEngineeringRAGAdapter()
