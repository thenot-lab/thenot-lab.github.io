# Eli OS v2 — Architecture

The generic multi-model gateway design, tailored to Dominion Labs: single
admin, home/VPS scale, zero/low dependency, budget-capped.

## 1. Client layer

| Client | Surface | Typical work |
|--------|---------|--------------|
| Web | thenot-lab.github.io + future app surfaces | Marketing, docs, demos |
| Telegram | CompanionBot | Persona chat, tasks in conversation, per-user memory |
| CLI | Eli Guardian | Repo/host scans, finding triage, report generation |
| Internal | Dominion workspace (cowork sessions, consulting docs) | Deep work, engagement deliverables |
| API | Other services calling the gateway (REST) | Automation, webhooks |

All clients speak to one **AI gateway** over HTTPS. No client calls a model
endpoint directly — routing, guardrails, and telemetry only work if the
gateway is the single choke point.

## 2. AI gateway & router (the Model Tree brain)

Stateless service; horizontally scalable but sized for one box.

- **Request classifier.** Inspects metadata + content: task type, length,
  user role, risk flags (irreversible? security-critical? external-facing?),
  interactivity (chat vs batch), prior failures on this task.
- **Model router.** Applies `routing/model_tree.json`:
  - quick, low-stakes → **Haiku 4.5**
  - everyday, structured → **Sonnet 5**
  - deep, multi-step → **Opus 4.8**
  - hardest, multi-constraint, high-risk decisions → **Fable 5** (top tier)
- **Escalation logic.** If an Opus run stalls — low confidence, iteration cap
  hit, conflicting outputs — escalate to the top tier with the *full trace +
  context* (see `memory/context_memory_spec.md`). The top tier may override or
  refine and push back a recommended approach; the router records the verdict.
- **Budget guards.** Per-day and per-project token ceilings; top-tier share
  target ≤10% of requests (alert when trending above).

## 3. Tooling & integrations layer

- **Web search** — available to all tiers, toggled per request; deep-research
  flags give Opus/top-tier runs priority use of it.
- **Productivity connectors** — Slack, Google Drive, Notion, etc. Sonnet is
  the default for "operate on this doc/file/message" tasks.
- **Custom tools** (standard tool-API schema, least privilege each):
  - *Data fetchers*: internal APIs, DBs, scan results, logs.
  - *Action tools*: ticket creation, workflow triggers, code execution,
    deploy hooks. Every action tool is tagged `reversible` or `irreversible`;
    irreversible ones require the guardrail gate (§6).

## 4. Context & memory layer

Specified in `memory/context_memory_spec.md`. Three stores:

- **Short-term context** — conversation state, current task-graph node,
  intermediate outputs. Shared across tiers so escalation carries history.
- **Long-term memory / vector store** — docs, prior decisions, architecture
  specs, playbooks, past engagement reports. Heavily used by top-tier runs
  for tradeoff analysis.
- **Profile & policy store** — user roles, permissions, tone prefs, risk
  thresholds. The router consults it to decide when top-tier review is
  *mandatory* (e.g. high-impact decisions, security-sensitive output).

## 5. Reasoning & workflow orchestration

Specified in `orchestration/task_graph_spec.md`.

- **Opus workflows** — multi-step plans, cowork-style sessions, iterative
  refinement; builds artifacts (docs, plans, code) before finalizing. Each
  workflow execution is a `brain-stack` workflow run (skeleton + decomposition
  + schema + cache key).
- **Top-tier decision engine** — entry pattern is fixed: goal, constraints,
  tradeoffs, 2–3 approaches, recommend one with reasoning
  (= brain-stack `Problem → Options → Tradeoffs → Recommendation`). Used for
  architecture decisions, strategy, complex debugging, multi-system tradeoffs.
  It can instruct other tiers: design the plan → Opus executes → Sonnet/Haiku
  handle follow-ups.
- **Task graph engine** — complex tasks as DAGs, subtasks assigned to tiers;
  the top tier can restructure the graph when constraints change.

## 6. Observability, safety, governance

Specified in `observability/telemetry_spec.md`.

- **Logging** — every request: model chosen, tools used, tokens (in/out/
  cached), latency, cost, confidence. Escalations tagged and auditable.
- **Guardrails** — content filters, role-based access, the irreversible-action
  gate, prompt-injection screening on tool/connector output (Eli Protocol
  applied to Eli OS itself).
- **Feedback loop** — user ratings, corrections, "this went wrong" signals;
  a periodic top-tier review of patterns proposes routing/prompt updates as
  PRs against this directory.

## 7. Data flow — typical complex task

1. Request enters the gateway.
2. Classifier tags it complex + high-impact → routes to the top tier.
3. Top tier pulls relevant memory (docs, prior decisions), calls web search /
   tools as needed, thinks through tradeoffs, proposes 2–3 approaches,
   recommends one.
4. Task-graph engine breaks the chosen approach into subtasks:
   Opus executes deep-work nodes; Sonnet handles structured doc edits,
   summaries, integrations; Haiku handles quick clarifications.
5. Outputs aggregate; optionally one more top-tier pass for coherence + risk.
6. Result returns to the client with trace metadata on request.

## 8. Deployment view (home-scale)

The generic design assumes a fleet; Dominion runs it on one box.

| Component | Dominion-scale choice |
|-----------|----------------------|
| Gateway + router | One FastAPI (or similar) service, Docker Compose, stateless |
| Tooling services | In-process tool registry first; split out only when a tool needs isolation |
| Short-term store | Redis or plain SQLite table (single admin ≠ Redis required) |
| Vector store | SQLite + sqlite-vec, or Postgres + pgvector if Postgres already runs |
| Profile/policy store | Same SQLite/Postgres, versioned YAML seed in repo |
| Observability | Structured JSONL logs + one dashboard (Grafana or a static HTML report); alerts via Telegram bot |
| Model endpoints | Managed API endpoints per tier; router picks per request |
| Secrets | Env vars via `.env` outside repo (`.gitignore` already guards) |

Rule: every component must pass the **home-executable** check
(`brain-stack/failure_modes.md#non-home-executable`).
