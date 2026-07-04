package com.quailcash.android

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.quailcash.android.data.network.NetworkModule
import com.quailcash.android.data.repository.AuthStore
import com.quailcash.android.data.repository.HomeRepository
import com.quailcash.android.ui.screens.admin.AdminScreen
import com.quailcash.android.ui.screens.admin.AdminViewModel
import com.quailcash.android.ui.screens.budget.BudgetScreen
import com.quailcash.android.ui.screens.budget.BudgetViewModel
import com.quailcash.android.ui.screens.dashboard.DashboardScreen
import com.quailcash.android.ui.screens.dashboard.DashboardViewModel
import com.quailcash.android.ui.screens.home.HomeScreen
import com.quailcash.android.ui.screens.home.HomeViewModel
import com.quailcash.android.ui.screens.home.NetWorthChartViewModel
import com.quailcash.android.ui.screens.login.LoginScreen
import com.quailcash.android.ui.screens.notifications.NotificationsScreen
import com.quailcash.android.ui.screens.notifications.NotificationsViewModel
import com.quailcash.android.ui.screens.settings.DashboardSettingsScreen
import com.quailcash.android.ui.screens.settings.NotificationPrefsScreen
import com.quailcash.android.ui.screens.settings.SettingsScreen
import com.quailcash.android.ui.screens.settings.SettingsViewModel
import com.quailcash.android.ui.theme.QuailAndroidTheme
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

private const val ROUTE_LOGIN = "login"
private const val ROUTE_DASHBOARD = "dashboard"
private const val ROUTE_HOME = "home"
private const val ROUTE_NOTIFICATIONS = "notifications"
private const val ROUTE_SETTINGS = "settings"
private const val ROUTE_DASHBOARD_SETTINGS = "dashboard_settings"
private const val ROUTE_NOTIFICATION_SETTINGS = "notification_settings"
private const val ROUTE_BUDGET = "budget"
private const val ROUTE_ADMIN = "admin"

class MainActivity : ComponentActivity() {
    private lateinit var authStore: AuthStore
    private var navController: NavHostController? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        authStore = AuthStore.getInstance(applicationContext)

        setContent {
            val nav = rememberNavController()
            navController = nav
            QuailAndroidTheme {
                AppNav(navController = nav, authStore = authStore)
            }

            LaunchedEffect(Unit) {
                intent?.let { handleDeepLink(it, nav) }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        navController?.let { handleDeepLink(intent, it) }
    }

    private fun handleDeepLink(intent: Intent, nav: NavHostController) {
        val uri: Uri = intent.data ?: return
        if (uri.scheme != AppConfig.AUTH_CALLBACK_SCHEME || uri.host != AppConfig.AUTH_CALLBACK_HOST) return

        val token = uri.getQueryParameter("token") ?: return
        val email = uri.getQueryParameter("email")
        val tenantId = uri.getQueryParameter("tenant_id")?.toIntOrNull()
        lifecycleScope.launch {
            authStore.save(token, email, tenantId)
            nav.navigate(ROUTE_DASHBOARD) { popUpTo(ROUTE_LOGIN) { inclusive = true } }
        }
    }
}

@Composable
private fun AppNav(navController: NavHostController, authStore: AuthStore) {
    val scope = rememberCoroutineScope()
    val api = remember { NetworkModule.create(authStore) }
    val repository = remember { HomeRepository(api) }
    val onSignOut: () -> Unit = {
        scope.launch {
            authStore.clear()
            navController.navigate(ROUTE_LOGIN) { popUpTo(ROUTE_LOGIN) { inclusive = true } }
        }
    }

    NavHost(navController = navController, startDestination = ROUTE_LOGIN) {
        composable(ROUTE_LOGIN) { LoginScreen() }

        composable(ROUTE_DASHBOARD) {
            val viewModel: DashboardViewModel = viewModel(factory = DashboardViewModel.Factory(repository))
            DashboardScreen(
                viewModel = viewModel,
                onOpenCash = { navController.navigate(ROUTE_HOME) },
                onOpenSettings = { navController.navigate(ROUTE_DASHBOARD_SETTINGS) },
                onOpenAdmin = { navController.navigate(ROUTE_ADMIN) },
            )
        }

        composable(ROUTE_ADMIN) {
            val viewModel: AdminViewModel = viewModel(factory = AdminViewModel.Factory(repository))
            AdminScreen(viewModel = viewModel, onBack = { navController.popBackStack() })
        }

        composable(ROUTE_HOME) {
            val viewModel: HomeViewModel = viewModel(factory = HomeViewModel.Factory(repository))
            val chartViewModel: NetWorthChartViewModel = viewModel(factory = NetWorthChartViewModel.Factory(repository))
            HomeScreen(
                viewModel = viewModel,
                chartViewModel = chartViewModel,
                repository = repository,
                onOpenDashboard = { navController.popBackStack(ROUTE_DASHBOARD, inclusive = false) },
                onOpenSettings = { navController.navigate(ROUTE_SETTINGS) },
                onOpenNotifications = { navController.navigate(ROUTE_NOTIFICATIONS) },
                onOpenBudget = { navController.navigate(ROUTE_BUDGET) },
            )
        }

        composable(ROUTE_NOTIFICATIONS) {
            val viewModel: NotificationsViewModel = viewModel(factory = NotificationsViewModel.Factory(repository))
            NotificationsScreen(viewModel = viewModel, onBack = { navController.popBackStack() })
        }

        composable(ROUTE_SETTINGS) {
            val viewModel: SettingsViewModel = viewModel(factory = SettingsViewModel.Factory(repository))
            SettingsScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onOpenNotificationSettings = { navController.navigate(ROUTE_NOTIFICATION_SETTINGS) },
            )
        }

        composable(ROUTE_DASHBOARD_SETTINGS) {
            DashboardSettingsScreen(
                onBack = { navController.popBackStack() },
                onOpenNotificationSettings = { navController.navigate(ROUTE_NOTIFICATION_SETTINGS) },
                onOpenAppSettings = { navController.navigate(ROUTE_SETTINGS) },
                onSignOut = onSignOut,
            )
        }

        composable(ROUTE_NOTIFICATION_SETTINGS) {
            val viewModel: SettingsViewModel = viewModel(factory = SettingsViewModel.Factory(repository))
            NotificationPrefsScreen(viewModel = viewModel, onBack = { navController.popBackStack() })
        }

        composable(ROUTE_BUDGET) {
            val viewModel: BudgetViewModel = viewModel(factory = BudgetViewModel.Factory(repository))
            BudgetScreen(viewModel = viewModel, onBack = { navController.popBackStack() })
        }
    }

    LaunchedEffect(Unit) {
        val session = authStore.session.first()
        if (session != null) {
            navController.navigate(ROUTE_DASHBOARD) { popUpTo(ROUTE_LOGIN) { inclusive = true } }
        }
    }
}
