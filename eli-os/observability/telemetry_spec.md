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
  "escalation_trigger": "null | self_reported_confidence | iterations_without_convergence | conflicting_outputs_across_runs | constraint_conflict_detected | policy",
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

`escalation_trigger` values are the **canonical signal names from
`routing/model_tree.json#escalation`** — telemetry producers and dashboards
must use them verbatim (plus `null` for "not escalated" and `policy` for
policy-store-forced routing) so the two files never disagree.

## Gate & action event schema

Model calls aren't the only auditable moments: RBAC denials, confirmation
pauses, and action-tool executions can all happen outside any model call. They
get their own record type in the same JSONL stream:

```json
{
  "ts": "iso8601",
  "record": "gate",
  "request_id": "string",
  "session_id": "string",
  "principal": "user/service identity from the profile store",
  "kind": "rbac_denial | content_filter | injection_flag | confirmation_pause | confirmation_result | action_execution",
  "action": "tool + operation (e.g. deploy_hook:trigger, drive:delete)",
  "reversibility": "reversible | irreversible | n/a",
  "decision": "allowed | denied | paused | confirmed | aborted",
  "result": "ok | failed | n/a"
}
```

Every gate outcome and every action-tool execution writes one — including
denials and pauses where no model was ever called.

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

Gate outcomes tied to a model call also land in that call's `guardrail_flags`;
outcomes outside a model call (denied requests, standalone action executions)
are captured as `gate` records. The two record types together are the audit
trail — neither alone is complete.

## Feedback loop

- **Capture:** user ratings, explicit corrections, and "this went wrong"
  signals attach to the `request_id` that produced the output.
- **Review:** a periodic (weekly) top-tier pass reads the telemetry +
  corrections and asks: which routes misfired? which prompts underperformed?
  where did escalation trigger too late or never?
- **Act:** it proposes concrete changes — a routing rule, a prompt pattern, an
  escalation threshold — as a **PR against this directory**. Routing policy
  evolves through reviewed diffs, not silent drift. Every change is versioned;
  `routing/model_tree.json` and `routing/routing_policy.md` move together.

## What is deliberately NOT claimed

Telemetry measures real tokens, real latency, real cost against the real model
that ran. It does not — and cannot — reattribute a tier's usage to a cheaper
one. The cost levers it helps you tune are the honest three: **tier-fit
routing, cache-hit rate, and batch coverage.**
