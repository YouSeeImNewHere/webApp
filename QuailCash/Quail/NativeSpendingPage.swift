import SwiftUI
import Charts
import Combine

struct NativeSpendingPageView: View {
    @EnvironmentObject private var navigator: AppNavigator
    @StateObject private var model = SpendingPageViewModel()
    @State private var activeDay: SpendingDayModal?

    var body: some View {
        AppChromeFrame(
            title: "Spending",
            badgeValue: nil,
            selectedTab: .spending,
            showsBottomBar: true,
            onLeadingTap: { navigator.show(.settings) },
            onTrailingTap: { navigator.show(.notifications) },
            onSelectTab: selectTab
        ) {
            AppPageScroll(refreshAction: {
                await model.reload()
            }) {
                spendingChartCard
                categoriesCard
            }
        }
        .task { model.startIfNeeded() }
        .sheet(item: $activeDay) { modal in
            SpendingDaySheet(payload: modal.payload)
                .presentationDetents([.medium, .large])
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

    private var spendingChartCard: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(alignment: .center, spacing: 8) {
                Spacer(minLength: 0)
                Text(model.viewMode.title)
                    .font(.system(size: 16, weight: .bold, design: .rounded))
                Spacer(minLength: 0)
                Button("Next ▶") {
                    model.nextView()
                }
                .buttonStyle(SpendingSecondaryButtonStyle())
            }

            HStack(spacing: 6) {
                spendingMetricPill(title: model.metricTitle, value: model.metricValue)
                spendingMetricPill(title: model.secondaryMetricTitle, value: model.secondaryMetricValue, compact: true, valueColor: model.secondaryMetricColor)
            }

            HStack(spacing: 4) {
                spendingDateField(title: "Start", date: $model.startDate)
                Spacer(minLength: 10)
                spendingDateField(title: "End", date: $model.endDate)
                Spacer(minLength: 4)
                Button("Update") {
                    model.updateFromPickers()
                }
                .buttonStyle(SpendingPrimaryButtonStyle())
                .frame(height: 36)
            }

            HStack(spacing: 5) {
                ForEach(0..<4, id: \.self) { idx in
                    Button("Q\(idx + 1)") { model.setQuarter(idx + 1) }
                        .buttonStyle(SpendingChipButtonStyle())
                }

                Button("YTD") { model.setYTD() }
                    .buttonStyle(SpendingChipButtonStyle())

                Spacer(minLength: 12)

                HStack(spacing: 4) {
                    Button {
                        model.previousYear()
                    } label: {
                        Image(systemName: "arrow.left")
                    }
                    .buttonStyle(SpendingChipButtonStyle())

                    Text(String(model.selectedYear))
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)

                    Button {
                        model.nextYear()
                    } label: {
                        Image(systemName: "arrow.right")
                    }
                    .buttonStyle(SpendingChipButtonStyle())
                }
            }

            chartContainer

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 7) {
                    ForEach(Array(spendingMonthNames.enumerated()), id: \.offset) { idx, name in
                        Button(name) { model.setMonth(idx) }
                            .buttonStyle(SpendingChipButtonStyle())
                    }

                    Button("Annual") { model.setAnnual() }
                        .buttonStyle(SpendingChipButtonStyle())
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
    }

    @ViewBuilder
    private var chartContainer: some View {
        if model.isLoading {
            HStack {
                ProgressView()
                Text("Loading spending...")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, minHeight: 220, alignment: .center)
            .padding(10)
            .background(Color.black.opacity(0.02), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        } else if let error = model.errorMessage {
            VStack(spacing: 8) {
                Text(error)
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                Button("Retry") {
                    Task { await model.reload() }
                }
                .buttonStyle(SpendingSecondaryButtonStyle())
            }
            .frame(maxWidth: .infinity, minHeight: 220, alignment: .center)
            .padding(10)
            .background(Color.black.opacity(0.02), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        } else {
            GeometryReader { proxy in
                ZStack(alignment: .topLeading) {
                    currentChartBody
                        .frame(width: proxy.size.width, height: 224, alignment: .topLeading)
                        .clipped()
                        .padding(11)
                        .background(Color.black.opacity(0.02), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                }
            }
            .frame(height: 224)
        }
    }

    @ViewBuilder
    private var currentChartBody: some View {
        switch model.viewMode {
        case .spending:
            Chart(model.spendingPoints) { point in
                BarMark(
                    x: .value("Date", point.date),
                    y: .value("Value", point.value),
                    width: .fixed(model.barWidth)
                )
                .foregroundStyle(Color(red: 0.23, green: 0.51, blue: 0.96).opacity(0.82))
                .cornerRadius(4)
            }
            .chartXAxis(.hidden)
            .chartYAxis {
                AxisMarks(position: .leading) { _ in
                    AxisGridLine().foregroundStyle(.black.opacity(0.07))
                    AxisTick().foregroundStyle(.black.opacity(0.08))
                    AxisValueLabel()
                        .font(.system(size: 10, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
            .chartYScale(domain: model.spendingYDomain)
        case .categories:
            Chart(Array(model.categoryRows.enumerated()), id: \.element.id) { index, row in
                SectorMark(
                    angle: .value("Spent", max(row.total, 0)),
                    innerRadius: .ratio(0.52),
                    angularInset: 1
                )
                .foregroundStyle(spendingPalette[index % spendingPalette.count])
            }
            .chartLegend(position: .bottom, spacing: 10)
            .padding(8)
        case .unbudgetedSafe:
            Chart {
                ForEach(model.unbudgetedSafeSeries) { point in
                    BarMark(
                        x: .value("Date", point.dateValue),
                        y: .value("Amount", point.dailySafeToSpend),
                        width: .fixed(model.barWidth)
                    )
                    .foregroundStyle(Color.green.opacity(0.42))
                    .position(by: .value("Type", "Safe"))
                    .cornerRadius(4)

                    BarMark(
                        x: .value("Date", point.dateValue),
                        y: .value("Amount", point.unbudgetedSpend),
                        width: .fixed(model.barWidth)
                    )
                    .foregroundStyle(Color.red.opacity(0.72))
                    .position(by: .value("Type", "Unbudgeted"))
                    .cornerRadius(4)
                }

                if let selected = model.selectedUnbudgetedPoint {
                    RuleMark(x: .value("Selected", selected.dateValue))
                        .foregroundStyle(.black.opacity(0.18))
                }
            }
            .chartXAxis(.hidden)
            .chartYAxis {
                AxisMarks(position: .leading) { _ in
                    AxisGridLine().foregroundStyle(.black.opacity(0.07))
                    AxisTick().foregroundStyle(.black.opacity(0.08))
                    AxisValueLabel()
                        .font(.system(size: 10, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
            .chartOverlay { proxy in
                GeometryReader { geometry in
                    Rectangle()
                        .fill(.clear)
                        .contentShape(Rectangle())
                        .gesture(
                            DragGesture(minimumDistance: 0)
                                .onChanged { value in
                                    model.updateUnbudgetedSelection(location: value.location, proxy: proxy, geometry: geometry)
                                }
                                .onEnded { value in
                                    model.updateUnbudgetedSelection(location: value.location, proxy: proxy, geometry: geometry)
                                    if let day = model.selectedUnbudgetedPoint?.date {
                                        Task {
                                            if let payload = await model.loadDay(day) {
                                                activeDay = SpendingDayModal(payload: payload)
                                            }
                                        }
                                    }
                                }
                        )
                }
            }
        }
    }

    private var categoriesCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Spacer(minLength: 0)
                Text("Categories")
                    .font(.system(size: 17, weight: .semibold, design: .rounded))
                Spacer(minLength: 0)
            }

            if model.categoryRows.isEmpty {
                Text("No spending categories for this range.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            } else {
                VStack(spacing: 8) {
                    ForEach(model.categoryRows) { row in
                        Button {
                            navigator.show(.category(row.linkCategory))
                        } label: {
                            HStack(spacing: 10) {
                                Text(row.category)
                                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                                    .foregroundStyle(.primary)
                                    .multilineTextAlignment(.leading)
                                Spacer(minLength: 12)
                                Text(spendingMoney(row.total))
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
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
    }
}

private enum SpendingViewMode: Int, CaseIterable {
    case spending
    case categories
    case unbudgetedSafe

    var title: String {
        switch self {
        case .spending: return "Spending"
        case .categories: return "Spending • Categories"
        case .unbudgetedSafe: return "Unbudgeted vs Daily Safe"
        }
    }
}

private struct SpendingCategoryRow: Identifiable, Hashable {
    let category: String
    let total: Double
    let linkCategory: String
    var id: String { linkCategory + "::" + category }
}

private struct SpendingDayModal: Identifiable {
    let id = UUID()
    let payload: SpendingUnbudgetedDayPayload
}

private struct SpendingSafePoint: Identifiable, Hashable {
    let date: String
    let dateValue: Date
    let unbudgetedSpend: Double
    let dailySafeToSpend: Double
    var id: String { date }
}

@MainActor
private final class SpendingPageViewModel: ObservableObject {
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var startDate: Date
    @Published var endDate: Date
    @Published var selectedYear: Int
    @Published var viewMode: SpendingViewMode = .spending
    @Published var spendingSeries: [ChartSeriesPoint] = []
    @Published var categoryRows: [SpendingCategoryRow] = []
    @Published var unbudgetedSafeSeries: [SpendingSafePoint] = []
    @Published var selectedUnbudgetedPoint: SpendingSafePoint?

    private var didStart = false
    private let api = QuailAPI.shared

    init() {
        let calendar = Calendar.current
        let now = Date()
        let year = calendar.component(.year, from: now)
        selectedYear = year
        startDate = calendar.date(from: DateComponents(year: year, month: 1, day: 1)) ?? now
        endDate = now
    }

    func startIfNeeded() {
        guard !didStart else { return }
        didStart = true
        Task { await reload() }
    }

    func nextView() {
        let nextRaw = (viewMode.rawValue + 1) % SpendingViewMode.allCases.count
        viewMode = SpendingViewMode(rawValue: nextRaw) ?? .spending
        Task { await ensureActiveModeDataLoaded() }
    }

    func updateFromPickers() {
        let range = normalizedRange(start: startDate, end: endDate)
        startDate = range.start
        endDate = range.end
        selectedYear = Calendar.current.component(.year, from: startDate)
        Task { await reload() }
    }

    func setQuarter(_ quarter: Int) {
        let q = max(1, min(4, quarter))
        let startMonth = ((q - 1) * 3) + 1
        let start = Calendar.current.date(from: DateComponents(year: selectedYear, month: startMonth, day: 1)) ?? startDate
        let endMonth = startMonth + 2
        let lastDay = Calendar.current.range(of: .day, in: .month, for: Calendar.current.date(from: DateComponents(year: selectedYear, month: endMonth, day: 1)) ?? Date())?.count ?? 30
        let end = Calendar.current.date(from: DateComponents(year: selectedYear, month: endMonth, day: lastDay)) ?? endDate
        setRange(start: start, end: end)
    }

    func setMonth(_ monthIndex: Int) {
        let month = max(1, min(12, monthIndex + 1))
        let start = Calendar.current.date(from: DateComponents(year: selectedYear, month: month, day: 1)) ?? startDate
        let end = Calendar.current.date(byAdding: DateComponents(month: 1, day: -1), to: start) ?? endDate
        setRange(start: start, end: end)
    }

    func setAnnual() {
        let start = Calendar.current.date(from: DateComponents(year: selectedYear, month: 1, day: 1)) ?? startDate
        let end = Calendar.current.date(from: DateComponents(year: selectedYear, month: 12, day: 31)) ?? endDate
        setRange(start: start, end: end)
    }

    func setYTD() {
        let now = Date()
        let start = Calendar.current.date(from: DateComponents(year: selectedYear, month: 1, day: 1)) ?? startDate
        let end: Date
        if selectedYear == Calendar.current.component(.year, from: now) {
            end = now
        } else {
            end = Calendar.current.date(from: DateComponents(year: selectedYear, month: 12, day: 31)) ?? endDate
        }
        setRange(start: start, end: end)
    }

    func previousYear() {
        setYear(selectedYear - 1)
    }

    func nextYear() {
        setYear(selectedYear + 1)
    }

    func setYear(_ year: Int) {
        let currentYear = Calendar.current.component(.year, from: Date())
        selectedYear = min(year, currentYear)
        setYTD()
    }

    func reload() async {
        isLoading = true
        defer { isLoading = false }
        errorMessage = nil
        selectedUnbudgetedPoint = nil
        do {
            let start = Self.isoDate(startDate)
            let end = Self.isoDate(endDate)
            async let spending = api.fetchSpendingSeries(start: start, end: end)
            async let categories = api.fetchSpendingCategoryTotals(start: start, end: end)
            async let unknown = api.fetchUnknownMerchantRange(start: start, end: end)
            let (spendingRes, categoryRes, unknownRes) = try await (spending, categories, unknown)
            spendingSeries = spendingRes
            categoryRows = Self.buildCategoryRows(categories: categoryRes, unknown: unknownRes)
            if viewMode == .unbudgetedSafe {
                try await loadUnbudgetedSafeRange(start: start, end: end)
            } else {
                unbudgetedSafeSeries = []
            }
        } catch is CancellationError {
            return
        } catch QuailAPIError.unauthorized {
            errorMessage = "Sign in to load spending."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadDay(_ day: String) async -> SpendingUnbudgetedDayPayload? {
        do {
            return try await api.fetchSpendingUnbudgetedDay(day: day)
        } catch {
            return nil
        }
    }

    func updateUnbudgetedSelection(location: CGPoint, proxy: ChartProxy, geometry: GeometryProxy) {
        guard !unbudgetedSafeSeries.isEmpty else {
            selectedUnbudgetedPoint = nil
            return
        }
        guard let plotFrameAnchor = proxy.plotFrame else {
            selectedUnbudgetedPoint = nil
            return
        }
        let plotFrame = geometry[plotFrameAnchor]
        let xOffset = location.x - plotFrame.origin.x
        guard let date: Date = proxy.value(atX: xOffset) else {
            selectedUnbudgetedPoint = nil
            return
        }
        selectedUnbudgetedPoint = unbudgetedSafeSeries.min(by: {
            abs($0.dateValue.timeIntervalSince(date)) < abs($1.dateValue.timeIntervalSince(date))
        })
    }

    var metricTitle: String {
        switch viewMode {
        case .spending, .categories:
            return "Total"
        case .unbudgetedSafe:
            return "Unbudgeted total"
        }
    }

    var metricValue: String {
        switch viewMode {
        case .spending:
            return spendingMoney(spendingSeries.reduce(0) { $0 + $1.value })
        case .categories:
            return spendingMoney(categoryRows.reduce(0) { $0 + $1.total })
        case .unbudgetedSafe:
            return spendingMoney(unbudgetedSafeSeries.reduce(0) { $0 + $1.unbudgetedSpend })
        }
    }

    var secondaryMetricTitle: String {
        switch viewMode {
        case .spending:
            return "% Growth"
        case .categories:
            return "Top"
        case .unbudgetedSafe:
            return "Latest safe/day"
        }
    }

    var secondaryMetricValue: String {
        switch viewMode {
        case .spending:
            return spendingGrowthDisplayText
        case .categories:
            return topCategoryDisplayText
        case .unbudgetedSafe:
            return spendingMoney(unbudgetedSafeSeries.last?.dailySafeToSpend ?? 0)
        }
    }

    var secondaryMetricColor: Color {
        switch viewMode {
        case .spending:
            return spendingGrowthColor
        case .categories, .unbudgetedSafe:
            return .primary
        }
    }

    var spendingPoints: [SpendingBarPoint] {
        spendingSeries.compactMap { point in
            guard let date = Self.parseDate(point.date) else { return nil }
            return SpendingBarPoint(date: date, value: point.value)
        }
    }

    var barWidth: CGFloat {
        let count = max(spendingPoints.count, unbudgetedSafeSeries.count)
        switch count {
        case 0...10: return 18
        case 11...20: return 14
        case 21...40: return 10
        case 41...80: return 6
        default: return 4
        }
    }

    var spendingYDomain: ClosedRange<Double> {
        let values = spendingPoints.map(\.value)
        guard let maxValue = values.max() else { return 0...1 }
        return 0...max(1, maxValue * 1.15)
    }

    private var spendingGrowthDisplayText: String {
        let pct = Self.multiMonthGrowth(from: spendingSeries)
        guard let pct else { return "—" }
        return String(format: "%.1f%%", abs(pct))
    }

    private var spendingGrowthColor: Color {
        guard let pct = Self.multiMonthGrowth(from: spendingSeries) else { return .primary }
        return pct >= 0 ? .red : .green
    }

    private var topCategoryDisplayText: String {
        let total = categoryRows.reduce(0) { $0 + $1.total }
        guard let top = categoryRows.first, total > 0 else { return "—" }
        let pct = (top.total / total) * 100.0
        return "\(top.category) \(String(format: "%.1f%%", pct))"
    }

    private func setRange(start: Date, end: Date) {
        let range = normalizedRange(start: start, end: end)
        startDate = range.start
        endDate = range.end
        selectedYear = Calendar.current.component(.year, from: range.start)
        Task { await reload() }
    }

    private func ensureActiveModeDataLoaded() async {
        guard viewMode == .unbudgetedSafe else { return }
        guard unbudgetedSafeSeries.isEmpty else { return }
        do {
            try await loadUnbudgetedSafeRange(start: Self.isoDate(startDate), end: Self.isoDate(endDate))
        } catch is CancellationError {
            return
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func loadUnbudgetedSafeRange(start: String, end: String) async throws {
        let safeRes = try await api.fetchSpendingUnbudgetedSafeRange(start: start, end: end)
        unbudgetedSafeSeries = safeRes.series.compactMap { Self.mapSafePoint($0) }
    }

    private func normalizedRange(start: Date, end: Date) -> (start: Date, end: Date) {
        let cal = Calendar.current
        let s = cal.startOfDay(for: start)
        let e = cal.startOfDay(for: max(start, end))
        return (s, e)
    }

    private static func buildCategoryRows(categories: [SpendingCategoryTotalPayload], unknown: UnknownMerchantRangePayload) -> [SpendingCategoryRow] {
        var rows = categories.map { SpendingCategoryRow(category: $0.category, total: max(0, $0.total), linkCategory: $0.category) }
        if unknown.total > 0, unknown.txCount > 0 {
            rows.append(SpendingCategoryRow(category: "Unknown merchant (\(unknown.txCount))", total: unknown.total, linkCategory: "Unknown merchant"))
        }
        return rows.sorted { $0.total > $1.total }
    }

    private static func parseDate(_ iso: String) -> Date? {
        let df = DateFormatter()
        df.locale = Locale(identifier: "en_US_POSIX")
        df.timeZone = TimeZone(secondsFromGMT: 0)
        df.dateFormat = "yyyy-MM-dd"
        return df.date(from: iso)
    }

    private static func mapSafePoint(_ point: SpendingUnbudgetedSafePoint) -> SpendingSafePoint? {
        guard let date = parseDate(point.date) else { return nil }
        return SpendingSafePoint(date: point.date, dateValue: date, unbudgetedSpend: point.unbudgetedSpend, dailySafeToSpend: point.dailySafeToSpend)
    }

    private static func isoDate(_ date: Date) -> String {
        let cal = Calendar.current
        let y = cal.component(.year, from: date)
        let m = cal.component(.month, from: date)
        let d = cal.component(.day, from: date)
        return String(format: "%04d-%02d-%02d", y, m, d)
    }

    private static func multiMonthGrowth(from series: [ChartSeriesPoint]) -> Double? {
        var monthTotals: [String: Double] = [:]
        for point in series {
            guard point.date.count >= 7 else { continue }
            let key = String(point.date.prefix(7))
            monthTotals[key, default: 0] += point.value
        }
        let keys = monthTotals.keys.sorted()
        guard keys.count >= 2, let first = monthTotals[keys.first!], let last = monthTotals[keys.last!], abs(first) > 1e-9 else {
            return nil
        }
        return ((last - first) / abs(first)) * 100.0
    }
}

private struct SpendingBarPoint: Identifiable {
    let id = UUID()
    let date: Date
    let value: Double
}

private struct SpendingDaySheet: View {
    let payload: SpendingUnbudgetedDayPayload

    var body: some View {
        NavigationStack {
            ScrollView(showsIndicators: false) {
                VStack(alignment: .leading, spacing: 14) {
                    HStack(spacing: 10) {
                        spendingDayChip("Unbudgeted", spendingMoney(payload.totals.unbudgetedSpend))
                        spendingDayChip("Safe/day", spendingMoney(payload.totals.dailySafeToSpend))
                    }

                    VStack(spacing: 10) {
                        ForEach(payload.purchases) { purchase in
                            HStack(alignment: .top, spacing: 10) {
                                Circle()
                                    .fill(purchase.kind == "roundup" ? Color.orange.opacity(0.22) : Color.black.opacity(0.08))
                                    .frame(width: 34, height: 34)
                                    .overlay(
                                        Image(systemName: purchase.kind == "roundup" ? "arrow.up.right.circle.fill" : "cart.fill")
                                            .font(.system(size: 13, weight: .semibold))
                                            .foregroundStyle(.primary)
                                    )

                                VStack(alignment: .leading, spacing: 3) {
                                    Text(purchase.merchant)
                                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                                    Text("\(purchase.category) • \(purchase.bank) / \(purchase.account)")
                                        .font(.system(size: 11, weight: .medium, design: .rounded))
                                        .foregroundStyle(.secondary)
                                }

                                Spacer(minLength: 12)

                                Text(spendingMoney(purchase.amount))
                                    .font(.system(size: 14, weight: .bold, design: .rounded))
                                    .foregroundStyle(.primary)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 12)
                            .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Color.black.opacity(0.05), lineWidth: 1))
                        }
                    }
                }
                .padding(16)
            }
            .navigationTitle(spendingMediumDate(payload.day))
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private func spendingDayChip(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 10, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 13, weight: .bold, design: .rounded))
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Color.black.opacity(0.05), lineWidth: 1))
    }
}

private struct SpendingPrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .semibold, design: .rounded))
            .foregroundStyle(.white)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(Color.black.opacity(configuration.isPressed ? 0.78 : 1.0), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

private struct SpendingSecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .semibold, design: .rounded))
            .foregroundStyle(.primary)
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(Color.black.opacity(configuration.isPressed ? 0.06 : 0.04), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(.black.opacity(0.08), lineWidth: 1))
    }
}

private struct SpendingChipButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 11, weight: .semibold, design: .rounded))
            .foregroundStyle(.primary)
            .padding(.horizontal, 9)
            .padding(.vertical, 6)
            .background(Capsule(style: .continuous).fill(Color.black.opacity(configuration.isPressed ? 0.06 : 0.04)))
            .overlay(Capsule(style: .continuous).stroke(.black.opacity(0.08), lineWidth: 1))
    }
}

private func spendingDateField(title: String, date: Binding<Date>) -> some View {
    VStack(spacing: 4) {
        Text(title)
            .font(.system(size: 10, weight: .semibold, design: .rounded))
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .center)
        DatePicker("", selection: date, displayedComponents: .date)
            .labelsHidden()
            .datePickerStyle(.compact)
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 8)
            .frame(height: 36)
            .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
    }
    .frame(maxWidth: .infinity)
}

private func spendingMetricPill(title: String, value: String, compact: Bool = false, valueColor: Color = .primary) -> some View {
    VStack(alignment: .leading, spacing: 4) {
        Text(title)
            .font(.system(size: 10, weight: .semibold, design: .rounded))
            .foregroundStyle(.secondary)
        Text(value)
            .font(.system(size: compact ? 13 : 14, weight: .bold, design: .rounded))
            .foregroundStyle(valueColor)
            .lineLimit(1)
            .minimumScaleFactor(0.8)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(.horizontal, 12)
    .padding(.vertical, 10)
    .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(.black.opacity(0.05), lineWidth: 1))
}

private let spendingPalette: [Color] = [
    Color(red: 0.91, green: 0.30, blue: 0.24),
    Color(red: 0.56, green: 0.27, blue: 0.68),
    Color(red: 0.95, green: 0.61, blue: 0.07),
    Color(red: 0.91, green: 0.12, blue: 0.39),
    Color(red: 0.18, green: 0.80, blue: 0.44),
    Color(red: 0.20, green: 0.60, blue: 0.86),
    Color(red: 0.10, green: 0.74, blue: 0.61),
    Color(red: 0.83, green: 0.33, blue: 0.00),
]

private let spendingMonthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

private func spendingMoney(_ value: Double) -> String {
    let formatter = NumberFormatter()
    formatter.numberStyle = .currency
    formatter.currencyCode = "USD"
    formatter.minimumFractionDigits = 2
    formatter.maximumFractionDigits = 2
    return formatter.string(from: NSNumber(value: value)) ?? String(format: "$%.2f", value)
}

private func spendingMediumDate(_ iso: String) -> String {
    let df = DateFormatter()
    df.locale = Locale(identifier: "en_US_POSIX")
    df.timeZone = TimeZone(secondsFromGMT: 0)
    df.dateFormat = "yyyy-MM-dd"
    guard let date = df.date(from: iso) else { return iso }
    let out = DateFormatter()
    out.locale = Locale(identifier: "en_US_POSIX")
    out.dateFormat = "MMM d"
    return out.string(from: date)
}
