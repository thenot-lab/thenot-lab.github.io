# Unified Utilization & Cost Optimization Plan

One plan for keeping Eli OS cheap and effective across **all** Dominion
projects. It rests on three real levers and rejects the fake one.

## The levers (and the non-lever)

| Lever | What it actually does | Where enforced |
|-------|----------------------|----------------|
| **Tier-fit routing** | Runs each task on the cheapest tier that clears its bar; reserves the top tier for the ~10% that need it. | `routing/model_tree.json`, `routing/routing_policy.md` |
| **Prompt caching** | Discounts the repeated stable prefix (global + project + patterns + workflow) within the cache window. | `brain-stack/cache/cache_key_schema.md`, `brain-stack/prompts/prompt_reasoner.md` |
| **Batch API** | Discounts async, non-interactive bulk jobs. | `routing/model_tree.json#budget_guards`, `brain-stack/batch/` |
| ~~Re-tiered billing~~ | **Not a thing.** You're billed for the model that runs, at its rate. No amount of scaffolding changes that. | rejected in every spec |

The durable asset is the **artifacts** — routing policy, workflows, playbooks,
standing instructions. Authored once by the strongest model available, they run
on whatever model you have later. That is what survives a lineup or pricing
change — not the authoring model's capability (doesn't transfer) and not a
billing tier (always follows the model that runs).

## Optimization by lever

### 1. Tier-fit routing
- **Default down, escalate up.** Route to the lowest plausible tier; let
  escalation pull work up only on real stall signals. Cheaper *and* usually
  faster.
- **Reserve the top tier.** Target ≤10% of requests; alert at 15%
  (`observability/telemetry_spec.md`). If the share creeps up, the fix is a routing/prompt
  change (a PR), not a bigger budget.
- **Right-size Opus.** Deep work only. A task that's really "format this doc"
  routed to Opus is pure waste — the classifier's job is to catch that.

### 2. Prompt caching
- **Stable prefix first, always.** Global → project → patterns → workflow, then
  the variable goal/constraints/context. Any variable content in the prefix
  breaks caching for every later call.
- **Version, don't mutate.** Bump `WORKFLOW_VERSION` when a workflow changes;
  never silently edit a cached prefix (stale-prefix = correctness bug).
- **Target:** ≥70% cache-hit rate on workflow runs; below that, investigate
  prefix instability before anything else.

### 3. Batch coverage
- **Everything non-interactive that's bulk goes to batch.** Guardian repo
  scans, CompanionBot nightly analytics, any job >20 requests
  (`routing/model_tree.json#budget_guards`).
- Batch + cache compose: batched jobs still reuse the cached prefix.

## Per-project cost profile

| Project | Dominant tier | Batch? | Cache leverage | Top-tier trigger |
|---------|---------------|--------|----------------|------------------|
| CompanionBot | Haiku/Sonnet | Nightly analytics | Persona + project prefix cached | Rare; high-impact only |
| Eli Guardian | Sonnet/Opus | Bulk scans | `net_sec_hardening` prefix cached across findings | Contested finding / cross-system risk |
| Consulting | Opus | Rarely | Engagement + workflow prefix cached | Architecture review, scoping (policy-forced) |
| Site / Dev tools | Sonnet | No | `ui_surface_design` prefix cached | Escalation on build stall |

## Budgeting

- Per-project **daily token ceilings** in the policy store
  (`memory/context_memory_spec.md`). Breach → defer to batch or block
  non-essential work, not a silent overspend.
- **Cost per project/day** on the dashboard; **cost per resolved task** as the
  efficiency metric (falling = optimization working).
- New task = new chat: stale context is silent token spend and pollutes routing.

## Quarterly review

Driven by the feedback loop (`observability/telemetry_spec.md`):
1. Top-tier share within target? If not, which routes misfired → PR.
2. Cache-hit rate ≥70%? If not, which prefixes are unstable → PR.
3. Batch coverage complete? Any bulk job still running interactively → PR.
4. Cost per resolved task trend — up or down, and why.

Optimization is a reviewed, versioned process against this repo — not a
one-time setting.
