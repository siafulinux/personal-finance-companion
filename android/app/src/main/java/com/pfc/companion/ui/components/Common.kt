package com.pfc.companion.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import com.pfc.companion.data.ExplanationLine
import com.pfc.companion.data.SafeToSpend
import com.pfc.companion.ui.theme.NumberStyle
import com.pfc.companion.util.formatDate
import com.pfc.companion.util.formatMoney
import com.pfc.companion.util.formatSignedMoney

sealed interface UiState<out T> {
    data object Loading : UiState<Nothing>
    data class Ready<T>(val data: T) : UiState<T>
    data class Failed(val message: String) : UiState<Nothing>
}

@Composable
inline fun <reified T : ViewModel> rememberScreenViewModel(
    key: String,
    crossinline create: () -> T,
): T {
    val instance = remember(key) { create() }
    val factory = remember(key) {
        object : ViewModelProvider.Factory {
            override fun <VM : ViewModel> create(modelClass: Class<VM>): VM =
                modelClass.cast(instance)!!
        }
    }
    return viewModel(key = key, factory = factory)
}

@Composable
fun SectionCard(
    modifier: Modifier = Modifier,
    title: String? = null,
    subtitle: String? = null,
    action: (@Composable () -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(24.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
    ) {
        Column(modifier = Modifier.padding(20.dp)) {
            if (title != null) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = title,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                        if (subtitle != null) {
                            Text(
                                text = subtitle,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    action?.invoke()
                }
                Spacer(Modifier.height(14.dp))
            }
            content()
        }
    }
}

enum class PillTone { Neutral, Positive, Warning, Danger }

@Composable
fun Pill(text: String, tone: PillTone = PillTone.Neutral) {
    val scheme = MaterialTheme.colorScheme
    val (background, foreground) = when (tone) {
        PillTone.Neutral -> scheme.surfaceVariant to scheme.onSurfaceVariant
        PillTone.Positive -> scheme.primaryContainer to scheme.onPrimaryContainer
        PillTone.Warning -> Color(0xFFF6E3C5) to Color(0xFF6B4410)
        PillTone.Danger -> Color(0xFFF7D6D3) to Color(0xFF7A1F19)
    }
    Surface(color = background, shape = RoundedCornerShape(50)) {
        Text(
            text = text.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            color = foreground,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 9.dp, vertical = 4.dp),
        )
    }
}

@Composable
fun MoneyText(
    amount: String,
    modifier: Modifier = Modifier,
    signed: Boolean = false,
    style: androidx.compose.ui.text.TextStyle = MaterialTheme.typography.bodyLarge,
    color: Color = MaterialTheme.colorScheme.onSurface,
) {
    Text(
        text = if (signed) formatSignedMoney(amount) else formatMoney(amount),
        modifier = modifier,
        style = style.merge(NumberStyle),
        color = color,
    )
}

@Composable
fun LoadingPane(label: String = "Loading your ledger") {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 48.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        CircularProgressIndicator()
        Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
fun ErrorPane(message: String, onRetry: (() -> Unit)? = null) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(
            text = "Something needs attention",
            style = MaterialTheme.typography.titleMedium,
        )
        Text(
            text = message,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        if (onRetry != null) {
            TextButton(onClick = onRetry) { Text("Try again") }
        }
    }
}

@Composable
fun EmptyMessage(title: String, body: String) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 24.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(title, style = MaterialTheme.typography.titleSmall)
        Text(
            body,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
fun SafeToSpendCard(
    data: SafeToSpend,
    modifier: Modifier = Modifier,
    showExplanation: Boolean = true,
) {
    val scheme = MaterialTheme.colorScheme
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(28.dp),
        colors = CardDefaults.cardColors(containerColor = scheme.primaryContainer),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .background(
                    Brush.linearGradient(
                        listOf(scheme.primaryContainer, scheme.surface),
                    )
                )
                .padding(22.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "SAFE TO SPEND",
                    style = MaterialTheme.typography.labelMedium,
                    color = scheme.onPrimaryContainer,
                    fontWeight = FontWeight.SemiBold,
                )
                if (data.payday != null) {
                    Pill("Until ${formatDate(data.payday)}")
                }
            }
            Spacer(Modifier.height(6.dp))
            Text(
                text = formatMoney(data.amount),
                style = MaterialTheme.typography.displaySmall.merge(NumberStyle),
                color = scheme.onPrimaryContainer,
            )
            Text(
                text = "Spendable now without touching bills, buffers or reserves.",
                style = MaterialTheme.typography.bodySmall,
                color = scheme.onSurfaceVariant,
            )

            Spacer(Modifier.height(16.dp))
            HorizontalDivider(color = scheme.outline.copy(alpha = 0.4f))
            Spacer(Modifier.height(12.dp))

            BreakdownRow("Available", data.eligibleBalance)
            BreakdownRow("Pending", "-${data.pendingDebits}")
            BreakdownRow("Bills reserved", "-${data.billReserves}")
            BreakdownRow("Buffer", "-${data.minimumBuffer}")
            BreakdownRow("Reserves", "-${data.explicitReserves}")

            if (data.warnings.isNotEmpty()) {
                Spacer(Modifier.height(12.dp))
                data.warnings.take(3).forEach { warning ->
                    Text(
                        text = "!  $warning",
                        style = MaterialTheme.typography.bodySmall,
                        color = scheme.error,
                    )
                }
            }

            if (showExplanation && data.explanation.isNotEmpty()) {
                Spacer(Modifier.height(12.dp))
                HorizontalDivider(color = scheme.outline.copy(alpha = 0.4f))
                Spacer(Modifier.height(10.dp))
                Text(
                    "HOW THIS IS CALCULATED",
                    style = MaterialTheme.typography.labelSmall,
                    color = scheme.onSurfaceVariant,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.height(6.dp))
                data.explanation.forEach { line -> ExplanationRow(line) }
            }
        }
    }
}

@Composable
private fun BreakdownRow(label: String, amount: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 3.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        MoneyText(amount, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun ExplanationRow(line: ExplanationLine) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(line.label, style = MaterialTheme.typography.bodySmall)
            if (!line.detail.isNullOrBlank()) {
                Text(
                    line.detail,
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
        MoneyText(
            line.amount,
            style = MaterialTheme.typography.bodySmall,
            color = when (line.kind) {
                "credit" -> MaterialTheme.colorScheme.primary
                "debit" -> MaterialTheme.colorScheme.error
                else -> MaterialTheme.colorScheme.onSurface
            },
        )
    }
}

@Composable
fun ScreenHeader(eyebrow: String, title: String, description: String? = null) {
    Column(modifier = Modifier.fillMaxWidth()) {
        Text(
            eyebrow.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.primary,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(4.dp))
        Text(title, style = MaterialTheme.typography.headlineSmall)
        if (description != null) {
            Spacer(Modifier.height(4.dp))
            Text(
                description,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
fun HorizontalGap(height: Int = 12) {
    Box(Modifier.height(height.dp))
}
