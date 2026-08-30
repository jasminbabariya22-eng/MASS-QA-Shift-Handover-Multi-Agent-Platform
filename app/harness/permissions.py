from typing import Dict, List, Set, Optional
import logfire

from app.harness.contracts import ToolPermission, HarnessPolicyDecision


class HarnessPermissionManager:
    """
    Role-Based Access Control (RBAC) and Tool Permission Gateway for AI Harness.
    Ensures agents and users only access capabilities they are explicitly authorized for.
    """

    # All 10 Refinery Domain Operational Roles
    ROLE_PERMISSIONS: Dict[str, Set[ToolPermission]] = {
        "CONSOLE_OPERATOR": {
            ToolPermission.RETRIEVE_DOCUMENT,
            ToolPermission.SEARCH_KNOWLEDGE_BASE,
            ToolPermission.GENERATE_GROUNDED_ANSWER,
            ToolPermission.CREATE_HANDOVER,
            ToolPermission.READ_HANDOVER,
            ToolPermission.UPDATE_HANDOVER,
            ToolPermission.TRANSITION_HANDOVER,
            ToolPermission.MANAGE_SAFETY_ITEMS,
            ToolPermission.READ_LOOP,
            ToolPermission.READ_INSTRUMENT,
            ToolPermission.READ_IO_MAPPING,
            ToolPermission.READ_ENGINEERING_DOCUMENT
        },
        "FIELD_OPERATOR": {
            ToolPermission.RETRIEVE_DOCUMENT,
            ToolPermission.SEARCH_KNOWLEDGE_BASE,
            ToolPermission.GENERATE_GROUNDED_ANSWER,
            ToolPermission.READ_HANDOVER,
            ToolPermission.UPDATE_HANDOVER,
            ToolPermission.READ_LOOP,
            ToolPermission.READ_INSTRUMENT,
            ToolPermission.READ_ENGINEERING_DOCUMENT
        },
        "OUTGOING_OPERATOR": {
            ToolPermission.RETRIEVE_DOCUMENT,
            ToolPermission.SEARCH_KNOWLEDGE_BASE,
            ToolPermission.CREATE_HANDOVER,
            ToolPermission.READ_HANDOVER,
            ToolPermission.UPDATE_HANDOVER,
            ToolPermission.TRANSITION_HANDOVER,
            ToolPermission.MANAGE_SAFETY_ITEMS
        },
        "INCOMING_OPERATOR": {
            ToolPermission.RETRIEVE_DOCUMENT,
            ToolPermission.SEARCH_KNOWLEDGE_BASE,
            ToolPermission.READ_HANDOVER,
            ToolPermission.TRANSITION_HANDOVER,
            ToolPermission.READ_LOOP,
            ToolPermission.READ_INSTRUMENT
        },
        "SHIFT_SUPERVISOR": {
            ToolPermission.RETRIEVE_DOCUMENT,
            ToolPermission.SEARCH_KNOWLEDGE_BASE,
            ToolPermission.GENERATE_GROUNDED_ANSWER,
            ToolPermission.CREATE_HANDOVER,
            ToolPermission.READ_HANDOVER,
            ToolPermission.UPDATE_HANDOVER,
            ToolPermission.TRANSITION_HANDOVER,
            ToolPermission.READ_AUDIT,
            ToolPermission.MANAGE_SAFETY_ITEMS,
            ToolPermission.READ_LOOP,
            ToolPermission.READ_INSTRUMENT,
            ToolPermission.READ_IO_MAPPING,
            ToolPermission.READ_ENGINEERING_DOCUMENT,
            ToolPermission.VALIDATE_LOOP
        },
        "OPERATIONS_ENGINEER": {
            ToolPermission.RETRIEVE_DOCUMENT,
            ToolPermission.SEARCH_KNOWLEDGE_BASE,
            ToolPermission.GENERATE_GROUNDED_ANSWER,
            ToolPermission.READ_HANDOVER,
            ToolPermission.READ_AUDIT,
            ToolPermission.READ_LOOP,
            ToolPermission.READ_INSTRUMENT,
            ToolPermission.READ_IO_MAPPING,
            ToolPermission.READ_ENGINEERING_DOCUMENT,
            ToolPermission.VALIDATE_LOOP
        },
        "MAINTENANCE_LEAD": {
            ToolPermission.RETRIEVE_DOCUMENT,
            ToolPermission.READ_HANDOVER,
            ToolPermission.UPDATE_HANDOVER,
            ToolPermission.MANAGE_SAFETY_ITEMS,
            ToolPermission.READ_INSTRUMENT
        },
        "HSE_REPRESENTATIVE": {
            ToolPermission.RETRIEVE_DOCUMENT,
            ToolPermission.SEARCH_KNOWLEDGE_BASE,
            ToolPermission.READ_HANDOVER,
            ToolPermission.READ_AUDIT,
            ToolPermission.MANAGE_SAFETY_ITEMS
        },
        "PLANT_MANAGER": {
            ToolPermission.RETRIEVE_DOCUMENT,
            ToolPermission.SEARCH_KNOWLEDGE_BASE,
            ToolPermission.GENERATE_GROUNDED_ANSWER,
            ToolPermission.CREATE_HANDOVER,
            ToolPermission.READ_HANDOVER,
            ToolPermission.UPDATE_HANDOVER,
            ToolPermission.TRANSITION_HANDOVER,
            ToolPermission.READ_AUDIT,
            ToolPermission.MANAGE_SAFETY_ITEMS,
            ToolPermission.READ_LOOP,
            ToolPermission.VALIDATE_LOOP
        },
        "ADMIN": {
            ToolPermission.RETRIEVE_DOCUMENT,
            ToolPermission.SEARCH_KNOWLEDGE_BASE,
            ToolPermission.GENERATE_GROUNDED_ANSWER,
            ToolPermission.CREATE_HANDOVER,
            ToolPermission.READ_HANDOVER,
            ToolPermission.UPDATE_HANDOVER,
            ToolPermission.TRANSITION_HANDOVER,
            ToolPermission.READ_AUDIT,
            ToolPermission.MANAGE_SAFETY_ITEMS,
            ToolPermission.READ_LOOP,
            ToolPermission.READ_INSTRUMENT,
            ToolPermission.READ_IO_MAPPING,
            ToolPermission.READ_ENGINEERING_DOCUMENT,
            ToolPermission.VALIDATE_LOOP
        }
    }

    # Agent Tool Whitelists
    AGENT_TOOL_WHITELIST: Dict[str, Set[ToolPermission]] = {
        "qa_technical_agent": {
            ToolPermission.RETRIEVE_DOCUMENT,
            ToolPermission.SEARCH_KNOWLEDGE_BASE,
            ToolPermission.GENERATE_GROUNDED_ANSWER
        },
        "shift_handover_agent": {
            ToolPermission.CREATE_HANDOVER,
            ToolPermission.READ_HANDOVER,
            ToolPermission.UPDATE_HANDOVER,
            ToolPermission.TRANSITION_HANDOVER,
            ToolPermission.READ_AUDIT,
            ToolPermission.MANAGE_SAFETY_ITEMS
        }
    }

    def verify_role_authorization(self, user_role: str, required_permission: ToolPermission) -> bool:
        """
        Verify if the given user role possesses the requested permission.
        """
        if required_permission == ToolPermission.REMOTE_EQUIPMENT_CONTROL:
            logfire.warning(f"[HarnessRBAC] Immediate Denial: Prohibited permission {required_permission}")
            return False

        role_str = user_role.upper().strip()
        perms = self.ROLE_PERMISSIONS.get(role_str, set())
        allowed = required_permission in perms
        if not allowed:
            logfire.warning(f"[HarnessRBAC] Role '{role_str}' denied for permission '{required_permission}'")
        return allowed

    def verify_agent_tool_permission(self, agent_id: str, tool_permission: ToolPermission) -> bool:
        """
        Verify if the given agent is authorized to invoke the specified tool.
        """
        if tool_permission == ToolPermission.REMOTE_EQUIPMENT_CONTROL:
            logfire.error(f"[HarnessAgent] Prohibited autonomous action '{tool_permission}' denied for agent '{agent_id}'")
            return False

        allowed_tools = self.AGENT_TOOL_WHITELIST.get(agent_id, set())
        allowed = tool_permission in allowed_tools
        if not allowed:
            logfire.warning(f"[HarnessAgent] Agent '{agent_id}' attempted unauthorized tool '{tool_permission}'")
        return allowed


# Global Permission Manager Singleton
permission_manager = HarnessPermissionManager()
