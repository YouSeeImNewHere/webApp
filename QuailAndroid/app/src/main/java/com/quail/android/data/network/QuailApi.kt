package com.quail.android.data.network

import com.quail.android.data.model.BankInfoOptions
import com.quail.android.data.model.BudgetGroupUpsertRequest
import com.quail.android.data.model.BudgetGroupUpsertResponse
import com.quail.android.data.model.CategoryRuleApplyJobResponse
import com.quail.android.data.model.CategoryRuleCreateRequest
import com.quail.android.data.model.CategoryRuleCreateResponse
import com.quail.android.data.model.ChartPoint
import com.quail.android.data.model.ExtraSavedDetail
import com.quail.android.data.model.FinancingPlanCreateRequest
import com.quail.android.data.model.FinancingPlanResponse
import com.quail.android.data.model.HomePayload
import com.quail.android.data.model.AndroidPushDeviceBody
import com.quail.android.data.model.AndroidPushDeviceResponse
import com.quail.android.data.model.AndroidPushTestBody
import com.quail.android.data.model.AndroidPushTestResponse
import com.quail.android.data.model.HomelabMetricsResponse
import com.quail.android.data.model.MonthBudget
import com.quail.android.data.model.MonthlyReport
import com.quail.android.data.model.NotificationDetail
import com.quail.android.data.model.NotificationListResponse
import com.quail.android.data.model.NotificationSettingsResponse
import com.quail.android.data.model.OkResponse
import com.quail.android.data.model.PageBudgetResponse
import com.quail.android.data.model.RecurringCalendarResponse
import com.quail.android.data.model.RecurringGroup
import com.quail.android.data.model.RefreshCacheResponse
import com.quail.android.data.model.RoundUpSettings
import com.quail.android.data.model.RoundUpSettingsUpdateRequest
import com.quail.android.data.model.SavingsGoalUpdateRequest
import com.quail.android.data.model.SinkingFundAdjustRequest
import com.quail.android.data.model.SinkingFundAdjustResponse
import com.quail.android.data.model.SinkingFundCreateRequest
import com.quail.android.data.model.SinkingFundIdResponse
import com.quail.android.data.model.SinkingFundUpdateRequest
import com.quail.android.data.model.SpentSoFarBreakdown
import com.quail.android.data.model.SpentSoFarTransactionsResponse
import com.quail.android.data.model.Transaction
import com.quail.android.data.model.TransactionDetailResponse
import com.quail.android.data.model.TxCategoryUpdateRequest
import com.quail.android.data.model.TxCategoryUpdateResponse
import com.quail.android.data.model.TxDeleteResponse
import com.quail.android.data.model.TxIgnoreUpdateRequest
import com.quail.android.data.model.TxIgnoreUpdateResponse
import com.quail.android.data.model.TxInvertAmountResponse
import com.quail.android.data.model.TxMetaUpdateRequest
import com.quail.android.data.model.TxMetaUpdateResponse
import com.quail.android.data.model.UnassignedTransaction
import com.quail.android.data.model.UpcomingRequest
import com.quail.android.data.model.UpcomingResponse
import com.quail.android.data.model.VerifyBalanceRequest
import com.quail.android.data.model.VerifyBalanceResponse
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface QuailApi {
    @GET("page/home")
    suspend fun getHome(@Query("tx_limit") txLimit: Int = 15): HomePayload

    @POST("page/home/upcoming")
    suspend fun getUpcoming(@Body request: UpcomingRequest = UpcomingRequest()): UpcomingResponse

    // mode is one of ChartMode.path ("net-worth"/"savings"/"investments"/"spending")
    // — each is its own top-level route in analytics.py, not a query param.
    @GET("{mode}")
    suspend fun getChartSeries(
        @Path("mode") mode: String,
        @Query("start") start: String,
        @Query("end") end: String,
    ): List<ChartPoint>

    @GET("extra-saved-detail")
    suspend fun getExtraSavedDetail(): ExtraSavedDetail

    @GET("transaction/{id}")
    suspend fun getTransactionDetail(@Path("id") id: String): TransactionDetailResponse

    @POST("transaction/{id}/category")
    suspend fun setTransactionCategory(
        @Path("id") id: String,
        @Body request: TxCategoryUpdateRequest,
    ): TxCategoryUpdateResponse

    @PATCH("transaction/{id}/meta")
    suspend fun updateTransactionMeta(
        @Path("id") id: String,
        @Body request: TxMetaUpdateRequest,
    ): TxMetaUpdateResponse

    @POST("transaction/{id}/invert-amount")
    suspend fun invertTransactionAmount(@Path("id") id: String): TxInvertAmountResponse

    @POST("transaction/{id}/ignore")
    suspend fun setTransactionIgnored(
        @Path("id") id: String,
        @Body request: TxIgnoreUpdateRequest,
    ): TxIgnoreUpdateResponse

    @DELETE("transaction/{id}")
    suspend fun deleteTransaction(@Path("id") id: String): TxDeleteResponse

    @GET("spent-so-far-breakdown")
    suspend fun getSpentSoFarBreakdown(
        @Query("start") start: String,
        @Query("end") end: String,
    ): SpentSoFarBreakdown

    @GET("spent-so-far-transactions")
    suspend fun getSpentSoFarTransactions(
        @Query("category") category: String,
        @Query("start") start: String,
        @Query("end") end: String,
        @Query("limit") limit: Int = 500,
    ): SpentSoFarTransactionsResponse

    @GET("unassigned")
    suspend fun getUnassigned(
        @Query("limit") limit: Int = 25,
        @Query("mode") mode: String = "freq",
    ): List<UnassignedTransaction>

    @POST("category-rules")
    suspend fun createCategoryRule(@Body request: CategoryRuleCreateRequest): CategoryRuleCreateResponse

    @GET("category-rules/jobs/{jobId}")
    suspend fun getCategoryRuleApplyJob(@Path("jobId") jobId: Int): CategoryRuleApplyJobResponse

    @GET("categories")
    suspend fun getCategories(): List<String>

    @POST("financing/plans")
    suspend fun createFinancingPlan(@Body request: FinancingPlanCreateRequest): FinancingPlanResponse

    @POST("account/{id}/balance-verified")
    suspend fun verifyBalance(
        @Path("id") accountId: Int,
        @Body request: VerifyBalanceRequest,
    ): VerifyBalanceResponse

    // ---- Notifications ----

    @GET("notifications")
    suspend fun getNotifications(@Query("limit") limit: Int = 100): NotificationListResponse

    @GET("notifications/{id}")
    suspend fun getNotificationDetail(@Path("id") id: Int): NotificationDetail

    @POST("notifications/{id}/read")
    suspend fun markNotificationRead(@Path("id") id: Int): OkResponse

    @POST("notifications/{id}/dismiss")
    suspend fun dismissNotification(@Path("id") id: Int): OkResponse

    @POST("notifications/mark-all-read")
    suspend fun markAllNotificationsRead(): OkResponse

    @POST("notifications/clear-read")
    suspend fun clearReadNotifications(): OkResponse

    // ---- Settings ----

    @GET("settings/notifications")
    suspend fun getNotificationSettings(): NotificationSettingsResponse

    @POST("settings/notifications")
    suspend fun setNotificationSettings(@Body prefs: Map<String, Boolean>): NotificationSettingsResponse

    @POST("settings/refresh-home-widget-cache")
    suspend fun refreshHomeWidgetCache(): RefreshCacheResponse

    @GET("admin/homelab-metrics")
    suspend fun getHomelabMetrics(): HomelabMetricsResponse

    @POST("notifications/android/devices")
    suspend fun registerAndroidPushDevice(@Body body: AndroidPushDeviceBody): AndroidPushDeviceResponse

    @DELETE("notifications/android/devices")
    suspend fun deleteAndroidPushDevice(@Body body: AndroidPushDeviceBody): AndroidPushDeviceResponse

    @POST("notifications/android/test")
    suspend fun sendAndroidPushTest(@Body body: AndroidPushTestBody): AndroidPushTestResponse

    // ---- Recurring ----

    @GET("recurring")
    suspend fun getRecurring(
        @Query("min_occ") minOcc: Int = 3,
        @Query("include_stale") includeStale: Boolean = false,
    ): List<RecurringGroup>

    @POST("recurring/ignore/merchant")
    suspend fun ignoreRecurringMerchant(@Query("name") name: String): OkResponse

    @POST("recurring/unignore/merchant")
    suspend fun unignoreRecurringMerchant(@Query("name") name: String): OkResponse

    @POST("recurring/ignore/pattern")
    suspend fun ignoreRecurringPattern(
        @Query("merchant") merchant: String,
        @Query("amount") amount: Double,
        @Query("account_id") accountId: Int = -1,
    ): OkResponse

    @GET("recurring/calendar")
    suspend fun getRecurringCalendar(
        @Query("year") year: Int,
        @Query("month") month: Int,
        @Query("min_occ") minOcc: Int = 3,
        @Query("include_stale") includeStale: Boolean = false,
    ): RecurringCalendarResponse

    // ---- All transactions ----

    @GET("transactions-all")
    suspend fun getTransactionsAll(
        @Query("limit") limit: Int = 50,
        @Query("offset") offset: Int = 0,
        @Query("merchant") merchant: String = "",
        @Query("card") account: String = "",
        @Query("category") category: String = "",
        @Query("start") start: String = "",
        @Query("end") end: String = "",
        @Query("amt_min") amtMin: Double? = null,
        @Query("amt_max") amtMax: Double? = null,
        @Query("amt_abs") amtAbs: Int = 1,
    ): List<Transaction>

    @GET("bank-info")
    suspend fun getBankInfo(): BankInfoOptions

    // ---- Analytics ----

    @GET("reports/monthly")
    suspend fun getMonthlyReport(@Query("month") month: String): MonthlyReport

    // ---- Budget ----

    @GET("page/budget")
    suspend fun getPageBudget(
        @Query("year") year: Int,
        @Query("month") month: Int,
        @Query("recalc") recalc: Int = 0,
    ): PageBudgetResponse

    @GET("month-budget")
    suspend fun getMonthBudget(@Query("year") year: Int, @Query("month") month: Int): MonthBudget

    @POST("budget/groups")
    suspend fun upsertBudgetGroup(@Body request: BudgetGroupUpsertRequest): BudgetGroupUpsertResponse

    @DELETE("budget/groups")
    suspend fun deleteBudgetGroup(
        @Query("year") year: Int,
        @Query("month") month: Int,
        @Query("name") name: String,
    ): OkResponse

    @POST("funds")
    suspend fun createFund(@Body request: SinkingFundCreateRequest): SinkingFundIdResponse

    @PATCH("funds/{id}")
    suspend fun updateFund(@Path("id") id: Int, @Body request: SinkingFundUpdateRequest): OkResponse

    @POST("funds/{id}/adjust")
    suspend fun adjustFund(@Path("id") id: Int, @Body request: SinkingFundAdjustRequest): SinkingFundAdjustResponse

    @DELETE("funds/{id}")
    suspend fun deleteFund(@Path("id") id: Int): OkResponse

    @POST("settings/savings-goal")
    suspend fun setSavingsGoal(@Body request: SavingsGoalUpdateRequest): OkResponse

    @GET("settings/round-ups")
    suspend fun getRoundUps(): RoundUpSettings

    @POST("settings/round-ups")
    suspend fun setRoundUps(@Body request: RoundUpSettingsUpdateRequest): RoundUpSettings
}
