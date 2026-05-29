# 00c — Context7 Verifications (Phase 2 §10.4 + Sandbox Hardening)

Pulled during the Phase 2 §10.4 closeout session. Extends `00-context7-docs.md`
(Phase 0 base) and `00b-context7-extended.md` (Phase 1+ additions) with the
live API surfaces verified for the platform-MCP build and the Firecracker
patterns needed for the sandbox prod hardening.

## Library IDs Resolved (this session)

| Lib | Context7 ID | Snippets | Score | Used for |
|---|---|---|---|---|
| HackerOne API | `/websites/api_hackerone` | 569 | 81.0 | h1-mcp submission verify |
| Bugcrowd | `/websites/bugcrowd` | 2262 | 74.2 | bugcrowd-mcp body shape verify |
| Intigriti API | `/websites/intigriti_readme_io_reference` | 245 | 55.5 | intigriti-mcp endpoint discovery |
| Intigriti Researcher API | `/websites/intigriti-researcher-api_readme_io_reference` | 37 | 60.4 | researcher endpoint surface |
| Firecracker | `/firecracker-microvm/firecracker` | 1162 | (already in 00b) | sandbox jailer + netns |

**Not indexed in context7** (verified empty on this session's resolves):
- YesWeHack — `Yes We Hack`, `YesWeHack`, `YWH` all returned no library.
- Immunefi — `Immunefi` returned no library.
- For both, `yeswehack-mcp` and `immunefi-mcp` ship with build-plan-derived
  body shapes plus an `extra` parameter that lets callers pass programme-
  specific fields without forking the client. Verify against your live
  programme on first prod submit.

---

## HackerOne — POST /v1/hackers/reports

**Verified:** the shipped h1-mcp matches the live API on every load-bearing
field. Two refinements landed after this lookup
(commit `2e56883`): added `structured_scope_id`; relaxed `weakness_id ≤ 0`
rejection to `weakness_id < 0` (the docs use `0` as the unspecified-weakness
sentinel).

```http
POST https://api.hackerone.com/v1/hackers/reports
Authorization: Basic <base64(username:api_token)>
Content-Type: application/json
Accept: application/json
```

```json
{
  "data": {
    "type": "report",
    "attributes": {
      "team_handle":              "<program slug>",
      "title":                    "<= 200 chars>",
      "vulnerability_information": "<full markdown>",
      "impact":                   "<impact section>",
      "severity_rating":          "none|low|medium|high|critical",
      "weakness_id":              0,
      "structured_scope_id":      0
    }
  }
}
```

**Auth:** HTTP Basic. Username = your H1 username; password = personal API
token. The H1 docs use `weakness_id: 0` and `structured_scope_id: 0` in their
published example as unspecified-sentinel placeholders.

**Severity enum:** `none | low | medium | high | critical`. **No `informational`
tier.**

**Weakness IDs are H1's own catalogue**, not MITRE CWE. Fetch via
`GET /v1/weaknesses` and cache. A future helper could bridge normalize-mcp's
`CWE-NN` output to the H1 weakness ID, but that mapping is platform-specific
and out of scope for h1-mcp v0.1.

**Response shape (201):**
```json
{
  "data": {
    "id": "<report uuid>",
    "type": "report",
    "attributes": {
      "title": "...",
      "state": "new"
    }
  }
}
```

H1's April 2026 deprecation affected the *org-assets* endpoint
(`/v1/organizations/{id}/assets`), already migrated in
`control-plane/src/control_plane/domains/scope_management/integrations/hackerone.py`.
The `/v1/hackers/reports` endpoint is unaffected by that migration.

---

## Bugcrowd — POST /submissions

**Verified:** the build-plan-derived `{"submission": {target, title, ...}}`
body shape was **wrong**. Real Bugcrowd `/submissions` takes a JSON:API
resource. Fixed in commit `938d9f3`.

```http
POST https://api.bugcrowd.com/submissions
Authorization: Token <api_token>
Content-Type: application/json
Accept: application/json
```

```json
{
  "data": {
    "type": "submission",
    "attributes": {
      "title":       "<= 200 chars>",
      "description": "<full markdown report>",
      "severity":    1,
      "vrt_id":      "cross_site_scripting_xss.reflected"
    },
    "relationships": {
      "program": {"data": {"type": "program", "id": "<program_uuid>"}},
      "target":  {"data": {"type": "target",  "id": "<target_uuid>"}}
    }
  }
}
```

**Required:** `attributes.title`, `attributes.description`,
`relationships.program.data.id`. **Optional:** `attributes.severity` (P1..P5
integer), `attributes.vrt_id` (Bugcrowd VRT taxonomy, dot-separated),
`relationships.target.data.id`.

**Severity mapping** — Bugcrowd uses P1..P5 integers; the cross-platform
canonical names map as:

| Canonical name | Bugcrowd P-tier | Integer |
|----------------|-----------------|---------|
| critical | P1 | 1 |
| high | P2 | 2 |
| medium | P3 | 3 |
| low | P4 | 4 |
| informational | P5 | 5 |

**Auth scheme** is Bugcrowd's documented `Token <api_token>` (Authorization
header). Some accounts expect `Bearer` instead — bugcrowd-mcp exposes
`BUGCROWD_AUTH_SCHEME` env to override.

**Response (201):** JSON:API submission resource with `data.id` (the new
submission UUID), `data.attributes.state` (`new`), and an optional
`included[]` array carrying a `ClaimTicket`.

**Error states observed in docs:**
- 400 Bad request
- 403 Forbidden client-generated ID
- 404 Missing resource
- 409 Incorrect data type parameter
- 422 Required attributes were not provided

---

## Intigriti — Researcher API has no public submission endpoint

**Verified across both indexed Intigriti libraries.** The researcher API
(`https://api.intigriti.com/external/researcher`) exposes **GET endpoints
only** — programme listing, programme detail, scope, rules of engagement.
The company API (`https://api.intigriti.com/external/company`) exposes POST
write endpoints but none of them creates a new submission; only side
operations (post-comment, add-bonus, change-state).

**Researchers create new submissions through the Intigriti web UI**, not
the API. This is the platform's documented model.

`intigriti-mcp` ships `submit_report` as a placeholder:

- Default `submit_url` → `{base_url}/v1/submissions` (intentionally a path
  Intigriti will 404, so a caller cannot accidentally believe it works).
- Override via `INTIGRITI_SUBMIT_URL` env to point at a relay you operate
  (e.g. a CI hook that opens a PR-style submission ticket).

**Read-only researcher endpoints that DO work:**

```http
GET /v1/programs                      # programme listing
GET /v1/programs/{programId}          # programme detail (scope, ROE)
```

Both take `Authorization: Bearer <PAT>`. Programme detail returns scope
domains with per-asset `tier`, `maxBounty`, `minBounty`, `description`. This
is what `bbscope` v2's `--auth` mode uses; control-plane's scope-ingest
worker can use the same surface.

**Severity enum (researcher portal vocabulary):** `informational | low |
medium | high | critical | exceptional`. The `exceptional` tier is
Intigriti-only, above `critical`. `intigriti-mcp` accepts it for forward
compatibility with any future relay endpoint.

---

## Firecracker — Jailer + Network Namespace + Egress NAT

For the **sandbox-mcp prod hardening** task. The current sandbox-mcp ships
the protocol + `LocalSubprocessDriver` (DEV-ONLY, refuses to run without
two independent gates) + `DockerDriver` scaffold (refuses to run without
the `bs5-egress-gate` sidecar). The Firecracker driver is the production
target.

### Jailer invocation (per-VM isolation)

```bash
/usr/bin/jailer \
    --id <microvm_id> \
    --exec-file /usr/bin/firecracker \
    --uid 1000 \
    --gid 1000 \
    --cgroup cpuset.cpus=0-1 \
    --cgroup cpuset.mems=0 \
    --netns /var/run/netns/<scope_token_jti> \
    --daemonize \
    --new-pid-ns
```

The `--netns` argument is the integration seam for the egress allowlist:
each VM gets its own network namespace named after the scope JWT's `jti`
claim, and the iptables rules inside that namespace enforce the allowlist.

### Per-namespace TAP + IP forwarding

```bash
# Namespace per finding/job
sudo ip netns add bs5_${JTI}

# TAP inside the namespace
sudo ip netns exec bs5_${JTI} ip tuntap add name vmtap0 mode tap
sudo ip netns exec bs5_${JTI} ip addr add 192.168.241.1/29 dev vmtap0
sudo ip netns exec bs5_${JTI} ip link set vmtap0 up

# veth pair to the host root namespace
sudo ip link add veth-${JTI}-h type veth peer name veth-${JTI}-g
sudo ip link set veth-${JTI}-g netns bs5_${JTI}
sudo ip addr add 10.0.0.1/30 dev veth-${JTI}-h
sudo ip link set veth-${JTI}-h up
sudo ip netns exec bs5_${JTI} ip addr add 10.0.0.2/30 dev veth-${JTI}-g
sudo ip netns exec bs5_${JTI} ip link set veth-${JTI}-g up
sudo ip netns exec bs5_${JTI} ip route add default via 10.0.0.1
```

### Scope-derived egress allowlist (the bs5-egress-gate sidecar's job)

```bash
# 1. resolve every scope wildcard / exact_host to its IPs
for HOST in $(jq -r '.targets.exact_hosts[], .targets.wildcards[]' scope.json); do
  dig +short A "$HOST"
done | sort -u > /tmp/${JTI}.allowed_ips

# 2. drop anything not on the allowlist
UPSTREAM=$(ip -j route list default | jq -r '.[0].dev')
ip netns exec bs5_${JTI} iptables -P FORWARD DROP
while read IP; do
  ip netns exec bs5_${JTI} iptables -t nat -A POSTROUTING -d "$IP" -o veth-${JTI}-g -j MASQUERADE
  iptables -t nat -A POSTROUTING -s 10.0.0.0/30 -d "$IP" -o "$UPSTREAM" -j MASQUERADE
  iptables -A FORWARD -s 10.0.0.0/30 -d "$IP" -j ACCEPT
  iptables -A FORWARD -d 10.0.0.0/30 -s "$IP" -j ACCEPT
done < /tmp/${JTI}.allowed_ips

# 3. teardown after the run (bs5-egress-gate's `release` API)
sudo ip netns del bs5_${JTI}
sudo ip link del veth-${JTI}-h 2>/dev/null
```

### Boot kernel + rootfs (Firecracker API over Unix socket)

```bash
API_SOCKET=/var/run/firecracker/${JTI}.sock

curl -X PUT --unix-socket $API_SOCKET --data "{
  \"kernel_image_path\": \"/var/lib/firecracker/vmlinux-5.10\",
  \"boot_args\": \"console=ttyS0 reboot=k panic=1\"
}" http://localhost/boot-source

curl -X PUT --unix-socket $API_SOCKET --data "{
  \"drive_id\": \"rootfs\",
  \"path_on_host\": \"/var/lib/firecracker/bs5-runtime.ext4\",
  \"is_root_device\": true,
  \"is_read_only\": true
}" http://localhost/drives/rootfs

curl -X PUT --unix-socket $API_SOCKET --data "{
  \"iface_id\": \"eth0\",
  \"guest_mac\": \"06:00:AC:10:00:02\",
  \"host_dev_name\": \"vmtap0\"
}" http://localhost/network-interfaces/eth0

curl -X PUT --unix-socket $API_SOCKET --data "{
  \"action_type\": \"InstanceStart\"
}" http://localhost/actions
```

**Pinned versions** in the future runtime image (Phase 2 §10.4 hardening):

| Component | Pinned to |
|-----------|-----------|
| Firecracker | v1.7.x (latest LTS) |
| Jailer | bundled with Firecracker |
| Kernel | vmlinux-5.10 (Firecracker recommended) |
| Rootfs | `bs5-runtime:0.1.0` — alpine + curl + jq + python3, no shell history, no caches |

### Sandbox-mcp wiring

The `DockerDriver.preflight()` already raises `NotImplementedError` until
`BS_EGRESS_GATE_URL` is set. The Firecracker driver follows the same
preflight: refuses to run without:

1. `BS_FIRECRACKER_BIN=/usr/bin/firecracker`
2. `BS_JAILER_BIN=/usr/bin/jailer`
3. `BS_EGRESS_GATE_URL=http://127.0.0.1:7799` (the bs5-egress-gate sidecar)
4. `BS_RUNTIME_IMAGE=bs5/sandbox-runtime:0.1.0`

Build steps (separate hardening task, NOT this session's deliverable):

1. Author `infra/sandbox/egress-gate/` — Go or Python sidecar that exposes
   `POST /jit/{jti}` (install rules from scope token) and
   `DELETE /jit/{jti}` (teardown).
2. Build `infra/sandbox/runtime/` — minimal Alpine ext4 rootfs with the
   needed binaries.
3. Implement `mcp/sandbox-mcp/src/sandbox_mcp/drivers/firecracker.py` —
   Python httpx client that hits the Firecracker Unix socket and the
   egress-gate sidecar.
4. Update `mcp/sandbox-mcp/src/sandbox_mcp/server.py::_select_driver` to
   instantiate it when `SANDBOX_DRIVER=firecracker`.

---

## Notes for future context7 pulls

- **Re-pull H1 after major version changes.** The hacker API has been
  stable for years, but H1 publishes deprecation timelines well in advance
  (e.g. April 2026 for `structured_scopes`).
- **Bugcrowd's JSON:API spec is verbose** (2262 snippets). Re-pull only the
  endpoint of interest with a targeted query — full-doc pulls waste budget.
- **Intigriti is unlikely to expose a researcher submission API soon** —
  the platform's UX is built around the web UI's structured submission
  wizard. Watch for changes via the Intigriti changelog rather than
  re-querying context7.
- **YesWeHack and Immunefi** would benefit from being added to context7;
  until indexed, the relevant client lives behind the `extra` parameter
  pattern so callers can adjust without forking.
