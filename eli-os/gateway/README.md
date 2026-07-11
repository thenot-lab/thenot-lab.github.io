# Eli OS Gateway — Phase 1

The gateway skeleton from the roadmap: a stateless service that accepts a
request, runs the classifier, applies `../routing/model_tree.json` (loaded as
config — policy changes need no code change), calls the chosen Claude model,
and writes a telemetry record per `../observability/telemetry_spec.md`.

**Zero dependencies.** Python 3.9+ stdlib only, raw HTTP against
`api.anthropic.com` — the Dominion home-executable rule applied to our own
infrastructure. Swapping in the official `anthropic` SDK later is a drop-in
change confined to `call_model()`.

## Run it

```sh
# Routing decision only — no API key needed, nothing leaves the machine
python3 gateway.py route '{"project": "eli_guardian", "task_type": "semantic_code_analysis"}'

# Full call (needs ANTHROPIC_API_KEY)
python3 gateway.py complete '{"task_type": "chat", "prompt": "hello"}'

# HTTP service
python3 gateway.py serve --port 8484
curl -s localhost:8484/healthz
curl -s -X POST localhost:8484/route -d '{"task_type": "architecture_decision"}'
curl -s -X POST localhost:8484/complete -d '{"task_type": "chat", "prompt": "hi", "dry_run": true}'
```

## Tests (offline, no key required)

```sh
cd eli-os/gateway && python3 test_gateway.py
```

The tests are the Phase 1 acceptance criteria: every project-override and rule
in `model_tree.json` routes to the tier the policy predicts, and every call
writes a schema-shaped telemetry record.

## What it implements

| Spec | Where |
|------|-------|
| Classifier (explicit metadata wins, keyword fallback) | `classify()` |
| Router: project overrides → rules top-down → default | `route()` |
| Escalation triggers with canonical names | `check_escalation()` |
| Budget guard: top-tier share alert at >15% | `top_tier_share()` + `_finish()` |
| Per-tier model config (thinking / effort / fallbacks) | `build_payload()` |
| Model call with retry on 429/5xx, `retry-after` honored | `call_model()` |
| Telemetry: `model_call` + `gate` JSONL records | `model_call_record()` / `gate_record()` |

Per-tier API behavior baked in (from the current Claude API surface):

- **Top tier (`claude-fable-5`)** — thinking is always on, so no `thinking`
  param is sent; **server-side refusal fallback to `claude-opus-4-8` is enabled
  by default** (beta `server-side-fallback-2026-06-01`): Fable's safety
  classifiers can decline benign-adjacent security work, which matters for a
  security-focused shop, and the fallback re-serves the request in the same
  call. `stop_reason: "refusal"` is still checked before reading content.
- **Opus / Sonnet** — `thinking: {"type": "adaptive"}` + `output_config.effort:
  "high"` explicitly (omitting `thinking` on Opus runs without thinking).
- **Haiku** — no thinking/effort params (not supported on that tier).
- **System prompt** — sent as a text block with `cache_control: {"type":
  "ephemeral"}`: callers pass the assembled stable prefix (see
  `../../brain-stack/prompts/prompt_reasoner.md`) and repeated calls hit the
  prompt cache.

## Not in Phase 1 (by design — see `../plans/roadmap.md`)

Memory stores and full cache-key bookkeeping (Phase 2), the task-graph engine
(Phase 3), Guardian wiring (Phase 4), RBAC/injection screening/irreversible
gate enforcement (Phase 5), dashboards (Phase 6). The `gate` telemetry record
type exists now so Phase 5 has its audit-trail shape ready.
