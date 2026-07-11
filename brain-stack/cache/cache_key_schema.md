# cache_key_schema.md — Deterministic Cache-Key Convention

A stable, human-readable key that identifies a cacheable prompt prefix. Same
inputs → same key → same cached prefix reused.

## Key formula

```text
cache_key = [
  "project:"  + PROJECT_ID,
  "workflow:" + WORKFLOW_ID,
  "version:"  + WORKFLOW_VERSION,
  "role:"     + AGENT_ROLE
].join("|")
```

## Examples

```text
project:dominion|workflow:net_sec_hardening|version:1.0|role:reasoner
project:dominion|workflow:ui_surface_design|version:2.0|role:architect
```

## Rules

- The key covers **only the stable prefix** (global + project + patterns +
  workflow spec, plus the SYSTEM block with the role bound). It must **not**
  include the goal, mode, constraints, or context — those are the variable
  suffix and change every call. (`AGENT_ROLE` stays in the key because the
  SYSTEM block binds it into the prefix — one prefix per workflow + role
  pairing. `MODE` lives in the USER suffix; keying on it would split identical
  prefixes and cut cache reuse.)
- Bump `WORKFLOW_VERSION` whenever the workflow spec or any pattern it pulls
  changes. A stale prefix served under an old key is a correctness bug, not a
  cost saving.
- Two calls with the same key are guaranteed to share the same prefix bytes.
  If they don't, the prefix wasn't actually stable — fix the assembly order
  (`prompts/prompt_reasoner.md`), don't work around it in the key.

## How this maps to a real provider

The key is *your* bookkeeping label. On the Anthropic API, caching is turned on
by marking the end of the stable prefix with a `cache_control` breakpoint on
the last stable block; the API then reuses it on subsequent calls within the
cache window. Use this `cache_key` string as the log/label for which prefix you
expected to hit, so cache misses are debuggable.

### Honest note on what caching buys

Caching reduces the **input token price of the repeated prefix** within the
cache window. That is the entire benefit. It does **not** change which model
runs, does not change the output price, and does not re-tier billing. It's a
real discount on repeated input — nothing more, nothing less.
