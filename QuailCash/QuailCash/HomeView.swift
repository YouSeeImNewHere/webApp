import SwiftUI
import WebKit
import Combine
import Charts
import UniformTypeIdentifiers

struct HomeView: View {
    @EnvironmentObject private var navigator: AppNavigator
    @StateObject private var model = HomeViewModel()
    @State private var activePopup: HomePopup?
    @State private var activeSheet: HomeSheet?

    var body: some View {
        AppChromeFrame(
            title: "Home",
            badgeValue: notificationBadgeValue,
            selectedTab: navigator.currentTab,
            onLeadingTap: { navigate(.settings) },
            onTrailingTap: { navigate(.notifications) },
            onSelectTab: selectTab
        ) {
            AppPageScroll(contentPadding: 12, refreshAction: {
                await model.reload()
            }) {
                    chartSection

                    if let home = model.home {
                        monthlySnapshotCard(
                            home: home,
                            extraSaved: model.extraSaved,
                            onBudget: { navigate(.budget) },
                            onIncome: { activePopup = .incomeBreakdown },
                            onSpent: { activePopup = .spentBreakdown },
                            onExtraSaved: { activePopup = .extraSavedBreakdown },
                            onRecalc: { Task { await model.recalculateDailySnapshot() } }
                        )
                        monthlySpendingCard(
                            home: home,
                            onCategory: { navigate(.category($0)) },
                            onUnassigned: { activeSheet = .unassigned }
                        )
                        bankTotalsCard(home: home,
                                       onImport: { activeSheet = .csvImport },
                                       onBankInfo: { activeSheet = .bankInfo },
                                       onOpenAccount: { account in navigate(.account(account, audit: false)) },
                                       onVerifyAccount: { account in activePopup = .verifyAccount(account) },
                                       onAuditAccount: { account in navigate(.account(account, audit: true)) })
                        upcomingTransactionsSection
                        recentTransactions(home: home) { tx in
                            activeSheet = .transaction(tx)
                        }
                    } else {
                        loadingBlock
                    }
                }
        }
        .onAppear {
            print("[QuailCash] HomeView appeared")
            model.startIfNeeded()
        }
        .sheet(isPresented: $model.showAuthSheet) {
            AuthSessionView(
                startURL: AppConfig.mobileAuthStartURL(),
                callbackScheme: AppConfig.callbackScheme,
                onAuthenticated: {
                    print("[QuailCash] Auth sheet reported authenticated")
                    model.finishAuthentication()
                },
                onCancel: {
                    print("[QuailCash] Auth sheet cancelled")
                    model.cancelAuthentication()
                }
            )
        }
        .sheet(item: $activeSheet) { sheet in
            HomeSheetHost(
                sheet: sheet,
                onDismiss: { activeSheet = nil },
                onRefresh: { Task { await model.reload() } }
            )
            .presentationDetents(sheet.detents)
            .presentationDragIndicator(.visible)
        }
        .overlay {
            if let popup = activePopup {
                HomePopupOverlay(
                    popup: popup,
                    onDismiss: { activePopup = nil },
                    onRefresh: { Task { await model.reload() } }
                )
            }
        }
        .onChange(of: model.showAuthSheet) { _, isShowing in
            if isShowing {
                print("[QuailCash] Presenting auth sheet")
            }
        }
    }

    private var notificationBadgeValue: Int? {
        model.home?.notificationsUnread
    }

    private func navigate(_ route: AppRoute) {
        navigator.show(route)
    }

    private func selectTab(_ tab: BottomTab) {
        switch tab {
        case .home:
            navigator.popToRoot()
        case .spending:
            navigator.show(AppRoute.spending)
        case .all:
            navigator.show(AppRoute.allTransactions)
        case .analytics:
            navigator.show(AppRoute.analytics)
        case .recurring:
            navigator.show(AppRoute.recurring)
        }
    }

    private var loadingBlock: some View {
        VStack(spacing: 14) {
            Text("Backend: \(AppConfig.apiBaseURL.absoluteString)")
                .font(.footnote)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            if model.isLoading {
                ProgressView()
                    .scaleEffect(1.15)
                Text("Loading real data...")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            } else if let error = model.errorMessage {
                Text(error)
                    .font(.callout)
                    .foregroundStyle(.red)
                    .multilineTextAlignment(.center)
            } else {
                Text("Waiting for data.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }

            if model.needsAuthentication {
                Button {
                    model.showAuthSheet = true
                } label: {
                    Text("Sign in")
                        .font(.system(size: 15, weight: .semibold, design: .rounded))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 13)
                }
                .buttonStyle(PrimaryButtonStyle())
            } else if model.errorMessage != nil {
                Button {
                    Task { await model.reload() }
                } label: {
                    Text("Retry")
                        .font(.system(size: 15, weight: .semibold, design: .rounded))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 13)
                }
                .buttonStyle(PrimaryButtonStyle())
            }
        }
        .frame(maxWidth: .infinity)
        .padding(14)
        .background(.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
    }

    private var statusCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Status")
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .textCase(.uppercase)

            Text(model.statusText)
                .font(.system(size: 16, weight: .semibold, design: .rounded))
                .foregroundStyle(.primary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
    }

    private var chartSection: some View {
        AnalyticsChartSection()
    }

    private func monthlySnapshotCard(
        home: HomePayload,
        extraSaved: Double?,
        onBudget: @escaping () -> Void,
        onIncome: @escaping () -> Void,
        onSpent: @escaping () -> Void,
        onExtraSaved: @escaping () -> Void,
        onRecalc: @escaping () -> Void
    ) -> some View {
        MonthlySnapshotCard(
            monthBudget: home.monthBudget,
            dayLimit: home.dayLimit,
            extraSaved: extraSaved,
            onBudget: onBudget,
            onIncome: onIncome,
            onSpent: onSpent,
            onExtraSaved: onExtraSaved,
            onRecalc: onRecalc
        )
    }

    private func monthlySpendingCard(
        home: HomePayload,
        onCategory: @escaping (String) -> Void,
        onUnassigned: @escaping () -> Void
    ) -> some View {
        MonthlySpendingCard(
            totals: home.categoryTotalsMonth?.categories ?? [],
            unknownMerchantTotal: home.unknownMerchantTotalMonth,
            unassignedAllTime: home.categoryTotalsMonth?.unassignedAllTime,
            onCategory: onCategory,
            onUnknownMerchants: { onCategory("Unknown merchants") },
            onUnassigned: onUnassigned
        )
    }

    private func metricTile(title: String, value: String, subtitle: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title.uppercased())
                .font(.system(size: 10, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .tracking(0.6)
            Text(value)
                .font(.system(size: 20, weight: .bold, design: .rounded))
                .foregroundStyle(.primary)
                .lineLimit(1)
            Text(subtitle)
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
    }

    private func metricTile(title: String, value: Double, subtitle: String) -> some View {
        metricTile(
            title: title,
            value: moneyValue(value),
            subtitle: subtitle
        )
    }

    private func bankTotalsCard(
        home: HomePayload,
        onImport: @escaping () -> Void,
        onBankInfo: @escaping () -> Void,
        onOpenAccount: @escaping (BankAccountPayload) -> Void,
        onVerifyAccount: @escaping (BankAccountPayload) -> Void,
        onAuditAccount: @escaping (BankAccountPayload) -> Void
    ) -> some View {
        BankTotalsAccordionCard(
            bankTotals: home.bankTotals,
            onImport: onImport,
            onBankInfo: onBankInfo,
            onOpenAccount: onOpenAccount,
            onVerifyAccount: onVerifyAccount,
            onAuditAccount: onAuditAccount
        )
    }

    private func recentTransactions(home: HomePayload, onTapTransaction: @escaping (TransactionItem) -> Void) -> some View {
        RecentTransactionsCard(transactions: Array(home.transactions.prefix(8)), onTapTransaction: onTapTransaction)
    }

    private var upcomingTransactionsSection: some View {
        UpcomingTransactionsCard(
            events: model.upcomingEvents,
            isLoading: model.upcomingLoading,
            errorMessage: model.upcomingError
        ) { group in
            activeSheet = .upcomingDay(group)
        }
    }
}

private struct RecentTransactionsCard: View {
    let transactions: [TransactionItem]
    let onTapTransaction: (TransactionItem) -> Void
    @State private var isExpanded = true

    var body: some View {
        VStack(alignment: .leading, spacing: isExpanded ? 12 : 0) {
            HStack {
                Spacer(minLength: 0)
                Text("Recent transactions")
                    .font(.system(size: 17, weight: .semibold, design: .rounded))
                Spacer(minLength: 0)
                Image(systemName: "chevron.down")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .rotationEffect(.degrees(isExpanded ? 180 : 0))
            }
            .contentShape(Rectangle())
            .onTapGesture {
                withAnimation(.spring(response: 0.28, dampingFraction: 0.9)) {
                    isExpanded.toggle()
                }
            }

            if isExpanded {
                VStack(spacing: 10) {
                    ForEach(transactions) { tx in
                        TransactionRow(tx: tx)
                            .onTapGesture {
                                onTapTransaction(tx)
                            }
                    }
                }
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
    }
}

private struct MonthlySnapshotCard: View {
    let monthBudget: MonthBudgetPayload?
    let dayLimit: DayLimitPayload?
    let extraSaved: Double?
    let onBudget: () -> Void
    let onIncome: () -> Void
    let onSpent: () -> Void
    let onExtraSaved: () -> Void
    let onRecalc: () -> Void
    @State private var isExpanded = true

    var body: some View {
        VStack(alignment: .leading, spacing: isExpanded ? 12 : 0) {
            HStack(alignment: .center, spacing: 8) {
                Color.clear
                    .frame(width: 40, height: 1)

                Spacer(minLength: 0)

                Text("This month")
                    .font(.system(size: 17, weight: .semibold, design: .rounded))
                    .frame(maxWidth: .infinity)

                Spacer(minLength: 0)

                HStack(spacing: 8) {
                    Button {
                        onBudget()
                    } label: {
                        Image(systemName: "chart.bar.fill")
                            .font(.system(size: 15, weight: .semibold))
                            .frame(width: 32, height: 32)
                            .background(Color.black.opacity(0.04), in: Circle())
                    }
                    .buttonStyle(.plain)

                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(.secondary)
                        .frame(width: 12)
                }
                .frame(width: 40, alignment: .trailing)
            }
            .contentShape(Rectangle())

            if isExpanded {
                HStack(alignment: .top, spacing: 12) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Safe to spend")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                        Text(moneyValue(monthBudget?.safeToSpend ?? 0))
                            .font(.system(size: 28, weight: .bold, design: .rounded))
                            .foregroundStyle((monthBudget?.safeToSpend ?? 0) < 0 ? .red : .primary)
                            .lineLimit(1)
                        Text(monthMeta)
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }

                    Spacer(minLength: 8)

                    VStack(alignment: .leading, spacing: 6) {
                        Text("Today left")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            Text(moneyValue(dayLimit?.remainingToday ?? monthBudget?.dailyLimit ?? 0))
                                .font(.system(size: 22, weight: .bold, design: .rounded))
                                .foregroundStyle(.primary)
                                .lineLimit(1)
                            Button("Recalc") {
                                onRecalc()
                            }
                            .font(.system(size: 11, weight: .semibold, design: .rounded))
                            .buttonStyle(SecondarySmallButtonStyle())
                        }
                        Text(dayMeta)
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }
                }

                VStack(spacing: 8) {
                    monthRow(
                        label: "Income",
                        value: monthBudget?.expectedIncome ?? 0,
                        tappable: true,
                        action: onIncome
                    )
                    monthRow(
                        label: "Spent so far",
                        value: monthBudget?.spentSoFar ?? 0,
                        tappable: true,
                        action: onSpent
                    )
                    monthRow(
                        label: "Remaining bills",
                        value: monthBudget?.billsRemaining ?? 0,
                        tappable: false,
                        action: nil
                    )
                    monthRow(
                        label: "Extra saved",
                        value: extraSaved ?? 0,
                        tappable: true,
                        action: onExtraSaved
                    )
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(.white, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
        .contentShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .onTapGesture {
            withAnimation(.snappy) {
                isExpanded.toggle()
            }
        }
    }

    private var monthMeta: String {
        guard let asOf = monthBudget?.asOf else { return "" }
        let date = formattedDate(asOf)
        let days = monthBudget?.daysLeft ?? 0
        if date.isEmpty { return "\(days) days left" }
        return "\(date)\n\(days) days left"
    }

    private var dayMeta: String {
        let baseline = dayLimit?.baseline ?? monthBudget?.dailyLimit ?? 0
        let spentToday = dayLimit?.spentTodayFree ?? 0
        return "Baseline: \(moneyValue(baseline))\nSpent Today: \(moneyValue(spentToday))"
    }

    private func formattedDate(_ raw: String) -> String {
        let parts = raw.split(separator: "-")
        guard parts.count == 3,
              let year = Int(parts[0]),
              let month = Int(parts[1]),
              let day = Int(parts[2]) else { return "" }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "dd-MMM"
        let date = Calendar(identifier: .gregorian).date(from: DateComponents(year: year, month: month, day: day))
        return date.map { formatter.string(from: $0) } ?? ""
    }

    private func monthRow(label: String, value: Double, tappable: Bool, action: (() -> Void)?) -> AnyView {
        let row = HStack(spacing: 10) {
            Text(label)
                .font(.system(size: 14, weight: .semibold, design: .rounded))
                .foregroundStyle(.primary)
            Spacer(minLength: 12)
            Text(moneyValue(value))
                .font(.system(size: 14, weight: .semibold, design: .rounded))
                .foregroundStyle(.primary)
            if tappable {
                Image(systemName: "chevron.right")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 12)
        .background(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(Color.black.opacity(0.03))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Color.black.opacity(0.05), lineWidth: 1)
        )
        .opacity(tappable ? 1.0 : 0.96)

        if tappable, let action {
            return AnyView(
                Button(action: action) {
                    row
                }
                .buttonStyle(.plain)
            )
        } else {
            return AnyView(row)
        }
    }
}

private struct UpcomingDayGroup: Identifiable, Hashable {
    let id: String
    let date: String
    let weekday: String
    let shortDate: String
    let items: [UpcomingEventPayload]
}

private struct UpcomingTransactionsCard: View {
    let events: [UpcomingEventPayload]
    let isLoading: Bool
    let errorMessage: String?
    let onOpenDay: (UpcomingDayGroup) -> Void
    @State private var isExpanded = true

    var body: some View {
        VStack(alignment: .leading, spacing: isExpanded ? 12 : 0) {
            HStack {
                Spacer(minLength: 0)
                Text("Upcoming transactions")
                    .font(.system(size: 17, weight: .semibold, design: .rounded))
                Spacer(minLength: 0)
                Image(systemName: "chevron.down")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .rotationEffect(.degrees(isExpanded ? 180 : 0))
            }
            .contentShape(Rectangle())
            .onTapGesture {
                withAnimation(.spring(response: 0.28, dampingFraction: 0.9)) {
                    isExpanded.toggle()
                }
            }

            if isExpanded {
                if isLoading {
                    ProgressView()
                        .frame(maxWidth: .infinity, minHeight: 78, alignment: .center)
                } else if let errorMessage, !errorMessage.isEmpty {
                    Text(errorMessage)
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                } else {
                    let groups = groupedDays
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 10) {
                            ForEach(groups) { group in
                                Button {
                                    onOpenDay(group)
                                } label: {
                                    VStack(alignment: .leading, spacing: 8) {
                                        HStack {
                                            Text(group.weekday)
                                                .font(.system(size: 14, weight: .bold, design: .rounded))
                                            Spacer(minLength: 10)
                                            Text(group.shortDate)
                                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                                .foregroundStyle(.secondary)
                                        }

                                        if group.items.isEmpty {
                                            Text("—")
                                                .font(.system(size: 13, weight: .medium, design: .rounded))
                                                .foregroundStyle(.secondary)
                                        } else {
                                            let summaries = categorySummaries(for: group.items)
                                            ForEach(Array(summaries.prefix(2)), id: \.label) { summary in
                                                HStack(spacing: 8) {
                                                    Text(summary.label)
                                                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                                                        .foregroundStyle(.primary)
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
                                    .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                                    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Color.black.opacity(0.05), lineWidth: 1))
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
    }

    private var groupedDays: [UpcomingDayGroup] {
        let grouped = Dictionary(grouping: events, by: { $0.date })
        return grouped.keys.sorted().map { key in
            let date = homeDateFromISO(key) ?? Date()
            let items = (grouped[key] ?? []).sorted {
                let lhsIncome = isIncome($0)
                let rhsIncome = isIncome($1)
                if lhsIncome != rhsIncome { return lhsIncome && !rhsIncome }
                return abs($0.amount ?? 0) > abs($1.amount ?? 0)
            }
            return UpcomingDayGroup(
                id: key,
                date: key,
                weekday: homeWeekdayShort(date),
                shortDate: homeMonthDayShort(date),
                items: items
            )
        }
    }

    private func categorySummaries(for items: [UpcomingEventPayload]) -> [(label: String, amount: String, color: Color)] {
        let grouped = Dictionary(grouping: items, by: { categoryLabel(for: $0) })
        let summaries: [CategorySummary] = grouped.map { key, values in
            let total = values.reduce(0.0) { $0 + abs($1.amount ?? 0) }
            let income = values.contains(where: isIncome)
            return CategorySummary(
                label: key,
                amount: "\(income ? "+" : "-")\(moneyValue(total))",
                color: income ? Color.green : Color.red,
                total: total
            )
        }
        return summaries
            .sorted { lhs, rhs in lhs.total > rhs.total }
            .map { ($0.label, $0.amount, $0.color) }
    }

    private func categoryLabel(for event: UpcomingEventPayload) -> String {
        if let category = event.category?.trimmingCharacters(in: .whitespacesAndNewlines), !category.isEmpty {
            return category
        }
        if let type = event.type?.trimmingCharacters(in: .whitespacesAndNewlines), !type.isEmpty {
            return type.capitalized
        }
        return "Unassigned"
    }

    private func isIncome(_ event: UpcomingEventPayload) -> Bool {
        let type = (event.type ?? "").lowercased()
        let cadence = (event.cadence ?? "").lowercased()
        return type == "income" || cadence == "paycheck" || cadence == "interest"
    }
}

private struct MonthlySpendingCard: View {
    let totals: [CategoryTotalItem]
    let unknownMerchantTotal: UnknownMerchantTotalMonth?
    let unassignedAllTime: Int?
    let onCategory: (String) -> Void
    let onUnknownMerchants: () -> Void
    let onUnassigned: () -> Void
    @State private var isExpanded = true

    var body: some View {
        VStack(alignment: .leading, spacing: isExpanded ? 12 : 0) {
            HStack {
                Spacer(minLength: 0)
                Text("Monthly Spending")
                    .font(.system(size: 17, weight: .semibold, design: .rounded))
                Spacer(minLength: 0)
                Image(systemName: "chevron.down")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .rotationEffect(.degrees(isExpanded ? 180 : 0))
            }
            .contentShape(Rectangle())
            .onTapGesture {
                withAnimation(.spring(response: 0.28, dampingFraction: 0.9)) {
                    isExpanded.toggle()
                }
            }

            if isExpanded {
                VStack(spacing: 8) {
                    if totals.isEmpty {
                        Text("No spending yet this month.")
                            .font(.system(size: 13, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.vertical, 6)
                    } else {
                        ForEach(totals, id: \.self) { item in
                            categoryRow(
                                name: item.category ?? "Unknown",
                                count: item.count,
                                amount: item.total ?? item.amount ?? 0,
                                action: { onCategory(item.category ?? "Unknown") }
                            )
                        }
                    }

                    if let unknownMerchantTotal, unknownMerchantTotal.total > 0, unknownMerchantTotal.txCount > 0 {
                        categoryRow(
                            name: "Unknown merchants",
                            count: unknownMerchantTotal.txCount,
                            amount: unknownMerchantTotal.total,
                            action: onUnknownMerchants
                        )
                    }

                    if let unassignedAllTime {
                        Button(action: onUnassigned) {
                            HStack(spacing: 8) {
                                Text("Unassigned")
                                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                                Spacer(minLength: 8)
                                Text("+ Rule")
                                    .font(.system(size: 12, weight: .bold, design: .rounded))
                                    .foregroundStyle(.secondary)
                                Text("\(unassignedAllTime)")
                                    .font(.system(size: 11, weight: .bold, design: .rounded))
                                    .frame(minWidth: 22, minHeight: 22)
                                    .background(Color.black.opacity(0.06), in: Capsule())
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 12)
                            .background(
                                RoundedRectangle(cornerRadius: 14, style: .continuous)
                                    .fill(Color.black.opacity(0.03))
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 14, style: .continuous)
                                    .stroke(Color.black.opacity(0.05), lineWidth: 1)
                            )
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

private func categoryRow(name: String, count: Int?, amount: Double, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Text(name)
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                if let count, count > 0 {
                    Text("\(count)")
                        .font(.system(size: 11, weight: .bold, design: .rounded))
                        .foregroundStyle(.primary)
                        .frame(minWidth: 22, minHeight: 22)
                        .background(Color.black.opacity(0.06), in: Capsule())
                }
                Spacer(minLength: 8)
                Text(moneyValue(amount))
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                    .foregroundStyle(.primary)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Color.black.opacity(0.03))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(Color.black.opacity(0.05), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
}
}

enum ChartMode: String, CaseIterable, Identifiable {
    case netWorth
    case savings
    case investments
    case spending

    var id: String { rawValue }

    var title: String {
        switch self {
        case .netWorth: return "Net Worth"
        case .savings: return "Savings"
        case .investments: return "Investments"
        case .spending: return "Spending"
        }
    }

    var endpoint: String {
        switch self {
        case .netWorth: return "/net-worth"
        case .savings: return "/savings"
        case .investments: return "/investments"
        case .spending: return "/spending"
        }
    }

    var tint: Color {
        switch self {
        case .netWorth: return .blue
        case .savings: return .green
        case .investments: return .purple
        case .spending: return .orange
        }
    }

    var subtitle: String {
        switch self {
        case .netWorth: return "All accounts"
        case .savings: return "Savings balances"
        case .investments: return "Investment balances"
        case .spending: return "Spending total"
        }
    }
}

@MainActor
final class ChartViewModel: ObservableObject {
    @Published var selectedMode: ChartMode = .netWorth
    @Published var selectedYear: Int = Calendar.current.component(.year, from: Date())
    @Published var startDate: Date = Calendar.current.date(from: DateComponents(year: Calendar.current.component(.year, from: Date()), month: 1, day: 1)) ?? Date()
    @Published var endDate: Date = Date()
    @Published var points: [ChartPoint] = []
    @Published var selectedPoint: ChartPoint?
    @Published var tooltipExpanded = true
    @Published var projectedGrowthEnabled = false
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let api = QuailCashAPI.shared
    private var didStart = false

    func startIfNeeded() {
        guard !didStart else { return }
        didStart = true
        resetToCurrentYear()
        Task { await reload() }
    }

    func select(_ mode: ChartMode) {
        guard selectedMode != mode else { return }
        selectedMode = mode
        Task { await reload() }
    }

    func nextMode() {
        let modes = ChartMode.allCases
        guard let idx = modes.firstIndex(of: selectedMode) else { return }
        selectedMode = modes[(idx + 1) % modes.count]
        Task { await reload() }
    }

    func setRange(start: Date, end: Date, reload: Bool = false) {
        let normalized = normalizedRange(start: start, end: end)
        startDate = normalized.start
        endDate = normalized.end
        selectedYear = Calendar.current.component(.year, from: normalized.start)
        selectedPoint = nil
        if reload {
            Task { await self.reload() }
        }
    }

    func updateFromPickers() {
        setRange(start: startDate, end: endDate, reload: true)
    }

    func setQuarter(_ quarter: Int) {
        let year = selectedYear
        let startMonth = max(1, min(4, quarter)) * 3 - 2
        let start = Calendar.current.date(from: DateComponents(year: year, month: startMonth, day: 1)) ?? startDate
        let endMonth = startMonth + 2
        let lastDay = Calendar.current.range(of: .day, in: .month, for: Calendar.current.date(from: DateComponents(year: year, month: endMonth, day: 1)) ?? Date())?.count ?? 30
        let end = Calendar.current.date(from: DateComponents(year: year, month: endMonth, day: lastDay)) ?? endDate
        setRange(start: start, end: end, reload: true)
    }

    func setMonth(_ monthIndex: Int) {
        let year = selectedYear
        let month = max(1, min(12, monthIndex + 1))
        let start = Calendar.current.date(from: DateComponents(year: year, month: month, day: 1)) ?? startDate
        let end = Calendar.current.date(byAdding: DateComponents(month: 1, day: -1), to: start) ?? endDate
        setRange(start: start, end: end, reload: true)
    }

    func setAnnual() {
        let year = selectedYear
        let start = Calendar.current.date(from: DateComponents(year: year, month: 1, day: 1)) ?? startDate
        let end = Calendar.current.date(from: DateComponents(year: year, month: 12, day: 31)) ?? endDate
        setRange(start: start, end: end, reload: true)
    }

    func setYTD() {
        let year = selectedYear
        let start = Calendar.current.date(from: DateComponents(year: year, month: 1, day: 1)) ?? startDate
        let end = min(Date(), Calendar.current.date(from: DateComponents(year: year, month: 12, day: 31)) ?? Date())
        setRange(start: start, end: end, reload: true)
    }

    func setYear(_ year: Int) {
        let today = Date()
        let currentYear = Calendar.current.component(.year, from: today)
        let clamped = min(year, currentYear)
        selectedYear = clamped
        let start = Calendar.current.date(from: DateComponents(year: clamped, month: 1, day: 1)) ?? startDate
        let end = (clamped == currentYear) ? today : (Calendar.current.date(from: DateComponents(year: clamped, month: 12, day: 31)) ?? endDate)
        setRange(start: start, end: end, reload: true)
    }

    func previousYear() {
        setYear(selectedYear - 1)
    }

    func nextYear() {
        setYear(selectedYear + 1)
    }

    func reload() async {
        isLoading = true
        errorMessage = nil
        do {
            let raw = try await api.fetchChartSeries(mode: selectedMode, start: Self.isoDate(startDate), end: Self.isoDate(endDate))
            points = Self.mapPoints(raw)
            selectedPoint = points.last
        } catch QuailCashAPIError.unauthorized {
            errorMessage = "Sign in to load chart data."
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func updateSelection(location: CGPoint, proxy: ChartProxy, geometry: GeometryProxy) {
        guard !points.isEmpty else {
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

        selectedPoint = points.min(by: {
            abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date))
        })
    }

    func clearSelection() {
        selectedPoint = nil
    }

    var currentValueText: String {
        guard let last = points.last else { return moneyValue(0) }
        return moneyValue(last.value)
    }

    var rangeLabel: String {
        "\(Self.isoDate(startDate)) to \(Self.isoDate(endDate))"
    }

    var subtitle: String { selectedMode.subtitle }

    var nextModeTitle: String {
        return "Next ▶"
    }

    var growthPercentText: String {
        guard let first = points.first?.value, let last = points.last?.value, first != 0 else {
            return "—"
        }
        let pct = ((last - first) / abs(first)) * 100.0
        return String(format: "%+.2f%%", pct)
    }

    var growthPercentDisplayText: String {
        guard let first = points.first?.value, let last = points.last?.value, first != 0 else {
            return "—"
        }
        let pct = ((last - first) / abs(first)) * 100.0
        return String(format: "%.1f%%", abs(pct))
    }

    var growthPercentValueColor: Color {
        guard let first = points.first?.value, let last = points.last?.value, first != 0 else {
            return .primary
        }
        return last >= first ? .green : .red
    }

    var growthDeltaText: String {
        guard let first = points.first?.value, let last = points.last?.value else {
            return moneyValue(0)
        }
        return moneyValue(last - first)
    }

    var yDomain: ClosedRange<Double> {
        let values = points.map(\.value)
        guard let minValue = values.min(), let maxValue = values.max() else {
            return 0...1
        }
        if minValue == maxValue {
            let pad = max(1, abs(maxValue) * 0.05)
            return (minValue - pad)...(maxValue + pad)
        }
        let pad = max(1, (maxValue - minValue) * 0.12)
        return (minValue - pad)...(maxValue + pad)
    }

    var projectedPoints: [ChartPoint] {
        guard projectedGrowthEnabled, points.count >= 2 else { return [] }
        let sample = Array(points.suffix(min(points.count, 8)))
        guard let first = sample.first, let last = sample.last else { return [] }
        let interval = max(1, Calendar.current.dateComponents([.day], from: first.date, to: last.date).day ?? sample.count - 1)
        let slope = (last.value - first.value) / Double(interval)
        let futureCount = 7
        return (1...futureCount).compactMap { step in
            guard let date = Calendar.current.date(byAdding: .day, value: step, to: last.date) else { return nil }
            return ChartPoint(date: date, value: last.value + slope * Double(step), banks: nil, savings: nil, cards: nil, cardsBalance: nil)
        }
    }

    var tooltipTitle: String {
        selectedPoint.map { Self.tooltipDateFormatter.string(from: $0.date) } ?? ""
    }

    var tooltipLines: [String] {
        guard let p = selectedPoint else { return [] }
        if selectedMode == .netWorth {
            return [
                "Net Worth: \(moneyValue(p.value))",
                "Banks: \(moneyValue(p.banks ?? 0))",
                "Savings: \(moneyValue(p.savings ?? 0))",
                "Cards: \(moneyValue(p.cards ?? 0))",
            ]
        }
        return ["\(selectedMode.title): \(moneyValue(p.value))"]
    }

    private func resetToCurrentYear() {
        let cal = Calendar.current
        let now = Date()
        let startOfYear = cal.date(from: cal.dateComponents([.year], from: now)) ?? now
        selectedYear = cal.component(.year, from: now)
        startDate = startOfYear
        endDate = now
        selectedPoint = nil
    }

    private func normalizedRange(start: Date, end: Date) -> (start: Date, end: Date) {
        let cal = Calendar.current
        let s = cal.startOfDay(for: start)
        let e = cal.startOfDay(for: max(start, end))
        return (s, e)
    }

    private static func mapPoints(_ raw: [ChartSeriesPoint]) -> [ChartPoint] {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let fallback = ISO8601DateFormatter()
        let dateOnly: DateFormatter = {
            let df = DateFormatter()
            df.locale = Locale(identifier: "en_US_POSIX")
            df.timeZone = TimeZone(secondsFromGMT: 0)
            df.dateFormat = "yyyy-MM-dd"
            return df
        }()
        return raw.compactMap { point in
            guard let date = formatter.date(from: point.date)
                    ?? fallback.date(from: point.date)
                    ?? dateOnly.date(from: point.date) else { return nil }
            return ChartPoint(
                date: date,
                value: point.value,
                banks: point.banks,
                savings: point.savings,
                cards: point.cards,
                cardsBalance: point.cardsBalance
            )
        }
        .sorted { $0.date < $1.date }
    }

    private static func isoDate(_ date: Date) -> String {
        let cal = Calendar.current
        let y = cal.component(.year, from: date)
        let m = cal.component(.month, from: date)
        let d = cal.component(.day, from: date)
        return String(format: "%04d-%02d-%02d", y, m, d)
    }

    private static let tooltipDateFormatter: DateFormatter = {
        let df = DateFormatter()
        df.locale = Locale(identifier: "en_US_POSIX")
        df.dateFormat = "MMM dd"
        return df
    }()
}

struct ChartPoint: Identifiable, Hashable {
    let id = UUID()
    let date: Date
    let value: Double
    let banks: Double?
    let savings: Double?
    let cards: Double?
    let cardsBalance: Double?
}

private struct AnalyticsChartSection: View {
    @StateObject private var model = ChartViewModel()

    var body: some View {
        VStack(alignment: .leading, spacing: 11) {
            HStack(alignment: .center, spacing: 8) {
                Spacer(minLength: 0)
                Text(model.selectedMode.title)
                    .font(.system(size: 16, weight: .bold, design: .rounded))

                Spacer(minLength: 0)

                Button("Next ▶") {
                    model.nextMode()
                }
                .buttonStyle(ChartSecondaryButtonStyle())
            }

            HStack(spacing: 4) {
                dateField(title: "Start", date: Binding(get: { model.startDate }, set: { model.startDate = $0 }))
                Spacer(minLength: 10)
                dateField(title: "End", date: Binding(get: { model.endDate }, set: { model.endDate = $0 }))

                Spacer(minLength: 4)

                Button("Update") {
                    model.updateFromPickers()
                }
                .buttonStyle(ChartPrimaryButtonStyle())
                .frame(height: 36)
            }

            HStack(spacing: 6) {
                metricPill(title: model.selectedMode.title, value: model.currentValueText)
                metricPill(title: "% Growth", value: model.growthPercentDisplayText, compact: true, valueColor: model.growthPercentValueColor)
            }

            HStack(spacing: 5) {
                ForEach(0..<4) { idx in
                    Button("Q\(idx + 1)") {
                        model.setQuarter(idx + 1)
                    }
                    .buttonStyle(ChartChipButtonStyle())
                }

                Button("YTD") {
                    model.setYTD()
                }
                .buttonStyle(ChartChipButtonStyle())

                Spacer(minLength: 12)

                HStack(spacing: 4) {
                    Button {
                        model.previousYear()
                    } label: {
                        Image(systemName: "arrow.left")
                    }
                    .buttonStyle(ChartChipButtonStyle())

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
                    .buttonStyle(ChartChipButtonStyle())
                }
            }

            chartContainer

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 7) {
                    ForEach(Array(["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"].enumerated()), id: \.offset) { idx, name in
                        Button(name) {
                            model.setMonth(idx)
                        }
                        .buttonStyle(ChartChipButtonStyle())
                    }

                    Button("Annual") {
                        model.setAnnual()
                    }
                    .buttonStyle(ChartChipButtonStyle())
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
        .task {
            model.startIfNeeded()
        }
    }

    private var chartContainer: some View {
        GeometryReader { proxy in
            ZStack(alignment: .topLeading) {
                chartBody
                    .frame(width: proxy.size.width, height: 224, alignment: .topLeading)
                    .clipped()
                    .padding(11)
                    .background(Color.black.opacity(0.02), in: RoundedRectangle(cornerRadius: 20, style: .continuous))

                if model.selectedMode == .netWorth {
                    HStack(spacing: 6) {
                        VStack(alignment: .leading, spacing: 1) {
                            Text("Project")
                                .font(.system(size: 8, weight: .semibold, design: .rounded))
                                .foregroundStyle(.secondary)
                            Text("Growth")
                                .font(.system(size: 8, weight: .semibold, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                        Toggle("", isOn: $model.projectedGrowthEnabled)
                            .labelsHidden()
                            .controlSize(.mini)
                            .toggleStyle(SwitchToggleStyle(tint: model.selectedMode.tint))
                    }
                    .scaleEffect(0.9, anchor: .leading)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 4)
                    .background(Color.white.opacity(0.9), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(.black.opacity(0.08), lineWidth: 1))
                    .padding(.top, 8)
                    .padding(.leading, 68)
                    .contentShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .onTapGesture {
                        model.projectedGrowthEnabled.toggle()
                    }
                }

                if model.selectedPoint != nil {
                    VStack(alignment: .leading, spacing: 4) {
                        if model.tooltipExpanded {
                            ForEach(model.tooltipLines, id: \.self) { line in
                                Text(line)
                                    .font(.system(size: 10, weight: .medium, design: .rounded))
                                    .foregroundStyle(.white.opacity(0.92))
                            }
                        }
                        HStack(spacing: 4) {
                            Text(model.tooltipTitle)
                                .font(.system(size: 10, weight: .medium, design: .rounded))
                                .foregroundStyle(.white.opacity(0.88))
                            if !model.tooltipExpanded {
                                Image(systemName: "chevron.down")
                                    .font(.system(size: 9, weight: .bold))
                                    .foregroundStyle(.white.opacity(0.92))
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .trailing)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 6)
                    .background(Color.black.opacity(0.82), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .frame(maxWidth: 160, alignment: .leading)
                    .padding(.trailing, 10)
                    .padding(.bottom, 22)
                    .contentShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .onTapGesture {
                        model.tooltipExpanded.toggle()
                    }
                    .transition(.opacity.combined(with: .scale))
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
                }
            }
        }
        .frame(height: 224)
    }

    @ViewBuilder
    private var chartBody: some View {
        if model.isLoading {
            HStack {
                ProgressView()
                Text("Loading chart...")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, minHeight: 170, alignment: .center)
        } else if let error = model.errorMessage {
            VStack(spacing: 6) {
                Text(error)
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                Button("Retry") {
                    Task { await model.reload() }
                }
                .buttonStyle(SecondarySmallButtonStyle())
            }
            .frame(maxWidth: .infinity, minHeight: 170, alignment: .center)
        } else {
            Chart {
                ForEach(model.points) { point in
                    AreaMark(
                        x: .value("Date", point.date),
                        yStart: .value("Baseline", model.yDomain.lowerBound),
                        yEnd: .value("Value", point.value)
                    )
                    .foregroundStyle(
                        LinearGradient(
                            colors: [model.selectedMode.tint.opacity(0.16), model.selectedMode.tint.opacity(0.04)],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )

                    LineMark(
                        x: .value("Date", point.date),
                        y: .value("Value", point.value)
                    )
                    .foregroundStyle(model.selectedMode.tint)
                    .lineStyle(StrokeStyle(lineWidth: 2.8, lineCap: .round, lineJoin: .round))
                }

                ForEach(model.projectedPoints) { point in
                    LineMark(
                        x: .value("Date", point.date),
                        y: .value("Value", point.value)
                    )
                    .foregroundStyle(model.selectedMode.tint.opacity(0.5))
                    .lineStyle(StrokeStyle(lineWidth: 2.1, lineCap: .round, lineJoin: .round, dash: [5, 4]))
                }

                if let selected = model.selectedPoint {
                    RuleMark(x: .value("Selected", selected.date))
                        .foregroundStyle(.black.opacity(0.18))

                    PointMark(
                        x: .value("Selected", selected.date),
                        y: .value("Selected", selected.value)
                    )
                    .foregroundStyle(model.selectedMode.tint)
                    .symbolSize(70)
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
        HStack(spacing: 6) {
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
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 13, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 13, style: .continuous).stroke(.black.opacity(0.05), lineWidth: 1))
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

private struct ChartPrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .bold, design: .rounded))
            .padding(.horizontal, 14)
            .frame(height: 36)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(Color.black.opacity(configuration.isPressed ? 0.82 : 1.0))
            )
            .foregroundStyle(.white)
    }
}

private struct ChartSecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .bold, design: .rounded))
            .padding(.horizontal, 10)
            .frame(height: 36)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(Color.white.opacity(configuration.isPressed ? 0.85 : 1.0))
            )
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.14), lineWidth: 1))
            .foregroundStyle(.primary)
    }
}

private struct ChartChipButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 11, weight: .semibold, design: .rounded))
            .padding(.horizontal, 10)
            .frame(height: 32)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(Color.white.opacity(configuration.isPressed ? 0.82 : 1.0))
            )
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.14), lineWidth: 1))
            .foregroundStyle(.primary)
    }
}

private struct SecondarySmallButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 11, weight: .semibold, design: .rounded))
            .padding(.horizontal, 10)
            .frame(height: 30)
            .background(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(Color.black.opacity(configuration.isPressed ? 0.10 : 0.06))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(Color.black.opacity(0.06), lineWidth: 1)
            )
            .foregroundStyle(.primary)
    }
}

@MainActor
final class HomeViewModel: ObservableObject {
    @Published var home: HomePayload?
    @Published var extraSaved: Double?
    @Published var showAuthSheet = false
    @Published var isLoading = false
    @Published var needsAuthentication = false
    @Published var errorMessage: String?
    @Published var statusText: String = "Starting..."
    @Published var upcomingEvents: [UpcomingEventPayload] = []
    @Published var upcomingLoading = false
    @Published var upcomingError: String?

    private let api = QuailCashAPI.shared
    private var didStart = false

    func load() async {
        await reload()
    }

    func startIfNeeded() {
        guard !didStart else { return }
        didStart = true
        statusText = "Loading home payload..."
        print("[QuailCash] HomeViewModel.startIfNeeded()")
        Task { await reload() }
    }

    func reload() async {
        isLoading = true
        errorMessage = nil
        needsAuthentication = false
        statusText = "Requesting /page/home ..."
        print("[QuailCash] HomeViewModel.reload() begin")
        do {
            extraSaved = nil
            home = try await api.fetchHome(txLimit: 15)
            extraSaved = try? await api.fetchExtraSaved()
            upcomingLoading = true
            upcomingError = nil
            do {
                upcomingEvents = try await api.fetchUpcomingWindow(daysAhead: 30)
            } catch {
                upcomingEvents = []
                upcomingError = error.localizedDescription
            }
            upcomingLoading = false
            if let credit = home?.bankTotals.credit {
                let accounts = credit.accounts.map { "\($0.id):\($0.total)" }.joined(separator: ", ")
                print("[QuailCash] HomeViewModel.creditTotals total=\(credit.total) accounts=[\(accounts)]")
            }
            statusText = "Loaded real data."
            print("[QuailCash] HomeViewModel.reload() success")
        } catch QuailCashAPIError.unauthorized {
            needsAuthentication = true
            showAuthSheet = true
            errorMessage = nil
            statusText = "Signed out. Sign in to load real data."
            upcomingEvents = []
            upcomingLoading = false
            upcomingError = nil
            print("[QuailCash] HomeViewModel.reload() unauthorized -> showing auth sheet")
        } catch {
            errorMessage = error.localizedDescription
            statusText = "Error: \(error.localizedDescription)"
            upcomingEvents = []
            upcomingLoading = false
            upcomingError = nil
            print("[QuailCash] HomeViewModel.reload() error: \(error.localizedDescription)")
        }
        isLoading = false
        print("[QuailCash] HomeViewModel.reload() end")
    }

    func finishAuthentication() {
        print("[QuailCash] HomeViewModel.finishAuthentication()")
        showAuthSheet = false
        Task { await reload() }
    }

    func cancelAuthentication() {
        print("[QuailCash] HomeViewModel.cancelAuthentication()")
        showAuthSheet = false
        needsAuthentication = true
    }

    func recalculateDailySnapshot() async {
        print("[QuailCash] HomeViewModel.recalculateDailySnapshot() begin")
        statusText = "Recalculating daily snapshot..."
        do {
            _ = try await api.fetchDayLimit(recalc: true)
            await reload()
        } catch QuailCashAPIError.unauthorized {
            needsAuthentication = true
            showAuthSheet = true
            errorMessage = nil
            statusText = "Signed out. Sign in to recalculate."
        } catch {
            errorMessage = error.localizedDescription
            statusText = "Error: \(error.localizedDescription)"
        }
        print("[QuailCash] HomeViewModel.recalculateDailySnapshot() end")
    }
}

private struct BankTotalsAccordionCard: View {
    let bankTotals: BankTotalsPayload
    let onImport: () -> Void
    let onBankInfo: () -> Void
    let onOpenAccount: (BankAccountPayload) -> Void
    let onVerifyAccount: (BankAccountPayload) -> Void
    let onAuditAccount: (BankAccountPayload) -> Void
    @State private var isExpanded = true
    @State private var expandedSection: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Spacer(minLength: 0)
                Text("Bank Totals")
                    .font(.system(size: 17, weight: .semibold, design: .rounded))
                Spacer(minLength: 0)
                Image(systemName: "chevron.down")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .rotationEffect(.degrees(isExpanded ? 180 : 0))
            }
            .contentShape(Rectangle())
            .onTapGesture {
                withAnimation(.spring(response: 0.28, dampingFraction: 0.9)) {
                    isExpanded.toggle()
                }
            }

            if isExpanded {
                HStack(spacing: 8) {
                    Button("Import CSV/Excel") {
                        onImport()
                    }
                    .buttonStyle(HomeHeaderActionStyle(primary: true))

                    Button("Bank Info") {
                        onBankInfo()
                    }
                    .buttonStyle(HomeHeaderActionStyle(primary: false))
                }

                sectionCard(title: "Checking", key: "checking", group: bankTotals.checking)
                sectionCard(title: "Savings", key: "savings", group: bankTotals.savings)
                sectionCard(title: "Credit", key: "credit", group: bankTotals.credit)
                sectionCard(title: "Investment", key: "investment", group: bankTotals.investment)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
    }

    @ViewBuilder
    private func sectionCard(title: String, key: String, group: BankGroupPayload?) -> some View {
        if let group {
            let isExpanded = expandedSection == key
            Button {
                withAnimation(.spring(response: 0.28, dampingFraction: 0.9)) {
                    expandedSection = isExpanded ? nil : key
                }
            } label: {
                VStack(alignment: .leading, spacing: 10) {
                    HStack(alignment: .top, spacing: 10) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(title)
                                .font(.system(size: 16, weight: .semibold, design: .rounded))
                                .foregroundStyle(.primary)
                                .lineLimit(1)
                            Text("\(group.accounts.count) acct")
                                .font(.system(size: 11, weight: .semibold, design: .rounded))
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }

                        Spacer(minLength: 8)

                        VStack(alignment: .trailing, spacing: 2) {
                            Text(bankTotalText(title: title, total: group.total))
                                .font(.system(size: 15, weight: .bold, design: .rounded))
                                .foregroundStyle(.primary)
                                .lineLimit(1)
                            if title == "Credit" {
                                let creditTotal = group.accounts.compactMap { $0.creditLimit }.filter { $0 > 0 }.reduce(0, +)
                                if creditTotal > 0 {
                                    let pctUsed = creditUsageSummaryPct(total: group.total, accounts: group.accounts)
                                    Text("Limit \(moneyValue(creditTotal))  \(pctUsed)% used")
                                        .font(.system(size: 11, weight: .semibold, design: .rounded))
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                }
                            }
                        }

                        Image(systemName: "chevron.down")
                            .font(.system(size: 13, weight: .semibold))
                            .rotationEffect(.degrees(isExpanded ? 180 : 0))
                            .foregroundStyle(.secondary)
                            .padding(.leading, 2)
                            .padding(.top, 2)
                    }

                    if isExpanded {
                        VStack(spacing: 10) {
                            ForEach(group.accounts) { account in
                                AccountRow(
                                    account: account,
                                    groupKey: title.lowercased(),
                                    onOpen: { onOpenAccount(account) },
                                    onVerify: { onVerifyAccount(account) },
                                    onAudit: { onAuditAccount(account) }
                                )
                            }
                        }
                        .padding(.top, 4)
                        .transition(.opacity.combined(with: .move(edge: .top)))
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(16)
                .background(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(Color.black.opacity(isExpanded ? 0.03 : 0.02))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(Color.black.opacity(0.06), lineWidth: 1)
                )
            }
            .buttonStyle(.plain)
        }
    }

    private func bankTotalText(title: String, total: Double) -> String {
        if title == "Credit" {
            return formatAccountBalance(total)
        }
        return moneyValue(abs(total))
    }

    private func creditUsageSummaryPct(total: Double, accounts: [BankAccountPayload]) -> Int {
        let limits = accounts.map { Double($0.creditLimit ?? 0) }.filter { $0 > 0 }
        let totalLimit = limits.reduce(0, +)
        guard totalLimit > 0 else { return 0 }
        let used = accounts.reduce(0.0) { $0 + max(0, -$1.total) }
        return Int(((used / totalLimit) * 100).rounded())
    }
}

private struct AccountRow: View {
    let account: BankAccountPayload
    let groupKey: String
    let onOpen: () -> Void
    let onVerify: () -> Void
    let onAudit: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(account.name)
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(.primary)
                    .lineLimit(1)

                if let csv = account.lastCsvUploadAt, !csv.isEmpty {
                    Text("CSV: \(relativeTimestampText(csv))")
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                if let verified = account.lastManualVerifiedAt, !verified.isEmpty {
                    Text("Verified: \(relativeTimestampText(verified))")
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }

            Spacer(minLength: 10)

            VStack(alignment: .trailing, spacing: 8) {
                Text(balanceText)
                    .font(.system(size: 16, weight: .bold, design: .rounded))
                    .foregroundStyle(.primary)

                HStack(spacing: 6) {
                    Button("Verified", action: onVerify)
                    Button("Audit", action: onAudit)
                }
                .buttonStyle(AccountChipStyle())
            }
        }
        .padding(.vertical, 10)
        .padding(.horizontal, 12)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
        .contentShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .onTapGesture(perform: onOpen)
    }

    private var balanceText: String {
        if groupKey == "credit" {
            return formatAccountBalance(account.total)
        }
        return moneyValue(abs(account.total))
    }

    private func relativeTimestampText(_ raw: String) -> String {
        guard let date = parseAccountTimestamp(raw) else { return raw }
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .full
        return formatter.localizedString(for: date, relativeTo: Date())
    }

    private func parseAccountTimestamp(_ raw: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: raw) {
            return date
        }
        if let date = ISO8601DateFormatter().date(from: raw) {
            return date
        }
        let fallback = DateFormatter()
        fallback.locale = Locale(identifier: "en_US_POSIX")
        fallback.dateFormat = "yyyy-MM-dd"
        return fallback.date(from: raw)
    }
}

private struct TransactionRow: View {
    let tx: TransactionItem

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(transactionDateText)
                    .font(.system(size: 12, weight: .bold, design: .rounded))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)

                ZStack {
                    Circle()
                        .fill(Color.black.opacity(0.06))
                        .frame(width: 38, height: 38)
                    Text(txMerchantInitial)
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                        .foregroundStyle(.primary)
                }
            }
            .frame(width: 46, alignment: .leading)

            VStack(alignment: .leading, spacing: 3) {
                Text(tx.merchant.isEmpty ? "Unknown merchant" : tx.merchant)
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

            Text(formattedAmount)
                .font(.system(size: 14, weight: .bold, design: .rounded))
                .foregroundStyle(tx.amount >= 0 ? .red : .green)
        }
        .padding(.vertical, 10)
        .padding(.horizontal, 12)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private var transactionSubtitle: String {
        let left = [tx.bank, tx.card].compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
        return left.isEmpty ? (tx.category ?? "") : left.joined(separator: " • ")
    }

    private var txMerchantInitial: String {
        let raw = tx.merchant.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let first = raw.first else { return "?" }
        return String(first).uppercased()
    }

    private var transactionDateText: String {
        if let raw = tx.dateISO ?? tx.postedDate ?? tx.date, let formatted = formattedDateString(raw) {
            return formatted
        }
        return "Today"
    }

    private func formattedDateString(_ raw: String) -> String? {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = iso.date(from: raw) ?? ISO8601DateFormatter().date(from: raw) {
            let out = DateFormatter()
            out.locale = Locale(identifier: "en_US_POSIX")
            out.dateFormat = "MMM d"
            return out.string(from: date)
        }
        return nil
    }

    private var formattedAmount: String {
        moneyValue(tx.amount)
    }
}

private struct HomePopupOverlay: View {
    let popup: HomePopup
    let onDismiss: () -> Void
    let onRefresh: () -> Void

    var body: some View {
        ZStack {
            Color.black.opacity(0.46)
                .ignoresSafeArea()
                .onTapGesture(perform: onDismiss)

            switch popup {
            case .incomeBreakdown:
                IncomeBreakdownPopupView(onDismiss: onDismiss, onRefresh: onRefresh)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 18)
            case .spentBreakdown:
                SpentBreakdownPopupView(onDismiss: onDismiss, onRefresh: onRefresh)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 18)
            case .extraSavedBreakdown:
                ExtraSavedBreakdownPopupView(onDismiss: onDismiss, onRefresh: onRefresh)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 18)
            case .bankInfo:
                BankInfoPopupView(onDismiss: onDismiss, onRefresh: onRefresh)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 18)
            case .transaction(let tx):
                SharedTransactionInspectPopupView(transaction: tx, onDismiss: onDismiss, onRefresh: onRefresh)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 18)
            case .verifyAccount(let account):
                AccountVerifyPopupView(account: account, onDismiss: onDismiss, onRefresh: onRefresh)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 18)
            case .auditAccount(let account):
                AccountAuditPopupView(account: account, onDismiss: onDismiss)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 18)
            }
        }
        .transition(.opacity.combined(with: .scale(scale: 0.98)))
    }
}

@MainActor
private struct IncomeBreakdownPopupView: View {
    let onDismiss: () -> Void
    let onRefresh: () -> Void

    @State private var payload: MonthBudgetPayload?
    @State private var loadError: String?
    @State private var isLoading = true

    var body: some View {
        PopupChrome(title: "Last month's income", subtitle: subtitleText, onClose: onDismiss) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if isLoading {
                        ProgressView().padding(.vertical, 22)
                    } else if let loadError {
                        Text(loadError)
                            .font(.system(size: 13, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    } else if let payload {
                        HStack(spacing: 8) {
                            incomePill("Last month paychecks used", nativeMoneyValue(payload.incomeBasisTotal ?? 0))
                            incomePill("Recurring income", nativeMoneyValue(payload.baseIncome ?? 0))
                            incomePill("Income total", nativeMoneyValue(payload.expectedIncome ?? 0))
                        }

                        Text("Budget basis")
                            .font(.system(size: 15, weight: .bold, design: .rounded))

                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(payload.incomeBasisPaychecks ?? [], id: \.self) { item in
                                HStack {
                                    Text(item.date ?? "")
                                        .font(.system(size: 12, weight: .medium, design: .rounded))
                                        .foregroundStyle(.secondary)
                                    Spacer()
                                    Text("\(item.merchant ?? "Paycheck")  \(nativeMoneyValue(item.amount ?? 0))")
                                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                                }
                                .padding(12)
                                .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                            }
                        }

                        if let basis = payload.incomeBasisMonth,
                           let year = basis.year,
                           let month = basis.month {
                            Text("Basis month: \(String(format: "%04d-%02d", year, month))")
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .padding(16)
            }
        }
        .task { await load() }
    }

    private var subtitleText: String {
        if let payload {
            return nativeMoneyValue(payload.expectedIncome ?? 0)
        }
        return isLoading ? "Loading…" : "Income breakdown"
    }

    private func incomePill(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label)
                .font(.system(size: 10, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 13, weight: .bold, design: .rounded))
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func load() async {
        isLoading = true
        do {
            payload = try await QuailCashAPI.shared.fetchMonthBudget()
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
        isLoading = false
    }
}

@MainActor
private struct SpentBreakdownPopupView: View {
    let onDismiss: () -> Void
    let onRefresh: () -> Void

    @State private var payload: SpentSoFarBreakdownPayload?
    @State private var loadError: String?
    @State private var isLoading = true
    @State private var expandedCategory: String?
    @State private var transactionsByCategory: [String: [TransactionItem]] = [:]
    @State private var loadingCategories: Set<String> = []

    var body: some View {
        PopupChrome(title: "Spent so far", subtitle: subtitleText, onClose: onDismiss) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if isLoading {
                        ProgressView().padding(.vertical, 22)
                    } else if let loadError {
                        Text(loadError)
                            .font(.system(size: 13, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    } else if let payload {
                        HStack(spacing: 8) {
                            spentPill("Free spend", nativeMoneyValue(payload.total))
                            spentPill("All spend", nativeMoneyValue(payload.totalAll))
                            spentPill("Roundups", nativeMoneyValue(payload.roundupsTotal))
                        }

                        breakdownSection(title: "Excluded categories", items: payload.excluded, accent: .red, tappable: false)
                        breakdownSection(title: "Included categories", items: payload.included, accent: .primary, tappable: true)
                    }
                }
                .padding(16)
            }
        }
        .task { await load() }
    }

    private var subtitleText: String {
        if let payload {
            return "\(payload.start)  \(payload.end)"
        }
        return isLoading ? "Loading…" : "Breakdown"
    }

    private func spentPill(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label)
                .font(.system(size: 10, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 13, weight: .bold, design: .rounded))
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func breakdownSection(title: String, items: [SpentBreakdownCategory], accent: Color, tappable: Bool) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 15, weight: .bold, design: .rounded))

            if items.isEmpty {
                Text("None")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            } else {
                VStack(spacing: 8) {
                    ForEach(items, id: \.self) { item in
                        let isOpen = expandedCategory == item.category
                        Button {
                            guard tappable else { return }
                            Task { await toggleCategory(item.category) }
                        } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Text(item.category)
                                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                                    Spacer()
                                    Text(nativeMoneyValue(item.total))
                                        .font(.system(size: 14, weight: .bold, design: .rounded))
                                }
                                if tappable && isOpen {
                                    if loadingCategories.contains(item.category) {
                                        ProgressView().padding(.vertical, 6)
                                    } else if let txs = transactionsByCategory[item.category], !txs.isEmpty {
                                        VStack(spacing: 6) {
                                            ForEach(txs.prefix(5)) { tx in
                                                HStack {
                                                    VStack(alignment: .leading, spacing: 2) {
                                                        Text(tx.merchant.isEmpty ? "Unknown merchant" : tx.merchant)
                                                            .font(.system(size: 12, weight: .semibold, design: .rounded))
                                                            .foregroundStyle(.primary)
                                                        Text([tx.bank, tx.card].compactMap { $0 }.joined(separator: " • "))
                                                            .font(.system(size: 11, weight: .medium, design: .rounded))
                                                            .foregroundStyle(.secondary)
                                                    }
                                                    Spacer()
                                                    Text(nativeMoneyValue(tx.amount))
                                                        .font(.system(size: 12, weight: .bold, design: .rounded))
                                                }
                                                .padding(.vertical, 8)
                                                .padding(.horizontal, 10)
                                                .background(Color.black.opacity(0.02), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                                            }
                                        }
                                    } else {
                                        Text("No transactions.")
                                            .font(.system(size: 12, weight: .medium, design: .rounded))
                                            .foregroundStyle(.secondary)
                                    }
                                }
                            }
                            .padding(12)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(accent.opacity(0.08), lineWidth: 1))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    private func load() async {
        isLoading = true
        do {
            payload = try await QuailCashAPI.shared.fetchSpentSoFarBreakdown(start: nativeIsoMonthStart(), end: nativeIsoToday())
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
        isLoading = false
    }

    private func toggleCategory(_ category: String) async {
        if expandedCategory == category {
            expandedCategory = nil
            return
        }
        expandedCategory = category
        if transactionsByCategory[category] != nil { return }

        loadingCategories.insert(category)
        defer { loadingCategories.remove(category) }

        do {
            transactionsByCategory[category] = try await QuailCashAPI.shared.fetchSpentSoFarTransactions(
                category: category,
                start: nativeIsoMonthStart(),
                end: nativeIsoToday(),
                limit: 500
            )
        } catch {
            transactionsByCategory[category] = []
        }
    }
}

@MainActor
private struct ExtraSavedBreakdownPopupView: View {
    let onDismiss: () -> Void
    let onRefresh: () -> Void

    @State private var payload: ExtraSavedDetailPayload?
    @State private var loadError: String?
    @State private var isLoading = true

    var body: some View {
        PopupChrome(title: "Extra saved", subtitle: subtitleText, onClose: onDismiss) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if isLoading {
                        ProgressView().padding(.vertical, 22)
                    } else if let loadError {
                        Text(loadError)
                            .font(.system(size: 13, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    } else if let payload {
                        HStack(spacing: 8) {
                            extraSavedPill("Month start", payload.monthStart)
                            extraSavedPill("Today", payload.today)
                            extraSavedPill("Total", nativeMoneyValue(payload.totalExtraSaved))
                        }

                        VStack(spacing: 8) {
                            ForEach(payload.days, id: \.self) { day in
                                HStack {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(day.day)
                                            .font(.system(size: 13, weight: .semibold, design: .rounded))
                                        Text("Baseline \(nativeMoneyValue(day.baseline)) • Free spend \(nativeMoneyValue(day.spentTodayFree))")
                                            .font(.system(size: 11, weight: .medium, design: .rounded))
                                            .foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    Text(nativeMoneyValue(day.leftover))
                                        .font(.system(size: 13, weight: .bold, design: .rounded))
                                }
                                .padding(12)
                                .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                            }
                        }
                    }
                }
                .padding(16)
            }
        }
        .task { await load() }
    }

    private var subtitleText: String {
        if let payload {
            return "\(payload.monthStart)  \(payload.today)"
        }
        return isLoading ? "Loading…" : "Breakdown"
    }

    private func extraSavedPill(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label)
                .font(.system(size: 10, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 13, weight: .bold, design: .rounded))
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func load() async {
        isLoading = true
        do {
            payload = try await QuailCashAPI.shared.fetchExtraSavedDetail()
            loadError = nil
        } catch {
            loadError = error.localizedDescription
        }
        isLoading = false
    }
}

private struct BankInfoPopupView: View {
    @Environment(\.dismiss) private var dismiss
    let onDismiss: () -> Void
    let onRefresh: () -> Void

    @State private var payload: BankInfoPayload?
    @State private var loadError: String?
    @State private var selectedAccountID: Int = 0
    @State private var ratePercent = ""
    @State private var effectiveDate = isoToday()
    @State private var note = ""
    @State private var saveMessage: String?
    @State private var isSaving = false

    var body: some View {
        PopupChrome(title: "Bank info", subtitle: payload?.lastUpdated ?? "Loading…", onClose: close) {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    rateEditor

                    bankSection(title: "Accounts", subtitle: "Savings & checking", accounts: payload?.accounts ?? [], cardStyle: false)
                    bankCardsSection
                }
                .padding(16)
            }
        }
        .task { await load() }
    }

    private var rateEditor: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Set a new rate")
                .font(.system(size: 16, weight: .bold, design: .rounded))

            VStack(alignment: .leading, spacing: 10) {
                labeledField("Account") {
                    Picker("Account", selection: $selectedAccountID) {
                        ForEach(payload?.accounts ?? []) { account in
                            Text("\(account.bank) — \(account.name) (APY)").tag(account.id)
                        }
                        ForEach(payload?.creditCards ?? []) { card in
                            Text("\(card.bank) — \(card.name) (APR)").tag(card.id)
                        }
                    }
                    .pickerStyle(.menu)
                }

                labeledField("Rate (%)") {
                    TextField("e.g. 3.54", text: $ratePercent)
                        .keyboardType(.decimalPad)
                }

                labeledField("Effective date") {
                    TextField("YYYY-MM-DD", text: $effectiveDate)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled(true)
                }

                labeledField("Note") {
                    TextField("optional", text: $note)
                }
            }

            HStack(spacing: 10) {
                Button("Save rate") { Task { await saveRate() } }
                    .buttonStyle(PrimaryButtonStyle())
                if let saveMessage {
                    Text(saveMessage)
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(14)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }

    @ViewBuilder
    private var bankCardsSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            bankSection(title: "Credit cards", subtitle: "APR, limits & rewards", cards: payload?.creditCards ?? [])
        }
    }

    @ViewBuilder
    private func bankSection(title: String, subtitle: String, accounts: [BankInfoAccountPayload], cardStyle: Bool) -> some View {
        if !accounts.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 16, weight: .bold, design: .rounded))
                    Text(subtitle)
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }

                VStack(spacing: 8) {
                    ForEach(accounts) { account in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text("\(account.bank) — \(account.name)")
                                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                                Spacer()
                Text(account.apy.map { String(format: "%.2f%%", $0) } ?? "—")
                                    .font(.system(size: 13, weight: .bold, design: .rounded))
                            }
                            HStack {
                                Text("Type")
                                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                                    .foregroundStyle(.secondary)
                                Spacer()
                                Text(account.type.uppercased())
                                    .font(.system(size: 11, weight: .bold, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                            if let notes = account.notes, !notes.isEmpty {
                                Text(notes)
                                    .font(.system(size: 11, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .padding(10)
                        .background(Color.white, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func bankSection(title: String, subtitle: String, cards: [BankInfoCreditCardPayload]) -> some View {
        if !cards.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 16, weight: .bold, design: .rounded))
                    Text(subtitle)
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }

                VStack(spacing: 8) {
                    ForEach(cards) { card in
                        VStack(alignment: .leading, spacing: 5) {
                            HStack {
                                Text("\(card.bank) — \(card.name)")
                                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                                Spacer()
                                Text(card.apr.map { String(format: "%.2f%%", $0) } ?? "—")
                                    .font(.system(size: 13, weight: .bold, design: .rounded))
                            }
                            HStack {
                                Text("Limit")
                                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                                    .foregroundStyle(.secondary)
                                Spacer()
                                Text(card.creditLimit.map { moneyValue($0) } ?? "—")
                                    .font(.system(size: 11, weight: .bold, design: .rounded))
                            }
                            if !card.benefits.isEmpty {
                                ForEach(Array(card.benefits.enumerated()), id: \.offset) { _, benefit in
                                    HStack {
                                        Text((benefit.categories ?? []).joined(separator: ", ").isEmpty ? "Cash back" : (benefit.categories ?? []).joined(separator: ", "))
                                            .font(.system(size: 11, weight: .semibold, design: .rounded))
                                            .foregroundStyle(.secondary)
                                        Spacer()
                                        Text(benefit.cashbackPercent.map { String(format: "%.2f%%", $0) } ?? "—")
                                            .font(.system(size: 11, weight: .bold, design: .rounded))
                                    }
                                }
                            }
                        }
                        .padding(10)
                        .background(Color.white, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
                    }
                }
            }
        }
    }

    private func labeledField<Content: View>(_ label: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            content()
                .font(.system(size: 13, weight: .medium, design: .rounded))
                .padding(.horizontal, 10)
                .padding(.vertical, 8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
        }
    }

    private func load() async {
        do {
            let next = try await QuailCashAPI.shared.fetchBankInfo()
            await MainActor.run {
                payload = next
                loadError = nil
                if selectedAccountID == 0 {
                    selectedAccountID = next.accounts.first?.id ?? next.creditCards.first?.id ?? 0
                }
                if effectiveDate.isEmpty {
                    effectiveDate = isoToday()
                }
            }
        } catch {
            await MainActor.run {
                loadError = error.localizedDescription
            }
        }
    }

    private func saveRate() async {
        guard selectedAccountID > 0, let rate = Double(ratePercent) else {
            saveMessage = "Pick an account and enter a rate."
            return
        }
        isSaving = true
        defer { isSaving = false }
        do {
            _ = try await QuailCashAPI.shared.setInterestRate(accountID: selectedAccountID, ratePercent: rate, effectiveDate: effectiveDate, note: note)
            saveMessage = "Saved."
            onRefresh()
            await load()
        } catch {
            saveMessage = "Save failed."
        }
    }

    private func close() {
        dismiss()
        onDismiss()
    }
}

private struct TransactionInspectPopupView: View {
    @Environment(\.dismiss) private var dismiss
    let transaction: TransactionItem
    let onDismiss: () -> Void
    let onRefresh: () -> Void

    @State private var detail: TransactionDetailPayload?
    @State private var categoryText = ""
    @State private var statusText = "posted"
    @State private var postedDateText = ""
    @State private var metaEditing = false
    @State private var saveStatus: String = ""
    @State private var actionStatus: String = ""
    @State private var showDeleteConfirm = false
    @State private var showInvertConfirm = false
    @State private var isSaving = false

    var body: some View {
        PopupChrome(title: "Transaction", subtitle: subtitleText, onClose: close) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    txGrid
                    categoryEditor
                    detailSection
                    actionToolbar
                    if metaEditing {
                        metaEditor
                    }
                    if !saveStatus.isEmpty {
                        Text(saveStatus)
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                    if !actionStatus.isEmpty {
                        Text(actionStatus)
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(16)
            }
        }
        .task { await load() }
        .confirmationDialog("Delete this transaction?", isPresented: $showDeleteConfirm, titleVisibility: .visible) {
            Button("Delete", role: .destructive) { Task { await deleteTransaction() } }
            Button("Cancel", role: .cancel) {}
        }
        .confirmationDialog("Invert this transaction amount?", isPresented: $showInvertConfirm, titleVisibility: .visible) {
            Button("Invert", role: .destructive) { Task { await invertAmount() } }
            Button("Cancel", role: .cancel) {}
        }
    }

    private var subtitleText: String {
        let amount = moneyValue(detail?.amount ?? transaction.amount)
        let date = detail?.postedDate ?? detail?.purchaseDate ?? transaction.postedDate ?? transaction.dateISO ?? "—"
        return "\(amount)  •  \(date)"
    }

    private var txGrid: some View {
        VStack(alignment: .leading, spacing: 10) {
            txKV(label: "Merchant", value: detail?.merchant.isEmpty == false ? detail!.merchant : transaction.merchant)
            txKV(label: "Account", value: detail?.card ?? transaction.card ?? "—")
            txKV(label: "Amount", value: moneyValue(detail?.amount ?? transaction.amount))
            txKV(label: "Date", value: detail?.postedDate ?? transaction.postedDate ?? transaction.dateISO ?? "—")
            txKV(label: "Matches", value: detail?.categoryRulePattern ?? (detail?.category ?? transaction.category ?? "—"))
        }
        .padding(12)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }

    private var categoryEditor: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("category")
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)

            HStack(spacing: 8) {
                TextField("Set category", text: $categoryText)
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))

                Button("Save") { Task { await saveCategory() } }
                    .buttonStyle(PrimaryButtonStyle())
            }
            .disabled(isSaving)
        }
    }

    private var detailSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("details")
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)

            VStack(spacing: 8) {
                txDetailRow(label: "Bank", value: detail?.bank ?? transaction.bank ?? "—")
                txDetailRow(label: "Card", value: detail?.card ?? transaction.card ?? "—")
                txDetailRow(label: "Status", value: detail?.status ?? transaction.status ?? "posted")
                txDetailRow(label: "Account type", value: detail?.accountType ?? transaction.accountType ?? "—")
                txDetailRow(label: "Ignored", value: (detail?.isIgnored ?? false) ? "Yes" : "No")
            }
            .padding(12)
            .background(Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
        }
    }

    private var actionToolbar: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Button(metaEditing ? "Close edit" : "Edit status/date") {
                    metaEditing.toggle()
                }
                .buttonStyle(HomeHeaderActionStyle(primary: false))

                Button("Invert amount") { showInvertConfirm = true }
                    .buttonStyle(HomeHeaderActionStyle(primary: false))

                Button((detail?.isIgnored ?? false) ? "Unignore" : "Ignore") {
                    Task { await toggleIgnore() }
                }
                .buttonStyle(HomeHeaderActionStyle(primary: false))

                Button("Delete") { showDeleteConfirm = true }
                    .buttonStyle(HomeHeaderActionStyle(primary: true))
            }
            .font(.system(size: 11, weight: .semibold, design: .rounded))
        }
    }

    private var metaEditor: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Status")
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundStyle(.secondary)
                    Picker("", selection: $statusText) {
                        Text("posted").tag("posted")
                        Text("pending").tag("pending")
                    }
                    .pickerStyle(.menu)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text("Posted date")
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundStyle(.secondary)
                    TextField("MM/DD/YYYY or unknown", text: $postedDateText)
                        .font(.system(size: 13, weight: .medium, design: .rounded))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)
                        .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
                }
            }
            HStack(spacing: 8) {
                Button("Save") { Task { await saveMeta() } }
                    .buttonStyle(PrimaryButtonStyle())
                Button("Cancel") {
                    if let detail {
                        statusText = (detail.status ?? "posted").lowercased()
                        postedDateText = detail.postedDate ?? detail.purchaseDate ?? ""
                    }
                    metaEditing = false
                    saveStatus = ""
                }
                .buttonStyle(HomeHeaderActionStyle(primary: false))
            }
        }
    }

    private func txKV(label: String, value: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(label)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .frame(width: 74, alignment: .leading)
            Text(value)
                .font(.system(size: 13, weight: .medium, design: .rounded))
                .foregroundStyle(.primary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
        }
    }

    private func txDetailRow(label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.system(size: 11, weight: .bold, design: .rounded))
                .foregroundStyle(.primary)
        }
    }

    private func load() async {
        do {
            let next = try await QuailCashAPI.shared.fetchTransactionDetail(txId: transaction.id)
            await MainActor.run {
                detail = next
                categoryText = next.category ?? transaction.category ?? ""
                statusText = (next.status ?? transaction.status ?? "posted").lowercased()
                postedDateText = next.postedDate ?? next.purchaseDate ?? transaction.postedDate ?? transaction.dateISO ?? ""
                saveStatus = ""
                actionStatus = ""
            }
        } catch {
            await MainActor.run {
                categoryText = transaction.category ?? ""
                statusText = (transaction.status ?? "posted").lowercased()
                postedDateText = transaction.postedDate ?? transaction.dateISO ?? ""
                saveStatus = error.localizedDescription
            }
        }
    }

    private func saveCategory() async {
        isSaving = true
        defer { isSaving = false }
        do {
            _ = try await QuailCashAPI.shared.updateTransactionCategory(txId: transaction.id, category: categoryText)
            saveStatus = "Saved."
            onRefresh()
            await load()
        } catch {
            saveStatus = "Failed to save category."
        }
    }

    private func saveMeta() async {
        isSaving = true
        defer { isSaving = false }
        do {
            _ = try await QuailCashAPI.shared.updateTransactionMeta(txId: transaction.id, status: statusText, postedDate: postedDateText)
            saveStatus = "Saved."
            metaEditing = false
            onRefresh()
            await load()
        } catch {
            saveStatus = "Failed to save metadata."
        }
    }

    private func toggleIgnore() async {
        do {
            let next = !((detail?.isIgnored ?? false))
            _ = try await QuailCashAPI.shared.ignoreTransaction(txId: transaction.id, ignored: next)
            actionStatus = next ? "Ignored from calculations." : "Included in calculations."
            onRefresh()
            await load()
        } catch {
            actionStatus = "Failed to update ignore state."
        }
    }

    private func invertAmount() async {
        do {
            _ = try await QuailCashAPI.shared.invertTransactionAmount(txId: transaction.id)
            actionStatus = "Amount inverted."
            onRefresh()
            await load()
        } catch {
            actionStatus = "Failed to invert amount."
        }
    }

    private func deleteTransaction() async {
        do {
            _ = try await QuailCashAPI.shared.deleteTransaction(txId: transaction.id)
            actionStatus = "Deleted."
            onDismiss()
            onRefresh()
        } catch {
            actionStatus = "Failed to delete transaction."
        }
    }

    private func close() {
        dismiss()
        onDismiss()
    }
}

private struct AccountVerifyPopupView: View {
    @Environment(\.dismiss) private var dismiss
    let account: BankAccountPayload
    let onDismiss: () -> Void
    let onRefresh: () -> Void

    @State private var verifiedDate = isoToday()
    @State private var message = "On the selected date, the final balances for this account match between the bank data and database data."
    @State private var statusText: String?

    var body: some View {
        PopupChrome(title: "Verify Balance", subtitle: account.name, onClose: close) {
            VStack(alignment: .leading, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Verification date")
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundStyle(.secondary)
                    TextField("YYYY-MM-DD", text: $verifiedDate)
                        .font(.system(size: 13, weight: .medium, design: .rounded))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)
                        .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
                }

                Text(message)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                    .lineSpacing(2)

                HStack(spacing: 8) {
                    Button("Cancel") { close() }
                        .buttonStyle(HomeHeaderActionStyle(primary: false))
                    Button("Confirm") { Task { await confirm() } }
                        .buttonStyle(PrimaryButtonStyle())
                }

                if let statusText {
                    Text(statusText)
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
            .padding(16)
        }
    }

    private func confirm() async {
        do {
            _ = try await QuailCashAPI.shared.verifyAccountBalance(accountID: account.id, verifiedDate: verifiedDate)
            statusText = "Saved."
            onRefresh()
            close()
        } catch {
            statusText = "Failed to verify."
        }
    }

    private func close() {
        dismiss()
        onDismiss()
    }
}

private struct AccountAuditPopupView: View {
    @Environment(\.dismiss) private var dismiss
    let account: BankAccountPayload
    let onDismiss: () -> Void

    var body: some View {
        PopupChrome(title: "Account Audit", subtitle: account.name, onClose: close) {
            VStack(alignment: .leading, spacing: 10) {
                popupKV(label: "Account", value: account.name)
                popupKV(label: "Balance", value: formatAccountBalance(account.total))
                popupKV(label: "CSV", value: account.lastCsvUploadAt ?? "—")
                popupKV(label: "Verified", value: account.lastManualVerifiedAt ?? "—")
                popupKV(label: "Credit limit", value: account.creditLimit.map { moneyValue($0) } ?? "—")
            }
            .padding(16)
        }
    }

    private func popupKV(label: String, value: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(label)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .frame(width: 74, alignment: .leading)
            Text(value)
                .font(.system(size: 13, weight: .medium, design: .rounded))
                .foregroundStyle(.primary)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func close() {
        dismiss()
        onDismiss()
    }
}

private enum HomeSheet: Identifiable {
    case transaction(TransactionItem)
    case bankInfo
    case csvImport
    case unassigned
    case upcomingDay(UpcomingDayGroup)

    var id: String {
        switch self {
        case .transaction(let tx):
            return "sheet-tx-\(tx.id)"
        case .bankInfo:
            return "sheet-bank-info"
        case .csvImport:
            return "sheet-csv-import"
        case .unassigned:
            return "sheet-unassigned"
        case .upcomingDay(let group):
            return "sheet-upcoming-\(group.id)"
        }
    }

    var detents: Set<PresentationDetent> {
        switch self {
        case .upcomingDay:
            return [.medium, .large]
        default:
            return [.large]
        }
    }
}

private struct HomeSheetHost: View {
    let sheet: HomeSheet
    let onDismiss: () -> Void
    let onRefresh: () -> Void

    var body: some View {
        switch sheet {
        case .transaction(let tx):
            TransactionInspectSheetView(transaction: tx, onDismiss: onDismiss, onRefresh: onRefresh)
        case .bankInfo:
            BankInfoSheetView(onDismiss: onDismiss, onRefresh: onRefresh)
        case .csvImport:
            CsvImportSheetView(onDismiss: onDismiss, onRefresh: onRefresh)
        case .unassigned:
            UnassignedWizardSheetView(onDismiss: onDismiss, onRefresh: onRefresh)
        case .upcomingDay(let group):
            UpcomingDaySheetView(group: group, onDismiss: onDismiss)
        }
    }
}

private struct UpcomingDaySheetView: View {
    @Environment(\.dismiss) private var dismiss
    let group: UpcomingDayGroup
    let onDismiss: () -> Void

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 10) {
                    ForEach(group.items, id: \.id) { event in
                        let merchant = event.merchant?.trimmingCharacters(in: .whitespacesAndNewlines)
                        HStack(alignment: .top, spacing: 10) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(((merchant?.isEmpty == false ? merchant : "Unknown") ?? "Unknown").uppercased())
                                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                                Text([categoryLabel(event), event.cadence].compactMap { value in
                                    guard let value, !value.isEmpty else { return nil }
                                    return value
                                }.joined(separator: " • "))
                                .font(.system(size: 11, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Text(signedAmount(event))
                                .font(.system(size: 13, weight: .bold, design: .rounded))
                                .foregroundStyle(isIncome(event) ? .green : .red)
                        }
                        .padding(12)
                        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Color.black.opacity(0.05), lineWidth: 1))
                    }
                }
                .padding(16)
            }
            .navigationTitle(group.date)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Close") { close() }
                }
            }
        }
    }

    private func categoryLabel(_ event: UpcomingEventPayload) -> String? {
        if let category = event.category, !category.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return category
        }
        if let type = event.type, !type.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return type.capitalized
        }
        return "Unassigned"
    }

    private func isIncome(_ event: UpcomingEventPayload) -> Bool {
        let type = (event.type ?? "").lowercased()
        let cadence = (event.cadence ?? "").lowercased()
        return type == "income" || cadence == "paycheck" || cadence == "interest"
    }

    private func signedAmount(_ event: UpcomingEventPayload) -> String {
        "\(isIncome(event) ? "+" : "-")\(moneyValue(abs(event.amount ?? 0)))"
    }

    private func close() {
        dismiss()
        onDismiss()
    }
}

struct TransactionInspectSheetView: View {
    @Environment(\.dismiss) private var dismiss
    let transaction: TransactionItem
    let onDismiss: () -> Void
    let onRefresh: () -> Void

    @State private var detail: TransactionDetailPayload?
    @State private var categoryText = ""
    @State private var statusText = "posted"
    @State private var postedDateText = ""
    @State private var metaEditing = false
    @State private var statusMessage = ""
    @State private var showDeleteConfirm = false
    @State private var showInvertConfirm = false
    @State private var isSaving = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    sheetSection(title: "Transaction") {
                        VStack(alignment: .leading, spacing: 10) {
                            txKV(label: "Merchant", value: detail?.merchant.isEmpty == false ? detail?.merchant ?? transaction.merchant : transaction.merchant)
                            txKV(label: "Account", value: detail?.card ?? transaction.card ?? "—")
                            txKV(label: "Amount", value: moneyValue(detail?.amount ?? transaction.amount), valueColor: (detail?.amount ?? transaction.amount) >= 0 ? .red : .green)
                            txKV(label: "Date", value: detail?.postedDate ?? transaction.postedDate ?? transaction.dateISO ?? "—")
                            txKV(label: "Matches", value: detail?.categoryRulePattern ?? (detail?.category ?? transaction.category ?? "—"))
                        }
                    }

                    sheetSection(title: "Category") {
                        VStack(alignment: .leading, spacing: 8) {
                            TextField("Set category", text: $categoryText)
                                .font(.system(size: 13, weight: .medium, design: .rounded))
                                .padding(.horizontal, 10)
                                .padding(.vertical, 10)
                                .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))

                            Button("Save category") { Task { await saveCategory() } }
                                .buttonStyle(PrimaryButtonStyle())
                                .disabled(isSaving)
                        }
                    }

                    sheetSection(title: "Details") {
                        VStack(alignment: .leading, spacing: 10) {
                            if metaEditing {
                                Picker("Status", selection: $statusText) {
                                    Text("posted").tag("posted")
                                    Text("pending").tag("pending")
                                }
                                .pickerStyle(.segmented)

                                TextField("MM/DD/YYYY or unknown", text: $postedDateText)
                                    .font(.system(size: 13, weight: .medium, design: .rounded))
                                    .padding(.horizontal, 10)
                                    .padding(.vertical, 10)
                                    .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))

                                HStack(spacing: 8) {
                                    Button("Save status/date") { Task { await saveMeta() } }
                                        .buttonStyle(PrimaryButtonStyle())
                                    Button("Cancel") {
                                        resetMetaFields()
                                        metaEditing = false
                                    }
                                    .buttonStyle(HomeHeaderActionStyle(primary: false))
                                }
                            } else {
                                txDetailRow(label: "Bank", value: detail?.bank ?? transaction.bank ?? "—")
                                txDetailRow(label: "Card", value: detail?.card ?? transaction.card ?? "—")
                                txDetailRow(label: "Status", value: detail?.status ?? transaction.status ?? "posted")
                                txDetailRow(label: "Account type", value: detail?.accountType ?? transaction.accountType ?? "—")
                                txDetailRow(label: "Ignored", value: (detail?.isIgnored ?? false) ? "Yes" : "No")
                            }
                        }
                    }

                    sheetSection(title: "Actions") {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack(spacing: 8) {
                                Button(metaEditing ? "Close edit" : "Edit status/date") {
                                    metaEditing.toggle()
                                    if !metaEditing { resetMetaFields() }
                                }
                                .buttonStyle(HomeHeaderActionStyle(primary: false))

                                Button("Invert amount") { showInvertConfirm = true }
                                    .buttonStyle(HomeHeaderActionStyle(primary: false))
                            }

                            HStack(spacing: 8) {
                                Button((detail?.isIgnored ?? false) ? "Unignore" : "Ignore") {
                                    Task { await toggleIgnore() }
                                }
                                .buttonStyle(HomeHeaderActionStyle(primary: false))

                                Button("Delete") { showDeleteConfirm = true }
                                    .buttonStyle(HomeHeaderActionStyle(primary: true))
                            }
                        }
                    }

                    if !statusMessage.isEmpty {
                        Text(statusMessage)
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(16)
            }
            .navigationTitle("Transaction")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Close") { close() }
                }
            }
        }
        .task { await load() }
        .confirmationDialog("Delete this transaction?", isPresented: $showDeleteConfirm, titleVisibility: .visible) {
            Button("Delete", role: .destructive) { Task { await deleteTransaction() } }
            Button("Cancel", role: .cancel) {}
        }
        .confirmationDialog("Invert this transaction amount?", isPresented: $showInvertConfirm, titleVisibility: .visible) {
            Button("Invert", role: .destructive) { Task { await invertAmount() } }
            Button("Cancel", role: .cancel) {}
        }
    }

    private func sheetSection<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 16, weight: .bold, design: .rounded))
            content()
        }
        .padding(14)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Color.black.opacity(0.05), lineWidth: 1))
    }

    private func txKV(label: String, value: String, valueColor: Color = .primary) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(label)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .frame(width: 74, alignment: .leading)
            Text(value)
                .font(.system(size: 13, weight: .medium, design: .rounded))
                .foregroundStyle(valueColor)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
        }
    }

    private func txDetailRow(label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.system(size: 11, weight: .bold, design: .rounded))
                .foregroundStyle(.primary)
        }
    }

    private func load() async {
        do {
            let next = try await QuailCashAPI.shared.fetchTransactionDetail(txId: transaction.id)
            detail = next
            categoryText = next.category ?? transaction.category ?? ""
            statusText = (next.status ?? transaction.status ?? "posted").lowercased()
            postedDateText = next.postedDate ?? next.purchaseDate ?? transaction.postedDate ?? transaction.dateISO ?? ""
            statusMessage = ""
        } catch {
            categoryText = transaction.category ?? ""
            statusText = (transaction.status ?? "posted").lowercased()
            postedDateText = transaction.postedDate ?? transaction.dateISO ?? ""
            statusMessage = error.localizedDescription
        }
    }

    private func resetMetaFields() {
        statusText = (detail?.status ?? transaction.status ?? "posted").lowercased()
        postedDateText = detail?.postedDate ?? detail?.purchaseDate ?? transaction.postedDate ?? transaction.dateISO ?? ""
    }

    private func saveCategory() async {
        isSaving = true
        defer { isSaving = false }
        do {
            _ = try await QuailCashAPI.shared.updateTransactionCategory(txId: transaction.id, category: categoryText)
            statusMessage = "Saved."
            onRefresh()
            await load()
        } catch {
            statusMessage = "Failed to save category."
        }
    }

    private func saveMeta() async {
        isSaving = true
        defer { isSaving = false }
        do {
            _ = try await QuailCashAPI.shared.updateTransactionMeta(txId: transaction.id, status: statusText, postedDate: postedDateText)
            statusMessage = "Saved."
            metaEditing = false
            onRefresh()
            await load()
        } catch {
            statusMessage = "Failed to save metadata."
        }
    }

    private func toggleIgnore() async {
        do {
            let next = !(detail?.isIgnored ?? false)
            _ = try await QuailCashAPI.shared.ignoreTransaction(txId: transaction.id, ignored: next)
            statusMessage = next ? "Ignored from calculations." : "Included in calculations."
            onRefresh()
            await load()
        } catch {
            statusMessage = "Failed to update ignore state."
        }
    }

    private func invertAmount() async {
        do {
            _ = try await QuailCashAPI.shared.invertTransactionAmount(txId: transaction.id)
            statusMessage = "Amount inverted."
            onRefresh()
            await load()
        } catch {
            statusMessage = "Failed to invert amount."
        }
    }

    private func deleteTransaction() async {
        do {
            _ = try await QuailCashAPI.shared.deleteTransaction(txId: transaction.id)
            onDismiss()
            onRefresh()
            dismiss()
        } catch {
            statusMessage = "Failed to delete transaction."
        }
    }

    private func close() {
        dismiss()
        onDismiss()
    }
}

private struct BankInfoSheetView: View {
    @Environment(\.dismiss) private var dismiss
    let onDismiss: () -> Void
    let onRefresh: () -> Void

    @State private var payload: BankInfoPayload?
    @State private var loadError: String?
    @State private var selectedAccountID = 0
    @State private var ratePercent = ""
    @State private var effectiveDate = isoToday()
    @State private var note = ""
    @State private var saveMessage: String?
    @State private var isSaving = false

    var body: some View {
        NavigationStack {
            ZStack(alignment: .top) {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        modalHeader(
                            title: "Bank Info",
                            subtitle: loadError ?? "Last updated: \(payload?.lastUpdated ?? "—")"
                        )

                        cardSection(title: "Set a new rate", subtitle: "Account, rate, date, and note") {
                            VStack(alignment: .leading, spacing: 10) {
                                labeledMenu(title: "Account") {
                                    Picker("Account", selection: $selectedAccountID) {
                                        ForEach(payload?.accounts ?? []) { account in
                                            Text("\(account.bank) — \(account.name) (APY)").tag(account.id)
                                        }
                                        ForEach(payload?.creditCards ?? []) { card in
                                            Text("\(card.bank) — \(card.name) (APR)").tag(card.id)
                                        }
                                    }
                                }

                                modalField("Rate (%)", text: $ratePercent, keyboard: .decimalPad)
                                modalField("Effective date", text: $effectiveDate)
                                modalField("Note", text: $note)

                                HStack(spacing: 8) {
                                    Button("Save rate") { Task { await saveRate() } }
                                        .buttonStyle(PrimaryButtonStyle())
                                        .disabled(isSaving || selectedAccountID == 0)
                                    if let saveMessage, !saveMessage.isEmpty {
                                        Text(saveMessage)
                                            .font(.system(size: 12, weight: .medium, design: .rounded))
                                            .foregroundStyle(.secondary)
                                    }
                                }
                            }
                        }

                        cardSection(title: "Accounts", subtitle: "Savings & checking") {
                            if (payload?.accounts ?? []).isEmpty {
                                emptyCardNote("No account info saved yet.")
                            } else {
                                VStack(spacing: 8) {
                                    ForEach(payload?.accounts ?? []) { account in
                                        VStack(alignment: .leading, spacing: 8) {
                                            Text("\(account.bank) — \(account.name)")
                                                .font(.system(size: 13, weight: .semibold, design: .rounded))
                                            bankInfoGridRow(label: "Type", value: account.type.isEmpty ? "—" : account.type)
                                            bankInfoGridRow(label: "APY", value: account.apy.map { String(format: "%.2f%%", $0) } ?? "—")
                                            if let notes = account.notes, !notes.isEmpty {
                                                Text(notes)
                                                    .font(.system(size: 12, weight: .medium, design: .rounded))
                                                    .foregroundStyle(.secondary)
                                            }
                                        }
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                        .padding(12)
                                        .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                                        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
                                    }
                                }
                            }
                        }

                        cardSection(title: "Credit cards", subtitle: "APR, limits & rewards") {
                            if (payload?.creditCards ?? []).isEmpty {
                                emptyCardNote("No card info saved yet.")
                            } else {
                                VStack(spacing: 8) {
                                    ForEach(payload?.creditCards ?? []) { card in
                                        VStack(alignment: .leading, spacing: 8) {
                                            Text("\(card.bank) — \(card.name)")
                                                .font(.system(size: 13, weight: .semibold, design: .rounded))
                                            bankInfoGridRow(label: "APR", value: card.apr.map { String(format: "%.2f%%", $0) } ?? "—")
                                            bankInfoGridRow(label: "Limit", value: card.creditLimit.map(moneyValue) ?? "—")
                                            if card.benefits.isEmpty {
                                                emptyCardNote("No benefits saved.")
                                            } else {
                                                VStack(spacing: 6) {
                                                    ForEach(Array(card.benefits.enumerated()), id: \.offset) { _, benefit in
                                                        bankInfoGridRow(
                                                            label: (benefit.categories ?? []).joined(separator: ", ").isEmpty ? "Cash back" : (benefit.categories ?? []).joined(separator: ", "),
                                                            value: benefit.cashbackPercent.map { String(format: "%.2f%%", $0) } ?? "—"
                                                        )
                                                    }
                                                }
                                            }
                                        }
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                        .padding(12)
                                        .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                                        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
                                    }
                                }
                            }
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.top, 72)
                    .padding(.bottom, 16)
                }
                pinnedCloseButton
            }
            .toolbar(.hidden, for: .navigationBar)
        }
        .task { await load() }
    }

    private func modalHeader(title: String, subtitle: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 18, weight: .bold, design: .rounded))
                Text(subtitle)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var pinnedCloseButton: some View {
        VStack {
            HStack {
                Spacer()
                Button("Close") { close() }
                    .buttonStyle(HomeHeaderActionStyle(primary: false))
            }
            .padding(.horizontal, 16)
            .padding(.top, 8)
            Spacer()
        }
    }

    private func cardSection<Content: View>(title: String, subtitle: String? = nil, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 16, weight: .bold, design: .rounded))
            if let subtitle, !subtitle.isEmpty {
                Text(subtitle)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            content()
        }
        .padding(14)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Color.black.opacity(0.05), lineWidth: 1))
    }

    private func labeledMenu<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            content()
                .pickerStyle(.menu)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 10)
                .frame(height: 40)
                .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
        }
    }

    private func modalField(_ title: String, text: Binding<String>, keyboard: UIKeyboardType = .default) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            TextField(title, text: text)
                .keyboardType(keyboard)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                .padding(.horizontal, 10)
                .frame(height: 40)
                .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
        }
    }

    private func bankInfoGridRow(label: String, value: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(label)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .frame(width: 72, alignment: .leading)
            Text(value)
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func emptyCardNote(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 12, weight: .medium, design: .rounded))
            .foregroundStyle(.secondary)
    }

    private func load() async {
        do {
            let next = try await QuailCashAPI.shared.fetchBankInfo()
            payload = next
            loadError = nil
            if selectedAccountID == 0 {
                selectedAccountID = next.accounts.first?.id ?? next.creditCards.first?.id ?? 0
            }
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func saveRate() async {
        guard selectedAccountID != 0, let rate = Double(ratePercent.trimmingCharacters(in: .whitespacesAndNewlines)) else {
            saveMessage = "Pick an account and enter a rate."
            return
        }
        isSaving = true
        defer { isSaving = false }
        do {
            _ = try await QuailCashAPI.shared.setInterestRate(accountID: selectedAccountID, ratePercent: rate, effectiveDate: effectiveDate, note: note)
            saveMessage = "Saved."
            onRefresh()
            await load()
        } catch {
            saveMessage = "Save failed."
        }
    }

    private func close() {
        dismiss()
        onDismiss()
    }
}

private struct CsvImportSheetView: View {
    @Environment(\.dismiss) private var dismiss
    let onDismiss: () -> Void
    let onRefresh: () -> Void

    @State private var showFileImporter = false
    @State private var selectedFileURL: URL?
    @State private var selectedFileName = "No file selected"
    @State private var bankInfo: BankInfoPayload?
    @State private var preview: CsvPreviewPayload?
    @State private var dryRun: CsvDryRunPayload?
    @State private var importResult: CsvImportResultPayload?
    @State private var message = ""
    @State private var selectedAccountID = 0
    @State private var purchaseCol = ""
    @State private var postedCol = ""
    @State private var amountCol = ""
    @State private var debitCol = ""
    @State private var creditCol = ""
    @State private var merchantCol = ""
    @State private var indicatorCol = ""
    @State private var creditIndicatorValue = "credit"
    @State private var invertAmount = false
    @State private var isWorking = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    modalHeader

                    sectionCard(title: "Upload file") {
                        VStack(alignment: .leading, spacing: 10) {
                            VStack(alignment: .leading, spacing: 5) {
                                Text("Drag and drop CSV/Excel here")
                                    .font(.system(size: 13, weight: .bold, design: .rounded))
                                Text("or choose a file manually")
                                    .font(.system(size: 12, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(12)
                            .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                            .overlay(
                                RoundedRectangle(cornerRadius: 12, style: .continuous)
                                    .stroke(style: StrokeStyle(lineWidth: 1, dash: [5]))
                                    .foregroundStyle(Color.black.opacity(0.18))
                            )

                            HStack(spacing: 8) {
                                Button("Choose file") { showFileImporter = true }
                                    .buttonStyle(HomeHeaderActionStyle(primary: false))
                                Text(selectedFileName)
                                    .font(.system(size: 12, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                        }
                    }

                    if selectedFileURL != nil || preview != nil {
                        sectionCard(title: "Setup") {
                            VStack(alignment: .leading, spacing: 10) {
                                modalMenu("Account", selection: $selectedAccountID, choices: accountChoices)
                                Text("Header row is detected automatically from the first row.")
                                    .font(.system(size: 12, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)

                                HStack(spacing: 8) {
                                    Button("Preview file") { Task { await loadPreview() } }
                                        .buttonStyle(HomeHeaderActionStyle(primary: false))
                                        .disabled(selectedFileURL == nil || isWorking)
                                    Button("Cancel") { close() }
                                        .buttonStyle(HomeHeaderActionStyle(primary: false))
                                }
                            }
                        }
                    }

                    if let preview {
                        sectionCard(title: "Mapping") {
                            VStack(spacing: 10) {
                                mappingPicker("Transaction date", selection: $purchaseCol, columns: preview.columns)
                                mappingPicker("Posted date", selection: $postedCol, columns: preview.columns, optional: true)
                                mappingPicker("Amount", selection: $amountCol, columns: preview.columns, optional: true)
                                mappingPicker("Debit amount", selection: $debitCol, columns: preview.columns, optional: true)
                                mappingPicker("Credit amount", selection: $creditCol, columns: preview.columns, optional: true)
                                mappingPicker("Merchant", selection: $merchantCol, columns: preview.columns)
                                mappingPicker("Indicator", selection: $indicatorCol, columns: preview.columns, optional: true)

                                modalTextField("Indicator value treated as credit", text: $creditIndicatorValue)

                                Toggle("Invert all amounts", isOn: $invertAmount)
                                    .tint(.black)
                            }
                        }

                        sectionCard(title: "Preview") {
                            VStack(alignment: .leading, spacing: 10) {
                                Text("\(preview.rowCount) rows • \(preview.columnCount) columns")
                                    .font(.system(size: 12, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)

                                ScrollView(.horizontal, showsIndicators: true) {
                                    VStack(alignment: .leading, spacing: 8) {
                                        HStack(spacing: 8) {
                                            ForEach(preview.columns) { column in
                                                Text(column.label)
                                                    .font(.system(size: 11, weight: .bold, design: .rounded))
                                                    .frame(width: 140, alignment: .leading)
                                            }
                                        }

                                        ForEach(preview.previewRows) { row in
                                            HStack(spacing: 8) {
                                                ForEach(Array(row.cells.enumerated()), id: \.offset) { _, cell in
                                                    Text(cell)
                                                        .font(.system(size: 11, weight: .medium, design: .rounded))
                                                        .frame(width: 140, alignment: .leading)
                                                        .lineLimit(2)
                                                }
                                            }
                                        }
                                    }
                                }

                                HStack(spacing: 8) {
                                    Button("Dry run") { Task { await runDryRun() } }
                                        .buttonStyle(HomeHeaderActionStyle(primary: false))
                                    Button("Save mapping") { Task { await saveMapping() } }
                                        .buttonStyle(HomeHeaderActionStyle(primary: false))
                                    Button("Done") { close() }
                                        .buttonStyle(HomeHeaderActionStyle(primary: false))
                                    Button("Import") { Task { await runImport() } }
                                        .buttonStyle(PrimaryButtonStyle())
                                        .disabled(!canImport || isWorking)
                                }
                            }
                        }
                    }

                    if let dryRun {
                        sectionCard(title: "Dry run comparison") {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack(spacing: 8) {
                                    drySummaryCard(title: "Valid", value: "\(dryRun.summary?.validRows ?? 0)")
                                    drySummaryCard(title: "Invalid", value: "\(dryRun.summary?.invalidRows ?? 0)")
                                    drySummaryCard(title: "Total", value: "\(dryRun.summary?.totalRows ?? 0)")
                                }
                                if let compare = dryRun.compare {
                                    HStack(spacing: 8) {
                                        drySummaryCard(title: "Update exact", value: "\(compare.wouldUpdateExactCount ?? 0)")
                                        drySummaryCard(title: "Update tip", value: "\(compare.wouldUpdateTipCount ?? 0)")
                                        drySummaryCard(title: "Insert", value: "\(compare.wouldInsertCount ?? 0)")
                                        drySummaryCard(title: "Pending", value: "\(compare.pendingCount ?? 0)")
                                    }
                                    Text("Window \(compare.importStartDate ?? "—") to \(compare.importEndDate ?? "—")")
                                        .font(.system(size: 12, weight: .medium, design: .rounded))
                                        .foregroundStyle(.secondary)
                                }
                            }
                        }
                    }

                    if let importResult {
                        sectionCard(title: "Import result") {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Inserted \(importResult.inserted ?? 0) • Updated \(importResult.updated ?? 0) • Auto categorized \(importResult.autoCategorized ?? 0)")
                                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                                Text("Skipped \(importResult.skipped ?? 0) • Reconciled \(importResult.reconciledPendingDuplicates ?? 0) • Deleted stale pending \(importResult.stalePendingDeleted ?? 0)")
                                    .font(.system(size: 12, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }

                    if !message.isEmpty {
                        Text(message)
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(16)
            }
            .toolbar(.hidden, for: .navigationBar)
        }
        .task { await loadAccounts() }
        .fileImporter(
            isPresented: $showFileImporter,
            allowedContentTypes: [.data, .commaSeparatedText, .plainText],
            allowsMultipleSelection: false
        ) { result in
            switch result {
            case .success(let urls):
                guard let url = urls.first else { return }
                do {
                    selectedFileURL = try copyImportedFile(url)
                    selectedFileName = selectedFileURL?.lastPathComponent ?? url.lastPathComponent
                    preview = nil
                    dryRun = nil
                    importResult = nil
                    message = ""
                } catch {
                    message = error.localizedDescription
                }
            case .failure(let error):
                message = error.localizedDescription
            }
        }
    }

    private var accountChoices: [(id: Int, label: String)] {
        let accounts = (bankInfo?.accounts ?? []).map { (id: $0.id, label: "\($0.bank) — \($0.name) (APY)") }
        let cards = (bankInfo?.creditCards ?? []).map { (id: $0.id, label: "\($0.bank) — \($0.name) (APR)") }
        return accounts + cards
    }

    private var canImport: Bool {
        selectedFileURL != nil && selectedAccountID != 0 && !purchaseCol.isEmpty && !merchantCol.isEmpty && (!amountCol.isEmpty || (!debitCol.isEmpty && !creditCol.isEmpty))
    }

    private var modalHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Import CSV/Excel")
                    .font(.system(size: 18, weight: .bold, design: .rounded))
                Text("Drop a CSV or Excel file, preview it, map columns, then import.")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            Button("Close") { close() }
                .buttonStyle(HomeHeaderActionStyle(primary: false))
        }
    }

    private func sectionCard<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 16, weight: .bold, design: .rounded))
            content()
        }
        .padding(14)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Color.black.opacity(0.05), lineWidth: 1))
    }

    private func modalMenu(_ title: String, selection: Binding<Int>, choices: [(id: Int, label: String)]) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Picker(title, selection: selection) {
                ForEach(choices, id: \.id) { choice in
                    Text(choice.label).tag(choice.id)
                }
            }
            .pickerStyle(.menu)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 10)
            .frame(height: 40)
            .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
        }
    }

    private func mappingPicker(_ title: String, selection: Binding<String>, columns: [CsvPreviewColumnPayload], optional: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Picker(title, selection: selection) {
                if optional {
                    Text("Not mapped").tag("")
                }
                ForEach(columns) { column in
                    Text("\(column.label) (col \(column.index + 1))").tag(String(column.index))
                }
            }
            .pickerStyle(.menu)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 10)
            .frame(height: 40)
            .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
        }
    }

    private func modalTextField(_ title: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            TextField(title, text: text)
                .padding(.horizontal, 10)
                .frame(height: 40)
                .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
        }
    }

    private func drySummaryCard(title: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 10, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 16, weight: .bold, design: .rounded))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
    }

    private func loadAccounts() async {
        do {
            let payload = try await QuailCashAPI.shared.fetchBankInfo()
            bankInfo = payload
            if selectedAccountID == 0 {
                selectedAccountID = payload.accounts.first?.id ?? payload.creditCards.first?.id ?? 0
            }
        } catch {
            message = error.localizedDescription
        }
    }

    private func applyDefaultMappings(from preview: CsvPreviewPayload) {
        func match(_ keywords: [String]) -> String {
            let lowercased = preview.columns.map { ($0.index, $0.label.lowercased()) }
            return lowercased.first(where: { pair in
                keywords.contains(where: { pair.1.contains($0) })
            }).map { String($0.0) } ?? ""
        }

        purchaseCol = match(["transaction date", "purchase date", "date"])
        postedCol = match(["posted date"])
        amountCol = match(["amount"])
        debitCol = match(["debit"])
        creditCol = match(["credit"])
        merchantCol = match(["merchant", "description", "payee"])
        indicatorCol = match(["indicator", "type"])
    }

    private func mappingFields() -> [String: String] {
        var fields: [String: String] = [
            "account_id": String(selectedAccountID),
            "purchase_col": purchaseCol,
            "merchant_col": merchantCol,
            "delimiter": "auto",
            "header_row": "1",
            "data_start_row": "2",
            "invert_amount": invertAmount ? "true" : "false",
            "credit_indicator_value": creditIndicatorValue,
        ]
        if !postedCol.isEmpty { fields["posted_col"] = postedCol }
        if !amountCol.isEmpty { fields["amount_col"] = amountCol }
        if !debitCol.isEmpty { fields["debit_col"] = debitCol }
        if !creditCol.isEmpty { fields["credit_col"] = creditCol }
        if !indicatorCol.isEmpty { fields["indicator_col"] = indicatorCol }
        return fields
    }

    private func saveMapping() async {
        guard canImport else {
            message = "Choose a file, account, and required columns first."
            return
        }
        isWorking = true
        defer { isWorking = false }
        do {
            var payload: [String: Any] = [
                "purchase_col": Int(purchaseCol) ?? 0,
                "merchant_col": Int(merchantCol) ?? 0,
                "credit_indicator_value": creditIndicatorValue,
                "invert_amount": invertAmount,
            ]
            if let value = Int(postedCol) { payload["posted_col"] = value }
            if let value = Int(amountCol) { payload["amount_col"] = value }
            if let value = Int(debitCol) { payload["debit_col"] = value }
            if let value = Int(creditCol) { payload["credit_col"] = value }
            if let value = Int(indicatorCol) { payload["indicator_col"] = value }
            try await QuailCashAPI.shared.saveCsvMappingPreset(accountID: selectedAccountID, preset: payload)
            message = "Mapping saved."
        } catch {
            message = error.localizedDescription
        }
    }

    private func loadPreview() async {
        guard let selectedFileURL else {
            message = "Pick a file first."
            return
        }
        isWorking = true
        defer { isWorking = false }
        do {
            let next = try await QuailCashAPI.shared.fetchCsvPreview(fileURL: selectedFileURL)
            preview = next
            dryRun = nil
            importResult = nil
            applyDefaultMappings(from: next)
            message = "Preview loaded."
        } catch {
            message = error.localizedDescription
        }
    }

    private func runDryRun() async {
        guard let selectedFileURL, canImport else {
            message = "Complete the required mapping first."
            return
        }
        isWorking = true
        defer { isWorking = false }
        do {
            dryRun = try await QuailCashAPI.shared.runCsvDryRun(fileURL: selectedFileURL, fields: mappingFields())
            message = "Dry run complete."
        } catch {
            message = error.localizedDescription
        }
    }

    private func runImport() async {
        guard let selectedFileURL, canImport else {
            message = "Complete the required mapping first."
            return
        }
        isWorking = true
        defer { isWorking = false }
        do {
            importResult = try await QuailCashAPI.shared.importCsvMapped(fileURL: selectedFileURL, fields: mappingFields())
            message = "Import complete."
            onRefresh()
        } catch {
            message = error.localizedDescription
        }
    }

    private func copyImportedFile(_ url: URL) throws -> URL {
        let scoped = url.startAccessingSecurityScopedResource()
        defer {
            if scoped { url.stopAccessingSecurityScopedResource() }
        }
        let fileManager = FileManager.default
        let ext = url.pathExtension.isEmpty ? "dat" : url.pathExtension
        let tempURL = fileManager.temporaryDirectory.appendingPathComponent("csv-import-\(UUID().uuidString).\(ext)")
        if fileManager.fileExists(atPath: tempURL.path) {
            try fileManager.removeItem(at: tempURL)
        }
        try fileManager.copyItem(at: url, to: tempURL)
        return tempURL
    }

    private func close() {
        dismiss()
        onDismiss()
    }
}

private struct UnassignedWizardSheetView: View {
    @Environment(\.dismiss) private var dismiss
    let onDismiss: () -> Void
    let onRefresh: () -> Void

    private struct DeferredRule: Hashable {
        let category: String
        let keywords: [String]
    }

    @State private var mode: UnassignedMode = .freq
    @State private var rows: [UnassignedTransactionPayload] = []
    @State private var categories: [String] = []
    @State private var index = 0
    @State private var categoryText = ""
    @State private var keywordsText = ""
    @State private var skipped: [UnassignedTransactionPayload] = []
    @State private var pendingDeferredRules: [DeferredRule] = []
    @State private var deferApplyUntilClose = false
    @State private var skippedOpen = false
    @State private var message = ""
    @State private var isLoading = false

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 14) {
                modalHeader

                sectionCard(title: "Current transaction") {
                    if let current {
                        VStack(alignment: .leading, spacing: 10) {
                            txKV(label: "Merchant", value: current.merchant.isEmpty ? "Unknown" : current.merchant)
                            txKV(label: "Account", value: [current.bank, current.card].compactMap { $0 }.joined(separator: " • "))
                            txKV(label: "Amount", value: moneyValue(current.amount), valueColor: current.amount >= 0 ? .red : .green)
                            txKV(label: "Date", value: current.postedDate ?? "—")
                            txKV(label: "Matches", value: current.usageCount.map(String.init) ?? "—")
                        }
                    } else {
                        Text("No unassigned transactions right now.")
                            .font(.system(size: 13, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }

                sectionCard(title: "Create rule") {
                    VStack(alignment: .leading, spacing: 10) {
                        Toggle("Defer apply until close", isOn: $deferApplyUntilClose)
                            .font(.system(size: 12, weight: .semibold, design: .rounded))
                            .tint(.black)

                        HStack(spacing: 8) {
                            fieldShell(title: "Category") {
                                TextField("Start typing…", text: $categoryText)
                                    .textInputAutocapitalization(.never)
                                    .autocorrectionDisabled(true)
                            }
                            Menu {
                                ForEach(categories, id: \.self) { category in
                                    Button(category) { categoryText = category }
                                }
                            } label: {
                                Text("Choose")
                            }
                            .buttonStyle(HomeHeaderActionStyle(primary: false))
                        }

                        fieldShell(title: "Keywords (comma separated)") {
                            TextField("amazon, prime", text: $keywordsText)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled(true)
                        }

                        VStack(alignment: .leading, spacing: 10) {
                            HStack(alignment: .center, spacing: 8) {
                                Button("Skip") { Task { await skipCurrent() } }
                                    .buttonStyle(UnassignedEqualActionStyle(primary: false))
                                    .disabled(current == nil || isLoading)
                                Button("View skipped (\(skipped.count))") { skippedOpen.toggle() }
                                    .buttonStyle(UnassignedEqualActionStyle(primary: false))
                                Button("Save rule") { Task { await saveRule() } }
                                    .buttonStyle(UnassignedEqualActionStyle(primary: true))
                                    .disabled(current == nil || isLoading)
                            }
                        }
                        .padding(10)
                        .background(Color.white.opacity(0.65), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(.black.opacity(0.05), lineWidth: 1))
                    }
                }

                sectionCard(title: "Queue") {
                    HStack(spacing: 10) {
                        Button("Prev") { move(-1) }
                            .buttonStyle(UnassignedQueueNavStyle())
                            .disabled(index == 0 || rows.isEmpty)
                        Spacer(minLength: 0)
                        VStack(spacing: 3) {
                            Text("Queue")
                                .font(.system(size: 13, weight: .bold, design: .rounded))
                            Text(rows.isEmpty ? "0 / 0" : "\(index + 1) / \(rows.count)")
                                .font(.system(size: 12, weight: .semibold, design: .rounded))
                                .foregroundStyle(.secondary)
                            if !pendingDeferredRules.isEmpty {
                                Text("Queued \(pendingDeferredRules.count)")
                                    .font(.system(size: 11, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .frame(maxWidth: .infinity)
                        Spacer(minLength: 0)
                        Button("Next") { move(1) }
                            .buttonStyle(UnassignedQueueNavStyle())
                            .disabled(rows.isEmpty)
                    }

                    if skippedOpen {
                        if skipped.isEmpty {
                            Text("No skipped transactions.")
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                        } else {
                            VStack(spacing: 8) {
                                ForEach(Array(skipped.enumerated()), id: \.element.id) { offset, tx in
                                    HStack(alignment: .top, spacing: 10) {
                                        VStack(alignment: .leading, spacing: 4) {
                                            Text(tx.merchant.isEmpty ? "Unknown" : tx.merchant)
                                                .font(.system(size: 12, weight: .semibold, design: .rounded))
                                            Text([moneyValue(tx.amount), tx.postedDate ?? ""].filter { !$0.isEmpty }.joined(separator: " • "))
                                                .font(.system(size: 11, weight: .medium, design: .rounded))
                                                .foregroundStyle(.secondary)
                                        }
                                        Spacer()
                                        Button("Use") { restoreSkipped(at: offset) }
                                            .buttonStyle(HomeHeaderActionStyle(primary: false))
                                    }
                                    .padding(10)
                                    .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
                                }
                            }
                        }
                    }
                }

                if !message.isEmpty {
                    Text(message)
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 0)
            }
            .padding(16)
            .toolbar(.hidden, for: .navigationBar)
        }
        .task {
            await loadCategories()
            await loadRows(resetIndex: true)
        }
    }

    private var modalHeader: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Create rule")
                        .font(.system(size: 18, weight: .bold, design: .rounded))
                    Text(rows.isEmpty ? "0 / 0" : "\(index + 1) / \(rows.count)")
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 8)
                Button("Close") { Task { await close() } }
                    .buttonStyle(HomeHeaderActionStyle(primary: false))
            }

            modeTabs
        }
    }

    private var modeTabs: some View {
        HStack(spacing: 0) {
            modeTabButton(title: "Most frequent", value: .freq)
            modeTabButton(title: "Most recent", value: .recent)
        }
        .padding(.top, 2)
    }

    private var current: UnassignedTransactionPayload? {
        guard index >= 0, index < rows.count else { return nil }
        return rows[index]
    }

    private func sectionCard<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 16, weight: .bold, design: .rounded))
            content()
        }
        .padding(14)
        .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Color.black.opacity(0.05), lineWidth: 1))
    }

    private func fieldShell<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            content()
                .padding(.horizontal, 10)
                .frame(height: 40)
                .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
        }
    }

    private func modeTabButton(title: String, value: UnassignedMode) -> some View {
        Button(title) {
            guard mode != value else { return }
            mode = value
            Task { await loadRows(resetIndex: true) }
        }
        .font(.system(size: 12, weight: .semibold, design: .rounded))
        .frame(maxWidth: .infinity)
        .frame(height: 38)
        .background(
            ZStack(alignment: .bottom) {
                Color.clear
                Rectangle()
                    .fill(mode == value ? Color.black : Color.black.opacity(0.12))
                    .frame(height: mode == value ? 2 : 1)
            }
        )
        .overlay(
            Rectangle()
                .stroke(Color.black.opacity(0.08), lineWidth: 0.5)
        )
        .foregroundStyle(mode == value ? .primary : .secondary)
        .buttonStyle(.plain)
    }

    private func txKV(label: String, value: String, valueColor: Color = .primary) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(label)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .frame(width: 74, alignment: .leading)
            Text(value.isEmpty ? "—" : value)
                .font(.system(size: 13, weight: .medium, design: .rounded))
                .foregroundStyle(valueColor)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func loadCategories() async {
        do {
            categories = try await QuailCashAPI.shared.fetchCategories()
        } catch {
            message = error.localizedDescription
        }
    }

    private func loadRows(resetIndex: Bool) async {
        isLoading = true
        defer { isLoading = false }
        do {
            rows = try await QuailCashAPI.shared.fetchUnassigned(limit: 25, mode: mode)
            if resetIndex || index >= rows.count {
                index = 0
            }
            if rows.isEmpty {
                message = "No unassigned transactions right now."
            } else if message == "No unassigned transactions right now." {
                message = ""
            }
        } catch {
            message = error.localizedDescription
        }
    }

    private func toggleMode() {
        mode = mode == .freq ? .recent : .freq
        Task { await loadRows(resetIndex: true) }
    }

    private func move(_ delta: Int) {
        guard !rows.isEmpty else { return }
        index = min(max(0, index + delta), rows.count - 1)
    }

    private func removeCurrentAndAdvance() async {
        guard !rows.isEmpty else { return }
        rows.remove(at: index)
        categoryText = ""
        keywordsText = ""
        if index >= rows.count {
            index = max(0, rows.count - 1)
        }
        if rows.isEmpty {
            await loadRows(resetIndex: true)
        }
    }

    private func skipCurrent() async {
        guard let current else { return }
        skipped.append(current)
        await removeCurrentAndAdvance()
        if rows.isEmpty {
            message = "No additional unassigned transactions right now."
        } else {
            message = "Transaction skipped."
        }
    }

    private func restoreSkipped(at index: Int) {
        guard skipped.indices.contains(index) else { return }
        let tx = skipped.remove(at: index)
        rows.insert(tx, at: min(self.index, rows.count))
        self.index = min(self.index, rows.count - 1)
        if rows.isEmpty == false {
            message = ""
        }
    }

    private func parsedKeywords() -> [String] {
        keywordsText
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    private func saveRule() async {
        let category = categoryText.trimmingCharacters(in: .whitespacesAndNewlines)
        let keywords = parsedKeywords()

        guard !category.isEmpty else {
            message = "Enter a category."
            return
        }
        guard !keywords.isEmpty else {
            message = "Enter at least one keyword."
            return
        }

        if deferApplyUntilClose {
            pendingDeferredRules.append(DeferredRule(category: category, keywords: keywords))
            message = "Queued \(pendingDeferredRules.count) rule(s) for apply on close."
            await removeCurrentAndAdvance()
            return
        }

        isLoading = true
        defer { isLoading = false }
        do {
            let job = try await QuailCashAPI.shared.createCategoryRule(category: category, keywords: keywords, applyNow: true)
            if let job {
                message = "Saved. Applying rule..."
                try await waitForApplyJob(job.id)
            }
            onRefresh()
            await removeCurrentAndAdvance()
            if !rows.isEmpty {
                message = "Rule saved."
            }
        } catch {
            message = error.localizedDescription
        }
    }

    private func flushDeferredRules() async throws {
        guard !pendingDeferredRules.isEmpty else { return }
        let queued = pendingDeferredRules
        pendingDeferredRules = []
        var failures: [DeferredRule] = []
        for rule in queued {
            do {
                if let job = try await QuailCashAPI.shared.createCategoryRule(category: rule.category, keywords: rule.keywords, applyNow: true) {
                    try await waitForApplyJob(job.id)
                }
            } catch {
                failures.append(rule)
            }
        }
        if !failures.isEmpty {
            pendingDeferredRules = failures
            throw NSError(domain: "QuailCashAPI", code: 3, userInfo: [NSLocalizedDescriptionKey: "Failed to save \(failures.count) deferred rule(s)."])
        }
    }

    private func waitForApplyJob(_ jobID: Int) async throws {
        let deadline = Date().addingTimeInterval(90)
        while Date() < deadline {
            let job = try await QuailCashAPI.shared.fetchCategoryRuleJob(jobID: jobID)
            let status = (job.status ?? "").lowercased()
            if status == "completed" {
                message = "Applied to \(job.totalApplied ?? 0) transactions."
                return
            }
            if status == "failed" {
                throw NSError(domain: "QuailCashAPI", code: 1, userInfo: [NSLocalizedDescriptionKey: job.error ?? "Rule apply failed."])
            }
            try await Task.sleep(nanoseconds: 1_200_000_000)
        }
        throw NSError(domain: "QuailCashAPI", code: 2, userInfo: [NSLocalizedDescriptionKey: "Rule apply timed out."])
    }

    private func close() async {
        if !categoryText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !parsedKeywords().isEmpty {
            await saveRule()
            if isLoading { return }
        }
        if !pendingDeferredRules.isEmpty {
            message = "Saving \(pendingDeferredRules.count) deferred rule(s)..."
            do {
                try await flushDeferredRules()
                onRefresh()
            } catch {
                message = error.localizedDescription
                return
            }
        }
        dismiss()
        onDismiss()
    }
}

private struct UnassignedEqualActionStyle: ButtonStyle {
    let primary: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 11, weight: .semibold, design: .rounded))
            .frame(maxWidth: .infinity)
            .frame(height: 34)
            .background(
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .fill(primary ? Color.black : Color.black.opacity(0.04))
                    .opacity(configuration.isPressed ? 0.82 : 1.0)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .stroke(Color.black.opacity(primary ? 0.0 : 0.08), lineWidth: 1)
            )
            .foregroundStyle(primary ? .white : .primary)
    }
}

private struct UnassignedQueueNavStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .semibold, design: .rounded))
            .frame(minWidth: 72)
            .frame(height: 36)
            .background(
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .fill(Color.black.opacity(configuration.isPressed ? 0.08 : 0.04))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .stroke(Color.black.opacity(0.08), lineWidth: 1)
            )
            .foregroundStyle(.primary)
    }
}

private enum HomePopup: Identifiable {
    case incomeBreakdown
    case spentBreakdown
    case extraSavedBreakdown
    case bankInfo
    case transaction(TransactionItem)
    case verifyAccount(BankAccountPayload)
    case auditAccount(BankAccountPayload)

    var id: String {
        switch self {
        case .incomeBreakdown:
            return "incomeBreakdown"
        case .spentBreakdown:
            return "spentBreakdown"
        case .extraSavedBreakdown:
            return "extraSavedBreakdown"
        case .bankInfo:
            return "bankInfo"
        case .transaction(let tx):
            return "tx-\(tx.id)"
        case .verifyAccount(let account):
            return "verify-\(account.id)"
        case .auditAccount(let account):
            return "audit-\(account.id)"
        }
    }
}

private func homeDateFromISO(_ iso: String) -> Date? {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter.date(from: iso)
}

private func homeWeekdayShort(_ date: Date) -> String {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.dateFormat = "EEE"
    return formatter.string(from: date)
}

private func homeMonthDayShort(_ date: Date) -> String {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.dateFormat = "MM/dd"
    return formatter.string(from: date)
}

private func isoToday() -> String {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter.string(from: Date())
}

private struct PopupChrome<Content: View>: View {
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

private func moneyValue(_ value: Double) -> String {
    let formatter = NumberFormatter()
    formatter.numberStyle = .currency
    formatter.currencyCode = "USD"
    formatter.maximumFractionDigits = 2
    formatter.minimumFractionDigits = 2
    return formatter.string(from: NSNumber(value: value)) ?? "$\(value)"
}

private func formatAccountBalance(_ value: Double) -> String {
    let amount = abs(value)
    let raw = moneyValue(amount)
    if value > 0 { return "CR \(raw)" }
    if value < 0 { return raw }
    return moneyValue(0)
}

private struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .bold, design: .rounded))
            .padding(.horizontal, 12)
            .frame(height: 34)
            .foregroundStyle(.white)
            .background(
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .fill(.black)
                    .opacity(configuration.isPressed ? 0.78 : 1.0)
            )
    }
}

private struct AccountChipStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 11, weight: .semibold, design: .rounded))
            .padding(.horizontal, 9)
            .padding(.vertical, 6)
            .background(
                Capsule(style: .continuous)
                    .fill(Color.white)
                    .opacity(configuration.isPressed ? 0.8 : 1.0)
            )
            .overlay(
                Capsule(style: .continuous)
                    .stroke(.black.opacity(0.08), lineWidth: 1)
            )
            .foregroundStyle(.primary)
    }
}

private struct HomeHeaderActionStyle: ButtonStyle {
    let primary: Bool

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 11, weight: .semibold, design: .rounded))
            .padding(.horizontal, 10)
            .frame(height: 30)
            .background(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(primary ? Color.black : Color.black.opacity(0.04))
                    .opacity(configuration.isPressed ? 0.8 : 1.0)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(Color.black.opacity(primary ? 0.0 : 0.08), lineWidth: 1)
            )
            .foregroundStyle(primary ? .white : .primary)
    }
}
    private struct CategorySummary {
        let label: String
        let amount: String
        let color: Color
        let total: Double
    }
