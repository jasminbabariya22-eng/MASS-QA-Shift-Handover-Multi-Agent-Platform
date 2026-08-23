from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
import uuid
import logfire

from app.governance.contracts import (
    ApprovalRequest,
    HITLDecision,
    HITLStatus,
    RiskLevel,
    DecisionPayload
)
from app.db.models.hitl_approval import HITLApprovalModel
from app.db.models.shift_handover import ShiftHandoverModel
from app.services.shift_handover_service import ShiftHandoverService


# Custom Domain Exceptions for HITL Governance
class HITLError(Exception):
    """Base exception for HITL governance errors."""
    pass


class ApprovalNotFoundError(HITLError):
    """Raised when the specified approval request is not found."""
    pass


class ApprovalAlreadyDecidedError(HITLError):
    """Raised when trying to decide an approval request that is no longer PENDING."""
    pass


class ApprovalExpiredError(HITLError):
    """Raised when an approval request has passed its expiration timestamp."""
    pass


class SeparationOfDutiesViolationError(HITLError):
    """Raised when the requester attempts to approve their own high-risk action."""
    pass


class UnauthorizedApproverError(HITLError):
    """Raised when the approver lacks the mandatory operational role."""
    pass


class ApprovalReasonRequiredError(HITLError):
    """Raised when rejection or return is submitted without a mandatory operational reason."""
    pass


class ApprovalStaleError(HITLError):
    """Raised when the underlying handover state or version changed since approval creation."""
    pass


class ApprovalAlreadyConsumedError(HITLError):
    """Raised when trying to execute an approval that has already been executed."""
    pass


class HITLService:
    """
    Deterministic Human-In-The-Loop (HITL) Service.
    Manages approval lifecycles, role authorization gates, separation of duties, expiration,
    idempotency, concurrency checks, and audit trails.
    """

    DEFAULT_TTL_SECONDS = 3600  # 1 hour expiration window

    def __init__(self):
        # In-memory store for fast isolated testing; database session utilized when provided
        self._in_memory_store: Dict[str, ApprovalRequest] = {}

    def create_approval_request(
        self,
        request_id: str,
        action: str,
        requested_by: str,
        requested_role: str,
        required_role: str,
        handover_id: Optional[str] = None,
        session_id: Optional[str] = None,
        risk_level: RiskLevel = RiskLevel.HIGH,
        reason: Optional[str] = None,
        proposed_payload: Optional[Dict[str, Any]] = None,
        expected_handover_version: Optional[int] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        db: Optional[Session] = None
    ) -> ApprovalRequest:
        """
        Create a new HITL approval request in PENDING status.
        """
        apr_id = f"APR-{uuid.uuid4().hex[:12].upper()}"
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=ttl_seconds)

        approval = ApprovalRequest(
            id=apr_id,
            request_id=request_id,
            session_id=session_id,
            handover_id=handover_id,
            action=action.upper(),
            risk_level=risk_level,
            status=HITLStatus.PENDING,
            requested_by=requested_by,
            requested_role=requested_role.upper(),
            required_role=required_role.upper(),
            reason=reason,
            proposed_payload=proposed_payload or {},
            created_at=now,
            expires_at=expires_at,
            version=1,
            expected_handover_version=expected_handover_version
        )

        # Store in-memory
        self._in_memory_store[apr_id] = approval

        # Persist to PostgreSQL if db session provided
        if db:
            try:
                db_record = HITLApprovalModel(
                    id=approval.id,
                    request_id=approval.request_id,
                    session_id=approval.session_id,
                    handover_id=approval.handover_id,
                    action=approval.action,
                    risk_level=approval.risk_level.value,
                    status=approval.status.value,
                    requested_by=approval.requested_by,
                    requested_role=approval.requested_role,
                    required_role=approval.required_role,
                    reason=approval.reason,
                    proposed_payload=approval.proposed_payload,
                    created_at=approval.created_at,
                    expires_at=approval.expires_at,
                    version=approval.version,
                    expected_handover_version=approval.expected_handover_version
                )
                db.add(db_record)
                db.commit()
            except Exception as db_ex:
                logfire.warning(f"[HITLService] DB persistence fallback on create: {db_ex}")
                if hasattr(db, "rollback"):
                    db.rollback()

        logfire.info(f"[HITLService] Created Approval {apr_id} for action '{action}' (ReqBy: {requested_by}, ReqRole: {required_role})")
        return approval

    def get_approval(self, approval_id: str, db: Optional[Session] = None) -> Optional[ApprovalRequest]:
        """
        Retrieve approval request by ID with lazy expiration evaluation and memory fallback.
        """
        approval: Optional[ApprovalRequest] = None

        if db:
            try:
                record = db.query(HITLApprovalModel).filter(HITLApprovalModel.id == approval_id).first()
                if record:
                    approval = self._orm_to_domain(record)
            except Exception as db_ex:
                logfire.warning(f"[HITLService] DB query fallback on get: {db_ex}")
                if hasattr(db, "rollback"):
                    db.rollback()

        if not approval:
            approval = self._in_memory_store.get(approval_id)

        if not approval:
            return None

        # Lazy Expiration Check
        now = datetime.now(timezone.utc)
        if approval.status == HITLStatus.PENDING and now > approval.expires_at:
            approval.status = HITLStatus.EXPIRED
            self._in_memory_store[approval_id] = approval
            if db:
                try:
                    record = db.query(HITLApprovalModel).filter(HITLApprovalModel.id == approval_id).first()
                    if record:
                        record.status = HITLStatus.EXPIRED.value
                        db.commit()
                except Exception:
                    pass
            logfire.warning(f"[HITLService] Approval {approval_id} has expired.")

        return approval

    def list_approvals(
        self,
        handover_id: Optional[str] = None,
        status: Optional[HITLStatus] = None,
        user_id: Optional[str] = None,
        db: Optional[Session] = None
    ) -> List[ApprovalRequest]:
        """
        List approval requests with optional filtering.
        """
        if db:
            try:
                query = db.query(HITLApprovalModel)
                if handover_id:
                    query = query.filter(HITLApprovalModel.handover_id == handover_id)
                if status:
                    query = query.filter(HITLApprovalModel.status == status.value)
                if user_id:
                    query = query.filter(HITLApprovalModel.requested_by == user_id)
                records = query.order_by(HITLApprovalModel.created_at.desc()).all()
                if records:
                    return [self._orm_to_domain(r) for r in records]
            except Exception as db_ex:
                logfire.warning(f"[HITLService] DB list fallback to in-memory: {db_ex}")
                if hasattr(db, "rollback"):
                    db.rollback()

        # In-memory list
        res = list(self._in_memory_store.values())
        if handover_id:
            res = [a for a in res if a.handover_id == handover_id]
        if status:
            res = [a for a in res if a.status == status]
        if user_id:
            res = [a for a in res if a.requested_by == user_id]
        return sorted(res, key=lambda a: a.created_at, reverse=True)

    def decide_approval(
        self,
        approval_id: str,
        decision: HITLDecision,
        decider_id: str,
        decider_role: str,
        reason: Optional[str] = None,
        db: Optional[Session] = None
    ) -> ApprovalRequest:
        """
        Record human decision on an approval request.
        Enforces separation of duties, role authorization, expiration, and mandatory rejection reasons.
        """
        approval = self.get_approval(approval_id, db=db)
        if not approval:
            raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found.")

        # 1. Check Status & Expiration
        now = datetime.now(timezone.utc)
        if approval.status == HITLStatus.EXPIRED or now > approval.expires_at:
            approval.status = HITLStatus.EXPIRED
            raise ApprovalExpiredError(f"Approval request '{approval_id}' has expired.")

        if approval.status != HITLStatus.PENDING:
            raise ApprovalAlreadyDecidedError(f"Approval request '{approval_id}' is already {approval.status.value}.")

        # 2. Separation of Duties Check: Requester cannot approve their own high-risk action
        decider_id_norm = decider_id.strip()
        if decider_id_norm == approval.requested_by and decision == HITLDecision.APPROVE:
            logfire.warning(f"[HITLService] Separation of duties violation on {approval_id}: {decider_id} attempted self-approval.")
            raise SeparationOfDutiesViolationError(
                f"Separation of duties violation: Requester '{approval.requested_by}' cannot approve their own action."
            )

        # 3. Role Authorization Check
        decider_role_norm = decider_role.strip().upper()
        if decider_role_norm != approval.required_role and decider_role_norm not in ["SHIFT_SUPERVISOR", "SYSTEM_ADMIN", "ADMIN"]:
            logfire.warning(f"[HITLService] Unauthorized approver on {approval_id}: {decider_role_norm} != {approval.required_role}")
            raise UnauthorizedApproverError(
                f"Unauthorized approver: Role '{decider_role_norm}' is not authorized. Required: '{approval.required_role}'."
            )

        # 4. Mandatory Reason Check on Rejection / Return
        if decision in [HITLDecision.REJECT, HITLDecision.RETURN] and not (reason and reason.strip()):
            raise ApprovalReasonRequiredError(f"Operational reason is mandatory when decision is {decision.value}.")

        # 5. Apply Decision
        approval.decision = decision
        approval.decision_reason = reason
        approval.decided_by = decider_id_norm
        approval.decided_at = now

        if decision == HITLDecision.APPROVE:
            approval.status = HITLStatus.APPROVED
        elif decision == HITLDecision.REJECT:
            approval.status = HITLStatus.REJECTED
        elif decision == HITLDecision.RETURN:
            approval.status = HITLStatus.RETURNED
        elif decision == HITLDecision.ESCALATE:
            approval.status = HITLStatus.ESCALATED
        elif decision == HITLDecision.CANCEL:
            approval.status = HITLStatus.CANCELLED

        # Persist update
        self._in_memory_store[approval_id] = approval

        if db:
            try:
                record = db.query(HITLApprovalModel).filter(HITLApprovalModel.id == approval_id).first()
                if record:
                    record.decision = approval.decision.value
                    record.decision_reason = approval.decision_reason
                    record.decided_by = approval.decided_by
                    record.decided_at = approval.decided_at
                    record.status = approval.status.value
                    db.commit()
            except Exception as db_ex:
                logfire.warning(f"[HITLService] DB decide update fallback: {db_ex}")
                if hasattr(db, "rollback"):
                    db.rollback()

        logfire.info(f"[HITLService] Approval {approval_id} decided as {decision.value} by {decider_id} ({decider_role})")
        return approval

    def consume_and_execute(
        self,
        approval_id: str,
        shift_service: Optional[ShiftHandoverService] = None,
        db: Optional[Session] = None
    ) -> Tuple[ApprovalRequest, Any]:
        """
        Execute the deterministic workflow transition after human approval.
        Enforces idempotency (single consumption) and optimistic locking staleness checks.
        """
        approval = self.get_approval(approval_id, db=db)
        if not approval:
            raise ApprovalNotFoundError(f"Approval request '{approval_id}' not found.")

        # 1. Check if already consumed / replay protection
        if approval.consumed_at is not None or approval.status == HITLStatus.CONSUMED:
            raise ApprovalAlreadyConsumedError(f"Approval request '{approval_id}' has already been executed/consumed.")

        if approval.status != HITLStatus.APPROVED:
            raise ApprovalAlreadyDecidedError(f"Cannot execute approval in status '{approval.status.value}'. Must be APPROVED.")

        # 2. Concurrency / Staleness Check
        if approval.handover_id and approval.expected_handover_version is not None and db:
            live_version = None
            try:
                handover_record = db.query(ShiftHandoverModel).filter(ShiftHandoverModel.id == approval.handover_id).first()
                if handover_record:
                    live_version = getattr(handover_record, "version", None)
            except Exception as db_ex:
                logfire.warning(f"[HITLService] DB handover version query check: {db_ex}")

            if live_version is not None and live_version != approval.expected_handover_version:
                logfire.error(
                    f"[HITLService] Stale approval on {approval.handover_id}: "
                    f"expected v{approval.expected_handover_version}, found live v{live_version}"
                )
                raise ApprovalStaleError(
                    f"Approval is stale: Handover '{approval.handover_id}' version changed (v{approval.expected_handover_version} -> v{live_version})."
                )

        # 3. Execute Workflow Transition via Shift Service if attached
        workflow_result = None
        if shift_service and approval.handover_id:
            act = approval.action.upper()
            if act in ["SUBMIT", "SUBMIT_HANDOVER"]:
                workflow_result = shift_service.submit_handover(
                    db=db,
                    handover_id=approval.handover_id,
                    actor_id=approval.requested_by,
                    actor_role=approval.requested_role,
                    request_id=approval.request_id
                )
            elif act in ["APPROVE", "APPROVE_HANDOVER"]:
                workflow_result = shift_service.approve_handover(
                    db=db,
                    handover_id=approval.handover_id,
                    supervisor_id=approval.decided_by or approval.requested_by,
                    request_id=approval.request_id
                )
            elif act in ["ACKNOWLEDGE", "ACKNOWLEDGE_HANDOVER"]:
                workflow_result = shift_service.acknowledge_handover(
                    db=db,
                    handover_id=approval.handover_id,
                    incoming_operator_id=approval.decided_by or approval.requested_by,
                    request_id=approval.request_id
                )

        # 4. Mark as Consumed
        now = datetime.now(timezone.utc)
        approval.consumed_at = now
        approval.status = HITLStatus.CONSUMED

        self._in_memory_store[approval_id] = approval

        if db:
            try:
                record = db.query(HITLApprovalModel).filter(HITLApprovalModel.id == approval_id).first()
                if record:
                    record.consumed_at = approval.consumed_at
                    record.status = HITLStatus.CONSUMED.value
                    db.commit()
            except Exception as db_ex:
                logfire.warning(f"[HITLService] DB consume update fallback: {db_ex}")
                if hasattr(db, "rollback"):
                    db.rollback()

        logfire.info(f"[HITLService] Approval {approval_id} consumed and executed successfully.")
        return approval, workflow_result

    @staticmethod
    def _orm_to_domain(record: HITLApprovalModel) -> ApprovalRequest:
        return ApprovalRequest(
            id=record.id,
            request_id=record.request_id,
            session_id=record.session_id,
            handover_id=record.handover_id,
            action=record.action,
            risk_level=RiskLevel(record.risk_level),
            status=HITLStatus(record.status),
            requested_by=record.requested_by,
            requested_role=record.requested_role,
            required_role=record.required_role,
            reason=record.reason,
            proposed_payload=record.proposed_payload or {},
            decision=HITLDecision(record.decision) if record.decision else None,
            decision_reason=record.decision_reason,
            decided_by=record.decided_by,
            created_at=record.created_at,
            expires_at=record.expires_at,
            decided_at=record.decided_at,
            consumed_at=record.consumed_at,
            version=record.version,
            expected_handover_version=record.expected_handover_version
        )


# Global HITL Service Singleton
hitl_service = HITLService()
