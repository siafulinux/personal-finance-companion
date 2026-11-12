package com.pfc.companion.ui.screens

import android.Manifest
import android.content.Context
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.pfc.companion.ServiceLocator
import com.pfc.companion.data.ShoppingVisit
import com.pfc.companion.data.TrackedLocation
import com.pfc.companion.location.ShoppingMonitoring
import com.pfc.companion.ui.components.EmptyMessage
import com.pfc.companion.ui.components.HorizontalGap
import com.pfc.companion.ui.components.LoadingPane
import com.pfc.companion.ui.components.Pill
import com.pfc.companion.ui.components.PillTone
import com.pfc.companion.ui.components.ScreenHeader
import com.pfc.companion.ui.components.SectionCard
import com.pfc.companion.ui.components.rememberScreenViewModel
import com.pfc.companion.ui.vm.ShoppingIntelligenceViewModel
import com.pfc.companion.util.formatDate
import com.pfc.companion.util.formatMoney
import kotlinx.coroutines.launch
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Shopping Intelligence: consent, the places being watched, and the visit history.
 *
 * Location is opt-in and every switch here is reversible. The permission prompts
 * are asked for in the order Android requires — foreground, then background after
 * the user has already granted the first — and refusing any of them leaves the rest
 * of the app untouched.
 */
@Composable
fun ShoppingIntelligenceScreen(onBack: () -> Unit) {
    val context = LocalContext.current
    val viewModel = rememberScreenViewModel("shopping-intelligence") {
        ShoppingIntelligenceViewModel(ServiceLocator.repository)
    }
    val state by viewModel.state.collectAsState()
    val scope = rememberCoroutineScope()

    var permissionNote by remember { mutableStateOf<String?>(null) }
    var addingPlace by remember { mutableStateOf(false) }
    var trackingVisit by remember { mutableStateOf<ShoppingVisit?>(null) }
    var confirmingClear by remember { mutableStateOf(false) }

    val foregroundLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { granted ->
        val fine = granted[Manifest.permission.ACCESS_FINE_LOCATION] == true ||
            granted[Manifest.permission.ACCESS_COARSE_LOCATION] == true
        if (!fine) {
            permissionNote = "Without location access the app cannot tell when you arrive somewhere. " +
                "Everything else keeps working."
            return@rememberLauncherForActivityResult
        }
        permissionNote = null
        viewModel.setConsent(true)
        rearm(context, viewModel, scope)
    }
    val backgroundLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            permissionNote = null
            rearm(context, viewModel, scope)
        } else {
            permissionNote = "Background access is still off, so arrivals are only noticed while the app is open."
        }
    }
    val notificationLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { }

    LaunchedEffect(Unit) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            notificationLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    val settings = state.settings

    Column(Modifier.fillMaxSize().padding(20.dp)) {
        TextButton(onClick = onBack) { Text("Back") }
        if (state.loading) {
            LoadingPane("Loading Shopping Intelligence")
            return@Column
        }
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            item {
                ScreenHeader(
                    eyebrow = "Shopping Check",
                    title = "Shopping Intelligence",
                    description = "Guidance when you arrive somewhere — from your own finances, " +
                        "not from a guess about what you might buy.",
                )
            }
            state.error?.let { message ->
                item {
                    Text(message, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                }
            }
            permissionNote?.let { note ->
                item {
                    SectionCard(title = "Permissions") {
                        Text(note, style = MaterialTheme.typography.bodySmall)
                        TextButton(onClick = {
                            foregroundLauncher.launch(
                                arrayOf(
                                    Manifest.permission.ACCESS_FINE_LOCATION,
                                    Manifest.permission.ACCESS_COARSE_LOCATION,
                                )
                            )
                        }) { Text("Try again") }
                    }
                }
            }

            item {
                SectionCard(
                    title = "Location features",
                    subtitle = if (settings?.optedIn == true) "On for this account" else "Off",
                ) {
                    ToggleRow(
                        label = "Use my location in Shopping Check",
                        checked = settings?.optedIn == true,
                        enabled = !state.busy,
                        onChange = { wanted ->
                            if (!wanted) {
                                viewModel.setConsent(false)
                                scope.launch { ShoppingMonitoring.stop(context) }
                            } else {
                                foregroundLauncher.launch(
                                    arrayOf(
                                        Manifest.permission.ACCESS_FINE_LOCATION,
                                        Manifest.permission.ACCESS_COARSE_LOCATION,
                                    )
                                )
                            }
                        },
                    )
                    ToggleRow(
                        label = "Watch the places I saved",
                        checked = settings?.enabled == true,
                        enabled = !state.busy && settings?.optedIn == true,
                        onChange = { wanted ->
                            viewModel.patch(
                                buildJsonObject {
                                    put("shopping_intelligence_enabled", wanted)
                                }
                            )
                        },
                    )
                    ToggleRow(
                        label = "Discover new places",
                        checked = settings?.discoveryEnabled == true,
                        enabled = !state.busy && settings?.enabled == true,
                        onChange = { wanted ->
                            viewModel.setDiscovery(wanted)
                            scope.launch {
                                val current = state.settings
                                if (wanted && current != null) {
                                    ShoppingMonitoring.applySettings(context, current)
                                    runCatching { ShoppingMonitoring.registerActivityTransitions(context) }
                                } else {
                                    runCatching { ShoppingMonitoring.removeActivityTransitions(context) }
                                }
                            }
                        },
                    )
                    if (settings?.paused == true) {
                        HorizontalGap(6)
                        Pill("Paused", PillTone.Warning)
                        TextButton(onClick = { viewModel.pause(0) }) { Text("Resume now") }
                    } else {
                        TextButton(onClick = { viewModel.pause(120) }) { Text("Pause for 2 hours") }
                    }
                    if (!ShoppingMonitoring.hasBackgroundLocation(context)) {
                        TextButton(onClick = {
                            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                                backgroundLauncher.launch(Manifest.permission.ACCESS_BACKGROUND_LOCATION)
                            }
                        }) { Text("Allow arrivals in the background") }
                    }
                    Text(
                        "Saved places use Android geofences, which cost almost nothing. New places " +
                            "are only looked for when movement stops, using a single balanced fix.",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            item {
                SectionCard(
                    title = "Notifications",
                    subtitle = "At most one per ${settings?.cooldownMinutes ?: 120} minutes",
                ) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf(30, 60, 120, 240).forEach { minutes ->
                            TextButton(onClick = { viewModel.setCooldown(minutes) }) {
                                Text((if (settings?.cooldownMinutes == minutes) "• " else "") + "${minutes}m")
                            }
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        listOf("22:00" to "07:00", "21:00" to "08:00", null to null).forEach { window ->
                            TextButton(onClick = { viewModel.setQuietHours(window.first, window.second) }) {
                                Text(
                                    when {
                                        window.first == null -> "No quiet hours"
                                        settings?.quietStart == window.first && settings?.quietEnd == window.second ->
                                            "• ${window.first}–${window.second}"
                                        else -> "${window.first}–${window.second}"
                                    }
                                )
                            }
                        }
                    }
                    Text(
                        "History is kept for ${settings?.retentionDays ?: 90} days and can be cleared " +
                            "at any time.",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            item {
                SectionCard(
                    title = "Tracked places",
                    subtitle = "${state.locations.size} saved",
                    action = { TextButton(onClick = { addingPlace = true }) { Text("Add") } },
                ) {
                    if (state.locations.isEmpty()) {
                        EmptyMessage(
                            "No places yet",
                            "Add a store you visit often, or accept a suggestion the next time the " +
                                "app notices you somewhere new.",
                        )
                    }
                    state.locations.forEach { location ->
                        TrackedPlaceRow(
                            location = location,
                            busy = state.busy,
                            onToggle = { active ->
                                viewModel.updateLocation(location.id, buildJsonObject {
                                    put("is_active", active)
                                })
                                scope.launch { rearm(context, viewModel, scope) }
                            },
                            onToggleNotifications = { enabled ->
                                viewModel.updateLocation(location.id, buildJsonObject {
                                    put("notify_enabled", enabled)
                                })
                            },
                            onDelete = { viewModel.deleteLocation(location.id) },
                        )
                    }
                }
            }

            item {
                SectionCard(
                    title = "Visit history",
                    subtitle = if (state.suggested > 0) "${state.suggested} suggestion(s)" else "Recent arrivals",
                    action = {
                        if (state.visits.isNotEmpty()) {
                            TextButton(onClick = { confirmingClear = true }) { Text("Clear") }
                        }
                    },
                ) {
                    if (state.visits.isEmpty()) {
                        EmptyMessage(
                            "Nothing recorded",
                            "Visits appear here once you have arrived somewhere with the feature on.",
                        )
                    }
                    state.visits.forEach { visit ->
                        VisitRow(
                            visit = visit,
                            busy = state.busy,
                            onTrack = { trackingVisit = visit },
                            onIgnore = { viewModel.ignoreVisit(visit.id) },
                            onDelete = { viewModel.deleteVisit(visit.id) },
                        )
                    }
                }
            }

            item { Text("") }
        }
    }

    if (addingPlace) {
        PlaceDialog(
            onDismiss = { addingPlace = false },
            onSave = { name, merchant, budget ->
                viewModel.addLocation(name, merchant, budget)
                addingPlace = false
            },
        )
    }
    trackingVisit?.let { visit ->
        PlaceDialog(
            title = "Add ${visit.businessName}",
            initialName = visit.businessName,
            onDismiss = { trackingVisit = null },
            onSave = { _, _, budget ->
                viewModel.trackVisit(visit, budget)
                trackingVisit = null
            },
        )
    }
    if (confirmingClear) {
        AlertDialog(
            onDismissRequest = { confirmingClear = false },
            title = { Text("Clear visit history?") },
            text = {
                Text(
                    "This deletes every recorded visit on the server. Your tracked places, their " +
                        "budgets and your transactions are kept."
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    confirmingClear = false
                    viewModel.clearHistory()
                }) { Text("Clear history") }
            },
            dismissButton = { TextButton(onClick = { confirmingClear = false }) { Text("Cancel") } },
        )
    }
}

private fun rearm(context: Context, viewModel: ShoppingIntelligenceViewModel, scope: kotlinx.coroutines.CoroutineScope) {
    viewModel.refresh()
    scope.launch {
        val settings = runCatching { ServiceLocator.repository.locationSettings() }.getOrNull() ?: return@launch
        ShoppingMonitoring.applySettings(context, settings)
        if (!settings.enabled || !settings.optedIn) {
            ShoppingMonitoring.stop(context)
            return@launch
        }
        val places = runCatching { ServiceLocator.repository.trackedLocations() }.getOrDefault(emptyList())
        runCatching { ShoppingMonitoring.registerGeofences(context, places) }
        if (settings.discoveryEnabled) {
            runCatching { ShoppingMonitoring.registerActivityTransitions(context) }
        } else {
            runCatching { ShoppingMonitoring.removeActivityTransitions(context) }
        }
    }
}

@Composable
private fun ToggleRow(
    label: String,
    checked: Boolean,
    enabled: Boolean,
    onChange: (Boolean) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(end = 12.dp))
        Switch(checked = checked, onCheckedChange = onChange, enabled = enabled)
    }
}

@Composable
private fun TrackedPlaceRow(
    location: TrackedLocation,
    busy: Boolean,
    onToggle: (Boolean) -> Unit,
    onToggleNotifications: (Boolean) -> Unit,
    onDelete: () -> Unit,
) {
    Column(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Text(location.name, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
        Text(
            listOfNotNull(
                location.address ?: location.merchant,
                if (location.hasCoordinates) "geofenced" else "needs a location fix",
                "${location.visitCount} visits",
                location.monthSpend?.let { "${formatMoney(it)} this month" },
            ).joinToString(" · "),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        if (location.budgetRemaining != null) {
            Text(
                "${formatMoney(location.budgetRemaining)} left of ${formatMoney(location.monthlyBudget)}",
                style = MaterialTheme.typography.labelSmall,
            )
        }
        // FlowRow, not Row: two labelled switches plus Remove exceed a narrow card,
        // and a Row squeezes the trailing button's label mid-word. Flowing keeps each
        // control whole and wraps to a second line when it has to.
        FlowRow(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
            itemVerticalAlignment = Alignment.CenterVertically,
        ) {
            Text(if (location.isActive) "Watching" else "Paused", style = MaterialTheme.typography.labelSmall)
            Switch(checked = location.isActive, onCheckedChange = onToggle, enabled = !busy)
            Text("Notify", style = MaterialTheme.typography.labelSmall)
            Switch(checked = location.notifyEnabled, onCheckedChange = onToggleNotifications, enabled = !busy)
            TextButton(onClick = onDelete, enabled = !busy) { Text("Remove", maxLines = 1) }
        }
    }
}

@Composable
private fun VisitRow(
    visit: ShoppingVisit,
    busy: Boolean,
    onTrack: () -> Unit,
    onIgnore: () -> Unit,
    onDelete: () -> Unit,
) {
    Column(Modifier.fillMaxWidth().padding(vertical = 6.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(visit.businessName.ifBlank { "Unknown place" }, style = MaterialTheme.typography.bodyMedium)
            Text(formatDate(visit.visitedAt), style = MaterialTheme.typography.labelSmall)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            when (visit.status) {
                "suggested" -> Pill("New place", PillTone.Warning)
                "ignored" -> Pill("Ignored", PillTone.Neutral)
                "tracked" -> Pill("Tracked", PillTone.Positive)
                else -> Pill(visit.status.replaceFirstChar { it.uppercase() }, PillTone.Neutral)
            }
            if (visit.visitCount > 0) Pill("${visit.visitCount} visits", PillTone.Neutral)
            if (visit.transactionCount > 0) {
                Pill("${visit.transactionCount} purchases · ${formatMoney(visit.spendTotal)}", PillTone.Neutral)
            }
        }
        Text(
            if (visit.transactionCount > 0) {
                "A visit is not a purchase; these are matched transactions from your ledger."
            } else {
                "No matching transaction was found for this visit."
            },
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            if (visit.status != "tracked") {
                Button(onClick = onTrack, enabled = !busy) { Text("Add place") }
                TextButton(onClick = onIgnore, enabled = !busy) { Text("Ignore") }
            }
            TextButton(onClick = onDelete, enabled = !busy) { Text("Delete") }
        }
    }
}

@Composable
private fun PlaceDialog(
    title: String = "Add a place",
    initialName: String = "",
    onDismiss: () -> Unit,
    onSave: (String, String?, String?) -> Unit,
) {
    var name by remember { mutableStateOf(initialName) }
    var merchant by remember { mutableStateOf("") }
    var budget by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = merchant,
                    onValueChange = { merchant = it },
                    label = { Text("Merchant match (optional)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = budget,
                    onValueChange = { budget = it },
                    label = { Text("Monthly budget here (optional)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Text(
                    "A place without coordinates can be saved now and geofenced later from a visit.",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        },
        confirmButton = {
            TextButton(
                enabled = name.isNotBlank(),
                onClick = { onSave(name.trim(), merchant.ifBlank { null }, budget.ifBlank { null }) },
            ) { Text("Save") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}
