package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

// ---- Email Parser Wizard: GET/POST /email-parser/trial/* ----
// Separate concept from category rules (which categorize existing
// transactions by merchant keyword) — this reads Gmail messages and creates
// new transaction drafts from forwarded bank/card notification emails.

@Serializable
data class ParserAccountItem(
    val id: Int,
    val institution: String? = null,
    val name: String? = null,
    val accounttype: String? = null,
    @SerialName("receives_emails") val receivesEmails: Boolean = true,
    @SerialName("has_parser_setting") val hasParserSetting: Boolean = false,
)

@Serializable
data class ParserAccountsResponse(
    val ok: Boolean = true,
    val accounts: List<ParserAccountItem> = emptyList(),
)

@Serializable
data class ParserSamplesRequest(
    @SerialName("account_id") val accountId: Int,
    @SerialName("sender_query") val senderQuery: String,
    @SerialName("subject_query") val subjectQuery: String = "",
    @SerialName("try_html_on_missing_fields") val tryHtmlOnMissingFields: Boolean = false,
    @SerialName("lookback_days") val lookbackDays: Int = 30,
    val limit: Int = 40,
)

@Serializable
data class ParserSampleItem(
    @SerialName("sample_id") val sampleId: String,
    val sender: String? = null,
    val subject: String? = null,
    @SerialName("received_at") val receivedAt: String? = null,
    val snippet: String? = null,
    val body: String? = null,
    @SerialName("account_id") val accountId: Int? = null,
)

@Serializable
data class ParserSamplesResponse(
    val ok: Boolean = true,
    val items: List<ParserSampleItem> = emptyList(),
    val count: Int = 0,
    val stale: Boolean = false,
    val warning: String? = null,
)

@Serializable
data class ParserWizardFieldMap(
    @SerialName("amount_group") val amountGroup: Int = 1,
    @SerialName("merchant_group") val merchantGroup: Int = 2,
    @SerialName("date_group") val dateGroup: Int = 3,
    @SerialName("time_group") val timeGroup: Int = 0,
)

@Serializable
data class ParserWizardGuided(
    @SerialName("amount_label") val amountLabel: String = "",
    @SerialName("merchant_label") val merchantLabel: String = "",
    @SerialName("date_label") val dateLabel: String = "",
    @SerialName("time_label") val timeLabel: String = "",
    @SerialName("amount_order") val amountOrder: Int = 1,
    @SerialName("merchant_order") val merchantOrder: Int = 2,
    @SerialName("date_order") val dateOrder: Int = 3,
    @SerialName("time_order") val timeOrder: Int = 0,
    @SerialName("amount_end") val amountEnd: String = "auto",
    @SerialName("merchant_end") val merchantEnd: String = "auto",
    @SerialName("date_end") val dateEnd: String = "auto",
    @SerialName("time_end") val timeEnd: String = "auto",
    @SerialName("amount_end_text") val amountEndText: String = "",
    @SerialName("merchant_end_text") val merchantEndText: String = "",
    @SerialName("date_end_text") val dateEndText: String = "",
    @SerialName("time_end_text") val timeEndText: String = "",
    @SerialName("account_before") val accountBefore: String = "",
    @SerialName("account_exact") val accountExact: String = "",
)

@Serializable
data class ParserWizardSetting(
    @SerialName("draft_id") val draftId: Int = 0,
    val name: String = "",
    @SerialName("subject_contains") val subjectContains: String = "",
    @SerialName("sender_pattern") val senderPattern: String = "",
    @SerialName("parser_mode") val parserMode: String = "guided",
    @SerialName("parsing_method") val parsingMethod: String = "guided_blocks",
    @SerialName("parser_slot") val parserSlot: String = "parser_1",
    @SerialName("override_on_primary") val overrideOnPrimary: Boolean = false,
    @SerialName("backup_assume_unknown") val backupAssumeUnknown: Boolean = false,
    @SerialName("invert_amount_sign") val invertAmountSign: Boolean = false,
    @SerialName("pending_ttl_minutes") val pendingTtlMinutes: Int = 30,
    @SerialName("body_regex") val bodyRegex: String = "",
    val flags: String = "i",
    @SerialName("field_map") val fieldMap: ParserWizardFieldMap = ParserWizardFieldMap(),
    val guided: ParserWizardGuided = ParserWizardGuided(),
)

@Serializable
data class ParserAccountSettingsResponse(
    val ok: Boolean = true,
    @SerialName("account_id") val accountId: Int = 0,
    val settings: List<ParserWizardSetting> = emptyList(),
)

/** Shared shape for both /preview (sampleIds required, name/status ignored)
 * and /save (name required, sampleIds ignored) — kept as one request class
 * since the two endpoints otherwise take an identical parser config. */
@Serializable
data class ParserConfigRequest(
    val name: String = "",
    @SerialName("parser_mode") val parserMode: String = "guided",
    @SerialName("parsing_method") val parsingMethod: String = "guided_blocks",
    @SerialName("account_id") val accountId: Int,
    @SerialName("sender_pattern") val senderPattern: String = "",
    @SerialName("subject_contains") val subjectContains: String = "",
    @SerialName("body_regex") val bodyRegex: String = "",
    val flags: String = "i",
    @SerialName("field_map") val fieldMap: ParserWizardFieldMap = ParserWizardFieldMap(),
    val guided: ParserWizardGuided = ParserWizardGuided(),
    @SerialName("sample_ids") val sampleIds: List<String> = emptyList(),
    @SerialName("parser_slot") val parserSlot: String = "parser_1",
    @SerialName("override_on_primary") val overrideOnPrimary: Boolean = false,
    @SerialName("backup_assume_unknown") val backupAssumeUnknown: Boolean = false,
    @SerialName("invert_amount_sign") val invertAmountSign: Boolean = false,
    @SerialName("pending_ttl_minutes") val pendingTtlMinutes: Int = 30,
    val status: String = "trial_inactive",
)

@Serializable
data class ParserPreviewRow(
    @SerialName("sample_id") val sampleId: String,
    val matched: Boolean = false,
    val extracted: Map<String, String> = emptyMap(),
    val error: String? = null,
)

@Serializable
data class ParserPreviewResponse(
    val ok: Boolean = true,
    val rows: List<ParserPreviewRow> = emptyList(),
    val matched: Int = 0,
)

@Serializable
data class ParserSaveResponse(
    val ok: Boolean = true,
    @SerialName("draft_id") val draftId: Int = 0,
)

@Serializable
data class ParserCorrelationRequest(
    @SerialName("account_id") val accountId: Int,
    @SerialName("primary_draft_id") val primaryDraftId: Int,
    @SerialName("secondary_draft_id") val secondaryDraftId: Int? = null,
    @SerialName("sample_ids") val sampleIds: List<String> = emptyList(),
)

@Serializable
data class ParserCorrelationSummary(
    @SerialName("no_match") val noMatch: Int = 0,
    val pending: Int = 0,
    val resolved: Int = 0,
    @SerialName("notify_immediate") val notifyImmediate: Int = 0,
    @SerialName("skip_already_notified") val skipAlreadyNotified: Int = 0,
    @SerialName("insert_trial") val insertTrial: Int = 0,
    @SerialName("merge_existing") val mergeExisting: Int = 0,
)

@Serializable
data class ParserCorrelationRow(
    @SerialName("sample_id") val sampleId: String,
    val subject: String? = null,
    val sender: String? = null,
    @SerialName("received_at") val receivedAt: String? = null,
    @SerialName("matched_rule") val matchedRule: String? = null,
    val action: String? = null,
    @SerialName("tx_action") val txAction: String? = null,
    val notify: Boolean = false,
    val key: String? = null,
    val extracted: Map<String, String> = emptyMap(),
)

@Serializable
data class ParserCorrelationResponse(
    val ok: Boolean = true,
    val summary: ParserCorrelationSummary = ParserCorrelationSummary(),
    @SerialName("pending_count") val pendingCount: Int = 0,
    val rows: List<ParserCorrelationRow> = emptyList(),
)

@Serializable
data class ParserDraftsResetRequest(@SerialName("account_id") val accountId: Int? = null)

@Serializable
data class ParserDraftsResetResponse(val ok: Boolean = true, val deleted: Int = 0)

@Serializable
data class ParserDraftDeleteOneRequest(
    @SerialName("account_id") val accountId: Int,
    @SerialName("parser_slot") val parserSlot: String,
)

@Serializable
data class ParserDraftDeleteOneResponse(
    val ok: Boolean = true,
    val deleted: Int = 0,
    @SerialName("account_id") val accountId: Int = 0,
    @SerialName("parser_slot") val parserSlot: String = "",
)

@Serializable
data class ParserTestRunRequest(
    @SerialName("sender_query") val senderQuery: String = "",
    @SerialName("subject_query") val subjectQuery: String = "",
    @SerialName("try_html_on_missing_fields") val tryHtmlOnMissingFields: Boolean = false,
    @SerialName("lookback_days") val lookbackDays: Int = 7,
    val limit: Int = 40,
)

@Serializable
data class ParserTestRunSummary(
    val fetched: Int = 0,
    val parsers: Int = 0,
    val matched: Int = 0,
    val skipped: Int = 0,
    @SerialName("would_insert") val wouldInsert: Int = 0,
    @SerialName("would_skip_insert") val wouldSkipInsert: Int = 0,
)

@Serializable
data class ParserTestRunParserRef(
    @SerialName("draft_id") val draftId: Int = 0,
    val name: String = "",
    @SerialName("account_id") val accountId: Int = 0,
    @SerialName("account_label") val accountLabel: String = "",
    val slot: String = "",
    @SerialName("override_on_primary") val overrideOnPrimary: Boolean = false,
    @SerialName("backup_assume_unknown") val backupAssumeUnknown: Boolean = false,
    @SerialName("invert_amount_sign") val invertAmountSign: Boolean = false,
)

@Serializable
data class ParserTestRunRow(
    @SerialName("sample_id") val sampleId: String,
    val subject: String? = null,
    val sender: String? = null,
    @SerialName("received_at") val receivedAt: String? = null,
    val matched: Boolean = false,
    val parser: ParserTestRunParserRef? = null,
    @SerialName("would_insert") val wouldInsert: Boolean = false,
    @SerialName("skip_reason") val skipReason: String = "",
    val extracted: Map<String, String> = emptyMap(),
    @SerialName("would_db_row") val wouldDbRow: JsonElement? = null,
)

@Serializable
data class ParserTestRunResponse(
    val ok: Boolean = true,
    val summary: ParserTestRunSummary = ParserTestRunSummary(),
    val rows: List<ParserTestRunRow> = emptyList(),
)
