# Companion patch — drop-in Kotlin + wiring for the Elli connection

These are **reference implementations** for the `eli-companion-android` repo.
They live here (not in that private repo) because this session's write scope is
`thenot-lab.github.io`. Apply them to the companion app in Android Studio / CI.

## Files

- **`ElliClient.kt`** → `app/src/main/kotlin/com/dominionlabs/elicompanion/network/ElliClient.kt`
  On-device client for `tool_router :8081` (chat) + `context_bridge :8082`
  (event tee). Complete and self-contained.

## Wiring changes (small, in existing files)

1. **`data/SettingsManager.kt`** — add one setting:
   ```kotlin
   var elliAuthToken: String?    // the ELLI_AUTH_TOKEN from ~/.elli_env on device
       get() = prefs.getString("elli_auth_token", null)
       set(v) { prefs.edit().putString("elli_auth_token", v).apply() }
   ```

2. **`network/mTLSClient.kt`** — tee captured events to the on-device store.
   In `postEvent` and `postObserverEvent`, after the existing host call, add:
   ```kotlin
   // Mirror to on-device Elli so she can use this context (fire-and-forget).
   ElliClient(settingsManager).teeContextEvent(type, payloadAsJsonObject)
   ```
   (`postObserverEvent` already has a `JsonObject`; `postEvent`'s
   `Map<String,String>` converts with the existing `anyToJson` helper.)

3. **`MainActivity.kt`** — add the chat + gallery routes to the `NavHost`:
   ```kotlin
   composable("chat")    { ChatScreen(navController) }
   composable("gallery") { GalleryScreen(navController) }
   ```
   and a Home button into `chat`.

4. **Device side (`eli/runtime/device_inference/tool_router.py`)** — 3 lines in
   `main()` so Elli gets the context tools + grounding:
   ```python
   import elli_router_ext as ext          # from this folder, deployed alongside
   store = ext.patch_tool_router(sys.modules[__name__])
   # run context_bridge.main() in a second thread, or as its own Termux service
   ```

## New screens to author (specced in `../PLAN.md`)

- `ui/ChatScreen.kt` + `ui/ConversationDrawer.kt` — chat with sidebar (item 2).
- `data/ConversationStore.kt` — Room threads/messages (item 2).
- `voice/VoiceIO.kt` — TextToSpeech + SpeechRecognizer (item 5).
- `ui/GalleryScreen.kt` + `capture/MediaIndexer.kt` — gallery/footfinder (item 6).
- `connector/AppConnector.kt` — Elli's tool loop → `EliAgenticEngine` (item 7).

No new third-party dependencies are required: OkHttp, kotlinx-serialization,
Room, Compose, and the media/speech APIs are all already on the classpath or
in the Android platform.
