# context_memory_spec.md — Context & Memory Layer

Three stores. Shared across tiers so escalation carries full history. Sized for
single-admin / home-scale (SQLite-first; upgrade only when a limit is real).

## 1. Short-term context store

Conversation state + the current task's working set. Lives for the task's
lifetime; evicted or archived after.

```json
{
  "session_id": "string",
  "project": "companionbot | eli_guardian | consulting | site_devtools",
  "task_id": "string",
  "current_node": "task-graph node id (see orchestration/task_graph_spec.md)",
  "messages": ["ordered conversation turns"],
  "intermediate_outputs": [{ "node": "id", "tier": "haiku|sonnet|opus|top", "output": "…", "confidence": 0.0 }],
  "active_constraints": ["hard constraints carried across the whole task"],
  "cache_key": "the brain-stack cache key for the stable prefix in use"
}
```

Backing store: Redis if already running, else a SQLite table. Single admin does
not need Redis; don't add it for its own sake.

## 2. Long-term memory / vector store

Durable knowledge, retrieved by semantic search at task start.

- **Contents:** architecture specs (this repo), prior decisions + their
  rationale, playbooks (`protocol/`), past Guardian findings, engagement
  reports, brand/tone docs.
- **Schema per record:** `{ id, project, type, title, text, embedding, source,
  created_at, supersedes? }`.
- **Retrieval:** top-k by cosine similarity, filtered by `project`; injected as
  the `[CONTEXT_BLOB]` slot of the prompt skeleton.
- **Heavy user:** the top tier, for tradeoff analysis and approach
  recommendation — it reads prior decisions so it doesn't re-litigate settled
  ones.
- **Backing store:** SQLite + sqlite-vec, or pgvector if Postgres already runs.
- **Write policy:** decisions and playbooks are written back after a task
  completes (with `supersedes` linking the record they replace) so the store
  is the living memory, not a stale dump.

## 3. Profile & policy store

Governs *who* gets *what* and *when the top tier is mandatory*.

```yaml
users:
  admin:
    role: owner
    permissions: [all_tools, irreversible_actions_with_gate]
    tone: direct
    risk_threshold: high        # tolerates the model acting without asking on reversible work
policies:
  force_top_tier_review_when:
    - output_is_security_critical
    - decision_is_high_impact         # architecture, spend, external commitment
    - action_is_irreversible_and_external
  budgets:
    per_project_daily_token_ceiling:
      eli_guardian: 2_000_000
      consulting: 1_000_000
      companionbot: 500_000
      site_devtools: 250_000
  top_tier_share_target: 0.10
```

The router reads this *before* routing: a policy match can force the top tier
regardless of task size, and a budget breach can force batch/deferral.

## Escalation handoff (why the stores matter)

When Opus stalls and the router escalates (`routing/model_tree.json#escalation`),
the top-tier call receives, assembled in cache-friendly order:

1. Stable prefix (brain-stack: global + project + patterns + workflow) — cached.
2. **Full short-term context** — every intermediate output *and its confidence*,
   not a summary. The contradictions are the signal.
3. **Relevant long-term memory** — prior decisions on this surface.
4. The escalation reason (which trigger fired).

Rule: **never hand up a summary.** Summarizing before escalation discards the
conflicting outputs that triggered the escalation in the first place.
