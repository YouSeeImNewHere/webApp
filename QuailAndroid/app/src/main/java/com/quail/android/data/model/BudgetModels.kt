package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class BudgetGroup(
    val id: Int = 0,
    val name: String = "",
    val allocated: Double = 0.0,
    val cap: Double? = null,
    val categories: List<String> = emptyList(),
    val spent: Double = 0.0,
    val remaining: Double = 0.0,
    @SerialName("over_cap") val overCap: Boolean = false,
    @SerialName("read_only") val readOnly: Boolean = false,
    @SerialName("synthetic_kind") val syntheticKind: String? = null,
)

@Serializable
data class SinkingFund(
    val id: Int = 0,
    val name: String = "",
    @SerialName("target_amount") val targetAmount: Double = 0.0,
    @SerialName("target_date") val targetDate: String? = null,
    val cadence: String = "monthly",
    @SerialName("contrib_amount") val contribAmount: Double = 0.0,
    @SerialName("reserved_balance") val reservedBalance: Double = 0.0,
    @SerialName("needed_per_day") val neededPerDay: Double? = null,
    @SerialName("is_active") val isActive: Boolean = true,
)

@Serializable
data class BudgetSpentCategory(
    val category: String = "",
    val spent: Double = 0.0,
)

@Serializable
data class SavingsGoalConfig(
    val mode: String = "percent",
    val value: Double = 0.0,
)

@Serializable
data class PageBudgetResponse(
    val ok: Boolean = true,
    val month: MonthBudget? = null,
    val groups: List<BudgetGroup> = emptyList(),
    val funds: List<SinkingFund> = emptyList(),
    @SerialName("spent_categories") val spentCategories: List<BudgetSpentCategory> = emptyList(),
    @SerialName("savings_goal_cfg") val savingsGoalCfg: SavingsGoalConfig? = null,
)

@Serializable
data class BudgetGroupUpsertRequest(
    val year: Int,
    val month: Int,
    val name: String,
    val allocated: Double = 0.0,
    val cap: Double? = null,
    val categories: List<String> = emptyList(),
)

@Serializable
data class BudgetGroupUpsertResponse(val ok: Boolean = true, val id: Int = 0)

@Serializable
data class SinkingFundCreateRequest(
    val name: String,
    @SerialName("target_amount") val targetAmount: Double = 0.0,
    @SerialName("target_date") val targetDate: String? = null,
    val cadence: String = "monthly",
    @SerialName("contrib_amount") val contribAmount: Double = 0.0,
)

@Serializable
data class SinkingFundUpdateRequest(
    val name: String? = null,
    @SerialName("target_amount") val targetAmount: Double? = null,
    @SerialName("target_date") val targetDate: String? = null,
    val cadence: String? = null,
    @SerialName("contrib_amount") val contribAmount: Double? = null,
    @SerialName("is_active") val isActive: Boolean? = null,
)

@Serializable
data class SinkingFundIdResponse(val ok: Boolean = true, val id: Int = 0)

@Serializable
data class SinkingFundAdjustRequest(val amount: Double, val note: String = "")

@Serializable
data class SinkingFundAdjustResponse(val ok: Boolean = true, @SerialName("reserved_balance") val reservedBalance: Double = 0.0)

@Serializable
data class SavingsGoalUpdateRequest(val mode: String, val value: Double)

@Serializable
data class RoundUpSettings(val ok: Boolean = true, val enabled: Boolean = false, val category: String? = null)

@Serializable
data class RoundUpSettingsUpdateRequest(val enabled: Boolean)
