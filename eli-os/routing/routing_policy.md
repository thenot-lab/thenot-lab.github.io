# routing_policy.md — The Dominion Model Tree

Human-readable version of `model_tree.json`: the decision tree, per-project
routing, and the entry prompt pattern for each tier.

## The decision tree

```text
Does the task need more than a quick answer?
├─ NO ─ Need max speed / minimal tokens?
│       ├─ YES → HAIKU 4.5   (chat, no files; web search on)
│       └─ NO  → SONNET 5    (simple structured tasks; connectors)
└─ YES ─ Is this the hardest, most ambitious work?
        ├─ NO  → OPUS 4.8    (deep work; effort HIGH always; skills in projects)
        └─ YES → TOP TIER    (complex multi-workflow, deep research, hard reasoning)
```

Two standing rules from the tree:
- **When Opus gets stuck, escalate.** The top tier is primarily an *escalation
  target*, not a default route. Save it for the ~10% of tasks that need it.
- **New task = new chat.** Don't drag unrelated context; it costs tokens and
  pollutes routing signals. Durable context belongs in memory, not the thread.

## Per-tier entry prompt patterns

Stable patterns — keep them verbatim so prefixes cache (see
`brain-stack/cache/cache_key_schema.md`).

**Haiku — quick interactive:**
> "I want to [desired results] with [constraints]. Ask me questions before you
> start."

**Sonnet — quick task:**
> "You are a [role]. [Task] this [input]. Keep it under [length]. Tone:
> [casual/formal]. No preamble. Just the output."

**Opus — cowork / deep work:**
> "[Goal + context]. DO NOT start yet. Ask me clarifying questions so we can
> refine the approach step by step."
> (Effort high. Use skills/workflows from brain-stack in projects.)

**Top tier — decision engine (the five-part frame):**
1. **The reason** — "I'm working on [X] for [who]. They need [what the output enables]."
2. **The goal** — "Goal: [outcome]. Here's everything I know: [context]." (outcome, not steps)
3. **The interview** *(interactive requests only)* — "Before you start, ask me
   everything you need to get this right." Non-interactive runs — batch jobs
   and automated escalations (e.g. Guardian contested findings) — must never
   stall waiting on a user: skip the interview, proceed on explicit **labeled
   assumptions**, and return missing inputs as `open_questions` in the output.
4. **The boundary** — "Do the simplest thing that works. Only pause for me on irreversible actions."
5. **The proof** — "Only report work you can point to evidence for. Lead with the outcome."

Compressed one-liner:
> "Here is my goal: [goal]. Here are my constraints: [constraints]. Think
> through the tradeoffs before answering, propose 2–3 approaches, and
> recommend one with your reasoning."

This is brain-stack's `Problem → Options → Tradeoffs → Recommendation`
skeleton in prompt form — the two are kept in sync deliberately.

## Per-project routing

### CompanionBot (Telegram)

| Task | Tier | Notes |
|------|------|-------|
| Persona small talk, quick Q&A | Haiku | web search on for factual |
| Summarize/format/operate on a message or doc | Sonnet | connector default |
| "Plan my week", code help, multi-step asks | Opus | cowork pattern |
| Anything high-impact (rare in chat) | Top | escalation only |
| Nightly analytics over conversations | Sonnet **batch** | never interactive |

### Eli Guardian (scanner)

| Task | Tier | Notes |
|------|------|-------|
| Finding triage + dedup | Haiku | cheap, high volume |
| STRIDE classification of findings | Sonnet | structured, schema-bound |
| Semantic code-path analysis, exploit-chain reasoning | Opus | deep work |
| Contested finding (models disagree) / cross-system risk verdict | Top | escalation trigger: conflicting outputs |
| Bulk repo scans | Sonnet **batch** | budget guard requires batch |

### Security Consulting

| Task | Tier | Notes |
|------|------|-------|
| Report drafting, formatting, client comms | Sonnet | |
| Threat models, remediation plans | Opus | via `net_sec_hardening` workflow |
| Architecture reviews, engagement scoping | Top | policy store forces top-tier review |

### Site / Dev tools

| Task | Tier | Notes |
|------|------|-------|
| Copy edits, small fixes | Sonnet | |
| UI/surface design | Opus | via `ui_surface_design` workflow |
| Build/debug sessions | Opus | escalate on stall |

## Escalation ladder

```text
haiku ──(needs structure)──▶ sonnet ──(needs depth)──▶ opus ──(stalls)──▶ top
                                                        │
   triggers: confidence < 0.6 · ≥3 iterations no convergence ·
             conflicting outputs · hard-constraint conflict
                                                        │
   handoff: full trace + short-term context + relevant memory
   top tier: override / refine / restructure graph → work returns down-tier
```

When escalating, always hand up the *trace*, not a summary — summaries hide
exactly the contradictions the top tier needs. For interactive requests the
top tier may then interview the user; automated escalations proceed on labeled
assumptions per the interview rule above.
