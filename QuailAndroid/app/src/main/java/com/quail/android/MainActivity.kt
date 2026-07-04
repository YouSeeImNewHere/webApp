package com.quail.android

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
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
import com.quail.android.data.network.NetworkModule
import com.quail.android.data.repository.AuthStore
import com.quail.android.data.repository.HomeRepository
import com.quail.android.data.repository.VehicleLocalStore
import com.quail.android.ui.screens.admin.AdminScreen
import com.quail.android.ui.screens.admin.AdminViewModel
import com.quail.android.ui.screens.budget.BudgetScreen
import com.quail.android.ui.screens.budget.BudgetViewModel
import com.quail.android.ui.screens.dashboard.DashboardScreen
import com.quail.android.ui.screens.dashboard.DashboardViewModel
import com.quail.android.ui.screens.home.HomeScreen
import com.quail.android.ui.screens.home.HomeViewModel
import com.quail.android.ui.screens.home.NetWorthChartViewModel
import com.quail.android.ui.screens.login.LoginScreen
import com.quail.android.ui.screens.notifications.NotificationsScreen
import com.quail.android.ui.screens.notifications.NotificationsViewModel
import com.quail.android.ui.screens.settings.DashboardSettingsScreen
import com.quail.android.ui.screens.settings.NotificationPrefsScreen
import com.quail.android.ui.screens.settings.SettingsScreen
import com.quail.android.ui.screens.settings.SettingsViewModel
import com.quail.android.ui.screens.vehicle.VehicleScreen
import com.quail.android.ui.screens.vehicle.VehicleViewModel
import com.quail.android.ui.theme.QuailAndroidTheme
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

private const val ROUTE_LOGIN = "login"
private const val ROUTE_DASHBOARD = "dashboard"
private const val ROUTE_HOME = "home"
private const val ROUTE_VEHICLE = "vehicle"
private const val ROUTE_NOTIFICATIONS = "notifications"
private const val ROUTE_SETTINGS = "settings"
private const val ROUTE_DASHBOARD_SETTINGS = "dashboard_settings"
private const val ROUTE_NOTIFICATION_SETTINGS = "notification_settings"
private const val ROUTE_BUDGET = "budget"
private const val ROUTE_ADMIN = "admin"

class MainActivity : ComponentActivity() {
    private lateinit var authStore: AuthStore
    private var navController: NavHostController? = null

    private val requestNotificationPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { /* no-op either way */ }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        authStore = AuthStore.getInstance(applicationContext)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = android.app.NotificationChannel(
                AppConfig.DEFAULT_NOTIFICATION_CHANNEL_ID,
                "Quail Alerts",
                android.app.NotificationManager.IMPORTANCE_HIGH,
            )
            getSystemService(android.app.NotificationManager::class.java).createNotificationChannel(channel)
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            requestNotificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }

        // Covers relaunching while already logged in; handleDeepLink() covers a fresh login.
        // No-ops silently (caught in registerFcmDeviceIfAvailable) if there's no session yet.
        registerFcmDeviceIfAvailable()

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
            registerFcmDeviceIfAvailable()
        }
    }

    /** onNewToken only fires when the FCM token is first minted or rotates —
     * not on every login — so the token generated before the user ever logs
     * in would otherwise never reach the backend. Called right after a
     * successful login to cover that gap. */
    private fun registerFcmDeviceIfAvailable() {
        com.google.firebase.messaging.FirebaseMessaging.getInstance().token
            .addOnCompleteListener { task ->
                val fcmToken = task.result ?: return@addOnCompleteListener
                lifecycleScope.launch {
                    try {
                        val repository = HomeRepository(NetworkModule.create(authStore))
                        repository.registerAndroidPushDevice(token = fcmToken, deviceName = Build.MODEL)
                    } catch (_: Exception) {
                        // Best-effort; QuailMessagingService.onNewToken will retry on next rotation.
                    }
                }
            }
    }
}

@Composable
private fun AppNav(navController: NavHostController, authStore: AuthStore) {
    val scope = rememberCoroutineScope()
    val context = androidx.compose.ui.platform.LocalContext.current
    val api = remember { NetworkModule.create(authStore) }
    val repository = remember { HomeRepository(api) }
    val vehicleLocalStore = remember { VehicleLocalStore.getInstance(context) }
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
                onOpenCar = { navController.navigate(ROUTE_VEHICLE) },
                onOpenSettings = { navController.navigate(ROUTE_DASHBOARD_SETTINGS) },
                onOpenAdmin = { navController.navigate(ROUTE_ADMIN) },
            )
        }

        composable(ROUTE_VEHICLE) {
            val viewModel: VehicleViewModel = viewModel(factory = VehicleViewModel.Factory(repository, vehicleLocalStore))
            VehicleScreen(
                viewModel = viewModel,
                onOpenDashboard = { navController.popBackStack(ROUTE_DASHBOARD, inclusive = false) },
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
