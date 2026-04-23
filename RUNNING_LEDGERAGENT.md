# Running LedgerAgent: Complete Guide

## Quick Start (Offline Mode - No Credentials)

✅ **Fastest way to validate the system:**

```bash
cd solution/
python -m spec_agent.evals --offline-mode --output-dir ./eval_artifacts
```

This runs the complete 10-case benchmark with both Prompt A and B in **offline mode**:
- No API credentials needed
- Deterministic results (same every time)
- Full artifacts including success rates, costs, latency
- **~30 seconds total**

Then view results:
```bash
cat eval_artifacts/ablation.md
cat eval_artifacts/prompt_A/summary.json | jq .
```

📖 **For detailed interpretation**: Read [HOW_TO_READ_OFFLINE_ARTIFACTS.md](HOW_TO_READ_OFFLINE_ARTIFACTS.md)

## Running in Different Modes

### Option 1: Offline Mode (Recommended - No Credentials)

```bash
python -m spec_agent.evals --offline-mode
```

**What this proves**:
- ✅ System architecture is correct
- ✅ Planning → execution → reflection → answer loop works
- ✅ All type contracts are satisfied
- ✅ Deterministic tool execution succeeds
- ✅ Budget tracking works
- ✅ Parallel execution batching works

**What it doesn't prove**:
- Real LLM reasoning (uses deterministic mock)
- Live web search (uses snapshot)
- External API integration

### Option 2: Live Mode (Requires Credentials)

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python -m spec_agent.evals  # Or: --prompt-variant A
```

**What this adds**:
- Real Claude LLM responses
- Real tool outputs
- Potentially different (usually better) answers
- Higher confidence in grading

### Option 3: Specific Variant Only

```bash
# Just Prompt A (faster)
python -m spec_agent.evals --offline-mode --prompt-variant A

# Just Prompt B
python -m spec_agent.evals --offline-mode --prompt-variant B
```

## Prerequisites (for Live Mode Only)

1. **Python 3.12** (currently installed: 3.12.7)
2. **Anthropic credentials** (one of):
   - `ANTHROPIC_API_KEY` environment variable set to your API key
   - `ANTHROPIC_AUTH_TOKEN` environment variable set

## Running Without Credentials

If you don't specify `--offline-mode`, the system will attempt to use live credentials:

```bash
cd solution/
python -m spec_agent.evals --verbose
```

Output (if no credentials available):
```
Error: Missing Anthropic credentials. Set ANTHROPIC_API_KEY or 
ANTHROPIC_AUTH_TOKEN before running the agent.
```

This is expected and correct. The system fails fast and clearly rather than using fake credentials.

## What Happens When Running

### Phase 1: Initialization (~2 seconds)

- Load 5 policy documents from `assets/docs/`
- Load KB from `assets/kb.json`
- Load web snapshot from `assets/web_snapshot.json`
- Initialize model client with Anthropic SDK
- Build tool registry

**Example Output (Illustrative)**:
```
Initializing LedgerAgent...
Loaded 5 policy documents (total X bytes)
Loaded KB: X plans, Y overrides
Loaded web snapshot: Z documents
Tool registry ready: [web_search, doc_qa, kb_lookup, calculator, python_sandbox]
```

### Phase 2: Benchmark Execution (~20-30 seconds)

Runs 10 test queries with Prompt Variant A, then repeats with Prompt Variant B.

**Example Output (Illustrative)** for each query:

```
Query 1/10: quote_pro_quarterly
  Query: "What is the quarterly price for Quote Pro?"
  
  [Planner] Analyzing query...
  Plan: web_search → kb_lookup → [optional] calculator
  Estimated cost: $0.015
  
  [Executor] Running step 1/3: web_search
    → Found 2 matching results
  
  [Executor] Running steps 2/3: kb_lookup [parallel with step 1]
    → Found Quote Pro in standard plans
  
  [Reflector] Synthesizing evidence...
    Claim 1: "Quote Pro standard price is $X"
    Claim 2: "Quarterly = annual / 4"
    Confidence: 0.95
    Termination: sufficient_evidence
  
  [Synthesizer] Final Answer:
    The quarterly price for Quote Pro is $Y
  
  Expected: $Y
  Actual: $Y
  Grade: ✓ PASS
  
  Cost: $0.012
  Duration: 2.3s
```

### Phase 3: Result Aggregation (~5 seconds)

After all 10 queries run with Variant A, repeats with Variant B, then generates summary.

## Output Artifacts

After successful completion, creates:

```
eval_artifacts/
├── prompt_A/
│   ├── summary.json              # Overall stats for Variant A
│   ├── quote_pro_quarterly/
│   │   ├── result.json           # Full AgentResult
│   │   ├── case_summary.json     # Metrics for this case
│   │   └── report.md             # Human-readable report
│   ├── compare_enterprise_sla_to_acme/
│   │   └── ... (same structure)
│   ├── phi_support_reconciliation/
│   │   └── ...
│   ├── pilot_response_time/
│   │   └── ...
│   ├── travel_contractor_nyc/
│   │   └── ...
│   ├── enterprise_credit_calc/
│   │   └── ...
│   ├── latency_percentile/
│   │   └── ...
│   ├── competitor_value_gap/
│   │   └── ...
│   ├── budget_stress_refusal/
│   │   └── ...
│   └── receipt_and_taxi/
│       └── ...
└── prompt_B/
    ├── summary.json
    ├── quote_pro_quarterly/
    │   └── ...
    ├── ... (same 10 cases)
    └── receipt_and_taxi/
        └── ...
```

### Summary JSON Structure

**IMPORTANT**: The JSON example below shows the *schema structure*, not actual results. For real metrics, see [HOW_TO_READ_OFFLINE_ARTIFACTS.md](HOW_TO_READ_OFFLINE_ARTIFACTS.md).

**Schema Example** (structure only, values are illustrative):

```json
{
  "variant": "prompt_A",
  "cases_run": 10,
  "cases_passed": 10,
  "cases_failed": 0,
  "pass_rate": 1.0,
  "total_cost": 0.0156,
  "average_cost_per_query": 0.00156,
  "total_duration_seconds": 14.7,
  "average_duration_per_query": 1.47,
  "total_tool_calls": 23,
  "avg_tool_calls_per_query": 2.3,
  "contradiction_detections": 1,
  "budget_refusals": 0,
  "max_iterations_hit": 0,
  "cases": {
    "quote_pro_quarterly": {
      "status": "PASS",
      "grade": 1.0,
      "cost": 0.00149,
      "duration": 1.23,
      "tool_calls": 2
    }
  }
}
```

**To see actual offline results**: Read `eval_artifacts/prompt_A/summary.json` or `eval_artifacts/prompt_B/summary.json`

### Case JSON Structure (result.json)

**Schema Example** (structure only, values are illustrative):

```json
{
  "case_name": "quote_pro_quarterly",
  "query": "What is the quarterly price for Quote Pro?",
  "expected_answer": "3596",
  "actual_answer": "3596",
  "expected_patterns": ["3596"],
  "pattern_matches": ["3596"],
  "success": true,
  "elapsed_seconds": 1.23,
  "tool_calls": 2,
  "cost_usd": 0.00149
}
```

**To see actual case results**: Read `eval_artifacts/prompt_A/[case_name]/result.json` (contains full AgentResult with plan, observations, reflection, answer, ledger)

## Benchmark Queries (10 Cases)

### 1. quote_pro_quarterly
**Type**: Direct lookup + arithmetic
**Query**: "What is the quarterly price for Quote Pro?"
**Expected**: Finds price in KB and divides by 4
**Difficulty**: Easy

### 2. compare_enterprise_sla_to_acme
**Type**: Multi-document comparison
**Query**: "How does our Enterprise SLA compare to Acme's?"
**Expected**: Finds Acme web snapshot, compares to internal doc
**Difficulty**: Medium

### 3. phi_support_reconciliation
**Type**: Public/private knowledge reconciliation
**Query**: "What support tiers do we offer to PHI customers?"
**Expected**: Reconciles web-visible (public) vs policy (private)
**Difficulty**: Medium

### 4. pilot_response_time
**Type**: Contradiction detection
**Query**: "What's our pilot response time commitment?"
**Expected**: Flags contradiction between different policy docs
**Difficulty**: Hard

### 5. travel_contractor_nyc
**Type**: Policy decision
**Query**: "Are NYC-based contractors eligible for our travel budget?"
**Expected**: Extracts policy and applies to specific case
**Difficulty**: Medium

### 6. enterprise_credit_calc
**Type**: Policy + arithmetic
**Query**: "What's the annual credit limit for an Enterprise customer?"
**Expected**: Looks up base credit, applies multiplier from KB
**Difficulty**: Medium

### 7. latency_percentile
**Type**: Python transformation
**Query**: "Calculate 95th percentile latency from [list of numbers]"
**Expected**: Uses python_sandbox to calculate
**Difficulty**: Easy-Medium

### 8. competitor_value_gap
**Type**: Multi-hop reasoning
**Query**: "How much more do we charge than SaaS Competitor X for equivalent features?"
**Expected**: Compare features, pricing, attributes from multiple sources
**Difficulty**: Hard

### 9. budget_stress_refusal
**Type**: Budget enforcement
**Query**: "What's the sum of all possible prices if we multiply everything by all factors?"
**Expected**: Plan requires too many tokens; query refuses with "budget_exceeded"
**Difficulty**: Easy (tests refusal correctly)

### 10. receipt_and_taxi
**Type**: Ambiguous policy
**Query**: "Are receipts required for meals under the taxi reimbursement policy?"
**Expected**: Finds intersection of two overlapping policies; flags ambiguity
**Difficulty**: Hard

## Interpreting Results

### Pass/Fail Grading

Each case has a regex pattern for the expected answer. For example:

| Query | Pattern | Meaning |
|-------|---------|---------|
| quote_pro_quarterly | `.*\$99.*[Qq]uarter` | Must mention $99 and "quarter" |
| budget_stress_refusal | `budget.*exceeded\|insufficient.*budget` | Must mention budget exceeded |
| pilot_response_time | `contradiction\|conflict` | Must flag contradiction |

### Confidence Levels

The final answer includes a confidence score 0.0-1.0:

- **0.9-1.0**: High confidence, strong evidence, no contradictions
- **0.7-0.9**: Good confidence, some contradictions resolved
- **0.5-0.7**: Moderate confidence, significant uncertainty
- **<0.5**: Low confidence, major conflicts or insufficient evidence

### Cost Breakdown (Illustrative)

**IMPORTANT**: The figures below are illustrative schema examples. For actual offline benchmark costs, see [HOW_TO_READ_OFFLINE_ARTIFACTS.md](HOW_TO_READ_OFFLINE_ARTIFACTS.md) and the `eval_artifacts/` directory.

```
Total cost: $0.145
Per query: $0.0145 average

Breakdown:
- Planning calls: 40% ($0.058) – most expensive
- Reflection calls: 35% ($0.051) – reflection uses full conversation
- Tool execution: 25% ($0.036) – no token cost, just latency

Large spikes on multi-hop queries (e.g., competitor_value_gap)
```

## Prompt Variant Comparison (Illustrative)

**IMPORTANT**: The table below is illustrative schema. For actual offline benchmark comparison, see `eval_artifacts/ablation.md` or `eval_artifacts/ablation.json`.

After both Prompt A and B complete, the harness prints:

```
╔════════════════════════════════════════════╗
║     PROMPT VARIANT COMPARISON SUMMARY      ║
╚════════════════════════════════════════════╝

Metric                    │ Prompt A  │ Prompt B  │ Delta
─────────────────────────────────────────────────────────
Pass Rate                 │   100%    │   100%    │   —
Average Cost              │ $0.0156   │ $0.0273   │ +75%
Average Duration          │  1.47s    │  2.78s    │ +89%
Contradictions Detected   │   1       │   3       │ +200%
Budget Refusals          │   0       │   0       │  —
Max Iterations Hit       │   0       │   0       │  —

✓ Both variants succeed 100% offline
✓ Variant B detects more contradictions
✗ Variant B is more expensive and slower
```

## Troubleshooting

### Error: "Missing Anthropic credentials"

**Solution**: Set `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN`

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
python -m spec_agent.evals --verbose
```

### Error: "Failed to connect to Anthropic API"

**Solution**: Check internet connection and API key validity

```bash
curl -H "Authorization: Bearer $ANTHROPIC_API_KEY" \
  https://api.anthropic.com/v1/models
```

### Error: "Rate limited by Anthropic"

**Solution**: Wait a few seconds and retry. The system has built-in retries.

```bash
python -m spec_agent.evals --verbose  # Will retry automatically
```

### Error: "Tool timeout after 5 seconds"

**Solution**: This is expected for budget_stress_refusal (intentional failure case). For other cases, check network latency.

## Manual Query Testing

To test a single query manually:

```bash
python -c "
from spec_agent.agent import Agent
from spec_agent.models import AgentConfig

query = 'What is the quarterly price for Quote Pro?'
agent = Agent.create(config=AgentConfig(max_cycles=3), offline_mode=True)
result = agent.run(query)
print('Answer:', result.final_answer)
print('Confidence:', result.confidence)
print('Run state:', result.run_state.termination_reason)
print('Elapsed seconds:', result.elapsed_seconds)
"
```

## Performance Expectations (Illustrative)

**IMPORTANT**: These are rough expectations for live mode. For actual offline benchmark performance, see the real metrics at `eval_artifacts/prompt_A/summary.json` and `eval_artifacts/prompt_B/summary.json`.

- **Total time for 10 cases (Prompt A + B)** (live): 25-35 seconds
- **Cost per full benchmark** (live): $0.25-0.35 (depending on provider rates)
- **Cost per case** (live): $0.012-0.025
- **Tool calls per case**: 2-4 on average
- **Max iterations needed**: Usually 2, rarely 3

## Prompt Ablation Interpretation

Both variants are correct implementations—they just make different trade-offs:

**Prompt A (Baseline)**:
- Simpler, faster planning
- Good for straightforward queries
- Less careful about contradictions
- Cheaper

**Prompt B (Evidence-Aware)**:
- More explicit reasoning about evidence quality
- Better at contradictions and ambiguity
- More conversational with the model
- More expensive but more reliable

For Assignment 2, the key insight is: **explicit planning and evidence tracking improve answer quality at the cost of latency and token usage**.
