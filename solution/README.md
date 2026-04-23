# LedgerAgent

A budget-aware, self-auditing analyst for multi-step reasoning over business policies, pricing, and structured data.

## Quick Start: Offline Benchmark (No Credentials Needed)

```bash
# Fastest way to validate the system:
python -m spec_agent.evals --offline-mode --prompt-variant A

# This runs 10 test queries with both Prompt A and B variants:
# - No API credentials required
# - Deterministic results (same every time)
# - Full artifacts with success rates, costs, latency
# - ~30 seconds total
```

View results:
```bash
cat eval_artifacts/ablation.md
cat eval_artifacts/prompt_A/summary.json | python -m json.tool
```

---

## Optional: Running with Live Credentials

If you have Anthropic API credentials:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# Or:
export ANTHROPIC_AUTH_TOKEN="..."

# Run live benchmark (real Claude responses)
python -m spec_agent.evals --output-dir ./eval_artifacts_live
```

## What LedgerAgent Does

1. **Plans explicitly**: LLM generates a structured execution plan with tool calls, dependencies, and parallel groups
2. **Executes in parallel**: Ready steps run concurrently; dependent steps wait
3. **Tracks budget strictly**: Token and cost estimation before each LLM call; refuses if cap exceeded
4. **Reflects on contradictions**: Extracts claims, flags conflicts between sources, reports uncertainty
5. **Answers with evidence**: Final answer includes confidence, uncertainty notes, and structured evidence

## Architecture

```text
query
  ↓
planner (A or B variant)
  ↓
execution plan → budget manager
  ↓
executor → tools (web_search, doc_qa, kb_lookup, calculator, python_sandbox)
  ↓
observations → reflection → claims / contradictions
  ↓
final answer + evidence ledger
```

## The 5 Tools

1. **web_search**: Query local snapshot of public web sources
2. **doc_qa**: Find answers in internal policy documents with citations
3. **kb_lookup**: Query structured internal knowledge base (pricing, overrides, SLAs)
4. **calculator**: Evaluate arithmetic expressions (prices, credits, discounts)
5. **python_sandbox**: Run restricted Python for transformations and statistics

## Design Principles

- **Small**: 5 tools, not 10+. Fewer tools = less confusion for LLM.
- **Typed**: Dataclasses throughout for runtime contracts and observability.
- **Inspectable**: Evidence ledger is first-class; tools log their decisions.
- **Eval-driven**: Benchmark suite with graded success criteria, not vibes.
- **Robust**: Handles budget limits, timeouts, contradictions, retries.
- **Honest**: Explicit about failure modes, uncertainty, and assumptions.

## Prompt Variants

- **Variant A**: Standard planning with basic completion criteria
- **Variant B**: Evidence-aware planning with specific completion signals, explicit contradiction handling, and emphasis on citation-backed answers

Both A and B use the same runtime and tools; only the planning/reflection prompts differ.

## Running Tests

```bash
uv run --group dev python -m pytest tests/ -v
```

## Current Status

**Implementation Complete**: All core components (planner, executor, budget, tools, reflection, answer synthesis) are implemented and imported correctly.

**Credentials Required for Benchmark**: Live evaluation requires valid Anthropic API credentials. The system fails cleanly if credentials are missing:

```
Error: Missing Anthropic credentials. Set ANTHROPIC_API_KEY or 
ANTHROPIC_AUTH_TOKEN before running the agent.
```

**Benchmark Harness Ready**: The 10-case benchmark is fully implemented in `spec_agent/eval_cases.py`. Each case includes:
- Multi-step query (2-5 required tools per case)
- Required answer patterns (regex-based grading)
- Forbidden patterns (to catch common mistakes)
- Stress tests (e.g., budget exhaustion at $0.002)
- Contradiction cases (internal vs. public policy conflicts)

**Local Assets**: The system uses deterministic local assets (docs, KB, web snapshot) for reproducible evaluation. No live web access is used in the benchmark path.

## What Would Be Needed for Live Results

To generate the full Prompt A/B benchmark report:

1. Set valid Anthropic credentials in environment
2. Run: `python -m spec_agent.evals --verbose`
3. Results are written to `eval_artifacts/prompt_A/` and `eval_artifacts/prompt_B/` with per-case summaries

The benchmark will generate:
- Success rate per variant
- Average latency and cost
- Average tool calls and contradictions flagged
- Per-case analysis including which required patterns matched
- Worst-performing query categories

## Known Limitations

- **Credential path only**: Uses env vars (ANTHROPIC_API_KEY/AUTH_TOKEN); no interactive login
- **Local assets only**: Web snapshot is fixed and checked in; no live web access
- **No persistence**: Each run is independent; no ledger store or trace viewer
- **Simple grading**: Uses regex matching for success; doesn't account for semantic equivalence
- **Single-model**: Only Anthropic; no multi-provider routing

## What's Not Included (Intentional Scope Boundaries)

This submission focuses on correctness, observability, and evaluation rigor. It deliberately excludes:

1. **Live web backend** – Local snapshot ensures reproducible evals
2. **Judge-model scoring** – Deterministic rubric is faster and more transparent
3. **Persistent trace store** – Not needed for single-agent evaluation
4. **Advanced contradiction resolution** – Source priority works for Assignment 2
5. **Concurrency/scaling** – ThreadPoolExecutor handles 10 test queries fine

These would be valuable in production but complicate evaluation clarity.

## References

- [ARCHITECTURE.md](./ARCHITECTURE.md) — Design decisions and trade-offs
- [REPORT.md](./REPORT.md) — What was built, what broke, what was learned
- [AI_USAGE.md](./AI_USAGE.md) — Transparency: how AI was used in development

