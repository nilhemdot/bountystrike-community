---
name: ci-infrastructure-fix-and-credential-least-privilege-hardening
description: Workflow command scaffold for ci-infrastructure-fix-and-credential-least-privilege-hardening in bountystrike-community.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /ci-infrastructure-fix-and-credential-least-privilege-hardening

Use this workflow when working on **ci-infrastructure-fix-and-credential-least-privilege-hardening** in `bountystrike-community`.

## Goal

Fixes CI workflow failures and improves security by scoping credentials to only the required platforms in scripts.

## Common Files

- `.github/workflows/integration-pg.yml`
- `.github/workflows/license-and-imports.yml`
- `scripts/orchestrator.py`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Diagnose CI workflow failures by reviewing logs and error messages.
- Update CI workflow YAML files to fix dependency installation, service images, or configuration issues.
- Update scripts (e.g., orchestrator.py) to scope credentials to only the necessary targets.
- Test CI workflows to confirm fixes and improved security.

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.