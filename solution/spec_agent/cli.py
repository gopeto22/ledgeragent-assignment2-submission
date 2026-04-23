"""CLI entrypoint for LedgerAgent."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .agent import Agent, AgentConfig
from .model_client import ConfigurationError


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ledger-agent",
        description="Run LedgerAgent on a multi-step analyst query.",
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="User query to answer. Use --query-file for longer prompts.",
    )
    parser.add_argument(
        "--query-file",
        type=Path,
        help="Path to a file containing the query text.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name (default: evals-anthropic/claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--prompt-variant",
        choices=["A", "B"],
        default="B",
        help="Prompt bundle to use for planning/reflection.",
    )
    parser.add_argument(
        "--max-budget-usd",
        type=float,
        default=0.25,
        help="Hard estimated cost cap for the run.",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=2,
        help="Maximum planning/execution cycles before stopping.",
    )
    parser.add_argument(
        "--asset-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "assets",
        help="Directory containing docs, KB, and web snapshot assets.",
    )
    parser.add_argument(
        "--output-ledger",
        type=Path,
        help="Optional path to write the JSON evidence ledger.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        query = _load_query(args)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    config_kwargs: dict[str, object] = {
        "prompt_variant": args.prompt_variant,
        "max_budget_usd": args.max_budget_usd,
        "max_cycles": args.max_cycles,
    }
    if args.model is not None:
        config_kwargs["model"] = args.model

    try:
        agent = Agent.create(
            config=AgentConfig(**config_kwargs),
            asset_root=args.asset_root,
        )
        result = agent.run(query)
    except ConfigurationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.output_ledger:
        args.output_ledger.parent.mkdir(parents=True, exist_ok=True)
        args.output_ledger.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

    print(result.final_answer)
    print()
    print(
        f"Termination: {result.run_state.termination_reason} | "
        f"Confidence: {result.confidence:.2f} | "
        f"Tool calls: {len(result.tool_calls)} | "
        f"Estimated cost: ${result.run_state.budget.spent_usd:.4f}"
    )
    if result.uncertainty_notes:
        print("Uncertainty:")
        for note in result.uncertainty_notes:
            print(f"- {note}")
    return 0 if result.success else 1


def _load_query(args: argparse.Namespace) -> str:
    if args.query_file:
        if not args.query_file.is_file():
            raise ValueError(f"Query file not found: {args.query_file}")
        query = args.query_file.read_text(encoding="utf-8")
    else:
        query = args.query or ""
    if not query.strip():
        raise ValueError("Provide a query as an argument or via --query-file")
    return query.strip()


if __name__ == "__main__":
    raise SystemExit(main())
