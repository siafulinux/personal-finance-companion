package com.pfc.companion.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.pfc.companion.ServiceLocator
import com.pfc.companion.ui.components.ErrorPane
import com.pfc.companion.ui.components.LoadingPane
import com.pfc.companion.ui.components.rememberScreenViewModel
import com.pfc.companion.ui.vm.TransactionFormViewModel

@Composable
fun TransactionFormScreen(
    transactionId: String?,
    onSaved: (String) -> Unit,
    onBack: () -> Unit,
) {
    val viewModel = rememberScreenViewModel("transaction-form-${transactionId ?: "new"}") {
        TransactionFormViewModel(ServiceLocator.repository, transactionId)
    }
    val state by viewModel.state.collectAsStateWithLifecycle()

    if (state.loading) {
        LoadingPane(if (transactionId == null) "Preparing the form" else "Loading transaction")
        return
    }

    if (state.accounts.isEmpty() && state.error != null) {
        Column(modifier = Modifier.fillMaxSize()) {
            ErrorPane(state.error ?: "Could not load the form.", onRetry = viewModel::load)
            TextButton(onClick = onBack) { Text("Back to ledger") }
        }
        return
    }

    Column(modifier = Modifier.fillMaxSize()) {
        TextButton(onClick = onBack, modifier = Modifier) {
            Text("← Back", style = MaterialTheme.typography.labelMedium)
        }
        TransactionFormContent(
            draft = state.draft,
            accounts = state.accounts,
            categories = state.categories,
            editing = state.editing,
            saving = state.saving,
            error = state.error,
            onChange = { viewModel.update { _ -> it } },
            onSubmit = { viewModel.submit(onSaved) },
            onCancel = onBack,
        )
    }
}
