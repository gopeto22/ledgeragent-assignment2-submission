# Architecture Decisions

## Chosen Stack

- Python 3.12
- Anthropic SDK behind a minimal model client boundary
- Standard-library concurrency via `ThreadPoolExecutor`
- Standard-library dataclasses for typed runtime state
- Local Markdown, JSON, and web-snapshot assets for reproducible evaluation

## System Diagram

```text
query
  |
  v
planner (Prompt A or B)
  |
  v
execution plan -----> budget manager
  |
  v
executor -----> tools (web_search, doc_qa, kb_lookup, calculator, python_sandbox)
  |
  v
observations -----> reflection -----> claims / contradictions
  |                                      |
  |                                      v
  +-------------------------------> final answer
                                         |
                                         v
                                  evidence ledger
```

## Key Decisions

### 1. Keep the package path, change the product

I kept the existing Python package path for speed, but changed the runtime, scripts, docs, and product identity to **LedgerAgent**. This preserved useful infrastructure while avoiding a repo-wide rename tax.

### 2. Use deterministic local tools for most reasoning

The benchmark is meant to measure agent judgment, not web flakiness. So the internal docs, KB, and public web sources are local checked-in assets. `web_search` is still a real tool, but it searches a reproducible snapshot.

### 3. Separate planner, executor, and budget logic

The runtime is split into:

- planner: LLM planning, reflection, and synthesis
- executor: dependency-aware parallel tool execution
- budget: token/cost estimation and hard cap enforcement

This makes the failure modes visible and keeps the orchestrator thin.

### 4. Make the evidence ledger first-class

The agent does not only return a final answer. It returns a structured run record with:

- plan
- tool calls
- observations
- claims
- contradictions
- budget state
- termination reason

That is the core product shape, not debug garnish.

## Rejected Alternatives

### Giant multi-agent system

Rejected because the assignment rewards runtime judgment and evidence quality more than feature breadth. A single orchestrated analyst with explicit planning is easier to inspect and benchmark.

### Live web search as the default backend

Rejected for the benchmark path because it makes evaluation brittle and non-reproducible. A snapshot backend is the better default for a take-home.

### Retrieval framework / vector DB

Rejected because the corpus is small enough to search deterministically without adding infrastructure or a new failure surface.

## Concurrency Model

Independent plan steps sharing a `parallel_group` are executed concurrently via `ThreadPoolExecutor`. This is intentionally small-scale but real parallelism, not just a label in the plan.

Example: A query that needs doc_qa, kb_lookup, and web_search in parallel will launch all three concurrently and wait for all to complete before reflection.

Each tool has a timeout (default 5 seconds); if a tool times out, the executor continues with other steps.

## Scaling Analysis: 100 Concurrent Users

At scale, the system would face these bottlenecks:

### 1. LLM Provider Latency (primary bottleneck)

- Planner call: ~1-2 seconds
- Reflection call: ~0.5-1 second
- Answer synthesis call: ~0.5-1 second
- **Total per request: ~2-4 seconds minimum**

With 100 concurrent users, you hit provider rate limits quickly. Mitigations:
- Request queuing with backpressure
- Circuit breaking (fallback plans if planner fails)
- Prompt caching if the provider supports it

### 2. Tool Corpus Loading (secondary bottleneck)

Each Agent instance loads:
- 5 policy documents (~50KB total)
- KB JSON (~2KB)
- Web snapshot JSON (~2KB)

With 100 short-lived processes, repeated parsing becomes noticeable. Mitigations:
- Singleton shared ToolRegistry loaded once at startup
- Pre-parse corpus at boot time
- Use mmap or memory-mapped files for large assets

### 3. Local Disk Artifact Writes

Each run writes:
- Result JSON (~5KB)
- Run state JSON (~2KB)
- Per-case summary (~1KB)

With 100 concurrent writes, contention on directory creation and write ordering. Mitigations:
- Use UUIDs for artifact paths to avoid conflicts
- Batch writes with a ledger service
- Write to object storage instead of local disk

### 4. Unbounded Parallelism in Tool Execution

If a plan has 10+ steps in the same parallel_group, all 10 tools launch concurrently. With 100 users, this could mean 1000 concurrent tool calls. Mitigations:
- Add max_parallel_workers config (default 4)
- Queue tool calls and respect rate limits
- Implement circuit breaking per tool

### 5. Model Token Overhead

Each planner call sends:
- Full query text
- Tool manifest (descriptions of all 5 tools)
- System prompt (~2KB)

With many concurrent calls, token usage spikes. Mitigations:
- Compile manifests once, not per request
- Use prompt compression or variable-length prompts
- Implement conversation pruning for long-running requests

## What I Would Build for 100 Users

Architecture changes needed:

```text
┌─────────────────────────────────────┐
│      HTTP Request Handler           │
│  (FastAPI / Flask + asyncio)        │
└──────────────┬──────────────────────┘
               │
               v
┌─────────────────────────────────────┐
│      Request Queue (Redis)          │
│  [prioritization, backpressure]     │
└──────────────┬──────────────────────┘
               │
               v
┌─────────────────────────────────────┐
│   Worker Pool (4-8 workers)         │
│  [each runs Agent.run()]            │
└──────────────┬──────────────────────┘
               │
        ┌──────┴──────┬─────────┐
        v             v         v
   ┌─────────┐  ┌──────────┐  ┌──────────┐
   │ Planner │  │ Executor │  │  Budget  │
   │(cached) │  │ (pool)   │  │(tracker) │
   └─────────┘  └──────────┘  └──────────┘
        │             │            │
        └─────────────┼────────────┘
                      v
              ┌──────────────────┐
              │ Tool Registry    │
              │ (singleton)      │
              │ + asset cache    │
              └──────────────────┘
                      │
        ┌─────────────┼──────────────┐
        v             v              v
    ┌────────┐  ┌────────┐  ┌────────────┐
    │ Docs   │  │   KB   │  │ Web Snap   │
    │(mmapped)  │(cached)│  │(mmap)      │
    └────────┘  └────────┘  └────────────┘
        │             │              │
        └─────────────┼──────────────┘
                      v
              ┌──────────────────┐
              │ Ledger Store     │
              │ (S3 / Cloud)     │
              └──────────────────┘
```

### Specific Changes

1. **Async runtime**: Switch from sync Agent.run() to async/await with proper concurrency control
2. **Shared ToolRegistry**: Load once at startup, not per request
3. **LLM rate limiting**: Implement queue with max_concurrent requests to provider
4. **Tool rate limits**: Per-tool concurrency caps and timeout handling
5. **Budget coordination**: Global budget allocator vs. per-request allocator
6. **Ledger store**: S3 or cloud storage for artifacts
7. **Metrics and monitoring**: Prometheus metrics for latency, costs, tool usage
8. **Circuit breaking**: Fallback plans if planner/executor fails

### Cost Model at 100 Users

Assuming:
- Average query takes 3 seconds (planning + execution + reflection)
- 100 concurrent users → ~33 queries/second (not all active simultaneously)
- Average cost per query: $0.01 (planner + reflection + tools)

**Cost per hour**: 33 queries/sec × 3600 sec = ~119K queries → ~$1.2K/hour

At this scale, cost becomes a real concern. Optimizations:
- Prompt caching to reduce duplicate work
- Lighter reflection for high-confidence cases
- Batch planning for similar queries

But this is well beyond submission scope.

## Current Implementation Status

- ✓ Single-request model (designed for batch/interactive use)
- ✓ Synchronous runtime (simple to reason about)
- ✓ Per-request Agent instance
- ✓ Basic tool timeouts and retries
- ✓ Per-request budget enforcement
- ✓ Local artifact writes

This is sufficient for the Assignment 2 evaluation with 10 benchmark queries, each running one at a time.

