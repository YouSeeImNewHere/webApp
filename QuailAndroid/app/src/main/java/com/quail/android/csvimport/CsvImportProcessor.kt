package com.quail.android.csvimport

import com.quail.android.data.model.CsvMappingPreset
import com.quail.android.data.model.CsvPreviewResponse
import com.quail.android.data.network.QuailApi
import kotlinx.coroutines.delay
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody

data class CsvProcessSummary(val processed: Int, val imported: Int, val review: Int, val failed: Int)

private fun presetMatchesPreview(preset: CsvMappingPreset, preview: CsvPreviewResponse): Boolean {
    val previewSignature = csvHeaderSignature(preview.columns)
    val saved = preset.headerSignature?.trim()
    if (!saved.isNullOrEmpty()) {
        return normalizedText(saved) == previewSignature
    }
    val valid = preview.columns.map { it.index }.toSet()
    val required = listOfNotNull(preset.purchaseCol, preset.merchantCol, preset.amountCol, preset.debitCol, preset.creditCol, preset.postedCol, preset.indicatorCol)
    return required.all { valid.contains(it) }
}

private fun mappingFields(preset: CsvMappingPreset, accountId: Int): Map<String, RequestBody> {
    val textPlain = "text/plain".toMediaTypeOrNull()
    val fields = mutableMapOf<String, RequestBody>()
    fields["delimiter"] = "auto".toRequestBody(textPlain)
    fields["account_id"] = accountId.toString().toRequestBody(textPlain)
    fields["credit_indicator_value"] = (preset.creditIndicatorValue ?: "credit").toRequestBody(textPlain)
    fields["invert_amount"] = (if (preset.invertAmount) "true" else "false").toRequestBody(textPlain)
    preset.purchaseCol?.let { fields["purchase_col"] = it.toString().toRequestBody(textPlain) }
    preset.postedCol?.let { fields["posted_col"] = it.toString().toRequestBody(textPlain) }
    preset.merchantCol?.let { fields["merchant_col"] = it.toString().toRequestBody(textPlain) }
    preset.categoryCol?.let { fields["category_col"] = it.toString().toRequestBody(textPlain) }
    if (preset.amountCol != null) {
        fields["amount_col"] = preset.amountCol.toString().toRequestBody(textPlain)
    } else {
        preset.debitCol?.let { fields["debit_col"] = it.toString().toRequestBody(textPlain) }
        preset.creditCol?.let { fields["credit_col"] = it.toString().toRequestBody(textPlain) }
    }
    preset.indicatorCol?.let { fields["indicator_col"] = it.toString().toRequestBody(textPlain) }
    return fields
}

object CsvImportProcessor {
    suspend fun processOne(
        api: QuailApi,
        repository: CsvImportRepository,
        item: CsvImportQueueEntity,
        onProgress: (String) -> Unit = {},
    ): String {
        val file = repository.storedFile(item)
        if (!file.exists()) {
            repository.updateStatus(item.id, CsvImportStatus.FAILED, "Stored file could not be read.")
            return CsvImportStatus.FAILED
        }

        return try {
            val preview = repository.fetchPreviewFromFile(file)
            onProgress("Checking saved mapping for ${item.accountLabel}")

            val presetResponse = api.getCsvMappingPreset(accountId = item.accountId)
            val preset = presetResponse.preset
            if (!presetResponse.found || preset == null || !preset.hasRequiredMapping || !presetMatchesPreview(preset, preview)) {
                val detail = "Saved mapping missing or header did not match. Review in app."
                repository.updateStatus(item.id, CsvImportStatus.NEEDS_REVIEW, detail)
                return CsvImportStatus.NEEDS_REVIEW
            }

            onProgress("Importing ${preview.rowCount} rows from ${item.originalFileName}")
            val fileBody = file.readBytes().toRequestBody("text/csv".toMediaTypeOrNull())
            val part = MultipartBody.Part.createFormData("file", item.originalFileName, fileBody)
            val jobResponse = api.ingestCsvMappedAsync(part, mappingFields(preset, item.accountId))

            var status = "running"
            var inserted = 0
            var updated = 0
            var skipped = 0
            var errorMsg: String? = null
            while (status == "running") {
                delay(800)
                val job = api.getCsvJobStatus(jobResponse.jobId)
                status = job.status
                inserted = job.inserted ?: inserted
                updated = job.updated ?: updated
                skipped = job.skipped ?: skipped
                errorMsg = job.error
                onProgress("Row ${job.processedRows ?: 0} of ${job.totalRows ?: preview.rowCount}")
            }

            if (status == "failed") {
                repository.updateStatus(item.id, CsvImportStatus.FAILED, errorMsg ?: "Import failed")
                CsvImportStatus.FAILED
            } else {
                val detail = "Inserted $inserted, updated $updated, skipped $skipped."
                repository.updateStatus(item.id, CsvImportStatus.IMPORTED, detail)
                CsvImportStatus.IMPORTED
            }
        } catch (e: Exception) {
            repository.updateStatus(item.id, CsvImportStatus.FAILED, e.message ?: "Import failed")
            CsvImportStatus.FAILED
        }
    }

    suspend fun processAll(
        api: QuailApi,
        repository: CsvImportRepository,
        onProgress: (processed: Int, total: Int, statusText: String) -> Unit = { _, _, _ -> },
    ): CsvProcessSummary {
        val candidates = repository.getAll().filter {
            it.status == CsvImportStatus.ASSIGNED || it.status == CsvImportStatus.FAILED || it.status == CsvImportStatus.NEEDS_REVIEW
        }
        if (candidates.isEmpty()) return CsvProcessSummary(0, 0, 0, 0)

        var imported = 0
        var review = 0
        var failed = 0

        candidates.forEachIndexed { index, item ->
            repository.updateStatus(item.id, CsvImportStatus.PROCESSING, "Processing ${item.originalFileName}...")
            onProgress(index, candidates.size, "${item.accountLabel}: ${item.originalFileName}")
            val result = processOne(api, repository, item) { text -> onProgress(index, candidates.size, text) }
            when (result) {
                CsvImportStatus.IMPORTED -> imported++
                CsvImportStatus.NEEDS_REVIEW -> review++
                CsvImportStatus.FAILED -> failed++
            }
            onProgress(index + 1, candidates.size, "Processed ${index + 1} of ${candidates.size}")
        }

        return CsvProcessSummary(candidates.size, imported, review, failed)
    }
}
