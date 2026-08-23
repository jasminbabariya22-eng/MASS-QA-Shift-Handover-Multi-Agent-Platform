import time
from typing import List, Optional
import logfire

from app.harness.contracts import ExecutionBudget


class BudgetExceededError(Exception):
    def __init__(self, message: str, code: str = "EXECUTION_BUDGET_EXCEEDED"):
        super().__init__(message)
        self.code = code


class AgentLoopDetectedError(BudgetExceededError):
    def __init__(self, message: str):
        super().__init__(message, code="AGENT_EXECUTION_LOOP_DETECTED")


class AgentDepthExceededError(BudgetExceededError):
    def __init__(self, message: str):
        super().__init__(message, code="AGENT_EXECUTION_DEPTH_EXCEEDED")


class ExecutionBudgetTracker:
    """
    Tracks and enforces resource, depth, and recursion limits across agent executions.
    Prevents infinite agent cycles, resource exhaustion, and runaway sub-tasks.
    """

    def __init__(self, budget: Optional[ExecutionBudget] = None):
        self.budget = budget or ExecutionBudget()
        self.start_time = time.time()
        self.call_chain: List[str] = []
        self.tool_call_count = 0
        self.agent_call_count = 0
        self.retry_count = 0

    def record_agent_invocation(self, agent_id: str) -> None:
        """
        Record a dispatched agent call, checking depth, call count, and cyclic loops.
        """
        self.agent_call_count += 1
        self.call_chain.append(agent_id)

        # 1. Check Max Agent Calls
        if self.agent_call_count > self.budget.max_agent_calls:
            raise BudgetExceededError(
                f"Agent call budget exceeded: {self.agent_call_count} > {self.budget.max_agent_calls}",
                code="MAX_AGENT_CALLS_EXCEEDED"
            )

        # 2. Check Depth
        current_depth = len(self.call_chain)
        if current_depth > self.budget.max_depth:
            raise AgentDepthExceededError(
                f"Agent invocation depth limit exceeded: {current_depth} > {self.budget.max_depth}"
            )

        # 3. Detect Recursion / Infinite Agent Loops
        # Check for immediate consecutive repeats e.g. [A, A, A]
        if len(self.call_chain) >= 3 and self.call_chain[-1] == self.call_chain[-2] == self.call_chain[-3]:
            raise AgentLoopDetectedError(f"Infinite agent loop detected on '{agent_id}'")

        # Check for alternating cycles e.g. [A, B, A, B]
        if len(self.call_chain) >= 4:
            if self.call_chain[-1] == self.call_chain[-3] and self.call_chain[-2] == self.call_chain[-4]:
                raise AgentLoopDetectedError(
                    f"Cyclic agent loop detected between '{self.call_chain[-2]}' and '{self.call_chain[-1]}'"
                )

        # 4. Check Duration
        elapsed = time.time() - self.start_time
        if elapsed > self.budget.max_execution_time_seconds:
            raise BudgetExceededError(
                f"Execution time budget exceeded: {elapsed:.2f}s > {self.budget.max_execution_time_seconds}s",
                code="EXECUTION_TIMEOUT"
            )

    def record_tool_call(self, tool_name: str) -> None:
        """
        Record a tool call and verify against tool budget.
        """
        self.tool_call_count += 1
        if self.tool_call_count > self.budget.max_tool_calls:
            raise BudgetExceededError(
                f"Tool invocation budget exceeded: {self.tool_call_count} > {self.budget.max_tool_calls}",
                code="MAX_TOOL_CALLS_EXCEEDED"
            )

    def record_retry(self) -> bool:
        """
        Record a transient retry attempt. Returns True if within budget, False otherwise.
        """
        self.retry_count += 1
        return self.retry_count <= self.budget.max_retries
