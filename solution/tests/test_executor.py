"""Tests for parallel execution and retry handling."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from spec_agent.executor import ExecutorConfig, PlanExecutor
from spec_agent.models import AgentRunState, BudgetState, ExecutionPlan, PlanStep, PromptVariant


class StubToolRegistry:
    """Mock tool registry for testing executor."""

    def __init__(self) -> None:
        self.calls = {}

    def execute(self, tool_name: str, tool_input: dict) -> SimpleNamespace:
        """Mock tool execution: succeed except on first 'retry' call."""
        key = str(tool_input.get("id", "unknown"))
        self.calls[key] = self.calls.get(key, 0) + 1
        succeed = not (key == "retry" and self.calls[key] == 1)
        
        return SimpleNamespace(
            ok=succeed,  # NOTE: executor expects 'ok', not 'success'
            summary=f"{tool_name} {key}",
            raw_output=f"{tool_name} {key}",
            data={"duration_ms": 1},
            citations=[],
            error=None if succeed else "temporary failure",
        )


def test_executor_runs_parallel_steps_and_retries_failures():
    """Test that executor handles parallel steps and retries failed calls."""
    registry = StubToolRegistry()
    executor = PlanExecutor(tool_registry=registry, config=ExecutorConfig(max_tool_retries=2))
    
    plan = ExecutionPlan(
        objective="Test plan",
        completion_criteria=["finish"],
        expected_answer_shape="n/a",
        possible_contradictions=[],
        prompt_variant=PromptVariant.B,
        steps=[
            PlanStep(
                step_id="a",
                description="doc",
                tool_name="doc_qa",
                tool_input={"id": "a"},
                expected_evidence="a",
                completion_signal="a",
                parallel_group="research",
            ),
            PlanStep(
                step_id="retry",
                description="kb",
                tool_name="kb_lookup",
                tool_input={"id": "retry"},
                expected_evidence="b",
                completion_signal="b",
                parallel_group="research",
            ),
        ],
    )
    
    run_state = AgentRunState(
        termination_reason="not_started",
        model_calls=0,
        tool_calls=0,
        tool_failures=0,
        tool_retries=0,
        parallel_batches=0,
        cycles=0,
        failure_notes=[],
        budget=BudgetState(max_budget_usd=0.25),
    )

    # Execute the plan
    tool_calls, observations, completed = executor.execute(plan=plan, run_state=run_state)

    # Verify results
    assert completed == {"a", "retry"}
    assert len(observations) == 2
    assert run_state.parallel_batches == 1
    # One retry for the "retry" step
    assert run_state.tool_retries >= 1
    # The "retry" step should have been called twice (once fail, once succeed)
    assert registry.calls["retry"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
