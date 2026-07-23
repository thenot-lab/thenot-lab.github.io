# Eli Companion ⇄ Ellie integration

Connects the **Eli Companion** capture app to **Ellie** (the on-device SLM)
so she can utilize the device context the companion captures — the "Connect
(Data)" spine from the planning note. See **[PLAN.md](PLAN.md)** for the full,
item-by-item build plan across both repos.

## What's here (built + tested)

| File | Role | Status |
|---|---|---|
| `context_bridge.py` | On-device SQLite context store + inferenced memory + READ tools + loopback ingest HTTP (fail-closed, bearer) | ✅ 14 tests |
| `ellie_router_ext.py` | Merges context tools into `tool_router` + grounds every chat turn | ✅ 7 tests |
| `demo.py` | Offline end-to-end: capture → store → grounded Ellie turn + tool calls | ✅ runs |
| `companion_patch/EllieClient.kt` | Companion→on-device chat + event-tee client (drop-in) | reference |
| `companion_patch/build-apk.yml` | CI that installs the Android SDK and assembles the APK | reference |

## Run it

```bash
cd eli-os/integration
python3 test_context_bridge.py      # 14 tests
python3 test_ellie_router_ext.py    # 7 tests
python3 demo.py                     # offline end-to-end loop
```

## On-device topology (all loopback, no cloud)

```
Eli Companion APK ─POST /v1/context/event→ context_bridge :8082 ─┐
                                                                 ├─ ContextStore (SQLite)
tool_router :8081 ─(patched)─ context READ tools + digest ───────┘
        ↑
Eli Companion APK ─POST /v1/chat/completions→ Ellie (the SLM)
```

The context bridge never makes outbound calls: captured data stays on the
phone. Host telemetry remains the separate, already-mTLS path.

## Deploy (device side)

1. Push `context_bridge.py` + `ellie_router_ext.py` next to
   `tool_router.py` on the device (same Termux `~/elli/`).
2. Export a shared `ELLI_AUTH_TOKEN` (already in `~/.elli_env`).
3. Start `context_bridge.py` as a second service (or a thread from
   `tool_router.main()`), then apply the 3-line `patch_tool_router` wiring.
4. Apply the companion patch (`companion_patch/README.md`) and build the APK.
