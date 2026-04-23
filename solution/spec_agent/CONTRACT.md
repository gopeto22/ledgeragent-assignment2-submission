# LedgerAgent Runtime Contracts

This document specifies the exact shape of all core data structures. Code and tests must match this exactly.

## AgentResult

Final structured result from a single agent run.

```
AgentResult:
  success: bool                              # True if the run completed successfully
  query: str                                 # The input query
  final_answer: str                          # The synthesized answer
  confidence: float                          # 0.0 to 1.0 confidence in the answer
  plan: ExecutionPlan | None                 # The execution plan generated (may be None if planning failed)
  observations: list[ToolObservation]        # All tool calls and their results
  claims: list[EvidenceClaim]                # Claims extracted during reflection
  contradictions: list[Contradiction]        # Contradictions detected between claims
  uncertainty_notes: list[str]               # Notes about areas of uncertainty
  tool_calls: list[ToolCall]                 # Flattened list of all tool invocations
  run_state: AgentRunState                   # State summary of the run
  elapsed_seconds: float                     # Total wall-clock time
```

## AgentRunState

Summary state of a single agent run for artifact reporting.

```
AgentRunState:
  termination_reason: str                    # "completed", "budget_exceeded", "planner_failed", "execution_error", "max_cycles_reached"
  model_calls: int                           # Total LLM calls (planning + reflection + answer synthesis)
  tool_calls: int                            # Total tool invocations
  tool_failures: int                         # Number of tool calls that failed
  tool_retries: int                          # Total retry attempts
  parallel_batches: int                      # Number of parallel execution groups
  cycles: int                                # Number of agent loops completed
  failure_notes: list[str]                   # Human-readable notes about any failures
  budget: BudgetState                        # Final budget state
```

## BenchmarkSummary (per-case artifact)

Summary for a single benchmark case.

```
BenchmarkSummary (JSON):
  name: str                                  # Case name (quote_pro_quarterly, etc.)
  category: str                              # Category (arithmetic_and_retrieval, etc.)
  success: bool                              # Does the answer match required patterns and avoid forbidden ones?
  elapsed_seconds: float                     # Wall-clock time for this case
  tool_calls: int                            # Number of tool invocations
  cost_usd: float                            # Cost of this case
  contradictions_flagged: int                # Number of contradictions detected
  termination_reason: str                    # How the agent terminated
  matched_required_patterns: list[str]       # Which required patterns matched
  matched_forbidden_patterns: list[str]      # Which forbidden patterns matched (should be empty for success)
  answer_preview: str                        # First 100 chars of final_answer
  confidence: float                          # Agent's confidence (0.0-1.0)
  failure_classification: dict | null        # If failed, classification info
    - category: str                          # budget_exhaustion, tool_failure, unresolved_contradiction, etc.
    - severity: str                          # low, medium, high, critical
    - reason: str                            # Human-readable explanation
```

## VariantSummary (per-variant artifact)

Summary of a full benchmark run with one prompt variant.

```
VariantSummary (JSON):
  generated_at: str (ISO8601)                # When this run occurred
  prompt_variant: str                        # "A" or "B"
  total_cases: int                           # 10
  passed: int                                # How many cases passed
  failed: int                                # How many cases failed
  success_rate: float                        # passed / total
  avg_cost_usd: float                        # Average cost per case
  avg_latency_seconds: float                 # Average wall-clock time per case
  category_pass_rates: dict                  # Pass rate by category
    - category_name: 
        - passed: int
        - total: int
        - pass_rate: float
        - failure_categories: dict           # Failure classification counts
  failure_analysis: dict
    - total_failures: int
    - failures_by_category: dict
    - failures_by_reason: dict
    - high_severity_failures: list
  cases: list[BenchmarkSummary]              # All 10 case summaries
```

## AblationSummary (A/B comparison artifact)

Cross-variant comparison.

```
AblationSummary (JSON):
  variant_a: str                             # "A"
  variant_b: str                             # "B"
  preferred_variant: str                     # Which variant is better
  success_rate_delta: float                  # variant_b_success_rate - variant_a_success_rate
  success_rate_delta_percent: float          # As a percentage
  cost_delta: float                          # variant_b_cost - variant_a_cost
  cost_delta_percent: float                  # As a percentage
  latency_delta: float                       # variant_b_latency - variant_a_latency
  latency_delta_percent: float               # As a percentage
  category_comparison: dict                  # Per-category performance
  variant_a_advantages: list[str]            # Categories where A excels
  variant_b_advantages: list[str]            # Categories where B excels
  hardest_for_both: list[str]                # Categories where both variants struggle
```

## Artifact Files

For each benchmark run:

```
eval_artifacts/
├── prompt_A/
│   ├── summary.json                        # VariantSummary for Variant A
│   ├── failure_analysis.md                 # Human-readable failure breakdown
│   ├── quote_pro_quarterly/
│   │   ├── result.json                     # Full AgentResult
│   │   ├── case_summary.json               # BenchmarkSummary
│   │   └── report.md                       # Human-readable case report
│   ├── [9 more case directories...]
├── prompt_B/
│   └── [same structure]
├── ablation.json                            # AblationSummary if both variants ran
└── ablation.md                              # Human-readable ablation comparison
```

## Contract Enforcement

1. **AgentResult** must serialize via `to_dict()` with all fields present
2. **AgentRunState** must be immutable after Agent completes; no fields should be added during execution
3. **VariantSummary** must include category_pass_rates and failure_analysis
4. **AblationSummary** must be generated if and only if both variants are present
5. All artifact JSON must be valid JSON with 2-space indentation
6. All artifact markdown must render correctly

## Testing

Every test fixture must conform to this contract. Mocks must produce valid AgentResult and AgentRunState objects.
