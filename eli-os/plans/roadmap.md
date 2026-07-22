# Eli OS v2 — Build Roadmap

Phased plan from the current specs to a running system. Each phase has a
concrete deliverable and an acceptance check. Home-executable throughout:
single admin, one box, zero/low dependency.

## Phase 0 — Specs (this PR) ✅

- **Deliverable:** the `eli-os/` specification set + the `brain-stack/`
  substrate it builds on.
- **Acceptance:** every layer (gateway, routing, protocol, memory,
  orchestration, observability) has a spec with schemas; JSON validates;
  cross-references resolve.

## Phase 1 — Gateway skeleton + routing ✅ (`gateway/`)

- **Deliverable:** a stateless gateway service (FastAPI or similar) that
  accepts a request, runs the classifier, applies `routing/model_tree.json`,
  calls the chosen model endpoint, and returns the result. Load routing from
  the JSON so policy changes are config, not code.
- **Acceptance:** a request with each task type routes to the tier the policy
  predicts; every call writes a telemetry record
  (`observability/telemetry_spec.md` schema).

## Phase 2 — Memory + caching ✅ (`memory/`)

- **Deliverable:** SQLite-backed short-term store; SQLite+vec long-term store
  with write-back of decisions/playbooks; the profile/policy store seeded from
  versioned YAML. Prompt assembly uses the brain-stack cache order.
- **Acceptance:** escalation handoff carries full short-term context (not a
  summary); cache-hit rate on a repeated workflow ≥70%.

## Phase 3 — Orchestration (task graph) ✅ (`orchestration/`)

- **Deliverable:** the DAG engine (`orchestration/task_graph_spec.md`): plan → execute →
  aggregate → review, with concurrency, retries, and node escalation.
- **Acceptance:** the Guardian worked example runs end to end; the top-tier
  node (n4) is *skipped* when its escalation condition isn't met, and *runs*
  when it is.

## Phase 4 — Eli Protocol wired into Guardian ✅ (`protocol/guardian.py`)

- **Deliverable:** Guardian findings flow triage → STRIDE → semantic → verdict
  → report through the tiers; output in the `net_sec_hardening` schema with
  evidence per finding and a protocol-phase tag per fix; playbooks in
  `protocol/` are loadable.
- **Acceptance:** a scan produces a report where every finding carries
  evidence and every remediation is tagged prevent/detect/respond/recover;
  a contested finding escalates to the top tier and is logged.

## Phase 5 — Guardrails + self-defense ✅ (`observability/guardrails.py`)

- **Deliverable:** RBAC, content filter, prompt-injection screen on
  tool/connector output, and the irreversible-action gate — all enforced in the
  gateway; guardrail outcomes in telemetry.
- **Acceptance:** an injected instruction in fetched content cannot trigger an
  action tool without the gate; an irreversible action pauses for confirmation
  with blast radius stated.

## Phase 6 — Feedback loop + dashboard ✅ (`observability/dashboard.py` + `review.py`)

- **Deliverable:** the observability dashboard (cost/day, top-tier share,
  cache-hit, escalation mix, guardrail flags) + the weekly top-tier review that
  proposes routing/prompt changes as PRs.
- **Acceptance:** the review produces at least one concrete, reviewed routing/
  prompt PR from real telemetry; top-tier share stays within target.

## Dependency order

```text
Phase 0 ─▶ 1 ─▶ 2 ─▶ 3 ─▶ 4
               └────────▶ 5 ─▶ 6
```

Phase 5 (guardrails) can start once the gateway (1) exists; everything else is
linear. Ship Phase 1–2 before wiring Guardian (4) so routing, memory, and
caching are proven before the first real product rides on them.

## Status — all phases implemented

Every phase now has a runnable, stdlib-only implementation with an offline
test suite encoding its acceptance criteria (77 tests total). `eli-os/demo.py`
runs the whole stack end to end without an API key: gateway routing →
memory + escalation handoff → Guardian scan through the task graph →
guardrails gate → dashboard + feedback review over the shared telemetry log.

| Phase | Module(s) | Tests |
|-------|-----------|-------|
| 1 | `gateway/gateway.py` | 19 |
| 2 | `memory/memory.py`, `memory/prompt_assembly.py` | 13 |
| 3 | `orchestration/task_graph.py` | 11 |
| 4 | `protocol/guardian.py` + `playbooks/` | 9 |
| 5 | `observability/guardrails.py` | 13 |
| 6 | `observability/dashboard.py`, `observability/review.py` | 12 |

The models are called through the Anthropic Messages API (`gateway.call_model`);
everything else — routing, memory, orchestration, scanning, guardrails,
telemetry, dashboard — runs locally with no third-party dependencies.

## Out of scope for v2

- Multi-box / autoscaling deployment (home-scale is the target).
- Fine-tuning or self-hosting model weights.
- Any mechanism claiming to change billing tier — it does not exist.
