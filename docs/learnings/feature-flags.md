# Feature Flags — OpenFeature + custom Unleash provider

## ⚠️ The flag is NOT an authorization boundary

`tier-enterprise` (and any tier flag) is a **rollout / config gate, NOT the security
boundary.** Entitlement MUST be enforced server-side against the tenant's signed plan
/ JWT. **Never** treat `is_enabled("tier-enterprise")` as the authorization check —
doing so is a privilege-escalation vector. The flag decides *rollout*; the signed plan
decides *entitlement*.

Two more rules that follow from this:

- **Evaluation context is untrusted input.** Tier decisions must not key off
  caller-supplied context fields as the trust source. A caller passing
  `context={"tier": "enterprise"}` must not be able to flip the gate on its own.
- **Community/solo in-memory defaults ship `tier-enterprise=False`.** Setting an
  in-memory enterprise flag to True is dev-only and must never ship in the community
  edition.

## Why a custom provider

OpenFeature has **no official Unleash provider for Python** (0% Python coverage in the
OpenFeature provider matrix; Unleash/unleash#3912 is still open). Options were:
(1) custom `AbstractProvider` wrapping the Unleash Python client, (2) `flagd` as an
eval-layer intermediary, (3) switch to a provider-native flag system. We chose (1) —
`control_plane.core.flags.provider.UnleashProvider` — to keep the OpenFeature API
surface while talking to self-hosted Unleash.

## Fail-closed doctrine

Every flag lookup fails closed:

- `is_enabled(flag, default=False)` returns `default` on ANY error and never raises.
- The Unleash provider treats an errored OR malformed/non-bool/spoofed response as
  fail-closed (returns default), not as enabled. A *successful* spoofed `"true"` is
  not trusted.
- If Unleash construction fails at `configure_flags()`, we fall back to the in-memory
  community default (still gated), never ungated.

## Provider integrity

- `UnleashProvider` rejects non-`https://` URLs unless `allow_insecure=True` (dev only).
- The token is read from env/secrets (`UNLEASH_TOKEN`), never hardcoded.

## Usage

```python
from control_plane.core.flags import configure_flags, is_enabled

configure_flags()                       # in-memory community default (offline)
# or set UNLEASH_URL + UNLEASH_TOKEN env → custom UnleashProvider

if is_enabled("tier-enterprise", default=False, context={"userId": tenant_id}):
    ...  # rollout-gated path ONLY — still enforce entitlement server-side
```

## Self-hosting Unleash

```bash
docker compose -f infra/docker-compose.unleash.yaml up -d
# admin UI: http://localhost:4242  (dev creds admin/unleash4all — rotate before non-local)
```

## Deferred

- **LaunchDarkly** for SaaS tenant flags (Phase 3+). OpenFeature has an official
  LaunchDarkly provider, so that path needs no custom code.
- Wiring the gate into subagent boundaries — lands with enterprise tier gating in
  Phase 4 (this plan provides only the primitive).
- CI enforcement that `is_enabled` is never used as an authz check.
