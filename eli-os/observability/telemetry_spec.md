# telemetry_spec.md — Observability, Safety, Governance

What every request records, the guardrails that gate it, and the feedback loop
that keeps routing honest. Home-scale: structured JSONL + one dashboard.

## Log record schema

One record per model call (node), appended to a JSONL log.

```json
{
  "ts": "iso8601",
  "request_id": "string",
  "session_id": "string",
  "task_id": "string",
  "node_id": "string",
  "project": "companionbot | eli_guardian | consulting | site_devtools",
  "tier": "haiku | sonnet | opus | top",
  "model": "resolved model id",
  "route_reason": "which rule/override/escalation selected the tier",
  "escalated": false,
  "escalation_trigger": "null | confidence | iterations | conflict | constraint_conflict | policy",
  "tools_used": ["web_search", "drive", "data_fetcher:access_logs", "..."],
  "tokens": { "in": 0, "out": 0, "cached": 0 },
  "cache_hit": true,
  "batch": false,
  "latency_ms": 0,
  "cost_usd": 0.0,
  "confidence": 0.0,
  "guardrail_flags": ["none | injection_suspected | irreversible_gate | rbac_denied | content_filter"],
  "outcome": "ok | retried | failed"
}
```

## Dashboards / signals to watch

| Signal | Why | Alert |
|--------|-----|-------|
| Top-tier request share | Keep the expensive tier for the ~10% that need it | `> 15%` (budget guard) |
| Cache-hit rate on workflow runs | Caching is a primary cost lever; misses = wasted input spend | `< 70%` on stable-prefix workflows |
| Cost per project / day | Budget ceilings from the policy store | approaching daily ceiling |
| Escalation rate + trigger mix | Rising escalations = a routing rule or prompt needs work | trend up week-over-week |
| Guardrail flags | Security posture of the gateway itself | any `injection_suspected` acting on an action tool |
| Failed / retried nodes | Reliability | spike |

## Guardrails (the safety gate)

Every request passes these before and after the model call:

1. **RBAC** — the profile/policy store authorizes the user for the tools/actions
   requested; deny → `rbac_denied`.
2. **Content filter** — input and output screened per policy.
3. **Prompt-injection screen** — tool/connector/web output is untrusted
   (Eli Protocol self-defense); suspicious content is flagged and may not
   trigger an action tool without the gate below.
4. **Irreversible-action gate** — any tool tagged `irreversible` (deploy,
   delete, external send, credential use) pauses for confirmation with the
   blast radius stated (`brain-stack/CLAUDE.global.md#safety`). No exceptions
   for automated flows unless the policy store pre-authorizes that exact action.
5. **High-impact review** — policy-flagged outputs get a top-tier review pass
   before reaching the user.

All gate outcomes land in `guardrail_flags` — the log is the audit trail.

## Feedback loop

- **Capture:** user ratings, explicit corrections, and "this went wrong"
  signals attach to the `request_id` that produced the output.
- **Review:** a periodic (weekly) top-tier pass reads the telemetry +
  corrections and asks: which routes misfired? which prompts underperformed?
  where did escalation trigger too late or never?
- **Act:** it proposes concrete changes — a routing rule, a prompt pattern, an
  escalation threshold — as a **PR against this directory**. Routing policy
  evolves through reviewed diffs, not silent drift. Every change is versioned;
  `model_tree.json` and `routing_policy.md` move together.

## What is deliberately NOT claimed

Telemetry measures real tokens, real latency, real cost against the real model
that ran. It does not — and cannot — reattribute a tier's usage to a cheaper
one. The cost levers it helps you tune are the honest three: **tier-fit
routing, cache-hit rate, and batch coverage.**
