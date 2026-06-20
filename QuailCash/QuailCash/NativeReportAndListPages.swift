import SwiftUI
import Combine

private func nativeCategorySymbolName(_ category: String?) -> String {
    let key = String(category ?? "")
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
        .replacingOccurrences(of: "[^a-z0-9]+", with: "-", options: .regularExpression)
        .trimmingCharacters(in: CharacterSet(charactersIn: "-"))

    switch key {
    case "food", "restaurants", "dining": return "fork.knife"
    case "shopping": return "bag"
    case "transportation", "transit": return "car.fill"
    case "travel": return "airplane"
    case "parking": return "parkingsign"
    case "games": return "gamecontroller.fill"
    case "snack": return "cup.and.saucer.fill"
    case "cash-withdrawal", "cash": return "banknote"
    case "bills", "utilities": return "doc.text"
    case "transfer", "card-payment": return "arrow.left.arrow.right"
    default: return "questionmark"
    }
}

private struct NativeIconBadge: View {
    let category: String?

    var body: some View {
        ZStack {
            Circle()
                .fill(Color.white)
                .overlay(Circle().stroke(.black.opacity(0.08), lineWidth: 1))
            Image(systemName: nativeCategorySymbolName(category))
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(.secondary)
        }
        .frame(width: 36, height: 36)
    }
}

private struct NativeCard<Content: View>: View {
    let title: String
    let centered: Bool
    @ViewBuilder let content: Content

    init(title: String, centered: Bool = false, @ViewBuilder content: () -> Content) {
        self.title = title
        self.centered = centered
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                if centered {
                    Spacer(minLength: 0)
                    Text(title)
                        .font(.system(size: 16, weight: .semibold, design: .rounded))
                        .frame(maxWidth: .infinity, alignment: .center)
                    Spacer(minLength: 0)
                } else {
                    Text(title)
                        .font(.system(size: 16, weight: .semibold, design: .rounded))
                    Spacer(minLength: 0)
                }
            }
            content
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
    }
}

private struct NativeSectionHeader: View {
    let title: String
    let isExpanded: Bool

    var body: some View {
        HStack {
            Spacer(minLength: 0)
            Text(title)
                .font(.system(size: 16, weight: .semibold, design: .rounded))
                .frame(maxWidth: .infinity)
            Spacer(minLength: 0)
            Image(systemName: "chevron.down")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.secondary)
                .rotationEffect(.degrees(isExpanded ? 180 : 0))
        }
    }
}

private func nativeShortDate(_ iso: String?) -> String {
    guard let iso, !iso.isEmpty else { return "—" }
    let input = DateFormatter()
    input.locale = Locale(identifier: "en_US_POSIX")
    input.timeZone = TimeZone(secondsFromGMT: 0)
    input.dateFormat = "yyyy-MM-dd"
    guard let date = input.date(from: iso) else { return iso }
    let output = DateFormatter()
    output.locale = Locale(identifier: "en_US_POSIX")
    output.timeZone = .current
    output.dateFormat = "MM/dd"
    return output.string(from: date)
}

private struct NativePrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(.white)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Color.black.opacity(configuration.isPressed ? 0.78 : 1.0))
            )
    }
}

private struct NativeSecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(.primary)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Color.black.opacity(configuration.isPressed ? 0.06 : 0.04))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(.black.opacity(0.08), lineWidth: 1)
            )
    }
}

private struct NativeChipButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 11, weight: .semibold, design: .rounded))
            .foregroundStyle(.primary)
            .padding(.horizontal, 9)
            .padding(.vertical, 6)
            .background(
                Capsule(style: .continuous)
                    .fill(Color.black.opacity(configuration.isPressed ? 0.06 : 0.04))
            )
            .overlay(
                Capsule(style: .continuous)
                    .stroke(.black.opacity(0.08), lineWidth: 1)
            )
    }
}

private struct NativePopupChrome<Content: View>: View {
    let title: String
    let subtitle: String
    let onClose: () -> Void
    let content: Content

    init(title: String, subtitle: String, onClose: @escaping () -> Void, @ViewBuilder content: () -> Content) {
        self.title = title
        self.subtitle = subtitle
        self.onClose = onClose
        self.content = content()
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(.system(size: 18, weight: .bold, design: .rounded))
                        .textCase(.uppercase)
                    Text(subtitle)
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                Spacer(minLength: 10)

                Button(action: onClose) {
                    Image(systemName: "xmark")
                        .font(.system(size: 12, weight: .bold))
                        .frame(width: 30, height: 30)
                        .background(Color.black.opacity(0.05), in: Circle())
                        .overlay(Circle().stroke(.black.opacity(0.06), lineWidth: 1))
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            .padding(.top, 16)
            .padding(.bottom, 12)

            content
        }
        .frame(maxWidth: 520)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).stroke(.black.opacity(0.08), lineWidth: 1))
        .shadow(color: .black.opacity(0.18), radius: 18, x: 0, y: 10)
    }
}

private func nativeSignedMoneyColor(_ value: Double) -> Color {
    if value < 0 { return .red }
    if value > 0 { return .green }
    return .primary
}

private func nativeMenuLabel(_ text: String) -> some View {
    HStack(spacing: 6) {
        Text(text)
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .foregroundStyle(.primary)
            .lineLimit(1)
            .truncationMode(.tail)
        Spacer(minLength: 8)
        Image(systemName: "chevron.down")
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(.secondary)
    }
    .padding(.horizontal, 12)
    .frame(height: 34)
    .frame(maxWidth: .infinity)
    .background(Color.white, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
}

private func nativeTransactionAmountColor(_ value: Double) -> Color {
    if value >= 0 { return .red }
    if value < 0 { return .green }
    return .primary
}

// MARK: - Analytics

private struct NativeAnalyticsReport: Decodable {
    let ok: Bool?
    let month: String?
    let summary: NativeAnalyticsSummary?
    let categoryBreakdown: [NativeAnalyticsCategory]
    let accountSummary: [NativeAnalyticsAccount]
    let biggestTransactions: NativeAnalyticsBiggestTransactions?
    let recurringSubscriptions: [NativeAnalyticsRecurringSubscription]
    let budgetPerformance: NativeAnalyticsBudgetPerformance?
    let changesVsPreviousMonth: NativeAnalyticsChanges?

    enum CodingKeys: String, CodingKey {
        case ok, month, summary, categoryBreakdown = "category_breakdown", accountSummary = "account_summary", biggestTransactions = "biggest_transactions", recurringSubscriptions = "recurring_subscriptions", budgetPerformance = "budget_performance", changesVsPreviousMonth = "changes_vs_previous_month"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        ok = try container.decodeIfPresent(Bool.self, forKey: .ok)
        month = try container.decodeIfPresent(String.self, forKey: .month)
        summary = try container.decodeIfPresent(NativeAnalyticsSummary.self, forKey: .summary)
        categoryBreakdown = try container.decodeIfPresent([NativeAnalyticsCategory].self, forKey: .categoryBreakdown) ?? []
        accountSummary = try container.decodeIfPresent([NativeAnalyticsAccount].self, forKey: .accountSummary) ?? []
        biggestTransactions = try container.decodeIfPresent(NativeAnalyticsBiggestTransactions.self, forKey: .biggestTransactions)
        recurringSubscriptions = try container.decodeIfPresent([NativeAnalyticsRecurringSubscription].self, forKey: .recurringSubscriptions) ?? []
        budgetPerformance = try container.decodeIfPresent(NativeAnalyticsBudgetPerformance.self, forKey: .budgetPerformance)
        changesVsPreviousMonth = try container.decodeIfPresent(NativeAnalyticsChanges.self, forKey: .changesVsPreviousMonth)
    }
}

private struct NativeAnalyticsSummary: Decodable {
    let income: Double?
    let spending: Double?
    let net: Double?
    let startingBalance: Double?
    let endingBalance: Double?

    enum CodingKeys: String, CodingKey {
        case income, spending, net
        case startingBalance = "starting_balance"
        case endingBalance = "ending_balance"
    }
}

private struct NativeAnalyticsCategory: Decodable, Hashable {
    let category: String?
    let amount: Double?
}

private struct NativeAnalyticsAccount: Decodable, Hashable {
    let bank: String?
    let name: String?
    let accountType: String?
    let startBalance: Double?
    let endBalance: Double?
    let change: Double?

    enum CodingKeys: String, CodingKey {
        case bank, name
        case accountType = "account_type"
        case startBalance = "start_balance"
        case endBalance = "end_balance"
        case change
    }
}

private struct NativeAnalyticsBiggestTransactions: Decodable {
    let outflows: [NativeAnalyticsTransaction]
    let inflows: [NativeAnalyticsTransaction]

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        outflows = try container.decodeIfPresent([NativeAnalyticsTransaction].self, forKey: .outflows) ?? []
        inflows = try container.decodeIfPresent([NativeAnalyticsTransaction].self, forKey: .inflows) ?? []
    }

    enum CodingKeys: String, CodingKey {
        case outflows
        case inflows
    }
}

private struct NativeAnalyticsTransaction: Decodable, Hashable, Identifiable {
    var id = UUID()
    let date: String?
    let merchant: String?
    let category: String?
    let amount: Double?
    let account: String?
}

private struct NativeAnalyticsRecurringSubscription: Decodable, Hashable {
    let merchant: String?
    let category: String?
    let hits: Int?
    let total: Double?
}

private struct NativeAnalyticsBudgetPerformance: Decodable {
    let plannedAllocations: Double?
    let actualSpentOnAllocated: Double?
    let remainingAllocated: Double?
    let freeSpendSoFar: Double?

    enum CodingKeys: String, CodingKey {
        case plannedAllocations = "planned_allocations"
        case actualSpentOnAllocated = "actual_spent_on_allocated"
        case remainingAllocated = "remaining_allocated"
        case freeSpendSoFar = "free_spend_so_far"
    }
}

private struct NativeAnalyticsChanges: Decodable {
    let incomePrevMonth: Double?
    let spendingPrevMonth: Double?
    let incomeChangePct: Double?
    let spendingChangePct: Double?
    let incomeChangeAbs: Double?
    let spendingChangeAbs: Double?

    enum CodingKeys: String, CodingKey {
        case incomePrevMonth = "income_prev_month"
        case spendingPrevMonth = "spending_prev_month"
        case incomeChangePct = "income_change_pct"
        case spendingChangePct = "spending_change_pct"
        case incomeChangeAbs = "income_change_abs"
        case spendingChangeAbs = "spending_change_abs"
    }
}

@MainActor
private final class NativeAnalyticsViewModel: ObservableObject {
    @Published var month: Date = Date()
    @Published var report: NativeAnalyticsReport?
    @Published var isLoading = false
    @Published var statusText = "Ready."
    @Published var errorMessage: String?

    func load() async {
        isLoading = true
        defer { isLoading = false }
        errorMessage = nil
        statusText = "Loading report..."
        do {
            let data = try await QuailCashAPI.shared.fetchData(
                path: "/reports/monthly",
                queryItems: [URLQueryItem(name: "month", value: monthKey)]
            )
            report = try JSONDecoder.quailCash.decode(NativeAnalyticsReport.self, from: data)
            statusText = "Loaded \(report?.month ?? monthKey)."
        } catch is CancellationError {
            return
        } catch {
            errorMessage = error.localizedDescription
            statusText = "Failed to load report."
        }
    }

    var monthKey: String {
        let cal = Calendar.current
        return String(format: "%04d-%02d", cal.component(.year, from: month), cal.component(.month, from: month))
    }

    func reload() { Task { await load() } }

    func exportPDF() {
        // Native placeholder for the web page's "Download PDF" action.
        statusText = "PDF export is not implemented yet."
    }
}

struct NativeAnalyticsPageView: View {
    @StateObject private var model = NativeAnalyticsViewModel()

    var body: some View {
        PageShell(title: "Analytics", subtitle: "Monthly report and category analysis") {
            VStack(alignment: .leading, spacing: 12) {
                analyticsHero
                analyticsToolbar
                Text(model.statusText)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                if let error = model.errorMessage {
                    NativeCard(title: "Error", centered: true) {
                        Text(error).font(.system(size: 13, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                    }
                } else if model.isLoading {
                    NativeCard(title: "Loading", centered: true) {
                        ProgressView().frame(maxWidth: .infinity, alignment: .center)
                    }
                } else if let report = model.report {
                    analyticsCard(title: "Month Summary") {
                        analyticsSummaryGrid(report.summary)
                    }
                    analyticsCard(title: "Category Breakdown") {
                        analyticsCategoryBreakdown(report.categoryBreakdown)
                    }
                    analyticsCard(title: "Savings Accounts") {
                        analyticsAccounts(report.accountSummary.filter { ($0.accountType ?? "").lowercased() == "savings" })
                    }
                    analyticsCard(title: "Liquid Accounts") {
                        analyticsAccounts(report.accountSummary.filter { ["checking", "debit", "cash"].contains(($0.accountType ?? "").lowercased()) })
                    }
                    analyticsCard(title: "Debt Accounts") {
                        analyticsAccounts(report.accountSummary.filter { ($0.accountType ?? "").lowercased() == "credit" })
                    }
                    analyticsCard(title: "Biggest Transactions") {
                        analyticsTransactions(report.biggestTransactions)
                    }
                    analyticsCard(title: "Recurring & Subscriptions") {
                        analyticsRecurring(report.recurringSubscriptions)
                    }
                    analyticsCard(title: "Budget Performance") {
                        analyticsBudget(report.budgetPerformance)
                    }
                    analyticsCard(title: "Changes vs Previous Month") {
                        analyticsChanges(report.changesVsPreviousMonth)
                    }
                }
            }
        }
        .task { await model.load() }
    }

    private var analyticsHero: some View {
        NativeCard(title: model.report?.month ?? "Monthly Report", centered: true) {
            VStack(alignment: .center, spacing: 8) {
                Text("Net \(nativeMoneyValue(model.report?.summary?.net ?? 0))")
                    .font(.system(size: 22, weight: .bold, design: .rounded))
                HStack(spacing: 8) {
                    heroChip("Income", nativeMoneyValue(model.report?.summary?.income ?? 0))
                    heroChip("Spending", nativeMoneyValue(model.report?.summary?.spending ?? 0))
                }
                HStack(spacing: 8) {
                    heroChip("Change", analyticsChangeText(model.report?.changesVsPreviousMonth?.incomeChangePct, positiveWhenUp: true))
                    heroChip("Spend", analyticsChangeText(model.report?.changesVsPreviousMonth?.spendingChangePct, positiveWhenUp: false))
                }
            }
        }
    }

    private var analyticsToolbar: some View {
        HStack(spacing: 8) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Month").font(.system(size: 10, weight: .semibold, design: .rounded)).foregroundStyle(.secondary)
                DatePicker("", selection: $model.month, displayedComponents: .date)
                    .labelsHidden()
                    .datePickerStyle(.compact)
                    .controlSize(.small)
            }
            Spacer(minLength: 0)
            Button("Load Report") { model.reload() }
                .buttonStyle(NativePrimaryButtonStyle())
            Button("Download PDF") { model.exportPDF() }
                .buttonStyle(NativeSecondaryButtonStyle())
        }
    }

    private func heroChip(_ title: String, _ value: String) -> some View {
        VStack(spacing: 2) {
            Text(title).font(.system(size: 10, weight: .semibold, design: .rounded)).foregroundStyle(.secondary)
            Text(value).font(.system(size: 12, weight: .bold, design: .rounded))
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    private func analyticsCard<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        NativeCard(title: title, centered: true) { content() }
    }

    private func analyticsSummaryGrid(_ summary: NativeAnalyticsSummary?) -> some View {
        VStack(spacing: 8) {
            summaryRow("Income", nativeMoneyValue(summary?.income ?? 0))
            summaryRow("Spending", nativeMoneyValue(summary?.spending ?? 0))
            summaryRow("Net", nativeMoneyValue(summary?.net ?? 0))
            summaryRow("Starting Balance", nativeMoneyValue(summary?.startingBalance ?? 0))
            summaryRow("Ending Balance", nativeMoneyValue(summary?.endingBalance ?? 0))
        }
    }

    private func summaryRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).font(.system(size: 13, weight: .semibold, design: .rounded))
            Spacer()
            Text(value).font(.system(size: 13, weight: .bold, design: .rounded))
        }
    }

    private func analyticsCategoryBreakdown(_ rows: [NativeAnalyticsCategory]) -> some View {
        VStack(spacing: 8) {
            ForEach(rows, id: \.self) { row in
                HStack {
                    Text(row.category ?? "Uncategorized")
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                    Spacer()
                    Text(nativeMoneyValue(row.amount ?? 0))
                        .font(.system(size: 13, weight: .bold, design: .rounded))
                }
            }
        }
    }

    private func analyticsAccounts(_ rows: [NativeAnalyticsAccount]) -> some View {
        VStack(spacing: 8) {
            ForEach(rows, id: \.self) { row in
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\((row.bank ?? "")) \((row.name ?? ""))".trimmingCharacters(in: .whitespaces))
                            .font(.system(size: 13, weight: .semibold, design: .rounded))
                        Text(row.accountType ?? "").font(.system(size: 11, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("Start \(nativeMoneyValue(row.startBalance ?? 0))")
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                        Text("End \(nativeMoneyValue(row.endBalance ?? 0))")
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                        Text("Change \(nativeMoneyValue(row.change ?? 0))")
                            .font(.system(size: 13, weight: .bold, design: .rounded))
                    }
                }
                .padding(12)
                .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
        }
    }

    private func analyticsTransactions(_ payload: NativeAnalyticsBiggestTransactions?) -> some View {
        VStack(spacing: 8) {
            ForEach((payload?.outflows ?? []) + (payload?.inflows ?? [])) { tx in
                HStack(alignment: .top, spacing: 10) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text((tx.merchant ?? "(No merchant)").uppercased())
                            .font(.system(size: 13, weight: .semibold, design: .rounded))
                        Text([tx.date, tx.category, tx.account].compactMap { $0 }.joined(separator: " • "))
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(nativeMoneyValue(tx.amount ?? 0))
                        .font(.system(size: 13, weight: .bold, design: .rounded))
                }
                .padding(12)
                .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
        }
    }

    private func analyticsRecurring(_ rows: [NativeAnalyticsRecurringSubscription]) -> some View {
        VStack(spacing: 8) {
            ForEach(rows, id: \.self) { row in
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text((row.merchant ?? "").uppercased())
                            .font(.system(size: 13, weight: .semibold, design: .rounded))
                        Text(row.category ?? "").font(.system(size: 11, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("\(row.hits ?? 0) hits").font(.system(size: 11, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                        Text(nativeMoneyValue(row.total ?? 0)).font(.system(size: 13, weight: .bold, design: .rounded))
                    }
                }
                .padding(12)
                .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
        }
    }

    private func analyticsBudget(_ p: NativeAnalyticsBudgetPerformance?) -> some View {
        VStack(spacing: 8) {
            summaryRow("Planned", nativeMoneyValue(p?.plannedAllocations ?? 0))
            summaryRow("Actual", nativeMoneyValue(p?.actualSpentOnAllocated ?? 0))
            summaryRow("Remaining", nativeMoneyValue(p?.remainingAllocated ?? 0))
            summaryRow("Free Spend", nativeMoneyValue(p?.freeSpendSoFar ?? 0))
        }
    }

    private func analyticsChanges(_ p: NativeAnalyticsChanges?) -> some View {
        VStack(spacing: 8) {
            summaryRow("Income Prev Month", nativeMoneyValue(p?.incomePrevMonth ?? 0))
            summaryRow("Income Change", nativeMoneyValue(p?.incomeChangeAbs ?? 0))
            summaryRow("Income %", analyticsChangeText(p?.incomeChangePct, positiveWhenUp: true))
            summaryRow("Spending Prev Month", nativeMoneyValue(p?.spendingPrevMonth ?? 0))
            summaryRow("Spending Change", nativeMoneyValue(p?.spendingChangeAbs ?? 0))
            summaryRow("Spending %", analyticsChangeText(p?.spendingChangePct, positiveWhenUp: false))
        }
    }

    private func analyticsChangeText(_ value: Double?, positiveWhenUp: Bool) -> String {
        guard let value else { return "—" }
        let cleaned = String(format: "%.1f%%", abs(value))
        let positive = positiveWhenUp ? value >= 0 : value <= 0
        return positive ? cleaned : cleaned
    }
}

// MARK: - Transactions

@MainActor
private final class NativeAllTransactionsViewModel: ObservableObject {
    @Published var transactions: [TransactionItem] = []
    @Published var isLoading = false
    @Published var done = false
    @Published var statusText = ""
    @Published var errorText: String?

    @Published var merchant = ""
    @Published var account = ""
    @Published var category = ""
    @Published var start = ""
    @Published var end = ""
    @Published var amountMode = "any"
    @Published var amountA = ""
    @Published var amountB = ""
    @Published var amountAbs = true
    @Published var addPanelOpen = false
    @Published var addTxAccount = ""
    @Published var addTxDate = nativeIsoToday()
    @Published var addTxStatus = "posted"
    @Published var addTxAmount = ""
    @Published var addTxMerchant = ""
    @Published var addTxMessage = ""
    @Published var addTxSaving = false
    @Published var filterOptionsLoaded = false
    @Published var accountOptions: [String] = []
    @Published var categoryOptions: [String] = []
    @Published var addAccountOptions: [(group: String, items: [(id: Int, label: String)])] = []
    @Published var offset = 0

    private var lastRequestKey = ""

    var query: [URLQueryItem] {
        var items: [URLQueryItem] = [
            URLQueryItem(name: "limit", value: "50"),
            URLQueryItem(name: "offset", value: String(offset)),
        ]
        if !merchant.isEmpty { items.append(URLQueryItem(name: "merchant", value: merchant)) }
        if !account.isEmpty { items.append(URLQueryItem(name: "card", value: account)) }
        if !category.isEmpty { items.append(URLQueryItem(name: "category", value: category)) }
        if !start.isEmpty { items.append(URLQueryItem(name: "start", value: start)) }
        if !end.isEmpty { items.append(URLQueryItem(name: "end", value: end)) }
        if amountMode != "any" { items.append(URLQueryItem(name: "amt_mode", value: amountMode)) }
        if let a = Double(amountA), amountMode == "exact" || amountMode == "min" || amountMode == "max" || amountMode == "between" {
            items.append(URLQueryItem(name: "amt_min", value: String(a)))
            if amountMode == "exact" { items.append(URLQueryItem(name: "amt_max", value: String(a))) }
        }
        if let b = Double(amountB), amountMode == "between" { items.append(URLQueryItem(name: "amt_max", value: String(b))) }
        if amountAbs { items.append(URLQueryItem(name: "amt_abs", value: "1")) }
        return items
    }

    func currentKey() -> String {
        query.filter { $0.name != "offset" }.map { "\($0.name)=\($0.value ?? "")" }.joined(separator: "&")
    }

    func resetAndReload() {
        offset = 0
        done = false
        transactions = []
        Task { await loadPage(force: true, replace: true) }
    }

    func loadNext() {
        Task { await loadPage(force: false, replace: false) }
    }

    func loadPage(force: Bool, replace: Bool) async {
        guard !isLoading else { return }
        if done && !force { return }
        let key = currentKey()
        if !force, !lastRequestKey.isEmpty, lastRequestKey != key { return }
        lastRequestKey = key
        isLoading = true
        errorText = nil
        statusText = offset == 0 ? "Loading..." : "Loading more..."
        do {
            let data = try await QuailCashAPI.shared.fetchData(path: "/transactions-all", queryItems: query)
            let rows = try JSONDecoder.quailCash.decode([TransactionItem].self, from: data)
            if replace { transactions = rows } else { transactions += rows }
            offset += rows.count
            done = rows.count < 50
            statusText = done ? "End of list." : ""
        } catch {
            errorText = error.localizedDescription
            statusText = "Failed to load transactions."
        }
        isLoading = false
    }

    func loadFilterOptions() async {
        guard !filterOptionsLoaded else { return }
        do {
            async let bankData = QuailCashAPI.shared.fetchData(path: "/bank-info")
            async let categoriesData = QuailCashAPI.shared.fetchData(path: "/categories")
            let bankJSON = try JSONDecoder.quailCash.decode(NativeBankInfoOptions.self, from: try await bankData)
            let categories = try JSONDecoder.quailCash.decode([String].self, from: try await categoriesData)
            accountOptions = (bankJSON.accounts.map { $0.name } + bankJSON.creditCards.map { $0.name }).filter { !$0.isEmpty }
            categoryOptions = categories.filter { !$0.isEmpty }
            addAccountOptions = [
                ("Accounts", bankJSON.accounts.map { (Int($0.id), "\($0.bank) - \($0.name)") }),
                ("Cards", bankJSON.creditCards.map { (Int($0.id), "\($0.bank) - \($0.name)") }),
            ].filter { !$0.items.isEmpty }
            filterOptionsLoaded = true
        } catch {
            accountOptions = []
            categoryOptions = []
            addAccountOptions = []
        }
    }

    func saveTransaction() async {
        guard let accountID = Int(addTxAccount), accountID > 0 else {
            addTxMessage = "Pick an account."
            return
        }
        guard let amount = Double(addTxAmount) else {
            addTxMessage = "Enter a valid amount."
            return
        }
        let merchant = addTxMerchant.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !addTxDate.isEmpty else {
            addTxMessage = "Pick a date."
            return
        }
        addTxSaving = true
        addTxMessage = "Saving..."
        do {
            try await QuailCashAPI.shared.sendJSON(path: "/transaction", method: "POST", jsonBody: [
                "account_id": accountID,
                "amount": amount,
                "merchant": merchant,
                "status": addTxStatus,
                "date": addTxDate,
                "source": "Manual",
            ])
            addTxAmount = ""
            addTxMerchant = ""
            addPanelOpen = false
            resetAndReload()
        } catch {
            addTxMessage = error.localizedDescription
        }
        addTxSaving = false
    }

    func clearFilters() {
        merchant = ""
        account = ""
        category = ""
        start = ""
        end = ""
        amountMode = "any"
        amountA = ""
        amountB = ""
        amountAbs = true
        resetAndReload()
    }
}

private struct NativeBankInfoOptions: Decodable {
    let accounts: [NativeBankInfoAccount]
    let creditCards: [NativeBankInfoCard]

    enum CodingKeys: String, CodingKey {
        case accounts
        case creditCards = "credit_cards"
    }
}

private struct NativeBankInfoAccount: Decodable {
    let id: Int
    let bank: String
    let name: String

    enum CodingKeys: String, CodingKey {
        case id = "account_id"
        case bank
        case name
    }
}

private struct NativeBankInfoCard: Decodable {
    let id: Int
    let bank: String
    let name: String

    enum CodingKeys: String, CodingKey {
        case id = "card_id"
        case bank
        case name
    }
}

struct NativeAllTransactionsPageView: View {
    @StateObject private var model = NativeAllTransactionsViewModel()
    @State private var selectedTransaction: TransactionItem?

    var body: some View {
        ZStack {
            PageShell(title: "All", subtitle: "") {
                VStack(alignment: .leading, spacing: 12) {
                    filterCard
                    if model.addPanelOpen { addTransactionCard }
                    transactionList
                    loadMoreButton
                    if !model.statusText.isEmpty {
                        Text(model.statusText)
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }
            }
            if let tx = selectedTransaction {
                SharedTransactionInspectPopupView(
                    transaction: tx,
                    onDismiss: {
                        selectedTransaction = nil
                    },
                    onRefresh: {
                        Task { await model.loadPage(force: true, replace: true) }
                    }
                )
                    .padding(.horizontal, 12)
                    .padding(.vertical, 18)
            }
        }
        .task {
            await model.loadFilterOptions()
            model.resetAndReload()
        }
    }

    private var filterCard: some View {
        NativeCard(title: "Filters", centered: true) {
            VStack(alignment: .leading, spacing: 10) {
                nativeTextField("Merchant", text: $model.merchant)
                gridRow {
                    nativePicker("Account", selection: $model.account, options: model.accountOptions, emptyLabel: "Any account")
                    nativePicker("Category", selection: $model.category, options: model.categoryOptions, emptyLabel: "Any category")
                }
                gridRow {
                    nativeDateField("From", text: $model.start)
                    nativeDateField("To", text: $model.end)
                }
                gridRow {
                    nativePickerPairs(
                        "Amount",
                        selection: $model.amountMode,
                        options: [
                            ("Any", "any"),
                            ("Exact", "exact"),
                            ("Min", "min"),
                            ("Max", "max"),
                            ("Between", "between")
                        ],
                        emptyLabel: "Any"
                    )
                    nativeTextField("Value", text: $model.amountA)
                    nativeTextField("And", text: $model.amountB)
                }
                HStack(spacing: 10) {
                    Text("ABS (treat -50 and +50 the same)")
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                    Spacer(minLength: 0)
                    Toggle("", isOn: $model.amountAbs)
                        .labelsHidden()
                }
                HStack {
                    Button("Add Transaction") {
                        model.addPanelOpen.toggle()
                    }
                    .buttonStyle(NativeSecondaryButtonStyle())
                    Button("Clear") {
                        model.clearFilters()
                    }
                    .buttonStyle(NativeSecondaryButtonStyle())
                    Button("Search") {
                        model.resetAndReload()
                    }
                    .buttonStyle(NativePrimaryButtonStyle())
                }
            }
        }
    }

    private var addTransactionCard: some View {
        NativeCard(title: "Add missed transaction", centered: true) {
            VStack(alignment: .leading, spacing: 10) {
                gridRow {
                    nativePickerGroups("Account", selection: $model.addTxAccount, groups: model.addAccountOptions)
                    nativeDateField("Date", text: $model.addTxDate)
                    nativePicker("Status", selection: $model.addTxStatus, options: ["Posted", "Pending"], emptyLabel: "Posted")
                }
                gridRow {
                    nativeTextField("Amount", text: $model.addTxAmount)
                    nativeTextField("Merchant", text: $model.addTxMerchant)
                }
                Text("Use positive for spending and negative for deposits/refunds.")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                HStack {
                    Button(model.addTxSaving ? "Saving..." : "Save") {
                        Task { await model.saveTransaction() }
                    }
                    .buttonStyle(NativePrimaryButtonStyle())
                    .disabled(model.addTxSaving)
                    Button("Cancel") { model.addPanelOpen = false }
                        .buttonStyle(NativeSecondaryButtonStyle())
                    if !model.addTxMessage.isEmpty {
                        Text(model.addTxMessage)
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private var transactionList: some View {
        VStack(spacing: 10) {
            ForEach(model.transactions) { tx in
                NativeTransactionRow(transaction: tx) {
                    selectedTransaction = tx
                }
            }
        }
    }

    private var loadMoreButton: some View {
        Button("Load more") {
            model.loadNext()
        }
        .buttonStyle(NativeSecondaryButtonStyle())
        .frame(maxWidth: .infinity, alignment: .center)
    }

    @ViewBuilder
    private func gridRow<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        HStack(alignment: .bottom, spacing: 8) {
            content()
        }
    }

    private func nativeTextField(_ title: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.system(size: 9, weight: .semibold, design: .rounded)).foregroundStyle(.secondary)
            TextField("", text: text)
                .textFieldStyle(.roundedBorder)
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .frame(height: 34)
                .frame(maxWidth: .infinity)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func nativeDateField(_ title: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.system(size: 9, weight: .semibold, design: .rounded)).foregroundStyle(.secondary)
            TextField("yyyy-mm-dd", text: text)
                .textFieldStyle(.roundedBorder)
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .frame(height: 34)
                .frame(maxWidth: .infinity)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func nativePicker(_ title: String, selection: Binding<String>, options: [String], emptyLabel: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.system(size: 9, weight: .semibold, design: .rounded)).foregroundStyle(.secondary)
            Menu {
                Button(emptyLabel) { selection.wrappedValue = "" }
                ForEach(options, id: \.self) { option in
                    Button(option) { selection.wrappedValue = option }
                }
            } label: {
                nativeMenuLabel(selection.wrappedValue.isEmpty ? emptyLabel : selection.wrappedValue)
            }
            .tint(.primary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func nativePickerPairs(_ title: String, selection: Binding<String>, options: [(label: String, value: String)], emptyLabel: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.system(size: 9, weight: .semibold, design: .rounded)).foregroundStyle(.secondary)
            Menu {
                Button(emptyLabel) { selection.wrappedValue = "" }
                ForEach(options, id: \.value) { option in
                    Button(option.label) { selection.wrappedValue = option.value }
                }
            } label: {
                let current = options.first(where: { $0.value == selection.wrappedValue })?.label ?? emptyLabel
                nativeMenuLabel(current)
            }
            .tint(.primary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func nativePickerGroups(_ title: String, selection: Binding<String>, groups: [(group: String, items: [(id: Int, label: String)])]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.system(size: 9, weight: .semibold, design: .rounded)).foregroundStyle(.secondary)
            Menu {
                Button("Pick account") { selection.wrappedValue = "" }
                ForEach(groups, id: \.group) { group in
                    Section(group.group) {
                        ForEach(group.items, id: \.id) { item in
                            Button(item.label) { selection.wrappedValue = String(item.id) }
                        }
                    }
                }
            } label: {
                let currentID = Int(selection.wrappedValue)
                let current = groups
                    .flatMap { $0.items }
                    .first(where: { $0.id == currentID })?
                    .label ?? "Pick account"
                nativeMenuLabel(current)
            }
            .tint(.primary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct NativeTransactionRow: View {
    let transaction: TransactionItem
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(alignment: .center, spacing: 10) {
                NativeIconBadge(category: transaction.category)
                VStack(alignment: .leading, spacing: 3) {
                    Text((transaction.merchant.isEmpty ? "Unknown merchant" : transaction.merchant).uppercased())
                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                        .foregroundStyle(.primary)
                        .lineLimit(1)
                    Text([transaction.bank, transaction.card].compactMap { $0 }.joined(separator: " • "))
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    if let category = transaction.category, !category.isEmpty {
                        Text(category)
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer(minLength: 10)
                VStack(alignment: .trailing, spacing: 4) {
                    Text(nativeMoneyValue(transaction.amount))
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                        .foregroundStyle(nativeTransactionAmountColor(transaction.amount))
                    if let rc = transaction.roundupCents, rc > 0 {
                        Text("¢ \(rc)")
                            .font(.system(size: 10, weight: .semibold, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .padding(12)
            .background(Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

private struct NativeTransactionInspectView: View {
    let transaction: TransactionItem
    let detail: TransactionDetailPayload?
    let onDismiss: () -> Void
    let onRefresh: () -> Void

    @State private var categoryText: String = ""
    @State private var statusText: String = ""
    @State private var dateText: String = ""
    @State private var actionStatus: String = ""
    @State private var showDeleteConfirm = false
    @State private var showInvertConfirm = false

    var body: some View {
        ZStack {
            Color.black.opacity(0.46)
                .ignoresSafeArea()
                .onTapGesture(perform: close)

            NativePopupChrome(
                title: "Transaction",
                subtitle: subtitleText,
                onClose: close
            ) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        NativeCard(title: "Transaction", centered: true) {
                            VStack(alignment: .leading, spacing: 10) {
                                txKV(label: "Merchant", value: detail?.merchant.isEmpty == false ? detail?.merchant ?? transaction.merchant : transaction.merchant)
                                txKV(label: "Account", value: detail?.card ?? transaction.card ?? "—")
                                txKV(label: "Amount", value: nativeMoneyValue(detail?.amount ?? transaction.amount), valueColor: nativeTransactionAmountColor(detail?.amount ?? transaction.amount))
                                txKV(label: "Date", value: detail?.postedDate ?? transaction.postedDate ?? transaction.dateISO ?? "—")
                                txKV(label: "Matches", value: detail?.categoryRulePattern ?? (detail?.category ?? transaction.category ?? "—"))
                            }
                        }

                        NativeCard(title: "Category", centered: true) {
                            VStack(alignment: .leading, spacing: 8) {
                                TextField("Category", text: $categoryText)
                                    .textFieldStyle(.roundedBorder)
                                Button("Save category") {
                                    Task { await saveCategory() }
                                }
                                .buttonStyle(NativePrimaryButtonStyle())
                            }
                        }

                        NativeCard(title: "Details", centered: true) {
                            VStack(alignment: .leading, spacing: 8) {
                                TextField("Status", text: $statusText).textFieldStyle(.roundedBorder)
                                TextField("Posted date", text: $dateText).textFieldStyle(.roundedBorder)
                                Button("Save status/date") {
                                    Task { await saveMeta() }
                                }
                                .buttonStyle(NativeSecondaryButtonStyle())
                            }
                        }

                        NativeCard(title: "Actions", centered: true) {
                            VStack(spacing: 8) {
                                Button("Invert amount") { showInvertConfirm = true }
                                    .buttonStyle(NativeSecondaryButtonStyle())
                                Button("Toggle ignore") { Task { await toggleIgnore() } }
                                    .buttonStyle(NativeSecondaryButtonStyle())
                                Button("Delete transaction", role: .destructive) { showDeleteConfirm = true }
                                    .buttonStyle(NativePrimaryButtonStyle())
                            }
                        }

                        if !actionStatus.isEmpty {
                            Text(actionStatus)
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(16)
                }
            }
        }
        .onAppear {
            categoryText = detail?.category ?? transaction.category ?? ""
            statusText = detail?.status ?? transaction.status ?? ""
            dateText = detail?.postedDate ?? transaction.postedDate ?? transaction.dateISO ?? ""
        }
        .confirmationDialog("Delete this transaction?", isPresented: $showDeleteConfirm, titleVisibility: .visible) {
            Button("Delete", role: .destructive) { Task { await deleteTx() } }
            Button("Cancel", role: .cancel) {}
        }
        .confirmationDialog("Invert this transaction amount?", isPresented: $showInvertConfirm, titleVisibility: .visible) {
            Button("Invert", role: .destructive) { Task { await invertTx() } }
            Button("Cancel", role: .cancel) {}
        }
    }

    private var subtitleText: String {
        let amount = nativeMoneyValue(detail?.amount ?? transaction.amount)
        let date = detail?.postedDate ?? detail?.purchaseDate ?? transaction.postedDate ?? transaction.dateISO ?? "—"
        return "\(amount)  •  \(date)"
    }

    private func close() {
        onDismiss()
    }

    private func txKV(label: String, value: String, valueColor: Color = .primary) -> some View {
        HStack {
            Text(label).font(.system(size: 12, weight: .semibold, design: .rounded)).foregroundStyle(.secondary)
            Spacer()
            Text(value).font(.system(size: 13, weight: .bold, design: .rounded))
                .foregroundStyle(valueColor)
        }
    }

    private func saveCategory() async {
        do {
            _ = try await QuailCashAPI.shared.updateTransactionCategory(txId: transaction.id, category: categoryText)
            actionStatus = "Category saved."
            onRefresh()
        } catch {
            actionStatus = error.localizedDescription
        }
    }

    private func saveMeta() async {
        do {
            _ = try await QuailCashAPI.shared.updateTransactionMeta(txId: transaction.id, status: statusText, postedDate: dateText)
            actionStatus = "Saved."
            onRefresh()
        } catch {
            actionStatus = error.localizedDescription
        }
    }

    private func invertTx() async {
        do {
            _ = try await QuailCashAPI.shared.invertTransactionAmount(txId: transaction.id)
            actionStatus = "Inverted."
            onRefresh()
        } catch {
            actionStatus = error.localizedDescription
        }
    }

    private func toggleIgnore() async {
        do {
            let next = !(detail?.isIgnored ?? transaction.isIgnored ?? false)
            _ = try await QuailCashAPI.shared.ignoreTransaction(txId: transaction.id, ignored: next)
            actionStatus = next ? "Ignored." : "Unignored."
            onRefresh()
        } catch {
            actionStatus = error.localizedDescription
        }
    }

    private func deleteTx() async {
        do {
            _ = try await QuailCashAPI.shared.deleteTransaction(txId: transaction.id)
            actionStatus = "Deleted."
            onDismiss()
            onRefresh()
        } catch {
            actionStatus = error.localizedDescription
        }
    }
}

// MARK: - Recurring

private struct NativeRecurringCalendarPayload: Decodable {
    let ok: Bool?
    let year: Int?
    let month: Int?
    let start: String?
    let end: String?
    let events: [NativeRecurringCalendarEvent]
}

private struct NativeRecurringCalendarEvent: Decodable, Hashable {
    let date: String
    let merchant: String?
    let merchantDisplay: String?
    let category: String?
    let amount: Double?
    let cadence: String?
    let accountID: Int?
    let kind: String?

    enum CodingKeys: String, CodingKey {
        case date, merchant, category, amount, cadence, kind
        case merchantDisplay = "merchant_display"
        case accountID = "account_id"
    }
}

private struct NativeRecurringGroup: Decodable, Hashable, Identifiable {
    var id: String { merchant ?? UUID().uuidString }
    let merchant: String?
    let merchantDisplay: String?
    let lastSeen: String?
    let patterns: [NativeRecurringPattern]?

    enum CodingKeys: String, CodingKey {
        case merchant
        case merchantDisplay = "merchant_display"
        case lastSeen = "last_seen"
        case patterns
    }
}

private struct NativeRecurringPattern: Decodable, Hashable, Identifiable {
    var id: String { key ?? UUID().uuidString }
    let key: String?
    let merchant: String?
    let merchantDisplay: String?
    let cadence: String?
    let amount: Double?
    let accountID: Int?
    let lastSeen: String?
    let occurrences: Int?
    let kind: String?
    let transferDisplay: String?
    let tx: [TransactionItem]?

    enum CodingKeys: String, CodingKey {
        case key, merchant
        case merchantDisplay = "merchant_display"
        case cadence, amount
        case accountID = "account_id"
        case lastSeen = "last_seen"
        case occurrences
        case kind
        case transferDisplay = "transfer_display"
        case tx
    }
}

private struct NativeRecurringIgnoredPreviewGroup: Decodable, Hashable, Identifiable {
    var id: String { merchant ?? UUID().uuidString }
    let merchant: String?
    let merchantDisplay: String?
    let lastSeen: String?
    let patterns: [NativeRecurringPattern]?

    enum CodingKeys: String, CodingKey {
        case merchant
        case merchantDisplay = "merchant_display"
        case lastSeen = "last_seen"
        case patterns
    }
}

@MainActor
private final class NativeRecurringViewModel: ObservableObject {
    @Published var month: Date = Date()
    @Published var minOccurrences = "3"
    @Published var includeStale = false
    @Published var groups: [NativeRecurringGroup] = []
    @Published var ignoredGroups: [NativeRecurringIgnoredPreviewGroup] = []
    @Published var calendar: NativeRecurringCalendarPayload?
    @Published var statusText = "Ready."
    @Published var isLoading = false
    @Published var selectedDayISO: String?
    @Published var selectedDayEvents: [NativeRecurringCalendarEvent] = []
    @Published var selectedPattern: NativeRecurringPattern?
    @Published var showDayModal = false
    @Published var showPatternModal = false
    @Published var showIgnoredModal = false
    @Published var mergeAlias = ""
    @Published var mergeSelectedKeys: Set<String> = []
    @Published var mergeCandidates: [NativeRecurringPattern] = []
    @Published var showMergeModal = false
    @Published var mergeMessage = ""

    func reloadAll() { Task { await loadAll() } }

    func loadAll() async {
        isLoading = true
        statusText = "Loading..."
        async let recurringData = QuailCashAPI.shared.fetchData(path: "/recurring", queryItems: [
            URLQueryItem(name: "min_occ", value: minOccurrences),
            URLQueryItem(name: "include_stale", value: includeStale ? "true" : "false"),
        ])
        async let calendarData = QuailCashAPI.shared.fetchData(path: "/recurring/calendar", queryItems: [
            URLQueryItem(name: "year", value: String(Calendar.current.component(.year, from: month))),
            URLQueryItem(name: "month", value: String(Calendar.current.component(.month, from: month))),
            URLQueryItem(name: "min_occ", value: minOccurrences),
            URLQueryItem(name: "include_stale", value: includeStale ? "true" : "false"),
        ])
        do {
            let rec = try await recurringData
            let cal = try await calendarData
            groups = try JSONDecoder.quailCash.decode([NativeRecurringGroup].self, from: rec)
            calendar = try JSONDecoder.quailCash.decode(NativeRecurringCalendarPayload.self, from: cal)
            statusText = "Loaded recurring data."
        } catch {
            statusText = error.localizedDescription
        }
        isLoading = false
    }

    func loadIgnored() async {
        do {
            let data = try await QuailCashAPI.shared.fetchData(path: "/recurring/ignored-preview", queryItems: [
                URLQueryItem(name: "min_occ", value: minOccurrences),
                URLQueryItem(name: "include_stale", value: includeStale ? "true" : "false"),
            ])
            ignoredGroups = try JSONDecoder.quailCash.decode([NativeRecurringIgnoredPreviewGroup].self, from: data)
        } catch {
            ignoredGroups = []
            mergeMessage = error.localizedDescription
        }
    }

    func openDay(_ event: NativeRecurringCalendarEvent) {
        selectedDayISO = event.date
        selectedDayEvents = calendar?.events.filter { $0.date == event.date } ?? []
        showDayModal = true
    }

    func openPattern(_ pattern: NativeRecurringPattern) {
        selectedPattern = pattern
        showPatternModal = true
    }

    func ignoreMerchant(_ merchant: String) async {
        do {
            try await QuailCashAPI.shared.sendJSON(path: "/recurring/ignore/merchant", method: "POST", queryItems: [URLQueryItem(name: "name", value: merchant)])
            await loadAll()
        } catch { statusText = error.localizedDescription }
    }

    func unignoreMerchant(_ merchant: String) async {
        do {
            try await QuailCashAPI.shared.sendJSON(path: "/recurring/unignore/merchant", method: "POST", queryItems: [URLQueryItem(name: "name", value: merchant)])
            await loadIgnored()
            await loadAll()
        } catch { statusText = error.localizedDescription }
    }

    func ignorePattern(_ pattern: NativeRecurringPattern) async {
        do {
            try await QuailCashAPI.shared.sendJSON(path: "/recurring/ignore/pattern", method: "POST", queryItems: [
                URLQueryItem(name: "merchant", value: pattern.merchant ?? ""),
                URLQueryItem(name: "amount", value: String(pattern.amount ?? 0)),
                URLQueryItem(name: "account_id", value: String(pattern.accountID ?? -1)),
            ])
            await loadAll()
        } catch { statusText = error.localizedDescription }
    }

    func openMergeModal(for merchant: String, patterns: [NativeRecurringPattern]) {
        mergeAlias = merchant
        mergeCandidates = patterns
        mergeSelectedKeys = []
        showMergeModal = true
        mergeMessage = ""
    }

    func mergeSelected() async {
        let keys = Array(mergeSelectedKeys)
        guard keys.count >= 2 else {
            mergeMessage = "Select at least 2 patterns."
            return
        }
        do {
            try await QuailCashAPI.shared.sendJSON(path: "/recurring/merge-patterns-selected", method: "POST", jsonBody: [
                "merchant": mergeAlias,
                "pattern_keys": keys,
            ])
            showMergeModal = false
            await loadAll()
        } catch {
            mergeMessage = error.localizedDescription
        }
    }
}

struct NativeRecurringPageView: View {
    @StateObject private var model = NativeRecurringViewModel()

    var body: some View {
        PageShell(title: "Recurring", subtitle: "Projected calendar and recurring groups") {
            VStack(alignment: .leading, spacing: 12) {
                calendarCard
                recurringControls
                recurringList
                Text(model.statusText)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
        }
        .task { await model.loadAll() }
        .sheet(isPresented: $model.showDayModal) {
            NativeRecurringDayModal(events: model.selectedDayEvents, dateISO: model.selectedDayISO ?? "")
        }
        .sheet(isPresented: $model.showPatternModal) {
            if let pattern = model.selectedPattern {
                NativeRecurringPatternModal(pattern: pattern, onIgnore: {
                    Task { await model.ignorePattern(pattern) }
                }, onOpenMerge: {
                    model.openMergeModal(for: pattern.merchant ?? "", patterns: [pattern])
                })
            }
        }
        .sheet(isPresented: $model.showIgnoredModal) {
            NativeIgnoredRecurringModal(groups: model.ignoredGroups, onUnignore: { merchant in
                Task { await model.unignoreMerchant(merchant) }
            }, onOpenPattern: { pattern in
                model.selectedPattern = pattern
                model.showPatternModal = true
            })
        }
        .sheet(isPresented: $model.showMergeModal) {
            NativeMergeRecurringModal(alias: model.mergeAlias, patterns: model.mergeCandidates, selected: $model.mergeSelectedKeys, message: $model.mergeMessage, onConfirm: {
                Task { await model.mergeSelected() }
            })
        }
    }

    private var calendarCard: some View {
        NativeCard(title: "Calendar", centered: true) {
            VStack(spacing: 10) {
                HStack {
                    Button { shiftMonth(-1) } label: {
                        Image(systemName: "chevron.left")
                    }
                    .buttonStyle(NativeChipButtonStyle())
                    Spacer()
                    Text(monthTitle)
                        .font(.system(size: 16, weight: .semibold, design: .rounded))
                    Spacer()
                    Button { shiftMonth(1) } label: {
                        Image(systemName: "chevron.right")
                    }
                    .buttonStyle(NativeChipButtonStyle())
                }
                HStack {
                    Text("Out: \(nativeMoneyValue(outTotal))").font(.system(size: 11, weight: .medium, design: .rounded))
                    Spacer()
                    Text("In: \(nativeMoneyValue(inTotal))").font(.system(size: 11, weight: .medium, design: .rounded))
                }
                HStack {
                    ForEach(["Sun","Mon","Tue","Wed","Thu","Fri","Sat"], id: \.self) { d in
                        Text(d).font(.system(size: 10, weight: .semibold, design: .rounded)).foregroundStyle(.secondary).frame(maxWidth: .infinity)
                    }
                }
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 6), count: 7), spacing: 6) {
                    ForEach(calendarCells, id: \.self) { cell in
                        if cell.inMonth {
                            Button {
                                if !cell.events.isEmpty { model.selectedDayEvents = cell.events; model.selectedDayISO = cell.dateISO; model.showDayModal = true }
                            } label: {
                                calendarCellView(cell)
                            }
                            .buttonStyle(.plain)
                        } else {
                            calendarCellView(cell)
                                .opacity(0.35)
                        }
                    }
                }
                .frame(maxWidth: .infinity)
            }
        }
    }

    private var recurringControls: some View {
        NativeCard(title: "Recurring", centered: true) {
            VStack(alignment: .leading, spacing: 10) {
                Toggle("Include stale", isOn: $model.includeStale)
                HStack {
                    Text("Min occurrences:")
                    TextField("", text: $model.minOccurrences)
                        .textFieldStyle(.roundedBorder)
                        .frame(width: 70)
                    Button("Refresh") { model.reloadAll() }.buttonStyle(NativeSecondaryButtonStyle())
                    Button("Review ignored") {
                        Task {
                            await model.loadIgnored()
                            model.showIgnoredModal = true
                        }
                    }.buttonStyle(NativeSecondaryButtonStyle())
                }
            }
        }
    }

    private var recurringList: some View {
        VStack(spacing: 10) {
            ForEach(model.groups, id: \.id) { group in
                NativeRecurringGroupCard(group: group, onTapPattern: { pattern in model.openPattern(pattern) }, onIgnoreMerchant: { merchant in Task { await model.ignoreMerchant(merchant) } }, onMerge: { merchant, patterns in model.openMergeModal(for: merchant, patterns: patterns) })
            }
        }
    }

    private var monthTitle: String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "MMMM yyyy"
        return f.string(from: model.month)
    }

    private var calendarCells: [NativeCalendarCell] {
        let cal = Calendar.current
        let year = cal.component(.year, from: model.month)
        let month = cal.component(.month, from: model.month)
        guard let first = cal.date(from: DateComponents(year: year, month: month, day: 1)) else { return [] }
        let last = cal.date(from: DateComponents(year: year, month: month + 1, day: 0)) ?? first
        var start = first
        start.addTimeInterval(-Double(cal.component(.weekday, from: first) - 1) * 86400)
        var end = last
        end.addTimeInterval(Double(7 - cal.component(.weekday, from: last)) * 86400)
        while Int(end.timeIntervalSince(start) / 86400) + 1 < 35 { end.addTimeInterval(7 * 86400) }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withFullDate]
        var cells: [NativeCalendarCell] = []
        var d = start
        while d <= end {
            let iso = formatter.string(from: d)
            let events = model.calendar?.events.filter { $0.date == iso } ?? []
            cells.append(NativeCalendarCell(dateISO: iso, day: cal.component(.day, from: d), inMonth: cal.component(.month, from: d) == month, events: events))
            d = cal.date(byAdding: .day, value: 1, to: d) ?? d.addingTimeInterval(86400)
        }
        return cells
    }

    private var outTotal: Double {
        guard let events = model.calendar?.events else { return 0 }
        var total = 0.0
        for event in events {
            let kind = (event.kind ?? "").lowercased()
            let isIncome = event.cadence == "paycheck" || kind == "income"
            if !isIncome {
                total += max(0, event.amount ?? 0)
            }
        }
        return total
    }

    private var inTotal: Double {
        guard let events = model.calendar?.events else { return 0 }
        var total = 0.0
        for event in events {
            let kind = (event.kind ?? "").lowercased()
            let isIncome = event.cadence == "paycheck" || kind == "income"
            if isIncome {
                total += abs(event.amount ?? 0)
            }
        }
        return total
    }

    private func shiftMonth(_ delta: Int) {
        if let next = Calendar.current.date(byAdding: .month, value: delta, to: model.month) {
            model.month = next
            model.reloadAll()
        }
    }

    private func calendarCellView(_ cell: NativeCalendarCell) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(String(cell.day))
                .font(.system(size: 12, weight: .semibold, design: .rounded))
            if !cell.events.isEmpty {
                HStack(spacing: 2) {
                    ForEach(cell.events.prefix(3), id: \.self) { event in
                        NativeIconBadge(category: event.category)
                            .frame(width: 18, height: 18)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, minHeight: 56, alignment: .topLeading)
        .padding(6)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

private struct NativeCalendarCell: Hashable {
    let dateISO: String
    let day: Int
    let inMonth: Bool
    let events: [NativeRecurringCalendarEvent]
}

private struct NativeRecurringGroupCard: View {
    let group: NativeRecurringGroup
    let onTapPattern: (NativeRecurringPattern) -> Void
    let onIgnoreMerchant: (String) -> Void
    let onMerge: (String, [NativeRecurringPattern]) -> Void
    @State private var expanded = true

    var body: some View {
        NativeCard(title: group.merchantDisplay ?? group.merchant ?? "Recurring", centered: true) {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Button {
                        withAnimation(.snappy) { expanded.toggle() }
                    } label: {
                        Image(systemName: expanded ? "chevron.down" : "chevron.right")
                    }
                    .buttonStyle(NativeChipButtonStyle())
                    Spacer()
                    Button("Merge") { onMerge(group.merchant ?? "", group.patterns ?? []) }
                        .buttonStyle(NativeSecondaryButtonStyle())
                    Button("Ignore") { onIgnoreMerchant(group.merchant ?? "") }
                        .buttonStyle(NativeSecondaryButtonStyle())
                }
                if expanded {
                    ForEach(group.patterns ?? [], id: \.id) { pattern in
                        NativeRecurringPatternRow(pattern: pattern, onTap: { onTapPattern(pattern) }, onIgnore: { onTapPattern(pattern) })
                    }
                }
            }
        }
    }
}

private struct NativeRecurringPatternRow: View {
    let pattern: NativeRecurringPattern
    let onTap: () -> Void
    let onIgnore: () -> Void
    var body: some View {
        HStack(spacing: 10) {
            Button(action: onTap) {
                NativeIconBadge(category: pattern.categoryForIcon)
            }
            .buttonStyle(.plain)
            VStack(alignment: .leading, spacing: 2) {
                Text((pattern.cadence ?? "irregular").capitalized)
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                Text("\(pattern.lastSeen ?? "") • x\(pattern.occurrences ?? 0)")
                    .font(.system(size: 10, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 4) {
                Button("Ignore") { onIgnore() }
                    .buttonStyle(NativeSecondaryButtonStyle())
                Text(nativeMoneyValue(pattern.amount ?? 0))
                    .font(.system(size: 13, weight: .bold, design: .rounded))
            }
        }
        .padding(10)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

private extension NativeRecurringPattern {
    var categoryForIcon: String? {
        if let tx = tx?.last, let category = tx.category, !category.isEmpty { return category }
        return kind
    }
}

private struct NativeRecurringDayModal: View {
    @Environment(\.dismiss) private var dismiss
    let events: [NativeRecurringCalendarEvent]
    let dateISO: String
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(events, id: \.self) { event in
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text((event.merchantDisplay ?? event.merchant ?? "Unknown").uppercased()).font(.system(size: 13, weight: .semibold, design: .rounded))
                                Text([event.category, event.cadence].compactMap { $0 }.joined(separator: " • "))
                                    .font(.system(size: 11, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Text(nativeMoneyValue(event.amount ?? 0)).font(.system(size: 13, weight: .bold, design: .rounded))
                        }
                        .padding(12)
                        .background(Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
                    }
                }
                .padding(16)
            }
            .navigationTitle(dateISO)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Close") { dismiss() } } }
        }
    }
}

private struct NativeRecurringPatternModal: View {
    @Environment(\.dismiss) private var dismiss
    let pattern: NativeRecurringPattern
    let onIgnore: () -> Void
    let onOpenMerge: () -> Void
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    NativeCard(title: pattern.merchantDisplay ?? pattern.merchant ?? "Pattern", centered: true) {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack { Text("Cadence"); Spacer(); Text(pattern.cadence ?? "—").bold() }
                            HStack { Text("Amount"); Spacer(); Text(nativeMoneyValue(pattern.amount ?? 0)).bold() }
                            HStack { Text("Occurrences"); Spacer(); Text("\(pattern.occurrences ?? 0)").bold() }
                            HStack { Text("Last seen"); Spacer(); Text(pattern.lastSeen ?? "—").bold() }
                        }
                    }
                    HStack {
                        Button("Ignore") { onIgnore() }.buttonStyle(NativeSecondaryButtonStyle())
                        Button("Merge") { onOpenMerge() }.buttonStyle(NativeSecondaryButtonStyle())
                    }
                    if let txs = pattern.tx, !txs.isEmpty {
                        NativeCard(title: "Transactions", centered: true) {
                            VStack(spacing: 8) {
                                ForEach(txs) { tx in
                                    NativeTransactionRow(transaction: tx) {}
                                }
                            }
                        }
                    }
                }
                .padding(16)
            }
            .navigationTitle("Occurrence")
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Close") { dismiss() } } }
        }
    }
}

private struct NativeIgnoredRecurringModal: View {
    @Environment(\.dismiss) private var dismiss
    let groups: [NativeRecurringIgnoredPreviewGroup]
    let onUnignore: (String) -> Void
    let onOpenPattern: (NativeRecurringPattern) -> Void
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 10) {
                    ForEach(groups, id: \.id) { group in
                        NativeCard(title: group.merchantDisplay ?? group.merchant ?? "Ignored", centered: true) {
                            VStack(spacing: 8) {
                                Button("Unignore") { onUnignore(group.merchant ?? "") }
                                    .buttonStyle(NativeSecondaryButtonStyle())
                                ForEach(group.patterns ?? [], id: \.id) { pattern in
                                    Button(action: { onOpenPattern(pattern) }) {
                                        HStack {
                                            Text((pattern.cadence ?? "").capitalized)
                                            Spacer()
                                            Text(nativeMoneyValue(pattern.amount ?? 0))
                                        }
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                    }
                }
                .padding(16)
            }
            .navigationTitle("Ignored merchants")
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Close") { dismiss() } } }
        }
    }
}

private struct NativeMergeRecurringModal: View {
    @Environment(\.dismiss) private var dismiss
    let alias: String
    let patterns: [NativeRecurringPattern]
    @Binding var selected: Set<String>
    @Binding var message: String
    let onConfirm: () -> Void
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Merchant: \(alias.uppercased())").font(.system(size: 14, weight: .bold, design: .rounded))
                    ForEach(patterns, id: \.id) { pattern in
                        let key = pattern.id
                        Button {
                            if selected.contains(key) { selected.remove(key) } else { selected.insert(key) }
                        } label: {
                            HStack {
                                Image(systemName: selected.contains(key) ? "checkmark.square.fill" : "square")
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(pattern.cadence ?? "irregular")
                                    Text("\(pattern.lastSeen ?? "") • \(nativeMoneyValue(pattern.amount ?? 0))").font(.system(size: 11, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                                }
                                Spacer()
                            }
                            .padding(10)
                            .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                    Text(message).font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                    HStack {
                        Button("Merge") { onConfirm() }.buttonStyle(NativePrimaryButtonStyle())
                        Button("Cancel") { dismiss() }.buttonStyle(NativeSecondaryButtonStyle())
                    }
                }
                .padding(16)
            }
            .navigationTitle("Merge recurring patterns")
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Close") { dismiss() } } }
        }
    }
}
