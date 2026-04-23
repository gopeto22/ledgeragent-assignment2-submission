"""CLI tests for LedgerAgent."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spec_agent.cli import main, parse_args
from spec_agent.model_client import ConfigurationError


class TestParseArgs:
    def test_accepts_query_argument(self):
        args = parse_args(["What is our Pro price?"])
        assert args.query == "What is our Pro price?"
        assert args.prompt_variant == "B"

    def test_accepts_query_file(self, tmp_path: Path):
        query_file = tmp_path / "query.txt"
        query_file.write_text("hello")
        args = parse_args(["--query-file", str(query_file), "--prompt-variant", "A"])
        assert args.query_file == query_file
        assert args.prompt_variant == "A"


class TestMain:
    def test_missing_query_returns_error(self):
        result = main([])
        assert result == 1

    @patch("spec_agent.cli.Agent")
    def test_successful_run_writes_ledger(
        self, mock_agent_cls: MagicMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ):
        ledger_path = tmp_path / "ledger.json"
        mock_agent = MagicMock()
        mock_agent.run.return_value = MagicMock(
            success=True,
            final_answer="Here is the answer.",
            confidence=0.8,
            uncertainty_notes=[],
            tool_calls=[MagicMock(), MagicMock()],
            run_state=MagicMock(
                termination_reason="completed",
                budget=MagicMock(spent_usd=0.0123),
            ),
            to_dict=MagicMock(return_value={"answer": "ok"}),
        )
        mock_agent_cls.create.return_value = mock_agent

        result = main(["What is our Pro price?", "--output-ledger", str(ledger_path)])

        assert result == 0
        assert json.loads(ledger_path.read_text(encoding="utf-8")) == {"answer": "ok"}
        captured = capsys.readouterr()
        assert "Here is the answer." in captured.out

    @patch("spec_agent.cli.Agent")
    def test_configuration_error_is_reported(
        self, mock_agent_cls: MagicMock, capsys: pytest.CaptureFixture[str]
    ):
        mock_agent_cls.create.side_effect = ConfigurationError("Missing Anthropic credentials")

        result = main(["What is our Pro price?"])

        assert result == 1
        captured = capsys.readouterr()
        assert "Missing Anthropic credentials" in captured.err
