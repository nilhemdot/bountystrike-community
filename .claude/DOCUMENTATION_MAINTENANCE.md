# DOCUMENTATION_MAINTENANCE.md — BountyStrike v5

## When to Update COMMON_MISTAKES.md

- A production bug or failed hunt traced to a coding pattern
- A new gotcha discovered during oracle field-validation
- Any security misconfiguration that reached staging

## When to Create a Completion Doc (.claude/completions/)

After every non-trivial task. Use the template at `.claude/templates/completion-template.md`.
Load completions only when user explicitly requests historical context.

## When to Archive (docs/archive/)

- Planning docs after the feature ships
- POC / spike summaries after decision is made
- Superseded architecture docs
- Never auto-load archived docs

## When to Update docs/learnings/

- New MCP pattern discovered during implementation
- Oracle behavior or calibration change
- New database migration pattern
- Agent prompt engineering insight

## Decision Tree

```
Did a bug reach production or cause a hunt failure?
  YES -> Add to COMMON_MISTAKES.md immediately

Did you complete a task?
  YES -> Create .claude/completions/<date>-<task>.md

Is a doc superseded by new design?
  YES -> Move to docs/archive/, update cross-references

Did you discover a reusable pattern?
  YES -> Add to relevant docs/learnings/ file
```

## File Size Limits

- CLAUDE.md: 200 lines max — link out instead of duplicating
- Any learnings file > 1,000 lines: split by sub-topic
- COMMON_MISTAKES.md: keep to top 10 items max — archive old ones
