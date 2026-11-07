package com.pfc.companion.data

import kotlinx.coroutines.flow.Flow

/**
 * Session surface used by the API client. Keeping it an interface lets repository
 * and ViewModel tests run on the JVM with an in-memory implementation.
 */
interface SessionState {
    val tokenFlow: Flow<String?>
    val baseUrlFlow: Flow<String>
    val themeFlow: Flow<String>

    /** Servers this device has connected to, most recent first. */
    val savedServers: Flow<List<String>>

    suspend fun token(): String?
    suspend fun baseUrl(): String
    suspend fun theme(): String

    suspend fun saveToken(value: String)
    suspend fun clearToken()
    suspend fun saveBaseUrl(value: String)
    suspend fun rememberServer(apiBaseUrl: String)
    suspend fun saveTheme(value: String)
}
