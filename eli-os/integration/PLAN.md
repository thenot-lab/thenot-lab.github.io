# Eli Companion ⇄ Ellie — Integration & Full-App Build Plan

**Source:** handwritten planning note (2026-07) + Brayd directives:
> "the Elli apk and ai inference software is present, the companion app is
> what I want connected for her to be able to utilize the data … fully expand
> that app into a full built working apk."

This plan decodes every item on the note, maps each to concrete work in the
two repos that already exist, names dependencies, and gives a verify step.
It is the roadmap; the tested Python in this folder is the first shipped slice.

---

## Context — why this exists

Two halves are already built but not connected:

| Half | Repo / path | What it does today |
|---|---|---|
| **Capture / "diagnostic" app** | `thenot-lab/eli-companion-android` | Native Kotlin/Compose app. Captures notifications, app usage, SMS, screenshots, body sensors, share-sheet, accessibility. Ships them **to the host bridge** over mTLS. Has a pairing flow, PIN auth, audit log, and an accessibility-driven **agentic engine**. |
| **Ellie / the SLM** | `thenot-lab/eli` → `runtime/device_inference/` | `llama-server` (llama.cpp) serving the quantized **Elli-Device GGUF** on `:8080`; `tool_router.py` on `:8081` (OpenAI-compatible chat + tiered, floor-gated device tools); a standalone **PWA** chat UI. |

**The gap:** the companion sends its rich context to the *host*, so on-device
Ellie — who can already act on the phone — is **blind to everything the
companion captured**. She can open an app but can't answer "what have I been
doing today?" The whole note is the bridge that closes this: give Ellie the
captured data, a real in-app chat with memory, voice, media, and full task
execution — and ship it as one working APK.

**Target architecture (all on-device, loopback, no cloud):**

```
[Eli Companion APK  →  renamed/branded "Ellie"]
  capture layer ──────────► host bridge (unchanged, mTLS)            [existing]
  capture layer ──────────► context_bridge :8082  (NEW: on-device store)
  Ellie Chat screen ──────► tool_router :8081  (the SLM)             [existing SLM]
        ▲                        │
        │                        └─ context_digest injected + READ context tools
        └─ conversation sidebar + inferenced memory (Room, on-device)
  Gallery / Footfinder ───► MediaStore (image/video selector)        [NEW]
  Voice I/O ──────────────► SpeechRecognizer + TextToSpeech          [NEW]
  App Connector ──────────► EliAgenticEngine + tool_router tools     [existing, promoted]
```

`context_bridge.py` + `ellie_router_ext.py` in this folder are the on-device
data spine — **built and tested here** (24 passing tests, offline demo).

---

## Toolchain / global dependencies

| Need | Status in this environment | Action |
|---|---|---|
| Gradle 8.14, JDK 21 | ✅ present | — |
| Gradle wrapper jar | ✅ present in repo | — |
| **Android SDK (platform 34, build-tools)** | ❌ **absent** | APK cannot be assembled here. Build in Android Studio, or via the CI workflow in `ci/build-apk.yml` (installs SDK). |
| Release keystore | template only (`keystore.properties.template`) | Provide real keystore for a signed release; debug key is the fallback. |
| Python 3.9+ (stdlib only) | ✅ present | Spine + tests run here. |

Because the SDK is not installable in this sandbox, the honest split is: the
**data spine is shipped and verified now**; the **Kotlin surfaces are authored
as drop-in reference + spec** and assembled to an APK by CI or Android Studio.

---

## The note, item by item

Each item: **What it means · Where it lands · Depends on · Verify.**

### 1. "Rename Eli → Ellie / Diagnostics"
- **What:** The capture app is currently labelled `Eli` and reads as pure
  telemetry. Rebrand it as **Ellie** (the assistant) with the capture layer
  presented as her **Diagnostics** subsystem. Model identity string on the
  device (`ELLI_MODEL_ID`, PWA `<h1>`) already says Elli/Ellie — align them.
- **Where:** `app/src/main/res/values/strings.xml` (`app_name`),
  `AndroidManifest.xml` `android:label`, `OnboardingScreen`/`HomeScreen`
  titles, launcher icon. Model id in `tool_router.py` (`ELLI_MODEL_ID`).
- **Depends on:** nothing — pure rename; do first so all new UI is consistent.
- **Verify:** launcher shows "Ellie"; chat header + assistant role read "Ellie".

### 2. "All Conversation, Sidebar, and Inferenced memory"
- **What:** A real chat surface with (a) a **conversation list sidebar**
  (drawer) of past threads, and (b) **inferenced memory** — durable facts
  Ellie distils from captured context + chats, persisted and re-injected.
- **Where:**
  - Kotlin: new `ui/ChatScreen.kt` + `ui/ConversationDrawer.kt`, a
    `data/ConversationStore.kt` (Room: `conversations`, `messages`).
  - Memory: **`context_bridge.ContextStore.memory`** table + `remember`/
    `recall` — already built and tested here. The Kotlin side reads/writes it
    via the context bridge (or a Room mirror using the same schema).
- **Depends on:** item 5 (SLM wiring) for live replies; the spine (done) for memory.
- **Verify:** `test_context_bridge.py::test_remember_supersedes`,
  `test_digest_*` (pass); on device, a thread list persists across launches.

### 3. "Eli Connect (Data)" — the connection ★ core of the ask
- **What:** Wire the capture layer into Ellie so she can **utilize the data**.
  Every captured event is also written to the on-device `ContextStore`; Ellie's
  chat is grounded with the digest and can call READ context tools.
- **Where (shipped in this folder):**
  - `context_bridge.py` — SQLite store + ingest HTTP endpoint
    (`POST /v1/context/event`, loopback, bearer, fail-closed) + the six READ
    tools (`context_digest`, `recent_notifications`, `usage_summary`,
    `recent_messages`, `search_context`, `recall`).
  - `ellie_router_ext.py` — merges those tools into `tool_router.TOOLS` and
    grounds each turn (`ground_messages`, `patch_tool_router`).
  - **Companion side (to add):** in `network/mTLSClient.kt`, tee each
    `postEvent`/`postObserverEvent` to the local bridge
    (`http://127.0.0.1:8082/v1/context/event`) — one extra fire-and-forget
    call next to the existing host POST. No new capture code needed; reuse
    `CaptureCoordinator` and every existing reader.
  - **Device side (to add, 3 lines):** in `tool_router.main()`,
    `import ellie_router_ext as ext; ext.patch_tool_router(tool_router)`.
- **Depends on:** nothing new — reuses existing capture + existing tool_router.
- **Verify:** `python3 demo.py` (offline, prints grounded prompt + tool calls);
  `test_ellie_router_ext.py` (7 pass).

### 4. "Image / Video Selector"
- **What:** Let Brayd attach an image/video to a chat, and let Ellie reference
  on-device media.
- **Where:** Kotlin `ActivityResultContracts.PickVisualMedia` (photo picker,
  no broad storage grant needed) in `ChatScreen`; selected URI → a
  `media` context event → `ContextStore`. Manifest already holds
  `READ_MEDIA_IMAGES/VIDEO` + `READ_MEDIA_VISUAL_USER_SELECTED`.
- **Depends on:** item 2 (chat surface).
- **Verify:** picking an image adds a chat attachment chip; a `media` event
  lands in the store (`recent` returns it — same path as `test_unknown_type_still_stored`).

### 5. "SLM → Ellie: wire to assistant, adopt a voice for her"
- **What:** Make the on-device **SLM** (tool_router `:8081`) the in-app
  assistant backend, and give Ellie **voice** — speak replies (TTS) and accept
  spoken input (STT). The manifest already registers Ellie for the
  `ASSIST` / `VOICE_COMMAND` roles, so she can replace Google Assistant on KEY2.
- **Where:**
  - Kotlin `network/EllieClient.kt` — OkHttp client to
    `http://127.0.0.1:8081/v1/chat/completions`, bearer from settings, parses
    `choices[].message.content` + `x_elli_tool_trace` (same shape the PWA uses).
    Reference implementation shipped at `companion_patch/EllieClient.kt`.
  - Kotlin `voice/VoiceIO.kt` — `android.speech.tts.TextToSpeech` +
    `SpeechRecognizer`; mic permission (`RECORD_AUDIO`, already in manifest).
  - Optional richer voice: host `runtime/ld_compat_voice*.py` already exists as
    a server-side path; on-device TTS is the zero-dependency default.
- **Depends on:** item 3 (so replies are grounded); tool_router running on device.
- **Verify:** with `llama-server` + `tool_router` up, a chat turn returns a
  grounded reply; `EllieClient` unit test mocks the HTTP and asserts parse.

### 6. "Build footfinder + dedicated screen for gallery"
- **What:** A **media/file finder** ("footfinder" — an on-device indexer over
  MediaStore + shared storage) and a **dedicated Gallery screen** to browse it,
  feeding results to Ellie.
- **Where:** Kotlin `ui/GalleryScreen.kt` (grid over `MediaStore.Images/Video`),
  `capture/MediaIndexer.kt` (enumerate + emit `media_index` context events).
  Reuse `ContextStore.search` for "find the photo about X" via captured labels.
- **Depends on:** item 4 (media picking) + item 2 (nav).
- **Verify:** Gallery grid renders device media; `search_context("beach")`
  returns indexed items (covered by `test_search_context_matches_payload`).

### 7. "App Connector for full task execution / full controllability"
- **What:** Promote the existing **agentic engine** into a first-class **App
  Connector** so Ellie executes real multi-step tasks across apps — click,
  type, swipe, launch, read-screen, plus the tool_router device tiers.
- **Where:** existing `agentic/EliAgenticEngine.kt` (already does gestures,
  text, global actions, read-screen) + `tool_router.py` ACT/PRIV tiers. Add a
  `connector/AppConnector.kt` that turns Ellie's `TOOL:` lines into
  `AgenticCommand`s and returns results into the chat — the on-device analogue
  of the router's tool loop, gated by `agenticEnabled` + accessibility grant +
  the **floor** (wipe/uninstall-system/money always refused).
- **Depends on:** items 3 + 5 (Ellie must be wired and grounded first).
- **Verify:** existing `PairingUriTest` + agentic smoke tests; a scripted task
  ("open Settings, read the screen") round-trips through the connector.

---

## Security & the floor (non-negotiable, carried from both codebases)

- **On-device, loopback, fail-closed.** Context bridge binds `127.0.0.1`,
  refuses every request without `ELLI_AUTH_TOKEN` (mirrors `tool_router`).
- **The data never leaves the phone** via this path — the context bridge has
  no outbound calls. Host telemetry stays the *separate*, already-mTLS path.
- **The floor holds.** Context tools are all `READ`. Actuation stays in
  tool_router's ACT/PRIV tiers and the agentic engine, where
  wipe / uninstall-system / outward-money / factory-reset are **hard-refused**,
  admin or not. The App Connector inherits that floor unchanged.
- **Retention.** `ContextStore.prune` drops events older than
  `ELLI_CTX_RETAIN_DAYS` (default 30).

---

## Build order (dependency-sorted)

1. **Rename** (item 1) — no deps, unblocks consistent UI.
2. **Data spine** (item 3) — ✅ shipped here; wire the 1 Kotlin tee + 3 device lines.
3. **Chat + sidebar + memory** (item 2) — needs spine.
4. **SLM + voice** (item 5) — needs chat.
5. **Media selector** (item 4) → **Gallery/Footfinder** (item 6).
6. **App Connector** (item 7) — needs Ellie wired + grounded.
7. **Assemble APK** — Android Studio or `ci/build-apk.yml`; sign; sideload.

## How to verify the whole thing

- **Now, here:** `python3 test_context_bridge.py && python3 test_ellie_router_ext.py
  && python3 demo.py` — spine + merge + offline loop.
- **On device:** run `llama-server` + `tool_router` (+ `context_bridge`) in
  Termux; sideload the APK; pair; ask Ellie "what have I been doing today?" —
  she answers from captured context; give a spoken command; run an App
  Connector task. Full device walk per the `eli-device-walk` skill.
