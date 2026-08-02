# NEXT SESSION HANDOFF — 2026-08-02 (~01:30Z)

Written by the cloud session (Fable 5) that picked up the 2026-08-02 handoff
cold. For Elli / Eli / whichever of us wakes next. Everything from tonight,
verified state only — each claim has a commit, run, or artifact behind it.

## 1. Elli Chat App APK — BUILT. The July 23 blocker is fully cleared.

Repo `eli-companion-android`, branch `claude/elli-integration`.

Three stacked blockers were hiding behind each other; all cleared tonight:
1. Account-level Actions block (0-job startup failures) — cleared upstream
   sometime after Jul 23 (billing/minutes).
2. `build-apk.yml` never parsed: `secrets` context in step-level `if:` is
   rejected by GitHub. Fixed via job-level `HAS_KEYSTORE` env flag → `9522c8d`.
3. `gradlew` committed without the exec bit (Windows) → `Permission denied`
   exit 126. Exec bit set + defensive chmod → `03964e3`.

First successful APK: run 30723278603→failed, then **30723744310 = green**.

## 2. The Elli rewrite had silently DROPPED merged features. Recovered.

The rewrite of `SettingsScreen.kt` (commit `00941d6`) clobbered two merged
features when the branch took main's history:
- **Editable host address** (PR #6) — restored with PR #8's corrected
  tri-state feedback (updated / no change / failed) → `fe1e4af`, build green,
  artifact `elli-apk` 20,391,915 B, sha256 0d9a7bf3…d921529, run 30724733544.
- **Capture-truth UI** (the "dead PHI stream showed ON for five weeks" fix —
  live OS grant state vs stored preference) — restored via the back-merge
  below.

Lesson for the goldmine: a rebase/rewrite that wins a file wholesale loses
main's fixes in that file with no conflict shown. Diff rewritten files
against main before trusting them.

## 3. PRs #7 / #8 (Eli's relay) — resolved. Titles in the relay were crossed.

- The numbers/timestamps matched `eli-companion-android`, not DVCS:
  - **PR #7** "Close all 6 Copilot findings" — was already MERGED (main's
    HEAD was its merge commit). Never stranded; the list API's unpopulated
    `merged` field misleads — trust the commit graph, not that field.
  - **PR #8** "report real host-address outcome" — real, open, checked, then
    MERGED to main with Brayd's approval → `ad75d62`.
- "DVCS deployment target / WARP enrollment" map to `dominion-ide` PRs
  #20–31: ALL closed (Hetzner eli-cloud deploy, pinned CI deploy key, ghcr
  token, Cloudflare Access). No open PRs in dominion-ide / eli /
  eli-companion-bridge. `liqui-dominion` has ~10 dependabot PRs open only.

## 4. CI now exists on main. No more compile-unverified fix branches.

main had ZERO workflows (that's how PR #8 shipped unverified). Added the
proven workflow to main with `fix/**` in the push triggers → `8371248`.
main's first-ever CI run 30726517857 = green, and it retroactively verified
PR #8's compile. Every push to main / claude/** / fix/** now builds an APK.

## 5. Back-merge main → claude/elli-integration DONE — verification in flight.

Merge commit `8712efc` (required un-shallowing the clone first). Union
resolution in SettingsScreen: kept Elli state (token/mirror/voice) AND took
main's capture-truth polling; deduped the host-address validator; workflow
kept `fix/**`. PR #5/#6 fixes auto-merged into MainActivity, SettingsManager,
mTLSClient, HomeScreen.

**FIRST ACTION FOR NEXT SESSION:** check the newest build-apk run on
`claude/elli-integration` for `8712efc`. Green → that run's `elli-apk` is the
definitive APK (Elli features + editable host + capture truth). Red → fix the
Kotlin error and re-push; the union merge is the only new code.

## 6. Sideload notes (Brayd's KEY2 runs Android 15)

minSdk 26 / targetSdk 34 — installs fine. Android 13+ blocks notification +
accessibility grants for sideloaded APKs until Settings → Apps → app → ⋮ →
"Allow restricted settings". Signed release build: add KEYSTORE_BASE64 /
KEYSTORE_PASSWORD / KEY_ALIAS / KEY_PASSWORD repo secrets and re-run.

## 7. Eli OS — Phases 7 & 8 shipped (thenot-lab.github.io)

Branch `claude/session-handoff-aug-2-dzyqrk` (NOT merged to main; no PR —
decide whether to PR/merge):
- Verified all of Phases 0–6 green first: 77 tests + offline demo.
- **Phase 7** `eli-os/deploy/` (`554c761`): gateway as a managed service —
  BRA.Y.AI registration (port 8484, health `/healthz`), `ELI_OS_GATEWAY.bat`,
  hardened systemd unit. Legion TODO: add `deploy/brayai_service.json` entry
  to `brayai/config.json` + the SERVICE_CONFIGS row (the skill copies in
  cloud sessions don't propagate back).
- **Phase 8** `eli-os/instance/` (`746d70e`, `944c308`): survivable instance —
  OneDrive durable core (atomic stamped snapshots via VACUUM INTO, repo
  bundle, handoffs) + `bootstrap.ps1` fresh-machine rebuild + rclone
  transport note aligned with EliContinuance. Future handoffs should
  dual-write: `python3 eli-os/instance/snapshot.py handoff --write f.md
  --push <branch>` — this file follows that pattern (git + Drive).

## 8. Standing items needing BRAYD (unchanged from Eli's manifest, re-flagged)

1. Rotate the Apify key (value echoed into a transcript — treat as exposed).
2. Google Takeout parts 21/19/20/55/56 (~2.5 GB) — links EXPIRE 2026-08-08.
3. `rclone config create gdrive drive` (unblocks 587 GiB migration).
4. Gemini key billing (free tier = inputs trained on; privacy control).
5. ADMIN_PASSWORD special-char policy failure.
6. NEW: a claude.ai MCP connector sits unauthorized (likely OneDrive) —
   authorize in claude.ai → Settings → Connectors to let cloud sessions
   sweep OneDrive directly.

## 9. Channel map (what tonight proved works)

- Legion ⇄ cloud: git branches (this file), NOT local `.claude` paths.
- Eli → anyone: Google Drive root (the continuance manifest was read tonight
  from a cloud session within the hour).
- Cloud → Legion: this repo + Drive copy of this handoff.

— cloud session, 2026-08-02
