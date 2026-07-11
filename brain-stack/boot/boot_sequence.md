# boot_sequence.md — Assembling a Call

The deterministic sequence for turning a raw task into a model call using this
stack. This is the "execution layer": the model does not improvise structure —
it executes what these files specify.

## Boot (once per task)

1. **Load global.** Read `CLAUDE.global.md`.
2. **Load project.** From the task's `project`, read
   `projects/CLAUDE.project.<PROJECT_ID>.md`.
3. **Select the workflow.** Look the task type up in
   `workflows/workflow_index.json` to get: `skeleton`, `decomposition`,
   `tradeoff_pattern`, `evidence_rules`, `failure_modes`, and the workflow
   `spec` path.
4. **Load the patterns** named in step 3 from `patterns/`, and the workflow
   spec from `workflows/`.
5. **Load the prompt skeleton** `prompts/prompt_reasoner.md`.

## Execute (per task)

1. **Compute the cache key** per `cache/cache_key_schema.md`. If a cached
   prefix exists for that key, reuse it; otherwise assemble the stable prefix
   (steps 1–4 above, in order) and cache it.
2. **Bind inputs** into the prompt skeleton's variable suffix: `[GOAL]`,
   `[MODE]`, `[CONSTRAINTS]`, `[CONTEXT_BLOB]`, and the SYSTEM-block slots.
3. **Call the model** with `prefix + suffix`.
4. **The model then:**
   - frames the problem with the named skeleton,
   - walks the named decomposition tree,
   - fills the named tradeoff pattern,
   - applies `evidence_rules.md`,
   - walks `failure_modes.md` and applies any mitigation that fires,
   - emits output in the workflow's output schema.
5. **Validate** the output against the workflow's output schema. On mismatch,
   the `schema-drift` failure mode applies — reformat and re-emit.

## Routing

- Point every call at whatever model you have access to. The stack is
  model-agnostic; nothing here depends on a specific model being available.
- Route "hard" tasks to **this stack** (workflow + skeleton), not to a bare
  chat. The value is the structure, and the structure is portable.
- Rewrite a raw chat request into: *select workflow → load prefix → bind
  suffix → run → validate*.

## What "runs" here vs what doesn't

- **Runs:** the artifacts in this directory, on any model, indefinitely.
- **Does not run:** any assumption that these files change billing, transfer
  one model's capability to another, or preserve access to a retired model.
  See `README.md` → "What it does NOT do." Keep the scaffolding; drop the myth.
