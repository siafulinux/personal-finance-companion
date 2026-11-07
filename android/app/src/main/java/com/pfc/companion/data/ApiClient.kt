package com.pfc.companion.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okio.BufferedSink
import java.io.IOException
import java.util.concurrent.TimeUnit

class ApiException(val status: Int, message: String) : Exception(message)

/**
 * Thin JSON client over OkHttp. The server speaks the same API as the web app,
 * including bearer tokens for non-browser clients.
 */
class ApiClient(
    private val session: SessionState,
    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build(),
) {
    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }

    private val jsonMedia = "application/json; charset=utf-8".toMediaType()

    suspend fun <T> get(
        path: String,
        serializer: KSerializer<T>,
        query: Map<String, String> = emptyMap(),
    ): T = execute(
        Request.Builder().url(buildUrl(path, query)).get().build(),
        serializer,
    )

    suspend fun <B, T> post(
        path: String,
        body: B,
        bodySerializer: KSerializer<B>,
        serializer: KSerializer<T>,
    ): T {
        val payload = json.encodeToString(bodySerializer, body).toRequestBody(jsonMedia)
        return execute(Request.Builder().url(buildUrl(path)).post(payload).build(), serializer)
    }

    suspend fun postNoContent(path: String, body: String = "{}") {
        val request = Request.Builder()
            .url(buildUrl(path))
            .post(body.toRequestBody(jsonMedia))
            .build()
        executeRaw(request)
    }

    suspend fun <T> postJson(
        path: String,
        body: kotlinx.serialization.json.JsonElement,
        serializer: KSerializer<T>,
    ): T = execute(
        Request.Builder()
            .url(buildUrl(path))
            .post(body.toString().toRequestBody(jsonMedia))
            .build(),
        serializer,
    )

    suspend fun <T> patch(
        path: String,
        body: kotlinx.serialization.json.JsonElement,
        serializer: KSerializer<T>,
    ): T = execute(
        Request.Builder()
            .url(buildUrl(path))
            .patch(body.toString().toRequestBody(jsonMedia))
            .build(),
        serializer,
    )

    suspend fun delete(path: String) {
        executeRaw(Request.Builder().url(buildUrl(path)).delete().build())
    }

    /**
     * Reads a URL verbatim without attaching any credential.
     *
     * This is how the app asks a server it has not been configured for yet what it
     * is (`/server/info`). Sending the current server's bearer token to an address
     * the user just typed would hand one installation's session to another, so this
     * path never authenticates — the endpoint it calls is public by design.
     */
    suspend fun <T> getAnonymous(url: String, serializer: KSerializer<T>): T {
        val request = try {
            Request.Builder().url(url).get().build()
        } catch (err: IllegalArgumentException) {
            throw ApiException(0, "That is not a valid server address.")
        }
        return execute(request, serializer, authenticate = false)
    }

    /** Streams a CSV from its content URI as multipart form data, reporting 0..1 progress. */
    suspend fun <T> uploadCsv(
        path: String,
        upload: CsvUpload,
        fields: Map<String, String> = emptyMap(),
        serializer: KSerializer<T>,
        onProgress: (Float) -> Unit = {},
    ): T {
        val multipart = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .apply { fields.forEach { (key, value) -> addFormDataPart(key, value) } }
            .addFormDataPart("file", upload.filename, CsvRequestBody(upload, onProgress))
            .build()
        val request = Request.Builder().url(buildUrl(path)).post(multipart).build()
        return execute(request, serializer)
    }

    private suspend fun buildUrl(path: String, query: Map<String, String> = emptyMap()): okhttp3.HttpUrl {
        // Canonicalise the stored address: a value saved without /api/v1 would
        // otherwise build /auth/me and answer 404.
        val base = ServerUrl.apiBaseFromStored(session.baseUrl()).toHttpUrl()
        val builder = base.newBuilder()
        path.trimStart('/').split('/').filter { it.isNotEmpty() }.forEach(builder::addPathSegment)
        query.forEach { (key, value) -> builder.addQueryParameter(key, value) }
        return builder.build()
    }

    private suspend fun <T> execute(
        request: Request,
        serializer: KSerializer<T>,
        authenticate: Boolean = true,
    ): T {
        val body = executeRaw(request, authenticate)
        return try {
            json.decodeFromString(serializer, body)
        } catch (err: Exception) {
            // A 200 that is not JSON usually means the address pointed at the web
            // app rather than its API, so name the place to fix it.
            throw ApiException(
                0,
                "The server answered with something other than JSON — check the server address in Settings. (${err.message})",
            )
        }
    }

    private suspend fun executeRaw(builder: Request, authenticate: Boolean = true): String =
        withContext(Dispatchers.IO) {
        val token = if (authenticate) session.token() else null
        // Second line of defence for the "switching servers" case: a request built
        // just before the address changed must not carry the old server's token.
        val currentBase = ServerUrl.apiBaseFromStored(session.baseUrl()).trimEnd('/')
        val belongsHere = builder.url.toString().startsWith(currentBase)
        val request = builder.newBuilder().apply {
            header("Accept", "application/json")
            if (!token.isNullOrBlank() && belongsHere) header("Authorization", "Bearer $token")
        }.build()

        val response = try {
            client.newCall(request).execute()
        } catch (err: IOException) {
            throw ApiException(0, "Cannot reach the finance server. Check the server address in Settings.")
        }

        response.use {
            val text = it.body?.string().orEmpty()
            if (it.isSuccessful) {
                return@withContext text
            }
            if (it.code == 401) {
                throw ApiException(401, "Your session expired. Sign in again.")
            }
            throw ApiException(it.code, readError(text, it.code))
        }
    }

    private class CsvRequestBody(
        private val upload: CsvUpload,
        private val onProgress: (Float) -> Unit,
    ) : RequestBody() {
        override fun contentType(): MediaType? = upload.mimeType.toMediaTypeOrNull()

        override fun contentLength(): Long = upload.contentLength

        override fun writeTo(sink: BufferedSink) {
            upload.openStream().use { input ->
                val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                var written = 0L
                while (true) {
                    val read = input.read(buffer)
                    if (read == -1) break
                    sink.write(buffer, 0, read)
                    written += read
                    if (upload.contentLength > 0) {
                        onProgress((written.toDouble() / upload.contentLength).toFloat().coerceIn(0f, 1f))
                    }
                }
            }
        }
    }

    private fun readError(text: String, status: Int): String {
        if (text.isBlank()) return fallbackError(status)
        return try {
            val parsed = json.parseToJsonElement(text)
            if (parsed !is JsonObject) return fallbackError(status)
            val detail = parsed["detail"]
            val message = when (detail) {
                is JsonArray -> detail.joinToString("; ") { item ->
                    val obj = item as? JsonObject
                    obj?.get("msg")?.jsonPrimitive?.content ?: item.toString()
                }
                null -> fallbackError(status)
                else -> detail.jsonPrimitive.content
            }
            // FastAPI validation responses carry the readable field errors separately.
            val fieldErrors = (parsed["errors"] as? JsonArray)
                ?.mapNotNull { (it as? JsonObject)?.get("msg")?.jsonPrimitive?.content }
                ?.distinct()
                .orEmpty()
            if (fieldErrors.isEmpty()) message else "$message ${fieldErrors.joinToString(" ")}"
        } catch (_: Exception) {
            fallbackError(status)
        }
    }

    /**
     * The status-only message. A 404 from a self-hosted server is almost always a
     * wrong address (a port that serves the web app, or a stored base missing the
     * API path), not a missing feature, so the hint points at the setting the user
     * can actually change.
     */
    private fun fallbackError(status: Int): String = if (status == 404) {
        "Request failed (404). The server is reachable but has no API at that address — check it in Settings."
    } else {
        "Request failed ($status)."
    }
}
