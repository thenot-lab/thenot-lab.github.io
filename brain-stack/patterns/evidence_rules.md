# evidence_rules.md — What Counts as Justification

A recommendation without evidence is a guess. These rules define what the model
must attach to a claim before it's allowed to stand.

## The rule

Every claim of capability or quality — "this works", "this is secure", "this is
fast", "this scales", "this is cheaper" — must carry at least one of:

1. **A concrete artifact** — a config snippet, command, code skeleton, or schema
   that demonstrates the claim.
2. **A worked example** — inputs → expected output showing the claim holds.
3. **An explicit context reference** — "per the constraint that …", "given the
   provided topology …", "because the spec states …".
4. **A named assumption** — if none of the above exist, state the assumption the
   claim depends on and label it `unverified`.

If a claim can carry none of these, it must be **downgraded** (from `certain`
to `likely`/`unverified`) or **dropped**.

## Security-specific

Classify every security claim by phase, and require phase-appropriate evidence:

- **Prevention** — the specific config/policy change and the attack it blocks.
- **Detection** — signal + threshold + action (a detection with no action is
  incomplete).
- **Response** — the ordered, executable containment/remediation steps.
- **Recovery** — the restore path and how integrity is verified afterward.

A security answer that only covers prevention triggers the `prevention-only`
failure mode.

## Cost-specific

Any "cheaper" claim must name the *mechanism*: fewer tokens, cached prefix,
batch discount, smaller model, or shorter output. "It's cheaper" with no
mechanism is not evidence. Claims that cost drops without any of these
mechanisms (e.g. "billed at a different tier") are **false-premise** — reject
per `failure_modes.md`.

## Anti-pattern

Do **not** cite the scaffolding itself as evidence ("this is right because the
skeleton says so"). The skeleton structures reasoning; it does not substitute
for it. Evidence points at the world (configs, examples, context), not at these
files.
