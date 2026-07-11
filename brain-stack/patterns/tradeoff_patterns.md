# tradeoff_patterns.md — Reusable Comparison Tables

Rules:
- **Fill the table before recommending.** The recommendation must come *after*
  the table, not before.
- **One row per option.** Every option from the skeleton's step 2 appears.
- **Tie the choice back to the table.** The recommendation cites the specific
  cells (columns) that drove it.
- Rate cells concretely — a value, a range, or Low/Med/High with a reason —
  never a bare adjective.

---

## `architecture_tradeoff_table`

| Option | Complexity | Cost | Risk | Flexibility | Time-to-implement |
|--------|-----------|------|------|-------------|-------------------|
| A: … | | | | | |
| B: … | | | | | |
| C: … | | | | | |

- **Complexity** — moving parts, operational burden.
- **Cost** — money + tokens + maintenance.
- **Risk** — likelihood × blast radius if it goes wrong.
- **Flexibility** — how well it adapts to changed requirements.
- **Time-to-implement** — realistic effort to first working version.

---

## `security_control_table`

For choosing between security measures.

| Control | Phase (prevent/detect/respond/recover) | Coverage (threats closed) | Cost/effort | Home-executable? | False-positive risk |
|---------|----------------------------------------|---------------------------|-------------|------------------|---------------------|
| … | | | | | |

Rule: the recommended set must cover **all four phases** or explicitly scope one
out. Any control marked *not* home-executable must be flagged, not silently
recommended.

---

## `model_cost_table`

For picking a model/config for a task class. This is the *legitimate* cost
lever — it compares real rates, not billing tricks.

| Option (model + config) | Capability fit | $/1M input | $/1M output | Cache-eligible prefix? | Batch-eligible? | Latency |
|-------------------------|----------------|-----------|-------------|------------------------|-----------------|---------|
| … | | | | | | |

Rules:
- Fill actual current rates from the provider's pricing at build time — do not
  guess; mark `unverified` if not checked.
- Prefer the cheapest option whose **capability fit** clears the task bar.
- Note caching (stable prefix reused) and batch (non-interactive discount) as
  the only real cost reductions — neither changes which model is billed.
