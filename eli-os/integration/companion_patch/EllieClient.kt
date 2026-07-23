// EllieClient.kt — companion-app client for the ON-DEVICE Ellie stack.
//
// Reference implementation to drop into eli-companion-android at
//   app/src/main/kotlin/com/dominionlabs/elicompanion/network/EllieClient.kt
//
// It connects the capture app to the two loopback services the Elli-Device
// stack already runs in Termux:
//   * tool_router :8081  — OpenAI-compatible chat + device tool-calling (the SLM)
//   * context_bridge :8082 — the on-device captured-context store (this repo)
//
// Two responsibilities:
//   1. chat(...)         — send a conversation to Ellie and get her reply +
//                          the device tool trace (same shape the PWA parses).
//   2. teeContextEvent() — mirror every captured event into the local context
//                          store so Ellie can read it. Call this right next to
//                          the existing host postEvent in mTLSClient.
//
// Loopback is NOT a security boundary on Android (other apps share 127.0.0.1),
// so the bearer token is required on every call — same rule as tool_router.
// Plain OkHttp (no mTLS): these are localhost services on the same device.

package com.dominionlabs.elicompanion.network

import com.dominionlabs.elicompanion.data.SettingsManager
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

class EllieClient(
    private val settings: SettingsManager,
    private val routerUrl: String = "http://127.0.0.1:8081/v1/chat/completions",
    private val contextUrl: String = "http://127.0.0.1:8082/v1/context/event",
) {
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

    // Long read timeout: a 1–1.5B GGUF on a Kryo 260 CPU is slow; the PWA uses
    // a 120s ceiling. Keep parity so slow first-token generations don't error.
    private val client = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .build()

    private fun bearer(): String = "Bearer ${settings.ellieAuthToken.orEmpty()}"

    /** One chat turn against on-device Ellie. Returns her reply text plus the
     *  device tool trace (what she actually did). Throws on transport/HTTP
     *  error so the caller can show "router offline — is Termux up?". */
    fun chat(history: List<ChatMessage>, model: String = "elli-device-1b"): EllieReply {
        if (settings.ellieAuthToken.isNullOrBlank()) {
            throw IllegalStateException("Ellie auth token not set (see ~/.elli_env on device)")
        }
        val req = ChatRequest(model = model, messages = history)
        val body = json.encodeToString(ChatRequest.serializer(), req)
            .toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url(routerUrl)
            .header("Authorization", bearer())
            .post(body)
            .build()
        client.newCall(request).execute().use { r ->
            if (!r.isSuccessful) throw java.io.IOException("Ellie router HTTP ${r.code}")
            val text = r.body?.string() ?: throw java.io.IOException("empty reply")
            val parsed = json.decodeFromString(ChatResponse.serializer(), text)
            val content = parsed.choices.firstOrNull()?.message?.content ?: "(empty reply)"
            return EllieReply(content = content, model = parsed.model, trace = parsed.tool_trace)
        }
    }

    /** Mirror a captured event into the on-device context store. Fire-and-
     *  forget: a failure here must never disrupt capture. Call alongside the
     *  existing host postEvent in mTLSClient (same `type`/`payload`). */
    fun teeContextEvent(type: String, payload: JsonObject) {
        val token = settings.ellieAuthToken
        if (token.isNullOrBlank()) return
        val event = ContextEvent(type = type, payload = payload, ts = nowIso())
        val body = json.encodeToString(ContextEvent.serializer(), event)
            .toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url(contextUrl)
            .header("Authorization", "Bearer $token")
            .post(body)
            .build()
        client.newCall(request).enqueue(object : okhttp3.Callback {
            override fun onFailure(call: okhttp3.Call, e: java.io.IOException) { /* store may be down; ignore */ }
            override fun onResponse(call: okhttp3.Call, response: okhttp3.Response) { response.close() }
        })
    }

    private fun nowIso(): String =
        java.time.Instant.now().truncatedTo(java.time.temporal.ChronoUnit.SECONDS).toString()

    data class EllieReply(val content: String, val model: String, val trace: JsonElement?)

    @Serializable data class ChatMessage(val role: String, val content: String)

    @Serializable
    private data class ChatRequest(
        val model: String,
        val messages: List<ChatMessage>,
        val temperature: Double = 0.2,
        val max_tokens: Int = 384,
    )

    @Serializable private data class ChatResponse(
        val model: String = "",
        val choices: List<Choice> = emptyList(),
        val x_elli_tool_trace: JsonElement? = null,
    ) {
        val tool_trace: JsonElement? get() = x_elli_tool_trace
    }

    @Serializable private data class Choice(val message: ChatMessage? = null)

    @Serializable
    private data class ContextEvent(
        val device_id: String = "",
        val type: String,
        val payload: JsonObject,
        val ts: String,
    )
}
