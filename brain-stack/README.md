# Brain Stack

A reusable reasoning-scaffolding system for LLM agents. It is a set of plain
text/JSON files — global rules, project context, named reasoning patterns,
workflow specs, prompt skeletons, and cost-control conventions — that you load
into a model's context so its output is structured, evidence-backed, and
consistent across runs.

It is **model-agnostic**. Point it at whatever model you have access to
(Claude Opus, Sonnet, Haiku, or anything else). Better scaffolding produces
better output from any model.

---

## What this does (and what it does not)

This directory delivers the buildable, genuinely useful core of the "Fable →
Opus brain stack" idea. Some claims in the original design don't hold up, so
read this before relying on it:

**What it actually does**
- Improves output quality on **any** model by giving it explicit reasoning
  frames, decomposition trees, tradeoff tables, and evidence rules.
- Makes runs **repeatable**: the same task hits the same skeleton and schema,
  so outputs are comparable and reviewable.
- Cuts input cost through **prompt caching** — the stable prefix (global rules,
  project context, skeletons) is cached and reused, so you pay full input rate
  only once per cache window.
- Cuts throughput cost through the **Batch API** — long, non-interactive jobs
  run at a discount.

**What it does NOT do — and why the original framing was wrong**
- **It cannot make one model "behave like" a more capable one.** Feeding
  Opus a prompt authored by a stronger model gives you *better-prompted Opus*,
  not the stronger model's capability. Scaffolding raises the floor of any
  model; it does not transfer another model's ceiling.
- **It does not change billing.** You are billed for the model that actually
  processes the tokens, at that model's rate, no matter who or what wrote the
  prompt. There is no "author attribution" in billing, and no way to have work
  done by one tier and billed at another. Caching and batch are the *only*
  real levers here, and both are legitimate, documented features — they lower
  cost by reducing/discounting tokens, not by re-tiering them.
- **It does not let you "ride through a model cutoff."** If a model is
  deprecated or access ends, saved prompts it once wrote do not restore access
  to its reasoning. What survives a cutoff is exactly this: the *artifacts*
  (rules, skeletons, schemas), which then run on whatever model is available.

Bottom line: keep the scaffolding, drop the billing/capability-transfer
premise. The value is real; the shortcut it was wrapped in is not.

---

## Layout

```text
brain-stack/
  CLAUDE.global.md            Global reasoning substrate (identity, core rules, style, safety)
  failure_modes.md            Known reasoning errors + mitigations
  projects/
    CLAUDE.project.dominion.md   Project-specific context (Dominion Labs)
  patterns/
    reasoning_skeletons.md    Named step-by-step reasoning frames
    decomposition_trees.md    Per-domain problem breakdowns
    tradeoff_patterns.md      Reusable comparison tables + rules
    evidence_rules.md         What counts as justification
  workflows/
    workflow_index.json       Binds each task type to its substrate pieces
    workflow_net_sec_hardening.md
    workflow_ui_surface_design.md
  prompts/
    prompt_reasoner.md        Stable, cache-friendly prompt skeleton
  cache/
    cache_key_schema.md       Deterministic cache-key convention
  batch/
    batch_net_sec_hardening.json  Batch job template
  boot/
    boot_sequence.md          How to assemble a call from these files
```

## How to use it

1. Pick the task type (e.g. `net_sec_hardening`).
2. Look it up in `workflows/workflow_index.json` to get its skeleton,
   decomposition tree, tradeoff pattern, and failure modes.
3. Assemble the prompt using `prompts/prompt_reasoner.md`, in this order so the
   stable part is a cacheable prefix: `CLAUDE.global.md` → project file →
   pattern files → workflow spec → (then the variable goal/constraints/context).
4. Call your model. Validate the output against the workflow's output schema.

See `boot/boot_sequence.md` for the concrete assembly order and
`cache/cache_key_schema.md` for how to key the cache.
