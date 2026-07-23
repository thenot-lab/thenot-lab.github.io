# Eli Companion ⇄ Elli integration

Connects the **Eli Companion** capture app to **Elli** (the on-device SLM)
so she can utilize the device context the companion captures — the "Connect
(Data)" spine from the planning note. See **[PLAN.md](PLAN.md)** for the full,
item-by-item build plan across both repos.

## What's here (built + tested)

| File | Role | Status |
|---|---|---|
| `context_bridge.py` | On-device SQLite context store + inferenced memory + READ tools + loopback ingest HTTP (fail-closed, bearer) | ✅ 14 tests |
| `elli_router_ext.py` | Merges context tools into `tool_router` + grounds every chat turn | ✅ 7 tests |
| `demo.py` | Offline end-to-end: capture → store → grounded Elli turn + tool calls | ✅ runs |
| `companion_patch/ElliClient.kt` | Companion→on-device chat + event-tee client (drop-in) | reference |
| `companion_patch/build-apk.yml` | CI that installs the Android SDK and assembles the APK | reference |

## Run it

```bash
cd eli-os/integration
python3 test_context_bridge.py      # 14 tests
python3 test_elli_router_ext.py    # 7 tests
python3 demo.py                     # offline end-to-end loop
```

## On-device topology (all loopback, no cloud)

```
Eli Companion APK ─POST /v1/context/event→ context_bridge :8082 ─┐
                                                                 ├─ ContextStore (SQLite)
tool_router :8081 ─(patched)─ context READ tools + digest ───────┘
        ↑
Eli Companion APK ─POST /v1/chat/completions→ Elli (the SLM)
```

The context bridge never makes outbound calls: captured data stays on the
phone. Host telemetry remains the separate, already-mTLS path.

## Deploy (device side)

1. Push `context_bridge.py` + `elli_router_ext.py` next to
   `tool_router.py` on the device (same Termux `~/elli/`).
2. Export a shared `ELLI_AUTH_TOKEN` (already in `~/.elli_env`).
3. Start `context_bridge.py` as a second service (or a thread from
   `tool_router.main()`), then apply the 3-line `patch_tool_router` wiring.
4. Apply the companion patch (`companion_patch/README.md`) and build the APK.

## Status (2026-07-23)

The full companion-app expansion is **implemented and pushed** to
`eli-companion-android` branch **`claude/elli-integration`** (v1.6.0): the
Elli chat + conversation sidebar + inferenced memory, the Connect (Data) tee,
image/video picker, voice I/O, gallery/footfinder, and the App Connector —
all seven note items. The device-side spine here (`context_bridge.py` +
`elli_router_ext.py`) is tested (21 passing) and the offline loop runs.

**The signed APK still needs to be assembled** — that couldn't happen in the
build sandbox for two independent reasons:
- the sandbox network policy blocks Google's SDK host (`dl.google.com`), so a
  local Android build can't fetch the platform/build-tools; and
- the repo's GitHub Actions runs **startup-fail with 0 jobs** (an account-level
  Actions block — exhausted private-repo minutes or a spending limit), so the
  `build-apk` CI can't start.

To produce the APK: either (a) restore GitHub Actions minutes/billing on the
account and re-run the `build-apk` workflow (artifact `elli-apk`), or (b) open
the branch in Android Studio (SDK + network present) and `assembleDebug`.
