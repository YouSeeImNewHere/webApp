package com.quail.android.ui.screens.wizards

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.bugreport.BugReportTopBarAction
import com.quail.android.data.model.MonthBudget
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import java.text.NumberFormat
import java.time.DayOfWeek
import java.time.LocalDate
import java.util.Locale

private val currency: NumberFormat = NumberFormat.getCurrencyInstance(Locale.US)
private val INCOME_TYPES = listOf("les" to "LES", "salary" to "Salary", "hourly" to "Hourly")
private val FILING_STATUSES = listOf("S", "MFJ", "HOH")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun IncomeWizardScreen(viewModel: IncomeWizardViewModel, onBack: () -> Unit) {
    val incomeType by viewModel.incomeType.collectAsState()
    val lesState by viewModel.lesState.collectAsState()
    val lesForm by viewModel.lesForm.collectAsState()
    val savingLes by viewModel.savingLes.collectAsState()
    val lesMessage by viewModel.lesMessage.collectAsState()
    val keywordsText by viewModel.keywordsText.collectAsState()
    val savingKeywords by viewModel.savingKeywords.collectAsState()
    val keywordsMessage by viewModel.keywordsMessage.collectAsState()
    val weekdayPointsText by viewModel.weekdayPointsText.collectAsState()
    val weekendPointsText by viewModel.weekendPointsText.collectAsState()
    val savingWeights by viewModel.savingWeights.collectAsState()
    val weightsMessage by viewModel.weightsMessage.collectAsState()
    val monthBudget by viewModel.monthBudget.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Income Wizard", fontWeight = FontWeight.Bold) },
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
                SectionCard("Income Type") {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        INCOME_TYPES.forEach { (value, label) ->
                            Surface(
                                onClick = { viewModel.setIncomeType(value) },
                                color = if (incomeType == value) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
                                shape = RoundedCornerShape(999.dp),
                            ) {
                                Text(
                                    label,
                                    color = if (incomeType == value) Color.Black else Color.Unspecified,
                                    fontWeight = FontWeight.SemiBold,
                                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp),
                                )
                            }
                        }
                    }
                }
            }

            if (incomeType != "les") {
                item {
                    SectionCard(if (incomeType == "salary") "Salary" else "Hourly") {
                        Text(
                            "In progress — salary and hourly income setup aren't available yet. Switch to LES for military pay projections.",
                            color = QuailTextDim,
                        )
                    }
                }
            } else {
                item {
                    SectionCard("LES Income Profile") {
                        when (val s = lesState) {
                            is LesProfileUiState.Loading -> CircularProgressIndicator()
                            is LesProfileUiState.Error -> Text(s.message, color = QuailBadRed)
                            is LesProfileUiState.Success -> LesProfileForm(lesForm, viewModel)
                        }
                        Row(modifier = Modifier.padding(top = 14.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Surface(
                                onClick = { viewModel.saveLesProfile() },
                                enabled = !savingLes,
                                color = MaterialTheme.colorScheme.primary,
                                shape = RoundedCornerShape(10.dp),
                            ) {
                                Text("Save", modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp), fontWeight = FontWeight.Bold, color = Color.Black)
                            }
                            Surface(
                                onClick = { viewModel.resetLesToDefaults() },
                                enabled = !savingLes,
                                color = QuailSurfaceRaised,
                                shape = RoundedCornerShape(10.dp),
                            ) {
                                Text("Reset to defaults", modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp), fontWeight = FontWeight.SemiBold)
                            }
                        }
                        lesMessage?.let { Text(it, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 8.dp)) }
                    }
                }
            }

            item {
                SectionCard("Paycheck Matching") {
                    Text(
                        "One keyword per line — used to identify paycheck deposits in your transaction history.",
                        color = QuailTextDim,
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.padding(bottom = 8.dp),
                    )
                    OutlinedTextField(
                        value = keywordsText,
                        onValueChange = { viewModel.setKeywordsText(it) },
                        modifier = Modifier.fillMaxWidth(),
                        minLines = 4,
                    )
                    Surface(
                        onClick = { viewModel.saveKeywords() },
                        enabled = !savingKeywords,
                        color = MaterialTheme.colorScheme.primary,
                        shape = RoundedCornerShape(10.dp),
                        modifier = Modifier.padding(top = 10.dp),
                    ) {
                        Text("Save", modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp), fontWeight = FontWeight.Bold, color = Color.Black)
                    }
                    keywordsMessage?.let { Text(it, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 8.dp)) }
                }
            }

            item {
                SectionCard("Daily Spending Weights") {
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        OutlinedTextField(
                            value = weekdayPointsText,
                            onValueChange = { viewModel.setWeekdayPointsText(it.filter { c -> c.isDigit() || c == '.' }) },
                            label = { Text("Weekday points") },
                            singleLine = true,
                            modifier = Modifier.weight(1f),
                        )
                        OutlinedTextField(
                            value = weekendPointsText,
                            onValueChange = { viewModel.setWeekendPointsText(it.filter { c -> c.isDigit() || c == '.' }) },
                            label = { Text("Weekend points") },
                            singleLine = true,
                            modifier = Modifier.weight(1f),
                        )
                    }
                    Surface(
                        onClick = { viewModel.saveDailyWeights() },
                        enabled = !savingWeights,
                        color = MaterialTheme.colorScheme.primary,
                        shape = RoundedCornerShape(10.dp),
                        modifier = Modifier.padding(top = 10.dp),
                    ) {
                        Text("Save", modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp), fontWeight = FontWeight.Bold, color = Color.Black)
                    }
                    weightsMessage?.let { Text(it, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 8.dp)) }

                    DailyWeightsPreview(monthBudget, weekdayPointsText.toDoubleOrNull(), weekendPointsText.toDoubleOrNull())
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
            Column(Modifier.padding(14.dp), content = content)
        }
    }
}

@Composable
private fun FieldRow(first: @Composable () -> Unit, second: @Composable () -> Unit) {
    Row(modifier = Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        androidx.compose.foundation.layout.Box(Modifier.weight(1f)) { first() }
        androidx.compose.foundation.layout.Box(Modifier.weight(1f)) { second() }
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

@Composable
private fun LesProfileForm(form: LesFormState, viewModel: IncomeWizardViewModel) {
    FieldRow(
        { TextCell("Paygrade", form.paygrade) { viewModel.updateLesForm { s -> s.copy(paygrade = it) } } },
        { TextCell("Service start (YYYY-MM-DD)", form.serviceStart) { viewModel.updateLesForm { s -> s.copy(serviceStart = it) } } },
    )
    FieldRow(
        { ToggleCell("Has dependents", form.hasDependents) { viewModel.updateLesForm { s -> s.copy(hasDependents = it) } } },
        { TextCell("BAH override", form.bahOverride, numeric = true) { viewModel.updateLesForm { s -> s.copy(bahOverride = it) } } },
    )
    FieldRow(
        { TextCell("BAS", form.bas, numeric = true) { viewModel.updateLesForm { s -> s.copy(bas = it) } } },
        { TextCell("TSP rate (0-1)", form.tspRate, numeric = true) { viewModel.updateLesForm { s -> s.copy(tspRate = it) } } },
    )
    FieldRow(
        { TextCell("Mid-month fraction", form.midMonthFraction, numeric = true) { viewModel.updateLesForm { s -> s.copy(midMonthFraction = it) } } },
        { ToggleCell("FICA on special pays", form.ficaIncludeSpecialPays) { viewModel.updateLesForm { s -> s.copy(ficaIncludeSpecialPays = it) } } },
    )
    FieldRow(
        { TextCell("Submarine pay", form.submarinePay, numeric = true) { viewModel.updateLesForm { s -> s.copy(submarinePay = it) } } },
        { TextCell("Career sea pay", form.careerSeaPay, numeric = true) { viewModel.updateLesForm { s -> s.copy(careerSeaPay = it) } } },
    )
    FieldRow(
        { TextCell("Special duty pay", form.specDutyPay, numeric = true) { viewModel.updateLesForm { s -> s.copy(specDutyPay = it) } } },
        { TextCell("Extra withholding", form.extraWithholding, numeric = true) { viewModel.updateLesForm { s -> s.copy(extraWithholding = it) } } },
    )
    FieldRow(
        { ToggleCell("Meal deduction", form.mealDeductionEnabled) { viewModel.updateLesForm { s -> s.copy(mealDeductionEnabled = it) } } },
        { TextCell("Meal deduction start", form.mealDeductionStart) { viewModel.updateLesForm { s -> s.copy(mealDeductionStart = it) } } },
    )
    FieldRow(
        { TextCell("Meal rate", form.mealRate, numeric = true) { viewModel.updateLesForm { s -> s.copy(mealRate = it) } } },
        { TextCell("Meal end day", form.mealEndDay, numeric = true) { viewModel.updateLesForm { s -> s.copy(mealEndDay = it) } } },
    )
    FieldRow(
        { TextCell("Allotments total", form.allotmentsTotal, numeric = true) { viewModel.updateLesForm { s -> s.copy(allotmentsTotal = it) } } },
        { TextCell("Mid-month collections", form.midMonthCollectionsTotal, numeric = true) { viewModel.updateLesForm { s -> s.copy(midMonthCollectionsTotal = it) } } },
    )

    Text("Filing status", color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 12.dp, bottom = 6.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        FILING_STATUSES.forEach { status ->
            Surface(
                onClick = { viewModel.updateLesForm { s -> s.copy(filingStatus = status) } },
                color = if (form.filingStatus == status) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
                shape = RoundedCornerShape(999.dp),
            ) {
                Text(
                    status,
                    color = if (form.filingStatus == status) Color.Black else Color.Unspecified,
                    fontWeight = FontWeight.SemiBold,
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                )
            }
        }
    }

    FieldRow(
        { ToggleCell("W-4 step 2 (multiple jobs)", form.step2MultipleJobs) { viewModel.updateLesForm { s -> s.copy(step2MultipleJobs = it) } } },
        { TextCell("Dependents under 17", form.depUnder17, numeric = true) { viewModel.updateLesForm { s -> s.copy(depUnder17 = it) } } },
    )
    FieldRow(
        { TextCell("Other dependents", form.otherDep, numeric = true) { viewModel.updateLesForm { s -> s.copy(otherDep = it) } } },
        { TextCell("Other income (annual)", form.otherIncomeAnnual, numeric = true) { viewModel.updateLesForm { s -> s.copy(otherIncomeAnnual = it) } } },
    )
    FieldRow(
        { TextCell("Other deductions (annual)", form.otherDeductionsAnnual, numeric = true) { viewModel.updateLesForm { s -> s.copy(otherDeductionsAnnual = it) } } },
        {},
    )
}

@Composable
private fun DailyWeightsPreview(monthBudget: MonthBudget?, weekdayPoints: Double?, weekendPoints: Double?) {
    if (monthBudget == null || weekdayPoints == null || weekendPoints == null || weekdayPoints <= 0 || weekendPoints <= 0) return
    val today = LocalDate.now()
    val lastDay = today.withDayOfMonth(today.lengthOfMonth())
    var weekdayDays = 0
    var weekendDays = 0
    var day = today.withDayOfMonth(1)
    while (!day.isAfter(lastDay)) {
        if (day.dayOfWeek == DayOfWeek.SATURDAY || day.dayOfWeek == DayOfWeek.SUNDAY) weekendDays++ else weekdayDays++
        day = day.plusDays(1)
    }
    val totalPoints = weekdayDays * weekdayPoints + weekendDays * weekendPoints
    if (totalPoints <= 0) return
    val pointValue = monthBudget.safeToSpend / totalPoints
    val weekdayLimit = pointValue * weekdayPoints
    val weekendLimit = pointValue * weekendPoints
    val isWeekendToday = today.dayOfWeek == DayOfWeek.SATURDAY || today.dayOfWeek == DayOfWeek.SUNDAY

    Column(Modifier.padding(top = 14.dp)) {
        Text("Preview", color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(bottom = 6.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            PreviewPill("Weekday limit", currency.format(weekdayLimit), highlighted = !isWeekendToday, modifier = Modifier.weight(1f))
            PreviewPill("Weekend limit", currency.format(weekendLimit), highlighted = isWeekendToday, modifier = Modifier.weight(1f))
        }
    }
}

@Composable
private fun PreviewPill(label: String, value: String, highlighted: Boolean, modifier: Modifier = Modifier) {
    Surface(
        color = if (highlighted) MaterialTheme.colorScheme.primary.copy(alpha = 0.18f) else QuailSurfaceRaised,
        shape = RoundedCornerShape(12.dp),
        modifier = modifier,
    ) {
        Column(Modifier.padding(10.dp)) {
            Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            Text(value, fontWeight = FontWeight.Bold)
        }
    }
}
