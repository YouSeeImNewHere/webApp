package com.quail.android.data.repository

import com.quail.android.data.model.BankInfoOptions
import com.quail.android.data.model.BudgetGroupUpsertRequest
import com.quail.android.data.model.CategoryRuleApplyJob
import com.quail.android.data.model.CategoryRuleCreateRequest
import com.quail.android.data.model.CategoryRuleCreateResponse
import com.quail.android.data.model.ChartMode
import com.quail.android.data.model.ChartPoint
import com.quail.android.data.model.ExtraSavedDetail
import com.quail.android.data.model.FinancingPlanCreateRequest
import com.quail.android.data.model.FinancingPlanResponse
import com.quail.android.data.model.HomePayload
import com.quail.android.data.model.AndroidPushDeviceBody
import com.quail.android.data.model.AndroidPushDeviceResponse
import com.quail.android.data.model.AndroidPushTestBody
import com.quail.android.data.model.AndroidPushTestResponse
import com.quail.android.data.model.HomelabMetrics
import com.quail.android.data.model.InterestRateUpsertRequest
import com.quail.android.data.model.InterestRateUpsertResponse
import com.quail.android.data.model.MonthlyReport
import com.quail.android.data.model.NotificationDetail
import com.quail.android.data.model.NotificationItem
import com.quail.android.data.model.NotificationSettingsResponse
import com.quail.android.data.model.PageBudgetResponse
import com.quail.android.data.model.RecurringGroup
import com.quail.android.data.model.RefreshCacheResponse
import com.quail.android.data.model.RoundUpSettings
import com.quail.android.data.model.RoundUpSettingsUpdateRequest
import com.quail.android.data.model.SavingsGoalUpdateRequest
import com.quail.android.data.model.SinkingFund
import com.quail.android.data.model.SinkingFundAdjustRequest
import com.quail.android.data.model.SinkingFundCreateRequest
import com.quail.android.data.model.SinkingFundUpdateRequest
import com.quail.android.data.model.SpentSoFarBreakdown
import com.quail.android.data.model.SpentSoFarTransaction
import com.quail.android.data.model.Transaction
import com.quail.android.data.model.TransactionDetail
import com.quail.android.data.model.TxCategoryUpdateRequest
import com.quail.android.data.model.TxIgnoreUpdateRequest
import com.quail.android.data.model.TxMetaUpdateRequest
import com.quail.android.data.model.UnassignedTransaction
import com.quail.android.data.model.UpcomingEvent
import com.quail.android.data.model.UpcomingRequest
import com.quail.android.data.model.VehicleFuelCreateRequest
import com.quail.android.data.model.VehicleFuelRecord
import com.quail.android.data.model.VehicleInspectionCreateRequest
import com.quail.android.data.model.VehicleInspectionItem
import com.quail.android.data.model.VehicleIssue
import com.quail.android.data.model.VehicleIssueCreateRequest
import com.quail.android.data.model.VehicleMaintenanceCreateRequest
import com.quail.android.data.model.VehicleMaintenanceRecord
import com.quail.android.data.model.VehicleMileageUpdateRequest
import com.quail.android.data.model.VehicleProfile
import com.quail.android.data.model.VehicleProfileUpdateRequest
import com.quail.android.data.model.VerifyBalanceRequest
import com.quail.android.data.model.VerifyBalanceResponse
import com.quail.android.data.network.QuailApi
import java.time.LocalDate

class HomeRepository(private val api: QuailApi) {
    suspend fun getHome(txLimit: Int = 15): HomePayload = api.getHome(txLimit)

    suspend fun getUpcoming(daysAhead: Int = 30): List<UpcomingEvent> =
        api.getUpcoming(UpcomingRequest(daysAhead = daysAhead)).events

    suspend fun getChartSeries(mode: ChartMode, start: LocalDate, end: LocalDate): List<ChartPoint> =
        api.getChartSeries(mode.path, start.toString(), end.toString())

    suspend fun getExtraSavedDetail(): ExtraSavedDetail = api.getExtraSavedDetail()

    suspend fun getTransactionDetail(id: String): TransactionDetail =
        api.getTransactionDetail(id).transaction

    suspend fun setTransactionCategory(id: String, category: String): TransactionDetail {
        api.setTransactionCategory(id, TxCategoryUpdateRequest(category))
        return api.getTransactionDetail(id).transaction
    }

    suspend fun updateTransactionMeta(id: String, status: String?, postedDate: String?): TransactionDetail {
        api.updateTransactionMeta(id, TxMetaUpdateRequest(status, postedDate))
        return api.getTransactionDetail(id).transaction
    }

    suspend fun invertTransactionAmount(id: String): TransactionDetail {
        api.invertTransactionAmount(id)
        return api.getTransactionDetail(id).transaction
    }

    suspend fun setTransactionIgnored(id: String, ignored: Boolean): TransactionDetail {
        api.setTransactionIgnored(id, TxIgnoreUpdateRequest(ignored))
        return api.getTransactionDetail(id).transaction
    }

    suspend fun deleteTransaction(id: String) {
        api.deleteTransaction(id)
    }

    suspend fun getSpentSoFarBreakdown(start: LocalDate, end: LocalDate): SpentSoFarBreakdown =
        api.getSpentSoFarBreakdown(start.toString(), end.toString())

    suspend fun getSpentSoFarTransactions(category: String, start: LocalDate, end: LocalDate): List<SpentSoFarTransaction> =
        api.getSpentSoFarTransactions(category, start.toString(), end.toString()).transactions

    suspend fun getUnassigned(limit: Int = 25, mode: String = "freq"): List<UnassignedTransaction> =
        api.getUnassigned(limit, mode)

    suspend fun createCategoryRule(category: String, keywords: List<String>, applyNow: Boolean = true): CategoryRuleCreateResponse =
        api.createCategoryRule(CategoryRuleCreateRequest(category, keywords, applyNow))

    suspend fun getCategoryRuleApplyJob(jobId: Int): CategoryRuleApplyJob = api.getCategoryRuleApplyJob(jobId).job

    suspend fun getCategories(): List<String> = api.getCategories()

    suspend fun createFinancingPlan(label: String, totalAmount: Double, totalMonths: Int, transactionId: String? = null): FinancingPlanResponse =
        api.createFinancingPlan(FinancingPlanCreateRequest(label, totalAmount, totalMonths, transactionId))

    suspend fun verifyBalance(accountId: Int, verifiedDate: String? = null): VerifyBalanceResponse =
        api.verifyBalance(accountId, VerifyBalanceRequest(verifiedDate))

    // ---- Notifications ----

    suspend fun getNotifications(limit: Int = 100): List<NotificationItem> = api.getNotifications(limit).items

    suspend fun getNotificationDetail(id: Int): NotificationDetail = api.getNotificationDetail(id)

    suspend fun markNotificationRead(id: Int) { api.markNotificationRead(id) }

    suspend fun dismissNotification(id: Int) { api.dismissNotification(id) }

    suspend fun markAllNotificationsRead() { api.markAllNotificationsRead() }

    suspend fun clearReadNotifications() { api.clearReadNotifications() }

    // ---- Settings ----

    suspend fun getNotificationSettings(): NotificationSettingsResponse = api.getNotificationSettings()

    suspend fun setNotificationSettings(prefs: Map<String, Boolean>): NotificationSettingsResponse =
        api.setNotificationSettings(prefs)

    suspend fun refreshHomeWidgetCache(): RefreshCacheResponse = api.refreshHomeWidgetCache()

    suspend fun getHomelabMetrics(): HomelabMetrics = api.getHomelabMetrics().homelab

    suspend fun registerAndroidPushDevice(token: String, deviceName: String? = null, appVersion: String? = null): AndroidPushDeviceResponse =
        api.registerAndroidPushDevice(AndroidPushDeviceBody(token = token, deviceName = deviceName, appVersion = appVersion))

    suspend fun deleteAndroidPushDevice(token: String): AndroidPushDeviceResponse =
        api.deleteAndroidPushDevice(AndroidPushDeviceBody(token = token))

    suspend fun sendAndroidPushTest(title: String? = null, body: String? = null): AndroidPushTestResponse =
        api.sendAndroidPushTest(AndroidPushTestBody(title = title, body = body))

    // ---- Recurring ----

    suspend fun getRecurring(minOcc: Int = 3, includeStale: Boolean = false): List<RecurringGroup> =
        api.getRecurring(minOcc, includeStale)

    suspend fun ignoreRecurringMerchant(name: String) { api.ignoreRecurringMerchant(name) }

    suspend fun unignoreRecurringMerchant(name: String) { api.unignoreRecurringMerchant(name) }

    suspend fun ignoreRecurringPattern(merchant: String, amount: Double, accountId: Int = -1) {
        api.ignoreRecurringPattern(merchant, amount, accountId)
    }

    suspend fun getRecurringCalendar(year: Int, month: Int, minOcc: Int = 3, includeStale: Boolean = false) =
        api.getRecurringCalendar(year, month, minOcc, includeStale).events

    // ---- All transactions ----

    suspend fun getTransactionsAll(
        limit: Int = 50,
        offset: Int = 0,
        merchant: String = "",
        account: String = "",
        category: String = "",
        start: String = "",
        end: String = "",
        amtMin: Double? = null,
        amtMax: Double? = null,
        amtAbs: Boolean = true,
    ): List<Transaction> = api.getTransactionsAll(
        limit, offset, merchant, account, category, start, end, amtMin, amtMax, if (amtAbs) 1 else 0,
    )

    suspend fun getBankInfo(): BankInfoOptions = api.getBankInfo()

    suspend fun setInterestRate(accountId: Int, ratePercent: Double, effectiveDate: String?, note: String?): InterestRateUpsertResponse =
        api.setInterestRate(InterestRateUpsertRequest(accountId, ratePercent, effectiveDate, note))

    // ---- Analytics ----

    suspend fun getMonthlyReport(month: String): MonthlyReport = api.getMonthlyReport(month)

    // ---- Budget ----

    suspend fun getPageBudget(year: Int, month: Int, recalc: Boolean = false): PageBudgetResponse =
        api.getPageBudget(year, month, if (recalc) 1 else 0)

    suspend fun getMonthBudget(year: Int, month: Int) = api.getMonthBudget(year, month)

    suspend fun upsertBudgetGroup(year: Int, month: Int, name: String, allocated: Double, cap: Double?, categories: List<String>): Int =
        api.upsertBudgetGroup(BudgetGroupUpsertRequest(year, month, name, allocated, cap, categories)).id

    suspend fun deleteBudgetGroup(year: Int, month: Int, name: String) { api.deleteBudgetGroup(year, month, name) }

    suspend fun createFund(name: String, targetAmount: Double, targetDate: String?, cadence: String, contribAmount: Double): Int =
        api.createFund(SinkingFundCreateRequest(name, targetAmount, targetDate, cadence, contribAmount)).id

    suspend fun updateFund(id: Int, name: String, targetAmount: Double, targetDate: String?, cadence: String, contribAmount: Double, isActive: Boolean = true) {
        api.updateFund(id, SinkingFundUpdateRequest(name, targetAmount, targetDate, cadence, contribAmount, isActive))
    }

    suspend fun adjustFund(id: Int, amount: Double, note: String): Double =
        api.adjustFund(id, SinkingFundAdjustRequest(amount, note)).reservedBalance

    suspend fun deleteFund(id: Int) { api.deleteFund(id) }

    suspend fun setSavingsGoal(mode: String, value: Double) { api.setSavingsGoal(SavingsGoalUpdateRequest(mode, value)) }

    suspend fun getRoundUps(): RoundUpSettings = api.getRoundUps()

    suspend fun setRoundUps(enabled: Boolean): RoundUpSettings = api.setRoundUps(RoundUpSettingsUpdateRequest(enabled))

    // ---- Vehicle (Quail Car) ----

    suspend fun getVehicleProfile(): VehicleProfile = api.getVehicleProfile()

    suspend fun putVehicleProfile(request: VehicleProfileUpdateRequest): VehicleProfile = api.putVehicleProfile(request)

    suspend fun updateVehicleMileage(mileage: Int) { api.updateVehicleMileage(VehicleMileageUpdateRequest(mileage)) }

    suspend fun getVehicleFuel(limit: Int = 200): List<VehicleFuelRecord> = api.getVehicleFuel(limit).records

    suspend fun addVehicleFuel(request: VehicleFuelCreateRequest): VehicleFuelRecord = api.addVehicleFuel(request)

    suspend fun deleteVehicleFuel(id: Int) { api.deleteVehicleFuel(id) }

    suspend fun getVehicleMaintenance(limit: Int = 200): List<VehicleMaintenanceRecord> = api.getVehicleMaintenance(limit).records

    suspend fun addVehicleMaintenance(request: VehicleMaintenanceCreateRequest): VehicleMaintenanceRecord = api.addVehicleMaintenance(request)

    suspend fun deleteVehicleMaintenance(id: Int) { api.deleteVehicleMaintenance(id) }

    suspend fun getVehicleIssues(): List<VehicleIssue> = api.getVehicleIssues()

    suspend fun addVehicleIssue(request: VehicleIssueCreateRequest): VehicleIssue = api.addVehicleIssue(request)

    suspend fun resolveVehicleIssue(id: Int): VehicleIssue = api.resolveVehicleIssue(id)

    suspend fun deleteVehicleIssue(id: Int) { api.deleteVehicleIssue(id) }

    suspend fun getVehicleInspections(): List<VehicleInspectionItem> = api.getVehicleInspections()

    suspend fun addVehicleInspection(request: VehicleInspectionCreateRequest): VehicleInspectionItem = api.addVehicleInspection(request)

    suspend fun checkVehicleInspection(id: Int): VehicleInspectionItem = api.checkVehicleInspection(id)
}
