package com.pfc.companion.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

private val Forest = Color(0xFF1F5C46)
private val ForestLight = Color(0xFF2F7A5D)
private val Mint = Color(0xFFCFE7DA)
private val Cream = Color(0xFFF7F4EC)
private val Ink = Color(0xFF17211C)
private val Clay = Color(0xFFB4552F)

private val LightColors = lightColorScheme(
    primary = Forest,
    onPrimary = Color.White,
    primaryContainer = Mint,
    onPrimaryContainer = Color(0xFF0C2A20),
    secondary = Clay,
    onSecondary = Color.White,
    background = Cream,
    onBackground = Ink,
    surface = Color(0xFFFDFCF8),
    onSurface = Ink,
    surfaceVariant = Color(0xFFEDE8DC),
    onSurfaceVariant = Color(0xFF4B544C),
    outline = Color(0xFFBFC6BA),
    error = Color(0xFF9B2C2C),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF8FD3B4),
    onPrimary = Color(0xFF04291C),
    primaryContainer = Color(0xFF17402F),
    onPrimaryContainer = Color(0xFFC6EEDC),
    secondary = Color(0xFFE7A585),
    onSecondary = Color(0xFF3B1608),
    background = Color(0xFF101613),
    onBackground = Color(0xFFE6EAE4),
    surface = Color(0xFF161D19),
    onSurface = Color(0xFFE6EAE4),
    surfaceVariant = Color(0xFF243029),
    onSurfaceVariant = Color(0xFFBFC9BF),
    outline = Color(0xFF4A574E),
    error = Color(0xFFF0A3A3),
)

val NumberStyle = TextStyle(
    fontFamily = FontFamily.Monospace,
    fontWeight = FontWeight.Medium,
    letterSpacing = (-0.5).sp,
)

@Composable
fun CompanionTheme(
    theme: String = "system",
    content: @Composable () -> Unit,
) {
    val dark = when (theme) {
        "light" -> false
        "dark" -> true
        else -> isSystemInDarkTheme()
    }
    MaterialTheme(
        colorScheme = if (dark) DarkColors else LightColors,
        typography = MaterialTheme.typography.copy(
            displaySmall = MaterialTheme.typography.displaySmall.copy(
                fontFamily = FontFamily.Serif,
                fontWeight = FontWeight.SemiBold,
            ),
            headlineSmall = MaterialTheme.typography.headlineSmall.copy(
                fontFamily = FontFamily.Serif,
                fontWeight = FontWeight.SemiBold,
            ),
        ),
        content = content,
    )
}
