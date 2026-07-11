# failure_modes.md — Known Reasoning Errors + Mitigations

Checked at the end of every workflow (the "check failure modes" step). Each
entry is a named error, how to detect it, and the mitigation that must be
applied before output is emitted.

| id | Failure mode | Detection | Mitigation |
|----|--------------|-----------|------------|
| `constraint-overfit` | Optimizing one constraint (usually cost or simplicity) so hard that others silently break. | Re-read the constraints list. Is any constraint unaddressed in the recommendation? | Map each recommendation line to the constraint(s) it satisfies. Any unmapped constraint = incomplete. |
| `monitoring-handwave` | "We'll monitor it" / "add alerting" with no concrete signal, threshold, or action. | Search output for "monitor", "observe", "alert", "watch". | Replace each with: **signal** (what metric/log), **threshold** (the trigger value), **action** (what happens when it fires). |
| `non-home-executable` | A plan that quietly assumes enterprise infra, a security team, or paid tooling the user doesn't have. | For each step, ask: can the user run this tonight with what they own? | Rewrite the step with home-grade tooling, or explicitly flag it as "requires X" so the user can decide. |
| `single-option` | Presenting one path as if no alternative exists. | Count distinct options offered. | Require ≥2 genuinely different options with a tradeoff table before recommending. |
| `evidence-gap` | A claim of "this works / is secure / is fast" with no config, example, or reference. | Flag every capability/quality claim. | Attach evidence per `patterns/evidence_rules.md`, or downgrade the claim's certainty label. |
| `false-premise-accept` | Building on a user premise that is factually wrong (e.g. "this reduces billing tier"). | Does the plan depend on a mechanism that must be true for the goal to hold? Is it actually true? | Name the false premise, explain why it fails, and deliver the version that achieves the real underlying goal. |
| `prevention-only` | A security answer that only prevents, ignoring detection/response/recovery. | Classify each measure into prevent / detect / respond / recover. | Ensure all four phases are represented, or state explicitly why one is out of scope. |
| `schema-drift` | Output that doesn't match the workflow's declared output schema. | Diff output shape against the schema. | Reformat to the schema, or note the deviation and why. |
| `state-gap` | A state model that omits a lifecycle state (loading, empty, error, success) or leaves a listed state unhandled — the output can be schema-valid and still incomplete. | Compare the emitted states against the required lifecycle set and the edge-surface handling list. | Enumerate the missing states and their handling, or scope them out explicitly with a reason. |

## Usage

Before emitting output, walk this table top to bottom. For each row, either
confirm it does not apply or apply the mitigation. Do not skip rows silently.
