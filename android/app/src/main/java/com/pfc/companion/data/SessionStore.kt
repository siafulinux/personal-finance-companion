package com.pfc.companion.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import com.pfc.companion.BuildConfig
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore("companion_session")

/**
 * Local session state: the bearer token for the selected server, the API base URL,
 * the servers this device has used, and the chosen theme.
 *
 * Tokens are kept per server (see [SecureTokenStore]), so pointing the app at a
 * different installation never carries a session across, and coming back to an
 * earlier one keeps the user signed in. Nothing financial is stored on the device;
 * the ledger lives on the server.
 */
class SessionStore(context: Context) : SessionState {
    private val appContext = context.applicationContext
    private val store = appContext.dataStore
    private val secure = SecureTokenStore(appContext)

    /** Bumped on every token write so [tokenFlow] re-reads the book. */
    private val tokenEpoch = MutableStateFlow(0)

    private val baseUrlStream: Flow<String> = store.data
        .map { it[BASE_URL] ?: BuildConfig.API_BASE_URL }
        .distinctUntilChanged()

    override val baseUrlFlow: Flow<String> = baseUrlStream

    override val themeFlow: Flow<String> = store.data.map { it[THEME] ?: "system" }

    override val tokenFlow: Flow<String?> = combine(baseUrlStream, tokenEpoch) { base, _ ->
        // A pre-0.3 build stored one bare token; adopt it for the address it was used with.
        secure.migrateLegacy(base)
        secure.read(base)
    }.distinctUntilChanged()

    override val savedServers: Flow<List<String>> = store.data.map { prefs ->
        prefs[SAVED_SERVERS]
            ?.split('\n')
            ?.map { it.trim() }
            ?.filter { it.isNotEmpty() }
            ?.distinct()
            .orEmpty()
    }

    override suspend fun token(): String? {
        val base = baseUrl()
        secure.migrateLegacy(base)
        return secure.read(base)
    }

    override suspend fun baseUrl(): String = baseUrlFlow.first()

    override suspend fun theme(): String = themeFlow.first()

    override suspend fun saveToken(value: String) {
        secure.write(baseUrl(), value)
        tokenEpoch.value += 1
    }

    override suspend fun clearToken() {
        secure.clear(baseUrl())
        tokenEpoch.value += 1
    }

    override suspend fun saveBaseUrl(value: String) {
        val normalized = normalize(value)
        store.edit { it[BASE_URL] = normalized }
        rememberServer(normalized)
    }

    override suspend fun rememberServer(apiBaseUrl: String) {
        val normalized = normalize(apiBaseUrl)
        store.edit { prefs ->
            val current = prefs[SAVED_SERVERS]
                ?.split('\n')
                ?.map { it.trim() }
                ?.filter { it.isNotEmpty() }
                .orEmpty()
            val ordered = (listOf(normalized) + current.filter { it != normalized })
                .take(MAX_SAVED_SERVERS)
            prefs[SAVED_SERVERS] = ordered.joinToString("\n")
        }
    }

    override suspend fun saveTheme(value: String) {
        store.edit { it[THEME] = value }
    }

    /** Every stored address ends with a slash; the API client appends path segments. */
    private fun normalize(value: String): String = value.trim().let {
        if (it.endsWith("/")) it else "$it/"
    }

    private companion object {
        const val MAX_SAVED_SERVERS = 5
        val BASE_URL = stringPreferencesKey("api_base_url")
        val THEME = stringPreferencesKey("theme")
        val SAVED_SERVERS = stringPreferencesKey("saved_servers")
    }
}
