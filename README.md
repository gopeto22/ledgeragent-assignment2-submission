# LedgerAgent

LedgerAgent is my submission for LEC AI Assignment 2: Production Agentic System.

It is a small agent runtime for multi-step business analysis. The agent plans before acting, runs independent tool calls in parallel, tracks budget usage, reflects on evidence, and returns a structured answer with an evidence ledger.

The main validation path is offline and deterministic, so the reviewer can run the benchmark without API credentials.

## Suggested review path

1. Read `FINAL_SUBMISSION_SUMMARY.md` for the short overview.
2. Read `HOW_TO_READ_OFFLINE_ARTIFACTS.md` to understand the benchmark outputs.
3. Run the offline benchmark from `RUNNING_LEDGERAGENT.md`.
4. For implementation details, read `solution/REPORT.md` and `solution/ARCHITECTURE.md`.

## Current status

- Runtime implemented across 7 core modules.
- Test suite passes: 59 passed, 3 skipped.
- Offline benchmark runs without credentials.
- Prompt A/B comparison artifacts are included under `solution/eval_artifacts/`.
- Live evaluation can also be run with Anthropic credentials, but it is optional.

## Quick check

```bash
cd solution

python -c "from spec_agent.agent import Agent; print('Agent imports')"
python -m pytest tests/ -q

python -m spec_agent.evals --offline-mode --output-dir ./eval_artifacts
cat eval_artifacts/ablation.md
