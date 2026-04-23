"""Eval harness tests for LedgerAgent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from spec_agent.evals import main, render_summary_markdown, run_benchmark
from spec_agent.model_client import ConfigurationError
from spec_agent.models import (
    AgentResult,
    AgentRunState,
    BudgetState,
    Citation,
    Contradiction,
    EvidenceClaim,
    ExecutionPlan,
    PlanStep,
    ToolCall,
    ToolObservation,
)


class FakeAgent:
    def __init__(self, result: AgentResult) -> None:
        self._result = result

    def run(self, query: str) -> AgentResult:
        assert query
        return self._result


def _fake_result() -> AgentResult:
    plan = ExecutionPlan(
        objective="Answer a query",
        completion_criteria=["Return a supported answer"],
        expected_answer_shape="Short answer",
        possible_contradictions=[],
        steps=[
            PlanStep(
                step_id="step_1",
                description="Lookup price",
                tool_name="kb_lookup",
                tool_input={"query": "Pro price"},
                expected_evidence="Price record",
                completion_signal="Found record",
            )
        ],
        prompt_variant="B",
    )
    citation = Citation(
        source_kind="kb",
        source_id="plans:1",
        title="plans record",
        locator="plans:1",
        uri="kb.json",
    )
    return AgentResult(
        success=True,
        query="What is our Pro price?",
        final_answer="The Pro plan costs 89 USD per seat.",
        confidence=0.8,
        uncertainty_notes=[],
        plan=plan,
        tool_calls=[
            ToolCall(
                step_id="step_1",
                tool_name="kb_lookup",
                tool_input={"query": "Pro price"},
                parallel_group=None,
                attempt=1,
                success=True,
                duration_ms=12,
            )
        ],
        observations=[
            ToolObservation(
                step_id="step_1",
                tool_name="kb_lookup",
                success=True,
                summary="Found KB record",
                raw_output="{}",
                data={"matches": [{"record": {"plan": "Pro", "seat_price_usd": 89}}]},
                citations=[citation],
                duration_ms=12,
            )
        ],
        claims=[
            EvidenceClaim(
                claim_id="claim_1",
                topic="pro price",
                statement="The Pro plan costs 89 USD per seat.",
                value="89 USD",
                confidence=0.8,
                citations=[citation],
                source_preference=2,
            )
        ],
        contradictions=[Contradiction(topic="none", claim_ids=["claim_1"], resolution="No contradiction")],
        run_state=AgentRunState(
            termination_reason="completed",
            model_calls=3,
            tool_calls=1,
            tool_failures=0,
            parallel_batches=1,
            cycles=1,
            budget=BudgetState(max_budget_usd=0.25, spent_usd=0.01),
        ),
        elapsed_seconds=0.042,
    )


def test_run_benchmark_writes_variant_summaries(tmp_path: Path):
    """Test that run_benchmark generates expected variant output structure."""
    import os
    from spec_agent.model_client import ConfigurationError
    
    # Skip if credentials not available
    if not any([
        os.environ.get("ANTHROPIC_API_KEY"),
        os.environ.get("ANTHROPIC_AUTH_TOKEN"),
    ]):
        pytest.skip("Anthropic credentials not available")
    
    output_dir = tmp_path / "evals"
    try:
        summary = run_benchmark(
            variant="A",
            asset_root=tmp_path,
            output_dir=output_dir,
        )
        
        # Check that summary contains expected fields
        assert "success_rate" in summary
        assert "category_pass_rates" in summary
        assert "prompt_variant" in summary
        assert summary["prompt_variant"] == "A"
        assert (output_dir / "prompt_A" / "summary.json").is_file()
    except ConfigurationError:
        pytest.skip("Anthropic credentials not available")


def test_render_summary_markdown_mentions_ablation():
    summary = {
        "generated_at": "2026-04-21T12:00:00Z",
        "model": "test-model",
        "prompt_version": "ledgeragent-v1",
        "variants": [
            {
                "variant": "A",
                "success_rate": 0.7,
                "avg_rubric": 7.4,
                "avg_latency_ms": 100.0,
                "avg_cost_usd": 0.01,
                "avg_tool_calls": 3.0,
                "avg_model_calls": 3.0,
                "hardest_categories": ["budget_stress"],
                "failed_cases": ["budget_case"],
            }
        ],
        "ablation": {"preferred_variant": "B", "success_rate_delta": 0.1},
    }

    markdown = render_summary_markdown(summary)

    assert "# LedgerAgent eval summary" in markdown
    assert "Prompt Ablation" in markdown
    assert "Preferred variant: B" in markdown


def test_main_reports_configuration_error(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path):
    def fake_run_benchmark(**_: object) -> Path:
        raise ConfigurationError("Missing Anthropic credentials")

    monkeypatch.setattr("spec_agent.evals.run_benchmark", fake_run_benchmark)

    result = main(["--output-dir", str(tmp_path)])

    assert result == 1
    captured = capsys.readouterr()
    assert "Missing Anthropic credentials" in captured.err
