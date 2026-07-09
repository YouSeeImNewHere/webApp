package com.quail.android.data.network

import com.quail.android.data.model.BankInfoOptions
import com.quail.android.data.model.CorrectiveRecordRecord
import com.quail.android.data.model.CorrectiveRecordUpsertRequest
import com.quail.android.data.model.TireSetRecord
import com.quail.android.data.model.TireSetUpsertRequest
import com.quail.android.data.model.VehicleProcedureRecord
import com.quail.android.data.model.VehicleProcedureUpsertRequest
import com.quail.android.data.model.BugNoteRecord
import com.quail.android.data.model.BugNoteUpsertRequest
import com.quail.android.data.model.BugReportRecord
import com.quail.android.data.model.BugReportUpsertRequest
import com.quail.android.data.model.BudgetGroupUpsertRequest
import com.quail.android.data.model.BudgetGroupUpsertResponse
import com.quail.android.data.model.CategoryRuleApplyJobResponse
import com.quail.android.data.model.ProjectChecklistRecord
import com.quail.android.data.model.ProjectChecklistUpsertRequest
import com.quail.android.data.model.ProjectQuickNoteRecord
import com.quail.android.data.model.ProjectQuickNoteUpsertRequest
import com.quail.android.data.model.ProjectRecord
import com.quail.android.data.model.ProjectUpsertRequest
import com.quail.android.data.model.CategoryRuleCreateRequest
import com.quail.android.data.model.CategoryRuleCreateResponse
import com.quail.android.data.model.ChartPoint
import com.quail.android.data.model.BodyweightRecord
import com.quail.android.data.model.BodyweightUpsertRequest
import com.quail.android.data.model.ExtraSavedDetail
import com.quail.android.data.model.FinancingPlanCreateRequest
import com.quail.android.data.model.CustomExerciseRecord
import com.quail.android.data.model.CustomExerciseUpsertRequest
import com.quail.android.data.model.GarminConnectRequest
import com.quail.android.data.model.GarminConnectResponse
import com.quail.android.data.model.GarminDailyHealthRecord
import com.quail.android.data.model.GarminMfaRequest
import com.quail.android.data.model.GarminMfaResponse
import com.quail.android.data.model.GarminStatusResponse
import com.quail.android.data.model.FinancingPlanResponse
import com.quail.android.data.model.FinancingPlanPayResponse
import com.quail.android.data.model.GoalRecord
import com.quail.android.data.model.GoalUpsertRequest
import com.quail.android.data.model.AvailabilityRecord
import com.quail.android.data.model.AvailabilityUpsertRequest
import com.quail.android.data.model.StartPlanResponse
import com.quail.android.data.model.TrainingPlanStatus
import com.quail.android.data.model.ScheduledWorkoutRecord
import com.quail.android.data.model.CompleteScheduledWorkoutRequest
import com.quail.android.data.model.HomePayload
import com.quail.android.data.model.MilestoneRecord
import com.quail.android.data.model.MilestoneUpsertRequest
import com.quail.android.data.model.RoutineRecord
import com.quail.android.data.model.RoutineUpsertRequest
import com.quail.android.data.model.WorkoutSessionListResponse
import com.quail.android.data.model.WorkoutSessionRecord
import com.quail.android.data.model.WorkoutSessionUpsertRequest
import com.quail.android.data.model.AndroidPushDeviceBody
import com.quail.android.data.model.AndroidPushDeviceResponse
import com.quail.android.data.model.AndroidPushTestBody
import com.quail.android.data.model.AndroidPushTestResponse
import com.quail.android.data.model.HomelabMetricsResponse
import com.quail.android.data.model.InterestRateUpsertRequest
import com.quail.android.data.model.InterestRateUpsertResponse
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
import com.quail.android.data.model.VehicleFuelCreateRequest
import com.quail.android.data.model.VehicleFuelListResponse
import com.quail.android.data.model.VehicleFuelRecord
import com.quail.android.data.model.VehicleInspectionCreateRequest
import com.quail.android.data.model.VehicleInspectionItem
import com.quail.android.data.model.VehicleIssue
import com.quail.android.data.model.VehicleIssueCreateRequest
import com.quail.android.data.model.VehicleIssueResolveRequest
import com.quail.android.data.model.VehicleMaintenanceCreateRequest
import com.quail.android.data.model.VehicleMaintenanceListResponse
import com.quail.android.data.model.VehicleMaintenanceRecord
import com.quail.android.data.model.VehicleMileageUpdateRequest
import com.quail.android.data.model.VehicleProfile
import com.quail.android.data.model.VehicleProfileUpdateRequest
import com.quail.android.data.model.VerifyBalanceRequest
import com.quail.android.data.model.VerifyBalanceResponse
import com.quail.android.data.model.AccountInfoResponse
import com.quail.android.data.model.AccountTransactionsRangeResponse
import com.quail.android.data.model.TransactionCreateRequest
import com.quail.android.data.model.TransactionCreateResponse
import com.quail.android.data.model.WidgetSummaryResponse
import com.quail.android.data.model.CsvPreviewResponse
import com.quail.android.data.model.CsvMappingPresetResponse
import com.quail.android.data.model.CsvMappingPresetUpsertRequest
import com.quail.android.data.model.CsvIngestJobResponse
import com.quail.android.data.model.CsvJobStatusResponse
import com.quail.android.data.model.OnboardingStatusResponse
import com.quail.android.data.model.OnboardingAccountCreate
import com.quail.android.data.model.OnboardingAccountResponse
import com.quail.android.data.model.OnboardingAccountDeleteResponse
import com.quail.android.data.model.PushoverKeyRequest
import com.quail.android.data.model.PushoverKeyResponse
import com.quail.android.data.model.PushoverTestRequest
import com.quail.android.data.model.PushoverTestResponse
import com.quail.android.data.model.OnboardingCompleteRequest
import com.quail.android.data.model.OnboardingCompleteResponse
import com.quail.android.data.model.LESProfileResponse
import com.quail.android.data.model.LESProfileRequest
import com.quail.android.data.model.LESPaychecksRequest
import com.quail.android.data.model.LESPaychecksResponse
import com.quail.android.data.model.DailyWeightsResponse
import com.quail.android.data.model.DailyWeightsRequest
import com.quail.android.data.model.PaycheckMatchersResponse
import com.quail.android.data.model.PaycheckMatchersRequest
import com.quail.android.data.model.ParserAccountsResponse
import com.quail.android.data.model.ParserSamplesRequest
import com.quail.android.data.model.ParserSamplesResponse
import com.quail.android.data.model.ParserAccountSettingsResponse
import com.quail.android.data.model.ParserConfigRequest
import com.quail.android.data.model.ParserPreviewResponse
import com.quail.android.data.model.ParserSaveResponse
import com.quail.android.data.model.ParserCorrelationRequest
import com.quail.android.data.model.ParserCorrelationResponse
import com.quail.android.data.model.ParserDraftsResetRequest
import com.quail.android.data.model.ParserDraftsResetResponse
import com.quail.android.data.model.ParserDraftDeleteOneRequest
import com.quail.android.data.model.ParserDraftDeleteOneResponse
import com.quail.android.data.model.ParserTestRunRequest
import com.quail.android.data.model.ParserTestRunResponse
import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.ResponseBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Part
import retrofit2.http.PartMap
import retrofit2.http.Path
import retrofit2.http.Query
import retrofit2.http.Streaming

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

    @GET("financing/plans")
    suspend fun getFinancingPlans(): List<FinancingPlanResponse>

    @POST("financing/plans")
    suspend fun createFinancingPlan(@Body request: FinancingPlanCreateRequest): FinancingPlanResponse

    @DELETE("financing/plans/{id}")
    suspend fun deleteFinancingPlan(@Path("id") id: Int): OkResponse

    @POST("financing/plans/{id}/pay")
    suspend fun payFinancingPlan(@Path("id") id: Int): FinancingPlanPayResponse

    @POST("account/{id}/balance-verified")
    suspend fun verifyBalance(
        @Path("id") accountId: Int,
        @Body request: VerifyBalanceRequest,
    ): VerifyBalanceResponse

    @GET("account/{id}")
    suspend fun getAccountInfo(@Path("id") accountId: Int): AccountInfoResponse

    @GET("account-series")
    suspend fun getAccountSeries(
        @Query("account_id") accountId: Int,
        @Query("start") start: String,
        @Query("end") end: String,
    ): List<ChartPoint>

    @GET("account-transactions-range")
    suspend fun getAccountTransactionsRange(
        @Query("account_id") accountId: Int,
        @Query("start") start: String,
        @Query("end") end: String,
        @Query("limit") limit: Int = 500,
    ): AccountTransactionsRangeResponse

    @POST("transaction")
    suspend fun createTransaction(@Body request: TransactionCreateRequest): TransactionCreateResponse

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

    @POST("interest-rate")
    suspend fun setInterestRate(@Body request: InterestRateUpsertRequest): InterestRateUpsertResponse

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

    // ---- Vehicle (Quail Car) ----

    @GET("vehicle/profile")
    suspend fun getVehicleProfile(): VehicleProfile

    @PUT("vehicle/profile")
    suspend fun putVehicleProfile(@Body request: VehicleProfileUpdateRequest): VehicleProfile

    @PATCH("vehicle/profile/mileage")
    suspend fun updateVehicleMileage(@Body request: VehicleMileageUpdateRequest): OkResponse

    @GET("vehicle/fuel")
    suspend fun getVehicleFuel(@Query("limit") limit: Int = 200): VehicleFuelListResponse

    @POST("vehicle/fuel")
    suspend fun addVehicleFuel(@Body request: VehicleFuelCreateRequest): VehicleFuelRecord

    @DELETE("vehicle/fuel/{id}")
    suspend fun deleteVehicleFuel(@Path("id") id: Int): OkResponse

    @GET("vehicle/maintenance")
    suspend fun getVehicleMaintenance(@Query("limit") limit: Int = 200): VehicleMaintenanceListResponse

    @POST("vehicle/maintenance")
    suspend fun addVehicleMaintenance(@Body request: VehicleMaintenanceCreateRequest): VehicleMaintenanceRecord

    @DELETE("vehicle/maintenance/{id}")
    suspend fun deleteVehicleMaintenance(@Path("id") id: Int): OkResponse

    @GET("vehicle/issues")
    suspend fun getVehicleIssues(): List<VehicleIssue>

    @POST("vehicle/issues")
    suspend fun addVehicleIssue(@Body request: VehicleIssueCreateRequest): VehicleIssue

    @POST("vehicle/issues/{id}/resolve")
    suspend fun resolveVehicleIssue(@Path("id") id: Int, @Body request: VehicleIssueResolveRequest = VehicleIssueResolveRequest()): VehicleIssue

    @DELETE("vehicle/issues/{id}")
    suspend fun deleteVehicleIssue(@Path("id") id: Int): OkResponse

    @GET("vehicle/inspections")
    suspend fun getVehicleInspections(): List<VehicleInspectionItem>

    @POST("vehicle/inspections")
    suspend fun addVehicleInspection(@Body request: VehicleInspectionCreateRequest): VehicleInspectionItem

    @POST("vehicle/inspections/{id}/check")
    suspend fun checkVehicleInspection(@Path("id") id: Int): VehicleInspectionItem

    @GET("vehicle/tires")
    suspend fun getTireSets(): List<TireSetRecord>

    @POST("vehicle/tires")
    suspend fun upsertTireSet(@Body request: TireSetUpsertRequest): TireSetRecord

    @DELETE("vehicle/tires/{id}")
    suspend fun deleteTireSet(@Path("id") id: Int): OkResponse

    @GET("vehicle/corrective")
    suspend fun getCorrectiveRecords(): List<CorrectiveRecordRecord>

    @POST("vehicle/corrective")
    suspend fun upsertCorrectiveRecord(@Body request: CorrectiveRecordUpsertRequest): CorrectiveRecordRecord

    @DELETE("vehicle/corrective/{id}")
    suspend fun deleteCorrectiveRecord(@Path("id") id: Int): OkResponse

    @GET("vehicle/procedures")
    suspend fun getVehicleProcedures(): List<VehicleProcedureRecord>

    @POST("vehicle/procedures")
    suspend fun upsertVehicleProcedure(@Body request: VehicleProcedureUpsertRequest): VehicleProcedureRecord

    @DELETE("vehicle/procedures/{id}")
    suspend fun deleteVehicleProcedure(@Path("id") id: Int): OkResponse

    // ---- Fitness (Quail Fitness) ----

    @GET("fitness/sessions")
    suspend fun getWorkoutSessions(@Query("limit") limit: Int = 200): WorkoutSessionListResponse

    @POST("fitness/sessions")
    suspend fun upsertWorkoutSession(@Body request: WorkoutSessionUpsertRequest): WorkoutSessionRecord

    @DELETE("fitness/sessions/{id}")
    suspend fun deleteWorkoutSession(@Path("id") id: Int): OkResponse

    @GET("fitness/routines")
    suspend fun getRoutines(): List<RoutineRecord>

    @POST("fitness/routines")
    suspend fun upsertRoutine(@Body request: RoutineUpsertRequest): RoutineRecord

    @DELETE("fitness/routines/{id}")
    suspend fun deleteRoutine(@Path("id") id: Int): OkResponse

    @GET("fitness/goals")
    suspend fun getGoals(): List<GoalRecord>

    @POST("fitness/goals")
    suspend fun upsertGoal(@Body request: GoalUpsertRequest): GoalRecord

    @DELETE("fitness/goals/{id}")
    suspend fun deleteGoal(@Path("id") id: Int): OkResponse

    @GET("fitness/availability")
    suspend fun getFitnessAvailability(): AvailabilityRecord

    @POST("fitness/availability")
    suspend fun setFitnessAvailability(@Body request: AvailabilityUpsertRequest): AvailabilityRecord

    @POST("fitness/plan/start-testing-week")
    suspend fun startTrainingPlanTestingWeek(): StartPlanResponse

    @POST("fitness/plan/generate")
    suspend fun generateTrainingPlan(): StartPlanResponse

    @GET("fitness/plan/status")
    suspend fun getTrainingPlanStatus(): TrainingPlanStatus

    @GET("fitness/plan/scheduled")
    suspend fun getScheduledWorkouts(@Query("start") start: String? = null, @Query("end") end: String? = null): List<ScheduledWorkoutRecord>

    @POST("fitness/plan/scheduled/{id}/complete")
    suspend fun completeScheduledWorkout(@Path("id") id: Int, @Body request: CompleteScheduledWorkoutRequest): OkResponse

    @POST("fitness/plan/scheduled/{id}/skip")
    suspend fun skipScheduledWorkout(@Path("id") id: Int): OkResponse

    @GET("fitness/milestones")
    suspend fun getMilestones(): List<MilestoneRecord>

    @POST("fitness/milestones")
    suspend fun upsertMilestone(@Body request: MilestoneUpsertRequest): MilestoneRecord

    @DELETE("fitness/milestones/{id}")
    suspend fun deleteMilestone(@Path("id") id: Int): OkResponse

    @GET("fitness/custom-exercises")
    suspend fun getCustomExercises(): List<CustomExerciseRecord>

    @POST("fitness/custom-exercises")
    suspend fun upsertCustomExercise(@Body request: CustomExerciseUpsertRequest): CustomExerciseRecord

    @DELETE("fitness/custom-exercises/{id}")
    suspend fun deleteCustomExercise(@Path("id") id: Int): OkResponse

    @GET("fitness/garmin/status")
    suspend fun getGarminStatus(): GarminStatusResponse

    @POST("fitness/garmin/connect")
    suspend fun connectGarmin(@Body request: GarminConnectRequest): GarminConnectResponse

    @POST("fitness/garmin/mfa")
    suspend fun submitGarminMfa(@Body request: GarminMfaRequest): GarminMfaResponse

    @DELETE("fitness/garmin/connect")
    suspend fun disconnectGarmin(): OkResponse

    @GET("fitness/garmin/daily-health")
    suspend fun getGarminDailyHealth(@Query("days") days: Int = 14): List<GarminDailyHealthRecord>

    @GET("fitness/bodyweight")
    suspend fun getBodyweightLogs(@Query("limit") limit: Int = 200): List<BodyweightRecord>

    @POST("fitness/bodyweight")
    suspend fun upsertBodyweight(@Body request: BodyweightUpsertRequest): BodyweightRecord

    @DELETE("fitness/bodyweight/{id}")
    suspend fun deleteBodyweight(@Path("id") id: Int): OkResponse

    // ---- Bugs (Quail Bugs) ----

    @GET("bugs/reports")
    suspend fun getBugReports(): List<BugReportRecord>

    @POST("bugs/reports")
    suspend fun upsertBugReport(@Body request: BugReportUpsertRequest): BugReportRecord

    @DELETE("bugs/reports/{id}")
    suspend fun deleteBugReport(@Path("id") id: Int): OkResponse

    @Multipart
    @POST("bugs/reports/{clientId}/screenshot")
    suspend fun uploadBugScreenshot(@Path("clientId") clientId: String, @Part file: MultipartBody.Part): OkResponse

    @Streaming
    @GET("bugs/reports/{id}/screenshot")
    suspend fun getBugScreenshot(@Path("id") id: Int): ResponseBody

    @GET("bugs/notes")
    suspend fun getBugNotes(): List<BugNoteRecord>

    @POST("bugs/notes")
    suspend fun upsertBugNote(@Body request: BugNoteUpsertRequest): BugNoteRecord

    @DELETE("bugs/notes/{id}")
    suspend fun deleteBugNote(@Path("id") id: Int): OkResponse

    // ---- Widget (Quail Cash home screen widget) ----

    @GET("widget/summary")
    suspend fun getWidgetSummary(@Query("widget_script_version") widgetScriptVersion: Int): WidgetSummaryResponse

    // ---- CSV import (bank statement ingestion) ----

    @Multipart
    @POST("csv/preview")
    suspend fun csvPreview(
        @Part file: MultipartBody.Part,
        @Part("delimiter") delimiter: RequestBody,
        @Part("header_row") headerRow: RequestBody,
        @Part("data_start_row") dataStartRow: RequestBody,
        @Part("max_rows") maxRows: RequestBody,
    ): CsvPreviewResponse

    @GET("csv/mapping-presets")
    suspend fun getCsvMappingPreset(
        @Query("account_id") accountId: Int,
        @Query("institution_key") institutionKey: String = "__account__",
    ): CsvMappingPresetResponse

    @POST("csv/mapping-presets")
    suspend fun saveCsvMappingPreset(@Body body: CsvMappingPresetUpsertRequest): OkResponse

    @Multipart
    @POST("csv/ingest-mapped/async")
    suspend fun ingestCsvMappedAsync(
        @Part file: MultipartBody.Part,
        @PartMap fields: Map<String, @JvmSuppressWildcards RequestBody>,
    ): CsvIngestJobResponse

    @GET("csv/jobs/{jobId}")
    suspend fun getCsvJobStatus(@Path("jobId") jobId: String): CsvJobStatusResponse

    // ---- Projects (Quail Projects) ----

    @GET("projects")
    suspend fun getProjects(): List<ProjectRecord>

    @POST("projects")
    suspend fun upsertProject(@Body request: ProjectUpsertRequest): ProjectRecord

    @DELETE("projects/{id}")
    suspend fun deleteProject(@Path("id") id: Int): OkResponse

    @GET("projects/quick-notes")
    suspend fun getProjectQuickNotes(): List<ProjectQuickNoteRecord>

    @POST("projects/quick-notes")
    suspend fun upsertProjectQuickNote(@Body request: ProjectQuickNoteUpsertRequest): ProjectQuickNoteRecord

    @DELETE("projects/quick-notes/{id}")
    suspend fun deleteProjectQuickNote(@Path("id") id: Int): OkResponse

    @GET("projects/checklists")
    suspend fun getProjectChecklists(): List<ProjectChecklistRecord>

    @POST("projects/checklists")
    suspend fun upsertProjectChecklist(@Body request: ProjectChecklistUpsertRequest): ProjectChecklistRecord

    @DELETE("projects/checklists/{id}")
    suspend fun deleteProjectChecklist(@Path("id") id: Int): OkResponse

    // ---- Setup Wizard ----

    @GET("onboarding/status")
    suspend fun getOnboardingStatus(): OnboardingStatusResponse

    @POST("onboarding/accounts")
    suspend fun createOnboardingAccount(@Body request: OnboardingAccountCreate): OnboardingAccountResponse

    @PUT("onboarding/accounts/{id}")
    suspend fun updateOnboardingAccount(@Path("id") id: Int, @Body request: OnboardingAccountCreate): OnboardingAccountResponse

    @DELETE("onboarding/accounts/{id}")
    suspend fun deleteOnboardingAccount(@Path("id") id: Int): OnboardingAccountDeleteResponse

    @POST("onboarding/pushover-key")
    suspend fun setOnboardingPushoverKey(@Body request: PushoverKeyRequest): PushoverKeyResponse

    @POST("onboarding/pushover-test")
    suspend fun testOnboardingPushover(@Body request: PushoverTestRequest): PushoverTestResponse

    @POST("onboarding/complete")
    suspend fun completeOnboarding(@Body request: OnboardingCompleteRequest = OnboardingCompleteRequest()): OnboardingCompleteResponse

    // ---- Income Wizard ----

    @GET("les-profile")
    suspend fun getLesProfile(@Query("key") key: String = "default"): LESProfileResponse

    @POST("les-profile")
    suspend fun setLesProfile(@Body request: LESProfileRequest): LESProfileResponse

    @POST("les/paychecks")
    suspend fun getLesPaychecks(@Body request: LESPaychecksRequest): LESPaychecksResponse

    @GET("settings/daily-weights")
    suspend fun getDailyWeights(): DailyWeightsResponse

    @POST("settings/daily-weights")
    suspend fun setDailyWeights(@Body request: DailyWeightsRequest): DailyWeightsResponse

    @GET("settings/paycheck-matchers")
    suspend fun getPaycheckMatchers(): PaycheckMatchersResponse

    @POST("settings/paycheck-matchers")
    suspend fun setPaycheckMatchers(@Body request: PaycheckMatchersRequest): PaycheckMatchersResponse

    // ---- Email Parser Wizard ----

    @GET("email-parser/trial/accounts")
    suspend fun getParserAccounts(): ParserAccountsResponse

    @POST("email-parser/trial/samples")
    suspend fun getParserSamples(@Body request: ParserSamplesRequest): ParserSamplesResponse

    @GET("email-parser/trial/account-settings/{accountId}")
    suspend fun getParserAccountSettings(@Path("accountId") accountId: Int): ParserAccountSettingsResponse

    @POST("email-parser/trial/preview")
    suspend fun previewParserConfig(@Body request: ParserConfigRequest): ParserPreviewResponse

    @POST("email-parser/trial/save")
    suspend fun saveParserConfig(@Body request: ParserConfigRequest): ParserSaveResponse

    @POST("email-parser/trial/correlation-preview")
    suspend fun previewParserCorrelation(@Body request: ParserCorrelationRequest): ParserCorrelationResponse

    @POST("email-parser/trial/drafts/reset")
    suspend fun resetParserDrafts(@Body request: ParserDraftsResetRequest): ParserDraftsResetResponse

    @POST("email-parser/trial/draft/delete-one")
    suspend fun deleteParserDraft(@Body request: ParserDraftDeleteOneRequest): ParserDraftDeleteOneResponse

    @POST("email-parser/trial/test-run")
    suspend fun runParserTest(@Body request: ParserTestRunRequest): ParserTestRunResponse
}
