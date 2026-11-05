package com.pfc.companion.ui.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.pfc.companion.ServiceLocator
import com.pfc.companion.data.CsvUpload
import com.pfc.companion.data.ImportCommitResult
import com.pfc.companion.data.ImportPreviewRow
import com.pfc.companion.ui.components.ErrorPane
import com.pfc.companion.ui.components.LoadingPane
import com.pfc.companion.ui.components.PickerField
import com.pfc.companion.ui.components.Pill
import com.pfc.companion.ui.components.PillTone
import com.pfc.companion.ui.components.ScreenHeader
import com.pfc.companion.ui.components.SectionCard
import com.pfc.companion.ui.components.rememberScreenViewModel
import com.pfc.companion.ui.vm.ImportState
import com.pfc.companion.ui.vm.ImportViewModel
import com.pfc.companion.ui.vm.importMappingFields
import com.pfc.companion.ui.vm.mappingReady
import com.pfc.companion.util.formatMoney

@Composable
fun ImportScreen(
    onDone: (String) -> Unit,
    onBack: () -> Unit,
) {
    val viewModel = rememberScreenViewModel("import") { ImportViewModel(ServiceLocator.repository) }
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    var pickError by remember { mutableStateOf<String?>(null) }
    var confirmCommit by remember { mutableStateOf(false) }

    val filePicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        pickError = null
        runCatching { CsvUpload.fromUri(context, uri) }
            .onSuccess(viewModel::upload)
            .onFailure { pickError = it.message ?: "That file could not be read." }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        TextButton(onClick = onBack) { Text("← Ledger") }

        when {
            state.accountsLoading -> LoadingPane("Loading accounts")
            state.accounts.isEmpty() -> ErrorPane(
                "Add an account in the web app before importing a CSV.",
                onRetry = viewModel::loadAccounts,
            )
            state.result != null -> ResultContent(
                result = state.result!!,
                failed = state.failedRecords,
                onDone = {
                    val summary = state.result?.let {
                        "Imported ${it.imported} transaction(s) from ${state.upload?.import?.filename ?: "CSV"}."
                    } ?: "Import complete."
                    onDone(summary)
                },
                onAnother = viewModel::reset,
            )
            state.upload != null -> MappingContent(
                state = state,
                onMapping = viewModel::updateMapping,
                onRefreshPreview = viewModel::refreshPreview,
                onCommit = { confirmCommit = true },
                onReset = viewModel::reset,
                pickError = pickError ?: state.error,
                onPickAnother = {
                    filePicker.launch(arrayOf("text/csv", "text/comma-separated-values", "text/plain", "application/csv"))
                },
            )
            else -> UploadContent(
                state = state,
                pickError = pickError ?: state.error,
                onSelectAccount = viewModel::selectAccount,
                onChooseFile = {
                    pickError = null
                    filePicker.launch(arrayOf("text/csv", "text/comma-separated-values", "text/plain", "application/csv"))
                },
            )
        }
    }

    if (confirmCommit) {
        val preview = state.preview
        AlertDialog(
            onDismissRequest = { confirmCommit = false },
            title = { Text("Import these transactions?") },
            text = {
                Text(
                    "${preview?.summary?.ready ?: 0} transaction(s) will be added. " +
                        "Duplicates and invalid rows are skipped, and bill matching runs on the server afterwards."
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    confirmCommit = false
                    viewModel.commit()
                }) { Text("Import") }
            },
            dismissButton = {
                TextButton(onClick = { confirmCommit = false }) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun UploadContent(
    state: ImportState,
    pickError: String?,
    onSelectAccount: (String) -> Unit,
    onChooseFile: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        ScreenHeader(
            eyebrow = "Import",
            title = "Bring in a CSV",
            description = "Pick a file with the system document picker. Nothing is saved until you review and confirm the preview.",
        )

        SectionCard(title = "Step 1 · Account and file") {
            PickerField(
                label = "Import into account",
                selected = state.accounts.firstOrNull { it.id == state.selectedAccountId }?.name
                    ?: "Choose an account",
                options = state.accounts.map { it.id to it.name },
                modifier = Modifier.fillMaxWidth(),
                enabled = !state.uploading,
                onSelect = onSelectAccount,
            )
            Spacer(Modifier.height(12.dp))
            Button(
                onClick = onChooseFile,
                enabled = state.selectedAccountId.isNotBlank() && !state.uploading,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(if (state.uploading) "Uploading…" else "Choose CSV file")
            }
            if (state.uploading) {
                Spacer(Modifier.height(10.dp))
                if (state.uploadProgress != null) {
                    LinearProgressIndicator(
                        progress = { state.uploadProgress ?: 0f },
                        modifier = Modifier.fillMaxWidth(),
                    )
                } else {
                    LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                }
                Spacer(Modifier.height(6.dp))
                Text(
                    "Uploading ${(state.uploadProgress?.times(100))?.toInt() ?: 0}%",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Spacer(Modifier.height(10.dp))
            Text(
                "Up to 5 MB. The app reads only the file you pick — no storage permission is requested, and the bytes stream straight to your server.",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (pickError != null) {
                Spacer(Modifier.height(8.dp))
                Text(pickError, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }
        }

        SectionCard(title = "What happens next") {
            Text(
                "1. Preview every row with duplicate and error detection.\n" +
                    "2. Adjust the column mapping if needed.\n" +
                    "3. Confirm the import; matching bills are handled by the server.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun MappingContent(
    state: ImportState,
    onMapping: (String, String?) -> Unit,
    onRefreshPreview: () -> Unit,
    onCommit: () -> Unit,
    onReset: () -> Unit,
    pickError: String?,
    onPickAnother: () -> Unit,
) {
    val upload = state.upload ?: return
    val preview = state.preview
    val headers = state.headers

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text(upload.import.filename, style = MaterialTheme.typography.headlineSmall)
        Text(
            "${preview?.summary?.totalRows ?: upload.import.rowCount} row(s) detected · " +
                (headers.size.toString() + " column(s)"),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        if (preview != null) {
            SectionCard(title = "Preview") {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    Stat("Ready", preview.summary.ready.toString(), PillTone.Positive)
                    Stat("Duplicates", preview.summary.duplicates.toString(), PillTone.Warning)
                    Stat("Invalid", preview.summary.rejected.toString(), PillTone.Danger)
                }
                Spacer(Modifier.height(8.dp))
                Text(
                    "${formatMoney(preview.summary.readyTotal)} of transactions ready to import",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        SectionCard(
            title = "Map your columns",
            subtitle = "The server suggests mappings, but you stay in control.",
        ) {
            importMappingFields.forEach { field ->
                PickerField(
                    label = field.label + if (field.hint != null) " · ${field.hint}" else "",
                    selected = state.mapping[field.key] ?: "Not mapped",
                    options = listOf("" to "Not mapped") + headers.map { it to it },
                    modifier = Modifier.fillMaxWidth(),
                    onSelect = { value -> onMapping(field.key, value.ifBlank { null }) },
                )
                Spacer(Modifier.height(8.dp))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(
                    onClick = onRefreshPreview,
                    enabled = mappingReady(state.mapping) && !state.busy,
                    modifier = Modifier.weight(1f),
                ) {
                    Text(if (state.busy) "Updating…" else "Update preview")
                }
                OutlinedButton(onClick = onReset, modifier = Modifier.weight(1f)) {
                    Text("Start over")
                }
            }
            if (!mappingReady(state.mapping)) {
                Spacer(Modifier.height(6.dp))
                Text(
                    "Map a date, a description and an amount (or debit/credit columns) to continue.",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        if (pickError != null) {
            Text(pickError, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
        }

        if (preview != null) {
            SectionCard(title = "Rows", subtitle = "First ${minOf(preview.rows.size, 40)} shown") {
                preview.rows.take(40).forEachIndexed { index, row ->
                    if (index > 0) HorizontalDivider(Modifier.padding(vertical = 6.dp))
                    PreviewRow(row)
                }
                if (preview.rows.isEmpty()) {
                    Text("No rows matched this mapping.", style = MaterialTheme.typography.bodySmall)
                }
            }

            Button(
                onClick = onCommit,
                enabled = preview.summary.ready > 0 && !state.busy,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(
                    when {
                        state.busy -> "Importing…"
                        preview.summary.ready == 0 -> "Nothing ready to import"
                        else -> "Review and import ${preview.summary.ready} transaction(s)"
                    }
                )
            }
            TextButton(onClick = onPickAnother, modifier = Modifier.fillMaxWidth()) {
                Text("Choose a different file")
            }
        } else {
            SectionCard(title = "This file needs a mapping") {
                Text(
                    "The server could not auto-map these columns. Map the fields above and update the preview.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            TextButton(onClick = onPickAnother) { Text("Choose a different file") }
        }
    }
}

@Composable
private fun ResultContent(
    result: ImportCommitResult,
    failed: List<com.pfc.companion.data.ImportRecord>,
    onDone: () -> Unit,
    onAnother: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        ScreenHeader(
            eyebrow = "Import complete",
            title = "${result.imported} transaction(s) added",
            description = if (result.alreadyCommitted) {
                "This file was already committed earlier; nothing was duplicated."
            } else {
                "Balances, budgets and Safe-to-Spend now reflect these rows on the server."
            },
        )

        SectionCard {
            ResultRow("Imported", result.imported)
            ResultRow("Duplicates skipped", result.duplicates)
            ResultRow("Invalid rows", result.rejected)
            ResultRow("Bills automatically matched", result.autoMatched)
            ResultRow("Bill matches to review", result.suggestedMatches)
        }

        if (failed.isNotEmpty()) {
            SectionCard(title = "Rejected rows", subtitle = "These were not imported") {
                failed.take(20).forEach { record ->
                    Text(
                        "Row ${record.rowNumber}: ${record.reason ?: "invalid data"}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.padding(vertical = 2.dp),
                    )
                }
            }
        }

        Text(
            "Re-importing the same file is safe: the server fingerprints each row and skips duplicates. " +
                "Possible bill matches stay under Bills until you confirm them.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        Button(onClick = onDone, modifier = Modifier.fillMaxWidth()) { Text("View ledger") }
        OutlinedButton(onClick = onAnother, modifier = Modifier.fillMaxWidth()) {
            Text("Import another file")
        }
    }
}

@Composable
private fun Stat(label: String, value: String, tone: PillTone) {
    Column {
        Pill(label, tone)
        Spacer(Modifier.height(4.dp))
        Text(value, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun ResultRow(label: String, value: Int) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium)
        Text(value.toString(), style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun PreviewRow(row: ImportPreviewRow) {
    Column {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    row.description.ifBlank { "(empty description)" },
                    style = MaterialTheme.typography.bodyMedium,
                )
                Text(
                    listOfNotNull(row.date, row.merchant).joinToString(" · "),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Column(horizontalAlignment = androidx.compose.ui.Alignment.End) {
                Text(row.amount ?: "—", style = MaterialTheme.typography.bodyMedium)
                Pill(
                    row.status,
                    when (row.status) {
                        "ok" -> PillTone.Positive
                        "duplicate" -> PillTone.Warning
                        else -> PillTone.Danger
                    },
                )
            }
        }
        if (row.reason != null) {
            Text(
                row.reason,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.error,
            )
        }
    }
}
