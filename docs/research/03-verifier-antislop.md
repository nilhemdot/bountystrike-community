# 03 — Deterministic Verifier + Anti-Slop Discipline (Parts 5-6, lines 1307-2046)

Source: `bountystrike_v5_build_plan.md`

## Verifier Strategy (Why It's the Moat)

Without deterministic verification: "another AI noise generator." With it: programs confirm findings.

**Confirmation Feedback Loop (AnyPoC paper):** AI systems that generate hypotheses *and* generate evidence from same generative process create a confirmation loop. Generator hallucinates; same/similar evaluator confirms. Reports are internally consistent but factually wrong.

**Architectural countermeasures (eliminated by construction):**
1. **Self-exploitation impossible** — Sandbox VM has no loopback to attacker; egress scope-gated; source-IP attribution rejects sandbox-VM-sourced "evidence."
2. **Mock validation impossible** — Validator is *different model*, *different invocation*, *no access* to generator transcript. Receives only PoC + target URL.
3. **Hallucinated code paths caught** — Oracle deterministically executes PoC; HTTP 404 = non-evidence (rejected).
4. **Timing coincidence eliminated** — Welch's t-test on N≥7 measurements; single-measurement timing rejected.

Validator-agent's tool definition file architecturally prohibits any tool exposing exploit-agent state.

## Bug-Class Oracles (8)

### XSS — Playwright DOM Mutation Observer

Headless Chromium in sandbox VM. Four-strategy detection:
1. **DOM mutation observer** — `MutationObserver` on `document.body` watching `childList`/`subtree`/`characterData`
2. **Dialog interception** — `page.on("dialog")` captures `alert()`/`confirm()`/`prompt()`
3. **Sentinel cookie/localStorage write** — payload writes known token; oracle reads back
4. **OAST callback (DOM-stored XSS)** — payload `fetch()`s Interactsh URL; 8s poll

```python
async with async_playwright() as p:
    browser = await p.chromium.launch(args=['--no-sandbox','--disable-dev-shm-usage'])
    page = await browser.new_page()
    page.on("dialog", handle_dialog)
    await page.expose_function("__bsmutationObserver", on_mutation)
    await page.add_init_script("""
        new MutationObserver(...).observe(document.body, 
            {childList:true,subtree:true,characterData:true})
    """)
    await page.goto(target_url, timeout=15000, wait_until='networkidle')
    await asyncio.wait_for(dialog_fired.wait(), timeout=5.0)
    oast_received = await check_oast_callback(oast_token, timeout=8)
```

Verdicts: `validated` (`alert_dialog` | `oast_callback`) | `unreproducible`.

### SSRF — Interactsh OAST Callback

Fresh unique token via `interactsh_client.register_token()` → `http://{token}.oast.fun`. Payload routed through Burp Collaborator (audit). Polls 20s for `http`/`dns` interactions. Validated when callback received; captures `callback_source_ip`, `interaction_type`, `timestamp`.

### SQLi — Welch's T-Test on Time Distributions

Directly addresses AnyPoC "timing coincidence."
- **Sample size:** N=7 minimum (each: 1 baseline + 1 injection)
- **Sleep:** 5 seconds
- **Test:** `scipy.stats.ttest_ind(injection_times, baseline_times, equal_var=False)`
- **Significance:** p < 0.01
- **Effect-size requirement:** `mean_injection - mean_baseline ≥ SLEEP_SECONDS * 0.8`
- **Verdicts:** `validated` (p<0.01 AND delta met) | `inconclusive` | `unreproducible`

### SSTI — Sandboxed Math Eval

Random `(a, b)` pair so `a*b` unique per run. Engine-specific:
- jinja2: `{{(a*b)|int}}`
- twig: `{{(a*b)}}`
- smarty: `{(a*b)}`
- freemarker: `${(a*b)?c}`
- mako: `${(a*b)}`
- pebble: `{{a*b}}`
- velocity: `#set($x=a*b)$x`

Validated iff `str(expected) in response.text`.

### IDOR — Cross-Account Access Matrix

Three-step:
1. Verify Account A *can* access its resource (baseline; status 200/201/202)
2. Try Account B's token against same resource
3. If B succeeds, verify resource is *not* publicly accessible

Validated only when (A=ok) AND (B=ok) AND (unauth=fail).

### Open Redirect

- Controlled domain: `redirect-verify.bountystrike.internal`
- Unique token path: `/verify/{generate_unique_token()}`
- Strategy 1: `follow_redirects=True` → `response.url.startswith(controlled_domain)`
- Strategy 2: No-follow → check `Location` header

### RCE — Multi-Strategy

1. **OOB DNS/HTTP:** `curl http://{oast_token}.oast.fun/{unique_exec_token}` — verify Interactsh callback path
2. **File write:** Write token to `/tmp/{token}`, retrieve via LFI/response
3. **Direct output:** `echo {unique_exec_token}` → match in response

### SSRF→IMDS — AWS Metadata Path

- IMDSv1: `curl http://169.254.169.254/latest/meta-data/instance-id`
- IMDSv2: PUT `/latest/api/token` with `X-aws-ec2-metadata-token-ttl-seconds: 21600`, then GET with `X-aws-ec2-metadata-token` header
- Validation: instance-id regex `i-[0-9a-f]{8,17}` OR IAM creds JSON
- IMDSv2 token-exchange success = severity-escalating factor

## Evidence Schema

```python
@dataclass
class EvidenceArtifact:
    finding_id: str
    oracle_method: str
    timestamp: str
    request_transcript: bytes   # Full HTTP request + headers (redacted auth)
    response_transcript: bytes
    oracle_data: dict           # Oracle-specific: OAST callback, timing data
    content_hash: str           # SHA-256 of (request + response + oracle_data)
    prev_audit_hash: str        # SHA-256 of previous audit log row (chain link)
    reproduction_command: str   # curl command or Python snippet
    environment_requirements: list[str]
    scope_token_jti: str
    sandbox_vm_id: str
    r2_key: str
```

**Independent verification path:** fetch `r2_key` → recompute SHA-256 → compare to `content_hash` → run `reproduction_command`. `prev_audit_hash` forms tamper-evident hash chain.

## AnyPoC Reward-Hacking Risks

| Failure Mode | Description | Countermeasure |
|---|---|---|
| Self-exploitation | Agent runs PoC against own process | No sandbox loopback; scope-gated egress; source-IP validation |
| Mock validation | Validator returns "pass" | Different model/invocation/no shared context |
| Hallucinated code paths | PoC references non-existent endpoints | Oracle executes; 404 rejected |
| Timing coincidence | Single jitter misread as SLEEP | Welch t-test N≥7 |
| Circular evidence | Generator creates own "evidence" | Timestamped + IP-attributed |
| Overfitting to test | Agent optimizes for benchmark metric | Benchmark targets never in training data |

## Verifier Build Roadmap (Phase 1, 4-6 weeks)

- W1-2: Interactsh client + SSRF + open-redirect oracles. Tests: DVWA, WebGoat, Juice Shop
- W3: XSS oracle (Playwright). Tests: PortSwigger Web Security Academy
- W4: SQLi timing oracle + Welch's t-test calibration. Tests: SQLmap test env
- W5: SSTI + IDOR + RCE OOB
- W6: Integration testing, FP/FN calibration on CVE-Bench

## Anti-Slop Gates T0-T3

### Five Non-Negotiable PRQs

- **PRQ-1 Evidence before submission:** `evidence_hash` non-NULL gates `mcp__*__submit_*` via PostToolUse hook
- **PRQ-2 Independent validation:** Oracle confirmation by validator-agent; different model/sandbox/no exploit-agent context
- **PRQ-3 Semantic dedup:** pgvector cosine vs all prior submissions. >0.85 → T2, >0.95 → T3
- **PRQ-4 Human approval mandatory:** No bypass. T3 = two-person, neither = exploit-agent's operator
- **PRQ-5 Quality gate:** 7 structural criteria

### Tier Conditions

```
T0 — Automated Confidence Gate
  When: oracle=validated, evidence_hash present, similarity<0.85, CVSS>=4.0
  Action: auto-advance to reporter-agent queue; no human

T1 — Coordinator Review (LLM)
  When: oracle=validated AND (similarity 0.75-0.85 OR CVSS 7.0-8.9 High)
  Action: coordinator-agent reviews; no human

T2 — Operator Review (single person)
  When: CVSS>=9.0 OR sandbox-exec exploit OR first-of-class for program OR oracle="flaky"
  Action: 1 operator via web dashboard; 15-min timeout

T3 — Two-Person Review
  When: CVSS>=9.5 OR novel chain (3+ hops) OR credential theft / ATO OR
        Immunefi smart-contract critical OR PII>10 records
  Action: 2 distinct operators; neither = exploit-agent's operator;
          30-min SLA; Slack/email escalation
```

### Finding Status ENUM (Postgres)

`hypothesis` → `exploit_attempt` → `exploit_candidate` → `validation_pending` → `validated` → `dedup_check` → `approval_pending_t1`/`t2`/`t3` → `approved` → `submitted` → {`confirmed`, `rejected`, `duplicate`, `wont_fix`, `archived`}

### Slop Crisis Evidence

- **Curl shutdown (Jan 31, 2026):** Stenberg killed H1 program; confirmed-rate <5%, submission volume 8x normal
- **HackerOne 9th Annual Report (Oct 2025):** 210% spike in AI-generated reports; 540% increase in AI prompt-injection reports
- **Bugcrowd (2025-2026):** Automated AI-content detection live; multiple researcher bans

### Report Quality Gate — 7 Criteria

1. Section "Steps to Reproduce" present
2. Section "Proof of Concept" present
3. Section "Impact" present
4. Word count: 150 ≤ wc ≤ 1500
5. **Prohibited phrases:** `leverages`, `delve`, `unveil`, `furthermore`, `moreover`, `it is important to note`, `holistic approach`, `potential vulnerability`, `may be vulnerable`, `could potentially`, `might be able to`, `it should be noted`, `it is worth mentioning`
6. Every technical claim has `[artifact:sha256:...]` citation
7. CVSS vector + score present; severity consistency

## Semantic Dedup (pgvector)

**Two-layer:**
1. **Structural fingerprint (O(1), exact dup):** unique index on `(cwe, platform, program_handle, asset_hash(url), param_name)`
2. **Semantic embedding similarity:**
   - Model: OpenAI `text-embedding-3-large`
   - **Dimensions: 1536**
   - Embedded fields: title + description + affected parameter
   - Operator: pgvector `<=>` (cosine distance)
   - Similarity = `1 - (embedding <=> query)`

**Thresholds:**
- **>0.75** → result set (top-10 displayed)
- **>0.85** → T2 escalation
- **>0.95** → T3 escalation

```sql
SELECT f.id, f.title, 1 - (f.embedding <=> $1) AS similarity
FROM findings f
WHERE f.program_handle = $2
  AND f.status NOT IN ('archived', 'rejected')
  AND 1 - (f.embedding <=> $1) > 0.75
ORDER BY similarity DESC
LIMIT 10;
```

## Kill Switch (3 Layers)

```
LAYER 1 — Redis Kill Flag (~10ms)
  Key:   bs:killswitch:{operator_id}
  Value: "halt_submissions" | "halt_scans" | "halt_all"
  TTL:   24h
  Check: OpenRouter Bridge MCP, before every model call

LAYER 2 — PreToolUse Hook (~50ms, scope-aware)
  halt_submissions → deny mcp__*__submit_*
  halt_scans       → deny network-touching tools
  halt_all         → deny all tool calls; exit code 2

LAYER 3 — Supervisor SIGTERM (~200ms, last resort)
  Hatchet/Temporal sends SIGTERM to all `claude -p` processes
  SessionEnd hook flushes audit log + saves checkpoint
```

**Activation:** CLI `bountystrike kill --reason "..."` OR red "HALT" web-dashboard button (2FA).

## Quality SLOs

| Metric | Target | Alert |
|---|---|---|
| Confirmed rate | >70% | <50% |
| FP rate (N/A submissions) | <10% | >20% |
| Time to validate | <30 min | >120 min |
| Time to submit | <4 hours | >24 hours |
| Duplicate submission rate | <5% | >10% |
| Oracle accuracy | >90% | <80% |
| Report rejection rate | <2% | >5% |
