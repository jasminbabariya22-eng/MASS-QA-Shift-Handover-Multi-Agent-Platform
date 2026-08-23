from typing import Optional, Dict, Any
import logfire

from app.governance.contracts import RiskLevel, HITLPolicyResult
from app.governance.risk import risk_classifier, RiskClassifier


class PolicyEngine:
    """
    Centralized governance and authorization policy engine.
    Determines action admissibility, required roles, and HITL gate requirements.
    """

    ACTION_REQUIRED_ROLES = {
        "SUBMIT": "CONSOLE_OPERATOR",
        "SUBMIT_HANDOVER": "CONSOLE_OPERATOR",
        "APPROVE": "SHIFT_SUPERVISOR",
        "APPROVE_HANDOVER": "SHIFT_SUPERVISOR",
        "REJECT": "SHIFT_SUPERVISOR",
        "REJECT_HANDOVER": "SHIFT_SUPERVISOR",
        "RETURN": "SHIFT_SUPERVISOR",
        "RETURN_HANDOVER": "SHIFT_SUPERVISOR",
        "ACKNOWLEDGE": "INCOMING_OPERATOR",
        "ACKNOWLEDGE_HANDOVER": "INCOMING_OPERATOR",
        "CREATE": "CONSOLE_OPERATOR",
        "CREATE_HANDOVER": "CONSOLE_OPERATOR"
    }

    def __init__(self, classifier: Optional[RiskClassifier] = None):
        self.risk_classifier = classifier or risk_classifier

    def evaluate(
        self,
        user_id: str,
        user_role: str,
        action: Optional[str] = None,
        message: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> HITLPolicyResult:
        """
        Evaluate policy against user identity, action, and payload.
        """
        act_norm = (action or "").strip().upper()
        risk = self.risk_classifier.classify(action=act_norm, message=message, payload=payload)

        # 1. Safety Interlock for CRITICAL operations
        if risk == RiskLevel.CRITICAL:
            logfire.warning(f"[PolicyEngine] Action blocked by Safety Interlock: '{message or act_norm}'")
            return HITLPolicyResult(
                allowed=False,
                risk_level=RiskLevel.CRITICAL,
                hitl_required=False,
                required_role=None,
                reason="Physical plant control, trip, or safety bypass operations are strictly prohibited.",
                blocked_by_safety=True
            )

        # 2. Determine Required Approver Role for High-Risk Actions
        required_role = self.ACTION_REQUIRED_ROLES.get(act_norm, "SHIFT_SUPERVISOR")

        # 3. Determine HITL Requirement
        if risk == RiskLevel.HIGH:
            logfire.info(f"[PolicyEngine] Action '{act_norm}' classified as HIGH risk. HITL approval required.")
            return HITLPolicyResult(
                allowed=True,
                risk_level=RiskLevel.HIGH,
                hitl_required=True,
                required_role=required_role,
                reason=f"High-risk operational action '{act_norm}' requires human authorization by {required_role}."
            )

        # 4. Medium / Low Risk Actions (Direct execution permitted)
        return HITLPolicyResult(
            allowed=True,
            risk_level=risk,
            hitl_required=False,
            required_role=None,
            reason="Standard operation permitted under automated governance."
        )


# Global Policy Engine Singleton
policy_engine = PolicyEngine()
