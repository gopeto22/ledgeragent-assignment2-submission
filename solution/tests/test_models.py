"""Tests for LedgerAgent's typed data models."""

from __future__ import annotations

import dataclasses
import json

from spec_agent.models import (
    AgentConfig,
    AgentResult,
    AgentRunState,
    BudgetState,
    Citation,
    Contradiction,
    EvidenceClaim,
    ExecutionPlan,
    PlanStep,
    PromptVariant,
    ReflectionResult,
    SourceKind,
    ToolCall,
    ToolObservation,
)


def test_prompt_variant_enum():
    """Test PromptVariant enum."""
    assert PromptVariant.A.value == "A"
    assert PromptVariant.B.value == "B"
    assert PromptVariant("A") == PromptVariant.A


def test_source_kind_enum():
    """Test SourceKind enum."""
    assert SourceKind.KB.value == "kb"
    assert SourceKind.DOC.value == "doc"
    assert SourceKind.WEB.value == "web"
    assert SourceKind("kb") == SourceKind.KB


def test_citation_creation():
    """Test Citation dataclass creation."""
    citation = Citation(
        source_kind=SourceKind.DOC,
        source_id="sla",
        title="Enterprise SLA",
        locator="Section 2.1",
        uri="https://internal.example.com/sla",
        text_snippet="99.9% uptime",
        relevance=0.95,
    )
    assert citation.source_kind == SourceKind.DOC
    assert citation.source_id == "sla"
    assert citation.title == "Enterprise SLA"


def test_citation_to_dict():
    """Test Citation serialization."""
    citation = Citation(
        source_kind=SourceKind.WEB,
        source_id="acme",
        title="Acme Pricing",
        relevance=0.85,
    )
    d = citation.to_dict()
    assert d["source_kind"] == "web"
    assert d["source_id"] == "acme"
    assert d["relevance"] == 0.85


def test_budget_state_creation():
    """Test BudgetState dataclass."""
    budget = BudgetState(max_budget_usd=0.50, spent_usd=0.12)
    assert budget.max_budget_usd == 0.50
    assert budget.spent_usd == 0.12
    assert not budget.blocked


def test_budget_state_blocking():
    """Test BudgetState blocking."""
    budget = BudgetState(max_budget_usd=0.10, blocked=True, blocked_reason="exceeded limit")
    assert budget.blocked
    assert budget.blocked_reason == "exceeded limit"


def test_plan_step_creation():
    """Test PlanStep dataclass."""
    step = PlanStep(
        step_id="step_1",
        description="Look up pricing in KB",
        tool_name="kb_lookup",
        tool_input={"query": "enterprise pricing"},
        depends_on=[],
        parallel_group="batch_1",
        optional=False,
        expected_evidence="enterprise plan pricing",
        completion_signal="found pricing",
    )
    assert step.step_id == "step_1"
    assert step.tool_name == "kb_lookup"
    assert step.parallel_group == "batch_1"


def test_execution_plan_creation():
    """Test ExecutionPlan dataclass."""
    step = PlanStep(
        step_id="step_1",
        description="Search KB",
        tool_name="kb_lookup",
        tool_input={"query": "pricing"},
    )
    plan = ExecutionPlan(
        objective="Find Quote Pro quarterly pricing",
        completion_criteria=["found annual price", "calculated quarterly"],
        expected_answer_shape="A number representing dollars per quarter",
        possible_contradictions=["different pricing tiers"],
        steps=[step],
        prompt_variant=PromptVariant.A,
    )
    assert plan.objective == "Find Quote Pro quarterly pricing"
    assert len(plan.completion_criteria) == 2
    assert plan.prompt_variant == PromptVariant.A


def test_execution_plan_prompt_variant_string():
    """Test ExecutionPlan with string prompt variant gets normalized."""
    plan = ExecutionPlan(
        objective="Test",
        completion_criteria=[],
        expected_answer_shape="",
        prompt_variant="B",
    )
    assert isinstance(plan.prompt_variant, PromptVariant)
    assert plan.prompt_variant == PromptVariant.B


def test_execution_plan_to_dict():
    """Test ExecutionPlan serialization."""
    step = PlanStep(
        step_id="step_1",
        description="Test",
        tool_name="kb_lookup",
        tool_input={},
    )
    plan = ExecutionPlan(
        objective="Test plan",
        completion_criteria=["found data"],
        expected_answer_shape="string",
        steps=[step],
    )
    d = plan.to_dict()
    assert d["objective"] == "Test plan"
    assert len(d["steps"]) == 1
    assert d["steps"][0]["tool_name"] == "kb_lookup"


def test_tool_call_creation():
    """Test ToolCall dataclass."""
    call = ToolCall(
        step_id="step_1",
        tool_name="kb_lookup",
        tool_input={"query": "pricing"},
        attempt=1,
        success=True,
        duration_ms=500,
    )
    assert call.tool_name == "kb_lookup"
    assert call.success
    assert call.duration_ms == 500


def test_tool_observation_creation():
    """Test ToolObservation dataclass."""
    citation = Citation(source_kind=SourceKind.KB, source_id="pricing")
    observation = ToolObservation(
        step_id="step_1",
        tool_name="kb_lookup",
        success=True,
        summary="Found pricing",
        raw_output="Quote Pro: $396/year",
        citations=[citation],
        duration_ms=150,
        attempts=1,
    )
    assert observation.tool_name == "kb_lookup"
    assert observation.success
    assert len(observation.citations) == 1


def test_tool_observation_with_error():
    """Test ToolObservation with error."""
    observation = ToolObservation(
        step_id="step_1",
        tool_name="web_search",
        success=False,
        summary="Failed to search",
        raw_output="",
        error="Timeout after 5 seconds",
    )
    assert not observation.success
    assert observation.error == "Timeout after 5 seconds"


def test_tool_observation_to_dict():
    """Test ToolObservation serialization."""
    citation = Citation(
        source_kind=SourceKind.DOC,
        source_id="doc1",
        title="Document 1",
    )
    observation = ToolObservation(
        step_id="step_1",
        tool_name="doc_qa",
        success=True,
        summary="Found answer",
        raw_output="Answer is X",
        citations=[citation],
    )
    d = observation.to_dict()
    assert d["tool_name"] == "doc_qa"
    assert d["success"]
    assert len(d["citations"]) == 1
    assert d["citations"][0]["source_id"] == "doc1"


def test_evidence_claim_creation():
    """Test EvidenceClaim dataclass."""
    citation = Citation(source_kind=SourceKind.KB, source_id="pricing")
    claim = EvidenceClaim(
        claim_id="claim_1",
        topic="Quote Pro pricing",
        statement="Annual price is $396",
        value=396,
        confidence=0.95,
        citations=[citation],
        source_preference=1,
    )
    assert claim.claim_id == "claim_1"
    assert claim.confidence == 0.95
    assert claim.value == 396


def test_contradiction_creation():
    """Test Contradiction dataclass."""
    contradiction = Contradiction(
        topic="Response time SLA",
        claim_ids=["claim_1", "claim_2"],
        resolution="Using newer policy document",
        winning_claim_id="claim_2",
        severity="high",
    )
    assert contradiction.topic == "Response time SLA"
    assert len(contradiction.claim_ids) == 2
    assert not contradiction.unresolved


def test_contradiction_unresolved():
    """Test Contradiction that's unresolved."""
    contradiction = Contradiction(
        topic="Travel budget",
        claim_ids=["claim_1", "claim_2"],
        unresolved=True,
        severity="medium",
    )
    assert contradiction.unresolved
    assert contradiction.winning_claim_id is None


def test_reflection_result_creation():
    """Test ReflectionResult dataclass."""
    claim = EvidenceClaim(
        claim_id="claim_1",
        topic="Test",
        statement="Test statement",
        confidence=0.9,
    )
    contradiction = Contradiction(
        topic="Test topic",
        claim_ids=["claim_1"],
    )
    result = ReflectionResult(
        claims=[claim],
        contradictions=[contradiction],
        uncertainty_notes=["Note 1"],
        needs_more_evidence=False,
        rationale="Clear evidence found",
        provisional_confidence=0.9,
    )
    assert len(result.claims) == 1
    assert len(result.contradictions) == 1
    assert result.provisional_confidence == 0.9


def test_reflection_result_to_dict():
    """Test ReflectionResult serialization."""
    claim = EvidenceClaim(
        claim_id="claim_1",
        topic="Topic",
        statement="Statement",
    )
    result = ReflectionResult(claims=[claim])
    d = result.to_dict()
    assert "claims" in d
    assert len(d["claims"]) == 1
    assert d["claims"][0]["claim_id"] == "claim_1"


def test_agent_run_state_creation():
    """Test AgentRunState dataclass."""
    budget = BudgetState(max_budget_usd=0.25)
    state = AgentRunState(
        termination_reason="sufficient_evidence",
        model_calls=2,
        tool_calls=3,
        tool_failures=0,
        parallel_batches=2,
        cycles=1,
        budget=budget,
    )
    assert state.model_calls == 2
    assert state.tool_calls == 3
    assert state.termination_reason == "sufficient_evidence"


def test_agent_run_state_with_failures():
    """Test AgentRunState with failures and notes."""
    state = AgentRunState(
        termination_reason="max_iterations_exceeded",
        tool_failures=1,
        tool_retries=2,
        failure_notes=["Tool X timed out", "Tool Y had parse error"],
    )
    assert state.tool_failures == 1
    assert len(state.failure_notes) == 2


def test_agent_config_creation():
    """Test AgentConfig dataclass."""
    config = AgentConfig(
        model="claude-sonnet-4",
        prompt_variant=PromptVariant.B,
        max_budget_usd=0.50,
        max_cycles=3,
        verbose=True,
    )
    assert config.model == "claude-sonnet-4"
    assert config.prompt_variant == PromptVariant.B
    assert config.max_budget_usd == 0.50


def test_agent_config_default_values():
    """Test AgentConfig with defaults."""
    config = AgentConfig()
    assert config.prompt_variant == PromptVariant("B")
    assert config.max_budget_usd == 0.25
    assert config.max_cycles == 2


def test_agent_config_prompt_variant_string():
    """Test AgentConfig with string prompt variant."""
    config = AgentConfig(prompt_variant="A")
    assert isinstance(config.prompt_variant, PromptVariant)
    assert config.prompt_variant == PromptVariant.A


def test_agent_result_success():
    """Test AgentResult for successful execution."""
    run_state = AgentRunState(
        termination_reason="sufficient_evidence",
        model_calls=2,
        tool_calls=2,
    )
    result = AgentResult(
        success=True,
        final_answer="The quarterly price is $99",
        confidence=0.95,
        run_state=run_state,
        elapsed_seconds=2.5,
    )
    assert result.success
    assert result.confidence == 0.95
    assert result.elapsed_seconds == 2.5


def test_agent_result_failure():
    """Test AgentResult for failed execution."""
    result = AgentResult(
        success=False,
        final_answer="Unable to determine answer due to budget exhaustion",
        confidence=0.2,
        uncertainty_notes=["Budget limit exceeded", "Incomplete evidence"],
    )
    assert not result.success
    assert len(result.uncertainty_notes) == 2


def test_agent_result_to_dict():
    """Test AgentResult serialization."""
    tool_call = ToolCall(
        step_id="step_1",
        tool_name="kb_lookup",
        tool_input={},
    )
    result = AgentResult(
        success=True,
        final_answer="Test answer",
        confidence=0.8,
        tool_calls=[tool_call],
    )
    d = result.to_dict()
    assert d["success"]
    assert d["final_answer"] == "Test answer"
    assert len(d["tool_calls"]) == 1


def test_models_json_serializable():
    """Test that all models can be JSON serialized."""
    citation = Citation(source_kind=SourceKind.KB, source_id="test")
    claim = EvidenceClaim(
        claim_id="claim_1",
        topic="Topic",
        statement="Statement",
        citations=[citation],
    )
    result = AgentResult(
        success=True,
        final_answer="Answer",
        confidence=0.9,
    )

    # Should not raise
    json_str = json.dumps(claim.to_dict())
    assert "claim_1" in json_str

    json_str = json.dumps(result.to_dict())
    assert "Answer" in json_str


def test_models_are_frozen_or_mutable():
    """Test Citation is frozen but others are mutable."""
    # Citation is frozen
    citation = Citation(source_kind=SourceKind.KB, source_id="test")
    try:
        citation.source_id = "changed"
        assert False, "Citation should be frozen"
    except (AttributeError, dataclasses.FrozenInstanceError):
        pass  # Expected

    # AgentResult is mutable
    result = AgentResult(success=True, final_answer="Test", confidence=0.5)
    result.confidence = 0.8  # Should work
    assert result.confidence == 0.8


def test_budget_state_to_dict():
    """Test BudgetState serialization."""
    budget = BudgetState(
        max_budget_usd=0.50,
        estimated_input_tokens=100,
        estimated_output_tokens=50,
        spent_usd=0.12,
    )
    d = budget.to_dict()
    assert d["max_budget_usd"] == 0.50
    assert d["spent_usd"] == 0.12
    assert d["blocked"] is False


def test_agent_run_state_to_dict():
    """Test AgentRunState serialization."""
    state = AgentRunState(
        termination_reason="sufficient_evidence",
        model_calls=3,
        tool_calls=5,
        parallel_batches=2,
    )
    d = state.to_dict()
    assert d["termination_reason"] == "sufficient_evidence"
    assert d["model_calls"] == 3
    assert d["tool_calls"] == 5
    assert "budget" in d
