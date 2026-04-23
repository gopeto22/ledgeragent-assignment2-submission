"""Planner, reflection, and answer synthesis for LedgerAgent."""

from __future__ import annotations

import json
import re
from typing import Any

from .budget import BudgetManager
from .model_client import ModelClient, TextBlock
from .models import (
    Citation,
    Contradiction,
    EvidenceClaim,
    ExecutionPlan,
    PlanStep,
    PromptVariant,
    ReflectionResult,
    ToolObservation,
)
from .prompts import answer_prompt, planner_prompt, reflection_prompt
from .tools import ToolRegistry

PLANNER_MAX_OUTPUT_TOKENS = 1400
REFLECTION_MAX_OUTPUT_TOKENS = 1600
ANSWER_MAX_OUTPUT_TOKENS = 1000


class PlannerError(RuntimeError):
    """Raised when the planner cannot produce a usable result."""


class LedgerPlanner:
    """LLM-backed planning and reflection helpers."""

    def __init__(
        self,
        *,
        client: ModelClient,
        model_name: str,
        budget_manager: BudgetManager,
        tool_registry: ToolRegistry,
    ) -> None:
        self.client = client
        self.model_name = model_name
        self.budget_manager = budget_manager
        self.tool_registry = tool_registry

    def build_plan(self, query: str, prompt_variant: PromptVariant) -> ExecutionPlan:
        manifest = self.tool_registry.manifest()
        system_prompt = planner_prompt(prompt_variant, manifest)
        user_payload = {"query": query}
        text = self._complete_text(
            system_prompt=system_prompt,
            user_payload=user_payload,
            max_tokens=PLANNER_MAX_OUTPUT_TOKENS,
        )
        try:
            payload = _parse_json_object(text)
            return self._plan_from_payload(payload, prompt_variant)
        except Exception:
            return self._fallback_plan(query, prompt_variant)

    def reflect(
        self,
        *,
        query: str,
        plan: ExecutionPlan,
        observations: list[ToolObservation],
        prompt_variant: PromptVariant,
    ) -> ReflectionResult:
        system_prompt = reflection_prompt(prompt_variant)
        user_payload = {
            "query": query,
            "plan": plan.to_dict(),
            "observations": [observation.to_dict() for observation in observations],
        }
        text = self._complete_text(
            system_prompt=system_prompt,
            user_payload=user_payload,
            max_tokens=REFLECTION_MAX_OUTPUT_TOKENS,
        )
        try:
            payload = _parse_json_object(text)
            return self._reflection_from_payload(payload, observations)
        except Exception:
            return self._fallback_reflection(observations)

    def answer(
        self,
        *,
        query: str,
        plan: ExecutionPlan,
        observations: list[ToolObservation],
        reflection: ReflectionResult,
    ) -> tuple[str, float, list[str]]:
        system_prompt = answer_prompt()
        user_payload = {
            "query": query,
            "plan": plan.to_dict(),
            "observations": [observation.to_dict() for observation in observations],
            "claims": [claim.to_dict() for claim in reflection.claims],
            "contradictions": [item.to_dict() for item in reflection.contradictions],
            "uncertainty_notes": reflection.uncertainty_notes,
        }
        text = self._complete_text(
            system_prompt=system_prompt,
            user_payload=user_payload,
            max_tokens=ANSWER_MAX_OUTPUT_TOKENS,
        )
        try:
            payload = _parse_json_object(text)
            return (
                str(payload["final_answer"]),
                float(payload.get("confidence", reflection.provisional_confidence or 0.5)),
                [str(item) for item in payload.get("uncertainty_notes", [])],
            )
        except Exception:
            answer_lines = [claim.statement for claim in reflection.claims[:3]]
            final_answer = "\n".join(answer_lines) or "Insufficient evidence to answer confidently."
            return final_answer, reflection.provisional_confidence or 0.4, reflection.uncertainty_notes

    def _complete_text(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        max_tokens: int,
    ) -> str:
        messages = [{"role": "user", "content": json.dumps(user_payload, default=str)}]
        budget_payload = {
            "system_prompt": system_prompt,
            "messages": messages,
            "tools": [],
        }
        self.budget_manager.reserve_model_call(
            prompt_payload=budget_payload,
            max_output_tokens=max_tokens,
        )
        response = self.client.complete(
            model=self.model_name,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            tools=[],
            messages=messages,
        )
        text = "\n".join(
            block.text for block in response.content if isinstance(block, TextBlock)
        ).strip()
        self.budget_manager.record_model_call(
            prompt_payload=budget_payload,
            response_payload={"text": text},
        )
        return text

    def _plan_from_payload(
        self,
        payload: dict[str, Any],
        prompt_variant: PromptVariant,
    ) -> ExecutionPlan:
        steps: list[PlanStep] = []
        for raw_step in payload.get("steps", []):
            tool_name = str(raw_step.get("tool_name", "")).strip()
            if tool_name not in self.tool_registry.specs:
                continue
            steps.append(
                PlanStep(
                    step_id=str(raw_step.get("step_id", f"step_{len(steps) + 1}")),
                    description=str(raw_step.get("description", "")),
                    tool_name=tool_name,
                    tool_input=dict(raw_step.get("tool_input", {})),
                    expected_evidence=str(raw_step.get("expected_evidence", "")),
                    completion_signal=str(raw_step.get("completion_signal", "")),
                    depends_on=[str(item) for item in raw_step.get("depends_on", [])],
                    parallel_group=raw_step.get("parallel_group"),
                    optional=bool(raw_step.get("optional", False)),
                )
            )
        if not steps:
            raise PlannerError("Planner did not return any valid steps")
        return ExecutionPlan(
            objective=str(payload.get("objective", "")),
            completion_criteria=[str(item) for item in payload.get("completion_criteria", [])],
            expected_answer_shape=str(payload.get("expected_answer_shape", "")),
            possible_contradictions=[
                str(item) for item in payload.get("possible_contradictions", [])
            ],
            steps=steps,
            prompt_variant=prompt_variant,
        )

    def _reflection_from_payload(
        self,
        payload: dict[str, Any],
        observations: list[ToolObservation],
    ) -> ReflectionResult:
        citation_index = _citation_index(observations)
        claims = [
            EvidenceClaim(
                claim_id=str(item.get("claim_id", f"claim_{index}")),
                topic=str(item.get("topic", "general")),
                statement=str(item.get("statement", "")),
                value=item.get("value"),
                confidence=float(item.get("confidence", 0.5)),
                citations=[
                    citation_index[citation_ref]
                    for citation_ref in item.get("citation_refs", [])
                    if citation_ref in citation_index
                ],
                source_preference=int(item.get("source_preference", 0)),
            )
            for index, item in enumerate(payload.get("claims", []), start=1)
        ]
        contradictions = [
            Contradiction(
                topic=str(item.get("topic", "general")),
                claim_ids=[str(claim_id) for claim_id in item.get("claim_ids", [])],
                resolution=str(item.get("resolution", "")),
                unresolved=bool(item.get("unresolved", False)),
                winning_claim_id=item.get("winning_claim_id"),
            )
            for item in payload.get("contradictions", [])
        ]
        suggested_steps = [
            PlanStep(
                step_id=str(item.get("step_id", f"followup_{index}")),
                description=str(item.get("description", "")),
                tool_name=str(item.get("tool_name", "")),
                tool_input=dict(item.get("tool_input", {})),
                expected_evidence=str(item.get("expected_evidence", "")),
                completion_signal=str(item.get("completion_signal", "")),
                depends_on=[str(dep) for dep in item.get("depends_on", [])],
                parallel_group=item.get("parallel_group"),
                optional=bool(item.get("optional", False)),
            )
            for index, item in enumerate(payload.get("suggested_additional_steps", []), start=1)
            if str(item.get("tool_name", "")) in self.tool_registry.specs
        ]
        return ReflectionResult(
            claims=claims,
            contradictions=contradictions,
            needs_more_evidence=bool(payload.get("needs_more_evidence", False)),
            rationale=str(payload.get("rationale", "")),
            uncertainty_notes=[str(item) for item in payload.get("uncertainty_notes", [])],
            suggested_additional_steps=suggested_steps,
            provisional_confidence=float(payload.get("provisional_confidence", 0.5)),
        )

    def _fallback_plan(self, query: str, prompt_variant: PromptVariant) -> ExecutionPlan:
        query_lower = query.lower()
        steps = [
            PlanStep(
                step_id="step_docs",
                description="Search internal policy documents for direct answer clues.",
                tool_name="doc_qa",
                tool_input={"question": query, "top_k": 3},
                expected_evidence="Relevant policy excerpts",
                completion_signal="At least one useful policy excerpt or an explicit no-match result",
                parallel_group="research",
            ),
            PlanStep(
                step_id="step_kb",
                description="Search the structured internal KB for prices, overrides, and limits.",
                tool_name="kb_lookup",
                tool_input={"query": query, "top_k": 5},
                expected_evidence="Relevant structured records",
                completion_signal="At least one useful KB record or an explicit no-match result",
                parallel_group="research",
            ),
        ]
        if any(token in query_lower for token in ("competitor", "market", "public", "roadmap", "acme")):
            steps.append(
                PlanStep(
                    step_id="step_web",
                    description="Search public web sources for external facts.",
                    tool_name="web_search",
                    tool_input={"query": query, "top_k": 3},
                    expected_evidence="Relevant external snippets",
                    completion_signal="At least one useful web result or an explicit no-match result",
                    parallel_group="research",
                )
            )
        return ExecutionPlan(
            objective=query,
            completion_criteria=[
                "Retrieve enough evidence to answer directly",
                "Note any contradictions across sources",
            ],
            expected_answer_shape="Concise analyst answer with evidence and uncertainty",
            possible_contradictions=["Internal policy may conflict with web snapshot claims"],
            steps=steps,
            prompt_variant=prompt_variant,
        )

    def _fallback_reflection(
        self,
        observations: list[ToolObservation],
    ) -> ReflectionResult:
        claims = []
        for index, observation in enumerate(observations, start=1):
            if not observation.success:
                continue
            claims.append(
                EvidenceClaim(
                    claim_id=f"claim_{index}",
                    topic=observation.tool_name,
                    statement=observation.summary,
                    value=observation.data.get("value") or observation.summary,
                    confidence=0.4,
                    citations=observation.citations,
                    source_preference=_source_preference(observation.citations),
                )
            )
        return ReflectionResult(
            claims=claims,
            contradictions=[],
            needs_more_evidence=False,
            rationale="Fallback reflection used because structured JSON parsing failed.",
            uncertainty_notes=["Used fallback reflection; evidence extraction may be incomplete."],
            provisional_confidence=0.4,
        )


def _parse_json_object(text: str) -> dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1:
        raise PlannerError("No JSON object found in model output")
    return json.loads(candidate[start : end + 1])


def _citation_index(observations: list[ToolObservation]) -> dict[str, Citation]:
    index: dict[str, Citation] = {}
    for observation in observations:
        for citation in observation.citations:
            index[_citation_key(citation)] = citation
    return index


def _citation_key(citation: Citation) -> str:
    return f"{citation.source_kind}:{citation.source_id}#{citation.locator}"


def _source_preference(citations: list[Citation]) -> int:
    if not citations:
        return 0
    precedence = {"doc": 3, "kb": 2, "web": 1, "calculator": 2, "python": 2, "agent": 0}
    return max(precedence.get(citation.source_kind, 0) for citation in citations)
