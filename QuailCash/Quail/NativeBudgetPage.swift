import SwiftUI
import Charts
import Combine

struct NativeBudgetPageView: View {
    @EnvironmentObject private var navigator: AppNavigator
    @StateObject private var model = BudgetPageViewModel()
    @StateObject private var financingStore = FinancingStore.shared
    @State private var groupEditor: BudgetGroupDraft?
    @State private var fundEditor: FundDraft?
    @State private var fundAdjustment: FundAdjustmentDraft?

    var body: some View {
        AppChromeFrame(
            title: "Budget",
            badgeValue: nil,
            selectedTab: .spending,
            showsBottomBar: true,
            onLeadingTap: { navigator.show(.settings) },
            onTrailingTap: { navigator.show(.notifications) },
            onSelectTab: selectTab
        ) {
            AppPageScroll(refreshAction: {
                await withTaskGroup(of: Void.self) { group in
                    group.addTask { await model.load() }
                    group.addTask { await financingStore.refresh() }
                }
            }) {
                monthSummaryCard
                budgetGroupsCard
                sinkingFundsCard
                if !financingStore.plans.isEmpty {
                    financedTransactionsCard
                }
                spentCategoriesCard
                trendCard
                roundupsCard
            }
        }
        .task {
            model.startIfNeeded()
            await financingStore.refresh()
        }
        .sheet(item: $groupEditor) { draft in
            BudgetGroupEditorSheet(
                draft: draft,
                onCancel: { groupEditor = nil },
                onSave: { updated in
                    groupEditor = nil
                    Task { await model.saveGroup(updated) }
                }
            )
        }
        .sheet(item: $fundEditor) { draft in
            FundEditorSheet(
                draft: draft,
                onCancel: { fundEditor = nil },
                onSave: { updated in
                    fundEditor = nil
                    Task { await model.saveFund(updated) }
                }
            )
        }
        .sheet(item: $fundAdjustment) { draft in
            FundAdjustmentSheet(
                draft: draft,
                onCancel: { fundAdjustment = nil },
                onSave: { amount, note in
                    fundAdjustment = nil
                    Task { await model.adjustFund(draft.fund, amount: amount, note: note) }
                }
            )
        }
    }

    private func selectTab(_ tab: BottomTab) {
        switch tab {
        case .home:
            navigator.popToRoot()
        case .spending:
            navigator.show(.spending)
        case .all:
            navigator.show(.allTransactions)
        case .analytics:
            navigator.show(.analytics)
        case .recurring:
            navigator.show(.recurring)
        }
    }

    private var monthSummaryCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Button("Previous") { model.shiftMonth(-1) }
                    .buttonStyle(BudgetSmallButtonStyle())
                Spacer()
                Text(model.monthLabel)
                    .font(.system(size: 16, weight: .bold, design: .rounded))
                Spacer()
                Button("Next") { model.shiftMonth(1) }
                    .buttonStyle(BudgetSmallButtonStyle())
            }

            HStack {
                Text("This month")
                    .font(.system(size: 17, weight: .bold, design: .rounded))
                Spacer()
                Text("Viewing \(model.monthLabel)")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }

            if let month = model.payload?.month {
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                    budgetKPI("Income", budgetMoney(month.expectedIncome ?? 0))
                    budgetKPI("Remaining bills", budgetMoney(month.billsRemaining ?? 0))
                    budgetKPI("Spent so far", budgetMoney(month.spentSoFar ?? 0))
                    budgetKPI("Allocated (groups)", budgetMoney(month.allocationsTotal ?? 0))
                    budgetKPI("Safe to spend", budgetMoney(month.safeToSpend ?? 0), emphasize: true)
                    todayLeftKPI
                }
            } else if model.isLoading {
                ProgressView().frame(maxWidth: .infinity).padding(.vertical, 20)
            } else if let error = model.errorMessage {
                Text(error).font(.system(size: 13, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .budgetCard()
    }

    private var todayLeftKPI: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Left Today")
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)
                Spacer()
                Button("Recalc") {
                    Task { await model.recalcToday() }
                }
                .buttonStyle(BudgetSmallButtonStyle())
                .disabled(!model.isCurrentMonth)
            }
            Text(model.isCurrentMonth ? budgetMoney(model.dayLimit?.remainingToday ?? 0) : "—")
                .font(.system(size: 18, weight: .bold, design: .rounded))
            Text(model.isCurrentMonth ? model.todayMeta : "Left Today is available for the current month only.")
                .font(.system(size: 11, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(12)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Color.black.opacity(0.05), lineWidth: 1))
    }

    private func budgetKPI(_ title: String, _ value: String, emphasize: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: emphasize ? 20 : 18, weight: .bold, design: .rounded))
                .foregroundStyle(emphasize && (model.payload?.month?.safeToSpend ?? 0) < 0 ? .red : .primary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Color.black.opacity(0.05), lineWidth: 1))
    }

    private var budgetGroupsCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Budgets")
                    .font(.system(size: 17, weight: .bold, design: .rounded))
                Spacer()
                Button("Add group") {
                    groupEditor = BudgetGroupDraft.new(year: model.year, month: model.month)
                }
                .buttonStyle(BudgetSmallButtonStyle())
            }

            if model.payload?.groups.isEmpty ?? true {
                Text("No group budgets yet. Tap Add group to create one.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            } else {
                VStack(spacing: 8) {
                    ForEach(model.payload?.groups ?? []) { group in
                        BudgetGroupRow(
                            group: group,
                            onEdit: {
                                groupEditor = BudgetGroupDraft(group: group, year: model.year, month: model.month, savingsMode: model.payload?.savingsGoalConfig?.mode ?? "amount")
                            },
                            onDelete: {
                                Task { await model.deleteGroup(group) }
                            }
                        )
                    }
                }
            }
        }
        .padding(14)
        .budgetCard()
    }

    private var sinkingFundsCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Sinking Funds")
                    .font(.system(size: 17, weight: .bold, design: .rounded))
                Spacer()
                Button("Add fund") {
                    fundEditor = FundDraft.new
                }
                .buttonStyle(BudgetSmallButtonStyle())
            }

            Text("Set money aside for big future expenses so it’s not accidentally spendable.")
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)

            if model.payload?.funds.isEmpty ?? true {
                Text("No sinking funds yet. Tap Add fund to create one.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            } else {
                VStack(spacing: 10) {
                    ForEach(model.payload?.funds ?? []) { fund in
                        SinkingFundCard(
                            fund: fund,
                            onAddMoney: { fundAdjustment = .init(fund: fund, mode: .add) },
                            onUseMoney: { fundAdjustment = .init(fund: fund, mode: .use) },
                            onEdit: { fundEditor = FundDraft(fund: fund) },
                            onDelete: { Task { await model.deleteFund(fund) } }
                        )
                    }
                }
            }
        }
        .padding(14)
        .budgetCard()
    }

    private var financedTransactionsCard: some View {
        let palette = QuailTheme.palette(for: UserDefaults.standard.string(forKey: "quail.settings.theme") ?? "system")
        return VStack(alignment: .leading, spacing: 14) {
            HStack {
                Label("Financed", systemImage: "creditcard.fill")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                Spacer()
                let totalMonthly = financingStore.activePlans.reduce(0) { $0 + $1.monthlyPayment }
                if totalMonthly > 0 {
                    Text("\(formatBudgetMoney(totalMonthly))/mo")
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundStyle(.purple)
                }
            }

            ForEach(financingStore.plans) { plan in
                FinancingPlanRow(plan: plan, palette: palette) {
                    Task { await financingStore.deletePlan(plan) }
                }
            }
        }
        .padding(14)
        .budgetCard()
    }

    private var spentCategoriesCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Categories spent this month")
                .font(.system(size: 17, weight: .bold, design: .rounded))

            Text("This is read-only. Add a group above only for categories you want to allocate.")
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)

            if let categories = model.payload?.spentCategories, !categories.isEmpty {
                VStack(spacing: 12) {
                    BudgetSpentPieChart(items: categories)
                        .frame(height: 280)

                    VStack(spacing: 8) {
                        ForEach(Array(categories.enumerated()), id: \.element.id) { index, item in
                            Button {
                                navigator.show(.category(item.category))
                            } label: {
                                HStack(spacing: 10) {
                                    Text("\(index + 1)")
                                        .font(.system(size: 11, weight: .bold, design: .rounded))
                                        .foregroundStyle(.white)
                                        .frame(width: 20, height: 20)
                                        .background(BudgetSpentPieChart.palette[index % BudgetSpentPieChart.palette.count], in: Circle())
                                    Text(item.category)
                                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                                        .foregroundStyle(.primary)
                                    Spacer()
                                    Text(budgetMoney(item.spent))
                                        .font(.system(size: 14, weight: .bold, design: .rounded))
                                        .foregroundStyle(.primary)
                                }
                                .padding(.horizontal, 12)
                                .padding(.vertical, 12)
                                .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                                .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Color.black.opacity(0.05), lineWidth: 1))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            } else {
                Text("No spending found yet for this month.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .budgetCard()
    }

    private var trendCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Budget trend (last 6 months)")
                .font(.system(size: 17, weight: .bold, design: .rounded))
            Text("Positive means you stayed under allocated budgets. Negative means you overspent allocations.")
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)

            if model.trendRows.isEmpty {
                Text(model.isLoading ? "Loading..." : "No trend data yet.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            } else {
                VStack(spacing: 8) {
                    ForEach(model.trendRows) { row in
                        HStack {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(row.label)
                                    .font(.system(size: 13, weight: .bold, design: .rounded))
                                Text("Allocated \(budgetMoney(row.allocated)) • Spent \(budgetMoney(row.spent))")
                                    .font(.system(size: 11, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Text(row.deltaText)
                                .font(.system(size: 14, weight: .bold, design: .rounded))
                                .foregroundStyle(row.delta >= 0 ? .green : .red)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(Color.black.opacity(0.05), lineWidth: 1))
                    }
                }
            }
        }
        .padding(14)
        .budgetCard()
    }

    private var roundupsCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Round-up Transactions")
                .font(.system(size: 17, weight: .bold, design: .rounded))
            Text("Round each purchase up to the next dollar and count the extra cents as spending in category Round-ups.")
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
            Toggle(isOn: Binding(
                get: { model.roundUpsEnabled },
                set: { newValue in
                    model.roundUpsEnabled = newValue
                    Task { await model.saveRoundups(enabled: newValue) }
                }
            )) {
                Text("Enable round-up spending")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
            }
            .tint(.black)
            if let status = model.roundupsStatusText, !status.isEmpty {
                Text(status)
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .budgetCard(dashed: true)
    }
}

@MainActor
private final class BudgetPageViewModel: ObservableObject {
    @Published var year: Int
    @Published var month: Int
    @Published var payload: PageBudgetPayload?
    @Published var dayLimit: DayLimitPayload?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var trendRows: [BudgetTrendRow] = []
    @Published var roundUpsEnabled = false
    @Published var roundupsStatusText: String?

    private let api = QuailAPI.shared
    private var started = false

    init() {
        let now = Date()
        let cal = Calendar.current
        year = cal.component(.year, from: now)
        month = cal.component(.month, from: now)
    }

    var monthLabel: String {
        let fmt = DateFormatter()
        fmt.dateFormat = "MMMM yyyy"
        let date = Calendar.current.date(from: DateComponents(year: year, month: month, day: 1)) ?? Date()
        return fmt.string(from: date)
    }

    var isCurrentMonth: Bool {
        let now = Date()
        let cal = Calendar.current
        return cal.component(.year, from: now) == year && cal.component(.month, from: now) == month
    }

    var todayMeta: String {
        let spent = dayLimit?.spentTodayFree ?? 0
        let baseline = dayLimit?.baseline ?? 0
        return "Spent today \(budgetMoney(spent)) • Baseline \(budgetMoney(baseline)) / day"
    }

    func startIfNeeded() {
        guard !started else { return }
        started = true
        Task { await load() }
    }

    func shiftMonth(_ delta: Int) {
        let current = Calendar.current.date(from: DateComponents(year: year, month: month, day: 1)) ?? Date()
        let shifted = Calendar.current.date(byAdding: .month, value: delta, to: current) ?? current
        year = Calendar.current.component(.year, from: shifted)
        month = Calendar.current.component(.month, from: shifted)
        Task { await load() }
    }

    func recalcToday() async {
        do {
            dayLimit = try await api.fetchDayLimit(recalc: true)
            payload = try await api.fetchPageBudget(year: year, month: month, recalc: true)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func load() async {
        isLoading = true
        do {
            async let budget = api.fetchPageBudget(year: year, month: month)
            async let roundups = api.fetchRoundUpSettings()
            async let day = isCurrentMonth ? api.fetchDayLimit() : Optional<DayLimitPayload>.none
            let loadedBudget = try await budget
            payload = loadedBudget
            let loadedRoundups = try await roundups
            roundUpsEnabled = loadedRoundups.enabled
            dayLimit = try await day
            trendRows = try await loadTrendRows()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func saveRoundups(enabled: Bool) async {
        roundupsStatusText = "Saving..."
        do {
            _ = try await api.saveRoundUpSettings(enabled: enabled)
            roundupsStatusText = "Saved"
            await load()
        } catch {
            roundupsStatusText = "Save failed"
            errorMessage = error.localizedDescription
        }
    }

    func saveGroup(_ draft: BudgetGroupDraft) async {
        do {
            if draft.syntheticKind == "savings_goal" {
                _ = try await api.saveSavingsGoal(mode: draft.savingsMode, value: draft.allocated)
            } else {
                _ = try await api.upsertBudgetGroup(
                    year: draft.year,
                    month: draft.month,
                    name: draft.name,
                    allocated: draft.allocated,
                    cap: draft.capEnabled ? draft.cap : nil,
                    categories: draft.categories
                )
            }
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func deleteGroup(_ group: BudgetGroupPayload) async {
        guard !(group.readOnly ?? false) else { return }
        do {
            _ = try await api.deleteBudgetGroup(year: year, month: month, name: group.name)
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func saveFund(_ draft: FundDraft) async {
        do {
            if let id = draft.fundID {
                _ = try await api.updateFund(id: id, name: draft.name, targetAmount: draft.targetAmount, targetDate: draft.targetDateNilIfEmpty, cadence: draft.cadence, contribAmount: draft.contribAmount, isActive: true)
            } else {
                _ = try await api.createFund(name: draft.name, targetAmount: draft.targetAmount, targetDate: draft.targetDateNilIfEmpty, cadence: draft.cadence, contribAmount: draft.contribAmount)
            }
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func adjustFund(_ fund: SinkingFundPayload, amount: Double, note: String) async {
        do {
            _ = try await api.adjustFund(id: fund.id, amount: amount, note: note)
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func deleteFund(_ fund: SinkingFundPayload) async {
        do {
            _ = try await api.deleteFund(id: fund.id)
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func loadTrendRows() async throws -> [BudgetTrendRow] {
        var rows: [BudgetTrendRow] = []
        let baseDate = Calendar.current.date(from: DateComponents(year: year, month: month, day: 1)) ?? Date()
        for offset in stride(from: 5, through: 0, by: -1) {
            let date = Calendar.current.date(byAdding: .month, value: -offset, to: baseDate) ?? baseDate
            let y = Calendar.current.component(.year, from: date)
            let m = Calendar.current.component(.month, from: date)
            let mb = try await api.fetchMonthBudget(year: y, month: m)
            let allocated = mb.allocationsTotal ?? 0
            let spent = mb.budgetedSpentTotal ?? 0
            rows.append(BudgetTrendRow(
                id: "\(y)-\(m)",
                label: monthLabel(year: y, month: m),
                allocated: allocated,
                spent: spent,
                delta: allocated - spent
            ))
        }
        return rows
    }

    private func monthLabel(year: Int, month: Int) -> String {
        let fmt = DateFormatter()
        fmt.dateFormat = "MMMM yyyy"
        let date = Calendar.current.date(from: DateComponents(year: year, month: month, day: 1)) ?? Date()
        return fmt.string(from: date)
    }
}

private struct BudgetTrendRow: Identifiable {
    let id: String
    let label: String
    let allocated: Double
    let spent: Double
    let delta: Double

    var deltaText: String {
        let sign = delta >= 0 ? "+" : "-"
        return "\(sign)\(budgetMoney(abs(delta)))"
    }
}

private struct BudgetGroupDraft: Identifiable {
    let id = UUID()
    let originalName: String?
    let year: Int
    let month: Int
    var name: String
    var allocated: Double
    var capEnabled: Bool
    var cap: Double
    var categoriesText: String
    var readOnly: Bool
    var syntheticKind: String?
    var savingsMode: String

    var categories: [String] {
        categoriesText
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    static func new(year: Int, month: Int) -> BudgetGroupDraft {
        .init(originalName: nil, year: year, month: month, name: "", allocated: 0, capEnabled: false, cap: 0, categoriesText: "", readOnly: false, syntheticKind: nil, savingsMode: "amount")
    }

    init(
        originalName: String?,
        year: Int,
        month: Int,
        name: String,
        allocated: Double,
        capEnabled: Bool,
        cap: Double,
        categoriesText: String,
        readOnly: Bool,
        syntheticKind: String?,
        savingsMode: String
    ) {
        self.originalName = originalName
        self.year = year
        self.month = month
        self.name = name
        self.allocated = allocated
        self.capEnabled = capEnabled
        self.cap = cap
        self.categoriesText = categoriesText
        self.readOnly = readOnly
        self.syntheticKind = syntheticKind
        self.savingsMode = savingsMode
    }

    init(group: BudgetGroupPayload, year: Int, month: Int, savingsMode: String) {
        self.originalName = group.name
        self.year = year
        self.month = month
        self.name = group.name
        self.allocated = group.allocated ?? 0
        self.capEnabled = group.cap != nil
        self.cap = group.cap ?? 0
        self.categoriesText = group.categories.joined(separator: ", ")
        self.readOnly = group.readOnly ?? false
        self.syntheticKind = group.syntheticKind
        self.savingsMode = savingsMode
    }
}

private struct FundDraft: Identifiable {
    let id = UUID()
    let fundID: Int?
    var name: String
    var targetAmount: Double
    var targetDate: String
    var cadence: String
    var contribAmount: Double

    var targetDateNilIfEmpty: String? { targetDate.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : targetDate }

    static var new: FundDraft {
        .init(fundID: nil, name: "", targetAmount: 0, targetDate: "", cadence: "monthly", contribAmount: 0)
    }

    init(fundID: Int?, name: String, targetAmount: Double, targetDate: String, cadence: String, contribAmount: Double) {
        self.fundID = fundID
        self.name = name
        self.targetAmount = targetAmount
        self.targetDate = targetDate
        self.cadence = cadence
        self.contribAmount = contribAmount
    }

    init(fund: SinkingFundPayload) {
        fundID = fund.id
        name = fund.name
        targetAmount = fund.targetAmount ?? 0
        targetDate = fund.targetDate ?? ""
        cadence = fund.cadence ?? "monthly"
        contribAmount = fund.contribAmount ?? 0
    }
}

private struct FundAdjustmentDraft: Identifiable {
    enum Mode { case add, use }
    let id = UUID()
    let fund: SinkingFundPayload
    let mode: Mode
}

private struct BudgetGroupRow: View {
    let group: BudgetGroupPayload
    let onEdit: () -> Void
    let onDelete: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(group.name)
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                Spacer()
                if group.readOnly ?? false {
                    Text("Read only")
                        .font(.system(size: 11, weight: .semibold, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
            HStack {
                budgetMiniKV("Allocated", budgetMoney(group.allocated ?? 0))
                Spacer()
                budgetMiniKV("Cap", group.cap.map { budgetMoney($0) } ?? "—")
            }
            HStack {
                budgetMiniKV("Spent", budgetMoney(group.spent ?? 0))
                Spacer()
                budgetMiniKV("Remaining", budgetMoney(group.remaining ?? 0), tone: (group.remaining ?? 0) < 0 || (group.overCap ?? false) ? .red : .primary)
            }
            if !(group.categories.isEmpty) {
                Text(group.categories.joined(separator: ", "))
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 8) {
                Button(group.syntheticKind == "savings_goal" ? "Save goal" : "Edit") { onEdit() }
                    .buttonStyle(BudgetSmallButtonStyle(primary: true))
                if !(group.readOnly ?? false) {
                    Button("Delete") { onDelete() }
                        .buttonStyle(BudgetSmallButtonStyle())
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(12)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Color.black.opacity(0.05), lineWidth: 1))
    }
}

private struct SinkingFundCard: View {
    let fund: SinkingFundPayload
    let onAddMoney: () -> Void
    let onUseMoney: () -> Void
    let onEdit: () -> Void
    let onDelete: () -> Void

    var progress: Double {
        let target = fund.targetAmount ?? 0
        guard target > 0 else { return 0 }
        return max(0, min(1, (fund.reservedBalance ?? 0) / target))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(fund.name)
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                Spacer()
                Text(budgetMoney(fund.reservedBalance ?? 0))
                    .font(.system(size: 15, weight: .bold, design: .rounded))
            }
            Text((fund.targetAmount ?? 0) > 0 ? "\(budgetMoney(fund.reservedBalance ?? 0)) / \(budgetMoney(fund.targetAmount ?? 0))" : "\(budgetMoney(fund.reservedBalance ?? 0)) set aside")
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
            GeometryReader { proxy in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(Color.black.opacity(0.08))
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(Color.black)
                        .frame(width: proxy.size.width * progress)
                }
            }
            .frame(height: 10)
            if let needed = fund.neededPerDay, needed > 0, let date = fund.targetDate, !date.isEmpty {
                Text("\(budgetMoney(needed)) / day to hit by \(date)")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            } else if let date = fund.targetDate, !date.isEmpty {
                Text("Target date: \(date)")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                Button("Add money", action: onAddMoney).buttonStyle(BudgetSmallButtonStyle())
                Button("Use money", action: onUseMoney).buttonStyle(BudgetSmallButtonStyle())
                Button("Edit", action: onEdit).buttonStyle(BudgetSmallButtonStyle())
                Button("Delete", action: onDelete).buttonStyle(BudgetSmallButtonStyle())
            }
        }
        .padding(12)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Color.black.opacity(0.05), lineWidth: 1))
    }
}

private struct BudgetSpentPieChart: View {
    static let palette: [Color] = [
        Color(red: 0.91, green: 0.30, blue: 0.24),
        Color(red: 0.56, green: 0.27, blue: 0.68),
        Color(red: 0.95, green: 0.61, blue: 0.07),
        Color(red: 0.91, green: 0.12, blue: 0.39),
        Color(red: 0.18, green: 0.80, blue: 0.44),
        Color(red: 0.20, green: 0.60, blue: 0.86),
        Color(red: 0.10, green: 0.74, blue: 0.61),
        Color(red: 0.83, green: 0.33, blue: 0.00),
    ]

    let items: [BudgetSpentCategoryPayload]

    var body: some View {
        Chart(Array(items.enumerated()), id: \.element.id) { index, item in
            SectorMark(
                angle: .value("Spent", max(item.spent, 0)),
                innerRadius: .ratio(0.52),
                angularInset: 1
            )
            .foregroundStyle(Self.palette[index % Self.palette.count])
        }
        .chartLegend(.hidden)
        .frame(maxWidth: .infinity)
        .padding(8)
        .clipped()
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Color.black.opacity(0.05), lineWidth: 1))
    }
}

private struct BudgetGroupEditorSheet: View {
    @State var draft: BudgetGroupDraft
    let onCancel: () -> Void
    let onSave: (BudgetGroupDraft) -> Void

    var body: some View {
        NavigationStack {
            Form {
                Section("Group") {
                    TextField("Work travel", text: $draft.name)
                        .disabled(draft.readOnly)
                    TextField("Allocated", value: $draft.allocated, format: .number)
                        .keyboardType(.decimalPad)
                    Toggle("Cap", isOn: $draft.capEnabled)
                    if draft.capEnabled {
                        TextField("Cap", value: $draft.cap, format: .number)
                            .keyboardType(.decimalPad)
                            .disabled(draft.readOnly)
                    }
                    TextField("Categories (comma-separated)", text: $draft.categoriesText)
                        .disabled(draft.readOnly || draft.syntheticKind == "savings_goal")
                }
            }
            .navigationTitle(draft.originalName == nil ? "Add group" : "Edit group")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel", action: onCancel) }
                ToolbarItem(placement: .confirmationAction) { Button("Save") { onSave(draft) } }
            }
        }
        .presentationDetents([.medium])
    }
}

private struct FundEditorSheet: View {
    @State var draft: FundDraft
    let onCancel: () -> Void
    let onSave: (FundDraft) -> Void

    var body: some View {
        NavigationStack {
            Form {
                Section("Fund") {
                    TextField("Vacation", text: $draft.name)
                    TextField("Target amount", value: $draft.targetAmount, format: .number)
                        .keyboardType(.decimalPad)
                    TextField("Target date (YYYY-MM-DD)", text: $draft.targetDate)
                    Picker("Cadence", selection: $draft.cadence) {
                        Text("Monthly").tag("monthly")
                        Text("Weekly").tag("weekly")
                        Text("Per paycheck").tag("paycheck")
                        Text("Custom").tag("custom")
                    }
                    TextField("Planned contribution", value: $draft.contribAmount, format: .number)
                        .keyboardType(.decimalPad)
                }
            }
            .navigationTitle(draft.fundID == nil ? "Add fund" : "Edit fund")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel", action: onCancel) }
                ToolbarItem(placement: .confirmationAction) { Button("Save") { onSave(draft) } }
            }
        }
        .presentationDetents([.medium])
    }
}

private struct FundAdjustmentSheet: View {
    @State private var amount: Double = 0
    @State private var note: String = ""
    let draft: FundAdjustmentDraft
    let onCancel: () -> Void
    let onSave: (Double, String) -> Void

    var body: some View {
        NavigationStack {
            Form {
                Section(draft.mode == .add ? "Add money" : "Use money") {
                    Text(draft.fund.name)
                    TextField("Amount", value: $amount, format: .number)
                        .keyboardType(.decimalPad)
                    TextField("Note", text: $note)
                }
            }
            .navigationTitle(draft.mode == .add ? "Add money" : "Use money")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel", action: onCancel) }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        let signed = draft.mode == .add ? abs(amount) : -abs(amount)
                        onSave(signed, note)
                    }
                }
            }
        }
        .presentationDetents([.fraction(0.34)])
    }
}

private struct BudgetSmallButtonStyle: ButtonStyle {
    var primary = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .semibold, design: .rounded))
            .foregroundStyle(primary ? Color.white : Color.primary)
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(primary ? Color.black : Color.black.opacity(0.04), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(primary ? Color.black : Color.black.opacity(0.08), lineWidth: 1)
            )
            .opacity(configuration.isPressed ? 0.82 : 1)
    }
}

private extension View {
    func budgetCard(dashed: Bool = false) -> some View {
        self
            .frame(maxWidth: .infinity, alignment: .leading)
            .clipped()
            .background(Color.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 18, style: .continuous)
                    .stroke(style: StrokeStyle(lineWidth: 1, dash: dashed ? [6, 4] : []))
                    .foregroundStyle(Color.black.opacity(0.06))
            )
    }
}

private func budgetMoney(_ value: Double) -> String {
    let formatter = NumberFormatter()
    formatter.numberStyle = .currency
    formatter.currencyCode = "USD"
    formatter.maximumFractionDigits = 2
    formatter.minimumFractionDigits = 2
    return formatter.string(from: NSNumber(value: value)) ?? String(format: "$%.2f", value)
}

private func budgetMiniKV(_ label: String, _ value: String, tone: Color = .primary) -> some View {
    VStack(alignment: .leading, spacing: 2) {
        Text(label)
            .font(.system(size: 10, weight: .semibold, design: .rounded))
            .foregroundStyle(.secondary)
        Text(value)
            .font(.system(size: 13, weight: .bold, design: .rounded))
            .foregroundStyle(tone)
    }
}


// MARK: - Financing plan row

private struct FinancingPlanRow: View {
    let plan: FinancingPlan
    let palette: QuailThemePalette
    let onDelete: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(plan.label)
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                    Text(plan.isComplete ? "Paid off" : "\(plan.monthsRemaining) months left • \(formatBudgetMoney(plan.monthlyPayment))/mo")
                        .font(.system(size: 11, design: .rounded))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Text("\(formatBudgetMoney(plan.amountPaid)) / \(formatBudgetMoney(plan.totalAmount))")
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                    .foregroundStyle(plan.isComplete ? .green : .secondary)
            }

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4)
                        .fill(palette.border)
                        .frame(height: 6)
                    RoundedRectangle(cornerRadius: 4)
                        .fill(plan.isComplete ? Color.green : Color.purple)
                        .frame(width: geo.size.width * plan.progressFraction, height: 6)
                }
            }
            .frame(height: 6)

            Button("Delete", role: .destructive, action: onDelete)
                .buttonStyle(BudgetSmallButtonStyle())
        }
        .padding(10)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .contextMenu {
            Button(role: .destructive) { onDelete() } label: {
                Label("Remove plan", systemImage: "trash")
            }
        }
    }
}

private func formatBudgetMoney(_ v: Double) -> String {
    let f = NumberFormatter()
    f.numberStyle = .currency
    f.currencyCode = "USD"
    f.maximumFractionDigits = 0
    return f.string(from: NSNumber(value: v)) ?? "$\(Int(v))"
}
