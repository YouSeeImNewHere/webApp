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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.quail.android.bugreport.NavPathHolder
import com.quail.android.csvimport.CsvImportDatabase
import com.quail.android.csvimport.CsvImportQueueScreen
import com.quail.android.csvimport.CsvImportRepository
import com.quail.android.csvimport.CsvImportViewModel
import com.quail.android.csvimport.CsvMappingSetupScreen
import com.quail.android.ui.screens.accountdetail.AccountDetailScreen
import com.quail.android.ui.screens.accountdetail.AccountDetailViewModel
import com.quail.android.ui.screens.accountdetail.shareTransactionsCsv
import com.quail.android.data.bugs.BugsDatabase
import com.quail.android.data.bugs.BugsRepository
import com.quail.android.data.fitness.FitnessDatabase
import com.quail.android.data.fitness.FitnessRepository
import com.quail.android.data.network.NetworkModule
import com.quail.android.data.projects.ProjectsDatabase
import com.quail.android.data.projects.ProjectsRepository
import com.quail.android.data.repository.AuthStore
import com.quail.android.data.repository.HomeRepository
import com.quail.android.data.repository.VehicleLocalStore
import com.quail.android.data.vehicle.VehicleOfflineDatabase
import com.quail.android.data.vehicle.VehicleOfflineRepository
import com.quail.android.ui.screens.admin.AdminScreen
import com.quail.android.ui.screens.admin.AdminViewModel
import com.quail.android.ui.screens.budget.BudgetScreen
import com.quail.android.ui.screens.budget.BudgetViewModel
import com.quail.android.ui.screens.bugs.BugsScreen
import com.quail.android.ui.screens.bugs.BugsViewModel
import com.quail.android.ui.screens.dashboard.DashboardScreen
import com.quail.android.ui.screens.dashboard.DashboardViewModel
import com.quail.android.ui.screens.fitness.FitnessActiveWorkoutScreen
import com.quail.android.ui.screens.fitness.FitnessAnalyticsScreen
import com.quail.android.ui.screens.fitness.FitnessCalendarScreen
import com.quail.android.ui.screens.fitness.FitnessScreen
import com.quail.android.ui.screens.fitness.FitnessSettingsScreen
import com.quail.android.ui.screens.fitness.FitnessViewModel
import com.quail.android.ui.screens.home.HomeScreen
import com.quail.android.ui.screens.home.HomeViewModel
import com.quail.android.ui.screens.home.NetWorthChartViewModel
import com.quail.android.ui.screens.login.LoginScreen
import com.quail.android.ui.screens.notifications.NotificationsScreen
import com.quail.android.ui.screens.notifications.NotificationsViewModel
import com.quail.android.ui.screens.projects.ProjectDetailScreen
import com.quail.android.ui.screens.projects.ProjectsScreen
import com.quail.android.ui.screens.projects.ProjectsViewModel
import com.quail.android.ui.screens.settings.DashboardSettingsScreen
import com.quail.android.ui.screens.settings.NotificationPrefsScreen
import com.quail.android.ui.screens.settings.SettingsScreen
import com.quail.android.ui.screens.settings.SettingsViewModel
import com.quail.android.ui.screens.vehicle.VehicleFuelHistoryScreen
import com.quail.android.ui.screens.vehicle.VehicleIssuesScreen
import com.quail.android.ui.screens.vehicle.VehicleNotificationsScreen
import com.quail.android.ui.screens.vehicle.VehicleProceduresScreen
import com.quail.android.ui.screens.vehicle.VehicleScreen
import com.quail.android.ui.screens.vehicle.VehicleSettingsScreen
import com.quail.android.ui.screens.vehicle.VehicleViewModel
import com.quail.android.ui.theme.QuailAndroidTheme
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

private const val ROUTE_LOGIN = "login"
private const val ROUTE_DASHBOARD = "dashboard"
private const val ROUTE_HOME = "home"
private const val ROUTE_VEHICLE = "vehicle"
private const val ROUTE_VEHICLE_PROCEDURES = "vehicle_procedures"
private const val ROUTE_VEHICLE_FUEL_HISTORY = "vehicle_fuel_history"
private const val ROUTE_VEHICLE_ISSUES = "vehicle_issues"
private const val ROUTE_VEHICLE_SETTINGS = "vehicle_settings"
private const val ROUTE_VEHICLE_NOTIFICATIONS = "vehicle_notifications"
private const val ROUTE_FITNESS = "fitness"
private const val ROUTE_FITNESS_ACTIVE_WORKOUT = "fitness_active_workout"
private const val ROUTE_FITNESS_SETTINGS = "fitness_settings"
private const val ROUTE_FITNESS_CALENDAR = "fitness_calendar"
private const val ROUTE_FITNESS_ANALYTICS = "fitness_analytics"
private const val ROUTE_BUGS = "bugs"
private const val ROUTE_PROJECTS = "projects"
private const val ROUTE_PROJECT_DETAIL = "project_detail/{clientId}"
private const val ROUTE_NOTIFICATIONS = "notifications"
private const val ROUTE_SETTINGS = "settings"
private const val ROUTE_DASHBOARD_SETTINGS = "dashboard_settings"
private const val ROUTE_NOTIFICATION_SETTINGS = "notification_settings"
private const val ROUTE_BUDGET = "budget"
private const val ROUTE_ADMIN = "admin"
private const val ROUTE_CSV_IMPORT_QUEUE = "csv_import_queue"
private const val ROUTE_CSV_MAPPING_SETUP = "csv_mapping_setup/{itemId}"
private const val ROUTE_ACCOUNT_DETAIL = "account_detail/{accountId}/{auditMode}"

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
    val vehicleOfflineRepository = remember { VehicleOfflineRepository(api, VehicleOfflineDatabase.getInstance(context), context) }
    val fitnessRepository = remember { FitnessRepository(api, FitnessDatabase.getInstance(context), context) }
    val bugsRepository = remember { BugsRepository(api, BugsDatabase.getInstance(context), context) }
    val projectsRepository = remember { ProjectsRepository(api, ProjectsDatabase.getInstance(context), context) }
    val csvImportRepository = remember { CsvImportRepository(api, CsvImportDatabase.getInstance(context), context) }
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
                onOpenFitness = { navController.navigate(ROUTE_FITNESS) },
                onOpenBugs = { navController.navigate(ROUTE_BUGS) },
                onOpenProjects = { navController.navigate(ROUTE_PROJECTS) },
                onOpenSettings = { navController.navigate(ROUTE_DASHBOARD_SETTINGS) },
                onOpenAdmin = { navController.navigate(ROUTE_ADMIN) },
            )
        }

        composable(ROUTE_BUGS) {
            val viewModel: BugsViewModel = viewModel(factory = BugsViewModel.Factory(bugsRepository))
            BugsScreen(viewModel = viewModel, onBack = { navController.popBackStack() })
        }

        composable(ROUTE_PROJECTS) {
            val viewModel: ProjectsViewModel = viewModel(factory = ProjectsViewModel.Factory(projectsRepository))
            ProjectsScreen(
                viewModel = viewModel,
                onOpenProject = { clientId -> navController.navigate("project_detail/$clientId") },
                onBack = { navController.popBackStack() },
            )
        }

        composable(ROUTE_PROJECT_DETAIL) { backStackEntry ->
            val parentEntry = remember(backStackEntry) { navController.getBackStackEntry(ROUTE_PROJECTS) }
            val viewModel: ProjectsViewModel = viewModel(parentEntry, factory = ProjectsViewModel.Factory(projectsRepository))
            val clientId = backStackEntry.arguments?.getString("clientId").orEmpty()
            ProjectDetailScreen(viewModel = viewModel, clientId = clientId, onBack = { navController.popBackStack() })
        }

        composable(ROUTE_FITNESS) {
            val viewModel: FitnessViewModel = viewModel(factory = FitnessViewModel.Factory(fitnessRepository))
            FitnessScreen(
                viewModel = viewModel,
                onStartWorkout = { navController.navigate(ROUTE_FITNESS_ACTIVE_WORKOUT) },
                onOpenSettings = { navController.navigate(ROUTE_FITNESS_SETTINGS) },
                onOpenCalendar = { navController.navigate(ROUTE_FITNESS_CALENDAR) },
                onOpenAnalytics = { navController.navigate(ROUTE_FITNESS_ANALYTICS) },
                onOpenDashboard = { navController.popBackStack(ROUTE_DASHBOARD, inclusive = false) },
            )
        }

        composable(ROUTE_FITNESS_SETTINGS) {
            val viewModel: FitnessViewModel = viewModel(factory = FitnessViewModel.Factory(fitnessRepository))
            FitnessSettingsScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
            )
        }

        composable(ROUTE_FITNESS_CALENDAR) {
            val viewModel: FitnessViewModel = viewModel(factory = FitnessViewModel.Factory(fitnessRepository))
            FitnessCalendarScreen(
                viewModel = viewModel,
                onOpenHome = { navController.popBackStack(ROUTE_FITNESS, inclusive = false) },
                onOpenSettings = { navController.navigate(ROUTE_FITNESS_SETTINGS) },
                onOpenAnalytics = { navController.navigate(ROUTE_FITNESS_ANALYTICS) },
                onOpenDashboard = { navController.popBackStack(ROUTE_DASHBOARD, inclusive = false) },
            )
        }

        composable(ROUTE_FITNESS_ANALYTICS) {
            val viewModel: FitnessViewModel = viewModel(factory = FitnessViewModel.Factory(fitnessRepository))
            FitnessAnalyticsScreen(
                viewModel = viewModel,
                onOpenHome = { navController.popBackStack(ROUTE_FITNESS, inclusive = false) },
                onOpenSettings = { navController.navigate(ROUTE_FITNESS_SETTINGS) },
                onOpenCalendar = { navController.navigate(ROUTE_FITNESS_CALENDAR) },
                onOpenDashboard = { navController.popBackStack(ROUTE_DASHBOARD, inclusive = false) },
            )
        }

        composable(ROUTE_FITNESS_ACTIVE_WORKOUT) { backStackEntry ->
            val parentEntry = remember(backStackEntry) { navController.getBackStackEntry(ROUTE_FITNESS) }
            val viewModel: FitnessViewModel = viewModel(parentEntry, factory = FitnessViewModel.Factory(fitnessRepository))
            FitnessActiveWorkoutScreen(
                viewModel = viewModel,
                onFinished = { navController.popBackStack() },
                onCancelled = { navController.popBackStack() },
            )
        }

        composable(ROUTE_VEHICLE) {
            val viewModel: VehicleViewModel = viewModel(factory = VehicleViewModel.Factory(vehicleOfflineRepository))
            VehicleScreen(
                viewModel = viewModel,
                onOpenProcedures = { navController.navigate(ROUTE_VEHICLE_PROCEDURES) },
                onOpenFuelHistory = { navController.navigate(ROUTE_VEHICLE_FUEL_HISTORY) },
                onOpenIssues = { navController.navigate(ROUTE_VEHICLE_ISSUES) },
                onOpenSettings = { navController.navigate(ROUTE_VEHICLE_SETTINGS) },
                onOpenNotifications = { navController.navigate(ROUTE_VEHICLE_NOTIFICATIONS) },
                onOpenDashboard = { navController.popBackStack(ROUTE_DASHBOARD, inclusive = false) },
            )
        }

        composable(ROUTE_VEHICLE_PROCEDURES) {
            val viewModel: VehicleViewModel = viewModel(factory = VehicleViewModel.Factory(vehicleOfflineRepository))
            VehicleProceduresScreen(
                viewModel = viewModel,
                onOpenHome = { navController.popBackStack(ROUTE_VEHICLE, inclusive = false) },
                onOpenIssues = { navController.navigate(ROUTE_VEHICLE_ISSUES) },
                onOpenSettings = { navController.navigate(ROUTE_VEHICLE_SETTINGS) },
                onOpenNotifications = { navController.navigate(ROUTE_VEHICLE_NOTIFICATIONS) },
                onOpenDashboard = { navController.popBackStack(ROUTE_DASHBOARD, inclusive = false) },
            )
        }

        composable(ROUTE_VEHICLE_FUEL_HISTORY) {
            val viewModel: VehicleViewModel = viewModel(factory = VehicleViewModel.Factory(vehicleOfflineRepository))
            VehicleFuelHistoryScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
            )
        }

        composable(ROUTE_VEHICLE_ISSUES) {
            val viewModel: VehicleViewModel = viewModel(factory = VehicleViewModel.Factory(vehicleOfflineRepository))
            VehicleIssuesScreen(
                viewModel = viewModel,
                onOpenHome = { navController.popBackStack(ROUTE_VEHICLE, inclusive = false) },
                onOpenProcedures = { navController.navigate(ROUTE_VEHICLE_PROCEDURES) },
                onOpenSettings = { navController.navigate(ROUTE_VEHICLE_SETTINGS) },
                onOpenNotifications = { navController.navigate(ROUTE_VEHICLE_NOTIFICATIONS) },
                onOpenDashboard = { navController.popBackStack(ROUTE_DASHBOARD, inclusive = false) },
            )
        }

        composable(ROUTE_VEHICLE_SETTINGS) {
            val viewModel: VehicleViewModel = viewModel(factory = VehicleViewModel.Factory(vehicleOfflineRepository))
            VehicleSettingsScreen(
                viewModel = viewModel,
                localStore = vehicleLocalStore,
                onBack = { navController.popBackStack() },
                onOpenNotifications = { navController.navigate(ROUTE_VEHICLE_NOTIFICATIONS) },
                onOpenHome = { navController.popBackStack(ROUTE_VEHICLE, inclusive = false) },
                onOpenProcedures = { navController.navigate(ROUTE_VEHICLE_PROCEDURES) },
                onOpenIssues = { navController.navigate(ROUTE_VEHICLE_ISSUES) },
                onOpenDashboard = { navController.popBackStack(ROUTE_DASHBOARD, inclusive = false) },
            )
        }

        composable(ROUTE_VEHICLE_NOTIFICATIONS) {
            val viewModel: VehicleViewModel = viewModel(factory = VehicleViewModel.Factory(vehicleOfflineRepository))
            VehicleNotificationsScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onOpenSettings = { navController.navigate(ROUTE_VEHICLE_SETTINGS) },
                onOpenHome = { navController.popBackStack(ROUTE_VEHICLE, inclusive = false) },
                onOpenProcedures = { navController.navigate(ROUTE_VEHICLE_PROCEDURES) },
                onOpenIssues = { navController.navigate(ROUTE_VEHICLE_ISSUES) },
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
                onOpenAccountDetail = { accountId, auditMode ->
                    navController.navigate("account_detail/$accountId/${if (auditMode) 1 else 0}")
                },
            )
        }

        composable(ROUTE_ACCOUNT_DETAIL) { backStackEntry ->
            val accountId = backStackEntry.arguments?.getString("accountId")?.toIntOrNull() ?: 0
            val auditMode = backStackEntry.arguments?.getString("auditMode") == "1"
            val detailViewModel: AccountDetailViewModel = viewModel(
                key = "account_detail_$accountId",
                factory = AccountDetailViewModel.Factory(repository, accountId, context),
            )
            val accountInfo by detailViewModel.accountInfo.collectAsState()
            androidx.compose.runtime.LaunchedEffect(auditMode) {
                if (auditMode) detailViewModel.toggleAuditMode()
            }
            AccountDetailScreen(
                api = api,
                viewModel = detailViewModel,
                accountName = accountInfo?.name ?: "Account",
                onBack = { navController.popBackStack() },
                onSwitchAccount = { newId, newAuditMode ->
                    navController.navigate("account_detail/$newId/${if (newAuditMode) 1 else 0}") {
                        popUpTo(ROUTE_ACCOUNT_DETAIL) { inclusive = true }
                    }
                },
                onShareCsv = { txs, accountName -> shareTransactionsCsv(context, txs, accountName) },
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
                onOpenCsvImportQueue = { navController.navigate(ROUTE_CSV_IMPORT_QUEUE) },
            )
        }

        composable(ROUTE_CSV_IMPORT_QUEUE) {
            val viewModel: CsvImportViewModel = viewModel(factory = CsvImportViewModel.Factory(api, csvImportRepository, context))
            CsvImportQueueScreen(
                viewModel = viewModel,
                onBack = { navController.popBackStack() },
                onSetupMapping = { item -> navController.navigate("csv_mapping_setup/${item.id}") },
            )
        }

        composable(ROUTE_CSV_MAPPING_SETUP) { backStackEntry ->
            val parentEntry = remember(backStackEntry) { navController.getBackStackEntry(ROUTE_CSV_IMPORT_QUEUE) }
            val viewModel: CsvImportViewModel = viewModel(parentEntry, factory = CsvImportViewModel.Factory(api, csvImportRepository, context))
            val itemId = backStackEntry.arguments?.getString("itemId").orEmpty()
            val items by viewModel.items.collectAsState()
            val item = items.find { it.id == itemId }
            if (item == null) {
                navController.popBackStack()
            } else {
                CsvMappingSetupScreen(
                    api = api,
                    repository = csvImportRepository,
                    item = item,
                    onBack = { navController.popBackStack() },
                    onSaved = { navController.popBackStack() },
                )
            }
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

    LaunchedEffect(Unit) {
        navController.currentBackStack.collect { stack ->
            NavPathHolder.current = stack.mapNotNull { it.destination.route }.joinToString(" > ")
        }
    }
}
