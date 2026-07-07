package com.quail.android.ui.screens.wizards

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Edit
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
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.bugreport.BugReportTopBarAction
import com.quail.android.csvimport.CsvImportRepository
import com.quail.android.csvimport.csvHeaderSignature
import com.quail.android.data.model.CardBenefitItem
import com.quail.android.data.model.OnboardingAccountItem
import com.quail.android.ui.overlay.AppOverlayHost
import com.quail.android.ui.overlay.InlineConfirmCard
import com.quail.android.ui.screens.settings.SettingsRow
import com.quail.android.ui.screens.settings.SettingsSection
import com.quail.android.ui.theme.QuailBadRed
import com.quail.android.ui.theme.QuailGoodGreen
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import kotlinx.coroutines.launch

private val ACCOUNT_TYPES = listOf("checking", "savings", "credit", "investment")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SetupWizardScreen(
    viewModel: SetupWizardViewModel,
    csvImportRepository: CsvImportRepository,
    onBack: () -> Unit,
    onOpenCsvImportQueue: () -> Unit,
    onOpenEmailParserWizard: () -> Unit,
) {
    val state by viewModel.state.collectAsState()
    val accountForm by viewModel.accountForm.collectAsState()
    val pushoverKeyText by viewModel.pushoverKeyText.collectAsState()
    val pushoverBusy by viewModel.pushoverBusy.collectAsState()
    val pushoverMessage by viewModel.pushoverMessage.collectAsState()
    val completing by viewModel.completing.collectAsState()
    val scope = rememberCoroutineScope()
    var deletingAccountId by remember { mutableStateOf<Int?>(null) }
    var pendingCsvAccount by remember { mutableStateOf<Pair<Int, String>?>(null) }

    val pickCsv = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri: Uri? ->
        val (accountId, accountLabel) = pendingCsvAccount ?: return@rememberLauncherForActivityResult
        pendingCsvAccount = null
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            runCatching {
                val bytes = csvImportRepository.readUriBytes(uri)
                val fileName = uri.lastPathSegment?.substringAfterLast('/') ?: "import.csv"
                val preview = csvImportRepository.fetchPreviewFromBytes(bytes, fileName)
                val signature = csvHeaderSignature(preview.columns)
                csvImportRepository.enqueueBytes(bytes, fileName, accountId, accountLabel, signature)
            }
            onOpenCsvImportQueue()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Setup Wizard", fontWeight = FontWeight.Bold) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back") } },
                actions = { BugReportTopBarAction() },
            )
        },
    ) { padding ->
        when (val s = state) {
            is SetupWizardUiState.Loading -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
            is SetupWizardUiState.Error -> Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Text(s.message, color = QuailBadRed)
            }
            is SetupWizardUiState.Success -> {
                val status = s.status
                LazyColumn(
                    modifier = Modifier.fillMaxSize().padding(padding),
                    contentPadding = PaddingValues(12.dp),
                    verticalArrangement = Arrangement.spacedBy(20.dp),
                ) {
                    item {
                        StatusPillsRow(status.steps.accountsAdded, status.steps.startingBalancesAdded, status.steps.transactionsImported, status.steps.pushoverUserKeySet)
                    }

                    item {
                        SettingsSection("Accounts") {
                            if (status.accounts.isEmpty()) {
                                Text(
                                    "No accounts yet — add one to get started.",
                                    color = QuailTextDim,
                                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 12.dp),
                                )
                            } else {
                                status.accounts.forEachIndexed { index, account ->
                                    AccountRow(
                                        account = account,
                                        onEdit = { viewModel.startEditAccount(account) },
                                        onDelete = { deletingAccountId = account.id },
                                        onImportCsv = {
                                            pendingCsvAccount = account.id to "${account.institution.orEmpty()} — ${account.name.orEmpty()}"
                                            pickCsv.launch(arrayOf("*/*"))
                                        },
                                    )
                                    if (index < status.accounts.size - 1) HorizontalDivider(color = QuailTextDim.copy(alpha = 0.12f))
                                    if (deletingAccountId == account.id) {
                                        InlineConfirmCard(
                                            title = "Delete ${account.name ?: "account"}?",
                                            text = "This removes the account and all of its transactions.",
                                            confirmLabel = "Delete",
                                            confirmColor = QuailBadRed,
                                            onConfirm = { deletingAccountId = null; viewModel.deleteAccount(account.id) },
                                            onCancel = { deletingAccountId = null },
                                        )
                                    }
                                }
                            }
                            SettingsRow(
                                icon = Icons.Filled.Edit,
                                iconColor = MaterialTheme.colorScheme.primary,
                                title = "Add Account",
                                subtitle = "Create a new bank or credit account",
                                onClick = { viewModel.startAddAccount() },
                            )
                        }
                    }

                    item {
                        SettingsSection("Email Parser") {
                            SettingsRow(
                                icon = Icons.Filled.Description,
                                iconColor = Color(0xFF26A69A),
                                title = "Set up email parsing",
                                subtitle = "Configure per-account rules that turn forwarded bank emails into transactions",
                                onClick = onOpenEmailParserWizard,
                            )
                        }
                    }

                    item {
                        SettingsSection("Notifications") {
                            Column(Modifier.padding(horizontal = 14.dp, vertical = 12.dp)) {
                                Text("Pushover key", color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(bottom = 6.dp))
                                OutlinedTextField(
                                    value = pushoverKeyText,
                                    onValueChange = { viewModel.setPushoverKeyText(it) },
                                    singleLine = true,
                                    modifier = Modifier.fillMaxWidth(),
                                )
                                Row(modifier = Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Surface(
                                        onClick = { viewModel.savePushoverKey() },
                                        enabled = !pushoverBusy,
                                        color = MaterialTheme.colorScheme.primary,
                                        shape = RoundedCornerShape(10.dp),
                                    ) {
                                        Text("Save", modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp), fontWeight = FontWeight.Bold, color = Color.Black)
                                    }
                                    Surface(
                                        onClick = { viewModel.testPushover() },
                                        enabled = !pushoverBusy,
                                        color = QuailSurfaceRaised,
                                        shape = RoundedCornerShape(10.dp),
                                    ) {
                                        Text("Send Test Notification", modifier = Modifier.padding(horizontal = 16.dp, vertical = 10.dp), fontWeight = FontWeight.SemiBold)
                                    }
                                }
                                pushoverMessage?.let {
                                    Text(it, color = QuailTextDim, style = MaterialTheme.typography.labelSmall, modifier = Modifier.padding(top = 8.dp))
                                }
                            }
                        }
                    }

                    item {
                        Surface(
                            onClick = { viewModel.markComplete(onBack) },
                            enabled = !completing,
                            color = if (status.wizardCompleted) QuailGoodGreen.copy(alpha = 0.18f) else MaterialTheme.colorScheme.primary,
                            shape = RoundedCornerShape(14.dp),
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Box(Modifier.fillMaxWidth().padding(vertical = 14.dp), contentAlignment = Alignment.Center) {
                                Text(
                                    if (status.wizardCompleted) "Setup complete" else "Mark Setup Complete",
                                    fontWeight = FontWeight.Bold,
                                    color = if (status.wizardCompleted) QuailGoodGreen else Color.Black,
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    accountForm?.let { form ->
        AccountFormSheet(form = form, viewModel = viewModel)
    }
}

@Composable
private fun StatusPillsRow(accountsAdded: Boolean, startingBalancesAdded: Boolean, transactionsImported: Boolean, pushoverSet: Boolean) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        StatusPill("Accounts", accountsAdded, Modifier.weight(1f))
        StatusPill("Balances", startingBalancesAdded, Modifier.weight(1f))
        StatusPill("Imported", transactionsImported, Modifier.weight(1f))
        StatusPill("Pushover", pushoverSet, Modifier.weight(1f))
    }
}

@Composable
private fun StatusPill(label: String, done: Boolean, modifier: Modifier = Modifier) {
    Surface(
        color = if (done) QuailGoodGreen.copy(alpha = 0.18f) else QuailSurfaceRaised,
        shape = RoundedCornerShape(12.dp),
        modifier = modifier,
    ) {
        Column(Modifier.padding(horizontal = 10.dp, vertical = 10.dp)) {
            Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            Text(if (done) "Done" else "Pending", fontWeight = FontWeight.Bold, color = if (done) QuailGoodGreen else QuailTextDim, style = MaterialTheme.typography.labelMedium)
        }
    }
}

@Composable
private fun AccountRow(account: OnboardingAccountItem, onEdit: () -> Unit, onDelete: () -> Unit, onImportCsv: () -> Unit) {
    Column(Modifier.padding(horizontal = 14.dp, vertical = 12.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("${account.institution.orEmpty()} — ${account.name.orEmpty()}", fontWeight = FontWeight.SemiBold)
                Text(account.accounttype?.replaceFirstChar { it.uppercase() } ?: "—", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
            }
            IconButton(onClick = onEdit) { Icon(Icons.Filled.Edit, contentDescription = "Edit", tint = QuailTextDim) }
            IconButton(onClick = onDelete) { Icon(Icons.Filled.Delete, contentDescription = "Delete", tint = QuailBadRed) }
        }
        val setup = account.setup
        Row(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Surface(
                onClick = onImportCsv,
                color = if (setup.csvMappingReady) QuailGoodGreen.copy(alpha = 0.18f) else QuailSurfaceRaised,
                shape = RoundedCornerShape(999.dp),
            ) {
                Text(
                    "Import CSV",
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
        if (setup.missing.isNotEmpty()) {
            Text(
                "Missing: ${setup.missing.joinToString(", ")}",
                color = QuailTextDim,
                style = MaterialTheme.typography.labelSmall,
                modifier = Modifier.padding(top = 6.dp),
            )
        }
    }
}

@Composable
private fun AccountFormSheet(form: AccountFormState, viewModel: SetupWizardViewModel) {
    val content: @Composable () -> Unit = {
        Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 24.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text(if (form.editingAccountId == null) "Add Account" else "Edit Account", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                IconButton(onClick = { viewModel.cancelAccountForm() }) { Icon(Icons.Filled.Close, contentDescription = "Close") }
            }

            OutlinedTextField(
                value = form.institution,
                onValueChange = { text -> viewModel.updateAccountForm { it.copy(institution = text) } },
                label = { Text("Institution") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
            )
            OutlinedTextField(
                value = form.name,
                onValueChange = { text -> viewModel.updateAccountForm { it.copy(name = text) } },
                label = { Text("Account name") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
            )

            Text("Type", color = QuailTextDim, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(top = 14.dp, bottom = 6.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                ACCOUNT_TYPES.forEach { type ->
                    Surface(
                        onClick = { viewModel.updateAccountForm { it.copy(accounttype = type) } },
                        color = if (form.accounttype == type) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
                        shape = RoundedCornerShape(999.dp),
                    ) {
                        Text(
                            type.replaceFirstChar { it.uppercase() },
                            color = if (form.accounttype == type) Color.Black else Color.Unspecified,
                            fontWeight = FontWeight.SemiBold,
                            style = MaterialTheme.typography.labelSmall,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                        )
                    }
                }
            }

            if (form.accounttype == "credit") {
                OutlinedTextField(
                    value = form.creditLimit,
                    onValueChange = { text -> viewModel.updateAccountForm { it.copy(creditLimit = text.filter { c -> c.isDigit() || c == '.' }) } },
                    label = { Text("Credit limit") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                )
                Text("Card benefits", color = QuailTextDim, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(top = 14.dp, bottom = 6.dp))
                form.cardBenefits.forEachIndexed { index, benefit ->
                    Row(Modifier.fillMaxWidth().padding(bottom = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        OutlinedTextField(
                            value = benefit.benefitType,
                            onValueChange = { text ->
                                viewModel.updateAccountForm { s ->
                                    s.copy(cardBenefits = s.cardBenefits.toMutableList().apply { set(index, benefit.copy(benefitType = text)) })
                                }
                            },
                            label = { Text("Category") },
                            singleLine = true,
                            modifier = Modifier.weight(1f),
                        )
                        OutlinedTextField(
                            value = if (benefit.cashbackPercent == 0.0) "" else benefit.cashbackPercent.toString(),
                            onValueChange = { text ->
                                viewModel.updateAccountForm { s ->
                                    s.copy(cardBenefits = s.cardBenefits.toMutableList().apply { set(index, benefit.copy(cashbackPercent = text.toDoubleOrNull() ?: 0.0)) })
                                }
                            },
                            label = { Text("% back") },
                            singleLine = true,
                            modifier = Modifier.weight(1f),
                        )
                        IconButton(onClick = {
                            viewModel.updateAccountForm { s -> s.copy(cardBenefits = s.cardBenefits.toMutableList().apply { removeAt(index) }) }
                        }) { Icon(Icons.Filled.Close, contentDescription = "Remove") }
                    }
                }
                Surface(
                    onClick = { viewModel.updateAccountForm { s -> s.copy(cardBenefits = s.cardBenefits + CardBenefitItem()) } },
                    color = QuailSurfaceRaised,
                    shape = RoundedCornerShape(10.dp),
                ) {
                    Text("+ Add benefit", modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp), fontWeight = FontWeight.SemiBold)
                }
            }

            OutlinedTextField(
                value = form.apyPercent,
                onValueChange = { text -> viewModel.updateAccountForm { it.copy(apyPercent = text.filter { c -> c.isDigit() || c == '.' }) } },
                label = { Text("APY / APR (%)") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(top = 14.dp),
            )
            if (form.editingAccountId == null) {
                OutlinedTextField(
                    value = form.startingBalance,
                    onValueChange = { text -> viewModel.updateAccountForm { it.copy(startingBalance = text.filter { c -> c.isDigit() || c == '.' || c == '-' }) } },
                    label = { Text("Starting balance") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
                )
                OutlinedTextField(
                    value = form.startingDate,
                    onValueChange = { text -> viewModel.updateAccountForm { it.copy(startingDate = text) } },
                    label = { Text("Starting date (YYYY-MM-DD, optional)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
                )
            }

            Row(Modifier.fillMaxWidth().padding(top = 14.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("Receives forwarded emails", style = MaterialTheme.typography.bodyMedium)
                Switch(checked = form.receivesEmails, onCheckedChange = { checked -> viewModel.updateAccountForm { it.copy(receivesEmails = checked) } })
            }
            Row(Modifier.fillMaxWidth().padding(top = 6.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Text("This is my paycheck account", style = MaterialTheme.typography.bodyMedium)
                Switch(checked = form.isPaycheckAccount, onCheckedChange = { checked -> viewModel.updateAccountForm { it.copy(isPaycheckAccount = checked) } })
            }

            form.error?.let {
                Text(it, color = QuailBadRed, modifier = Modifier.padding(top = 12.dp))
            }

            Surface(
                onClick = { viewModel.saveAccountForm() },
                enabled = !form.saving,
                color = MaterialTheme.colorScheme.primary,
                shape = RoundedCornerShape(14.dp),
                modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
            ) {
                Box(Modifier.fillMaxWidth().padding(vertical = 14.dp), contentAlignment = Alignment.Center) {
                    if (form.saving) {
                        CircularProgressIndicator(modifier = Modifier.size(20.dp))
                    } else {
                        Text("Save", fontWeight = FontWeight.Bold, color = Color.Black)
                    }
                }
            }
        }
    }
    SideEffect { AppOverlayHost.showBottomSheet(onDismissed = { viewModel.cancelAccountForm() }, content = content) }
    DisposableEffect(Unit) { onDispose { AppOverlayHost.dismiss() } }
}
