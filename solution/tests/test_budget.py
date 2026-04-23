"""Tests for budget estimation and enforcement."""

from __future__ import annotations

import pytest

from spec_agent.budget import BudgetExceededError, BudgetManager


def test_budget_manager_records_token_estimates():
    manager = BudgetManager.for_model(
        "evals-anthropic/claude-sonnet-4-6",
        max_budget_usd=0.25,
    )
    manager.record_model_call(
        prompt_payload={"query": "hello"},
        response_payload={"answer": "world"},
    )

    assert manager.state.estimated_input_tokens > 0
    assert manager.state.estimated_output_tokens > 0
    assert manager.state.spent_usd > 0


def test_budget_manager_blocks_when_cap_would_be_exceeded():
    manager = BudgetManager.for_model(
        "evals-anthropic/claude-sonnet-4-6",
        max_budget_usd=0.0001,
    )

    with pytest.raises(BudgetExceededError):
        manager.reserve_model_call(
            prompt_payload={"query": "x" * 4000},
            max_output_tokens=1200,
        )

    assert manager.state.blocked is True
    assert manager.state.blocked_reason is not None
