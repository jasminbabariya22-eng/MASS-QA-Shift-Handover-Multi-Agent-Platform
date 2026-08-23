import uuid
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc
import logfire

from app.db.models.shift_handover import (
    ShiftHandoverModel,
    SafetyCriticalItemModel,
    ShiftHandoverAuditModel,
)


class ShiftHandoverNotFoundError(Exception):
    """Raised when a requested Shift Handover cannot be found."""
    pass


class ConcurrencyConflictError(Exception):
    """Raised when an optimistic concurrency version conflict occurs."""
    pass


class TerminalStateError(Exception):
    """Raised when attempting to modify a handover in a terminal state."""
    pass


class ShiftHandoverRepository:
    """
    SQLAlchemy Repository layer for Shift Handover persistence, atomic state transitions,
    and optimistic concurrency locking in PostgreSQL.
    """

    @staticmethod
    def generate_handover_number(unit_id: str, shift_date: str) -> str:
        """
        Generate a human-readable, deterministic reference number: SHO-YYYYMMDD-UNIT-XXXX
        """
        date_clean = shift_date.replace("-", "")
        unit_clean = unit_id.replace("-", "").upper()
        suffix = uuid.uuid4().hex[:4].upper()
        return f"SHO-{date_clean}-{unit_clean}-{suffix}"

    @staticmethod
    def create_handover(
        db: Session,
        unit_id: str,
        shift_type: str,
        shift_date: str,
        outgoing_operator_id: str,
        operational_summary: str = "",
        unit_name: Optional[str] = None,
        outgoing_operator_name: Optional[str] = None,
        incoming_operator_id: Optional[str] = None,
        incoming_operator_name: Optional[str] = None,
        supervisor_id: Optional[str] = None,
        equipment_abnormalities: Optional[List[str]] = None,
        open_permits: Optional[List[str]] = None,
        loto_isolations: Optional[List[str]] = None,
        carry_forward_actions: Optional[List[str]] = None,
        notes: Optional[str] = None,
        handover_id: Optional[str] = None,
        handover_number: Optional[str] = None,
        actor_role: str = "CONSOLE_OPERATOR",
        request_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> ShiftHandoverModel:
        """
        Persist a new shift handover in DRAFT state with initial version=1 and initial audit record.
        """
        hid = handover_id or str(uuid.uuid4())
        hnum = handover_number or ShiftHandoverRepository.generate_handover_number(unit_id, shift_date)
        now = datetime.now(timezone.utc)

        handover = ShiftHandoverModel(
            id=hid,
            handover_number=hnum,
            workflow_code="SHIFT_HANDOVER",
            workflow_version="1.0.0",
            state="DRAFT",
            unit_id=unit_id,
            unit_name=unit_name,
            shift_type=shift_type,
            shift_date=shift_date,
            outgoing_operator_id=outgoing_operator_id,
            outgoing_operator_name=outgoing_operator_name,
            incoming_operator_id=incoming_operator_id,
            incoming_operator_name=incoming_operator_name,
            supervisor_id=supervisor_id,
            operational_summary=operational_summary,
            equipment_abnormalities=equipment_abnormalities or [],
            open_permits=open_permits or [],
            loto_isolations=loto_isolations or [],
            carry_forward_actions=carry_forward_actions or [],
            all_safety_items_acknowledged=False,
            notes=notes,
            version=1,
            created_at=now,
            updated_at=now
        )
        db.add(handover)

        audit = ShiftHandoverAuditModel(
            handover_id=hid,
            from_state="DRAFT",
            to_state="DRAFT",
            action="CREATE",
            actor_id=outgoing_operator_id,
            actor_role=actor_role,
            reason="Initial handover draft creation",
            request_id=request_id,
            session_id=session_id,
            metadata_={"unit_id": unit_id, "shift_type": shift_type, "version": 1},
            created_at=now
        )
        db.add(audit)
        db.flush()

        logfire.info(f"[ShiftRepo] Created handover {hid} [{hnum}] by {outgoing_operator_id}")
        return handover

    @staticmethod
    def get_by_id(db: Session, handover_id: str) -> Optional[ShiftHandoverModel]:
        """
        Retrieve a shift handover by primary key with eagerly loaded safety items and audit trail.
        """
        return db.query(ShiftHandoverModel).options(
            joinedload(ShiftHandoverModel.safety_items),
            joinedload(ShiftHandoverModel.audit_trail)
        ).filter(
            (ShiftHandoverModel.id == handover_id) | (ShiftHandoverModel.handover_number == handover_id)
        ).first()

    @staticmethod
    def list_handovers(
        db: Session,
        unit_id: Optional[str] = None,
        state: Optional[str] = None,
        shift_date: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[ShiftHandoverModel]:
        """
        List shift handovers with optional filtering by unit, state, or shift date.
        """
        query = db.query(ShiftHandoverModel)
        if unit_id:
            query = query.filter(ShiftHandoverModel.unit_id == unit_id)
        if state:
            query = query.filter(ShiftHandoverModel.state == state)
        if shift_date:
            query = query.filter(ShiftHandoverModel.shift_date == shift_date)

        return query.order_by(desc(ShiftHandoverModel.created_at)).offset(offset).limit(limit).all()

    @staticmethod
    def update_data(
        db: Session,
        handover_id: str,
        expected_version: int,
        updates: Dict[str, Any],
        actor_id: str,
        actor_role: str = "CONSOLE_OPERATOR"
    ) -> ShiftHandoverModel:
        """
        Update mutable handover information while in DRAFT or RETURNED state using optimistic concurrency locking.
        """
        handover = db.query(ShiftHandoverModel).filter(ShiftHandoverModel.id == handover_id).first()
        if not handover:
            raise ShiftHandoverNotFoundError(f"Handover {handover_id} not found.")

        if handover.is_terminal:
            raise TerminalStateError(f"Cannot update handover in terminal state '{handover.state}'.")

        if handover.version != expected_version:
            raise ConcurrencyConflictError(
                f"Version conflict: Handover is at version {handover.version}, expected {expected_version}."
            )

        now = datetime.now(timezone.utc)
        for k, v in updates.items():
            if hasattr(handover, k):
                setattr(handover, k, v)

        handover.updated_at = now
        db.flush()
        return handover

    @staticmethod
    def add_safety_item(
        db: Session,
        handover_id: str,
        category: str,
        equipment_tag: str,
        description: str,
        active: bool = True
    ) -> SafetyCriticalItemModel:
        """
        Attach a safety-critical item (LOTO, open permit, ESD bypass) to a handover package.
        """
        handover = db.query(ShiftHandoverModel).filter(ShiftHandoverModel.id == handover_id).first()
        if not handover:
            raise ShiftHandoverNotFoundError(f"Handover {handover_id} not found.")

        if handover.is_terminal:
            raise TerminalStateError(f"Cannot add safety item to terminal handover '{handover.state}'.")

        now = datetime.now(timezone.utc)
        item = SafetyCriticalItemModel(
            handover_id=handover_id,
            category=category,
            equipment_tag=equipment_tag,
            description=description,
            active=active,
            acknowledged_by_incoming=False,
            created_at=now,
            updated_at=now
        )
        db.add(item)
        handover.all_safety_items_acknowledged = False
        db.flush()
        return item

    @staticmethod
    def acknowledge_safety_item(
        db: Session,
        item_id: str,
        actor_id: str
    ) -> SafetyCriticalItemModel:
        """
        Record incoming operator acknowledgement for a specific safety critical item.
        """
        item = db.query(SafetyCriticalItemModel).filter(SafetyCriticalItemModel.id == item_id).first()
        if not item:
            raise ShiftHandoverNotFoundError(f"Safety item {item_id} not found.")

        now = datetime.now(timezone.utc)
        item.acknowledged_by_incoming = True
        item.acknowledged_by = actor_id
        item.acknowledged_at = now
        item.updated_at = now

        # Check if all safety items for this handover are now acknowledged
        unack_count = db.query(SafetyCriticalItemModel).filter(
            SafetyCriticalItemModel.handover_id == item.handover_id,
            SafetyCriticalItemModel.active == True,
            SafetyCriticalItemModel.acknowledged_by_incoming == False
        ).count()

        handover = db.query(ShiftHandoverModel).filter(ShiftHandoverModel.id == item.handover_id).first()
        if handover:
            handover.all_safety_items_acknowledged = (unack_count == 0)

        db.flush()
        return item

    @staticmethod
    def execute_transition_atomic(
        db: Session,
        handover_id: str,
        from_state: str,
        to_state: str,
        action: str,
        actor_id: str,
        actor_role: str,
        expected_version: int,
        reason: Optional[str] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        payload_updates: Optional[Dict[str, Any]] = None
    ) -> ShiftHandoverModel:
        """
        Execute an atomic state transition with optimistic concurrency lock, version increment,
        and audit logging in a single database transaction.
        """
        handover = db.query(ShiftHandoverModel).filter(ShiftHandoverModel.id == handover_id).first()
        if not handover:
            raise ShiftHandoverNotFoundError(f"Handover {handover_id} not found.")

        if handover.is_terminal:
            raise TerminalStateError(f"Cannot execute '{action}' on terminal handover in state '{handover.state}'.")

        now = datetime.now(timezone.utc)

        # 1. Optimistic Locking Query Update
        update_vals: Dict[str, Any] = {
            ShiftHandoverModel.state: to_state,
            ShiftHandoverModel.version: ShiftHandoverModel.version + 1,
            ShiftHandoverModel.updated_at: now
        }

        if to_state == "SUBMITTED" and not handover.submitted_at:
            update_vals[ShiftHandoverModel.submitted_at] = now
        elif to_state == "COMPLETED":
            update_vals[ShiftHandoverModel.completed_at] = now
        elif to_state == "CANCELLED":
            update_vals[ShiftHandoverModel.cancelled_at] = now
        elif to_state == "REJECTED":
            update_vals[ShiftHandoverModel.rejected_at] = now

        if payload_updates:
            for k, v in payload_updates.items():
                if hasattr(ShiftHandoverModel, k):
                    update_vals[getattr(ShiftHandoverModel, k)] = v

        rows = db.query(ShiftHandoverModel).filter(
            ShiftHandoverModel.id == handover_id,
            ShiftHandoverModel.version == expected_version,
            ShiftHandoverModel.state == from_state
        ).update(update_vals, synchronize_session=False)

        if rows == 0:
            # Re-read actual current status to provide accurate conflict reason
            current = db.query(ShiftHandoverModel).filter(ShiftHandoverModel.id == handover_id).first()
            if current:
                raise ConcurrencyConflictError(
                    f"Concurrency conflict: Handover is currently in state '{current.state}' (v={current.version}), "
                    f"expected '{from_state}' (v={expected_version})."
                )
            raise ShiftHandoverNotFoundError(f"Handover {handover_id} no longer exists.")

        # 2. Append-only Immutable Audit Record
        audit = ShiftHandoverAuditModel(
            handover_id=handover_id,
            from_state=from_state,
            to_state=to_state,
            action=action,
            actor_id=actor_id,
            actor_role=actor_role,
            reason=reason,
            request_id=request_id,
            session_id=session_id,
            metadata_={"version": expected_version + 1, "action": action},
            created_at=now
        )
        db.add(audit)
        db.flush()

        # Re-fetch updated model
        db.refresh(handover)
        logfire.info(
            f"[ShiftRepo] Transition applied [id={handover_id}]: {from_state} -> {action} -> {to_state} "
            f"(v={handover.version}, actor={actor_id})"
        )
        return handover

    @staticmethod
    def get_audit_trail(db: Session, handover_id: str) -> List[ShiftHandoverAuditModel]:
        """
        Retrieve all audit history entries for a given shift handover ordered chronologically.
        """
        return db.query(ShiftHandoverAuditModel).filter(
            ShiftHandoverAuditModel.handover_id == handover_id
        ).order_by(ShiftHandoverAuditModel.created_at).all()
