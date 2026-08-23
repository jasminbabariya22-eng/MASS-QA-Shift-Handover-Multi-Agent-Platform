from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
import logfire

from app.agents.shift.contracts import (
    ShiftHandover,
    ShiftHandoverData,
    ShiftHandoverState,
    ShiftHandoverRole,
    ShiftHandoverAction,
    ShiftHandoverTransitionResult,
    SafetyCriticalItem,
    ShiftType,
)
from app.agents.shift.workflow import shift_workflow_engine, ShiftHandoverWorkflowEngine
from app.db.models.shift_handover import ShiftHandoverModel, SafetyCriticalItemModel, ShiftHandoverAuditModel
from app.repositories.shift_handover_repository import (
    ShiftHandoverRepository,
    ShiftHandoverNotFoundError,
    ConcurrencyConflictError,
    TerminalStateError,
)


class ShiftHandoverService:
    """
    High-level Shift Handover orchestration service coordinating Step 5 workflow engine validation
    with PostgreSQL transactional persistence.
    """

    def __init__(self, workflow_engine: Optional[ShiftHandoverWorkflowEngine] = None):
        self.workflow_engine = workflow_engine or shift_workflow_engine

    @staticmethod
    def orm_to_domain(model: ShiftHandoverModel) -> ShiftHandover:
        """
        Convert SQLAlchemy ShiftHandoverModel to Pydantic ShiftHandover domain contract.
        """
        safety_items = [
            SafetyCriticalItem(
                item_id=item.id,
                category=item.category,
                equipment_tag=item.equipment_tag,
                description=item.description,
                active=item.active,
                acknowledged_by_incoming=item.acknowledged_by_incoming,
                created_at=item.created_at
            )
            for item in (model.safety_items or [])
        ]

        data = ShiftHandoverData(
            unit_id=model.unit_id,
            unit_name=model.unit_name,
            shift_type=ShiftType(model.shift_type) if model.shift_type in ShiftType._value2member_map_ else ShiftType.DAY,
            shift_date=model.shift_date,
            outgoing_operator_id=model.outgoing_operator_id,
            outgoing_operator_name=model.outgoing_operator_name,
            incoming_operator_id=model.incoming_operator_id,
            incoming_operator_name=model.incoming_operator_name,
            supervisor_id=model.supervisor_id,
            operational_summary=model.operational_summary or "",
            equipment_abnormalities=model.equipment_abnormalities or [],
            open_permits=model.open_permits or [],
            loto_isolations=model.loto_isolations or [],
            carry_forward_actions=model.carry_forward_actions or [],
            safety_items=safety_items,
            all_safety_items_acknowledged=model.all_safety_items_acknowledged,
            notes=model.notes
        )

        return ShiftHandover(
            handover_id=model.id,
            workflow_version=model.workflow_version,
            state=ShiftHandoverState(model.state),
            data=data,
            version=model.version,
            created_at=model.created_at,
            updated_at=model.updated_at,
            submitted_at=model.submitted_at,
            completed_at=model.completed_at,
            audit_trail=[]
        )

    def create_handover(
        self,
        db: Session,
        data: ShiftHandoverData,
        actor_id: str,
        actor_role: ShiftHandoverRole,
        handover_id: Optional[str] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Tuple[ShiftHandoverModel, ShiftHandoverTransitionResult]:
        """
        Create a new shift handover in DRAFT state and persist to database.
        """
        domain_obj, result = self.workflow_engine.create_handover(
            data=data,
            actor_id=actor_id,
            actor_role=actor_role,
            handover_id=handover_id
        )

        orm_model = ShiftHandoverRepository.create_handover(
            db=db,
            unit_id=data.unit_id,
            shift_type=data.shift_type.value,
            shift_date=data.shift_date,
            outgoing_operator_id=data.outgoing_operator_id,
            operational_summary=data.operational_summary,
            unit_name=data.unit_name,
            outgoing_operator_name=data.outgoing_operator_name,
            incoming_operator_id=data.incoming_operator_id,
            incoming_operator_name=data.incoming_operator_name,
            supervisor_id=data.supervisor_id,
            equipment_abnormalities=data.equipment_abnormalities,
            open_permits=data.open_permits,
            loto_isolations=data.loto_isolations,
            carry_forward_actions=data.carry_forward_actions,
            notes=data.notes,
            handover_id=domain_obj.handover_id,
            actor_role=actor_role.value,
            request_id=request_id,
            session_id=session_id
        )

        if data.safety_items:
            for item in data.safety_items:
                ShiftHandoverRepository.add_safety_item(
                    db=db,
                    handover_id=orm_model.id,
                    category=item.category,
                    equipment_tag=item.equipment_tag,
                    description=item.description,
                    active=item.active
                )

        return orm_model, result

    def get_handover(self, db: Session, handover_id: str) -> Optional[ShiftHandoverModel]:
        """
        Retrieve handover by ID or reference number.
        """
        return ShiftHandoverRepository.get_by_id(db, handover_id)

    def list_handovers(
        self,
        db: Session,
        unit_id: Optional[str] = None,
        state: Optional[str] = None,
        shift_date: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[ShiftHandoverModel]:
        """
        List handovers filtered by unit, state, or shift date.
        """
        return ShiftHandoverRepository.list_handovers(db, unit_id=unit_id, state=state, shift_date=shift_date, limit=limit, offset=offset)

    def update_handover(
        self,
        db: Session,
        handover_id: str,
        expected_version: int,
        updates: Dict[str, Any],
        actor_id: str,
        actor_role: str = "CONSOLE_OPERATOR"
    ) -> ShiftHandoverModel:
        """
        Update mutable draft/returned handover details with optimistic concurrency check.
        """
        return ShiftHandoverRepository.update_data(
            db=db,
            handover_id=handover_id,
            expected_version=expected_version,
            updates=updates,
            actor_id=actor_id,
            actor_role=actor_role
        )

    def add_safety_item(
        self,
        db: Session,
        handover_id: str,
        category: str,
        equipment_tag: str,
        description: str,
        active: bool = True
    ) -> SafetyCriticalItemModel:
        """
        Attach a safety-critical item (LOTO / PTW / ESD bypass) to a handover.
        """
        return ShiftHandoverRepository.add_safety_item(
            db=db,
            handover_id=handover_id,
            category=category,
            equipment_tag=equipment_tag,
            description=description,
            active=active
        )

    def acknowledge_safety_item(
        self,
        db: Session,
        item_id: str,
        actor_id: str
    ) -> SafetyCriticalItemModel:
        """
        Record incoming operator acknowledgement for a safety item.
        """
        return ShiftHandoverRepository.acknowledge_safety_item(
            db=db,
            item_id=item_id,
            actor_id=actor_id
        )

    def get_audit_history(self, db: Session, handover_id: str) -> List[ShiftHandoverAuditModel]:
        """
        Retrieve immutable audit trail for a handover.
        """
        return ShiftHandoverRepository.get_audit_trail(db, handover_id)

    def transition_handover(
        self,
        db: Session,
        handover_id: str,
        action: ShiftHandoverAction,
        actor_id: str,
        actor_role: ShiftHandoverRole,
        expected_version: Optional[int] = None,
        reason: Optional[str] = None,
        payload_updates: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> ShiftHandoverTransitionResult:
        """
        Execute an atomic state transition:
        1. Load current model from database
        2. Convert to domain model and run Step 5 workflow validation
        3. If valid, execute atomic optimistic-lock database update + audit insertion
        """
        orm_model = ShiftHandoverRepository.get_by_id(db, handover_id)
        if not orm_model:
            raise ShiftHandoverNotFoundError(f"Handover {handover_id} not found.")

        target_version = expected_version if expected_version is not None else orm_model.version
        if target_version != orm_model.version:
            raise ConcurrencyConflictError(
                f"Concurrency conflict: Current version is {orm_model.version}, but {target_version} was expected."
            )

        domain_handover = self.orm_to_domain(orm_model)

        workflow_res = self.workflow_engine.execute_transition(
            handover=domain_handover,
            action=action,
            actor_id=actor_id,
            actor_role=actor_role,
            reason=reason,
            expected_version=target_version,
            payload_updates=payload_updates
        )

        if not workflow_res.success:
            return workflow_res

        try:
            updated_model = ShiftHandoverRepository.execute_transition_atomic(
                db=db,
                handover_id=handover_id,
                from_state=workflow_res.previous_state.value,
                to_state=workflow_res.current_state.value,
                action=action.value,
                actor_id=actor_id,
                actor_role=actor_role.value,
                expected_version=target_version,
                reason=reason,
                request_id=request_id,
                session_id=session_id,
                payload_updates=payload_updates
            )
            return workflow_res
        except ConcurrencyConflictError:
            raise
        except Exception as e:
            logfire.error(f"[ShiftService] Database error during transition: {e}")
            raise


shift_handover_service = ShiftHandoverService()
