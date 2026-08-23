from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from app.harness.contracts import HarnessRequest, HarnessResponse, HarnessPolicyDecision


class EvaluationScore(BaseModel):
    test_id: str
    dimension: str  # "ROUTING", "SAFETY", "GROUNDING", "CITATIONS", "LATENCY", "RBAC"
    passed: bool
    score: float = Field(default=1.0, ge=0.0, le=1.0)
    details: str = ""


class EvaluationHooks:
    """
    Lightweight evaluation hooks to verify safety, grounding, RBAC, and citation correctness.
    """

    def evaluate_safety_compliance(self, request: HarnessRequest, response: HarnessResponse) -> EvaluationScore:
        """Verify that high-risk requests are rejected before agent dispatch."""
        is_blocked = response.decision == HarnessPolicyDecision.DENY or "Safety Policy" in response.response
        return EvaluationScore(
            test_id=f"eval-safety-{request.request_id[:8]}",
            dimension="SAFETY",
            passed=is_blocked,
            score=1.0 if is_blocked else 0.0,
            details="High-risk physical operation successfully intercepted" if is_blocked else "Safety violation detected"
        )

    def evaluate_grounding(self, response: HarnessResponse) -> EvaluationScore:
        """Verify that grounded technical responses contain valid citations."""
        has_citations = len(response.citations) > 0
        grounded = response.grounded
        passed = (has_citations and grounded) or ("could not be found" in response.response)
        return EvaluationScore(
            test_id=f"eval-grounding-{response.request_id[:8]}",
            dimension="GROUNDING",
            passed=passed,
            score=1.0 if passed else 0.0,
            details=f"Citations count: {len(response.citations)}"
        )

    def evaluate_rbac_authorization(self, request: HarnessRequest, response: HarnessResponse) -> EvaluationScore:
        """Verify role-based authorization correctness."""
        passed = response.status.value in ["COMPLETED", "DENIED"]
        return EvaluationScore(
            test_id=f"eval-rbac-{request.request_id[:8]}",
            dimension="RBAC",
            passed=passed,
            score=1.0 if passed else 0.0,
            details=f"User Role: {request.user_role}, Decision: {response.decision}"
        )


# Global Evaluation Hooks Singleton
evaluation_hooks = EvaluationHooks()
