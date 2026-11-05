package com.pfc.companion.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.DateRange
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.pfc.companion.ServiceLocator
import com.pfc.companion.data.ApiException
import com.pfc.companion.data.Profile
import com.pfc.companion.ui.components.LoadingPane
import com.pfc.companion.ui.screens.BillsScreen
import com.pfc.companion.ui.screens.BudgetsScreen
import com.pfc.companion.ui.screens.DashboardScreen
import com.pfc.companion.ui.screens.ImportScreen
import com.pfc.companion.ui.screens.LedgerScreen
import com.pfc.companion.ui.screens.LoginScreen
import com.pfc.companion.ui.screens.OnboardingScreen
import com.pfc.companion.ui.screens.SettingsScreen
import com.pfc.companion.ui.screens.ShoppingScreen
import com.pfc.companion.ui.screens.TransactionDetailScreen
import com.pfc.companion.ui.screens.TransactionFormScreen
import kotlinx.coroutines.launch

private sealed interface Session {
    data object Checking : Session
    data object SignedOut : Session
    data class NeedsOnboarding(val profile: Profile) : Session
    data object SignedIn : Session
}

private data class Destination(
    val route: String,
    val label: String,
    val icon: ImageVector,
)

private val destinations = listOf(
    Destination("home", "Home", Icons.Filled.Home),
    Destination("ledger", "Ledger", Icons.AutoMirrored.Filled.List),
    Destination("bills", "Bills", Icons.Filled.DateRange),
    Destination("budgets", "Budgets", Icons.Filled.Star),
    Destination("settings", "Settings", Icons.Filled.Settings),
)

@Composable
fun CompanionApp() {
    val repository = ServiceLocator.repository
    val token by repository.tokenFlow.collectAsState(initial = null)
    var sessionVersion by remember { mutableStateOf(0) }
    val session by androidx.compose.runtime.produceState<Session>(Session.Checking, token, sessionVersion) {
        if (token.isNullOrBlank()) {
            value = Session.SignedOut
            return@produceState
        }
        value = try {
            val profile = repository.profile()
            if (profile.user.onboardingCompletedAt == null) {
                Session.NeedsOnboarding(profile)
            } else {
                Session.SignedIn
            }
        } catch (err: ApiException) {
            if (err.status == 401) {
                repository.signOut()
                Session.SignedOut
            } else {
                // Keep the session and let the destination screen show its retry state.
                Session.SignedIn
            }
        } catch (_: Exception) {
            Session.SignedIn
        }
    }

    when (val current = session) {
        Session.Checking -> Box(Modifier.fillMaxSize().padding(32.dp)) { LoadingPane("Opening your ledger") }
        Session.SignedOut -> LoginScreen()
        is Session.NeedsOnboarding -> OnboardingScreen(
            profile = current.profile,
            onDone = { sessionVersion++ },
        )
        Session.SignedIn -> MainShell()
    }
}

@Composable
private fun MainShell() {
    val navController = rememberNavController()
    val scope = rememberCoroutineScope()
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination?.route
    var flash by remember { mutableStateOf<String?>(null) }

    Scaffold(
        bottomBar = {
            NavigationBar {
                destinations.forEach { destination ->
                    NavigationBarItem(
                        selected = currentRoute == destination.route,
                        onClick = {
                            navController.navigate(destination.route) {
                                popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(destination.icon, contentDescription = null) },
                        label = { Text(destination.label) },
                    )
                }
            }
        },
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = "home",
            modifier = Modifier.padding(padding),
        ) {
            composable("home") {
                DashboardScreen(
                    onOpenShopping = { navController.navigate("shopping") },
                    onOpenLedger = { navController.navigate("ledger") },
                )
            }
            composable("ledger") {
                LedgerScreen(
                    onAddTransaction = { navController.navigate("ledger/new") },
                    onImportCsv = { navController.navigate("ledger/import") },
                    onOpenTransaction = { id -> navController.navigate("ledger/detail/$id") },
                    flash = flash,
                    onFlashShown = { flash = null },
                )
            }
            composable("ledger/new") {
                TransactionFormScreen(
                    transactionId = null,
                    onSaved = { message ->
                        flash = message
                        navController.popBackStack("ledger", inclusive = false)
                    },
                    onBack = { navController.popBackStack() },
                )
            }
            composable("ledger/detail/{transactionId}") { entry ->
                val id = entry.arguments?.getString("transactionId").orEmpty()
                TransactionDetailScreen(
                    transactionId = id,
                    onEdit = { navController.navigate("ledger/edit/$id") },
                    onBack = { navController.popBackStack() },
                )
            }
            composable("ledger/edit/{transactionId}") { entry ->
                val id = entry.arguments?.getString("transactionId").orEmpty()
                TransactionFormScreen(
                    transactionId = id,
                    onSaved = { message ->
                        flash = message
                        navController.popBackStack("ledger", inclusive = false)
                    },
                    onBack = { navController.popBackStack() },
                )
            }
            composable("ledger/import") {
                ImportScreen(
                    onDone = { message ->
                        flash = message
                        navController.popBackStack("ledger", inclusive = false)
                    },
                    onBack = { navController.popBackStack() },
                )
            }
            composable("bills") { BillsScreen() }
            composable("budgets") { BudgetsScreen() }
            composable("shopping") {
                ShoppingScreen(onBack = { navController.popBackStack() })
            }
            composable("settings") {
                SettingsScreen(
                    onSignOut = { scope.launch { ServiceLocator.repository.logout() } },
                )
            }
        }
    }
}
