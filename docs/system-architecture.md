# System Architecture — BountyStrike v5

Visual reference for how BountyStrike v5 is wired together. Six Mermaid diagrams covering: component graph, end-to-end data flow, database ER, scope-JWT trust boundary, kill-switch layers, and the finding-status state machine.

Pair this with [`codebase-summary.md`](codebase-summary.md) for the file-level inventory and [`project-overview-pdr.md`](project-overview-pdr.md) for the design rationale.

**Generated:** 2026-05-01 against git HEAD `e9b4b77`. Reflects the 15 MCPs, 9 sub-agents, 4 wired PreToolUse hooks, 13 Postgres tables (12 from `01_schema.sql` + `02_dedup_fingerprints.sql`; `04_approval_queue.sql` adds `approval_queue` and `05_findings_raw_finding.sql` adds the `raw_finding` JSONB column), and the 8 oracles in `oracle-mcp` that exist on disk today. Phase 2 W7-8 sprint closed: 5 new field-validation suites (SSRF→IMDS, IDOR, RCE, SSTI, Open Redirect) pass at TPR=1.0/FPR=0.0, and T3 approval plumbing is wired in `scripts/orchestrator.py`.

## 1. Component Graph

The control plane orchestrates a fleet of Claude sub-agents. Sub-agents reach into MCP servers (stdio FastMCP) for any side-effecting work. Postgres is the single authoritative store; Redis is a kill-switch flag and approval cache; Cloudflare R2 (or local FS) holds blob evidence; OAST callbacks land at Interactsh.

```mermaid
graph TB
    Operator([Operator])
    JWT[Scope JWT<br/>RS256 4096-bit]
    Operator -->|issue via gen_scope_jwt.py| JWT

    subgraph CP["control-plane (FastAPI + DDD)"]
        CPCore[core/security<br/>validation + path guards]
        CPDom[domains/<br/>recon · approval_gate · evidence_management<br/>program_ranking · safety · scope_management]
        CPInf[infrastructure/database.py<br/>SQLAlchemy 2.0 async]
    end

    subgraph Agents[".claude/agents (9 sub-agent specs)"]
        Recon[recon-agent]
        Cloud[cloud-recon-agent]
        Scanner[scanner-agent]
        Hunter[ai-vuln-hunter]
        Exploit[exploit-agent]
        Validator[validator-agent]
        Reporter[reporter-agent]
        ScopeGuard[scope-guard]
        Selector[program-selector]
    end

    subgraph MCP["mcp/ (15 servers)"]
        OracleMCP[oracle-mcp<br/>8 verifiers + Playwright + scipy<br/>7 field-validated TPR=1.0/FPR=0.0]
        EvidenceMCP[evidence-mcp<br/>aiosqlite + R2/local blob]
        DedupMCP[dedup-mcp<br/>asyncpg + pgvector + OpenAI]
        StateMCP[state-mcp<br/>asyncpg]
        EVMCP[ev-mcp<br/>asyncpg + control-plane dep]
        KEVMCP[kev-mcp<br/>CISA KEV + EPSS + kev_match_program]
        ScopeMCP[scope-mcp<br/>TypeScript - JWT validate]
        H1[h1-mcp]
        BC[bugcrowd-mcp]
        IN[intigriti-mcp<br/>placeholder]
        YWH[yeswehack-mcp]
        IM[immunefi-mcp]
        Politeness[politeness-mcp<br/>token bucket]
        Sandbox[sandbox-mcp<br/>local + Docker scaffold]
        Normalize[normalize-mcp<br/>CVSS + CWE]
    end

    subgraph Hooks[".claude/hooks (4 PreToolUse + 2 task)"]
        Killswitch[pretool_killswitch.py]
        Antislop[pretool_antislop.py]
        Route[pretool_venice_route.py]
        Approval[pretool_approval_gate.py]
    end

    subgraph Infra["infra/ (Docker Compose)"]
        PG[(Postgres 17<br/>pgvector + pg_trgm)]
        RD[(Redis 7<br/>kill switch + cache)]
        Hatchet[Hatchet<br/>workflow engine]
        Langfuse[Langfuse<br/>LLM traces]
        R2[(Cloudflare R2<br/>or local FS)]
    end

    Interact[Interactsh<br/>OAST callbacks]
    Anthropic[Anthropic API]
    OR[OpenRouter / Venice<br/>cost-tier routing]

    JWT --> CP
    CP --> Agents
    Agents --> Hooks
    Hooks --> MCP
    MCP --> PG
    MCP --> RD
    EvidenceMCP --> R2
    OracleMCP --> Interact
    Agents --> Anthropic
    Route --> OR
    CP --> Hatchet
    CP --> Langfuse
    CP --> PG
```

## 2. End-to-End Data Flow

A single scan of one bounty program. `scripts/orchestrator.py` is the entry point; everything else fans out from there.

```mermaid
sequenceDiagram
    autonumber
    participant Op as Operator
    participant Orch as scripts/orchestrator.py
    participant DB as Postgres
    participant Recon as recon-agent
    participant Hunter as ai-vuln-hunter
    participant Oracle as oracle-mcp
    participant Dedup as dedup-mcp
    participant Evidence as evidence-mcp
    participant State as state-mcp
    participant Gate as approval_gate (T1/T2/T3)
    participant Submit as platform MCP<br/>(h1/bugcrowd/...)

    Op->>Orch: PROGRAM_HANDLE + SCOPE_JWT + DATABASE_URL
    Orch->>DB: INSERT scan_jobs (status=queued)
    Orch->>Recon: subprocess (scope_jwt env)
    Recon->>Recon: subfinder → httpx live → katana endpoints
    Recon->>DB: INSERT findings (status=hypothesis)
    Recon-->>Orch: recon_complete

    Note over Orch: scanner phase (skippable via SKIP_SCANNER)<br/>nuclei / ffuf / sqlmap / arjun / kiterunner

    loop per hypothesis (MAX_EXPLOITS parallel)
        Orch->>Hunter: spawn exploit-agent
        Hunter->>Oracle: PoC payload generation
        alt T2 needed (CVSS>7, limited PII)
            Hunter-->>Orch: status=approval_pending_t2
            Orch->>Gate: enqueue (approval_queue table, exp backoff 5s→60s)
            Gate-->>Op: scripts/approve.py — list / show / approve / reject
            Op->>Gate: approve(actor, reason)
            Gate-->>Orch: APPROVAL_TOKEN
            Orch->>Hunter: relaunch with APPROVAL_TOKEN
        end
        Hunter->>DB: status=exploit_pending_validation
    end

    loop per exploit (MAX_VALIDATORS parallel)
        Orch->>Hunter: spawn validator-agent
        Hunter->>Oracle: verify_xss / verify_ssrf / verify_sqli / verify_ssti /<br/>verify_idor / verify_rce / verify_open_redirect / verify_ssrf_imds
        Oracle-->>Hunter: oracle_data (deterministic verdict)
        Hunter->>Dedup: check_duplicate (fingerprint)
        Dedup-->>Hunter: is_dup, tier
        alt confirmed + not dup
            Hunter->>Evidence: put_artifact (request, response, oracle_data, repro)
            Evidence->>DB: INSERT evidence_artifacts
            Evidence->>DB: append audit_log (hash chain)
            Hunter->>State: update_finding_status(validated → dedup_check → approval_pending_t*)
            State->>DB: UPDATE findings.status with optimistic lock
            alt T3 needed (CVSS>9, novel chain, PII>10, sandbox exec)
                Orch->>Gate: enqueue T3 (queue.py:wait_for_approval)
                Note over Gate: T3 = 2 distinct actors, 30 min SLA
                Op->>Gate: approve #1 (returns None — first approver only)
                Op->>Gate: approve #2 (returns APPROVAL_TOKEN — distinct actor)
                Gate-->>Orch: APPROVAL_TOKEN
            end
            Gate->>Gate: T1 LLM review / T2 single human / T3 two-person
            Gate->>Submit: submit_report (only if approved)
            Submit->>DB: INSERT report_submissions
        end
    end

    Orch->>DB: UPDATE scan_jobs (status=complete, completed_at)
    Orch-->>Op: summary (hypotheses, validated, submitted)
```

## 3. Database ER

The 12 Postgres tables (11 in `infra/sql/01_schema.sql` + `dedup_fingerprints` from `02_dedup_fingerprints.sql`). Foreign keys shown; indexes/ENUMs noted in [`codebase-summary.md`](codebase-summary.md) §Tables.

```mermaid
erDiagram
    programs ||--o{ scopes : "program_handle"
    programs ||--o{ scope_changes : "program_handle"
    programs ||--o{ ev_score_history : "program_handle"
    programs ||--o{ scan_jobs : "program_handle"
    programs ||--o{ findings : "program_handle"

    scan_jobs ||--o{ findings : "job_id"
    findings ||--o{ evidence_artifacts : "finding_id"
    findings ||--o{ report_submissions : "finding_id"
    findings ||--o{ dedup_fingerprints : "finding_id (logical)"

    agent_sessions ||--o{ model_costs : "agent_session_id"

    audit_log ||--|| audit_log : "prev_hash chain"

    programs {
        text handle PK
        text platform
        numeric payout_min
        numeric payout_max
        numeric dup_rate
        timestamptz last_seen_at
        jsonb raw
    }

    scopes {
        bigserial id PK
        text program_handle FK
        text asset_type
        text identifier "trgm GIN"
        bool in_scope
        text[] tags
    }

    scope_changes {
        bigserial id PK
        text event_type
        text program_handle
        jsonb old_value
        jsonb new_value
        timestamptz detected_at
    }

    ev_score_history {
        bigserial id PK
        text program_handle
        numeric ev_score
        numeric f_payout
        numeric f_saturation
        numeric f_ops
        numeric f_fit
        numeric f_cve
    }

    scan_jobs {
        uuid id PK
        text program_handle
        text scope_jwt_jti
        text status
        numeric ev_score
        timestamptz completed_at
    }

    findings {
        uuid id PK
        uuid job_id FK
        text program_handle
        text cwe
        finding_status status
        text deduplication_key
        vector_1536 embedding "HNSW"
    }

    evidence_artifacts {
        uuid id PK
        uuid finding_id FK
        text content_hash
        text prev_audit_hash
        bytea request_transcript
        bytea response_transcript
        text r2_key
        text scope_token_jti
    }

    audit_log {
        bigserial id PK
        text actor
        text action
        bytea prev_hash
        bytea row_hash
        jsonb payload
    }

    agent_sessions {
        uuid id PK
        text agent_type
        text model
        bigint tokens_in
        bigint tokens_out
        numeric cost_usd
    }

    model_costs {
        bigserial id PK
        uuid agent_session_id FK
        text model
        int tokens_in
        int tokens_out
        numeric cost_usd
    }

    report_submissions {
        uuid id PK
        uuid finding_id FK
        text platform
        text submission_id
        text status
        numeric payout_usd
    }

    dedup_fingerprints {
        text fingerprint_hex PK
        text platform
        text program_handle
        text vuln_type
        text finding_id
    }
```

## 4. Scope-JWT Trust Boundary

The first non-negotiable: scope is enforced at the network layer, not the prompt. The control plane signs an RS256 4096-bit JWT; every MCP that touches a target validates it against the public key; the Firecracker VM (Phase 2+) runs an iptables egress allowlist derived from the JWT claims.

```mermaid
flowchart LR
    subgraph Trusted["Trusted plane (control-plane host)"]
        IssueJWT[gen_scope_jwt.py<br/>scripts/]
        Issuer[jwt_issuer.py<br/>RS256 sign with private key<br/>168h max expiry, JTI revocation]
        PrivKey[(keys/scope_jwt_private.pem<br/>4096-bit RSA — gitignored)]
        IssueJWT --> Issuer
        Issuer --> PrivKey
    end

    JWT[/Scope JWT<br/>claims: program_handle, platform,<br/>wildcards, exact_hosts, ips,<br/>exclusions.hostnames,<br/>exclusions.paths,<br/>rate_limits.default_rps,<br/>rate_limits.relaxed_hosts,<br/>jti, iss, sub, exp/]

    Issuer --> JWT

    subgraph SemiTrusted["Agent plane (sub-agents + MCPs)"]
        ScopeMCP[scope-mcp TS<br/>verify RS256 signature<br/>extract claims]
        PubKey[(keys/scope_jwt_public.pem)]
        ScopeMCP --> PubKey
        Recon[recon-agent]
        Validator[validator-agent]
        Oracle[oracle-mcp]
        ScopeGuard[scope-guard sub-agent<br/>synchronous adjudicator<br/>for ambiguous cases]
        Recon --> ScopeMCP
        Validator --> ScopeMCP
        Oracle --> ScopeMCP
        ScopeMCP -.->|ambiguous| ScopeGuard
    end

    JWT --> ScopeMCP

    subgraph Untrusted["Untrusted plane (target / sandbox)"]
        FW[iptables egress allowlist<br/>derived from JWT claims]
        VM[Firecracker microVM<br/>scope-bound netns + TAP]
        Target[Target host]
        FW --> VM
        VM --> Target
    end

    ScopeMCP -->|emit firewall rules| FW
    Validator -.->|exec inside| VM

    classDef trust fill:#d4edda,stroke:#28a745
    classDef semi fill:#fff3cd,stroke:#ffc107
    classDef untrust fill:#f8d7da,stroke:#dc3545
    class Trusted trust
    class SemiTrusted semi
    class Untrusted untrust
```

## 5. Kill-Switch Layers

Three independent enforcement paths so any one of them being down is not catastrophic.

```mermaid
flowchart TB
    Operator([Operator])

    subgraph L1["Layer 1 — Redis flag"]
        Redis[(Redis<br/>key: bountystrike:killswitch:global<br/>TTL 86400s<br/>backend: redis or memory)]
    end

    subgraph L2["Layer 2 — PreToolUse hook"]
        Hook[.claude/hooks/pretool_killswitch.py<br/>matcher: * — wraps every tool call<br/>fail-open if Redis unreachable]
    end

    subgraph L3["Layer 3 — Process supervisor"]
        Sup[systemd / docker stop / pkill<br/>SIGTERM → SIGKILL chain]
    end

    Tool[Any Claude tool call]
    Outbound[Outbound action<br/>HTTP, subprocess, write]

    Operator -->|redis-cli SET| Redis
    Tool --> Hook
    Hook -->|read flag| Redis
    Hook -->|deny if true| Tool
    Hook -.->|allow if false<br/>or Redis down| Outbound

    Operator -->|emergency| Sup
    Sup -->|SIGTERM| Tool
    Sup -->|SIGKILL after grace| Tool

    classDef crit fill:#f8d7da,stroke:#dc3545
    class Sup crit
```

**Properties:**
- **L1 instant** (~10 ms): operator runs `redis-cli -a $REDIS_PASSWORD SET bountystrike:killswitch:global 1 EX 86400`.
- **L2 enforces** on every tool invocation via the wired PreToolUse hook (`.claude/settings.json`).
- **L3 backstop**: if the agent runtime ignores the hook (bug or compromise), the supervisor terminates the process tree.
- **Fail-open at L2**: if Redis is unreachable, the hook allows the call (so a Redis outage doesn't halt every scan), and L3 remains as the backstop.

## 6. Finding Status State Machine

The `finding_status` ENUM has 16 states from `infra/sql/01_schema.sql`. State transitions are gated by approval-tier hooks and oracle verdicts.

```mermaid
stateDiagram-v2
    [*] --> hypothesis: recon-agent emits

    hypothesis --> exploit_attempt: exploit-agent picks up
    exploit_attempt --> exploit_candidate: exploit succeeds locally
    exploit_attempt --> hypothesis: retry with new payload

    exploit_candidate --> validation_pending: handed to validator-agent
    validation_pending --> validated: oracle confirms (TPR=1.0 path)
    validation_pending --> rejected: oracle rejects (FPR=0.0 path)

    validated --> dedup_check: dedup-mcp inspect
    dedup_check --> duplicate: fingerprint or semantic match
    dedup_check --> approval_pending_t1: novel + low impact
    dedup_check --> approval_pending_t2: novel + medium impact
    dedup_check --> approval_pending_t3: novel + high impact / new class

    approval_pending_t1 --> approved: T1 LLM review pass
    approval_pending_t2 --> approved: T2 single human approves
    approval_pending_t3 --> approved: T3 two-person sign-off

    approval_pending_t1 --> rejected: review fails
    approval_pending_t2 --> rejected: human rejects
    approval_pending_t3 --> rejected: review fails

    approved --> submitted: platform MCP submit_report
    submitted --> confirmed: triager accepts (target ≥70%)
    submitted --> rejected: triager rejects
    submitted --> wont_fix: program decision

    duplicate --> [*]
    confirmed --> [*]
    rejected --> [*]
    wont_fix --> [*]
    archived --> [*]

    note right of validated
        Phase 1.1c (XSS) + 1.1d (SSRF) + Phase 2 W7-8
        (SSRF→IMDS, IDOR, RCE, SSTI, Open Redirect):
        TPR=1.0, FPR=0.0 across 7 of 8 oracles.
        SQLi field-validation pending W9-10.
    end note

    note right of dedup_check
        Phase 2 §10.4 dedup-mcp:
        cross-session recall=1.0
        (commit 3d9e915)
    end note
```

## Component-to-File Cross-Reference

For each component above, the canonical source location:

| Component | File |
|---|---|
| Orchestrator entry | [`scripts/orchestrator.py`](../scripts/orchestrator.py) |
| Scope JWT issuance | [`control-plane/src/control_plane/domains/scope_management/services/jwt_issuer.py`](../control-plane/src/control_plane/domains/scope_management/services/jwt_issuer.py) |
| Scope JWT validation | [`mcp/scope-mcp/src/jwt.ts`](../mcp/scope-mcp/src/jwt.ts), [`mcp/scope-mcp/src/scope.ts`](../mcp/scope-mcp/src/scope.ts) |
| Approval gate logic | [`control-plane/src/control_plane/domains/approval_gate/services.py`](../control-plane/src/control_plane/domains/approval_gate/services.py) |
| Approval queue mechanics | [`control-plane/src/control_plane/domains/approval_gate/queue.py`](../control-plane/src/control_plane/domains/approval_gate/queue.py) — `enqueue / approve / reject / wait_for_approval` (exp backoff 5s→60s) |
| Operator approval CLI | [`scripts/approve.py`](../scripts/approve.py) — `list / show / approve / reject` subcommands |
| Approval queue migration | [`infra/sql/04_approval_queue.sql`](../infra/sql/04_approval_queue.sql) |
| `findings.raw_finding` migration | [`infra/sql/05_findings_raw_finding.sql`](../infra/sql/05_findings_raw_finding.sql) |
| EV scoring | [`control-plane/src/control_plane/domains/program_ranking/services/scoring_service.py`](../control-plane/src/control_plane/domains/program_ranking/services/scoring_service.py) |
| Recon service | [`control-plane/src/control_plane/domains/recon/service.py`](../control-plane/src/control_plane/domains/recon/service.py) |
| Postgres schema | [`infra/sql/01_schema.sql`](../infra/sql/01_schema.sql) |
| Dedup migration | [`infra/sql/02_dedup_fingerprints.sql`](../infra/sql/02_dedup_fingerprints.sql) |
| Audit realign migration | [`infra/sql/03_audit_log_realign.sql`](../infra/sql/03_audit_log_realign.sql) |
| Docker stack | [`infra/docker/docker-compose.yml`](../infra/docker/docker-compose.yml) |
| Kill-switch hook | [`.claude/hooks/pretool_killswitch.py`](../.claude/hooks/pretool_killswitch.py) |
| Antislop hook | [`.claude/hooks/pretool_antislop.py`](../.claude/hooks/pretool_antislop.py) |
| Approval-gate hook | [`.claude/hooks/pretool_approval_gate.py`](../.claude/hooks/pretool_approval_gate.py) |
| OpenRouter routing hook | [`.claude/hooks/pretool_venice_route.py`](../.claude/hooks/pretool_venice_route.py) |
| Hook wiring | [`.claude/settings.json`](../.claude/settings.json) |
| Sub-agent specs | [`.claude/agents/`](../.claude/agents/) |

## See Also

- [`project-overview-pdr.md`](project-overview-pdr.md) — design rationale + non-negotiables
- [`codebase-summary.md`](codebase-summary.md) — file inventory + dependency table + table list
- [`code-standards.md`](code-standards.md) — DDD layout + how to add a new MCP / hook / agent
- [`research/02-routing-ev.md`](research/02-routing-ev.md) — EV formula, model routing matrix, scope JWT scheme
- [`research/03-verifier-antislop.md`](research/03-verifier-antislop.md) — oracle designs + AnyPoC reward-hack countermeasures
- [`research/04-skills-mcps.md`](research/04-skills-mcps.md) — hook lifecycle + MCP catalogue
- [`research/05-deployment.md`](research/05-deployment.md) — solo + SaaS deployment walk-through
