
---

## `FINAL_SUBMISSION_SUMMARY.md`

```md
# LedgerAgent: Executive Summary

LedgerAgent is my Assignment 2 submission for a production-style agentic system. It answers multi-step business queries by planning, calling tools, reflecting on evidence, and returning a final answer with a structured evidence ledger.

The system is intentionally small: five tools, typed runtime contracts, deterministic local assets, and a benchmark harness with Prompt A/B comparison. I focused on reliability and inspectability rather than adding a large tool surface.

## Offline benchmark results

The included offline benchmark runs without credentials and covers 10 cases across retrieval, arithmetic, policy reasoning, contradiction detection, and budget handling.

| Metric | Prompt A | Prompt B |
|---|---:|---:|
| Success rate | 100% | 100% |
| Average cost | $0.0156 | $0.0273 |
| Average latency | 1.47s | 2.76s |

Prompt A is the preferred offline variant because it reaches the same success rate with lower cost and latency.

Artifacts are stored under:

```text
solution/eval_artifacts/
