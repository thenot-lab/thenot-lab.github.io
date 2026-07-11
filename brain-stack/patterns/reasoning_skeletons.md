# reasoning_skeletons.md — Named Reasoning Frames

Each skeleton is an ordered set of steps the model walks explicitly. A workflow
names the skeleton it uses; the model must produce a section per step.

---

## `Problem → Options → Tradeoffs → Recommendation`

The default design/decision skeleton.

1. **Frame the problem.** State the goal, constraints, and assumptions. Pull
   constraints to the top; nothing downstream may violate them.
2. **Generate options.** Produce 3–5 genuinely distinct options. Distinct =
   different mechanism, not the same idea reworded.
3. **Analyze tradeoffs.** Fill the applicable table from
   `tradeoff_patterns.md` (columns: complexity, cost, risk, flexibility,
   time-to-implement). One row per option.
4. **Recommend one option.** Commit to a single choice.
5. **Tie to evidence.** Justify the choice against the table and the
   constraints, referencing specific context (see `evidence_rules.md`).

---

## `Diagnostic` (troubleshooting / incident)

1. **Symptoms.** What is observed, precisely. Separate observation from
   inference.
2. **Hypotheses.** 2–4 candidate causes, each falsifiable.
3. **Discriminating tests.** For each hypothesis, the cheapest observation that
   confirms or kills it. Order by cost ascending.
4. **Diagnosis.** The surviving hypothesis, with the evidence that confirmed it.
5. **Fix + verification.** The remediation and how you'll confirm it worked
   (signal + expected value).

---

## `Design` (build something new)

1. **Requirements + constraints.** Functional and non-functional; hard vs soft.
2. **Interfaces / contracts.** Inputs, outputs, state, and boundaries first.
3. **Component decomposition.** Walk the relevant tree in
   `decomposition_trees.md`.
4. **Options at the risky joints.** Where a decision is load-bearing, branch
   into options + tradeoffs.
5. **Concrete artifact.** Schema, config, file skeleton, or ordered build steps.
6. **Failure/edge handling.** Empty, error, and abuse cases named explicitly.

---

## `Security audit`

Ordered detect → isolate → remediate → harden (Dominion default).

1. **Asset & topology map.** What exists, what it touches, trust boundaries.
2. **Threat model.** STRIDE (or per workflow) against the boundaries.
3. **Detection design.** Per threat: signal, threshold, action. No handwaving.
4. **Isolation / containment.** How to limit blast radius when a threat fires.
5. **Remediation playbook.** Ordered steps to remove the threat.
6. **Hardening baseline.** Preventive changes, mapped to the threats they close.

Every measure is tagged **prevent / detect / respond / recover**; all four must
appear or be explicitly scoped out.
