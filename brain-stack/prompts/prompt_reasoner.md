# prompt_reasoner.md — Cache-Friendly Prompt Skeleton

The structure never changes; only the `[SLOT]` values change per call. Keeping
the structure and the leading content stable is what makes the prefix
**cacheable** (see `cache/cache_key_schema.md`).

Assemble in this order so everything stable comes first and the variable
payload comes last:

```text
┌─ STABLE PREFIX (cacheable) ───────────────────────────────┐
│ 1. CLAUDE.global.md          (verbatim)                   │
│ 2. projects/CLAUDE.project.[PROJECT_ID].md   (verbatim)   │
│ 3. patterns: the skeleton, decomposition tree, tradeoff   │
│    pattern, and evidence_rules named by the workflow      │
│ 4. workflows/workflow_[WORKFLOW_ID].md       (verbatim)   │
├─ VARIABLE SUFFIX (changes every call) ────────────────────┤
│ 5. The filled USER block below                            │
└───────────────────────────────────────────────────────────┘
```

## SYSTEM block

```text
You are the [AGENT_ROLE] for project [PROJECT_ID].
Follow workflow [WORKFLOW_ID] v[WORKFLOW_VERSION].
Apply skeleton [SKELETON_NAME] and decomposition [DECOMP_NAME].
Obey the evidence rules and check the failure modes before emitting output.
Emit output strictly in the workflow's output schema.
```

The SYSTEM block sits at the top of the **stable prefix**: its slots bind once
per (project, workflow, role) pairing, not per call. Only the USER block below
varies per call.

## USER block

```text
Goal: [GOAL]
Mode: [MODE]                      # plan | analysis
Constraints:
[CONSTRAINTS]                     # bullet list; these are hard unless marked soft
Context:
[CONTEXT_BLOB]                    # topology, current state, existing surface, etc.
```

## Slot reference

| Slot | Source |
|------|--------|
| `[AGENT_ROLE]` | caller (e.g. `reasoner`, `architect`, `auditor`) |
| `[PROJECT_ID]` | task (e.g. `dominion`) |
| `[WORKFLOW_ID]` / `[WORKFLOW_VERSION]` | `workflow_index.json` + workflow spec |
| `[SKELETON_NAME]` / `[DECOMP_NAME]` | `workflow_index.json` |
| `[GOAL]` / `[MODE]` / `[CONSTRAINTS]` / `[CONTEXT_BLOB]` | the actual request |

## Why the order matters

Prompt caching charges full input rate for the prefix once, then a reduced rate
on cache hits within the cache window. If variable content (the goal/context)
appears *before* stable content, the prefix changes every call and never
caches. Always: stable first, variable last.
