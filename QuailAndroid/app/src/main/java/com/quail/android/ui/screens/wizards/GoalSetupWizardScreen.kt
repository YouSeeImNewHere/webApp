package com.quail.android.ui.screens.wizards

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.bugreport.BugReportTopBarAction
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim

private val WEEKDAY_LABELS = listOf("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun GoalSetupWizardScreen(viewModel: GoalSetupWizardViewModel, onDone: () -> Unit, onBack: () -> Unit) {
    val form by viewModel.form.collectAsState()
    val submitState by viewModel.submitState.collectAsState()

    LaunchedEffect(submitState) {
        if (submitState is GoalSetupSubmitState.Done) onDone()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Set Up Training Plan", fontWeight = FontWeight.Bold) },
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
                Text(
                    "Pick your goals and we'll build a concrete weekly schedule toward all of them at once — starting with a short testing week to measure where you're at.",
                    color = QuailTextDim,
                )
            }

            item {
                SectionCard("Run longer distances") {
                    ToggleCell("Include this goal", form.includeRunDistance) { viewModel.updateForm { f -> f.copy(includeRunDistance = it) } }
                    if (form.includeRunDistance) {
                        TextCell("Target distance (km)", form.targetDistanceKm, numeric = true) {
                            viewModel.updateForm { f -> f.copy(targetDistanceKm = it) }
                        }
                    }
                }
            }

            item {
                SectionCard("Faster mile time") {
                    ToggleCell("Include this goal", form.includeRunPace) { viewModel.updateForm { f -> f.copy(includeRunPace = it) } }
                    if (form.includeRunPace) {
                        TextCell("Target mile pace (mm:ss)", form.targetMilePaceText) {
                            viewModel.updateForm { f -> f.copy(targetMilePaceText = it) }
                        }
                    }
                }
            }

            item {
                SectionCard("Push-ups") {
                    ToggleCell("Include this goal", form.includeMaxReps) { viewModel.updateForm { f -> f.copy(includeMaxReps = it) } }
                    if (form.includeMaxReps) {
                        TextCell("Target reps", form.targetReps, numeric = true) {
                            viewModel.updateForm { f -> f.copy(targetReps = it) }
                        }
                    }
                }
            }

            item {
                SectionCard("L-sit hold") {
                    ToggleCell("Include this goal", form.includeMaxHold) { viewModel.updateForm { f -> f.copy(includeMaxHold = it) } }
                    if (form.includeMaxHold) {
                        TextCell("Target hold (seconds)", form.targetHoldSeconds, numeric = true) {
                            viewModel.updateForm { f -> f.copy(targetHoldSeconds = it) }
                        }
                    }
                }
            }

            item {
                SectionCard("By when") {
                    TextCell("Target date (YYYY-MM-DD)", form.targetDateText) {
                        viewModel.updateForm { f -> f.copy(targetDateText = it) }
                    }
                }
            }

            item {
                SectionCard("Which days can you train?") {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) {
                        WEEKDAY_LABELS.forEachIndexed { index, label ->
                            val selected = index in form.weekdaysAvailable
                            Surface(
                                onClick = { viewModel.toggleWeekday(index) },
                                color = if (selected) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
                                shape = CircleShape,
                                modifier = Modifier.weight(1f),
                            ) {
                                Text(
                                    label,
                                    color = if (selected) Color.Black else Color.Unspecified,
                                    fontWeight = FontWeight.SemiBold,
                                    modifier = Modifier.padding(vertical = 10.dp),
                                    textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                                    style = MaterialTheme.typography.labelSmall,
                                )
                            }
                        }
                    }
                    Text(
                        "Mark unavailable days later on the Plan tab too — this is just your usual week.",
                        color = QuailTextDim,
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.padding(top = 8.dp),
                    )
                }
            }

            (submitState as? GoalSetupSubmitState.Error)?.let { error ->
                item { Text(error.message, color = QuailBadRed) }
            }

            item {
                Button(
                    onClick = { viewModel.submit() },
                    enabled = submitState !is GoalSetupSubmitState.Saving,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    if (submitState is GoalSetupSubmitState.Saving) {
                        CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp))
                    }
                    Text("Start My Testing Week")
                }
            }
        }
    }
}

@Composable
private fun SectionCard(title: String, content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(
            title.uppercase(),
            color = QuailTextDim,
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(start = 4.dp),
        )
        Surface(color = MaterialTheme.colorScheme.surface, shape = RoundedCornerShape(18.dp), modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp), content = content)
        }
    }
}

@Composable
private fun TextCell(label: String, value: String, numeric: Boolean = false, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = { text -> onChange(if (numeric) text.filter { it.isDigit() || it == '.' || it == '-' } else text) },
        label = { Text(label) },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun ToggleCell(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
        Text(label, style = MaterialTheme.typography.labelMedium, modifier = Modifier.weight(1f))
        Switch(checked = checked, onCheckedChange = onChange)
    }
}
