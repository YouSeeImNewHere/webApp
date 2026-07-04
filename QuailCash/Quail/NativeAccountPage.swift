import SwiftUI
import Charts
import Combine

private func nativeAccountPalette() -> QuailThemePalette {
    QuailTheme.palette(for: UserDefaults.standard.string(forKey: "quail.settings.theme") ?? "system")
}

private struct NativeAccountTopBar: View {
    let badgeValue: Int?
    let selectedTab: BottomTab
    let accountLabel: String
    let accountOptions: [NativeAccountSwitchOption]
    let palette: QuailThemePalette
    let onLeadingTap: () -> Void
    let onTrailingTap: () -> Void
    let onSelectTab: (BottomTab) -> Void
    let onSelectAccount: (Int) -> Void

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Button(action: onLeadingTap) {
                Image(systemName: "gearshape.fill")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(palette.chromeIconForeground)
                    .frame(width: 36, height: 36)
                    .background(palette.chromeIconBackground, in: Circle())
                    .overlay(Circle().stroke(palette.border, lineWidth: 1))
            }
            .accessibilityLabel("Settings")

            Spacer(minLength: 4)

            Menu {
                ForEach(accountOptions) { option in
                    Button {
                        onSelectAccount(option.id)
                    } label: {
                        Text(option.label)
                    }
                }
            } label: {
                HStack(spacing: 8) {
                    Text(accountLabel)
                        .font(.system(size: 16, weight: .semibold, design: .rounded))
                        .foregroundStyle(palette.chromeIconForeground)
                        .lineLimit(1)
                        .minimumScaleFactor(0.75)
                    Image(systemName: "chevron.up.chevron.down")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(palette.chromeIconForeground.opacity(0.72))
                }
                .padding(.horizontal, 14)
                .frame(maxWidth: .infinity, alignment: .center)
                .frame(height: 38)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(palette.border, lineWidth: 1))
            }
            .frame(maxWidth: .infinity)
            .frame(minWidth: 228)

            Spacer(minLength: 4)

            Button(action: onTrailingTap) {
                ZStack(alignment: .topTrailing) {
                    Image(systemName: "bell.fill")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(palette.chromeIconForeground)
                        .frame(width: 36, height: 36)
                        .background(palette.chromeIconBackground, in: Circle())
                        .overlay(Circle().stroke(palette.border, lineWidth: 1))

                    if let badgeValue, badgeValue > 0 {
                        Text(badgeValue > 9 ? "9+" : "\(badgeValue)")
                            .font(.system(size: 10, weight: .bold, design: .rounded))
                            .foregroundStyle(palette.tooltipText)
                            .frame(minWidth: 16, minHeight: 16)
                            .padding(.horizontal, 4)
                            .background(palette.notificationBadge, in: Capsule(style: .continuous))
                            .offset(x: 4, y: -4)
                    }
                }
            }
            .accessibilityLabel("Notifications")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(palette.barBackground)
        .overlay(
            Rectangle()
                .fill(palette.barDivider)
                .frame(height: 1),
            alignment: .bottom
        )
    }
}

private struct NativeAccountChromeFrame<Content: View>: View {
    @EnvironmentObject private var navigator: AppNavigator
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    let badgeValue: Int?
    let selectedTab: BottomTab
    let accountLabel: String
    let accountOptions: [NativeAccountSwitchOption]
    let onLeadingTap: () -> Void
    let onTrailingTap: () -> Void
    let onSelectTab: (BottomTab) -> Void
    let onSelectAccount: (Int) -> Void
    let content: Content

    init(
        badgeValue: Int?,
        selectedTab: BottomTab,
        accountLabel: String,
        accountOptions: [NativeAccountSwitchOption],
        onLeadingTap: @escaping () -> Void,
        onTrailingTap: @escaping () -> Void,
        onSelectTab: @escaping (BottomTab) -> Void,
        onSelectAccount: @escaping (Int) -> Void,
        @ViewBuilder content: () -> Content
    ) {
        self.badgeValue = badgeValue
        self.selectedTab = selectedTab
        self.accountLabel = accountLabel
        self.accountOptions = accountOptions
        self.onLeadingTap = onLeadingTap
        self.onTrailingTap = onTrailingTap
        self.onSelectTab = onSelectTab
        self.onSelectAccount = onSelectAccount
        self.content = content()
    }

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        ZStack {
            LinearGradient(
                colors: [palette.backgroundTop, palette.backgroundBottom],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()

            content
        }
        .safeAreaInset(edge: .top, spacing: 0) {
            NativeAccountTopBar(
                badgeValue: badgeValue ?? navigator.unreadCount,
                selectedTab: selectedTab,
                accountLabel: accountLabel,
                accountOptions: accountOptions,
                palette: palette,
                onLeadingTap: onLeadingTap,
                onTrailingTap: onTrailingTap,
                onSelectTab: onSelectTab,
                onSelectAccount: onSelectAccount
            )
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            AppBottomBar(
                selectedTab: selectedTab,
                palette: palette,
                onSelectTab: onSelectTab,
                onDashboardTap: { navigator.setRoot(.dashboard) }
            )
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .toolbar(.hidden, for: .navigationBar)
        .task {
            await navigator.refreshUnreadCountIfNeeded()
        }
    }
}

private struct NativeAccountSwitchOption: Identifiable, Hashable {
    let id: Int
    let label: String
}

@MainActor
private final class NativeAccountPageModel: ObservableObject {
    @Published var info: AccountInfoPayload?
    @Published var accountOptions: [NativeAccountSwitchOption] = []
    @Published var series: [ChartPoint] = []
    @Published var selectedPoint: ChartPoint?
    @Published var projectedGrowthEnabled = false
    @Published var tooltipExpanded = true
    @Published var startDate: Date = Calendar.current.date(from: DateComponents(year: Calendar.current.component(.year, from: Date()), month: Calendar.current.component(.month, from: Date()), day: 1)) ?? Date()
    @Published var endDate: Date = Date()
    @Published var selectedYear: Int = Calendar.current.component(.year, from: Date())
    @Published var isLoadingChart = true
    @Published var chartError: String?
    @Published var upcomingEvents: [UpcomingEventPayload] = []
    @Published var upcomingLoading = true
    @Published var upcomingError: String?
    @Published var transactions: [TransactionItem] = []
    @Published var txLoading = true
    @Published var txError: String?
    @Published var addOpen = false
    @Published var addDate = ""
    @Published var addStatus = "posted"
    @Published var addAmount = ""
    @Published var addMerchant = ""
    @Published var addMessage = ""
    @Published var showVerifySheet = false
    @Published var verifyDate = ""
    @Published var isSavingAdd = false
    @Published var isVerifying = false

    let selectedAccount: BankAccountPayload
    let auditMode: Bool

    private let api = QuailAPI.shared
    private var didStart = false
    private var endBeforeProjected: Date?

    init(selectedAccount: BankAccountPayload, auditMode: Bool) {
        self.selectedAccount = selectedAccount
        self.auditMode = auditMode
        self.verifyDate = nativeIsoYesterday()
        resetCurrentMonth()
    }

    func startIfNeeded() {
        guard !didStart else { return }
        didStart = true
        Task { await loadEverything() }
    }

    var currentAccountID: Int { selectedAccount.id }

    var accountLabel: String {
        if let info {
            let left = info.institution?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            let right = info.name.trimmingCharacters(in: .whitespacesAndNewlines)
            let joined = [left, right].filter { !$0.isEmpty }.joined(separator: " - ")
            return joined.isEmpty ? right : joined
        }
        return selectedAccount.name
    }

    var accountTypeText: String {
        let raw = (info?.accountType ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if !raw.isEmpty { return raw.lowercased() }
        let fallback = selectedAccount.name.split(separator: "-").last.map(String.init) ?? "balance"
        return fallback.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    var isCreditAccount: Bool {
        accountTypeText.contains("credit")
    }

    var currentBalanceText: String {
        let value = series.last?.value ?? selectedAccount.total
        return isCreditAccount ? nativeFormatAccountBalance(value) : nativeMoneyValue(abs(value))
    }

    var growthPercentText: String {
        guard let first = series.first?.value, let last = series.last?.value, first != 0 else { return "—" }
        let pct = ((last - first) / abs(first)) * 100
        let absPct = abs(pct)
        let formatted: String
        if absPct > 100 {
            formatted = String(format: "%.0f%%", absPct.rounded())
        } else {
            formatted = String(format: "%.1f%%", (absPct * 10).rounded() / 10)
        }
        return pct < 0 ? "-\(formatted)" : formatted
    }

    var growthColor: Color {
        guard let first = series.first?.value, let last = series.last?.value, first != 0 else { return .primary }
        return last >= first ? .green : .red
    }

    var yDomain: ClosedRange<Double> {
        let values = series.map(\.value)
        guard let minValue = values.min(), let maxValue = values.max() else { return 0...1 }
        if minValue == maxValue {
            let pad = max(1, abs(maxValue) * 0.05)
            return (minValue - pad)...(maxValue + pad)
        }
        let pad = max(1, (maxValue - minValue) * 0.12)
        return (minValue - pad)...(maxValue + pad)
    }

    var projectedPoints: [ChartPoint] {
        guard projectedGrowthEnabled, series.count >= 2 else { return [] }
        let sample = Array(series.suffix(min(series.count, 8)))
        guard let first = sample.first, let last = sample.last else { return [] }
        let interval = max(1, Calendar.current.dateComponents([.day], from: first.date, to: last.date).day ?? sample.count - 1)
        let slope = (last.value - first.value) / Double(interval)
        return (1...7).compactMap { step in
            guard let date = Calendar.current.date(byAdding: .day, value: step, to: last.date) else { return nil }
            return ChartPoint(date: date, value: last.value + slope * Double(step), banks: nil, savings: nil, cards: nil, cardsBalance: nil)
        }
    }

    var tooltipTitle: String {
        selectedPoint.map { NativeAccountPageModel.tooltipFormatter.string(from: $0.date) } ?? ""
    }

    var tooltipLines: [String] {
        guard let p = selectedPoint else { return [] }
        return [
            "\(accountTypeText.capitalized): \(nativeMoneyValue(p.value))"
        ]
    }

    var accountSeriesStartEndLabel: String {
        "\(Self.isoDate(startDate)) to \(Self.isoDate(endDate))"
    }

    var csvExportText: String {
        guard !transactions.isEmpty else { return "" }
        let ordered = transactions.sorted {
            let a = ($0.effectiveDate ?? $0.dateISO ?? $0.postedDate ?? "")
            let b = ($1.effectiveDate ?? $1.dateISO ?? $1.postedDate ?? "")
            if a != b { return a > b }
            return $0.id > $1.id
        }
        var lines = ["status,purchase date,posted date,time,merchant,cost,running total"]
        for tx in ordered {
            let line = [
                csvCell(tx.status ?? "posted"),
                csvCell(tx.effectiveDate ?? tx.dateISO ?? tx.postedDate ?? tx.date ?? ""),
                csvCell(tx.postedDate ?? ""),
                csvCell(tx.date ?? ""),
                csvCell(tx.merchant),
                csvCell(String(format: "%.2f", tx.amount)),
                csvCell(String(format: "%.2f", tx.balanceAfter ?? 0)),
            ].joined(separator: ",")
            lines.append(line)
        }
        return lines.joined(separator: "\n") + "\n"
    }

    func loadEverything() async {
        await loadAccountInfo()
        await loadAccountSwitchOptions()
        await reloadChart()
        await reloadUpcoming()
        await reloadTransactions()
    }

    func loadAccountInfo() async {
        do {
            info = try await api.fetchAccountInfo(accountID: currentAccountID)
        } catch {
            info = nil
        }
    }

    func loadAccountSwitchOptions() async {
        do {
            let bank = try await api.fetchBankInfo()
            let accounts = bank.accounts.map { NativeAccountSwitchOption(id: $0.id, label: "\($0.bank) - \($0.name)") }
            let cards = bank.creditCards.map { NativeAccountSwitchOption(id: $0.id, label: "\($0.bank) - \($0.name)") }
            accountOptions = (accounts + cards).sorted { $0.label.localizedCaseInsensitiveCompare($1.label) == .orderedAscending }
        } catch {
            accountOptions = []
        }
    }

    func reloadChart() async {
        isLoadingChart = true
        chartError = nil
        do {
            let raw = try await api.fetchAccountSeries(accountID: currentAccountID, start: Self.isoDate(startDate), end: Self.isoDate(endDate))
            series = raw.compactMap { point in
                guard let date = Self.dateFormatter.date(from: point.date) else { return nil }
                return ChartPoint(date: date, value: point.value, banks: point.banks, savings: point.savings, cards: point.cards, cardsBalance: point.cardsBalance)
            }
            .sorted { $0.date < $1.date }
            selectedPoint = series.last
        } catch QuailAPIError.unauthorized {
            chartError = "Sign in to load chart data."
        } catch {
            chartError = error.localizedDescription
        }
        isLoadingChart = false
    }

    func reloadUpcoming() async {
        upcomingLoading = true
        upcomingError = nil
        do {
            upcomingEvents = try await api.fetchUpcomingWindow(daysAhead: 30, accountID: currentAccountID)
        } catch QuailAPIError.unauthorized {
            upcomingError = "Sign in to load upcoming items."
        } catch {
            upcomingError = error.localizedDescription
        }
        upcomingLoading = false
    }

    func reloadTransactions() async {
        txLoading = true
        txError = nil
        do {
            let payload = try await api.fetchAccountTransactionsRange(accountID: currentAccountID, start: Self.isoDate(startDate), end: Self.isoDate(endDate), limit: 500)
            transactions = payload.transactions
        } catch QuailAPIError.unauthorized {
            txError = "Sign in to load transactions."
        } catch {
            txError = error.localizedDescription
        }
        txLoading = false
    }

    func updateRange(reload: Bool = true) {
        let normalized = normalizedRange(start: startDate, end: endDate)
        startDate = normalized.start
        endDate = normalized.end
        selectedYear = Calendar.current.component(.year, from: normalized.start)
        selectedPoint = nil
        if reload {
            Task { await reloadChart(); await reloadTransactions(); await reloadUpcoming() }
        }
    }

    func setYear(_ year: Int) {
        let today = Date()
        let currentYear = Calendar.current.component(.year, from: today)
        let clamped = min(year, currentYear)
        selectedYear = clamped
        let start = Calendar.current.date(from: DateComponents(year: clamped, month: 1, day: 1)) ?? startDate
        let end = (clamped == currentYear) ? today : (Calendar.current.date(from: DateComponents(year: clamped, month: 12, day: 31)) ?? endDate)
        startDate = start
        endDate = end
        updateRange()
    }

    func previousYear() { setYear(selectedYear - 1) }
    func nextYear() { setYear(selectedYear + 1) }

    func setQuarter(_ quarter: Int) {
        let year = selectedYear
        let startMonth = max(1, min(4, quarter)) * 3 - 2
        let start = Calendar.current.date(from: DateComponents(year: year, month: startMonth, day: 1)) ?? startDate
        let endMonth = startMonth + 2
        let lastDay = Calendar.current.range(of: .day, in: .month, for: Calendar.current.date(from: DateComponents(year: year, month: endMonth, day: 1)) ?? Date())?.count ?? 30
        let end = Calendar.current.date(from: DateComponents(year: year, month: endMonth, day: lastDay)) ?? endDate
        startDate = start
        endDate = end
        updateRange()
    }

    func setMonth(_ monthIndex: Int) {
        let year = selectedYear
        let month = max(1, min(12, monthIndex + 1))
        let start = Calendar.current.date(from: DateComponents(year: year, month: month, day: 1)) ?? startDate
        let end = Calendar.current.date(byAdding: DateComponents(month: 1, day: -1), to: start) ?? endDate
        startDate = start
        endDate = end
        updateRange()
    }

    func setAnnual() {
        let year = selectedYear
        let start = Calendar.current.date(from: DateComponents(year: year, month: 1, day: 1)) ?? startDate
        let end = Calendar.current.date(from: DateComponents(year: year, month: 12, day: 31)) ?? endDate
        startDate = start
        endDate = end
        updateRange()
    }

    func setYTD() {
        let year = selectedYear
        let start = Calendar.current.date(from: DateComponents(year: year, month: 1, day: 1)) ?? startDate
        let end = min(Date(), Calendar.current.date(from: DateComponents(year: year, month: 12, day: 31)) ?? Date())
        startDate = start
        endDate = end
        updateRange()
    }

    func applyProjectedGrowthToggle(_ enabled: Bool) {
        projectedGrowthEnabled = enabled
        if enabled {
            if endBeforeProjected == nil { endBeforeProjected = endDate }
            let todayIso = Self.isoDate(Date())
            if !Self.sameMonth(Self.isoDate(endDate), todayIso) {
                projectedGrowthEnabled = false
                endBeforeProjected = nil
                return
            }
            if let endOfMonth = Calendar.current.date(from: DateComponents(year: Calendar.current.component(.year, from: Date()), month: Calendar.current.component(.month, from: Date()) + 1, day: 0)) {
                endDate = endOfMonth
            }
        } else {
            if let restore = endBeforeProjected {
                endDate = restore
            }
            endBeforeProjected = nil
        }
        updateRange()
    }

    func clearSelection() {
        selectedPoint = nil
    }

    func updateSelection(location: CGPoint, proxy: ChartProxy, geometry: GeometryProxy) {
        guard !series.isEmpty else {
            selectedPoint = nil
            return
        }
        guard let plotFrameAnchor = proxy.plotFrame else {
            selectedPoint = nil
            return
        }
        let plotFrame = geometry[plotFrameAnchor]
        let xOffset = location.x - plotFrame.origin.x
        guard let date: Date = proxy.value(atX: xOffset) else {
            selectedPoint = nil
            return
        }
        selectedPoint = series.min(by: {
            abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date))
        })
    }

    func loadCsvText() -> String { csvExportText }

    func saveNewTransaction(date: String, status: String, amount: Double, merchant: String) async throws {
        _ = try await api.createTransaction(accountID: currentAccountID, amount: amount, merchant: merchant, status: status, date: date)
    }

    func verifyBalance(on date: String) async throws {
        _ = try await api.verifyAccountBalance(accountID: currentAccountID, verifiedDate: date)
    }

    private func resetCurrentMonth() {
        let cal = Calendar.current
        let now = Date()
        startDate = cal.date(from: cal.dateComponents([.year, .month], from: now)) ?? now
        endDate = now
        selectedYear = cal.component(.year, from: now)
    }

    private func normalizedRange(start: Date, end: Date) -> (start: Date, end: Date) {
        let cal = Calendar.current
        let s = cal.startOfDay(for: start)
        let e = cal.startOfDay(for: max(start, end))
        return (s, e)
    }

    private static let dateFormatter: DateFormatter = {
        let df = DateFormatter()
        df.locale = Locale(identifier: "en_US_POSIX")
        df.calendar = Calendar(identifier: .gregorian)
        df.timeZone = TimeZone(secondsFromGMT: 0)
        df.dateFormat = "yyyy-MM-dd"
        return df
    }()

    private static let tooltipFormatter: DateFormatter = {
        let df = DateFormatter()
        df.locale = Locale(identifier: "en_US_POSIX")
        df.dateFormat = "MMM dd"
        return df
    }()

    private static func sameMonth(_ a: String, _ b: String) -> Bool {
        String(a).prefix(7) == String(b).prefix(7)
    }

    private static func isoDate(_ date: Date) -> String {
        let cal = Calendar.current
        let y = cal.component(.year, from: date)
        let m = cal.component(.month, from: date)
        let d = cal.component(.day, from: date)
        return String(format: "%04d-%02d-%02d", y, m, d)
    }
}

struct NativeAccountPageView: View {
    @EnvironmentObject private var navigator: AppNavigator
    @StateObject private var model: NativeAccountPageModel
    @State private var selectedTransaction: TransactionItem?

    init(account: BankAccountPayload, auditMode: Bool) {
        _model = StateObject(wrappedValue: NativeAccountPageModel(selectedAccount: account, auditMode: auditMode))
    }

    var body: some View {
        NativeAccountChromeFrame(
            badgeValue: nil,
            selectedTab: .home,
            accountLabel: model.accountLabel,
            accountOptions: model.accountOptions,
            onLeadingTap: { navigator.show(.settings) },
            onTrailingTap: { navigator.show(.notifications) },
            onSelectTab: selectTab,
            onSelectAccount: selectAccount
        ) {
            AppPageScroll(refreshAction: {
                await model.reloadChart()
                await model.reloadUpcoming()
                await model.reloadTransactions()
            }) {
                accountChartCard
                if !model.upcomingEvents.isEmpty || model.upcomingLoading || model.upcomingError != nil {
                    upcomingCard
                }
                transactionsCard
            }
        }
        .task {
            model.startIfNeeded()
        }
        .sheet(isPresented: $model.showVerifySheet) {
            verifyBalanceSheet
                .presentationDetents([.height(520)])
                .presentationDragIndicator(.visible)
        }
        .sheet(item: $selectedTransaction) { tx in
            SharedTransactionInspectPopupView(
                transaction: tx,
                onDismiss: { selectedTransaction = nil },
                onRefresh: { Task { await model.reloadTransactions(); await model.reloadChart() } }
            )
            .presentationDetents([.large])
            .presentationDragIndicator(.visible)
        }
    }

    private func selectTab(_ tab: BottomTab) {
        switch tab {
        case .home: navigator.popToRoot()
        case .spending: navigator.show(.spending)
        case .all: navigator.show(.allTransactions)
        case .analytics: navigator.show(.analytics)
        case .recurring: navigator.show(.recurring)
        }
    }

    private func selectAccount(_ id: Int) {
        guard id != model.currentAccountID else { return }
        let label = model.accountOptions.first(where: { $0.id == id })?.label ?? "Account"
        let parts = label.split(separator: "-", maxSplits: 1).map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
        let name = parts.count > 1 ? parts[1] : label
        navigator.replaceTop(with: .account(BankAccountPayload(id: id, name: name, total: 0, lastCsvUploadAt: nil, lastManualVerifiedAt: nil, creditLimit: nil), audit: model.auditMode))
    }

    private var accountChartCard: some View {
        AccountChartSection(model: model)
    }

    private var upcomingCard: some View {
        AccountUpcomingCard(events: model.upcomingEvents, isLoading: model.upcomingLoading, errorMessage: model.upcomingError)
    }

    private var transactionsCard: some View {
        AccountTransactionsCard(
            model: model,
            onAddToggle: { model.addOpen.toggle() },
            onExport: { },
            onAudit: {
                let next = model.auditMode ? nil : true
                let route = AppRoute.account(BankAccountPayload(id: model.currentAccountID, name: model.accountLabel, total: 0, lastCsvUploadAt: nil, lastManualVerifiedAt: nil, creditLimit: nil), audit: next ?? false)
                navigator.show(route)
            },
            onVerified: { model.showVerifySheet = true },
            onSelectTransaction: { selectedTransaction = $0 }
        )
    }

    private var verifyBalanceSheet: some View {
        VerifyBalanceSheetView(
            accountName: model.accountLabel,
            initialVerifiedDateISO: model.verifyDate,
            isSaving: model.isVerifying,
            statusText: model.addMessage.isEmpty ? nil : model.addMessage,
            onCancel: { model.showVerifySheet = false },
            onConfirm: { dateISO in
                model.isVerifying = true
                defer { model.isVerifying = false }
                do {
                    try await model.verifyBalance(on: dateISO)
                    model.showVerifySheet = false
                    await model.loadAccountInfo()
                } catch {
                    model.addMessage = error.localizedDescription
                    throw error
                }
            }
        )
    }
}

private struct AccountChartSection: View {
    @ObservedObject var model: NativeAccountPageModel

    var body: some View {
        let palette = nativeAccountPalette()
        VStack(alignment: .leading, spacing: 11) {
            HStack(spacing: 6) {
                metricPill(title: model.accountTypeText.isEmpty ? "balance" : model.accountTypeText, value: model.currentBalanceText)
                metricPill(title: "% Growth", value: model.growthPercentText, compact: true, valueColor: model.growthColor)
            }

            HStack(spacing: 4) {
                dateField(title: "Start", date: Binding(get: { model.startDate }, set: { model.startDate = $0 }))
                Spacer(minLength: 10)
                dateField(title: "End", date: Binding(get: { model.endDate }, set: { model.endDate = $0 }))
                Spacer(minLength: 4)
                Button("Update") {
                    model.updateRange()
                }
                .buttonStyle(AccountPrimaryButtonStyle())
                .frame(height: 36)
            }

            HStack(spacing: 5) {
                ForEach(0..<4) { idx in
                    Button("Q\(idx + 1)") { model.setQuarter(idx + 1) }
                        .buttonStyle(NativeAccountChipButtonStyle())
                }
                Button("YTD") { model.setYTD() }
                    .buttonStyle(NativeAccountChipButtonStyle())
                Spacer(minLength: 12)
                HStack(spacing: 4) {
                    Button { model.previousYear() } label: {
                        Image(systemName: "arrow.left")
                    }
                    .buttonStyle(NativeAccountChipButtonStyle())
                    Text(String(model.selectedYear))
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                    Button { model.nextYear() } label: {
                        Image(systemName: "arrow.right")
                    }
                    .buttonStyle(NativeAccountChipButtonStyle())
                }
            }

            chartContainer

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 7) {
                    ForEach(Array(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"].enumerated()), id: \.offset) { idx, name in
                        Button(name) { model.setMonth(idx) }
                            .buttonStyle(NativeAccountChipButtonStyle())
                    }
                    Button("Annual") { model.setAnnual() }
                        .buttonStyle(NativeAccountChipButtonStyle())
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private var chartContainer: some View {
        let palette = nativeAccountPalette()
        return GeometryReader { proxy in
            ZStack(alignment: .topLeading) {
                chartBody
                    .frame(width: proxy.size.width, height: 224, alignment: .topLeading)
                    .clipped()
                    .padding(11)
                    .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))

                HStack(spacing: 6) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Project")
                            .font(.system(size: 8, weight: .semibold, design: .rounded))
                            .foregroundStyle(.secondary)
                        Text("Growth")
                            .font(.system(size: 8, weight: .semibold, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                    Toggle("", isOn: Binding(
                        get: { model.projectedGrowthEnabled },
                        set: { model.applyProjectedGrowthToggle($0) }
                    ))
                    .labelsHidden()
                    .controlSize(.mini)
                    .toggleStyle(SwitchToggleStyle(tint: .blue))
                }
                .scaleEffect(0.9, anchor: .leading)
                .padding(.horizontal, 5)
                .padding(.vertical, 4)
                .background(palette.surface.opacity(0.96), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
                .padding(.top, 8)
                .padding(.leading, 68)
                .contentShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                .onTapGesture {
                    model.applyProjectedGrowthToggle(!model.projectedGrowthEnabled)
                }

                if model.selectedPoint != nil {
                    VStack(alignment: .leading, spacing: 4) {
                        if model.tooltipExpanded {
                            ForEach(model.tooltipLines, id: \.self) { line in
                                Text(line)
                                    .font(.system(size: 10, weight: .medium, design: .rounded))
                                    .foregroundStyle(palette.tooltipText.opacity(0.92))
                            }
                        }
                        HStack(spacing: 4) {
                            Text(model.tooltipTitle)
                                .font(.system(size: 10, weight: .medium, design: .rounded))
                                .foregroundStyle(palette.tooltipText.opacity(0.88))
                            if !model.tooltipExpanded {
                                Image(systemName: "chevron.down")
                                    .font(.system(size: 9, weight: .bold))
                                    .foregroundStyle(palette.tooltipText.opacity(0.92))
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .trailing)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 6)
                    .background(palette.tooltipBackground, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .frame(maxWidth: 160, alignment: .leading)
                    .padding(.trailing, 10)
                    .padding(.bottom, 22)
                    .contentShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .onTapGesture {
                        model.tooltipExpanded.toggle()
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
                }
            }
        }
        .frame(height: 224)
    }

    @ViewBuilder
    private var chartBody: some View {
        let palette = nativeAccountPalette()
        if model.isLoadingChart {
            HStack {
                ProgressView()
                Text("Loading chart...")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, minHeight: 170, alignment: .center)
        } else if let error = model.chartError {
            VStack(spacing: 6) {
                Text(error)
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                Button("Retry") {
                    Task { await model.reloadChart() }
                }
                .buttonStyle(AccountSecondaryButtonStyle())
            }
            .frame(maxWidth: .infinity, minHeight: 170, alignment: .center)
        } else {
            Chart {
                ForEach(model.series) { point in
                    AreaMark(
                        x: .value("Date", point.date),
                        yStart: .value("Baseline", model.yDomain.lowerBound),
                        yEnd: .value("Value", point.value)
                    )
                    .foregroundStyle(
                        LinearGradient(
                            colors: [palette.accent.opacity(0.16), palette.accent.opacity(0.04)],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )

                    LineMark(
                        x: .value("Date", point.date),
                        y: .value("Value", point.value)
                    )
                    .foregroundStyle(palette.accent)
                    .lineStyle(StrokeStyle(lineWidth: 2.8, lineCap: .round, lineJoin: .round))
                }

                ForEach(model.projectedPoints) { point in
                    LineMark(
                        x: .value("Date", point.date),
                        y: .value("Value", point.value)
                    )
                    .foregroundStyle(palette.accent.opacity(0.5))
                    .lineStyle(StrokeStyle(lineWidth: 2.1, lineCap: .round, lineJoin: .round, dash: [5, 4]))
                }

                if let selected = model.selectedPoint {
                    RuleMark(x: .value("Selected", selected.date))
                        .foregroundStyle(palette.border.opacity(2.0))

                    PointMark(
                        x: .value("Selected", selected.date),
                        y: .value("Selected", selected.value)
                    )
                    .foregroundStyle(palette.accent)
                    .symbolSize(70)
                }
            }
            .chartXAxis(.hidden)
            .chartYAxis {
                AxisMarks(position: .leading) { _ in
                    AxisGridLine().foregroundStyle(palette.border.opacity(0.9))
                    AxisTick().foregroundStyle(palette.border)
                    AxisValueLabel()
                        .font(.system(size: 10, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
            .chartYScale(domain: model.yDomain)
            .chartPlotStyle { plotArea in
                plotArea.clipped()
            }
            .chartOverlay { proxy in
                GeometryReader { geometry in
                    Rectangle()
                        .fill(.clear)
                        .contentShape(Rectangle())
                        .gesture(
                            DragGesture(minimumDistance: 0)
                                .onChanged { value in
                                    model.updateSelection(location: value.location, proxy: proxy, geometry: geometry)
                                }
                                .onEnded { value in
                                    model.updateSelection(location: value.location, proxy: proxy, geometry: geometry)
                                }
                        )
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func metricPill(title: String, value: String, compact: Bool = false, valueColor: Color = .primary) -> some View {
        let palette = nativeAccountPalette()
        return HStack(spacing: 6) {
            Text(title)
                .font(.system(size: compact ? 10 : 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Spacer(minLength: compact ? 2 : 4)
            Text(value)
                .font(.system(size: compact ? 13 : 14, weight: .bold, design: .rounded))
                .monospacedDigit()
                .foregroundStyle(valueColor)
        }
        .frame(maxWidth: compact ? 122 : .infinity)
        .padding(.horizontal, compact ? 9 : 11)
        .padding(.vertical, compact ? 7 : 8)
        .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 13, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 13, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func dateField(title: String, date: Binding<Date>) -> some View {
        VStack(alignment: .center, spacing: 3) {
            Text(title)
                .font(.system(size: 10, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .center)
            DatePicker("", selection: date, displayedComponents: .date)
                .labelsHidden()
                .datePickerStyle(.compact)
                .controlSize(.small)
        }
        .frame(width: 96, alignment: .leading)
    }
}

private struct AccountUpcomingCard: View {
    let events: [UpcomingEventPayload]
    let isLoading: Bool
    let errorMessage: String?

    var body: some View {
        let palette = nativeAccountPalette()
        VStack(alignment: .leading, spacing: 12) {
            Text("Upcoming transactions")
                .font(.system(size: 18, weight: .bold, design: .rounded))
            if isLoading {
                ProgressView().frame(maxWidth: .infinity, minHeight: 70, alignment: .center)
            } else if let errorMessage {
                Text(errorMessage)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        ForEach(groupUpcoming(events), id: \.date) { group in
                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    Text(group.weekday)
                                        .font(.system(size: 14, weight: .bold, design: .rounded))
                                    Spacer()
                                    Text(group.shortDate)
                                        .font(.system(size: 12, weight: .medium, design: .rounded))
                                        .foregroundStyle(.secondary)
                                }
                                let summaries = groupSummaries(group.items)
                                if summaries.isEmpty {
                                    Text("—")
                                        .font(.system(size: 13, weight: .medium, design: .rounded))
                                        .foregroundStyle(.secondary)
                                } else {
                                    ForEach(Array(summaries.prefix(2)), id: \.label) { summary in
                                        HStack(spacing: 8) {
                                            Text(summary.label)
                                                .font(.system(size: 12, weight: .semibold, design: .rounded))
                                                .lineLimit(1)
                                            Spacer(minLength: 8)
                                            Text(summary.amount)
                                                .font(.system(size: 12, weight: .bold, design: .rounded))
                                                .foregroundStyle(summary.color)
                                                .lineLimit(1)
                                        }
                                    }
                                    if summaries.count > 2 {
                                        Text("+\(summaries.count - 2) more")
                                            .font(.system(size: 11, weight: .medium, design: .rounded))
                                            .foregroundStyle(.secondary)
                                    }
                                }
                            }
                            .frame(width: 236, height: 126, alignment: .topLeading)
                            .padding(14)
                            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(palette.border, lineWidth: 1))
                        }
                    }
                }
            }
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private struct DayGroup: Identifiable {
        let id: String
        let date: String
        let weekday: String
        let shortDate: String
        let items: [UpcomingEventPayload]
    }

    private func groupUpcoming(_ events: [UpcomingEventPayload]) -> [DayGroup] {
        let grouped = Dictionary(grouping: events, by: { $0.date })
        return grouped.keys.sorted().map { key in
            let items = grouped[key] ?? []
            let date = nativeDateFromISO(key) ?? Date()
            return DayGroup(
                id: key,
                date: key,
                weekday: nativeWeekdayShort(date),
                shortDate: nativeMonthDayShort(date),
                items: items.sorted { ($0.amount ?? 0) < ($1.amount ?? 0) }
            )
        }
    }

    private struct GroupSummary {
        let label: String
        let amount: String
        let color: Color
        let total: Double
    }

    private func groupSummaries(_ items: [UpcomingEventPayload]) -> [GroupSummary] {
        var grouped: [String: (total: Double, income: Bool, count: Int)] = [:]
        for item in items {
            let label = categoryLabel(item)
            var current = grouped[label] ?? (0, false, 0)
            current.total += abs(item.amount ?? 0)
            current.income = current.income || isIncome(item)
            current.count += 1
            grouped[label] = current
        }
        return grouped.map { key, value in
            GroupSummary(
                label: value.count > 1 ? "\(key) (\(value.count))" : key,
                amount: "\(value.income ? "+" : "-")\(nativeMoneyValue(value.total))",
                color: value.income ? .green : .red,
                total: value.total
            )
        }
        .sorted { lhs, rhs in
            if lhs.total == rhs.total { return lhs.label < rhs.label }
            return lhs.total > rhs.total
        }
    }

    private func categoryLabel(_ event: UpcomingEventPayload) -> String {
        let value = (event.type ?? event.category ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return value.isEmpty ? "Unassigned" : value
    }

    private func isIncome(_ event: UpcomingEventPayload) -> Bool {
        let type = (event.type ?? "").lowercased()
        let cadence = (event.cadence ?? "").lowercased()
        return type == "income" || cadence == "paycheck" || cadence == "interest"
    }
}

private struct AccountTransactionsCard: View {
    @ObservedObject var model: NativeAccountPageModel
    let onAddToggle: () -> Void
    let onExport: () -> Void
    let onAudit: () -> Void
    let onVerified: () -> Void
    let onSelectTransaction: (TransactionItem) -> Void

    var body: some View {
        let palette = nativeAccountPalette()
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center, spacing: 10) {
                Text("Transactions")
                    .font(.system(size: 18, weight: .bold, design: .rounded))
                Spacer(minLength: 0)
                ShareLink(item: model.csvExportText, preview: SharePreview("account.csv")) {
                    Text("Download Transactions")
                        .font(.system(size: 12, weight: .bold, design: .rounded))
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(palette.primaryButton, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        .foregroundStyle(palette.primaryButtonText)
                }
            }

            HStack {
                Button("Add Transaction") { onAddToggle() }
                    .buttonStyle(AccountSecondaryButtonStyle())
                Button("Audit") { onAudit() }
                    .buttonStyle(AccountPrimaryButtonStyle())
                Button("Verified") { onVerified() }
                    .buttonStyle(AccountPrimaryButtonStyle())
            }

            if model.addOpen {
                addTransactionPanel
            }

            if model.auditMode {
                auditBanner
            }

            if model.txLoading {
                ProgressView().frame(maxWidth: .infinity, alignment: .center)
            } else if let txError = model.txError {
                Text(txError)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            } else {
                txList
            }
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private var auditBanner: some View {
        let palette = nativeAccountPalette()
        return Text("Audit mode")
            .font(.system(size: 11, weight: .bold, design: .rounded))
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(palette.elevatedSurface, in: Capsule())
            .overlay(Capsule().stroke(palette.border, lineWidth: 1))
    }

    private var addTransactionPanel: some View {
        let palette = nativeAccountPalette()
        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                accountField("Date", text: $model.addDate)
                accountField("Status", text: $model.addStatus)
            }
            HStack(spacing: 8) {
                accountField("Amount", text: $model.addAmount)
                accountField("Merchant", text: $model.addMerchant)
            }
            HStack(spacing: 8) {
                Button(model.isSavingAdd ? "Saving..." : "Save") {
                    Task {
                        model.isSavingAdd = true
                        defer { model.isSavingAdd = false }
                        do {
                            try await model.saveNewTransaction(
                                date: model.addDate.isEmpty ? nativeIsoToday() : model.addDate,
                                status: model.addStatus.isEmpty ? "posted" : model.addStatus,
                                amount: Double(model.addAmount) ?? 0,
                                merchant: model.addMerchant
                            )
                            model.addMessage = "Saved."
                            model.addOpen = false
                            await model.reloadTransactions()
                        } catch {
                            model.addMessage = error.localizedDescription
                        }
                    }
                }
                .buttonStyle(AccountPrimaryButtonStyle())
            Button("Cancel") { model.addOpen = false }
                    .buttonStyle(AccountSecondaryButtonStyle())
                if !model.addMessage.isEmpty {
                    Text(model.addMessage)
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(12)
        .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private var txList: some View {
        VStack(spacing: 12) {
            let grouped = groupTransactions(model.transactions)
            ForEach(grouped, id: \.id) { section in
                VStack(alignment: .leading, spacing: 10) {
                    HStack {
                        Text(section.title)
                            .font(.system(size: 16, weight: .bold, design: .rounded))
                        Spacer()
                        if let bal = section.balance {
                            Text(model.isCreditAccount ? nativeFormatAccountBalance(bal) : nativeMoneyValue(abs(bal)))
                                .font(.system(size: 14, weight: .bold, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                    }
                    ForEach(section.rows) { tx in
                        Button {
                            onSelectTransaction(tx)
                        } label: {
                            NativeAccountTransactionRow(transaction: tx, isCreditAccount: model.isCreditAccount)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.top, 4)
                Divider().opacity(0.3)
            }
        }
    }

    private struct TransactionSection: Identifiable {
        let id: String
        let title: String
        let balance: Double?
        let rows: [TransactionItem]
    }

    private func groupTransactions(_ rows: [TransactionItem]) -> [TransactionSection] {
        let pending = rows.filter { String($0.status ?? "").lowercased() == "pending" }
        let posted = rows.filter { String($0.status ?? "").lowercased() != "pending" }

        var sections: [TransactionSection] = []
        if !pending.isEmpty {
            sections.append(TransactionSection(id: "pending", title: "Pending", balance: pending.first?.balanceAfter, rows: pending))
        }

        let grouped = Dictionary(grouping: posted, by: { String($0.dateISO ?? $0.effectiveDate ?? $0.postedDate ?? "Unknown") })
        for key in grouped.keys.sorted(by: >) {
            let rows = grouped[key] ?? []
            sections.append(TransactionSection(id: key, title: nativeDayHeaderLabel(key), balance: rows.first?.balanceAfter, rows: rows))
        }
        return sections
    }
}

private struct NativeAccountTransactionRow: View {
    let transaction: TransactionItem
    let isCreditAccount: Bool

    var body: some View {
        let palette = nativeAccountPalette()
        return HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(transactionDateText)
                    .font(.system(size: 12, weight: .bold, design: .rounded))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)

                ZStack {
                    Circle()
                        .fill(palette.border.opacity(0.9))
                        .frame(width: 38, height: 38)
                    Text(txMerchantInitial)
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                        .foregroundStyle(.primary)
                }
            }
            .frame(width: 46, alignment: .leading)

            VStack(alignment: .leading, spacing: 3) {
                Text(transaction.merchant.isEmpty ? "Unknown merchant" : transaction.merchant)
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                    .textCase(.uppercase)
                Text(transactionSubtitle)
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 10)
            VStack(alignment: .trailing, spacing: 4) {
                Text(nativeMoneyValue(transaction.amount))
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                    .foregroundStyle(transaction.amount >= 0 ? palette.negative : palette.positive)
                if let bal = transaction.balanceAfter {
                    Text(balanceText(bal, isCreditAccount: isCreditAccount))
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 10)
        .padding(.horizontal, 12)
        .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private var transactionSubtitle: String {
        let left = [transaction.bank, transaction.card].compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
        return left.isEmpty ? (transaction.category ?? "") : left.joined(separator: " • ")
    }

    private var txMerchantInitial: String {
        let raw = transaction.merchant.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let first = raw.first else { return "?" }
        return String(first).uppercased()
    }

    private var transactionDateText: String {
        nativeShortTransactionDate(transaction.dateISO ?? transaction.postedDate ?? transaction.date ?? transaction.effectiveDate)
    }
}

private func balanceText(_ value: Double, isCreditAccount: Bool) -> String {
    isCreditAccount ? nativeFormatAccountBalance(value) : nativeMoneyValue(abs(value))
}

private struct NativeAccountIcon: View {
    let category: String?

    var body: some View {
        let palette = nativeAccountPalette()
        Image(systemName: nativeAccountSymbolName(category))
            .font(.system(size: 20, weight: .semibold))
            .foregroundStyle(palette.accent)
            .frame(width: 40, height: 40)
            .background(palette.surface, in: Circle())
            .overlay(Circle().stroke(palette.border, lineWidth: 1))
    }
}

private func nativeAccountSymbolName(_ category: String?) -> String {
    let key = String(category ?? "").lowercased()
    if key.contains("bill") { return "doc.text" }
    if key.contains("parking") { return "p.circle" }
    if key.contains("travel") { return "airplane" }
    if key.contains("grocer") || key.contains("food") { return "cart" }
    if key.contains("transfer") { return "arrow.left.arrow.right" }
    if key.contains("income") || key.contains("salary") || key.contains("paycheck") { return "banknote" }
    return "creditcard"
}

private func nativeDayHeaderLabel(_ iso: String) -> String {
    guard let date = nativeDateFromISO(iso) else { return iso }
    return "\(nativeMonthDayShort(date)) (\(nativeWeekdayShort(date)))"
}

private func nativeDateFromISO(_ iso: String) -> Date? {
    let df = DateFormatter()
    df.locale = Locale(identifier: "en_US_POSIX")
    df.calendar = Calendar(identifier: .gregorian)
    df.timeZone = TimeZone(secondsFromGMT: 0)
    df.dateFormat = "yyyy-MM-dd"
    return df.date(from: iso)
}

private func nativeWeekdayShort(_ date: Date) -> String {
    let df = DateFormatter()
    df.locale = Locale(identifier: "en_US_POSIX")
    df.timeZone = TimeZone(secondsFromGMT: 0)
    df.dateFormat = "EEE"
    return df.string(from: date)
}

private func nativeMonthDayShort(_ date: Date) -> String {
    let df = DateFormatter()
    df.locale = Locale(identifier: "en_US_POSIX")
    df.timeZone = TimeZone(secondsFromGMT: 0)
    df.dateFormat = "MM/dd"
    return df.string(from: date)
}

private func nativeIso(from date: Date) -> String {
    let df = DateFormatter()
    df.locale = Locale(identifier: "en_US_POSIX")
    df.calendar = Calendar(identifier: .gregorian)
    df.timeZone = TimeZone(secondsFromGMT: 0)
    df.dateFormat = "yyyy-MM-dd"
    return df.string(from: date)
}

private func nativeIsoYesterday() -> String {
    let date = Calendar(identifier: .gregorian).date(byAdding: .day, value: -1, to: Date()) ?? Date()
    return nativeIso(from: date)
}

private let nativeDateFormatter: DateFormatter = {
    let df = DateFormatter()
    df.locale = Locale(identifier: "en_US_POSIX")
    df.calendar = Calendar(identifier: .gregorian)
    df.timeZone = TimeZone(secondsFromGMT: 0)
    df.dateFormat = "yyyy-MM-dd"
    return df
}()

private func csvCell(_ value: String) -> String {
    if value.contains(",") || value.contains("\"") || value.contains("\n") {
        return "\"\(value.replacingOccurrences(of: "\"", with: "\"\""))\""
    }
    return value
}

private struct AccountPrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        let palette = QuailTheme.palette(for: UserDefaults.standard.string(forKey: "quail.settings.theme") ?? "system")
        configuration.label
            .font(.system(size: 13, weight: .bold, design: .rounded))
            .padding(.horizontal, 14)
            .frame(height: 36)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(palette.primaryButton.opacity(configuration.isPressed ? 0.82 : 1.0))
            )
            .foregroundStyle(palette.primaryButtonText)
    }
}

private struct NativeAccountChipButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        let palette = QuailTheme.palette(for: UserDefaults.standard.string(forKey: "quail.settings.theme") ?? "system")
        configuration.label
            .font(.system(size: 11, weight: .semibold, design: .rounded))
            .padding(.horizontal, 10)
            .frame(height: 32)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(palette.secondaryButton.opacity(configuration.isPressed ? 0.82 : 1.0))
            )
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(palette.border, lineWidth: 1))
            .foregroundStyle(palette.secondaryButtonText)
    }
}

private struct AccountSecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        let palette = QuailTheme.palette(for: UserDefaults.standard.string(forKey: "quail.settings.theme") ?? "system")
        configuration.label
            .font(.system(size: 12, weight: .bold, design: .rounded))
            .padding(.horizontal, 12)
            .frame(height: 36)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(palette.secondaryButton.opacity(configuration.isPressed ? 0.85 : 1.0))
            )
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(palette.border, lineWidth: 1))
            .foregroundStyle(palette.secondaryButtonText)
    }
}

private func accountField(_ title: String, text: Binding<String>) -> some View {
    let palette = QuailTheme.palette(for: UserDefaults.standard.string(forKey: "quail.settings.theme") ?? "system")
    return VStack(alignment: .leading, spacing: 4) {
        Text(title)
            .font(.system(size: 10, weight: .semibold, design: .rounded))
            .foregroundStyle(.secondary)
        TextField("", text: text)
            .textFieldStyle(.plain)
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .padding(.horizontal, 10)
            .padding(.vertical, 9)
            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
    .frame(maxWidth: .infinity)
}
