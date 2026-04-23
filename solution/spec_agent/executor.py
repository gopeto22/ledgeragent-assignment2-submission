"""Concurrent plan execution for LedgerAgent."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Iterable

from .models import AgentRunState, ExecutionPlan, PlanStep, ToolCall, ToolObservation
from .tools import ToolRegistry


@dataclass(frozen=True)
class ExecutorConfig:
    """Execution limits and retry settings."""

    parallel_workers: int = 4
    max_tool_retries: int = 2


class PlanExecutor:
    """Execute a plan with dependency awareness and parallel batches."""

    def __init__(self, *, tool_registry: ToolRegistry, config: ExecutorConfig) -> None:
        self.tool_registry = tool_registry
        self.config = config

    def execute(
        self,
        *,
        plan: ExecutionPlan,
        run_state: AgentRunState,
        already_completed: set[str] | None = None,
    ) -> tuple[list[ToolCall], list[ToolObservation], set[str]]:
        completed = set(already_completed or set())
        failed: set[str] = set()
        pending = {step.step_id: step for step in plan.steps if step.step_id not in completed}
        tool_calls: list[ToolCall] = []
        observations: list[ToolObservation] = []

        while pending:
            ready_steps = [
                step
                for step in pending.values()
                if all(dep in completed for dep in step.depends_on)
                and not any(dep in failed for dep in step.depends_on)
            ]
            if not ready_steps:
                run_state.failure_notes.append(
                    "Execution stopped because remaining steps had failed or unresolved dependencies."
                )
                break

            groups = _group_ready_steps(ready_steps)
            for group_steps in groups:
                run_state.parallel_batches += 1
                if len(group_steps) == 1:
                    call_records, observation = self._execute_step(group_steps[0])
                    tool_calls.extend(call_records)
                    observations.append(observation)
                    self._update_state(run_state, call_records, observation)
                    completed.add(group_steps[0].step_id) if observation.success else failed.add(group_steps[0].step_id)
                    pending.pop(group_steps[0].step_id, None)
                    continue

                with ThreadPoolExecutor(max_workers=min(len(group_steps), self.config.parallel_workers)) as pool:
                    futures = {
                        pool.submit(self._execute_step, step): step for step in group_steps
                    }
                    for future in as_completed(futures):
                        step = futures[future]
                        call_records, observation = future.result()
                        tool_calls.extend(call_records)
                        observations.append(observation)
                        self._update_state(run_state, call_records, observation)
                        completed.add(step.step_id) if observation.success else failed.add(step.step_id)
                        pending.pop(step.step_id, None)

        return tool_calls, observations, completed

    def _execute_step(self, step: PlanStep) -> tuple[list[ToolCall], ToolObservation]:
        call_records: list[ToolCall] = []
        last_observation: ToolObservation | None = None

        for attempt in range(1, self.config.max_tool_retries + 1):
            result = self.tool_registry.execute(step.tool_name, step.tool_input)
            duration_ms = int(result.data.get("duration_ms", 0))
            call_records.append(
                ToolCall(
                    step_id=step.step_id,
                    tool_name=step.tool_name,
                    tool_input=step.tool_input,
                    parallel_group=step.parallel_group,
                    attempt=attempt,
                    success=result.ok,
                    duration_ms=duration_ms,
                    error=result.error,
                    fallback_used=False,
                )
            )
            last_observation = ToolObservation(
                step_id=step.step_id,
                tool_name=step.tool_name,
                success=result.ok,
                summary=result.summary,
                raw_output=result.raw_output,
                data=result.data,
                citations=result.citations,
                error=result.error,
                duration_ms=duration_ms,
                attempts=attempt,
            )
            if result.ok or attempt >= self.config.max_tool_retries:
                return call_records, last_observation

        assert last_observation is not None
        return call_records, last_observation

    def _update_state(
        self,
        run_state: AgentRunState,
        call_records: list[ToolCall],
        observation: ToolObservation,
    ) -> None:
        run_state.tool_calls += len(call_records)
        retries = max(0, len(call_records) - 1)
        run_state.tool_retries += retries
        if not observation.success:
            run_state.tool_failures += 1


def _group_ready_steps(steps: Iterable[PlanStep]) -> list[list[PlanStep]]:
    grouped: dict[str, list[PlanStep]] = {}
    singles: list[list[PlanStep]] = []
    for step in steps:
        if step.parallel_group:
            grouped.setdefault(step.parallel_group, []).append(step)
        else:
            singles.append([step])
    return list(grouped.values()) + singles
