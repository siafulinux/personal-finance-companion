package com.pfc.companion.data

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * The plain-text shape stored inside the encrypted token blob: one bearer token
 * per server, keyed by the API base URL.
 *
 * Keeping tokens apart is what stops a token minted by one server from being sent
 * to another after the user switches addresses, and lets them switch back without
 * signing in again. A single token could not do both.
 */
object TokenBook {
    private val json = Json { ignoreUnknownKeys = true }

    /** Normalizes a key so `http://h:1/api/v1` and `http://h:1/api/v1/` are one entry. */
    fun key(baseUrl: String): String = baseUrl.trim().trimEnd('/').lowercase()

    fun decode(blob: String): Map<String, String> {
        val parsed = runCatching { json.parseToJsonElement(blob) as? JsonObject }.getOrNull()
            ?: return emptyMap()
        return parsed.mapNotNull { (key, value) ->
            val token = runCatching { value.jsonPrimitive.content }.getOrNull()
            if (token.isNullOrBlank()) null else key(key) to token
        }.toMap()
    }

    fun encode(tokens: Map<String, String>): String = buildJsonObject {
        tokens.forEach { (baseUrl, token) -> put(key(baseUrl), token) }
    }.toString()
}
