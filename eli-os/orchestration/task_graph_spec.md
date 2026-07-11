# task_graph_spec.md — Task Graph Engine

Complex tasks are DAGs. Each node is a unit of work assigned to a tier; edges
are dependencies. The top tier plans and may restructure the graph; lower
tiers execute nodes.

## Node schema

```json
{
  "id": "string",
  "title": "string",
  "depends_on": ["node id", "..."],
  "tier": "haiku | sonnet | opus | top",
  "workflow": "optional brain-stack workflow id (e.g. net_sec_hardening)",
  "input": { "goal": "…", "mode": "plan|analysis", "constraints": ["…"], "context_ref": "memory pointer" },
  "output_schema_ref": "workflow output schema, or inline schema",
  "condition": "optional guard, evaluated when dependencies resolve; unmet → skipped",
  "status": "pending | running | done | skipped | failed | escalated",
  "result": { "output": "…", "confidence": 0.0, "tokens": { "in": 0, "out": 0, "cached": 0 } },
  "retries": 0
}
```

## Lifecycle

```text
PLAN ──▶ EXECUTE ──▶ AGGREGATE ──▶ REVIEW ──▶ RETURN
 │                                    │
 │  (top tier designs the DAG)        │  (optional top-tier coherence + risk pass)
 └───────────── RESTRUCTURE ◀─────────┘  (if constraints changed / review fails)
```

1. **Plan.** For a complex/high-impact task the top tier builds the DAG:
   picks the approach (2–3 options → one), decomposes it into nodes, assigns a
   tier per node using `routing/model_tree.json`, sets dependencies.
2. **Execute.** Nodes run when every `depends_on` is `done` or `skipped` —
   `skipped` is a terminal state that *satisfies* downstream dependencies. A
   node with a `condition` evaluates it at that moment: unmet → `skipped`, and
   downstream nodes treat its output as absent. Independent nodes run
   concurrently. Each node is a model call through the gateway (so routing,
   caching, telemetry, guardrails all apply).
3. **Aggregate.** Collect node outputs into the task's short-term context.
4. **Review.** Optional top-tier pass for coherence + risk across the aggregate
   (mandatory when the policy store flags the task high-impact / security-
   critical).
5. **Return.** Final result to the client, with trace metadata on request.

## Tier assignment rules

- Assign the **lowest tier that clears the node's bar** — most nodes are
  Sonnet/Haiku. Opus for deep-work nodes. Top tier for plan + review + any node
  the policy store forces up.
- A node bound to a `workflow` inherits that workflow's skeleton, decomposition,
  schema, and cache key from brain-stack — the node doesn't re-invent structure.

## Restructure rules

The top tier may restructure the DAG when:
- a **hard constraint changes** mid-task (add/remove nodes, re-tier),
- an **execution node fails or escalates** and the plan assumed its output,
- the **review pass** finds an incoherence that a re-plan fixes more cheaply
  than patching.

Every restructure is logged with the trigger (telemetry), so graph churn is
visible and auditable.

## Node failure & escalation

| Situation | Handling |
|-----------|----------|
| Node fails (tool error, timeout) | Auto-retry (up to `max_retries`, default 2, exponential backoff) **only if the node is idempotent** — pure model calls and reads. A node that fired an external action retries only if the action tool supports an idempotency key + dedup; a node with an `irreversible` action is **never** auto-retried (it may have partially succeeded before the timeout — surface to the planner and the guardrail gate instead). Exhausted retries → `failed`, surfaced to the planner. |
| Opus node stalls | Escalate that node to the top tier with full trace (`routing/model_tree.json#escalation`); status → `escalated`. |
| Downstream depends on a failed node | Planner decides: substitute, re-plan, or return partial with the gap named explicitly (never silently drop). |

## Concurrency & budget

- Independent nodes run in parallel up to a small cap (home-scale: a handful,
  not hundreds).
- Non-interactive multi-node jobs over the batch threshold
  (`routing/model_tree.json#budget_guards`) run through the Batch API.
- Every node reuses its cacheable prefix; the aggregate cost is tracked per
  node and rolled up in telemetry.

## Worked example — Guardian scan of a repo

```text
n1 [haiku]  triage+dedup raw findings
n2 [sonnet] STRIDE classify           depends: n1
n3 [opus]   semantic analysis of top-risk paths   depends: n2   workflow: (guardian analysis)
n4 [top]    verdict on contested findings          depends: n3   (only if n3 confidence < 0.6 or conflicts)
n5 [sonnet] assemble report in net_sec_hardening output schema   depends: n2,n3,n4
```
n4 carries a `condition` (the escalation trigger): when it's unmet, n4 becomes
`skipped`, which satisfies n5's dependency, and n5 assembles the report without
a top-tier verdict. That is the ~10% top-tier reservation in practice.
