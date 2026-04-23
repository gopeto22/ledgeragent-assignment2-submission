# AI Usage Note

I used an AI coding agent as an implementation partner, not as an unchecked code generator.

## What AI helped write

- initial refactors and module scaffolding
- typed data-model drafts
- prompt scaffolding
- repeated test generation and update passes
- documentation drafts

## What I verified or constrained manually

- architecture boundaries and what to reuse vs rewrite
- the final runtime shape
- the benchmark design and scoring logic
- the deterministic tool behavior and local corpus design
- the failure handling and budget policy
- the final documentation narrative

## How outputs were verified

- unit tests were run locally
- imports and module compilation were checked
- eval harness structure and artifact writing were tested without live model calls
- no benchmark results were fabricated in the absence of credentials

## How I corrected the agent

- rejected broad framework expansion
- kept the tool set intentionally narrow
- required explicit planning and evidence-ledger outputs
- replaced stale coding-agent assumptions instead of trying to patch around them
- preferred deterministic local assets over fragile live integrations for the benchmark path
