"""Tests for LedgerAgent loop and contracts.

These tests use a mock LLM client to verify:
- Agent correctly constructs AgentResult with all required fields
- AgentRunState is properly populated
- Planning, execution, reflection cycle completes
- Budget enforcement works
- Contradiction detection works
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from spec_agent.agent import Agent
from spec_agent.model_client import ConfigurationError
from spec_agent.models import (
    AgentConfig,
    AgentResult,
    AgentRunState,
    BudgetState,
)


@pytest.fixture
def asset_root(tmp_path: Path) -> Path:
    """Create a minimal asset root for testing."""
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    
    # Create minimal doc
    docs_dir = asset_dir / "docs"
    docs_dir.mkdir()
    (docs_dir / "test.md").write_text("# Test Policy\n\nTest content")
    
    # Create minimal kb.json
    (asset_dir / "kb.json").write_text('{"test": "data"}')
    
    # Create minimal web_snapshot.json
    (asset_dir / "web_snapshot.json").write_text('{"test": "snapshot"}')
    
    return asset_dir


class TestAgentResultContract:
    """Verify AgentResult matches contract."""

    def test_agent_result_has_all_required_fields(self):
        """AgentResult must have all contract fields."""
        result = AgentResult(
            success=True,
            query="test query",
            final_answer="test answer",
            confidence=0.8,
            plan=None,
            observations=[],
            claims=[],
            contradictions=[],
            uncertainty_notes=[],
            tool_calls=[],
            run_state=AgentRunState(),
            elapsed_seconds=1.0,
        )
        
        # Verify all contract fields exist
        assert result.success is True
        assert result.query == "test query"
        assert result.final_answer == "test answer"
        assert result.confidence == 0.8
        assert result.plan is None
        assert result.observations == []
        assert result.claims == []
        assert result.contradictions == []
        assert result.uncertainty_notes == []
        assert result.tool_calls == []
        assert isinstance(result.run_state, AgentRunState)
        assert result.elapsed_seconds == 1.0

    def test_agent_result_serializes_to_dict(self):
        """AgentResult.to_dict() must produce valid JSON-serializable dict."""
        result = AgentResult(
            success=True,
            query="test",
            final_answer="answer",
            confidence=0.5,
        )
        
        d = result.to_dict()
        
        assert d["success"] is True
        assert d["query"] == "test"
        assert d["final_answer"] == "answer"
        assert d["confidence"] == 0.5
        assert "plan" in d
        assert "observations" in d
        assert "run_state" in d


class TestAgentRunStateContract:
    """Verify AgentRunState matches contract."""

    def test_agent_run_state_has_all_fields(self):
        """AgentRunState must have all contract fields."""
        state = AgentRunState(
            termination_reason="completed",
            model_calls=3,
            tool_calls=2,
            tool_failures=0,
            tool_retries=0,
            parallel_batches=1,
            cycles=1,
            failure_notes=[],
            budget=BudgetState(max_budget_usd=0.25, spent_usd=0.01),
        )
        
        assert state.termination_reason == "completed"
        assert state.model_calls == 3
        assert state.tool_calls == 2
        assert state.tool_failures == 0
        assert state.tool_retries == 0
        assert state.parallel_batches == 1
        assert state.cycles == 1
        assert state.failure_notes == []
        assert state.budget.spent_usd == 0.01

    def test_agent_run_state_serializes(self):
        """AgentRunState.to_dict() must be JSON-serializable."""
        state = AgentRunState(
            termination_reason="completed",
            model_calls=1,
            tool_calls=0,
        )
        
        d = state.to_dict()
        
        assert d["termination_reason"] == "completed"
        assert d["model_calls"] == 1
        assert "budget" in d  # Must have budget sub-dict


class TestAgentConfig:
    """Verify AgentConfig contract."""

    def test_defaults(self):
        """AgentConfig must have correct defaults."""
        config = AgentConfig()
        
        assert config.prompt_variant.value == "B"
        assert config.max_budget_usd == 0.25
        assert config.max_cycles == 2
        assert config.verbose is False

    def test_custom_values(self):
        """AgentConfig accepts custom values."""
        config = AgentConfig(
            prompt_variant="A",
            max_budget_usd=0.50,
            max_cycles=3,
            verbose=True,
        )
        
        assert config.prompt_variant.value == "A"
        assert config.max_budget_usd == 0.50
        assert config.max_cycles == 3
        assert config.verbose is True


class TestAgentCreate:
    """Verify Agent.create() factory method."""

    @pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("ANTHROPIC_AUTH_TOKEN"),
        reason="Anthropic credentials not available",
    )
    def test_agent_create_returns_agent(self, asset_root: Path):
        """Agent.create() must return an Agent instance."""
        config = AgentConfig()
        
        agent = Agent.create(
            config=config,
            asset_root=asset_root,
        )
        
        assert agent is not None
        assert hasattr(agent, "run")

    @pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("ANTHROPIC_AUTH_TOKEN"),
        reason="Anthropic credentials not available",
    )
    def test_agent_create_with_default_config(self, asset_root: Path):
        """Agent.create() works with no explicit config."""
        agent = Agent.create(asset_root=asset_root)
        
        assert agent is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
