import time
import uuid
from typing import Optional, List, Dict, Any, Generator
from datetime import datetime, timezone
import logfire

from app.db.database import SessionLocal
from app.agents.base import BaseAgent
from app.agents.contracts import (
    AgentRequest,
    RequestContext,
    AgentResult,
    AgentResponse,
    AgentErrorCode,
)
from app.agents.shift.contracts import (
    ShiftHandover,
    ShiftHandoverData,
    ShiftHandoverState,
    ShiftHandoverRole,
    ShiftHandoverAction,
    SafetyCriticalItem,
    ShiftType,
)
from app.agents.shift.command import ShiftCommand, ShiftCommandType
from app.agents.shift.extractor import ShiftCommandExtractor
from app.repositories.shift_handover_repository import (
    ShiftHandoverNotFoundError,
    ConcurrencyConflictError,
    TerminalStateError,
)


class ShiftHandoverAgent(BaseAgent):
    """
    Production Shift Handover Conversational Agent.
    
    Serves as the conversational coordination layer translating operator queries into
    typed commands and delegating to the deterministic Step 5 Workflow Engine and
    Step 6 PostgreSQL persistence layer.
    """

    def __init__(
        self,
        service: Optional[Any] = None,
        extractor: Optional[ShiftCommandExtractor] = None,
        session_factory: Optional[Any] = None
    ):
        super().__init__(
            agent_id="shift_handover_agent",
            name="MASS Shift Handover Agent",
            description="Manages plant shift logs, operator turnover workflows, equipment safety status, and audit history.",
            capabilities=[
                "create_handover",
                "draft_handover",
                "get_handover",
                "list_handovers",
                "transition_handover",
                "safety_status",
                "audit_history",
                "operational_queries",
            ],
            supports_streaming=True
        )
        self._service = service
        self.extractor = extractor or ShiftCommandExtractor()
        self.session_factory = session_factory or SessionLocal

    @property
    def service(self):
        if self._service is None:
            from app.services.shift_handover_service import shift_handover_service
            self._service = shift_handover_service
        return self._service

    def execute(self, request: AgentRequest, context: RequestContext) -> AgentResult:
        """
        Synchronous execution entrypoint translating natural-language request into
        deterministic workflow and database operations.
        """
        t_start = time.time()
        logfire.info(f"[{self.agent_id}] Executing query: '{request.message[:60]}...' [req_id={request.request_id}]")

        # 1. Resolve User Identity and Role
        actor_id = request.user_id or context.user_id or "operator_session"
        role_str = request.user_role or context.user_role or "CONSOLE_OPERATOR"
        try:
            actor_role = ShiftHandoverRole(role_str)
        except ValueError:
            actor_role = ShiftHandoverRole.CONSOLE_OPERATOR

        # 2. Extract Structured Command
        command = self.extractor.extract(request.message, context.metadata)

        # 3. Handle Clarifications
        if command.requires_clarification:
            return self._build_result(
                request_id=request.request_id,
                response=command.clarification_prompt or "Could you please clarify which unit or handover you are referring to?",
                query_type="clarification_required",
                confidence="medium",
                t_start=t_start,
                metadata={"requires_clarification": True}
            )

        # 4. Handle High-Impact Confirmation Requests
        if command.requires_confirmation:
            return self._build_result(
                request_id=request.request_id,
                response=command.confirmation_prompt or "Please confirm if you wish to proceed with this irreversible action.",
                query_type="confirmation_required",
                confidence="high",
                t_start=t_start,
                metadata={"requires_confirmation": True, "pending_action": command.action.value if command.action else None}
            )

        # 5. Database-Backed Execution Dispatch through Service Layer
        db = self.session_factory()
        try:
            cmd_type = command.command_type

            if cmd_type == ShiftCommandType.CREATE_HANDOVER:
                return self._handle_create(db, command, actor_id, actor_role, request, t_start)

            elif cmd_type in (
                ShiftCommandType.SUBMIT_HANDOVER,
                ShiftCommandType.REVIEW_HANDOVER,
                ShiftCommandType.APPROVE_HANDOVER,
                ShiftCommandType.RETURN_HANDOVER,
                ShiftCommandType.REJECT_HANDOVER,
                ShiftCommandType.ACKNOWLEDGE_HANDOVER,
                ShiftCommandType.CANCEL_HANDOVER,
                ShiftCommandType.ESCALATE_HANDOVER
            ):
                return self._handle_transition(db, command, actor_id, actor_role, request, t_start)

            elif cmd_type == ShiftCommandType.UPDATE_HANDOVER:
                return self._handle_update(db, command, actor_id, actor_role, request, t_start)

            elif cmd_type == ShiftCommandType.GET_SAFETY_STATUS:
                return self._handle_safety_status(db, command, request, t_start)

            elif cmd_type == ShiftCommandType.ADD_SAFETY_ITEM:
                return self._handle_add_safety_item(db, command, request, t_start)

            elif cmd_type == ShiftCommandType.ACKNOWLEDGE_SAFETY_ITEM:
                return self._handle_ack_safety_item(db, command, actor_id, request, t_start)

            elif cmd_type == ShiftCommandType.GET_AUDIT_HISTORY:
                return self._handle_audit_history(db, command, request, t_start)

            elif cmd_type == ShiftCommandType.LIST_HANDOVERS:
                return self._handle_list(db, command, request, t_start)

            else:  # GET_HANDOVER or default query
                return self._handle_get(db, command, request, t_start)

        except ConcurrencyConflictError as e:
            return self._build_result(
                request_id=request.request_id,
                response="⚠️ **Concurrency Conflict**: This handover was modified by another user. Please refresh and try again.",
                query_type="concurrency_conflict",
                status="conflict",
                success=False,
                t_start=t_start,
                error={"code": AgentErrorCode.INTERNAL_ERROR.value, "message": str(e)}
            )
        except TerminalStateError as e:
            return self._build_result(
                request_id=request.request_id,
                response=f"⚠️ **Terminal State**: {str(e)}",
                query_type="terminal_locked",
                status="error",
                success=False,
                t_start=t_start,
                error={"code": AgentErrorCode.INVALID_REQUEST.value, "message": str(e)}
            )
        except Exception as e:
            logfire.error(f"[{self.agent_id}] Unhandled error: {e}")
            return self._build_result(
                request_id=request.request_id,
                response="An error occurred while accessing the shift handover system. Please verify the unit or handover details and try again.",
                query_type="error",
                status="error",
                success=False,
                t_start=t_start,
                error={"code": AgentErrorCode.AGENT_EXECUTION_ERROR.value, "message": "Database operational error."}
            )
        finally:
            db.close()

    def stream(self, request: AgentRequest, context: RequestContext) -> Generator[Dict[str, Any], None, None]:
        """
        Streaming execution yielding step events and final result.
        """
        yield {"type": "progress", "step": "interpreting_request", "message": "Interpreting operational request..."}
        result = self.execute(request, context)
        yield {"type": "progress", "step": "completed", "message": "Operational transaction processed."}
        yield {"type": "token", "content": result.response}
        if result.citations:
            yield {"type": "citations", "citations": result.citations}
        yield {
            "type": "done",
            "request_id": result.request_id,
            "metadata": result.metadata
        }

    # --- Internal Command Handlers ---

    def _resolve_handover(self, db: Any, command: ShiftCommand) -> Optional[Any]:
        """Helper to resolve target handover through Service layer."""
        if command.handover_number:
            return self.service.get_handover(db, command.handover_number)
        if command.unit_id:
            candidates = self.service.list_handovers(db, unit_id=command.unit_id, limit=5)
            if candidates:
                for c in candidates:
                    if not getattr(c, "is_terminal", False):
                        return c
                return candidates[0]
        return None

    def _handle_create(self, db: Any, command: ShiftCommand, actor_id: str, actor_role: ShiftHandoverRole, request: AgentRequest, t_start: float) -> AgentResult:
        unit_id = command.unit_id or "CDU-101"
        data = ShiftHandoverData(
            unit_id=unit_id,
            unit_name=f"Plant Unit {unit_id}",
            shift_type=command.shift_type or ShiftType.DAY,
            shift_date=command.shift_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            outgoing_operator_id=actor_id,
            operational_summary=command.operational_summary or "Shift initiated via conversational agent."
        )

        model, result = self.service.create_handover(
            db=db,
            data=data,
            actor_id=actor_id,
            actor_role=actor_role,
            handover_id=None,
            request_id=request.request_id,
            session_id=request.session_id
        )
        if hasattr(db, "commit"):
            db.commit()

        msg = (
            f"✅ **Created Shift Handover Draft**:\n"
            f"- **Handover Number**: `{model.handover_number}`\n"
            f"- **Unit**: `{model.unit_id}`\n"
            f"- **Shift**: `{model.shift_type}` ({model.shift_date})\n"
            f"- **Current State**: `{model.state}` (v{model.version})"
        )
        return self._build_result(request.request_id, msg, "create_handover", t_start=t_start, metadata={"handover_id": model.id, "handover_number": model.handover_number, "state": model.state})

    def _handle_transition(self, db: Any, command: ShiftCommand, actor_id: str, actor_role: ShiftHandoverRole, request: AgentRequest, t_start: float) -> AgentResult:
        model = self._resolve_handover(db, command)
        if not model:
            return self._build_result(
                request.request_id,
                "I found multiple or no active handovers for this action. Please specify the handover number (e.g. `SHO-20260822-CDU101-XXXX`).",
                "handover_not_found",
                t_start=t_start,
                metadata={"requires_clarification": True}
            )

        if not command.action:
            return self._build_result(request.request_id, "No valid workflow action specified.", "invalid_action", t_start=t_start, success=False)

        payload_updates = {}
        if command.action == ShiftHandoverAction.ACKNOWLEDGE:
            payload_updates["incoming_operator_id"] = actor_id

        res = self.service.transition_handover(
            db=db,
            handover_id=model.id,
            action=command.action,
            actor_id=actor_id,
            actor_role=actor_role,
            expected_version=model.version,
            reason=command.reason,
            payload_updates=payload_updates or None,
            request_id=request.request_id,
            session_id=request.session_id
        )

        if not res.success:
            err_details = "; ".join(res.validation_errors) if res.validation_errors else res.message
            msg = f"❌ **Transition Blocked**: Cannot execute `{command.action.value}` on handover `{model.handover_number}` ({model.state}).\n*Reason*: {err_details}"
            return self._build_result(request.request_id, msg, "transition_failed", success=False, t_start=t_start, metadata={"validation_errors": res.validation_errors})

        if hasattr(db, "commit"):
            db.commit()
        if hasattr(db, "refresh"):
            db.refresh(model)

        msg = (
            f"✅ **Handover Updated Successfully**:\n"
            f"- **Reference**: `{model.handover_number}`\n"
            f"- **Action**: `{command.action.value}`\n"
            f"- **New State**: `{model.state}` (v{model.version})"
        )
        return self._build_result(request.request_id, msg, "transition_success", t_start=t_start, metadata={"handover_id": model.id, "state": model.state, "action": command.action.value})

    def _handle_update(self, db: Any, command: ShiftCommand, actor_id: str, actor_role: ShiftHandoverRole, request: AgentRequest, t_start: float) -> AgentResult:
        model = self._resolve_handover(db, command)
        if not model:
            return self._build_result(request.request_id, "Please specify which handover to update.", "handover_not_found", t_start=t_start)

        updated = self.service.update_handover(
            db=db,
            handover_id=model.id,
            expected_version=model.version,
            updates=command.updates,
            actor_id=actor_id,
            actor_role=actor_role.value
        )
        if hasattr(db, "commit"):
            db.commit()

        msg = f"📝 **Draft Updated**: Note added to handover `{model.handover_number}`."
        return self._build_result(request.request_id, msg, "update_handover", t_start=t_start, metadata={"handover_id": model.id})

    def _handle_get(self, db: Any, command: ShiftCommand, request: AgentRequest, t_start: float) -> AgentResult:
        model = self._resolve_handover(db, command)
        if not model:
            return self._build_result(request.request_id, "No active shift handover found for the requested unit.", "handover_not_found", t_start=t_start)

        msg = (
            f"📋 **Shift Handover Status**:\n"
            f"- **Reference**: `{model.handover_number}`\n"
            f"- **Unit**: `{model.unit_id}` ({model.unit_name or 'N/A'})\n"
            f"- **Shift**: `{model.shift_type}` ({model.shift_date})\n"
            f"- **State**: `{model.state}` (v{model.version})\n"
            f"- **Outgoing Operator**: `{model.outgoing_operator_id}`\n"
            f"- **Incoming Operator**: `{model.incoming_operator_id or 'Pending Assignment'}`\n"
            f"- **Summary**: {model.operational_summary or 'None logged'}\n"
            f"- **Active Safety Items**: {len(model.safety_items or [])}"
        )
        citations = [{
            "source_type": "SHIFT_DATABASE",
            "document_name": "PostgreSQL: shift_handovers",
            "record_id": model.handover_number,
            "unit_id": model.unit_id,
            "state": model.state
        }]
        return self._build_result(request.request_id, msg, "get_handover", t_start=t_start, citations=citations, metadata={"handover_id": model.id, "state": model.state})

    def _handle_list(self, db: Any, command: ShiftCommand, request: AgentRequest, t_start: float) -> AgentResult:
        items = self.service.list_handovers(db, unit_id=command.unit_id, limit=5)
        if not items:
            return self._build_result(request.request_id, "No shift handovers found in the system.", "list_handovers", t_start=t_start)

        lines = ["📋 **Recent Shift Handovers**:"]
        for item in items:
            lines.append(f"- `{item.handover_number}` | Unit: `{item.unit_id}` | `{item.shift_type}` | **{item.state}**")
        return self._build_result(request.request_id, "\n".join(lines), "list_handovers", t_start=t_start)

    def _handle_safety_status(self, db: Any, command: ShiftCommand, request: AgentRequest, t_start: float) -> AgentResult:
        model = self._resolve_handover(db, command)
        if not model:
            return self._build_result(request.request_id, "Please specify a unit or handover to inspect safety items.", "safety_status", t_start=t_start)

        if not model.safety_items:
            return self._build_result(request.request_id, f"🛡️ Handover `{model.handover_number}` currently has **no active safety items** (LOTO / PTW / ESD bypasses).", "safety_status", t_start=t_start)

        lines = [f"🛡️ **Safety Critical Items for {model.handover_number}**:"]
        for it in model.safety_items:
            status = "✅ Acknowledged" if it.acknowledged_by_incoming else "⚠️ PENDING ACKNOWLEDGEMENT"
            lines.append(f"- **[{it.category}]** Tag: `{it.equipment_tag}` — {it.description} ({status})")

        return self._build_result(request.request_id, "\n".join(lines), "safety_status", t_start=t_start, metadata={"safety_count": len(model.safety_items)})

    def _handle_add_safety_item(self, db: Any, command: ShiftCommand, request: AgentRequest, t_start: float) -> AgentResult:
        model = self._resolve_handover(db, command)
        if not model:
            return self._build_result(request.request_id, "Please specify which handover to attach the safety item to.", "add_safety_failed", t_start=t_start)

        item = self.service.add_safety_item(
            db=db,
            handover_id=model.id,
            category=command.safety_category or "LOTO",
            equipment_tag=command.equipment_tag or "GENERAL",
            description=command.description or "Safety observation logged via agent."
        )
        if hasattr(db, "commit"):
            db.commit()

        msg = f"🛡️ **Safety Item Attached**: `{item.category}` tag `{item.equipment_tag}` logged to handover `{model.handover_number}`."
        return self._build_result(request.request_id, msg, "add_safety_success", t_start=t_start, metadata={"safety_item_id": item.id})

    def _handle_ack_safety_item(self, db: Any, command: ShiftCommand, actor_id: str, request: AgentRequest, t_start: float) -> AgentResult:
        model = self._resolve_handover(db, command)
        if not model or not getattr(model, "safety_items", None):
            return self._build_result(request.request_id, "No safety items found for acknowledgement.", "ack_safety_failed", t_start=t_start)

        ack_count = 0
        for item in model.safety_items:
            if not getattr(item, "acknowledged_by_incoming", False):
                iid = getattr(item, "id", getattr(item, "item_id", str(uuid.uuid4())))
                self.service.acknowledge_safety_item(db=db, item_id=iid, actor_id=actor_id)
                setattr(item, "acknowledged_by_incoming", True)
                ack_count += 1
        if hasattr(db, "commit"):
            db.commit()

        msg = f"✅ **Acknowledged {ack_count} safety item(s)** on handover `{model.handover_number}`."
        return self._build_result(request.request_id, msg, "ack_safety_success", t_start=t_start)

    def _handle_audit_history(self, db: Any, command: ShiftCommand, request: AgentRequest, t_start: float) -> AgentResult:
        model = self._resolve_handover(db, command)
        if not model:
            return self._build_result(request.request_id, "Please specify a handover to inspect audit history.", "audit_history", t_start=t_start)

        audits = self.service.get_audit_history(db, model.id)
        lines = [f"📜 **Audit Trail for {model.handover_number}**:"]
        for a in audits:
            ts = a.created_at.strftime("%Y-%m-%d %H:%M:%S") if getattr(a, "created_at", None) else "N/A"
            r = f" (Reason: {a.reason})" if getattr(a, "reason", None) else ""
            lines.append(f"- `{ts}` | **{a.action}** | `{a.from_state} -> {a.to_state}` | Actor: `{a.actor_id}` ({a.actor_role}){r}")

        return self._build_result(request.request_id, "\n".join(lines), "audit_history", t_start=t_start, metadata={"audit_count": len(audits)})

    def _build_result(
        self,
        request_id: str,
        response: str,
        query_type: str,
        t_start: float,
        success: bool = True,
        status: str = "success",
        confidence: str = "high",
        citations: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[Dict[str, Any]] = None
    ) -> AgentResult:
        t_exec = round((time.time() - t_start) * 1000, 2)
        return AgentResult(
            request_id=request_id,
            agent_id=self.agent_id,
            status=status,
            success=success,
            response=response,
            citations=citations or [],
            confidence=confidence,
            query_type=query_type,
            grounded=True,
            execution_time_ms=t_exec,
            metadata=metadata or {},
            error=error
        )
