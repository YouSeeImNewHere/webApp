package com.quail.android.ui.screens.fitness

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.DEFAULT_EXERCISES
import com.quail.android.data.model.FitnessGoalTypeOption
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset

private fun LocalDate.toUtcMillis(): Long = atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()
private fun Long.toLocalDateUtc(): LocalDate = Instant.ofEpochMilli(this).atZone(ZoneOffset.UTC).toLocalDate()

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FitnessSheetHost(sheet: FitnessSheet, viewModel: FitnessViewModel, onDismiss: () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState()) {
        when (sheet) {
            is FitnessSheet.AddGoal -> AddGoalSheet(viewModel, onDismiss)
            is FitnessSheet.LogBodyweight -> LogBodyweightSheet(viewModel, onDismiss)
        }
    }
}

@Composable
private fun SheetScaffold(title: String, onDismiss: () -> Unit, content: @Composable () -> Unit) {
    Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
        Row(Modifier.fillMaxWidth().padding(bottom = 12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            IconButton(onClick = onDismiss) { Icon(Icons.Filled.Close, contentDescription = "Close") }
        }
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { content() }
    }
}

@Composable
private fun SaveButton(label: String, enabled: Boolean, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        color = if (enabled) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
        shape = RoundedCornerShape(14.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Text(
            label,
            fontWeight = FontWeight.Bold,
            color = if (enabled) Color.Black else QuailTextDim,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            modifier = Modifier.fillMaxWidth().padding(vertical = 14.dp),
        )
    }
}

// ---- Log bodyweight ----

@Composable
private fun LogBodyweightSheet(viewModel: FitnessViewModel, onDismiss: () -> Unit) {
    var weight by remember { mutableStateOf("") }

    SheetScaffold("Log Weight", onDismiss) {
        OutlinedTextField(
            value = weight,
            onValueChange = { weight = it.filter { c -> c.isDigit() || c == '.' } },
            label = { Text("Weight (kg)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        val kg = weight.toDoubleOrNull()
        SaveButton("Save", enabled = kg != null && kg > 0) {
            if (kg != null && kg > 0) {
                viewModel.logBodyweight(kg)
                onDismiss()
            }
        }
    }
}

// ---- Add goal ----

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AddGoalSheet(viewModel: FitnessViewModel, onDismiss: () -> Unit) {
    var title by remember { mutableStateOf("") }
    var goalType by remember { mutableStateOf(FitnessGoalTypeOption.entries.first()) }
    var showTypePicker by remember { mutableStateOf(false) }
    var targetExerciseId by remember { mutableStateOf<String?>(null) }
    var showExercisePicker by remember { mutableStateOf(false) }
    var targetReps by remember { mutableStateOf("") }
    var targetDate by remember { mutableStateOf(LocalDate.now().plusMonths(1)) }
    var showDatePicker by remember { mutableStateOf(false) }

    SheetScaffold("New Goal", onDismiss) {
        OutlinedTextField(value = title, onValueChange = { title = it }, label = { Text("Title") }, singleLine = true, modifier = Modifier.fillMaxWidth())

        Column {
            Text("Goal Type", color = QuailTextDim, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(bottom = 6.dp))
            Surface(onClick = { showTypePicker = !showTypePicker }, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
                Text(goalType.displayName, modifier = Modifier.padding(12.dp))
            }
            if (showTypePicker) {
                Column {
                    FitnessGoalTypeOption.entries.forEach { option ->
                        Surface(onClick = { goalType = option; showTypePicker = false }, color = Color.Transparent, modifier = Modifier.fillMaxWidth()) {
                            Text(option.displayName, modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp))
                        }
                    }
                }
            }
        }

        Column {
            Text("Target Exercise (optional)", color = QuailTextDim, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(bottom = 6.dp))
            Surface(onClick = { showExercisePicker = !showExercisePicker }, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
                Text(targetExerciseId?.let { id -> DEFAULT_EXERCISES.firstOrNull { it.id == id }?.name } ?: "None", modifier = Modifier.padding(12.dp))
            }
            if (showExercisePicker) {
                Column {
                    DEFAULT_EXERCISES.forEach { exercise ->
                        Surface(onClick = { targetExerciseId = exercise.id; showExercisePicker = false }, color = Color.Transparent, modifier = Modifier.fillMaxWidth()) {
                            Text(exercise.name, modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp))
                        }
                    }
                }
            }
        }

        OutlinedTextField(
            value = targetReps,
            onValueChange = { targetReps = it.filter(Char::isDigit) },
            label = { Text("Target reps (optional)") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        Surface(onClick = { showDatePicker = true }, color = QuailSurfaceRaised, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
            Row(Modifier.fillMaxWidth().padding(14.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Target date", color = QuailTextDim)
                Text(targetDate.toString(), fontWeight = FontWeight.SemiBold)
            }
        }

        SaveButton("Save Goal", enabled = title.isNotBlank()) {
            if (title.isNotBlank()) {
                viewModel.addGoal(title, goalType.name, targetExerciseId, targetReps.toIntOrNull(), null, targetDate.toString())
                onDismiss()
            }
        }
    }

    if (showDatePicker) {
        val pickerState = rememberDatePickerState(initialSelectedDateMillis = targetDate.toUtcMillis())
        DatePickerDialog(
            onDismissRequest = { showDatePicker = false },
            confirmButton = {
                TextButton(onClick = {
                    pickerState.selectedDateMillis?.let { targetDate = it.toLocalDateUtc() }
                    showDatePicker = false
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { showDatePicker = false }) { Text("Cancel") } },
        ) { DatePicker(state = pickerState) }
    }
}
