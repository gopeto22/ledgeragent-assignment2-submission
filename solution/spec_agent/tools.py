"""Tool registry and deterministic analyst tools for LedgerAgent."""

from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import json
import math
import re
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import Citation, SourceKind

DEFAULT_TOOL_TIMEOUT_SECONDS = 5.0
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "if",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "which",
    "with",
}


@dataclass(frozen=True)
class ToolSpec:
    """Human-readable contract for a tool."""

    name: str
    purpose: str
    when_to_use: str
    when_not_to_use: str
    failure_modes: list[str]
    input_schema: dict[str, Any]
    timeout_seconds: float = DEFAULT_TOOL_TIMEOUT_SECONDS


@dataclass
class ToolResult:
    """Structured tool output."""

    ok: bool
    summary: str
    raw_output: str
    data: dict[str, Any] = field(default_factory=dict)
    citations: list[Citation] = field(default_factory=list)
    error: str | None = None
    timeout_seconds: float = DEFAULT_TOOL_TIMEOUT_SECONDS

    @property
    def is_error(self) -> bool:
        return not self.ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "summary": self.summary,
            "raw_output": self.raw_output,
            "data": self.data,
            "citations": [citation.to_dict() for citation in self.citations],
            "error": self.error,
            "timeout_seconds": self.timeout_seconds,
        }


class ToolExecutionError(RuntimeError):
    """Raised when a tool cannot complete its work."""


class ToolRegistry:
    """Registry and dispatcher for LedgerAgent's tool set."""

    def __init__(self, asset_root: Path) -> None:
        self.asset_root = asset_root
        self.docs = _load_docs(asset_root / "docs")
        self.web_docs = _load_web_snapshot(asset_root / "web_snapshot.json")
        self.kb = json.loads((asset_root / "kb.json").read_text(encoding="utf-8"))
        self.specs: dict[str, ToolSpec] = {
            "web_search": ToolSpec(
                name="web_search",
                purpose="Search a local snapshot of public web sources for current-ish external facts.",
                when_to_use="Use for competitor, market, or public announcement questions.",
                when_not_to_use="Do not use for internal policy or structured pricing facts that already live in the KB or docs.",
                failure_modes=["no matches", "ambiguous public language"],
                input_schema={"query": "string", "top_k": "integer, optional"},
            ),
            "doc_qa": ToolSpec(
                name="doc_qa",
                purpose="Find answers inside internal policy documents and return cited excerpts.",
                when_to_use="Use for policy interpretation, exceptions, and clause-level evidence.",
                when_not_to_use="Do not use when the answer is clearly numeric and already structured in the KB.",
                failure_modes=["no relevant chunk", "conflicting document language"],
                input_schema={"question": "string", "doc_ids": "list[string], optional", "top_k": "integer, optional"},
            ),
            "kb_lookup": ToolSpec(
                name="kb_lookup",
                purpose="Query structured internal records from the JSON knowledge base.",
                when_to_use="Use for plan pricing, overrides, regional caps, and numeric targets.",
                when_not_to_use="Do not use when you need narrative explanation or clause text.",
                failure_modes=["no record found", "collection mismatch"],
                input_schema={"query": "string", "collection": "string, optional", "top_k": "integer, optional"},
            ),
            "calculator": ToolSpec(
                name="calculator",
                purpose="Evaluate exact arithmetic expressions safely.",
                when_to_use="Use for price calculations, credits, discounts, and exact numeric reasoning.",
                when_not_to_use="Do not use for percentiles or data transformations over lists; use python_sandbox instead.",
                failure_modes=["invalid expression", "division by zero"],
                input_schema={"expression": "string"},
            ),
            "python_sandbox": ToolSpec(
                name="python_sandbox",
                purpose="Run deterministic, restricted Python expressions for transformations and statistics.",
                when_to_use="Use for list/dict transformations, percentiles, medians, grouping, and derived metrics.",
                when_not_to_use="Do not use for open-ended scripting, imports, filesystem access, or network access.",
                failure_modes=["unsafe expression", "unsupported function", "bad input data"],
                input_schema={"expression": "string", "data": "JSON value"},
            ),
        }

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> ToolResult:
        handlers = {
            "web_search": self._web_search,
            "doc_qa": self._doc_qa,
            "kb_lookup": self._kb_lookup,
            "calculator": self._calculator,
            "python_sandbox": self._python_sandbox,
        }
        spec = self.specs.get(tool_name)
        handler = handlers.get(tool_name)
        if spec is None or handler is None:
            return ToolResult(
                ok=False,
                summary=f"Unknown tool: {tool_name}",
                raw_output=f"Unknown tool: {tool_name}",
                error=f"Unknown tool: {tool_name}",
            )

        started = time.monotonic()
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(handler, tool_input, spec)
            result = future.result(timeout=spec.timeout_seconds)
        except FutureTimeoutError:
            pool.shutdown(wait=False, cancel_futures=True)
            return ToolResult(
                ok=False,
                summary=f"{tool_name} timed out",
                raw_output=f"{tool_name} timed out after {spec.timeout_seconds:.2f}s",
                error=f"{tool_name} timed out after {spec.timeout_seconds:.2f}s",
                timeout_seconds=spec.timeout_seconds,
            )
        except ToolExecutionError as exc:
            pool.shutdown(wait=True, cancel_futures=True)
            return ToolResult(
                ok=False,
                summary=f"{tool_name} failed",
                raw_output=str(exc),
                error=str(exc),
                timeout_seconds=spec.timeout_seconds,
            )
        except Exception as exc:
            pool.shutdown(wait=True, cancel_futures=True)
            return ToolResult(
                ok=False,
                summary=f"{tool_name} failed",
                raw_output=str(exc),
                error=f"unexpected tool error: {exc}",
                timeout_seconds=spec.timeout_seconds,
            )
        else:
            pool.shutdown(wait=True, cancel_futures=True)
        duration_ms = int((time.monotonic() - started) * 1000)
        result.data.setdefault("duration_ms", duration_ms)
        return result

    def manifest(self) -> str:
        lines = []
        for spec in self.specs.values():
            lines.append(f"- {spec.name}: {spec.purpose}")
            lines.append(f"  use when: {spec.when_to_use}")
            lines.append(f"  do not use when: {spec.when_not_to_use}")
            lines.append(f"  input schema: {json.dumps(spec.input_schema, sort_keys=True)}")
            lines.append(f"  timeout seconds: {spec.timeout_seconds}")
        return "\n".join(lines)

    def list_specs(self) -> list[ToolSpec]:
        return list(self.specs.values())

    def _web_search(self, tool_input: dict[str, Any], spec: ToolSpec) -> ToolResult:
        query = str(tool_input.get("query", "")).strip()
        top_k = int(tool_input.get("top_k", 3))
        if not query:
            raise ToolExecutionError("web_search requires a non-empty query")
        matches = _rank_documents(query, self.web_docs, top_k=top_k)
        citations = [
            Citation(
                source_kind="web",
                source_id=item["id"],
                title=item["title"],
                locator="snapshot",
                uri=item.get("url"),
            )
            for item in matches
        ]
        summary = "Found web evidence" if matches else "No web matches found"
        return ToolResult(
            ok=True,
            summary=summary,
            raw_output=json.dumps(matches, indent=2),
            data={"matches": matches, "query": query},
            citations=citations,
            timeout_seconds=spec.timeout_seconds,
        )

    def _doc_qa(self, tool_input: dict[str, Any], spec: ToolSpec) -> ToolResult:
        question = str(tool_input.get("question", "")).strip()
        doc_ids = {doc_id for doc_id in tool_input.get("doc_ids", [])}
        top_k = int(tool_input.get("top_k", 3))
        if not question:
            raise ToolExecutionError("doc_qa requires a non-empty question")

        candidates = [
            item for item in self.docs if not doc_ids or item["doc_id"] in doc_ids
        ]
        matches = _rank_documents(question, candidates, top_k=top_k)
        citations = [
            Citation(
                source_kind="doc",
                source_id=item["doc_id"],
                title=item["title"],
                locator=item["locator"],
                uri=item["path"],
            )
            for item in matches
        ]
        summary = "Found policy evidence" if matches else "No policy matches found"
        return ToolResult(
            ok=True,
            summary=summary,
            raw_output=json.dumps(matches, indent=2),
            data={"matches": matches, "question": question},
            citations=citations,
            timeout_seconds=spec.timeout_seconds,
        )

    def _kb_lookup(self, tool_input: dict[str, Any], spec: ToolSpec) -> ToolResult:
        query = str(tool_input.get("query", "")).strip()
        collection = tool_input.get("collection")
        top_k = int(tool_input.get("top_k", 5))
        if not query:
            raise ToolExecutionError("kb_lookup requires a non-empty query")

        records: list[dict[str, Any]] = []
        collections = [str(collection)] if collection else list(self.kb.keys())
        for collection_name in collections:
            for index, record in enumerate(self.kb.get(collection_name, [])):
                haystack = json.dumps(record, sort_keys=True).lower()
                score = _score_tokens(_tokenize(query), haystack)
                if score > 0:
                    records.append(
                        {
                            "collection": collection_name,
                            "record_id": f"{collection_name}:{index}",
                            "score": score,
                            "record": record,
                        }
                    )

        records.sort(key=lambda item: item["score"], reverse=True)
        records = records[:top_k]
        citations = [
            Citation(
                source_kind="kb",
                source_id=item["record_id"],
                title=f"{item['collection']} record",
                locator=item["record_id"],
                uri=str(self.asset_root / "kb.json"),
            )
            for item in records
        ]
        summary = "Found KB records" if records else "No KB records found"
        return ToolResult(
            ok=True,
            summary=summary,
            raw_output=json.dumps(records, indent=2),
            data={"matches": records, "query": query},
            citations=citations,
            timeout_seconds=spec.timeout_seconds,
        )

    def _calculator(self, tool_input: dict[str, Any], spec: ToolSpec) -> ToolResult:
        expression = str(tool_input.get("expression", "")).strip()
        if not expression:
            raise ToolExecutionError("calculator requires a non-empty expression")
        try:
            value = _safe_calculate(expression)
        except Exception as exc:
            raise ToolExecutionError(f"calculator failed: {exc}") from exc

        return ToolResult(
            ok=True,
            summary=f"Calculated {value}",
            raw_output=str(value),
            data={"expression": expression, "value": value},
            timeout_seconds=spec.timeout_seconds,
        )

    def _python_sandbox(self, tool_input: dict[str, Any], spec: ToolSpec) -> ToolResult:
        expression = str(tool_input.get("expression", "")).strip()
        data = tool_input.get("data")
        if not expression:
            raise ToolExecutionError("python_sandbox requires a non-empty expression")

        try:
            value = _safe_python_eval(expression, data)
        except Exception as exc:
            raise ToolExecutionError(f"python_sandbox failed: {exc}") from exc

        return ToolResult(
            ok=True,
            summary="Python sandbox expression evaluated successfully",
            raw_output=json.dumps(value, indent=2, default=str),
            data={"expression": expression, "value": value},
            timeout_seconds=spec.timeout_seconds,
        )


def _load_docs(doc_root: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for path in sorted(doc_root.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        sections = re.split(r"^##\s+", raw, flags=re.MULTILINE)
        title = raw.splitlines()[0].lstrip("# ").strip()
        preamble = sections[0].strip()
        if preamble:
            docs.append(
                {
                    "id": path.stem,
                    "doc_id": path.stem,
                    "title": title,
                    "locator": "overview",
                    "path": str(path),
                    "text": preamble,
                }
            )
        for section in sections[1:]:
            lines = section.splitlines()
            heading = lines[0].strip()
            content = "\n".join(lines[1:]).strip()
            docs.append(
                {
                    "id": f"{path.stem}:{heading}",
                    "doc_id": path.stem,
                    "title": title,
                    "locator": heading,
                    "path": str(path),
                    "text": f"{heading}\n{content}",
                }
            )
    return docs


def _load_web_snapshot(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rank_documents(query: str, docs: list[dict[str, Any]], *, top_k: int) -> list[dict[str, Any]]:
    query_tokens = _tokenize(query)
    scored = []
    for item in docs:
        score = _score_tokens(query_tokens, item["text"].lower())
        if score <= 0:
            continue
        scored.append(
            {
                **item,
                "score": score,
                "snippet": _make_snippet(item["text"], query_tokens),
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def _tokenize(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-zA-Z0-9_]+", text.lower())
        if token not in STOPWORDS
    ]


def _score_tokens(query_tokens: list[str], haystack: str) -> float:
    if not query_tokens:
        return 0.0
    return float(sum(1 for token in query_tokens if token in haystack))


def _make_snippet(text: str, query_tokens: list[str], *, max_chars: int = 220) -> str:
    lowered = text.lower()
    for token in query_tokens:
        index = lowered.find(token)
        if index >= 0:
            start = max(0, index - 40)
            end = min(len(text), index + max_chars)
            return text[start:end].strip()
    return text[:max_chars].strip()


ALLOWED_CALCULATOR_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Constant,
    ast.Load,
    ast.FloorDiv,
    ast.Tuple,
    ast.List,
)


def _safe_calculate(expression: str) -> float:
    tree = ast.parse(expression, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_CALCULATOR_NODES):
            raise ValueError(f"Unsupported calculator expression node: {type(node).__name__}")
    value = eval(compile(tree, "<calculator>", "eval"), {"__builtins__": {}}, {})
    if not isinstance(value, (int, float)):
        raise ValueError("calculator expression did not produce a numeric result")
    return float(value) if isinstance(value, float) else value


ALLOWED_PYTHON_NODES = (
    ast.Expression,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Subscript,
    ast.Slice,
    ast.Index,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Gt,
    ast.GtE,
    ast.Lt,
    ast.LtE,
    ast.Call,
    ast.keyword,
)

ALLOWED_PYTHON_CALLS = {"len", "sum", "min", "max", "sorted", "round", "median", "percentile"}


def _safe_python_eval(expression: str, data: Any) -> Any:
    tree = ast.parse(expression, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_PYTHON_NODES):
            raise ValueError(f"Unsupported python_sandbox node: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_PYTHON_CALLS:
                raise ValueError("Only approved helper functions are allowed in python_sandbox")
        if isinstance(node, ast.Name) and node.id not in ALLOWED_PYTHON_CALLS | {"data"}:
            raise ValueError(f"Unknown name in python_sandbox: {node.id}")
    helpers = {
        "len": len,
        "sum": sum,
        "min": min,
        "max": max,
        "sorted": sorted,
        "round": round,
        "median": lambda values: statistics.median(list(values)),
        "percentile": _percentile,
    }
    return eval(compile(tree, "<python_sandbox>", "eval"), {"__builtins__": {}}, {"data": data, **helpers})


def _percentile(values: list[float] | tuple[float, ...], pct: float) -> float:
    if not values:
        raise ValueError("percentile requires a non-empty list")
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (float(pct) / 100) * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(ordered[lower])
    lower_value = float(ordered[lower])
    upper_value = float(ordered[upper])
    weight = rank - lower
    return lower_value + (upper_value - lower_value) * weight
