"""LedgerAgent — budget-aware, self-auditing multi-tool analyst."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from .budget import BudgetExceededError, BudgetManager
from .executor import ExecutorConfig, PlanExecutor
from .model_client import ConfigurationError, ModelClient, create_model_client
from .models import (
    AgentConfig,
    AgentResult,
    AgentRunState,
    ExecutionPlan,
    ReflectionResult,
    ToolCall,
)
from .planner import LedgerPlanner, PlannerError
from .tools import ToolRegistry

logger = logging.getLogger(__name__)


class Agent:
    """Main agent orchestrator: planner → executor → reflection → answer."""

    def __init__(
        self,
        *,
        config: AgentConfig,
        client: ModelClient,
        planner: LedgerPlanner,
        executor: PlanExecutor,
        budget_manager: BudgetManager,
        tool_registry: ToolRegistry,
    ) -> None:
        self.config = config
        self.client = client
        self.planner = planner
        self.executor = executor
        self.budget_manager = budget_manager
        self.tool_registry = tool_registry

    @classmethod
    def create(
        cls,
        *,
        config: AgentConfig | None = None,
        asset_root: Path | None = None,
        offline_mode: bool = False,
    ) -> Agent:
        """Factory method to create and wire a fully-functional Agent.
        
        Args:
            config: Agent configuration (defaults to AgentConfig())
            asset_root: Path to assets directory
            offline_mode: If True, use FakeModelClient for deterministic testing
        """
        config = config or AgentConfig()
        asset_root = asset_root or (Path(__file__).resolve().parent.parent / "assets")

        if not asset_root.is_dir():
            raise ValueError(f"Asset root not found: {asset_root}")

        try:
            client = create_model_client(config.model, offline_mode=offline_mode)
        except ConfigurationError:
            # In offline mode, we don't need credentials
            if offline_mode:
                from .model_client import FakeModelClient
                client = FakeModelClient()
            else:
                raise

        budget_manager = BudgetManager.for_model(
            config.model,
            max_budget_usd=config.max_budget_usd,
        )

        tool_registry = ToolRegistry(asset_root)

        planner = LedgerPlanner(
            client=client,
            model_name=config.model,
            budget_manager=budget_manager,
            tool_registry=tool_registry,
        )

        executor = PlanExecutor(
            tool_registry=tool_registry,
            config=ExecutorConfig(),
        )

        return cls(
            config=config,
            client=client,
            planner=planner,
            executor=executor,
            budget_manager=budget_manager,
            tool_registry=tool_registry,
        )

    def run(self, query: str) -> AgentResult:
        """Run the agent on a single multi-step analyst query."""
        start_time = time.monotonic()
        run_state = AgentRunState(budget=self.budget_manager.state)
        tool_calls: list[ToolCall] = []
        all_observations = []
        final_reflection: ReflectionResult | None = None
        final_answer = ""
        final_confidence = 0.5
        final_uncertainty_notes = []

        logger.info("Starting Agent run: %s", query[:80])

        for cycle in range(1, self.config.max_cycles + 1):
            logger.info("Planning cycle %d/%d", cycle, self.config.max_cycles)
            run_state.cycles = cycle

            try:
                # Plan
                plan = self.planner.build_plan(query, self.config.prompt_variant)
            except BudgetExceededError as exc:
                logger.warning("Budget exceeded during planning: %s", exc)
                run_state.termination_reason = "budget_exceeded"
                run_state.failure_notes.append(f"Budget cap during planning: {exc}")
                break
            except PlannerError as exc:
                logger.warning("Planner failed: %s", exc)
                run_state.termination_reason = "planner_failed"
                run_state.failure_notes.append(f"Planner error: {exc}")
                break
            except Exception as exc:
                logger.exception("Unexpected error during planning")
                run_state.termination_reason = "planning_error"
                run_state.failure_notes.append(f"Unexpected error: {exc}")
                break

            # Execute plan
            try:
                cycle_tool_calls, cycle_observations, completed_steps = self.executor.execute(
                    plan=plan,
                    run_state=run_state,
                    already_completed=set(obs.step_id for obs in all_observations),
                )
                tool_calls.extend(cycle_tool_calls)
                all_observations.extend(cycle_observations)
            except BudgetExceededError as exc:
                logger.warning("Budget exceeded during execution: %s", exc)
                run_state.termination_reason = "budget_exceeded"
                run_state.failure_notes.append(f"Budget cap during execution: {exc}")
                break
            except Exception as exc:
                logger.exception("Unexpected error during execution")
                run_state.termination_reason = "execution_error"
                run_state.failure_notes.append(f"Execution error: {exc}")
                break

            # Reflect
            try:
                reflection = self.planner.reflect(
                    query=query,
                    plan=plan,
                    observations=cycle_observations,
                    prompt_variant=self.config.prompt_variant,
                )
                final_reflection = reflection
            except BudgetExceededError as exc:
                logger.warning("Budget exceeded during reflection: %s", exc)
                run_state.termination_reason = "budget_exceeded"
                break
            except Exception as exc:
                logger.exception("Unexpected error during reflection")
                run_state.failure_notes.append(f"Reflection error: {exc}")

            # Check if we have enough evidence
            if final_reflection and not final_reflection.needs_more_evidence:
                logger.info("Sufficient evidence gathered, stopping cycles")
                break

            if cycle >= self.config.max_cycles:
                logger.info("Reached max cycles")
                break

        # Synthesize final answer
        if final_reflection:
            try:
                final_answer, final_confidence, final_uncertainty_notes = self.planner.answer(
                    query=query,
                    plan=ExecutionPlan(
                        objective=query,
                        completion_criteria=[],
                        expected_answer_shape="",
                    ),
                    observations=all_observations,
                    reflection=final_reflection,
                )
                run_state.termination_reason = (
                    "completed" if run_state.termination_reason == "not_started"
                    else run_state.termination_reason
                )
            except Exception as exc:
                logger.exception("Error during answer synthesis")
                final_answer = self._fallback_answer(final_reflection)
                final_confidence = final_reflection.provisional_confidence or 0.4
                run_state.failure_notes.append(f"Answer synthesis failed: {exc}")
        else:
            final_answer = "Unable to formulate an answer due to planning or execution failures."
            final_confidence = 0.0
            run_state.termination_reason = "failed"

        elapsed_seconds = time.monotonic() - start_time

        # Collect claims and contradictions from reflection
        claims = []
        contradictions = []
        if final_reflection:
            claims = final_reflection.claims
            contradictions = final_reflection.contradictions

        return AgentResult(
            success=run_state.termination_reason == "completed",
            query=query,
            final_answer=final_answer,
            confidence=final_confidence,
            plan=None,  # Plans are internal; not exposed in result
            observations=all_observations,
            claims=claims,
            contradictions=contradictions,
            uncertainty_notes=final_uncertainty_notes,
            tool_calls=tool_calls,
            run_state=run_state,
            elapsed_seconds=elapsed_seconds,
        )

    def _fallback_answer(self, reflection: ReflectionResult) -> str:
        """Generate a simple fallback answer from reflection."""
        if reflection and reflection.claims:
            return f"Based on the available evidence: {reflection.claims[0].claim_text}"
        return "Unable to synthesize an answer."

