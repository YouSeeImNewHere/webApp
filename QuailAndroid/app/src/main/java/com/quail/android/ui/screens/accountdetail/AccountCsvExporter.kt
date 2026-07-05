package com.quail.android.ui.screens.accountdetail

import android.content.Context
import android.content.Intent
import androidx.core.content.FileProvider
import com.quail.android.data.model.AccountLedgerTransaction
import java.io.File

private fun csvEscape(value: String): String {
    return if (value.contains(",") || value.contains("\"") || value.contains("\n")) {
        "\"${value.replace("\"", "\"\"")}\""
    } else {
        value
    }
}

private fun buildTransactionsCsv(transactions: List<AccountLedgerTransaction>): String {
    val header = listOf("Date", "Merchant", "Amount", "Category", "Status", "Balance After").joinToString(",")
    val rows = transactions.map { tx ->
        listOf(
            tx.dateISO ?: tx.effectiveDate ?: "",
            tx.merchant ?: "",
            tx.amount.toString(),
            tx.category ?: "",
            tx.status,
            tx.balanceAfter?.toString() ?: "",
        ).joinToString(",") { csvEscape(it) }
    }
    return (listOf(header) + rows).joinToString("\n")
}

fun shareTransactionsCsv(context: Context, transactions: List<AccountLedgerTransaction>, accountName: String) {
    val safeName = accountName.replace(Regex("[^A-Za-z0-9._-]+"), "-").ifBlank { "account" }
    val exportDir = File(context.cacheDir, "exports").apply { mkdirs() }
    val file = File(exportDir, "$safeName-transactions.csv")
    file.writeText(buildTransactionsCsv(transactions))

    val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = "text/csv"
        putExtra(Intent.EXTRA_STREAM, uri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(Intent.createChooser(intent, "Share transactions").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}
