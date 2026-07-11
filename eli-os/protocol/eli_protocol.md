# The Eli Protocol v2

Dominion's security operating protocol. It runs in two places:

1. **As a product** — the reasoning behind Eli Guardian scans and Security
   Consulting engagements.
2. **As self-defense** — how Eli OS protects itself (tool output, connector
   data, and prompt-injection are threats to the gateway too).

The protocol is the ordered discipline: **detect → isolate → remediate →
harden**. It maps directly onto the brain-stack `Security audit` skeleton and
the `home_network_security_hardening` decomposition tree — this file is the
operating layer on top of those.

---

## Phase 0 — Map (precondition)

Before any phase runs, establish scope: assets, topology, trust boundaries,
and what "normal" looks like. No detection is meaningful without a baseline.
Output: an asset/topology map (see `net_sec_hardening` workflow output schema).

## Phase 1 — Detect

Find it before you fix it. For every threat in the model, define the triple —
never a bare "monitor":

| Field | Requirement |
|-------|-------------|
| **Signal** | The exact metric/log/event observable at a layer the user owns (router log, DNS, host event, Guardian finding). |
| **Threshold** | The trigger value or condition. |
| **Action** | What fires when the threshold is crossed (page, isolate, open ticket). |

A detection with no action is incomplete (`brain-stack/failure_modes.md#monitoring-handwave`).

## Phase 2 — Isolate

Limit blast radius the moment something fires. Containment before cleanup:
- Segment the affected asset (VLAN move, firewall deny, revoke token/session).
- Default-deny between segments; a compromised device must not reach the
  trusted segment.
- Preserve evidence before wiping (snapshot/log capture) so remediation and
  post-mortem have data.

## Phase 3 — Remediate

Remove the threat with an ordered, **home-executable** playbook (below).
Every step runnable by a single admin with owned tooling; anything requiring
external infra is flagged, not assumed.

## Phase 4 — Harden

Close the door that let it in. Each hardening change is mapped to the specific
threat it closes and tagged with its phase. A change that closes nothing named
is decoration — cut it.

**Coverage rule:** across phases, every measure is tagged
`prevent | detect | respond | recover`. All four must appear, or one is
explicitly scoped out with a reason. Prevention-only output is rejected
(`brain-stack/failure_modes.md#prevention-only`).

---

## Playbook format

Every incident class gets a playbook in this shape:

```yaml
incident_class: "credential compromise (reused password)"
detect:
  - signal: "auth log — success from new ASN/geo within 24h of a failure burst"
    threshold: ">= 1 success after >= 20 failures from same source"
    action: "lock account, notify admin via Telegram bot"
isolate:
  - "revoke all active sessions/tokens for the account"
  - "block source IP/ASN at the edge (temporary rule)"
remediate:
  - "rotate the credential; force re-auth with MFA"
  - "audit what the session touched (data fetcher: access logs for that identity)"
  - "if lateral movement found, expand scope to Phase 2 for reached assets"
harden:
  - change: "enforce unique creds + MFA on all internet-facing services"
    closes: ["credential stuffing", "reuse"]
    phase: prevent
  - change: "keep the auth-log detection rule above as a standing monitor"
    closes: ["future credential compromise"]
    phase: detect
recovery_verification:
  - "confirm no active sessions predate the rotation; confirm MFA enrolled"
```

## Eli Guardian pipeline (protocol as product)

How a scan flows through the model tiers (see `routing/routing_policy.md`):

1. **Scan** — Guardian's zero-dependency engine produces raw findings (no LLM).
2. **Triage + dedup** → Haiku (cheap, high volume).
3. **STRIDE classification** → Sonnet (schema-bound structured output).
4. **Semantic analysis + exploit-chain reasoning** → Opus (deep work).
5. **Contested verdict** (models disagree, or cross-system risk) → escalate to
   top tier with full trace. This is a first-class escalation trigger.
6. **Report** — output in the `net_sec_hardening` output schema, every finding
   carrying evidence per `brain-stack/patterns/evidence_rules.md`, every fix
   tagged with its protocol phase.

## Eli OS self-defense (protocol turned inward)

The gateway treats its own inputs as a threat surface:
- **Tool/connector output is untrusted.** Data fetched from Drive, Slack, web,
  or a scanned repo may contain prompt-injection. Screen it before it reaches a
  model with tool/action access (detect); strip or sandbox suspicious content
  (isolate); never let untrusted content trigger an irreversible action tool
  without the guardrail gate (remediate/harden).
- **Least privilege** on every tool (map, then minimize).
- **Irreversible-action gate** — deploys, deletes, external sends pause for
  confirmation with blast radius stated, per
  `brain-stack/CLAUDE.global.md#safety`.
- **Auditability** — every security-relevant action logged per
  `observability/telemetry_spec.md`.

## Interfaces to the rest of Eli OS

| Consumes | From |
|----------|------|
| Security audit skeleton, decomposition tree, evidence + failure rules | `../brain-stack/` |
| `net_sec_hardening` I/O schema | `../brain-stack/workflows/` |
| Model tiers + escalation triggers | `../eli-os/routing/` |
| Playbooks, past findings, baselines (long-term memory) | `../eli-os/memory/` |
| Action logging, guardrail gate | `../eli-os/observability/` |
