package com.pfc.companion

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import com.pfc.companion.ui.CompanionApp
import com.pfc.companion.ui.theme.CompanionTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val theme by ServiceLocator.repository.themeFlow.collectAsState(initial = "system")
            CompanionTheme(theme = theme) {
                CompanionApp()
            }
        }
    }
}
