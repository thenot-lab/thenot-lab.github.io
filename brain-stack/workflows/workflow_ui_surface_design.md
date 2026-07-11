# workflow_ui_surface_design.md — UI Surface Design

- **Workflow id:** `ui_surface_design`
- **Version:** 2.0
- **Project:** dominion
- **Skeleton:** Design
- **Decomposition:** ui_surface
- **Tradeoff pattern:** architecture_tradeoff_table

## Input schema

```json
{
  "goal": "string — the surface to design",
  "mode": "plan | analysis",
  "user": "string — who uses it, in what context",
  "job": "string — what they're trying to accomplish",
  "constraints": ["string — platform, framework, brand, a11y, perf budget"],
  "existing": "string — current surface/system to fit into, if any"
}
```

## Output schema

```json
{
  "user_and_job": "string",
  "state_model": [{ "state": "string", "trigger": "string", "next": ["state"] }],
  "information_architecture": "string",
  "interaction_flow": { "primary_path": ["string"], "secondary_paths": [["string"]], "escape_hatches": ["string"] },
  "edge_surfaces": [{ "case": "empty|error|latency|denied|narrow-viewport", "handling": "string" }],
  "accessibility_perf": { "keyboard": "string", "contrast": "string", "labels": "string", "budget": "string" },
  "option_tradeoffs": "architecture_tradeoff_table (filled)",
  "recommendation": "string",
  "assumptions": ["string"]
}
```

## Steps

1. **User + job** (goal: ground the design; method: tree node 1; verify: the
   job is a concrete task, not "use the app").
2. **State model** (goal: enumerate all states; method: tree node 2; verify:
   loading, empty, error, and success all present — else `state-gap`; output
   shape matches the schema — else `schema-drift`).
3. **Information architecture** (goal: hierarchy of what's shown; verify:
   primary action is unambiguous).
4. **Interaction flow** (goal: primary + secondary paths + escape hatches;
   verify: every destructive action has an undo or confirm).
5. **Edge & failure surfaces** (goal: empty/error/latency/denied/narrow;
   verify: no state from step 2 is left without handling).
6. **Options at load-bearing joints** (goal: ≥2 options where a choice matters;
   method: fill `architecture_tradeoff_table`; verify: ≥2 genuinely distinct
   options presented — else `single-option`; the recommendation cites specific
   table cells — else `evidence-gap`).

## Error handling

- Unknown framework/brand → assume a neutral, accessible default and label it.
- Conflicting constraints (e.g. dense data + mobile-first) → surface as a
  tradeoff, offer options, don't silently pick.

## Evidence hooks

Apply `evidence_rules.md` at step 6: the recommendation references specific
tradeoff-table cells and the stated constraints.
