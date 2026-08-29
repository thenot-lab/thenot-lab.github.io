# AUDIT — "enhanced peek / work / files / research" — 2026-08-29

Scope: find every artifact matching the brief, list it, and give a completion
status backed by something that was actually run — not by what a README claims.
Every ✅ below has a command, a CI run, or a commit behind it. Anything I could
not execute in this container is marked **UNVERIFIED**, not "done".

## 0. Resolving the terms

`grep -rniE "enhanced peek|peek"` over this repo returns **zero hits**. The term
resolves to a *separate repository*: **`thenot-lab/EnhancedPeek`** (private,
last push 2026-08-14). "Research" resolves to two more:
`research-vision-collaboration` and `eli-researcher`. All three were attached
and audited. 51 repos exist on the account; the four "workspace" repos are
listed in §6 as matched-but-not-audited.

---

## 1. thenot-lab.github.io — this repo (main @ `fe20837`)

**Present:** 4 landing pages (`index`, `companion_bot`, `eli_guardian`,
`security_consulting`), `eli-os/` (Phases 0–8), `brain-stack/` (reasoning
substrate specs), `handoffs/` (1 file).

**Verified this session:**

| Check | Result |
|---|---|
| 6 unittest suites | **80 tests, all OK** |
| `eli-os/demo.py` end to end | **green** — routing → memory → Guardian → guardrails → dashboard → review |
| Audit branch vs main | `0 0` — identical, nothing to merge |

**Finding — the roadmap's test table is stale.** `eli-os/plans/roadmap.md`
claims 77 tests. Actual count is **80**: orchestration is 13 (table says 11),
guardrails is 14 (table says 13). Under-counted, not over-counted — the code is
ahead of its documentation.

**Finding — no CI in this repo at all.** There is no `.github/` directory. The
77/80 claim and the phase ✅ marks have never been machine-checked on push.

### Unmerged branches

| Branch | State | Call |
|---|---|---|
| `claude/eli-diagnostic-integration-j3ntnq` | 4 commits, 10 files, 1,324 lines — `eli-os/integration/` (context bridge, router ext, Kotlin companion patch). **Verified: 21 tests pass, demo runs offline.** No PR opened. | **Real work, stranded.** Merge it. |
| `eli/readme-stub-2026-08-02` | PR #4 **open** — adds a 26-line root README. main has no README. | Merge or close. |
| `claude/fable-opus-brain-stack-bcyzn5` | Squash-merged as PR #3; branch now sits **681 lines behind main** (lacks Phases 7–8 + the handoff). | Superseded. Safe to delete. |
| `claude/session-handoff-aug-2-dzyqrk` | Identical to main. | Merged. Safe to delete. |

**Finding — two stale status claims contradict the record:**
- The Aug-2 handoff §7 says Phases 7 & 8 are "NOT merged to main; no PR". They
  **are** on main (`554c761`, `746d70e`, `944c308`).
- `eli-os/integration/README.md` (on the unmerged branch, dated 2026-07-23) says
  "The signed APK still needs to be assembled". The Aug-2 handoff §5 records the
  APK **built and verified green** (run 30738991754, 20,408,064 B, sha256
  `7a56197f…8a53ae`). That blocker is cleared; the branch never got the memo.

**Eli OS completion: 8 of 8 phases implemented and offline-verified.** Two
acceptance criteria remain environment-bound: Phase 7 requires the gateway to
run under the service manager *on the Legion box*, and Phase 8's wipe test was
verified offline only, not on a genuinely fresh machine.

---

## 2. EnhancedPeek / "PeekViewer" (main @ `8e593a9`)

12-package TypeScript monorepo on Turborepo — 125 files, **20,851 lines of TS**.
Migrated off .NET MAUI → Android+PWA → this, via PR #7 (merged 2026-08-02).

**Verified this session, from a clean clone:**

| Check | Result |
|---|---|
| `npm ci` | exit 0 |
| `turbo run build` | **12/12 successful** |
| `vitest run` | **343/343 passed**, 10 files, 2.3s |
| `turbo run typecheck` | **13/13 successful** |
| CI on main (run 30762208585) | **success** |

That is a genuinely green repo. The gaps are in coverage and operations, not
correctness of what exists.

**Finding — 4 of 12 packages have no tests:** `acquisition`, `dashboard`,
`media`, `testing`. `acquisition` is the crawler → fetcher → renderer → parser
pipeline — the core product path. The 343 tests cover everything around it.

**Finding — documented stubs still open** (deliberate, but not production):
webhook POST in `alert-manager`, differential-privacy noise in `anonymizer`,
language detection in `field-normalizer` (returns `'und'`), HMAC signed URLs in
`media-store`, the default probe in proxy `health-checker`.

**Finding — infrastructure is written but never exercised.** `Dockerfile`,
`docker-compose.yml`, `prometheus.yml`, and k8s `namespace`/`deployment`
(`image: peekviewer:latest`, 2 replicas) all exist. There is **no deploy
workflow and no CD** — CI builds, tests, typechecks, and audits, nothing more.
`SECRETS.md` names 5 required production secrets (`DATABASE_URL`,
`ELASTICSEARCH_URL`, `REDIS_URL`, `ENCRYPTION_KEY`, `JWT_SECRET`) plus 4
optional; none are wired to anything.

**Finding — identity drift.** The GitHub description still reads ".NET MAUI task
management app with offline-first sync" — three architectures out of date. The
repo is `EnhancedPeek`; every package, the README, CODEOWNERS and the k8s
manifests say `PeekViewer`/`peekviewer`. `CODEOWNERS` points at a team
`@thenot-lab/peekviewer`.

**Finding — a claim worth reconciling before this ships.** The README leads with
"Privacy-First … GDPR/CCPA compliant by design", while `packages/proxy` ships
anti-bot fingerprint mitigation (user-agent rotation, header randomisation,
request-timing jitter) and `packages/acquisition` is a general web/social
extractor. Those two statements need to agree with each other, and the
extraction targets need a lawful basis on the record, before anything is
pointed at a live platform. The pre-rewrite history on
`preserved/media-library-app` (merged PR #2) went further — Instagram DM
harvesting via `sessionid`, contact-info scraping, deleted-content archiving.
That code is off main but still in the repo.

**Old refs:** `preserved/maui-april-2026`, `preserved/media-library-app`, `dev`,
and 4 stale `claude/*` / `copilot/*` branches; tags `v1.0.0`, `v1.0.1`, `v1.1.0`.

**Status: scaffold complete and green; unproven in production.** No integration
test, no runtime run, no deployment, and the primary acquisition path untested.

---

## 3. research-vision-collaboration (main @ `d5f0a9b`)

.NET 8 minimal API — 98 files. Foot / lower-kinetic-chain biomechanics from
uploaded images: constrained vision adapter (Qwen2.5VL 7B via local Ollama),
pedal-prehension physics (wrap angle, flexor tension, skin friction), SQLite
scan history, perceptual hashing, visual clustering, entity resolution, and a
dark-mode dashboard in `wwwroot`. Ships 9 PowerShell scripts covering install →
build → test → publish → Windows installer, plus Docker assets with an Ollama
init service.

**18 test files, 79 `[Fact]`/`[Theory]` cases. Only one TODO-shaped marker in
the whole codebase.**

**UNVERIFIED — the .NET SDK is not installed in this container** (`dotnet:
command not found`), so nothing here was run. The test count is real; the pass
rate is not something I can assert.

No CI workflows. `claude/restore-vscode-changes-6Lva7` is still present after
its PR #2 merged — stale.

---

## 4. eli-researcher (public, main @ `b2e5c53`)

6 files, 1,368 lines. `researcher.py` (952) + `scheduler.py` (317) +
`feeds.json` (79). Monitors 30+ RSS feeds across 8 categories, detects
opportunities, writes a research journal, runs as a daemon. Deliberately
zero-dependency — stdlib only.

**Verified:** both modules compile clean (`py_compile`).
**Finding: no tests, no CI, no `.github/`.** This is the lowest-assurance
artifact in the set — a 1,368-line daemon with nothing checking it.

---

## 5. Standing items from the Aug-2 handoff — one has now expired

Re-flagged, with today's date applied:

1. **Google Takeout parts 21/19/20/55/56 (~2.5 GB) — links expired 2026-08-08.
   That was 21 days ago. These are gone; re-export is required.**
2. Rotate the Apify key (echoed into a transcript — treat as exposed).
3. `rclone config create gdrive drive` — unblocks the 587 GiB migration.
4. Gemini key billing (free tier trains on inputs).
5. `ADMIN_PASSWORD` special-char policy failure.
6. A claude.ai MCP connector sits unauthorized (likely OneDrive).
7. Legion: add `eli-os/deploy/brayai_service.json` to `brayai/config.json` and
   the `SERVICE_CONFIGS` row — cloud sessions can't propagate this back.

## 6. Matched the brief, not audited

Attaching and building these was out of proportion to the ask; naming them so
the gap is explicit: `dominion-workspace`, `dominion-workspace-app`,
`dominion-workspace-desktop`, `ai-workspace-platfor` (the "work" cluster);
`dominion-eli-memory`, `dominion-eli-memory-documents`, `dominion-eli-skills`,
`eli`, `eli-companion-android`, `eli-companion-bridge`, `eli-guardian`.

---

## Bottom line

| Project | Built | Tested | Verified here | Deployed |
|---|---|---|---|---|
| Eli OS (8 phases) | ✅ | 80 tests | ✅ green | ✗ box-side unverified |
| eli-os/integration | ✅ | 21 tests | ✅ green | ✗ unmerged, no PR |
| EnhancedPeek | ✅ | 343 tests, 8/12 pkgs | ✅ green | ✗ no CD |
| research-vision | ✅ | 79 tests | ✗ no SDK here | ✗ |
| eli-researcher | ✅ | none | compiles only | ✗ (daemon) |

Nothing in this set is half-built. Everything in this set is un-run outside its
own test suite. The single highest-value action is merging
`claude/eli-diagnostic-integration-j3ntnq` — 1,324 verified lines whose only
recorded blocker was cleared three weeks before this audit.

— audit session, 2026-08-29
