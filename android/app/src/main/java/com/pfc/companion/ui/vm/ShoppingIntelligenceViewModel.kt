package com.pfc.companion.ui.vm

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.pfc.companion.data.FinanceRepository
import com.pfc.companion.data.LocationSettings
import com.pfc.companion.data.ShoppingVisit
import com.pfc.companion.data.TrackedLocation
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

data class ShoppingIntelligenceState(
    val loading: Boolean = true,
    val settings: LocationSettings? = null,
    val locations: List<TrackedLocation> = emptyList(),
    val visits: List<ShoppingVisit> = emptyList(),
    val suggested: Int = 0,
    val error: String? = null,
    val busy: Boolean = false,
)

/**
 * Holds the Shopping Intelligence preferences the server owns, plus the tracked
 * places and visit history the user can edit. Device monitoring is applied by the
 * screen, which has the Context and the permission launchers.
 */
class ShoppingIntelligenceViewModel(
    private val repository: FinanceRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(ShoppingIntelligenceState())
    val state: StateFlow<ShoppingIntelligenceState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = _state.value.settings == null, error = null)
            runCatching {
                val settings = repository.locationSettings()
                val locations = repository.trackedLocations()
                val visits = repository.shoppingVisits()
                Triple(settings, locations, visits)
            }
                .onSuccess { (settings, locations, visits) ->
                    _state.value = _state.value.copy(
                        loading = false,
                        settings = settings,
                        locations = locations,
                        visits = visits.items,
                        suggested = visits.suggested,
                    )
                }
                .onFailure {
                    _state.value = _state.value.copy(
                        loading = false,
                        error = it.message ?: "Could not load Shopping Intelligence.",
                    )
                }
        }
    }

    fun patch(body: JsonObject) {
        viewModelScope.launch {
            _state.value = _state.value.copy(busy = true, error = null)
            runCatching { repository.updateLocationSettings(body) }
                .onSuccess { settings ->
                    _state.value = _state.value.copy(busy = false, settings = settings)
                }
                .onFailure {
                    _state.value = _state.value.copy(busy = false, error = it.message ?: "That did not save.")
                }
        }
    }

    fun setConsent(enabled: Boolean) {
        patch(
            buildJsonObject {
                put("location_features_opted_in", enabled)
                put("shopping_intelligence_enabled", enabled)
                if (!enabled) put("discovery_enabled", false)
            }
        )
    }

    fun setDiscovery(enabled: Boolean) = patch(buildJsonObject { put("discovery_enabled", enabled) })

    fun pause(minutes: Int) = patch(buildJsonObject { put("pause_minutes", minutes) })

    fun setQuietHours(start: String?, end: String?) {
        val body = buildJsonObject {
            put("quiet_hours_start", start)
            put("quiet_hours_end", end)
        }
        patch(body)
    }

    fun setCooldown(minutes: Int) = patch(buildJsonObject { put("notification_cooldown_minutes", minutes) })

    fun addLocation(name: String, merchant: String?, budget: String?) {
        val body = buildJsonObject {
            put("name", name)
            if (!merchant.isNullOrBlank()) put("merchant", merchant)
            if (!budget.isNullOrBlank()) put("monthly_budget", budget)
        }
        mutate { repository.createLocation(body) }
    }

    /** Promotes a detected visit to a tracked place, keeping its coordinates. */
    fun trackVisit(visit: ShoppingVisit, budget: String?) {
        val body = buildJsonObject {
            put("name", visit.businessName.ifBlank { "Detected place" })
            if (!budget.isNullOrBlank()) put("monthly_budget", budget)
            put("is_active", true)
        }
        viewModelScope.launch {
            _state.value = _state.value.copy(busy = true, error = null)
            runCatching { repository.createLocationFromVisit(visit.id, body) }
                .onSuccess {
                    _state.value = _state.value.copy(busy = false)
                    refresh()
                }
                .onFailure {
                    _state.value = _state.value.copy(busy = false, error = it.message ?: "Could not add that place.")
                }
        }
    }

    fun updateLocation(id: String, body: JsonObject) {
        viewModelScope.launch {
            _state.value = _state.value.copy(busy = true, error = null)
            runCatching { repository.updateLocation(id, body) }
                .onSuccess { refresh() }
                .onFailure {
                    _state.value = _state.value.copy(busy = false, error = it.message ?: "That did not save.")
                }
        }
    }

    fun deleteLocation(id: String) {
        mutate { repository.deleteLocation(id) }
    }

    fun ignoreVisit(id: String) {
        mutate { repository.ignoreVisit(id) }
    }

    fun deleteVisit(id: String) {
        mutate { repository.deleteVisit(id) }
    }

    fun clearHistory() {
        mutate { repository.clearVisits() }
    }

    private fun mutate(block: suspend () -> Unit) {
        viewModelScope.launch {
            _state.value = _state.value.copy(busy = true, error = null)
            runCatching { block() }
                .onSuccess { refresh() }
                .onFailure {
                    _state.value = _state.value.copy(busy = false, error = it.message ?: "That did not save.")
                }
        }
    }
}
