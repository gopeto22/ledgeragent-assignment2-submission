"""LedgerAgent benchmark harness with Prompt A/B ablation."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .agent import Agent
from .eval_cases import benchmark_cases
from .model_client import ConfigurationError
from .models import AgentConfig, AgentResult, PromptVariant

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkSummary:
    """Summary statistics for a single case."""

    name: str
    category: str
    success: bool
    elapsed_seconds: float
    tool_calls: int
    cost_usd: float
    contradictions_flagged: int
    matches_required_patterns: list[str]
    matches_forbidden_patterns: list[str]
    reasons: list[str] = None

    def __post_init__(self) -> None:
        if self.reasons is None:
            self.reasons = []


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ledger-agent-eval",
        description="Run LedgerAgent against the 10-case benchmark.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("eval_artifacts"),
        help="Directory for benchmark artifacts",
    )
    parser.add_argument(
        "--prompt-variant",
        choices=["A", "B"],
        default=None,
        help="Run only variant A or B. Default: run both",
    )
    parser.add_argument(
        "--asset-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "assets",
        help="Asset root directory",
    )
    parser.add_argument(
        "--offline-mode",
        action="store_true",
        help="Use deterministic FakeModelClient (no credentials required)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    variants_to_run = []
    if args.prompt_variant:
        variants_to_run = [args.prompt_variant]
    else:
        variants_to_run = ["A", "B"]

    try:
        run_dir = args.output_dir
        run_dir.mkdir(parents=True, exist_ok=True)

        variant_summaries = {}
        for variant in variants_to_run:
            logger.info(f"Running benchmark with Prompt {variant}...")
            summary = run_benchmark(
                variant=variant,
                asset_root=args.asset_root,
                output_dir=run_dir,
                offline_mode=args.offline_mode,
            )
            variant_summaries[variant] = summary
            print(json.dumps(summary, indent=2))

        # Generate ablation comparison if multiple variants
        if len(variant_summaries) > 1:
            logger.info("Generating ablation comparison...")
            ablation = _generate_ablation_comparison(variant_summaries)
            
            # Write ablation JSON
            (run_dir / "ablation.json").write_text(json.dumps(ablation, indent=2))
            
            # Write ablation markdown
            ablation_md = render_ablation_comparison_markdown(ablation)
            (run_dir / "ablation.md").write_text(ablation_md)
            
            logger.info(f"Ablation complete. Preferred variant: {ablation.get('preferred_variant')}")

        return 0

    except ConfigurationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        logger.exception("Unexpected error")
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def run_benchmark(
    *,
    variant: str,
    asset_root: Path,
    output_dir: Path,
    offline_mode: bool = False,
) -> dict:
    """Run full benchmark suite with a single prompt variant.
    
    Args:
        variant: "A" or "B" for prompt variant
        asset_root: Path to assets directory
        output_dir: Directory to write artifacts
        offline_mode: If True, use FakeModelClient for deterministic testing
    """
    cases = benchmark_cases()
    case_summaries = []
    variant_dir = output_dir / f"prompt_{variant}"
    variant_dir.mkdir(parents=True, exist_ok=True)

    config = AgentConfig(
        model="evals-anthropic/claude-sonnet-4-6",
        prompt_variant=variant,
        max_budget_usd=0.25,
        max_cycles=2,
    )

    for case in cases:
        logger.info(f"Running case: {case.name}")
        try:
            agent = Agent.create(
                config=config,
                asset_root=asset_root,
                offline_mode=offline_mode,
            )
            result = agent.run(case.query)

            # Evaluate against success criteria
            success, matched_patterns, forbidden_matched = _evaluate_result(
                result.final_answer,
                case.required_patterns,
                case.forbidden_patterns,
            )

            contradictions_count = len(result.contradictions)
            
            # Classify failure if case didn't pass
            failure_info = {}
            if not (success and result.success):
                failure_info = _classify_failure(result, case)

            case_summary: dict = {
                "name": case.name,
                "category": case.category,
                "success": success and result.success,
                "elapsed_seconds": result.elapsed_seconds,
                "tool_calls": len(result.tool_calls),
                "cost_usd": result.run_state.budget.spent_usd,
                "contradictions_flagged": contradictions_count,
                "termination_reason": result.run_state.termination_reason,
                "matched_required_patterns": matched_patterns,
                "matched_forbidden_patterns": forbidden_matched,
                "answer_preview": result.final_answer[:100] if result.final_answer else "",
                "confidence": result.confidence,
                "failure_classification": failure_info if failure_info else None,
            }

            if case.budget_override_usd:
                case_summary["budget_override_applied"] = True

            case_summaries.append(case_summary)

            # Write per-case artifact
            case_dir = variant_dir / case.name
            case_dir.mkdir(parents=True, exist_ok=True)
            (case_dir / "result.json").write_text(json.dumps(result.to_dict(), indent=2))
            (case_dir / "case_summary.json").write_text(json.dumps(case_summary, indent=2))
            
            # Write human-readable case report
            case_report = _render_case_report(case_summary, case)
            (case_dir / "report.md").write_text(case_report)

        except ConfigurationError as exc:
            raise
        except Exception as exc:
            logger.exception(f"Case {case.name} failed")
            case_summaries.append({
                "name": case.name,
                "category": case.category,
                "success": False,
                "error": str(exc),
            })

    # Aggregate results
    passed = sum(1 for cs in case_summaries if cs.get("success", False))
    total = len(case_summaries)
    avg_cost = (
        sum(cs.get("cost_usd", 0) for cs in case_summaries) / total
        if total > 0 else 0
    )
    avg_latency = (
        sum(cs.get("elapsed_seconds", 0) for cs in case_summaries) / total
        if total > 0 else 0
    )

    # Calculate per-category pass rates
    category_stats: dict[str, dict[str, float | int]] = {}
    for cs in case_summaries:
        cat = cs.get("category", "unknown")
        if cat not in category_stats:
            category_stats[cat] = {"passed": 0, "total": 0, "failures": {}}
        category_stats[cat]["total"] += 1
        if cs.get("success", False):
            category_stats[cat]["passed"] += 1
        else:
            failure_cat = cs.get("failure_classification", {}).get("category", "unknown")
            if failure_cat not in category_stats[cat]["failures"]:
                category_stats[cat]["failures"][failure_cat] = 0
            category_stats[cat]["failures"][failure_cat] += 1

    category_pass_rates = {
        cat: {
            "passed": stats["passed"],
            "total": stats["total"],
            "pass_rate": stats["passed"] / stats["total"] if stats["total"] > 0 else 0,
            "failure_categories": stats["failures"]
        }
        for cat, stats in category_stats.items()
    }

    # Generate failure analysis
    failure_analysis = _generate_failure_analysis(case_summaries)

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "prompt_variant": variant,
        "total_cases": total,
        "passed": passed,
        "failed": total - passed,
        "success_rate": passed / total if total > 0 else 0,
        "avg_cost_usd": avg_cost,
        "avg_latency_seconds": avg_latency,
        "category_pass_rates": category_pass_rates,
        "failure_analysis": failure_analysis,
        "cases": case_summaries,
    }

    # Write variant summary
    (variant_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    # Write failure analysis markdown
    if failure_analysis["total_failures"] > 0:
        failure_md = render_failure_analysis_markdown(failure_analysis)
        (variant_dir / "failure_analysis.md").write_text(failure_md)

    return summary


def _evaluate_result(
    answer: str,
    required_patterns: list[str],
    forbidden_patterns: list[str],
) -> tuple[bool, list[str], list[str]]:
    """Check if answer matches required/forbidden patterns."""
    import re

    matched_required = []
    matched_forbidden = []

    for pattern in required_patterns:
        if re.search(pattern, answer, re.IGNORECASE):
            matched_required.append(pattern)

    for pattern in forbidden_patterns:
        if re.search(pattern, answer, re.IGNORECASE):
            matched_forbidden.append(pattern)

    # Pass if all required patterns match and no forbidden patterns match
    success = (
        len(matched_required) == len(required_patterns)
        and len(matched_forbidden) == 0
    )

    return success, matched_required, matched_forbidden


def _classify_failure(
    result: AgentResult,
    case: object,
) -> dict[str, str | float]:
    """Classify the reason for failure and assign failure categories."""
    classification = {
        "category": "unknown",
        "severity": "minor",
        "reason": "",
    }

    # Budget exhaustion
    if result.run_state.termination_reason == "budget_exceeded":
        classification["category"] = "budget_exhaustion"
        classification["severity"] = "major"
        classification["reason"] = "Ran out of token/cost budget before gathering sufficient evidence"
        return classification

    # Planning failure
    if result.run_state.termination_reason in ("planner_failed", "planning_error"):
        classification["category"] = "planner_failure"
        classification["severity"] = "critical"
        classification["reason"] = "LLM planner couldn't generate a valid execution plan"
        return classification

    # Tool execution failure
    if result.run_state.termination_reason == "execution_error":
        classification["category"] = "tool_failure"
        classification["severity"] = "major"
        classification["reason"] = f"Tool execution failed. Failures: {result.run_state.tool_failures}"
        return classification

    # Max iterations reached without sufficient evidence
    if result.run_state.cycles >= 2:
        classification["category"] = "max_iterations"
        classification["severity"] = "medium"
        classification["reason"] = "Reached max iterations without sufficient evidence"
        return classification

    # Unresolved contradictions
    if result.contradictions:
        unresolved = [c for c in result.contradictions if c.unresolved]
        if unresolved:
            classification["category"] = "unresolved_contradiction"
            classification["severity"] = "medium"
            classification["reason"] = f"Flagged {len(unresolved)} unresolved contradictions"
            return classification

    # Low confidence answer
    if not result.success and result.confidence < 0.5:
        classification["category"] = "low_confidence"
        classification["severity"] = "minor"
        classification["reason"] = f"Low confidence ({result.confidence:.1%}) answer"
        return classification

    # Pattern matching failure (insufficient evidence in answer)
    classification["category"] = "pattern_mismatch"
    classification["severity"] = "minor"
    classification["reason"] = "Answer didn't match required patterns"
    return classification


def _generate_failure_analysis(case_summaries: list[dict]) -> dict[str, Any]:
    """Generate structured failure analysis from case summaries."""
    failures_by_category: dict[str, list[dict]] = {}
    failures_by_reason: dict[str, list[dict]] = {}
    high_severity_failures: list[dict] = []
    
    for case in case_summaries:
        if not case.get("success", False):
            failure_info = case.get("failure_classification", {})
            
            # Group by failure category
            fail_category = failure_info.get("category", "unknown")
            if fail_category not in failures_by_category:
                failures_by_category[fail_category] = []
            failures_by_category[fail_category].append({
                "case": case.get("name"),
                "severity": failure_info.get("severity", "unknown"),
                "reason": failure_info.get("reason", ""),
            })
            
            # Group by failure reason
            fail_reason = failure_info.get("reason", "unknown")
            if fail_reason not in failures_by_reason:
                failures_by_reason[fail_reason] = []
            failures_by_reason[fail_reason].append(case.get("name"))
            
            # Collect high-severity failures
            if failure_info.get("severity") in ("critical", "major"):
                high_severity_failures.append({
                    "case": case.get("name"),
                    "category": case.get("category"),
                    "severity": failure_info.get("severity"),
                    "reason": failure_info.get("reason"),
                })
    
    return {
        "total_failures": len([c for c in case_summaries if not c.get("success")]),
        "failures_by_category": failures_by_category,
        "failures_by_reason": failures_by_reason,
        "high_severity_failures": high_severity_failures,
    }


def _render_case_report(case_summary: dict, case: object) -> str:
    """Render a case execution report as markdown."""
    lines = [
        f"# Case: {case_summary.get('name', 'unknown')}",
        "",
        f"**Status**: {'✅ PASS' if case_summary.get('success') else '❌ FAIL'}",
        f"**Category**: {case_summary.get('category', 'unknown')}",
        f"**Confidence**: {case_summary.get('confidence', 0):.1%}",
        "",
        "## Metrics",
        f"- Tool calls: {case_summary.get('tool_calls', 0)}",
        f"- Cost: ${case_summary.get('cost_usd', 0):.4f}",
        f"- Latency: {case_summary.get('elapsed_seconds', 0):.2f}s",
        f"- Termination: {case_summary.get('termination_reason', 'unknown')}",
        "",
        "## Evidence Evaluation",
        f"- Contradictions detected: {case_summary.get('contradictions_flagged', 0)}",
        f"- Required patterns matched: {len(case_summary.get('matched_required_patterns', []))}/{len(case.required_patterns) if hasattr(case, 'required_patterns') else '?'}",
        f"- Forbidden patterns matched: {len(case_summary.get('matched_forbidden_patterns', []))}",
        "",
    ]
    
    # Failure details
    failure_info = case_summary.get("failure_classification")
    if failure_info:
        lines.append("## Failure Details")
        lines.append(f"- Category: {failure_info.get('category', 'unknown')}")
        lines.append(f"- Severity: {failure_info.get('severity', 'unknown')}")
        lines.append(f"- Reason: {failure_info.get('reason', '')}")
        lines.append("")
    
    # Answer preview
    if case_summary.get("answer_preview"):
        lines.append("## Answer Preview")
        lines.append(f"> {case_summary.get('answer_preview', '')}")
        lines.append("")
    
    return "\n".join(lines)


def _generate_ablation_comparison(variant_summaries: dict[str, dict]) -> dict[str, Any]:
    """Generate cross-variant comparison metrics from multiple variant summaries."""
    if len(variant_summaries) < 2:
        return {}
    
    variants = list(variant_summaries.keys())
    var_a, var_b = variants[0], variants[1]
    
    summary_a = variant_summaries[var_a]
    summary_b = variant_summaries[var_b]
    
    # Calculate deltas
    success_rate_a = summary_a.get("success_rate", 0)
    success_rate_b = summary_b.get("success_rate", 0)
    
    cost_a = summary_a.get("avg_cost_usd", 0)
    cost_b = summary_b.get("avg_cost_usd", 0)
    
    latency_a = summary_a.get("avg_latency_seconds", 0)
    latency_b = summary_b.get("avg_latency_seconds", 0)
    
    # Determine preferred variant (higher success rate wins, then lower cost)
    preferred = var_a
    if success_rate_b > success_rate_a:
        preferred = var_b
    elif success_rate_b == success_rate_a and cost_b < cost_a:
        preferred = var_b
    
    # Category-level comparison
    category_comparison = {}
    categories_a = set(summary_a.get("category_pass_rates", {}).keys())
    categories_b = set(summary_b.get("category_pass_rates", {}).keys())
    for cat in categories_a | categories_b:
        rate_a = summary_a.get("category_pass_rates", {}).get(cat, {}).get("pass_rate", 0)
        rate_b = summary_b.get("category_pass_rates", {}).get(cat, {}).get("pass_rate", 0)
        category_comparison[cat] = {
            "variant_a_pass_rate": rate_a,
            "variant_b_pass_rate": rate_b,
            "delta": rate_b - rate_a,
            "winner": var_b if rate_b > rate_a else (var_a if rate_a > rate_b else "tie"),
        }
    
    return {
        "variant_a": var_a,
        "variant_b": var_b,
        "preferred_variant": preferred,
        "success_rate_delta": success_rate_b - success_rate_a,
        "success_rate_delta_percent": ((success_rate_b - success_rate_a) / success_rate_a * 100) if success_rate_a > 0 else 0,
        "cost_delta": cost_b - cost_a,
        "cost_delta_percent": ((cost_b - cost_a) / cost_a * 100) if cost_a > 0 else 0,
        "latency_delta": latency_b - latency_a,
        "latency_delta_percent": ((latency_b - latency_a) / latency_a * 100) if latency_a > 0 else 0,
        "category_comparison": category_comparison,
        "hardest_for_both": _find_hardest_categories(variants, [summary_a, summary_b]),
        "variant_a_advantages": _find_variant_advantages(var_a, category_comparison),
        "variant_b_advantages": _find_variant_advantages(var_b, category_comparison),
    }


def _find_hardest_categories(variants: list[str], summaries: list[dict]) -> list[str]:
    """Find categories where both variants struggle."""
    hardest = []
    for variant_sum in summaries:
        category_rates = variant_sum.get("category_pass_rates", {})
        for cat, stats in category_rates.items():
            if stats.get("pass_rate", 1.0) < 0.5:  # < 50% pass rate
                if cat not in hardest:
                    hardest.append(cat)
    return hardest


def _find_variant_advantages(variant: str, category_comparison: dict) -> list[str]:
    """Find categories where a variant significantly outperforms."""
    advantages = []
    for cat, comp in category_comparison.items():
        if comp["winner"] == variant:
            delta = abs(comp["delta"])
            if delta > 0.1:  # > 10 percentage point advantage
                advantages.append(f"{cat} (+{delta:.0%})")
    return advantages


def render_ablation_comparison_markdown(ablation: dict) -> str:
    """Render ablation comparison as detailed markdown."""
    lines = [
        "# Prompt Ablation Comparison",
        "",
        f"**Preferred Variant**: {ablation.get('preferred_variant', 'unknown')}",
        "",
        "## Overall Metrics",
        "",
        "| Metric | Variant A | Variant B | Delta |",
        "|--------|-----------|-----------|-------|",
    ]
    
    # Success rate
    var_a = ablation.get('variant_a', 'A')
    var_b = ablation.get('variant_b', 'B')
    
    # Note: The success rates would come from the variant_summaries passed in
    # For now, we'll use the delta values
    lines.append(f"| Success Rate | {ablation.get('success_rate_delta', 0):+.1%} |")
    lines.append(f"| Cost | {ablation.get('cost_delta_percent', 0):+.1f}% |")
    lines.append(f"| Latency | {ablation.get('latency_delta_percent', 0):+.1f}% |")
    lines.append("")
    
    # Category breakdown
    category_comp = ablation.get("category_comparison", {})
    if category_comp:
        lines.append("## Per-Category Performance")
        lines.append("")
        lines.append(f"| Category | {var_a} | {var_b} | Winner |")
        lines.append("|----------|-----------|-----------|--------|")
        
        for cat, comp in sorted(category_comp.items()):
            winner = comp.get("winner", "tie").upper()
            lines.append(
                f"| {cat} | {comp.get('variant_a_pass_rate', 0):.0%} | "
                f"{comp.get('variant_b_pass_rate', 0):.0%} | {winner} |"
            )
        lines.append("")
    
    # Advantages
    var_a_adv = ablation.get("variant_a_advantages", [])
    var_b_adv = ablation.get("variant_b_advantages", [])
    
    if var_a_adv or var_b_adv:
        lines.append("## Strengths")
        lines.append("")
        if var_a_adv:
            lines.append(f"**Variant {var_a} excels at**: {', '.join(var_a_adv)}")
        if var_b_adv:
            lines.append(f"**Variant {var_b} excels at**: {', '.join(var_b_adv)}")
        lines.append("")
    
    # Hardest categories
    hardest = ablation.get("hardest_for_both", [])
    if hardest:
        lines.append("## Challenging Categories")
        lines.append("")
        lines.append("Both variants struggle with:")
        for cat in hardest:
            lines.append(f"- {cat}")
        lines.append("")
    
    return "\n".join(lines)


def render_failure_analysis_markdown(failure_analysis: dict) -> str:
    """Render failure analysis as markdown."""
    lines = [
        "# Failure Analysis",
        "",
        f"Total failures: {failure_analysis.get('total_failures', 0)}",
        "",
    ]
    
    # High severity failures
    high_severity = failure_analysis.get("high_severity_failures", [])
    if high_severity:
        lines.append("## Critical Issues")
        lines.append("")
        for failure in high_severity:
            lines.append(f"- **{failure['case']}** ({failure['category']}): {failure['reason']}")
        lines.append("")
    
    # Failures by category
    by_category = failure_analysis.get("failures_by_category", {})
    if by_category:
        lines.append("## Failures by Type")
        lines.append("")
        for category, failures in sorted(by_category.items()):
            lines.append(f"### {category} ({len(failures)} cases)")
            for f in failures:
                severity_badge = f"[{f['severity'].upper()}]"
                lines.append(f"- {severity_badge} {f['case']}: {f['reason']}")
            lines.append("")
    
    return "\n".join(lines)


def render_summary_markdown(summary: dict) -> str:
    """Render a benchmark summary as markdown with ablation comparison."""
    lines = [
        "# LedgerAgent eval summary",
        "",
        f"Generated: {summary.get('generated_at', 'unknown')}",
        f"Model: {summary.get('model', 'unknown')}",
        "",
        "## Prompt Ablation",
        "",
    ]

    # Add variant comparison if available
    if "variants" in summary and isinstance(summary.get("variants"), list) and len(summary["variants"]) > 0:
        lines.append("### Results by Variant")
        lines.append("")
        lines.append("| Variant | Pass Rate | Avg Cost | Avg Latency |")
        lines.append("|---------|-----------|----------|-------------|")
        
        for variant in summary["variants"]:
            if "variant" in variant:
                pass_rate = variant.get('success_rate', 0)
                avg_cost = variant.get('avg_cost_usd', 0)
                avg_latency = variant.get('avg_latency_seconds', 0)
                lines.append(f"| {variant['variant']} | {pass_rate:.1%} | ${avg_cost:.4f} | {avg_latency:.2f}s |")
        lines.append("")
        
        # Add detailed variant sections
        for variant in summary["variants"]:
            if "variant" in variant:
                lines.append(f"### Variant {variant['variant']}")
                lines.append(f"- Success rate: {variant.get('success_rate', 0):.1%}")
                lines.append(f"- Avg latency: {variant.get('avg_latency_seconds', 0):.2f}s")
                lines.append(f"- Avg cost: ${variant.get('avg_cost_usd', 0):.4f}")
                if "avg_rubric" in variant:
                    lines.append(f"- Avg rubric score: {variant.get('avg_rubric', 0):.1f}/10")
                lines.append("")

    # Add ablation conclusion if available
    if "ablation" in summary:
        ablation = summary["ablation"]
        if "preferred_variant" in ablation:
            lines.append(f"**Preferred variant: {ablation['preferred_variant']}**")
        if "success_rate_delta" in ablation:
            delta = ablation['success_rate_delta']
            direction = "improvement" if delta > 0 else "decline"
            lines.append(f"Success rate {direction}: {delta:+.1%}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
