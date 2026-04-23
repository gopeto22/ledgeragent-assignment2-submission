"""Tests for model client configuration handling."""

from __future__ import annotations

import pytest

from spec_agent.model_client import AnthropicModelClient, ConfigurationError


def test_anthropic_client_requires_credentials(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY"):
        AnthropicModelClient()


def test_anthropic_client_uses_env_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    def fake_anthropic(**kwargs: str) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("spec_agent.model_client.anthropic.Anthropic", fake_anthropic)

    AnthropicModelClient()

    assert captured == {
        "api_key": "test-key",
    }
