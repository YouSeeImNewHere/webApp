package com.quail.android.ui.screens.fitness

import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.DirectionsRun
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.TrendingUp
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.DEFAULT_EXERCISES
import com.quail.android.data.model.DEFAULT_PROGRESSION_PATHS
import com.quail.android.data.model.FitnessGoalTypeOption
import com.quail.android.ui.overlay.AppOverlayHost
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import com.quail.android.bugreport.BugReportTopBarAction

private const val FITNESS_PROFILE_PREFS = "quail_fitness_profile"

/** Not private: also read by GoalSetupWizardViewModel to seed sensible
 * defaults for which training-plan goals to pre-select — the one place this
 * previously-inert Settings preference actually ties into the rest of the
 * app today. */
object FitnessProfilePrefs {
    fun get(context: Context) = context.getSharedPreferences(FITNESS_PROFILE_PREFS, Context.MODE_PRIVATE)

    fun primaryGoal(context: Context): FitnessGoalTypeOption =
        runCatching { FitnessGoalTypeOption.valueOf(get(context).getString("primary_goal", null) ?: "") }
            .getOrDefault(FitnessGoalTypeOption.MUSCLE_MASS)

    fun setPrimaryGoal(context: Context, goal: FitnessGoalTypeOption) {
        get(context).edit().putString("primary_goal", goal.name).apply()
    }

    fun ageYears(context: Context): Int = get(context).getInt("age_years", 25)
    fun setAgeYears(context: Context, value: Int) { get(context).edit().putInt("age_years", value).apply() }

    fun heightCm(context: Context): Int = get(context).getInt("height_cm", 175)
    fun setHeightCm(context: Context, value: Int) { get(context).edit().putInt("height_cm", value).apply() }

    /** 0=Beginner, 1=Novice, 2=Intermediate, 3=Advanced — mirrors FitnessProfileSheet's trainingYears picker on iOS. */
    fun experienceLevel(context: Context): Int = get(context).getInt("experience_level", 0)
    fun setExperienceLevel(context: Context, value: Int) { get(context).edit().putInt("experience_level", value).apply() }
}

private val EXPERIENCE_LABELS = listOf("Beginner (< 6 months)", "Novice (6–18 months)", "Intermediate (1.5–3 years)", "Advanced (3+ years)")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FitnessSettingsScreen(viewModel: FitnessViewModel, onBack: () -> Unit) {
    val context = LocalContext.current
    val data by viewModel.uiState.collectAsState()
    val garminState by viewModel.garminState.collectAsState()

    var primaryGoal by remember { mutableStateOf(FitnessProfilePrefs.primaryGoal(context)) }
    var ageYears by remember { mutableStateOf(FitnessProfilePrefs.ageYears(context)) }
    var heightCm by remember { mutableStateOf(FitnessProfilePrefs.heightCm(context)) }
    var experienceLevel by remember { mutableStateOf(FitnessProfilePrefs.experienceLevel(context)) }
    var showLogWeight by remember { mutableStateOf(false) }
    var showGarminConnect by remember { mutableStateOf(false) }
    var showCustomExerciseManager by remember { mutableStateOf(false) }
    var selectedExercise by remember { mutableStateOf<com.quail.android.data.model.Exercise?>(null) }
    var showProgressionPaths by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) { viewModel.refreshGarminStatus() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings", fontWeight = FontWeight.Bold) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back") } },
                actions = { BugReportTopBarAction() },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(12.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            item {
                SettingsSection("Profile") {
                    Text("Primary Goal", color = QuailTextDim, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(bottom = 6.dp))
                    Row(modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        FitnessGoalTypeOption.entries.forEach { option ->
                            Surface(
                                onClick = { primaryGoal = option; FitnessProfilePrefs.setPrimaryGoal(context, option) },
                                color = if (primaryGoal == option) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
                                shape = RoundedCornerShape(999.dp),
                            ) {
                                Text(
                                    option.displayName,
                                    color = if (primaryGoal == option) Color.Black else QuailTextDim,
                                    fontWeight = FontWeight.SemiBold,
                                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                                )
                            }
                        }
                    }

                    Row(modifier = Modifier.fillMaxWidth().padding(top = 14.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        StepperField(
                            label = "Age",
                            value = ageYears,
                            onChange = { ageYears = it.coerceIn(13, 99); FitnessProfilePrefs.setAgeYears(context, ageYears) },
                            modifier = Modifier.weight(1f),
                        )
                        StepperField(
                            label = "Height (cm)",
                            value = heightCm,
                            onChange = { heightCm = it.coerceIn(100, 250); FitnessProfilePrefs.setHeightCm(context, heightCm) },
                            step = 5,
                            modifier = Modifier.weight(1f),
                        )
                    }

                    Row(
                        modifier = Modifier.fillMaxWidth().padding(top = 14.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column {
                            Text("Weight", color = QuailTextDim, style = MaterialTheme.typography.labelMedium)
                            Text(
                                data?.latestBodyweightKg?.let { "%.1f kg".format(it) } ?: "Not logged",
                                fontWeight = FontWeight.SemiBold,
                                modifier = Modifier.padding(top = 2.dp),
                            )
                        }
                        Surface(onClick = { showLogWeight = true }, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
                            Text("Log Weight", color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp))
                        }
                    }

                    Text("Training Experience", color = QuailTextDim, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(top = 14.dp, bottom = 6.dp))
                    Column {
                        EXPERIENCE_LABELS.forEachIndexed { idx, label ->
                            Surface(
                                onClick = { experienceLevel = idx; FitnessProfilePrefs.setExperienceLevel(context, idx) },
                                color = if (experienceLevel == idx) QuailSurfaceRaised else Color.Transparent,
                                shape = RoundedCornerShape(10.dp),
                                modifier = Modifier.fillMaxWidth(),
                            ) {
                                Text(label, modifier = Modifier.padding(12.dp))
                            }
                        }
                    }
                }
            }

            item {
                SettingsSection("Health") {
                    SettingsRow(
                        icon = Icons.Filled.DirectionsRun,
                        title = "Garmin Connect",
                        subtitle = when (garminState) {
                            is GarminConnectState.Connected -> "Connected"
                            is GarminConnectState.Connecting -> "Connecting…"
                            is GarminConnectState.Disconnected -> "Tap to connect"
                            is GarminConnectState.NeedsMfa -> "Waiting for verification code"
                            is GarminConnectState.Error -> "Connection failed — tap to retry"
                            is GarminConnectState.Unknown -> "Checking…"
                        },
                    ) { showGarminConnect = true }
                }
            }

            item {
                SettingsSection("Library") {
                    SettingsRow(
                        icon = Icons.Filled.Person,
                        title = "Exercise Library",
                        subtitle = "${DEFAULT_EXERCISES.size + (data?.customExercises?.size ?: 0)} exercises · ${data?.customExercises?.size ?: 0} custom",
                    ) { showCustomExerciseManager = true }
                    HorizontalDivider(color = QuailSurfaceRaised, modifier = Modifier.padding(horizontal = 14.dp))
                    SettingsRow(icon = Icons.Filled.List, title = "Routines", subtitle = "${data?.routines?.size ?: 0} saved routines", onClick = null)
                    HorizontalDivider(color = QuailSurfaceRaised, modifier = Modifier.padding(horizontal = 14.dp))
                    SettingsRow(icon = Icons.Filled.TrendingUp, title = "Progression Paths", subtitle = "${DEFAULT_PROGRESSION_PATHS.size} paths") { showProgressionPaths = true }
                }
            }
        }
    }

    if (showLogWeight) {
        val content: @Composable () -> Unit = {
            LogBodyweightContent(viewModel) { showLogWeight = false }
        }
        SideEffect { AppOverlayHost.showBottomSheet(onDismissed = { showLogWeight = false }, content = content) }
        DisposableEffect(Unit) { onDispose { AppOverlayHost.dismiss() } }
    }

    if (showGarminConnect) {
        GarminConnectSheet(
            state = garminState,
            onDismiss = { showGarminConnect = false },
            onConnect = { email, password -> viewModel.connectGarmin(email, password) },
            onSubmitMfa = { sessionId, code -> viewModel.submitGarminMfa(sessionId, code) },
            onDisconnect = { viewModel.disconnectGarmin() },
        )
    }

    if (showCustomExerciseManager) {
        ExerciseLibrarySheet(
            allExercises = data?.allExercises ?: DEFAULT_EXERCISES,
            onDelete = { clientId -> viewModel.deleteCustomExercise(clientId) },
            onSelect = { exercise -> selectedExercise = exercise; showCustomExerciseManager = false },
            onDismiss = { showCustomExerciseManager = false },
        )
    }

    selectedExercise?.let { exercise ->
        ExerciseDetailSheet(
            exercise = exercise,
            sessions = data?.sessions ?: emptyList(),
            personalBest = personalBest(exercise.id, data?.sessions ?: emptyList()),
            onDelete = exercise.customClientId?.let { clientId -> { viewModel.deleteCustomExercise(clientId); selectedExercise = null } },
            onDismiss = { selectedExercise = null; showCustomExerciseManager = true },
        )
    }

    if (showProgressionPaths) {
        data?.let { ProgressionPathsSheet(it) { showProgressionPaths = false } }
    }
}

@Composable
private fun ProgressionPathsSheet(data: FitnessData, onDismiss: () -> Unit) {
    val content: @Composable () -> Unit = {
        Column(Modifier.verticalScroll(rememberScrollState()).fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
            Row(Modifier.fillMaxWidth().padding(bottom = 12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Progression Paths", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                IconButton(onClick = onDismiss) { Icon(Icons.Filled.Close, contentDescription = "Close") }
            }
            Text(
                "Your current step in each skill progression, based on your logged personal bests.",
                color = QuailTextDim,
                modifier = Modifier.padding(bottom = 12.dp),
            )
            ProgressionsSection(data)
        }
    }
    SideEffect { AppOverlayHost.showBottomSheet(onDismissed = onDismiss, content = content) }
    DisposableEffect(Unit) { onDispose { AppOverlayHost.dismiss() } }
}

@Composable
private fun SettingsSection(title: String, content: @Composable () -> Unit) {
    Column {
        Text(title.uppercase(), color = QuailTextDim, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(start = 4.dp, bottom = 6.dp))
        Surface(color = QuailSurface, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(14.dp)) { content() }
        }
    }
}

@Composable
private fun SettingsRow(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String, subtitle: String, onClick: (() -> Unit)?) {
    Surface(onClick = onClick ?: {}, color = Color.Transparent, modifier = Modifier.fillMaxWidth()) {
        Row(modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(end = 12.dp))
            Column {
                Text(title, fontWeight = FontWeight.SemiBold)
                Text(subtitle, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}

@Composable
private fun StepperField(label: String, value: Int, onChange: (Int) -> Unit, step: Int = 1, modifier: Modifier = Modifier) {
    Column(modifier = modifier) {
        Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 4.dp)) {
            IconButton(onClick = { onChange(value - step) }) { Text("–", color = QuailTextDim) }
            Text("$value", fontWeight = FontWeight.Bold)
            IconButton(onClick = { onChange(value + step) }) { Text("+", color = QuailTextDim) }
        }
    }
}

@Composable
private fun LogBodyweightContent(viewModel: FitnessViewModel, onDone: () -> Unit) {
    var weight by remember { mutableStateOf("") }
    Column(Modifier.verticalScroll(rememberScrollState()).fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
        Text("Log Weight", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.padding(bottom = 12.dp))
        OutlinedTextField(
            value = weight,
            onValueChange = { weight = it.filter { c -> c.isDigit() || c == '.' } },
            label = { Text("Weight (kg)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        val kg = weight.toDoubleOrNull()
        Surface(
            onClick = { if (kg != null && kg > 0) { viewModel.logBodyweight(kg); onDone() } },
            color = if (kg != null && kg > 0) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
            shape = RoundedCornerShape(14.dp),
            modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
        ) {
            Text(
                "Save",
                fontWeight = FontWeight.Bold,
                color = if (kg != null && kg > 0) Color.Black else QuailTextDim,
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(vertical = 14.dp),
            )
        }
    }
}

@Composable
private fun GarminConnectSheet(
    state: GarminConnectState,
    onDismiss: () -> Unit,
    onConnect: (String, String) -> Unit,
    onSubmitMfa: (String, String) -> Unit,
    onDisconnect: () -> Unit,
) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var mfaCode by remember { mutableStateOf("") }

    val content: @Composable () -> Unit = {
        Column(Modifier.verticalScroll(rememberScrollState()).fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
            Row(Modifier.fillMaxWidth().padding(bottom = 12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Garmin Connect", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                IconButton(onClick = onDismiss) { Icon(Icons.Filled.Close, contentDescription = "Close") }
            }

            when (state) {
                is GarminConnectState.Connected -> {
                    Text("Your Garmin account is connected. Recent runs sync in automatically.", color = QuailTextDim)
                    Surface(
                        onClick = onDisconnect,
                        color = QuailSurfaceRaised,
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
                    ) {
                        Text("Disconnect", textAlign = androidx.compose.ui.text.style.TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(vertical = 14.dp))
                    }
                }
                is GarminConnectState.NeedsMfa -> {
                    Text("Garmin sent you a verification code. Enter it below.", color = QuailTextDim, modifier = Modifier.padding(bottom = 12.dp))
                    OutlinedTextField(value = mfaCode, onValueChange = { mfaCode = it }, label = { Text("Verification code") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    Surface(
                        onClick = { if (mfaCode.isNotBlank()) onSubmitMfa(state.sessionId, mfaCode) },
                        color = MaterialTheme.colorScheme.primary,
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
                    ) {
                        Text("Verify", fontWeight = FontWeight.Bold, color = Color.Black, textAlign = androidx.compose.ui.text.style.TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(vertical = 14.dp))
                    }
                }
                else -> {
                    if (state is GarminConnectState.Error) {
                        Text(state.message, color = com.quail.android.ui.theme.QuailBadRed, modifier = Modifier.padding(bottom = 12.dp))
                    }
                    OutlinedTextField(value = email, onValueChange = { email = it }, label = { Text("Garmin email") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(
                        value = password,
                        onValueChange = { password = it },
                        label = { Text("Password") },
                        singleLine = true,
                        visualTransformation = androidx.compose.ui.text.input.PasswordVisualTransformation(),
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    )
                    val connecting = state is GarminConnectState.Connecting
                    Surface(
                        onClick = { if (!connecting && email.isNotBlank() && password.isNotBlank()) onConnect(email, password) },
                        color = MaterialTheme.colorScheme.primary,
                        shape = RoundedCornerShape(14.dp),
                        modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
                    ) {
                        if (connecting) {
                            Row(Modifier.fillMaxWidth().padding(vertical = 14.dp), horizontalArrangement = Arrangement.Center) {
                                CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp))
                            }
                        } else {
                            Text("Connect", fontWeight = FontWeight.Bold, color = Color.Black, textAlign = androidx.compose.ui.text.style.TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(vertical = 14.dp))
                        }
                    }
                }
            }
        }
    }
    SideEffect { AppOverlayHost.showBottomSheet(onDismissed = onDismiss, content = content) }
    DisposableEffect(Unit) { onDispose { AppOverlayHost.dismiss() } }
}

@Composable
private fun ExerciseLibrarySheet(
    allExercises: List<com.quail.android.data.model.Exercise>,
    onDelete: (String) -> Unit,
    onSelect: (com.quail.android.data.model.Exercise) -> Unit,
    onDismiss: () -> Unit,
) {
    val content: @Composable () -> Unit = {
        Column(Modifier.verticalScroll(rememberScrollState()).fillMaxWidth().padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
            Text("Exercise Library", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, modifier = Modifier.padding(bottom = 4.dp))
            Text("Tap an exercise to see how to perform it.", color = QuailTextDim, modifier = Modifier.padding(bottom = 12.dp))
            Column {
                allExercises.forEachIndexed { idx, exercise ->
                    Surface(onClick = { onSelect(exercise) }, color = Color.Transparent, modifier = Modifier.fillMaxWidth()) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column {
                                Text(exercise.name, fontWeight = FontWeight.SemiBold)
                                Text("${exercise.category.displayName} · ${exercise.difficulty.displayName}", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                            }
                            if (exercise.customClientId != null) {
                                Surface(onClick = { onDelete(exercise.customClientId) }, color = Color.Transparent) {
                                    Text("Delete", color = QuailTextDim)
                                }
                            }
                        }
                    }
                    if (idx < allExercises.size - 1) HorizontalDivider(color = QuailSurfaceRaised)
                }
            }
        }
    }
    SideEffect { AppOverlayHost.showBottomSheet(onDismissed = onDismiss, content = content) }
    DisposableEffect(Unit) { onDispose { AppOverlayHost.dismiss() } }
}
