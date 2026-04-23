"""Typed runtime models and artifacts for LedgerAgent."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Literal


class PromptVariant(str, Enum):
    """Prompt bundle variant for planning and reflection."""

    A = "A"
    B = "B"


class SourceKind(str, Enum):
    """Source type for citations."""

    KB = "kb"
    DOC = "doc"
    WEB = "web"


@dataclass(frozen=True)
class Citation:
    """Reference to a tool result or source document."""

    source_kind: str | SourceKind
    source_id: str
    title: str = ""
    locator: str = ""
    uri: str | None = None
    text_snippet: str = ""
    relevance: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        kind_value = self.source_kind.value if isinstance(self.source_kind, SourceKind) else self.source_kind
        return {
            "source_kind": kind_value,
            "source_id": self.source_id,
            "title": self.title,
            "locator": self.locator,
            "uri": self.uri,
            "text_snippet": self.text_snippet,
            "relevance": self.relevance,
        }


@dataclass
class BudgetState:
    """Real-time budget tracking state."""

    max_budget_usd: float
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    spent_usd: float = 0.0
    blocked: bool = False
    blocked_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlanStep:
    """A single step in an execution plan."""

    step_id: str
    description: str
    tool_name: str
    tool_input: dict[str, Any]
    depends_on: list[str] = field(default_factory=list)
    parallel_group: str | None = None
    optional: bool = False
    expected_evidence: str = ""
    completion_signal: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionPlan:
    """A structured plan with ordered or parallel steps."""

    objective: str
    completion_criteria: list[str]
    expected_answer_shape: str
    possible_contradictions: list[str] = field(default_factory=list)
    steps: list[PlanStep] = field(default_factory=list)
    prompt_variant: str | PromptVariant | None = None

    def __post_init__(self) -> None:
        if isinstance(self.prompt_variant, str):
            object.__setattr__(self, "prompt_variant", PromptVariant(self.prompt_variant))

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "completion_criteria": self.completion_criteria,
            "expected_answer_shape": self.expected_answer_shape,
            "possible_contradictions": self.possible_contradictions,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass
class ToolCall:
    """Record of a single tool invocation."""

    step_id: str
    tool_name: str
    tool_input: dict[str, Any]
    parallel_group: str | None = None
    attempt: int = 1
    success: bool = False
    duration_ms: int = 0
    error: str | None = None
    fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ToolObservation:
    """Structured result from tool execution."""

    step_id: str
    tool_name: str
    success: bool
    summary: str
    raw_output: str
    data: dict[str, Any] = field(default_factory=dict)
    citations: list[Citation] = field(default_factory=list)
    error: str | None = None
    duration_ms: int = 0
    attempts: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "success": self.success,
            "summary": self.summary,
            "raw_output": self.raw_output,
            "data": self.data,
            "citations": [c.to_dict() for c in self.citations],
            "error": self.error,
            "duration_ms": self.duration_ms,
            "attempts": self.attempts,
        }


@dataclass
class EvidenceClaim:
    """A single claim extracted from observations."""

    claim_id: str
    topic: str
    statement: str
    value: Any = None
    confidence: float = 1.0
    citations: list[Citation] = field(default_factory=list)
    source_preference: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "topic": self.topic,
            "statement": self.statement,
            "value": self.value,
            "confidence": self.confidence,
            "citations": [c.to_dict() for c in self.citations],
            "source_preference": self.source_preference,
        }


@dataclass
class Contradiction:
    """A detected conflict between claims."""

    topic: str
    claim_ids: list[str]
    resolution: str = ""
    unresolved: bool = False
    winning_claim_id: str | None = None
    severity: Literal["low", "medium", "high"] = "medium"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReflectionResult:
    """Output of the reflection stage."""

    claims: list[EvidenceClaim] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)
    needs_more_evidence: bool = False
    rationale: str = ""
    suggested_additional_steps: list[PlanStep] = field(default_factory=list)
    provisional_confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": [c.to_dict() for c in self.claims],
            "contradictions": [c.to_dict() for c in self.contradictions],
            "uncertainty_notes": self.uncertainty_notes,
            "needs_more_evidence": self.needs_more_evidence,
            "rationale": self.rationale,
            "suggested_additional_steps": [s.to_dict() for s in self.suggested_additional_steps],
            "provisional_confidence": self.provisional_confidence,
        }


@dataclass
class AgentRunState:
    """Comprehensive state snapshot of an agent run."""

    termination_reason: str = "not_started"
    model_calls: int = 0
    tool_calls: int = 0
    tool_failures: int = 0
    tool_retries: int = 0
    parallel_batches: int = 0
    cycles: int = 0
    failure_notes: list[str] = field(default_factory=list)
    budget: BudgetState = field(default_factory=lambda: BudgetState(max_budget_usd=0.25))

    def to_dict(self) -> dict[str, Any]:
        return {
            "termination_reason": self.termination_reason,
            "model_calls": self.model_calls,
            "tool_calls": self.tool_calls,
            "tool_failures": self.tool_failures,
            "tool_retries": self.tool_retries,
            "parallel_batches": self.parallel_batches,
            "cycles": self.cycles,
            "failure_notes": self.failure_notes,
            "budget": self.budget.to_dict(),
        }


@dataclass
class AgentConfig:
    """Configuration for LedgerAgent execution."""

    model: str = "evals-anthropic/claude-sonnet-4-6"
    prompt_variant: str | PromptVariant = "B"
    max_budget_usd: float = 0.25
    max_cycles: int = 2
    verbose: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.prompt_variant, str):
            object.__setattr__(self, "prompt_variant", PromptVariant(self.prompt_variant))


@dataclass
class AgentResult:
    """Final structured result from an agent run, including full evidence ledger."""

    success: bool
    final_answer: str
    confidence: float
    query: str = ""
    plan: ExecutionPlan | None = None
    observations: list[ToolObservation] = field(default_factory=list)
    claims: list[EvidenceClaim] = field(default_factory=list)
    contradictions: list[Contradiction] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    run_state: AgentRunState = field(default_factory=AgentRunState)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "query": self.query,
            "final_answer": self.final_answer,
            "confidence": self.confidence,
            "plan": self.plan.to_dict() if self.plan else None,
            "observations": [o.to_dict() for o in self.observations],
            "claims": [c.to_dict() for c in self.claims],
            "contradictions": [c.to_dict() for c in self.contradictions],
            "uncertainty_notes": self.uncertainty_notes,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "run_state": self.run_state.to_dict(),
            "elapsed_seconds": self.elapsed_seconds,
        }
