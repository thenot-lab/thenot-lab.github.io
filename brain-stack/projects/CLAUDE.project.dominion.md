# CLAUDE.project.dominion.md — Project Context: Dominion Labs

Loaded after `CLAUDE.global.md` for any task with `project: dominion`.
Layers project-specific domain, assumptions, and reasoning tweaks on top of the
global substrate.

## Domain

Dominion Labs — an independent software lab. Real surfaces this project reasons
about:

- **CompanionBot** — custom AI personas on Telegram: persistent memory,
  analytics, multi-model routing.
- **Eli Guardian** — zero-dependency Python security scanner; STRIDE threat
  modeling, semantic analysis.
- **Security Consulting** — threat modeling, penetration testing, security
  architecture reviews.
- **Custom Development / Dev Tools / AI Integration** — full-stack Python +
  TypeScript, Claude/other-model integrations, DevOps.

Cross-cutting themes: agentic workspaces, UI surfaces, and home/small-team
network security.

## Assumptions

- The user is technical and wants **architecture, not fluff**. Skip 101-level
  explanation unless asked.
- Deliverables must be **home/small-team executable** — no assumed SOC,
  enterprise SIEM, or paid tooling unless the user names it.
- Products favor **zero/low dependency** and **simplicity** — match that when
  proposing designs.
- Budget-conscious: prefer free/OSS and self-hosted before paid SaaS; when
  recommending a paid model/API, note the cost lever (caching, batch, tier).

## Success criteria

- Designs are **coherent across surfaces** (bot, scanner, consulting, web).
- Workflows are **automatable** — expressible as repeatable steps or scripts.
- Security work distinguishes **prevent / detect / respond / recover**.
- Every recommendation ties back to an explicit constraint or piece of context.

## Reasoning tweaks

- **UI / surface work:** prioritize interaction clarity and state management.
  Name the states, the transitions, and the failure/empty states before
  styling. Accessibility and mobile are constraints, not extras.
- **Security work:** order the reasoning **detect → isolate → remediate →
  harden**. Lead with what you can *observe*, then containment, then fix, then
  prevention. Reject prevention-only plans (see `failure_modes.md`).
- **Bot / agent work:** be explicit about memory scope, model routing, and
  cost per conversation. Multi-model = state the routing rule, not just "picks
  the best model".
