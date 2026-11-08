package com.pfc.companion.ui.screens

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.pfc.companion.data.Category
import com.pfc.companion.data.IncomeDraft
import com.pfc.companion.data.IncomeSource
import com.pfc.companion.data.MerchantAlias
import com.pfc.companion.data.NotificationDraft
import com.pfc.companion.data.NotificationPreferences
import com.pfc.companion.data.Preferences
import com.pfc.companion.data.Profile
import com.pfc.companion.data.RulesDraft
import com.pfc.companion.ui.components.PickerField
import com.pfc.companion.ui.components.Pill
import com.pfc.companion.ui.components.PillTone
import com.pfc.companion.ui.components.SectionCard
import com.pfc.companion.ui.vm.IncomeEditorState
import com.pfc.companion.ui.vm.IncomeViewModel
import com.pfc.companion.ui.vm.TaxonomyViewModel
import com.pfc.companion.util.formatDate
import com.pfc.companion.util.formatMoney
import java.io.File
import java.time.LocalDate

/** A shortlist of zones: enough to move a ledger's day boundary, small enough to scroll. */
private val commonTimezones = listOf(
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Anchorage",
    "Pacific/Honolulu",
    "America/Toronto",
    "America/Mexico_City",
    "America/Sao_Paulo",
    "Europe/London",
    "Europe/Dublin",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Madrid",
    "Europe/Amsterdam",
    "Europe/Warsaw",
    "Europe/Athens",
    "Africa/Cairo",
    "Africa/Lagos",
    "Africa/Johannesburg",
    "Asia/Dubai",
    "Asia/Karachi",
    "Asia/Kolkata",
    "Asia/Bangkok",
    "Asia/Shanghai",
    "Asia/Tokyo",
    "Asia/Seoul",
    "Australia/Sydney",
    "Pacific/Auckland",
    "UTC",
)

private val categoryColors = listOf(
    "#0f6b5c" to "Teal",
    "#2f7a5d" to "Green",
    "#b4552f" to "Rust",
    "#9a6b16" to "Amber",
    "#5b5f9e" to "Indigo",
    "#8a3f6b" to "Plum",
    "#64748b" to "Slate",
)

private val incomeFrequencies = listOf(
    "weekly" to "Weekly",
    "biweekly" to "Every 2 weeks",
    "semimonthly" to "Twice a month",
    "monthly" to "Monthly",
    "irregular" to "Irregular",
)

/**
 * Display name and timezone. Both are collected during first-run setup, and both
 * stay editable: the timezone decides when "today" rolls over for bills and budgets.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProfileSection(profile: Profile, saving: Boolean, onSave: (String, String) -> Unit) {
    var name by remember(profile.user.id) { mutableStateOf(profile.user.displayName) }
    var zone by remember(profile.user.id) { mutableStateOf(profile.user.timezone) }
    val zones = remember(profile.user.timezone) {
        (listOf(profile.user.timezone) + commonTimezones).distinct()
    }

    SectionCard(title = "Profile", subtitle = "How the ledger addresses you and which day it calls today.") {
        OutlinedTextField(
            value = name,
            onValueChange = { name = it.take(120) },
            label = { Text("Display name") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(8.dp))
        Text(
            profile.user.email,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(10.dp))
        PickerField(
            label = "Timezone",
            selected = zone.replace('_', ' '),
            options = zones.map { it to it.replace('_', ' ') },
            modifier = Modifier.fillMaxWidth(),
            onSelect = { zone = it },
        )
        Spacer(Modifier.height(10.dp))
        Button(
            onClick = { onSave(name, zone) },
            enabled = !saving && name.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (saving) "Saving…" else "Save profile")
        }
    }
}

/** The deterministic Safe-to-Spend inputs. The server owns the arithmetic. */
@Composable
fun RulesSection(preferences: Preferences, saving: Boolean, onSave: (RulesDraft) -> Unit) {
    var draft by remember(preferences) { mutableStateOf(RulesDraft.from(preferences)) }

    SectionCard(
        title = "Safe-to-Spend rules",
        subtitle = "These change the calculation itself, not just its display.",
    ) {
        OutlinedTextField(
            value = draft.buffer,
            onValueChange = { draft = draft.copy(buffer = it.sanitizeDecimal()) },
            label = { Text("Minimum cash buffer") },
            supportingText = { Text("Money you never want to spend.") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(8.dp))
        OutlinedTextField(
            value = draft.horizon,
            onValueChange = { draft = draft.copy(horizon = it.sanitizeDigits(2)) },
            label = { Text("Horizon without payday (days)") },
            supportingText = { Text("Used when no payday is known; 1 to 60.") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = draft.autoMatchThreshold,
                onValueChange = { draft = draft.copy(autoMatchThreshold = it.sanitizeDecimal()) },
                label = { Text("Auto-match") },
                supportingText = { Text("0.85 = high confidence") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                modifier = Modifier.weight(1f),
            )
            OutlinedTextField(
                value = draft.suggestionThreshold,
                onValueChange = { draft = draft.copy(suggestionThreshold = it.sanitizeDecimal()) },
                label = { Text("Suggestion") },
                supportingText = { Text("Below this, none") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                modifier = Modifier.weight(1f),
            )
        }
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = draft.toleranceAmount,
                onValueChange = { draft = draft.copy(toleranceAmount = it.sanitizeDecimal()) },
                label = { Text("Amount tolerance") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                modifier = Modifier.weight(1f),
            )
            OutlinedTextField(
                value = draft.tolerancePercent,
                onValueChange = { draft = draft.copy(tolerancePercent = it.sanitizeDecimal()) },
                label = { Text("Percent tolerance") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                modifier = Modifier.weight(1f),
            )
        }
        Spacer(Modifier.height(8.dp))
        ToggleRow(
            label = "Subtract pending debits",
            description = "Pending card holds reduce Safe-to-Spend before they post.",
            checked = draft.includePending,
            onChange = { draft = draft.copy(includePending = it) },
        )
        ToggleRow(
            label = "Auto-match bills",
            description = "Only unique, high-confidence matches settle a bill without you.",
            checked = draft.autoMatch,
            onChange = { draft = draft.copy(autoMatch = it) },
        )
        Spacer(Modifier.height(10.dp))
        Button(
            onClick = { onSave(draft) },
            enabled = !saving,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (saving) "Saving…" else "Save rules")
        }
    }
}

@Composable
fun NotificationsSection(
    notifications: NotificationPreferences,
    timezone: String,
    saving: Boolean,
    onSave: (NotificationDraft, String) -> Unit,
) {
    var draft by remember(notifications) { mutableStateOf(NotificationDraft.from(notifications)) }

    SectionCard(title = "Notifications", subtitle = "What the server is allowed to tell you about.") {
        ToggleRow(
            label = "Shopping assistant",
            description = "Store checks used by the shopping screen.",
            checked = draft.shoppingAssistant,
            onChange = { draft = draft.copy(shoppingAssistant = it) },
        )
        ToggleRow(
            label = "Bill reminders",
            description = "Upcoming bills that are about to come due.",
            checked = draft.billReminders,
            onChange = { draft = draft.copy(billReminders = it) },
        )
        ToggleRow(
            label = "Low-money warnings",
            description = "When Safe-to-Spend approaches your buffer.",
            checked = draft.lowMoney,
            onChange = { draft = draft.copy(lowMoney = it) },
        )
        ToggleRow(
            label = "Favorite-store reminders",
            description = "Reserved for a later phase; stored but not sent yet.",
            checked = draft.favoriteStores,
            onChange = { draft = draft.copy(favoriteStores = it) },
        )
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = draft.quietStart,
                onValueChange = { draft = draft.copy(quietStart = it.take(5)) },
                label = { Text("Quiet from") },
                placeholder = { Text("22:00") },
                singleLine = true,
                modifier = Modifier.weight(1f),
            )
            OutlinedTextField(
                value = draft.quietEnd,
                onValueChange = { draft = draft.copy(quietEnd = it.take(5)) },
                label = { Text("Quiet until") },
                placeholder = { Text("07:00") },
                singleLine = true,
                modifier = Modifier.weight(1f),
            )
        }
        Text(
            "Location features are never enabled by this app; there is no GPS permission in the manifest.",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(10.dp))
        OutlinedButton(
            onClick = { onSave(draft, timezone) },
            enabled = !saving,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (saving) "Saving…" else "Save notifications")
        }
    }
}

/**
 * Income sources and their next payday.
 *
 * This is the data first-run setup collects. Changing the payday moves the end of
 * the Safe-to-Spend horizon, so it is a planning input, not a label.
 */
@Composable
fun IncomeSection(viewModel: IncomeViewModel, onMessage: (String) -> Unit) {
    val sources by viewModel.sources.collectAsStateWithLifecycle()
    val loading by viewModel.loading.collectAsStateWithLifecycle()
    val error by viewModel.error.collectAsStateWithLifecycle()
    val editor by viewModel.editor.collectAsStateWithLifecycle()

    SectionCard(
        title = "Income sources",
        subtitle = "The next payday ends the Safe-to-Spend horizon.",
        action = {
            TextButton(onClick = viewModel::startAdd) { Text("Add") }
        },
    ) {
        if (loading) {
            Text("Loading income…", style = MaterialTheme.typography.bodySmall)
        } else if (sources.isEmpty()) {
            Text(
                "No income recorded. Add a paycheck so the horizon ends at your next payday instead of a fixed window.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        } else {
            sources.forEachIndexed { index, source ->
                if (index > 0) HorizontalDivider(Modifier.padding(vertical = 8.dp))
                IncomeRow(
                    source = source,
                    onEdit = { viewModel.startEdit(source) },
                    onRemove = { viewModel.remove(source.id, onMessage) },
                )
            }
        }
        if (error != null) {
            Text(
                error!!,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
        }
    }

    IncomeEditorDialog(
        state = editor,
        onChange = viewModel::updateDraft,
        onSave = { viewModel.save(onMessage) },
        onDismiss = viewModel::closeEditor,
    )
}

@Composable
private fun IncomeRow(source: IncomeSource, onEdit: () -> Unit, onRemove: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                source.name,
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.Medium,
            )
            Text(
                listOfNotNull(
                    source.frequency.replace('_', ' '),
                    source.nextPayday?.let { "next ${formatDate(it)}" },
                    if (!source.isActive) "inactive" else null,
                ).joinToString(" · "),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(formatMoney(source.amount), style = MaterialTheme.typography.bodyLarge)
            Row {
                TextButton(onClick = onEdit) { Text("Edit") }
                TextButton(onClick = onRemove) { Text("Remove") }
            }
        }
    }
}

@Composable
private fun IncomeEditorDialog(
    state: IncomeEditorState,
    onChange: ((IncomeDraft) -> IncomeDraft) -> Unit,
    onSave: () -> Unit,
    onDismiss: () -> Unit,
) {
    if (!state.open) return
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (state.editingId == null) "Add income" else "Edit income") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = state.draft.name,
                    onValueChange = { value -> onChange { it.copy(name = value.take(120)) } },
                    label = { Text("Name") },
                    placeholder = { Text("Paycheck") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = state.draft.amount,
                    onValueChange = { value -> onChange { it.copy(amount = value.sanitizeDecimal()) } },
                    label = { Text("Take-home per paycheck") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                PickerField(
                    label = "Frequency",
                    selected = incomeFrequencies.firstOrNull { it.first == state.draft.frequency }?.second
                        ?: "Every 2 weeks",
                    options = incomeFrequencies,
                    modifier = Modifier.fillMaxWidth(),
                    onSelect = { value -> onChange { it.copy(frequency = value) } },
                )
                OutlinedTextField(
                    value = state.draft.nextPayday,
                    onValueChange = { value -> onChange { it.copy(nextPayday = value.take(10)) } },
                    label = { Text("Next payday") },
                    placeholder = { Text(LocalDate.now().toString()) },
                    supportingText = { Text("YYYY-MM-DD. Bills due before it are reserved.") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                if (state.editingId != null) {
                    ToggleRow(
                        label = "Active",
                        description = "Inactive income stops counting toward the horizon.",
                        checked = state.draft.isActive,
                        onChange = { checked -> onChange { it.copy(isActive = checked) } },
                    )
                }
                if (state.error != null) {
                    Text(
                        state.error!!,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onSave, enabled = !state.saving) {
                Text(if (state.saving) "Saving…" else "Save")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !state.saving) { Text("Cancel") }
        },
    )
}

/** Categories and merchant aliases: the inputs matching and budgets both read. */
@Composable
fun TaxonomySection(viewModel: TaxonomyViewModel) {
    val categories by viewModel.categories.collectAsStateWithLifecycle()
    val aliases by viewModel.aliases.collectAsStateWithLifecycle()
    val error by viewModel.error.collectAsStateWithLifecycle()
    val busy by viewModel.busy.collectAsStateWithLifecycle()

    var newCategory by remember { mutableStateOf("") }
    var color by remember { mutableStateOf(categoryColors.first().first) }
    var aliasText by remember { mutableStateOf("") }
    var aliasMerchant by remember { mutableStateOf("") }

    SectionCard(title = "Categories", subtitle = "Budgets and spending both group by these.") {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Bottom) {
            OutlinedTextField(
                value = newCategory,
                onValueChange = { newCategory = it.take(80) },
                label = { Text("New category") },
                singleLine = true,
                modifier = Modifier.weight(1f),
            )
            OutlinedButton(
                onClick = {
                    viewModel.createCategory(newCategory, color)
                    newCategory = ""
                },
                enabled = !busy && newCategory.isNotBlank(),
            ) {
                Text("Add")
            }
        }
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            categoryColors.forEach { (value, label) ->
                FilterChip(
                    selected = color == value,
                    onClick = { color = value },
                    label = { Text(label) },
                )
            }
        }
        Spacer(Modifier.height(10.dp))
        categories.forEachIndexed { index, category ->
            if (index > 0) HorizontalDivider(Modifier.padding(vertical = 6.dp))
            CategoryRow(
                category = category,
                busy = busy,
                onArchive = { viewModel.archiveCategory(category.id) },
                onDelete = { viewModel.deleteCategory(category.id) },
            )
        }

        Spacer(Modifier.height(14.dp))
        HorizontalDivider()
        Spacer(Modifier.height(12.dp))
        Text("Merchant aliases", style = MaterialTheme.typography.titleSmall)
        Text(
            "Teach matching that a statement descriptor is a known bill merchant.",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(
                value = aliasText,
                onValueChange = { aliasText = it.take(120) },
                label = { Text("Statement text") },
                placeholder = { Text("XFINITY") },
                singleLine = true,
                modifier = Modifier.weight(1f),
            )
            OutlinedTextField(
                value = aliasMerchant,
                onValueChange = { aliasMerchant = it.take(160) },
                label = { Text("Merchant") },
                placeholder = { Text("Comcast") },
                singleLine = true,
                modifier = Modifier.weight(1f),
            )
        }
        Spacer(Modifier.height(8.dp))
        OutlinedButton(
            onClick = {
                viewModel.createAlias(aliasText, aliasMerchant)
                aliasText = ""
                aliasMerchant = ""
            },
            enabled = !busy && aliasText.isNotBlank() && aliasMerchant.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Add alias")
        }
        Spacer(Modifier.height(8.dp))
        aliases.forEachIndexed { index, alias ->
            if (index > 0) HorizontalDivider(Modifier.padding(vertical = 6.dp))
            AliasRow(alias = alias, onRemove = { viewModel.deleteAlias(alias.id) })
        }
        if (error != null) {
            Spacer(Modifier.height(8.dp))
            Text(
                error!!,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error,
            )
        }
    }
}

@Composable
private fun CategoryRow(
    category: Category,
    busy: Boolean,
    onArchive: () -> Unit,
    onDelete: () -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(category.name, style = MaterialTheme.typography.bodyMedium)
            Text(
                category.kind,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (category.isArchived) {
                Pill("Archived", PillTone.Neutral)
            } else {
                TextButton(onClick = onArchive, enabled = !busy) { Text("Archive") }
            }
            TextButton(onClick = onDelete, enabled = !busy) { Text("Delete") }
        }
    }
}

@Composable
private fun AliasRow(alias: MerchantAlias, onRemove: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(alias.alias, style = MaterialTheme.typography.bodyMedium)
            Text(
                "matches ${alias.canonicalMerchant}",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        TextButton(onClick = onRemove) { Text("Remove") }
    }
}

/** Export and account deletion, matching what the web settings offer. */
@Composable
fun DataSection(
    saving: Boolean,
    onExport: () -> Unit,
    onDeleteAccount: (String, String) -> Unit,
) {
    var deleting by remember { mutableStateOf(false) }
    var password by remember { mutableStateOf("") }
    var confirmation by remember { mutableStateOf("") }

    SectionCard(title = "Your data", subtitle = "Export a complete copy, or delete the account.") {
        Text(
            "The export is the server's own JSON: accounts, transactions, budgets, bills, occurrences, matches, reserves, income and imports.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(10.dp))
        OutlinedButton(onClick = onExport, enabled = !saving, modifier = Modifier.fillMaxWidth()) {
            Text(if (saving) "Preparing export…" else "Export my data")
        }
        Spacer(Modifier.height(10.dp))
        OutlinedButton(
            onClick = { deleting = true },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Delete my account", color = MaterialTheme.colorScheme.error)
        }
    }

    if (deleting) {
        AlertDialog(
            onDismissRequest = { deleting = false },
            title = { Text("Delete this account permanently?") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        "Every account, transaction, budget, bill, import and export record will be removed from this server.",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    OutlinedTextField(
                        value = password,
                        onValueChange = { password = it },
                        label = { Text("Password") },
                        singleLine = true,
                        visualTransformation = PasswordVisualTransformation(),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                        modifier = Modifier.fillMaxWidth(),
                    )
                    OutlinedTextField(
                        value = confirmation,
                        onValueChange = { confirmation = it },
                        label = { Text("Type DELETE to confirm") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        deleting = false
                        onDeleteAccount(password, confirmation)
                        password = ""
                        confirmation = ""
                    },
                    enabled = confirmation == "DELETE" && password.isNotBlank(),
                ) { Text("Delete permanently") }
            },
            dismissButton = {
                TextButton(onClick = { deleting = false }) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun ToggleRow(
    label: String,
    description: String,
    checked: Boolean,
    onChange: (Boolean) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.bodyMedium)
            Text(
                description,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Switch(checked = checked, onCheckedChange = onChange)
    }
}

/** Hands the export to whatever the user picks, from a cache file this app owns. */
fun shareExport(context: Context, json: String) {
    val directory = File(context.cacheDir, "exports").apply { mkdirs() }
    val file = File(directory, "finance-export-${LocalDate.now()}.json")
    file.writeText(json)
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = "application/json"
        putExtra(Intent.EXTRA_STREAM, uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(Intent.createChooser(intent, "Export your data"))
}

/** Keeps typing stable: invalid characters are dropped rather than the field clearing. */
private fun String.sanitizeDecimal(): String {
    val cleaned = filter { it.isDigit() || it == '.' }
    val whole = cleaned.substringBefore('.').take(9)
    if (!cleaned.contains('.')) return whole
    val fraction = cleaned.substringAfter('.').filter(Char::isDigit).take(2)
    return "$whole.$fraction"
}

private fun String.sanitizeDigits(max: Int): String = filter(Char::isDigit).take(max)
