package com.quail.android.csvimport

import android.content.Context
import android.net.Uri
import com.quail.android.data.model.CsvPreviewColumn
import com.quail.android.data.model.CsvPreviewResponse
import com.quail.android.data.network.QuailApi
import kotlinx.coroutines.flow.Flow
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.util.UUID

fun normalizedText(text: String): String =
    text.lowercase().replace(Regex("[^a-z0-9]+"), " ").trim()

fun csvHeaderSignature(columns: List<CsvPreviewColumn>): String =
    normalizedText(columns.joinToString("|") { it.label })

private fun sanitizeFileName(name: String): String {
    val cleaned = name.replace(Regex("[^A-Za-z0-9._-]+"), "-")
    return cleaned.ifBlank { "import.csv" }
}

class CsvImportRepository(
    private val api: QuailApi,
    private val db: CsvImportDatabase,
    private val context: Context,
) {
    private val queueDir: File by lazy {
        File(context.filesDir, "csv_import_queue").apply { mkdirs() }
    }
    private val prefs by lazy { context.getSharedPreferences("csv_header_account_cache", Context.MODE_PRIVATE) }

    val items: Flow<List<CsvImportQueueEntity>> = db.csvImportQueueDao().observeAll()

    fun suggestedAccountId(headerSignature: String): Int? {
        if (headerSignature.isBlank()) return null
        val v = prefs.getInt(headerSignature, -1)
        return if (v >= 0) v else null
    }

    fun rememberAccountForSignature(headerSignature: String, accountId: Int) {
        if (headerSignature.isBlank()) return
        prefs.edit().putInt(headerSignature, accountId).apply()
    }

    suspend fun fetchPreviewFromFile(file: File): CsvPreviewResponse =
        fetchPreviewFromBytes(file.readBytes(), file.name)

    suspend fun fetchPreviewFromBytes(bytes: ByteArray, fileName: String): CsvPreviewResponse {
        val body = bytes.toRequestBody("text/csv".toMediaTypeOrNull())
        val part = MultipartBody.Part.createFormData("file", fileName, body)
        val textPlain = "text/plain".toMediaTypeOrNull()
        return api.csvPreview(
            file = part,
            delimiter = "auto".toRequestBody(textPlain),
            headerRow = "1".toRequestBody(textPlain),
            dataStartRow = "2".toRequestBody(textPlain),
            maxRows = "8".toRequestBody(textPlain),
        )
    }

    suspend fun readUriBytes(uri: Uri): ByteArray =
        context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
            ?: throw IllegalStateException("Could not read shared file")

    suspend fun enqueueBytes(
        bytes: ByteArray,
        originalFileName: String,
        accountId: Int,
        accountLabel: String,
        headerSignature: String,
    ) {
        val id = UUID.randomUUID().toString()
        val storedFileName = "$id-${sanitizeFileName(originalFileName)}"
        File(queueDir, storedFileName).writeBytes(bytes)
        db.csvImportQueueDao().upsert(
            CsvImportQueueEntity(
                id = id,
                originalFileName = originalFileName,
                storedFileName = storedFileName,
                accountId = accountId,
                accountLabel = accountLabel,
                headerSignature = headerSignature,
                status = CsvImportStatus.ASSIGNED,
                detail = "Assigned to $accountLabel. Ready for batch processing.",
            ),
        )
    }

    fun storedFile(entity: CsvImportQueueEntity): File = File(queueDir, entity.storedFileName)

    suspend fun updateStatus(id: String, status: String, detail: String) =
        db.csvImportQueueDao().updateStatus(id, status, detail)

    suspend fun remove(id: String) {
        val entity = db.csvImportQueueDao().getAll().find { it.id == id } ?: return
        runCatching { storedFile(entity).delete() }
        db.csvImportQueueDao().delete(id)
    }

    suspend fun getAll(): List<CsvImportQueueEntity> = db.csvImportQueueDao().getAll()
}
