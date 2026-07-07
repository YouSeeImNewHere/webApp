package com.quail.android.ui.screens.wizards

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.RadioButtonChecked
import androidx.compose.material.icons.filled.RadioButtonUnchecked
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
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
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import com.quail.android.bugreport.BugReportTopBarAction
import com.quail.android.data.model.ParserAccountItem
import com.quail.android.data.model.ParserSampleItem
import com.quail.android.data.model.ParserWizardSetting
import com.quail.android.ui.theme.QuailAccent
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import com.quail.android.ui.theme.QuailWarnYellow

private val PARSER_MODES = listOf("guided" to "Guided (no regex)", "advanced" to "Advanced (regex)")
private val EXTRACT_FIELD_COLORS = mapOf(
    "amount" to QuailGoodGreen,
    "merchant" to QuailAccent,
    "date" to QuailWarnYellow,
    "time" to QuailBadRed,
)

/** Highlights whatever the current parser config actually extracted
 * (amount/merchant/date/time) directly in the raw email text, so typing a
 * "text before" label and seeing it light up the right spot below is the
 * feedback loop — instead of guessing blind and only finding out via a
 * separate results list. */
private fun highlightedBody(body: String, extracted: Map<String, String>): AnnotatedString {
    data class MatchRange(val start: Int, val end: Int, val color: Color)

    val ranges = extracted.mapNotNull { (key, value) ->
        val color = EXTRACT_FIELD_COLORS[key] ?: return@mapNotNull null
        if (value.isBlank()) return@mapNotNull null
        val idx = body.indexOf(value)
        if (idx < 0) null else MatchRange(idx, idx + value.length, color)
    }.sortedBy { it.start }

    if (ranges.isEmpty()) return AnnotatedString(body)

    return buildAnnotatedString {
        var cursor = 0
        for (range in ranges) {
            if (range.start < cursor) continue
            append(body.substring(cursor, range.start))
            withStyle(SpanStyle(background = range.color.copy(alpha = 0.35f), fontWeight = FontWeight.Bold)) {
                append(body.substring(range.start, range.end))
            }
            cursor = range.end
        }
        append(body.substring(cursor))
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EmailParserWizardScreen(viewModel: EmailParserWizardViewModel, onBack: () -> Unit) {
    val accountsState by viewModel.accountsState.collectAsState()
    val scopeForm by viewModel.scopeForm.collectAsState()
    val samplesState by viewModel.samplesState.collectAsState()
    val selectedSampleIds by viewModel.selectedSampleIds.collectAsState()
    val primarySampleId by viewModel.primarySampleId.collectAsState()
    val primarySample by viewModel.primarySample.collectAsState()
    val livePreviewRow by viewModel.livePreviewRow.collectAsState()
    val livePreviewLoading by viewModel.livePreviewLoading.collectAsState()
    val ruleForm by viewModel.ruleForm.collectAsState()
    val existingSettings by viewModel.existingSettings.collectAsState()
    val previewState by viewModel.previewState.collectAsState()
    val testRunState by viewModel.testRunState.collectAsState()
    val saving by viewModel.saving.collectAsState()
    val saveMessage by viewModel.saveMessage.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Email Parser Wizard", fontWeight = FontWeight.Bold) },
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
                SectionCard("1. Scope") {
                    when (val s = accountsState) {
                        is ParserAccountsUiState.Loading -> CircularProgressIndicator()
                        is ParserAccountsUiState.Error -> Text(s.message, color = QuailBadRed)
                        is ParserAccountsUiState.Success -> AccountPicker(s.accounts, scopeForm.accountId, viewModel)
                    }
                    OutlinedTextField(
                        value = scopeForm.senderQuery,
                        onValueChange = { text -> viewModel.updateScopeForm { it.copy(senderQuery = text) } },
                        label = { Text("Sender contains") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
                    )
                    OutlinedTextField(
                        value = scopeForm.subjectQuery,
                        onValueChange = { text -> viewModel.updateScopeForm { it.copy(subjectQuery = text) } },
                        label = { Text("Subject contains (optional)") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                    )
                    Row(modifier = Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        OutlinedTextField(
                            value = scopeForm.lookbackDays,
                            onValueChange = { text -> viewModel.updateScopeForm { it.copy(lookbackDays = text.filter { c -> c.isDigit() }) } },
                            label = { Text("Lookback days") },
                            singleLine = true,
                            modifier = Modifier.weight(1f),
                        )
                        OutlinedTextField(
                            value = scopeForm.limit,
                            onValueChange = { text -> viewModel.updateScopeForm { it.copy(limit = text.filter { c -> c.isDigit() }) } },
                            label = { Text("Max samples") },
                            singleLine = true,
                            modifier = Modifier.weight(1f),
                        )
                    }
                    Row(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Text("Try HTML fallback", style = MaterialTheme.typography.labelMedium)
                        Switch(checked = scopeForm.tryHtmlFallback, onCheckedChange = { checked -> viewModel.updateScopeForm { it.copy(tryHtmlFallback = checked) } })
                    }
                    Surface(
                        onClick = { viewModel.loadSamples() },
                        color = MaterialTheme.colorScheme.primary,
                        shape = RoundedCornerShape(10.dp),
                        modifier = Modifier.padding(top = 10.dp),
                    ) {
                        Text("Load Samples", modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp), fontWeight = FontWeight.Bold, color = Color.Black)
                    }
                }
            }

            item {
                SectionCard("2. Candidate Samples") {
                    when (val s = samplesState) {
                        is ParserSamplesUiState.Idle -> Text("Load samples to see candidate emails here.", color = QuailTextDim)
                        is ParserSamplesUiState.Loading -> CircularProgressIndicator()
                        is ParserSamplesUiState.Error -> Text(s.message, color = QuailBadRed)
                        is ParserSamplesUiState.Success -> {
                            if (s.warning != null) {
                                Text(s.warning, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(bottom = 8.dp))
                            }
                            if (s.items.isEmpty()) {
                                Text("No matching emails found in that range.", color = QuailTextDim)
                            } else {
                                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    s.items.forEach { sample ->
                                        SampleRow(
                                            sample = sample,
                                            selected = sample.sampleId in selectedSampleIds,
                                            isPrimary = sample.sampleId == primarySampleId,
                                            onToggleSelected = { viewModel.toggleSampleSelected(sample.sampleId) },
                                            onSetPrimary = { viewModel.setPrimarySample(sample.sampleId) },
                                        )
                                    }
                                }
                            }
                        }
                    }
                }
            }

            if (primarySample != null) {
                item {
                    SectionCard("Reference Email") {
                        ReferenceEmailCard(sample = primarySample!!, extracted = livePreviewRow?.extracted ?: emptyMap(), loading = livePreviewLoading)
                    }
                }
            }

            item {
                SectionCard("3. Parser Rule") {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        PARSER_MODES.forEach { (value, label) ->
                            Surface(
                                onClick = { viewModel.updateRuleForm { it.copy(mode = value) } },
                                color = if (ruleForm.mode == value) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
                                shape = RoundedCornerShape(999.dp),
                            ) {
                                Text(
                                    label,
                                    color = if (ruleForm.mode == value) Color.Black else Color.Unspecified,
                                    fontWeight = FontWeight.SemiBold,
                                    style = MaterialTheme.typography.labelSmall,
                                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                                )
                            }
                        }
                    }
                    OutlinedTextField(
                        value = ruleForm.name,
                        onValueChange = { text -> viewModel.updateRuleForm { it.copy(name = text) } },
                        label = { Text("Parser name") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
                    )

                    if (ruleForm.mode == "advanced") {
                        OutlinedTextField(
                            value = ruleForm.bodyRegex,
                            onValueChange = { text -> viewModel.updateRuleForm { it.copy(bodyRegex = text) } },
                            label = { Text("Body regex") },
                            modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
                        )
                        OutlinedTextField(
                            value = ruleForm.flags,
                            onValueChange = { text -> viewModel.updateRuleForm { it.copy(flags = text) } },
                            label = { Text("Regex flags (e.g. i, is, ism)") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                        )
                        Row(modifier = Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            SmallNumberField("Amount grp", ruleForm.amountGroup, Modifier.weight(1f)) { viewModel.updateRuleForm { s -> s.copy(amountGroup = it) } }
                            SmallNumberField("Merchant grp", ruleForm.merchantGroup, Modifier.weight(1f)) { viewModel.updateRuleForm { s -> s.copy(merchantGroup = it) } }
                        }
                        Row(modifier = Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            SmallNumberField("Date grp", ruleForm.dateGroup, Modifier.weight(1f)) { viewModel.updateRuleForm { s -> s.copy(dateGroup = it) } }
                            SmallNumberField("Time grp (0=none)", ruleForm.timeGroup, Modifier.weight(1f)) { viewModel.updateRuleForm { s -> s.copy(timeGroup = it) } }
                        }
                    } else {
                        GuidedFieldGroup("Amount", ruleForm.amountLabel, ruleForm.amountOrder) { label, order ->
                            viewModel.updateRuleForm { it.copy(amountLabel = label, amountOrder = order) }
                        }
                        GuidedFieldGroup("Merchant", ruleForm.merchantLabel, ruleForm.merchantOrder) { label, order ->
                            viewModel.updateRuleForm { it.copy(merchantLabel = label, merchantOrder = order) }
                        }
                        GuidedFieldGroup("Date", ruleForm.dateLabel, ruleForm.dateOrder) { label, order ->
                            viewModel.updateRuleForm { it.copy(dateLabel = label, dateOrder = order) }
                        }
                        GuidedFieldGroup("Time (0 = skip)", ruleForm.timeLabel, ruleForm.timeOrder) { label, order ->
                            viewModel.updateRuleForm { it.copy(timeLabel = label, timeOrder = order) }
                        }
                        Row(modifier = Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            OutlinedTextField(
                                value = ruleForm.accountBefore,
                                onValueChange = { text -> viewModel.updateRuleForm { it.copy(accountBefore = text) } },
                                label = { Text("Account guard label") },
                                singleLine = true,
                                modifier = Modifier.weight(1f),
                            )
                            OutlinedTextField(
                                value = ruleForm.accountExact,
                                onValueChange = { text -> viewModel.updateRuleForm { it.copy(accountExact = text) } },
                                label = { Text("Account guard value") },
                                singleLine = true,
                                modifier = Modifier.weight(1f),
                            )
                        }
                    }

                    HorizontalDivider(modifier = Modifier.padding(vertical = 12.dp))

                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(
                            value = ruleForm.parserSlot,
                            onValueChange = { text -> viewModel.updateRuleForm { it.copy(parserSlot = text) } },
                            label = { Text("Parser slot") },
                            singleLine = true,
                            modifier = Modifier.weight(1f),
                        )
                        OutlinedTextField(
                            value = ruleForm.pendingTtlMinutes,
                            onValueChange = { text -> viewModel.updateRuleForm { it.copy(pendingTtlMinutes = text.filter { c -> c.isDigit() }) } },
                            label = { Text("Pending TTL (min)") },
                            singleLine = true,
                            modifier = Modifier.weight(1f),
                        )
                    }
                    ToggleRow("Override on primary", ruleForm.overrideOnPrimary) { viewModel.updateRuleForm { s -> s.copy(overrideOnPrimary = it) } }
                    ToggleRow("Backup assumes unknown", ruleForm.backupAssumeUnknown) { viewModel.updateRuleForm { s -> s.copy(backupAssumeUnknown = it) } }
                    ToggleRow("Invert amount sign", ruleForm.invertAmountSign) { viewModel.updateRuleForm { s -> s.copy(invertAmountSign = it) } }

                    Row(modifier = Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Surface(onClick = { viewModel.runPreview() }, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp)) {
                            Text("Preview Selected Samples", modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp), fontWeight = FontWeight.SemiBold)
                        }
                        Surface(
                            onClick = { viewModel.saveRule() },
                            enabled = !saving,
                            color = MaterialTheme.colorScheme.primary,
                            shape = RoundedCornerShape(10.dp),
                        ) {
                            Text("Save Parser", modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp), fontWeight = FontWeight.Bold, color = Color.Black)
                        }
                    }
                    saveMessage?.let { Text(it, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 8.dp)) }

                    PreviewResults(previewState)
                }
            }

            if (existingSettings.isNotEmpty()) {
                item {
                    SectionCard("Saved Parsers") {
                        existingSettings.forEachIndexed { index, setting ->
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(setting.name.ifBlank { setting.parserSlot }, fontWeight = FontWeight.SemiBold)
                                    Text("${setting.parserSlot} • ${setting.parserMode}", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                                }
                                Surface(onClick = { viewModel.loadExistingRule(setting) }, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
                                    Text("Edit", modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp), style = MaterialTheme.typography.labelSmall)
                                }
                                IconButton(onClick = { viewModel.deleteRule(setting.parserSlot) }) {
                                    Icon(Icons.Filled.Delete, contentDescription = "Delete", tint = QuailBadRed)
                                }
                            }
                            if (index < existingSettings.size - 1) HorizontalDivider(color = QuailTextDim.copy(alpha = 0.12f))
                        }
                    }
                }
            }

            item {
                SectionCard("4. Test All Saved Parsers") {
                    Surface(onClick = { viewModel.runTestAll() }, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp)) {
                        Text("Test All Saved Parsers", modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp), fontWeight = FontWeight.SemiBold)
                    }
                    TestRunResults(testRunState)
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
private fun AccountPicker(accounts: List<ParserAccountItem>, selectedId: Int?, viewModel: EmailParserWizardViewModel) {
    Row(modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        accounts.filter { it.receivesEmails }.forEach { account ->
            Surface(
                onClick = { viewModel.selectAccount(account.id) },
                color = if (selectedId == account.id) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
                shape = RoundedCornerShape(999.dp),
            ) {
                Text(
                    "${account.institution.orEmpty()} — ${account.name.orEmpty()}",
                    color = if (selectedId == account.id) Color.Black else Color.Unspecified,
                    fontWeight = FontWeight.SemiBold,
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                )
            }
        }
    }
}

@Composable
private fun SampleRow(sample: ParserSampleItem, selected: Boolean, isPrimary: Boolean, onToggleSelected: () -> Unit, onSetPrimary: () -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    Surface(onClick = { expanded = !expanded }, color = QuailSurfaceRaised, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = selected, onCheckedChange = { onToggleSelected() })
                IconButton(onClick = onSetPrimary) {
                    Icon(
                        if (isPrimary) Icons.Filled.RadioButtonChecked else Icons.Filled.RadioButtonUnchecked,
                        contentDescription = "Use as primary sample",
                        tint = if (isPrimary) MaterialTheme.colorScheme.primary else QuailTextDim,
                    )
                }
                Column(Modifier.weight(1f)) {
                    Text(sample.subject ?: "(no subject)", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                    Text(sample.sender ?: "", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
                }
            }
            if (expanded) {
                Text(
                    sample.body ?: sample.snippet ?: "",
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
        }
    }
}

/** Keeps the actual email text on screen while the rule fields below are
 * being edited, with whatever the live preview currently extracts
 * highlighted right in place — so "what do I type as the label" has a
 * visible answer instead of requiring a guess. */
@Composable
private fun ReferenceEmailCard(sample: ParserSampleItem, extracted: Map<String, String>, loading: Boolean) {
    Column {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(sample.subject ?: "(no subject)", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodyMedium)
                Text(sample.sender ?: "", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            }
            if (loading) CircularProgressIndicator(modifier = Modifier.padding(start = 8.dp))
        }
        if (extracted.isNotEmpty()) {
            Row(modifier = Modifier.padding(top = 8.dp).horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf("amount", "merchant", "date", "time").forEach { key ->
                    val value = extracted[key]
                    val color = EXTRACT_FIELD_COLORS.getValue(key)
                    Surface(color = color.copy(alpha = 0.18f), shape = RoundedCornerShape(999.dp)) {
                        Text(
                            "$key: ${value ?: "—"}",
                            color = color,
                            fontWeight = FontWeight.SemiBold,
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
                        )
                    }
                }
            }
        }
        Surface(
            color = QuailSurfaceRaised,
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
        ) {
            Text(
                highlightedBody(sample.body ?: sample.snippet.orEmpty(), extracted),
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.padding(12.dp),
            )
        }
    }
}

@Composable
private fun GuidedFieldGroup(title: String, label: String, order: String, onChange: (label: String, order: String) -> Unit) {
    Text(title, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 10.dp, bottom = 4.dp))
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(
            value = label,
            onValueChange = { onChange(it, order) },
            label = { Text("Text before") },
            singleLine = true,
            modifier = Modifier.weight(2f),
        )
        OutlinedTextField(
            value = order,
            onValueChange = { text -> onChange(label, text.filter { it.isDigit() }) },
            label = { Text("Order") },
            singleLine = true,
            modifier = Modifier.weight(1f),
        )
    }
}

@Composable
private fun SmallNumberField(label: String, value: String, modifier: Modifier = Modifier, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = { text -> onChange(text.filter { it.isDigit() }) },
        label = { Text(label) },
        singleLine = true,
        modifier = modifier,
    )
}

@Composable
private fun ToggleRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = MaterialTheme.typography.labelMedium)
        Switch(checked = checked, onCheckedChange = onChange)
    }
}

@Composable
private fun PreviewResults(state: ParserPreviewUiState) {
    when (state) {
        is ParserPreviewUiState.Idle -> {}
        is ParserPreviewUiState.Loading -> Box(Modifier.fillMaxWidth().padding(top = 14.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        is ParserPreviewUiState.Error -> Text(state.message, color = QuailBadRed, modifier = Modifier.padding(top = 12.dp))
        is ParserPreviewUiState.Success -> {
            Column(Modifier.padding(top = 14.dp)) {
                Text("Matched ${state.matched} / ${state.rows.size}", fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(bottom = 8.dp))
                state.rows.forEach { row ->
                    Surface(
                        color = if (row.matched) QuailGoodGreen.copy(alpha = 0.12f) else QuailSurfaceRaised,
                        shape = RoundedCornerShape(10.dp),
                        modifier = Modifier.fillMaxWidth().padding(bottom = 6.dp),
                    ) {
                        Column(Modifier.padding(10.dp)) {
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Icon(
                                    if (row.matched) Icons.Filled.CheckCircle else Icons.Filled.RadioButtonUnchecked,
                                    contentDescription = null,
                                    tint = if (row.matched) QuailGoodGreen else QuailTextDim,
                                )
                                Text(row.sampleId, style = MaterialTheme.typography.labelSmall, color = QuailTextDim)
                            }
                            if (row.matched) {
                                Row(modifier = Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                                    Text("Amount: ${row.extracted["amount"] ?: "—"}", style = MaterialTheme.typography.labelSmall)
                                    Text("Merchant: ${row.extracted["merchant"] ?: "—"}", style = MaterialTheme.typography.labelSmall)
                                }
                                Row(modifier = Modifier.fillMaxWidth().padding(top = 2.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                                    Text("Date: ${row.extracted["date"] ?: "—"}", style = MaterialTheme.typography.labelSmall)
                                    Text("Time: ${row.extracted["time"] ?: "—"}", style = MaterialTheme.typography.labelSmall)
                                }
                            } else if (row.error != null) {
                                Text(row.error, color = QuailBadRed, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 4.dp))
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TestRunResults(state: ParserTestRunUiState) {
    when (state) {
        is ParserTestRunUiState.Idle -> {}
        is ParserTestRunUiState.Loading -> Box(Modifier.fillMaxWidth().padding(top = 14.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        is ParserTestRunUiState.Error -> Text(state.message, color = QuailBadRed, modifier = Modifier.padding(top = 12.dp))
        is ParserTestRunUiState.Success -> {
            val summary = state.response.summary
            Column(Modifier.padding(top = 14.dp)) {
                Text(
                    "Fetched ${summary.fetched} • ${summary.parsers} parsers • matched ${summary.matched} • would insert ${summary.wouldInsert}",
                    style = MaterialTheme.typography.labelSmall,
                    color = QuailTextDim,
                )
            }
        }
    }
}
