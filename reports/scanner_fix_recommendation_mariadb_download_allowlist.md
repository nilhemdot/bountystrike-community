# Scanner-Fix Recommendation — mariadb `/download/` allowlist xss-candidate FP

**Severity:** scanner false-positive class (5× confirmed; full meta-class confirmed at N=3 per memory; first filed at N=4)
**Filed by:** exploit-agent run on finding `24cd67e3-0b23-4bdd-afbe-49e564a9f430` (2026-05-13); appended on finding `afd6b2b8-2167-4297-8e27-759eb5e77c3b` (2026-05-13)
**Related memory:** `project_mariadb_download_allowlist_fp.md`

## Pattern

Scanner emits `xss-candidate` for params on `https://mariadb.org/download` matching the param-name heuristic (`tab`, `prod`, `rel`, `old`). These params drive a server-side allowlist (product/release/OS-tab selectors) and never reach the response body unescaped.

## Confirmed occurrences

| Finding ID                              | Date       | Reflected | Resolution           |
|-----------------------------------------|------------|-----------|----------------------|
| 78baef24-a508-47e4-9cc0-1040a0837a43    | 2026-05-13 | 0/4       | approval_pending_t2  |
| 24cd67e3-0b23-4bdd-afbe-49e564a9f430    | 2026-05-13 | 0/4       | approval_pending_t2  |
| afd6b2b8-2167-4297-8e27-759eb5e77c3b    | 2026-05-13 | 0/4       | approval_pending_t2  |
| (2 earlier same-meta-class hits — see `project_wp_rest_route_fp_meta.md`, `project_wp_ver_xss_fp_class.md`) | | | |

This is the 5th hit on the meta-class (param-name xss-candidate without reflection check). Memory's stated trigger for filing this ticket: 4th occurrence — already met. The 5th occurrence proves the orchestrator pre-empt rule from `project_mariadb_download_allowlist_fp` is not yet enforced.

## Proposed fix (cheapest first)

1. **Upstream pre-filter (preferred)**: in the scanner emitting `xss-candidate`, add a single reflection probe (sentinel injection → grep response body) before persisting the row. If `reflected_count == 0`, downgrade `xss-candidate` → `xss-candidate-unreflected` (or drop entirely).
2. **Param-name allowlist exception**: hard-code `/download/{tab,prod,rel,old}` as known-allowlist params for `mariadb.org`. Lower priority — narrow fix, won't catch the next program with the same pattern.
3. **No change**: every future hit costs one exploit-agent invocation + one operator T2 review. Cost grows linearly with mariadb scan frequency.

## Recommendation

Implement #1 — generic reflection probe in the scanner. Same root cause as `wp-ver-xss-fp-class` and `wp-rest-route-fp-meta`, so the fix removes three FP classes at once.

## Verification plan

- Re-run mariadb recon → scanner pass against `mariadb.org`.
- Expect `xss-candidate` count on `/download/` allowlist params to drop to 0.
- Add a regression test fixture: probe URL above + assertion `count == 0`.
