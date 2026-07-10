---
name: environment-variable-reconciliation-and-passthrough-fix
description: Workflow command scaffold for environment-variable-reconciliation-and-passthrough-fix in bountystrike-community.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /environment-variable-reconciliation-and-passthrough-fix

Use this workflow when working on **environment-variable-reconciliation-and-passthrough-fix** in `bountystrike-community`.

## Goal

Ensures that environment variable documentation (.env.example) matches the actual variables used in code, and that scripts correctly pass through required environment variables to subprocesses or services.

## Common Files

- `.env.example`
- `scripts/orchestrator.py`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Identify new or changed environment variables in code/scripts.
- Update .env.example to document all required variables, splitting sections if needed.
- Update scripts (e.g., orchestrator.py) to ensure correct passthrough of required variables.
- Test that all services/scripts receive the correct environment variables.

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.