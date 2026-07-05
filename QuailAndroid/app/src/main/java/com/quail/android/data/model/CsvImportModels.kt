package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class CsvPreviewColumn(
    val index: Int = 0,
    val label: String = "",
)

@Serializable
data class CsvPreviewRow(
    @SerialName("row_number") val rowNumber: Int = 0,
    val cells: List<String> = emptyList(),
)

@Serializable
data class CsvPreviewResponse(
    val ok: Boolean = false,
    val delimiter: String = ",",
    @SerialName("has_header_detected") val hasHeaderDetected: Boolean = false,
    @SerialName("row_count") val rowCount: Int = 0,
    @SerialName("column_count") val columnCount: Int = 0,
    val columns: List<CsvPreviewColumn> = emptyList(),
    @SerialName("preview_rows") val previewRows: List<CsvPreviewRow> = emptyList(),
)

@Serializable
data class CsvMappingPreset(
    @SerialName("purchase_col") val purchaseCol: Int? = null,
    @SerialName("posted_col") val postedCol: Int? = null,
    @SerialName("amount_col") val amountCol: Int? = null,
    @SerialName("debit_col") val debitCol: Int? = null,
    @SerialName("credit_col") val creditCol: Int? = null,
    @SerialName("merchant_col") val merchantCol: Int? = null,
    @SerialName("category_col") val categoryCol: Int? = null,
    @SerialName("indicator_col") val indicatorCol: Int? = null,
    @SerialName("credit_indicator_value") val creditIndicatorValue: String? = "credit",
    @SerialName("invert_amount") val invertAmount: Boolean = false,
    @SerialName("header_signature") val headerSignature: String? = null,
) {
    val hasRequiredMapping: Boolean get() =
        purchaseCol != null && merchantCol != null && (amountCol != null || (debitCol != null && creditCol != null))
}

@Serializable
data class CsvMappingPresetResponse(
    val ok: Boolean = false,
    val found: Boolean = false,
    val preset: CsvMappingPreset? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
)

@Serializable
data class CsvMappingPresetUpsertRequest(
    @SerialName("account_id") val accountId: Int,
    @SerialName("institution_key") val institutionKey: String = "__account__",
    val preset: CsvMappingPreset,
)

@Serializable
data class CsvIngestJobResponse(
    val ok: Boolean = false,
    @SerialName("job_id") val jobId: String = "",
)

@Serializable
data class CsvJobStatusResponse(
    val ok: Boolean = false,
    val status: String = "",
    @SerialName("total_rows") val totalRows: Int? = null,
    @SerialName("processed_rows") val processedRows: Int? = null,
    val inserted: Int? = null,
    val updated: Int? = null,
    val skipped: Int? = null,
    val error: String? = null,
)
