"""Tests for LedgerAgent's analyst tools."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

from spec_agent.tools import ToolRegistry, ToolResult


def _asset_root() -> Path:
    return Path(__file__).resolve().parents[1] / "assets"


def test_manifest_lists_all_required_tools():
    registry = ToolRegistry(_asset_root())
    manifest = registry.manifest()

    assert "web_search" in manifest
    assert "doc_qa" in manifest
    assert "kb_lookup" in manifest
    assert "calculator" in manifest
    assert "python_sandbox" in manifest


def test_web_search_returns_snapshot_results():
    registry = ToolRegistry(_asset_root())

    result = registry.execute("web_search", {"query": "Acme uptime credits", "top_k": 2})

    assert result.ok
    assert result.data["matches"]
    assert any("Acme" in item["title"] for item in result.data["matches"])
    assert any(citation.source_kind == "web" for citation in result.citations)


def test_doc_qa_returns_policy_excerpt():
    registry = ToolRegistry(_asset_root())

    result = registry.execute(
        "doc_qa",
        {"question": "What is the UK dinner cap?", "doc_ids": ["expense_policy"], "top_k": 2},
    )

    assert result.ok
    assert "75 GBP" in result.raw_output
    assert any(citation.source_kind == "doc" for citation in result.citations)


def test_kb_lookup_returns_structured_record():
    registry = ToolRegistry(_asset_root())

    result = registry.execute(
        "kb_lookup",
        {"collection": "plans", "query": "Enterprise seat price"},
    )

    assert result.ok
    assert result.data["matches"]
    assert result.data["matches"][0]["collection"] == "plans"
    assert "149" in result.raw_output


def test_calculator_evaluates_arithmetic():
    registry = ToolRegistry(_asset_root())

    result = registry.execute("calculator", {"expression": "42 * 89 + 70 * 0.12"})

    assert result.ok
    assert abs(float(result.data["value"]) - 3746.4) < 1e-9


def test_calculator_rejects_unsafe_expression():
    registry = ToolRegistry(_asset_root())

    result = registry.execute("calculator", {"expression": "__import__('os').system('pwd')"})

    assert result.is_error
    assert "failed" in result.summary.lower()


def test_python_sandbox_supports_percentile_helpers():
    registry = ToolRegistry(_asset_root())

    result = registry.execute(
        "python_sandbox",
        {
            "expression": "percentile(data['latencies'], 90)",
            "data": {"latencies": [120, 180, 220, 260, 300, 340]},
        },
    )

    assert result.ok
    assert abs(float(result.data["value"]) - 320.0) < 1e-9


def test_python_sandbox_rejects_imports():
    registry = ToolRegistry(_asset_root())

    result = registry.execute(
        "python_sandbox",
        {"expression": "__import__('os')", "data": {}},
    )

    assert result.is_error
    assert "failed" in result.summary.lower()


def test_tool_execution_enforces_timeouts():
    registry = ToolRegistry(_asset_root())
    registry.specs["calculator"] = replace(
        registry.specs["calculator"],
        timeout_seconds=0.01,
    )

    def slow_calculator(tool_input: dict[str, object], spec) -> ToolResult:
        time.sleep(spec.timeout_seconds * 2)
        return ToolResult(
            ok=True,
            summary="finished",
            raw_output="2",
            data={"value": 2},
            timeout_seconds=spec.timeout_seconds,
        )

    registry._calculator = slow_calculator  # type: ignore[method-assign]

    result = registry.execute("calculator", {"expression": "1 + 1"})

    assert result.is_error
    assert "timed out" in (result.error or "")


def test_unexpected_tool_exceptions_are_returned_as_structured_failures():
    registry = ToolRegistry(_asset_root())

    def broken_calculator(tool_input: dict[str, object], spec) -> ToolResult:
        raise ValueError("boom")

    registry._calculator = broken_calculator  # type: ignore[method-assign]

    result = registry.execute("calculator", {"expression": "1 + 1"})

    assert result.is_error
    assert result.error == "unexpected tool error: boom"
