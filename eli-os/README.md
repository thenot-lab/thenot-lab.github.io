# Eli OS v2 — Dominion Labs Agent Operating System

The unified specification for how every Dominion Labs surface (CompanionBot,
Eli Guardian, Security Consulting, Custom Dev, the site) uses AI models:
which model handles which work, how tasks escalate, how context is shared,
how everything is observed, and how cost is kept flat.

Eli OS v2 = five layers, each specified in its own file, all sitting on the
reasoning substrate already built in [`../brain-stack/`](../brain-stack/):

```
┌──────────────────────────────────────────────────────────────┐
│  CLIENTS      site · Telegram (CompanionBot) · CLI (Eli      │
│               Guardian) · internal Dominion workspace        │
├──────────────────────────────────────────────────────────────┤
│  GATEWAY &    request classifier → model router → escalation │
│  ROUTER       routing/{model_tree.json · routing_policy.md}  │
├──────────────────────────────────────────────────────────────┤
│  ORCHESTRA-   task-graph engine (DAG): plan → execute →      │
│  TION         aggregate → review   orchestration/            │
├──────────────────────────────────────────────────────────────┤
│  CONTEXT &    short-term task state · long-term vector store │
│  MEMORY       · profile/policy store   memory/               │
├──────────────────────────────────────────────────────────────┤
│  OBSERVABIL-  telemetry · guardrails · feedback loop         │
│  ITY          observability/                                 │
├──────────────────────────────────────────────────────────────┤
│  SUBSTRATE    ../brain-stack/ — global rules, skeletons,     │
│  (v1, built)  workflows, prompts, cache keys, batch          │
└──────────────────────────────────────────────────────────────┘
```

Cross-cutting: **the Eli Protocol** (`protocol/eli_protocol.md`) — Dominion's
security operating protocol (detect → isolate → remediate → harden). It is both
a product behavior (Eli Guardian, consulting) and how Eli OS protects itself.

## Files

| File | What it specifies |
|------|-------------------|
| `ARCHITECTURE.md` | Full system architecture + data flow + home-scale deployment view |
| `routing/model_tree.json` | Machine-readable routing policy: tiers, rules, escalation, budget guards |
| `routing/routing_policy.md` | Human routing policy: per-project task→tier tables, prompt patterns per tier |
| `protocol/eli_protocol.md` | The full Eli Protocol v2: phases, evidence, playbook format, Guardian pipeline |
| `memory/context_memory_spec.md` | Short-term, long-term, and policy stores; escalation context handoff |
| `orchestration/task_graph_spec.md` | DAG engine: node schema, tier assignment, restructure + review rules |
| `observability/telemetry_spec.md` | Log record schema, guardrails, feedback loop |
| `plans/utilization_optimization.md` | Unified cost/utilization plan across all projects |
| `plans/roadmap.md` | Phased build plan with acceptance criteria |

## Design stance (read before extending)

1. **Tier-fit, not tier-worship.** Most requests are Haiku/Sonnet work. Opus is
   for deep work. The top tier is reserved for the ~10% of tasks that are
   genuinely multi-constraint and high-impact — reached mostly by *escalation*,
   not by default routing.
2. **Artifacts outlive access.** Standing instructions, routing policies,
   workflows, and playbooks are authored once by the strongest available model
   and versioned in this repo. When model availability or pricing changes
   (e.g. a tier leaving a plan), the *structure* keeps running on whatever
   model remains. That is the durable part — not the authoring model's
   capability, which does not transfer, and not billing, which always follows
   the model that actually runs.
3. **Real cost levers only.** Tier-fit routing, prompt caching (stable prefix),
   and the Batch API (async discount). Nothing here assumes re-tiered billing.
4. **Home-executable.** Every component must run single-admin on a home server
   or small VPS with zero/low-dependency tooling — the Dominion ethos.

## Sources

Built from: the Claude Model Tree and Fable-5 prompting guides (routing +
prompt patterns), a multi-model gateway architecture draft (classifier, router,
escalation, memory, task graph, observability), the existing `brain-stack/`,
and the live Dominion Labs pages in this repo. The referenced Copilot chat
logs were not accessible (auth-gated share link); anything in them that isn't
reflected here should be pasted into a session and folded in as a follow-up.
