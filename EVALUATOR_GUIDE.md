# Evaluator Guide

This guide explains how I would review the submission. For the shortest path, start with `README.md`.

## Recommended order

1. `FINAL_SUBMISSION_SUMMARY.md`  
   Short overview of the system and results.

2. `HOW_TO_READ_OFFLINE_ARTIFACTS.md`  
   Explains the benchmark outputs and how to verify them.

3. `solution/REPORT.md`  
   Written report covering what I built, what broke, and what I learned.

4. `solution/ARCHITECTURE.md`  
   Architecture, trade-offs, and 100-user scaling notes.

5. Core code:
   - `solution/spec_agent/agent.py`
   - `solution/spec_agent/planner.py`
   - `solution/spec_agent/executor.py`
   - `solution/spec_agent/evals.py`
   - `solution/spec_agent/models.py`

## Quick verification

```bash
cd solution

python -c "from spec_agent.agent import Agent; print('Agent imports')"
python -m pytest tests/ -q
python -m spec_agent.evals --offline-mode --prompt-variant A
