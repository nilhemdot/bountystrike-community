# EV Scoring
**Definition:** An expected-value formula in `domains/program_ranking/services/scoring_service.py` that ranks bounty programs so the operator spends time where payoff is highest.
**Why it matters:** With finite scan budget, picking the right program dominates outcome — this turns program selection into a ranked, data-driven choice.

## How it works
The score combines five factors: `f_payout` (bounty size), `f_saturation` (how picked-over the program is), `f_ops` (operational cost/difficulty), `f_fit` (match to operator profile), `f_cve` (recent CVE/KEV relevance, fed by kev-mcp). Scores are time-series'd in `ev_score_history` with freshness decay. `ev-mcp` exposes `rank_programs` / `get_program_details`; the `program-selector` sub-agent produces a read-only top-N recommendation.

## Related
- [[McpServers]] — ev-mcp + kev-mcp
- [[SubAgents]] — program-selector consumes the ranking
- [[ControlPlane]] — scoring_service implementation

## Sources
- docs/codebase-summary.md — 2026-05-01
- docs/research/02-routing-ev.md — referenced
