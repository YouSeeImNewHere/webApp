package com.quail.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ---- Income Wizard: LES profile, paycheck projection, daily weights, paycheck matchers ----

@Serializable
data class LESProfile(
    val paygrade: String = "E-5",
    @SerialName("service_start") val serviceStart: String = "2020-01-01",
    @SerialName("has_dependents") val hasDependents: Boolean = true,
    val bas: Double = 465.77,
    @SerialName("bah_override") val bahOverride: Double? = null,
    @SerialName("submarine_pay") val submarinePay: Double = 0.0,
    @SerialName("career_sea_pay") val careerSeaPay: Double = 0.0,
    @SerialName("spec_duty_pay") val specDutyPay: Double = 0.0,
    @SerialName("tsp_rate") val tspRate: Double = 0.05,
    @SerialName("filing_status") val filingStatus: String = "S",
    @SerialName("step2_multiple_jobs") val step2MultipleJobs: Boolean = false,
    @SerialName("dep_under17") val depUnder17: Int = 0,
    @SerialName("other_dep") val otherDep: Int = 0,
    @SerialName("other_income_annual") val otherIncomeAnnual: Double = 0.0,
    @SerialName("other_deductions_annual") val otherDeductionsAnnual: Double = 0.0,
    @SerialName("extra_withholding") val extraWithholding: Double = 0.0,
    @SerialName("meal_rate") val mealRate: Double = 13.30,
    @SerialName("meal_end_day") val mealEndDay: Int = 31,
    @SerialName("meal_deduction_enabled") val mealDeductionEnabled: Boolean = false,
    @SerialName("meal_deduction_start") val mealDeductionStart: String? = null,
    @SerialName("mid_month_fraction") val midMonthFraction: Double = 0.50,
    @SerialName("allotments_total") val allotmentsTotal: Double = 0.0,
    @SerialName("mid_month_collections_total") val midMonthCollectionsTotal: Double = 0.0,
    @SerialName("fica_include_special_pays") val ficaIncludeSpecialPays: Boolean = false,
)

@Serializable
data class LESProfileResponse(
    val key: String = "default",
    val profile: LESProfile = LESProfile(),
)

@Serializable
data class LESProfileRequest(
    val key: String = "default",
    val profile: LESProfile,
)

@Serializable
data class LESPaycheckEvent(
    val date: String,
    @SerialName("pay_target") val payTarget: String? = null,
    val cadence: String? = null,
    val merchant: String? = null,
    val amount: Double = 0.0,
    val type: String? = null,
    @SerialName("account_id") val accountId: Int? = null,
    val spillover: Boolean = false,
)

@Serializable
data class LESEntitlements(
    @SerialName("base_pay") val basePay: Double = 0.0,
    val bah: Double = 0.0,
    val bas: Double = 0.0,
    @SerialName("submarine_pay") val submarinePay: Double = 0.0,
    @SerialName("career_sea_pay") val careerSeaPay: Double = 0.0,
    @SerialName("spec_duty_pay") val specDutyPay: Double = 0.0,
)

@Serializable
data class LESW4(
    @SerialName("filing_status") val filingStatus: String = "S",
    @SerialName("step2_multiple_jobs") val step2MultipleJobs: Boolean = false,
    @SerialName("dep_under17") val depUnder17: Int = 0,
    @SerialName("other_dep") val otherDep: Int = 0,
    @SerialName("other_income_annual") val otherIncomeAnnual: Double = 0.0,
    @SerialName("other_deductions_annual") val otherDeductionsAnnual: Double = 0.0,
    @SerialName("extra_withholding") val extraWithholding: Double = 0.0,
)

@Serializable
data class LESRates(
    @SerialName("tsp_rate") val tspRate: Double = 0.0,
    @SerialName("meal_rate") val mealRate: Double = 0.0,
    @SerialName("meal_end_day") val mealEndDay: Int = 31,
    @SerialName("mid_month_fraction") val midMonthFraction: Double = 0.50,
)

@Serializable
data class LESDeductions(
    @SerialName("federal_taxes") val federalTaxes: Double = 0.0,
    @SerialName("fica_social_security") val ficaSocialSecurity: Double = 0.0,
    @SerialName("fica_medicare") val ficaMedicare: Double = 0.0,
    val sgli: Double = 0.0,
    val afrh: Double = 0.0,
    @SerialName("roth_tsp") val rothTsp: Double = 0.0,
    @SerialName("meal_deduction") val mealDeduction: Double = 0.0,
    @SerialName("allotments_total") val allotmentsTotal: Double = 0.0,
    @SerialName("mid_month_collections_total") val midMonthCollectionsTotal: Double = 0.0,
)

@Serializable
data class LESNet(
    @SerialName("projected_mid_month") val projectedMidMonth: Double = 0.0,
    @SerialName("projected_eom") val projectedEom: Double = 0.0,
    @SerialName("projected_monthly_net") val projectedMonthlyNet: Double = 0.0,
    @SerialName("mid_month_pay") val midMonthPay: Double = 0.0,
    val eom: Double = 0.0,
    @SerialName("mid_month_is_actual") val midMonthIsActual: Boolean = false,
    @SerialName("mid_month_actual") val midMonthActual: Double? = null,
)

@Serializable
data class LESBreakdown(
    @SerialName("as_of") val asOf: String? = null,
    val profile: LESProfile? = null,
    val entitlements: LESEntitlements = LESEntitlements(),
    val w4: LESW4 = LESW4(),
    val rates: LESRates = LESRates(),
    val deductions: LESDeductions = LESDeductions(),
    val net: LESNet = LESNet(),
)

@Serializable
data class LESPaychecksRequest(
    val year: Int,
    val month: Int,
    val profile: LESProfile,
)

@Serializable
data class LESPaychecksResponse(
    val events: List<LESPaycheckEvent> = emptyList(),
    val breakdown: LESBreakdown = LESBreakdown(),
)

@Serializable
data class DailyWeightsResponse(
    @SerialName("weekday_points") val weekdayPoints: Double = 1.0,
    @SerialName("weekend_points") val weekendPoints: Double = 2.0,
)

@Serializable
data class DailyWeightsRequest(
    @SerialName("weekday_points") val weekdayPoints: Double,
    @SerialName("weekend_points") val weekendPoints: Double,
)

@Serializable
data class PaycheckMatchersResponse(
    val keywords: List<String> = emptyList(),
)

@Serializable
data class PaycheckMatchersRequest(
    val keywords: List<String>,
)
