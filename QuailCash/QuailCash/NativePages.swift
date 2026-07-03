import SwiftUI
import WebKit
import Combine
import Charts

private func nativePagesPalette() -> QuailThemePalette {
    QuailTheme.palette(for: UserDefaults.standard.string(forKey: "quail.settings.theme") ?? "system")
}

enum AppRoute: Hashable {
    case dashboard
    case dashboardSettings
    case home
    case fitness
    case fitnessSettings
    case fitnessNotifications
    case fitnessGoals
    case vehicle
    case vehicleSettings
    case vehicleNotifications
    case spending
    case map
    case mapSettings
    case mapTripAnalytics
    case savedPlaces
    case adminDashboard
    case bugLogger
    case projects
    case settings
    case setupWizard
    case parserWizard
    case incomeWizard
    case notificationSettings
    case notifications
    case budget
    case analytics
    case recurring
    case allTransactions
    case bankInfo
    case csvImport
    case importQueue
    case ruleBuilder
    case category(String)
    case account(BankAccountPayload, audit: Bool)
}

struct NativePageView: View {
    let route: AppRoute

    var body: some View {
        Group {
            switch route {
            case .dashboard:
                DashboardPageView()
            case .dashboardSettings:
                DashboardSettingsPageView()
            case .home:
                HomeView()
            case .fitness:
                FitnessPageView()
            case .fitnessSettings:
                QuailFitnessSettingsPageView()
            case .fitnessNotifications:
                QuailFitnessNotificationsPageView()
            case .fitnessGoals:
                FitnessGoalsPageView()
            case .vehicle:
                VehiclePageView()
            case .vehicleSettings:
                QuailCarSettingsPageView()
            case .vehicleNotifications:
                QuailCarNotificationsPageView()
            case .spending:
                NativeSpendingPageView()
            case .map:
                RouteMapPageView()
            case .mapSettings:
                MapSettingsPageView()
            case .mapTripAnalytics:
                MapTripAnalyticsPageView()
            case .savedPlaces:
                SavedPlacesPageView()
            case .adminDashboard:
                AdminDashboardPageView()
            case .bugLogger:
                BugLoggerPageView()
            case .projects:
                ProjectsPageView()
            case .settings:
                SettingsHomePageView()
            case .setupWizard:
                InitialSetupPageView()
            case .parserWizard:
                ParserWizardPageView()
            case .incomeWizard:
                IncomeWizardPageView()
            case .notificationSettings:
                NotificationSettingsPageView()
            case .notifications:
                NotificationsPageView()
            case .budget:
                NativeBudgetPageView()
            case .analytics:
                NativeAnalyticsPageView()
            case .recurring:
                NativeRecurringPageView()
            case .allTransactions:
                NativeAllTransactionsPageView()
            case .bankInfo:
                BankInfoPageView()
            case .csvImport:
                CsvImportPageView()
            case .importQueue:
                ImportQueuePageView()
            case .ruleBuilder:
                RuleBuilderPageView()
            case .category(let name):
                CategoryPageView(category: name)
            case .account(let account, let audit):
                NativeAccountPageView(account: account, auditMode: audit)
                    .id("account-\(account.id)-\(audit ? 1 : 0)")
            }
        }
        .toolbar(.hidden, for: .navigationBar)
    }
}

private struct RouteWebPageView: UIViewRepresentable {
    let url: URL

    func makeCoordinator() -> Coordinator {
        Coordinator(baseURL: AppConfig.apiBaseURL, token: AuthStore.token)
    }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        config.allowsInlineMediaPlayback = true

        let controller = WKUserContentController()
        if let token = AuthStore.token, !token.isEmpty {
            let escapedToken = token.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "'", with: "\\'")
            let scriptSource = """
            (() => {
              const mobileToken = '\(escapedToken)';
              const originalFetch = window.fetch.bind(window);
              window.fetch = (resource, init = {}) => {
                const headers = new Headers(init.headers || {});
                headers.set('Authorization', 'Bearer ' + mobileToken);
                if (!headers.has('Accept')) headers.set('Accept', 'application/json, text/html;q=0.9, */*;q=0.8');
                init.headers = headers;
                return originalFetch(resource, init);
              };
            })();
            """
            controller.addUserScript(WKUserScript(source: scriptSource, injectionTime: .atDocumentStart, forMainFrameOnly: false))
        }
        config.userContentController = controller

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.backgroundColor = .systemBackground
        webView.scrollView.backgroundColor = .systemBackground
        webView.load(context.coordinator.authenticatedRequest(for: url))
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        private let baseURL: URL
        private let token: String?

        init(baseURL: URL, token: String?) {
            self.baseURL = baseURL
            self.token = token
        }

        func authenticatedRequest(for url: URL) -> URLRequest {
            var request = URLRequest(url: url)
            request.cachePolicy = .reloadIgnoringLocalCacheData
            request.timeoutInterval = 60
            if let token, !token.isEmpty {
                request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                request.setValue("application/json, text/html;q=0.9, */*;q=0.8", forHTTPHeaderField: "Accept")
            }
            return request
        }

        private func shouldAuthReload(_ request: URLRequest) -> Bool {
            guard let requestURL = request.url else { return false }
            guard requestURL.scheme == baseURL.scheme,
                  requestURL.host == baseURL.host,
                  requestURL.port == baseURL.port else {
                return false
            }
            guard let token, !token.isEmpty else { return false }
            let currentAuth = request.value(forHTTPHeaderField: "Authorization") ?? ""
            return currentAuth.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            if navigationAction.targetFrame?.isMainFrame == true, shouldAuthReload(navigationAction.request) {
                decisionHandler(.cancel)
                webView.load(authenticatedRequest(for: navigationAction.request.url ?? baseURL))
                return
            }
            decisionHandler(.allow)
        }
    }
}

struct PageShell<Content: View>: View {
    let title: String
    let subtitle: String
    let refreshAction: (() async -> Void)?
    let content: Content

    @EnvironmentObject private var navigator: AppNavigator
    init(title: String, subtitle: String, refreshAction: (() async -> Void)? = nil, @ViewBuilder content: () -> Content) {
        self.title = title
        self.subtitle = subtitle
        self.refreshAction = refreshAction
        self.content = content()
    }

    var body: some View {
        AppChromeFrame(
            title: title,
            badgeValue: nil,
            selectedTab: navigator.currentTab,
            showsBottomBar: true,
            onLeadingTap: { navigator.show(.settings) },
            onTrailingTap: { navigator.show(.notifications) },
            onSelectTab: { tab in navigateTab(tab) }
        ) {
            AppPageScroll(refreshAction: refreshAction) {
                content
            }
        }
    }

    private func navigateTab(_ tab: BottomTab) {
        switch tab {
        case .home: navigator.setRoot(.home)
        case .spending: navigator.show(.spending)
        case .all: navigator.show(.allTransactions)
        case .analytics: navigator.show(.analytics)
        case .recurring: navigator.show(.recurring)
        }
    }
}

@MainActor
private final class DashboardGlanceModel: ObservableObject {
    @Published var safeToSpend: Double? = nil
    @Published var billsRemaining: Double? = nil
    @Published var daysLeft: Int = DashboardGlanceModel.calendarDaysLeft()

    func load() async {
        do {
            let home = try await QuailCashAPI.shared.fetchHome(txLimit: 1)
            safeToSpend = home.monthBudget?.safeToSpend
            billsRemaining = home.monthBudget?.billsRemaining
            daysLeft = home.monthBudget?.daysLeft ?? DashboardGlanceModel.calendarDaysLeft()
        } catch { }
    }

    private static func calendarDaysLeft() -> Int {
        let cal = Calendar.current
        let now = Date()
        guard let range = cal.range(of: .day, in: .month, for: now) else { return 0 }
        return range.count - cal.component(.day, from: now)
    }
}

@MainActor
private final class DashboardAuthModel: ObservableObject {
    @Published var isSignedIn: Bool? = nil
    @Published var showAuthSheet = false

    func checkAuth() async {
        do {
            _ = try await QuailCashAPI.shared.fetchNotificationsUnreadCount()
            isSignedIn = true
        } catch QuailCashAPIError.unauthorized {
            isSignedIn = false
        } catch {
            // network error — leave state unchanged
        }
    }

    func finishAuth() {
        showAuthSheet = false
        Task { await checkAuth() }
    }

    func cancelAuth() {
        showAuthSheet = false
    }
}

private struct DashboardApp {
    let title: String
    let icon: String
    let accent: Color
    let onTap: () -> Void
}

private struct DashboardPageView: View {
    @EnvironmentObject private var navigator: AppNavigator
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @StateObject private var authModel = DashboardAuthModel()

    private var apps: [DashboardApp] {
        let palette = QuailTheme.palette(for: themeSelection)
        return [
            DashboardApp(title: "Cash",     icon: "creditcard.fill",                       accent: palette.accent,    onTap: { navigator.setRoot(.home) }),
            DashboardApp(title: "Car",      icon: "car.fill",                              accent: .orange,           onTap: { navigator.setRoot(.vehicle) }),
            DashboardApp(title: "Fitness",  icon: "figure.strengthtraining.traditional",   accent: palette.positive,  onTap: { navigator.setRoot(.fitness) }),
            DashboardApp(title: "Maps",     icon: "map.fill",                              accent: .blue,             onTap: { navigator.setRoot(.map) }),
            DashboardApp(title: "Admin",    icon: "server.rack",                           accent: .purple,           onTap: { navigator.show(.adminDashboard) }),
            DashboardApp(title: "Bugs",     icon: "ladybug.fill",                          accent: .red,              onTap: { navigator.show(.bugLogger) }),
            DashboardApp(title: "Projects", icon: "folder.fill",                           accent: .teal,             onTap: { navigator.show(.projects) }),
        ]
    }

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        AppChromeFrame(
            title: "Quail",
            badgeValue: nil,
            selectedTab: nil,
            showsBottomBar: false,
            onLeadingTap: { navigator.show(.dashboardSettings) },
            onTrailingTap: { navigator.show(.notifications) },
            onSelectTab: { _ in }
        ) {
            VStack(spacing: 24) {
                if authModel.isSignedIn == false {
                    signInBanner(palette: palette).padding(.horizontal, 16).padding(.top, 8)
                }

                // Horizontal quick-glance strip
                DashboardGlanceStrip()

                // App icon grid
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 16), count: 4), spacing: 28) {
                    ForEach(apps, id: \.title) { app in
                        AppIconButton(app: app)
                    }
                }
                .padding(.horizontal, 24)

                Spacer()
            }
            .padding(.top, 8)
        }
        .sheet(isPresented: $authModel.showAuthSheet) {
            AuthSessionView(
                startURL: AppConfig.mobileAuthStartURL(),
                callbackScheme: AppConfig.callbackScheme,
                onAuthenticated: { authModel.finishAuth() },
                onCancel: { authModel.cancelAuth() }
            )
        }
        .task { await authModel.checkAuth() }
    }

    private func signInBanner(palette: QuailThemePalette) -> some View {
        HStack(spacing: 12) {
            Image(systemName: "person.crop.circle.badge.exclamationmark")
                .font(.system(size: 20, weight: .semibold))
                .foregroundStyle(palette.accent)
            Text("Not signed in")
                .font(.system(size: 13, weight: .semibold, design: .rounded))
            Spacer()
            Button("Sign In") { authModel.showAuthSheet = true }
                .font(.system(size: 13, weight: .bold, design: .rounded))
                .foregroundStyle(palette.primaryButtonText)
                .padding(.horizontal, 14).padding(.vertical, 7)
                .background(palette.primaryButton, in: Capsule())
        }
        .padding(12)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(palette.accent.opacity(0.3), lineWidth: 1))
    }
}

private struct AppIconButton: View {
    let app: DashboardApp

    var body: some View {
        Button(action: app.onTap) {
            VStack(spacing: 8) {
                ZStack {
                    RoundedRectangle(cornerRadius: 20, style: .continuous)
                        .fill(app.accent.gradient)
                        .frame(width: 62, height: 62)
                        .shadow(color: app.accent.opacity(0.35), radius: 6, y: 3)
                    Image(systemName: app.icon)
                        .font(.system(size: 26, weight: .semibold))
                        .foregroundStyle(.white)
                }
                Text(app.title)
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
            }
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Horizontal glance strip

private func relativeShort(_ date: Date) -> String {
    let f = RelativeDateTimeFormatter(); f.unitsStyle = .abbreviated
    return f.localizedString(for: date, relativeTo: Date())
}

private struct DashboardGlanceStrip: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var fit = FitnessStore.shared
    @ObservedObject private var car = VehicleStore.shared
    @StateObject private var cash = DashboardGlanceModel()

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 12) {
                glanceCard(icon: "creditcard.fill", title: "Cash", color: palette.accent, rows: financeRows(palette: palette), palette: palette)
                glanceCard(icon: "car.fill", title: "Car", color: .orange, rows: carRows, palette: palette)
                glanceCard(icon: "figure.strengthtraining.traditional", title: "Fitness", color: palette.positive, rows: fitnessRows, palette: palette)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 4)
        }
        .task { await cash.load() }
    }

    private func glanceCard(icon: String, title: String, color: Color, rows: [(String, String)], palette: QuailThemePalette) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: icon).font(.system(size: 11, weight: .bold)).foregroundStyle(color)
                Text(title.uppercased())
                    .font(.system(size: 10, weight: .bold, design: .rounded))
                    .foregroundStyle(.secondary)
                    .tracking(0.5)
            }
            VStack(alignment: .leading, spacing: 5) {
                ForEach(rows, id: \.0) { label, value in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(label)
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                        Spacer(minLength: 4)
                        Text(value)
                            .font(.system(size: 12, weight: .semibold, design: .rounded))
                            .lineLimit(1)
                    }
                }
            }
        }
        .padding(14)
        .frame(width: 200)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func financeRows(palette: QuailThemePalette) -> [(String, String)] {
        let spendText: String = {
            guard let s = cash.safeToSpend else { return "—" }
            return s < 0 ? "-\(moneyValue(abs(s)))" : moneyValue(s)
        }()
        let days = cash.daysLeft
        return [
            ("Safe to spend", spendText),
            ("Month closes", days == 0 ? "Today" : "in \(days)d"),
            ("Bills remaining", cash.billsRemaining.map { moneyValue($0) } ?? "—"),
        ]
    }

    private var carRows: [(String, String)] {
        let mileage = car.profile.currentMileage
        let lastFuel = car.fuelRecords.max(by: { $0.date < $1.date })
        let openCount = car.openIssues.count
        return [
            ("Odometer", mileage > 0 ? "\(mileage.formatted()) mi" : "—"),
            ("Last fillup", lastFuel.map { relativeShort($0.date) } ?? "—"),
            ("Issues", openCount == 0 ? "None" : "\(openCount) open"),
        ]
    }

    private var fitnessRows: [(String, String)] {
        let cal = Calendar.current; let now = Date()
        let sorted = fit.sessions.sorted { $0.date > $1.date }
        let weekCount = sorted.filter { cal.isDate($0.date, equalTo: now, toGranularity: .weekOfYear) }.count
        let lastDate = sorted.first?.date
        return [
            ("This week", weekCount == 0 ? "Rest" : "\(weekCount) session\(weekCount == 1 ? "" : "s")"),
            ("Last workout", lastDate.map { relativeShort($0) } ?? "—"),
            ("Active goals", "\(fit.goals.filter { $0.targetDate > now }.count)"),
        ]
    }
}


private struct DashboardModulePlaceholderPageView: View {
    @EnvironmentObject private var navigator: AppNavigator
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"

    let title: String
    let subtitle: String
    let icon: String

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        AppChromeFrame(
            title: title,
            badgeValue: nil,
            selectedTab: nil,
            showsBottomBar: false,
            onLeadingTap: { navigator.show(.settings) },
            onTrailingTap: { navigator.show(.notifications) },
            onSelectTab: { _ in }
        ) {
            AppPageScroll(contentPadding: 14) {
                VStack(alignment: .leading, spacing: 14) {
                    VStack(alignment: .leading, spacing: 10) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 20, style: .continuous)
                                .fill(palette.elevatedSurface)
                                .frame(width: 72, height: 72)
                            Image(systemName: icon)
                                .font(.system(size: 28, weight: .semibold))
                                .foregroundStyle(palette.accent)
                        }

                        Text(title)
                            .font(.system(size: 28, weight: .bold, design: .rounded))
                        Text(subtitle)
                            .font(.system(size: 14, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                    .padding(18)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).stroke(palette.border, lineWidth: 1))

                    Button {
                        navigator.setRoot(.dashboard)
                    } label: {
                        Text("Back to Dashboard")
                            .font(.system(size: 14, weight: .semibold, design: .rounded))
                            .frame(maxWidth: .infinity, minHeight: 44)
                            .foregroundStyle(palette.primaryButtonText)
                            .background(palette.primaryButton, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

// MARK: - Dashboard Settings Page

@MainActor
private func dashboardSingleTab(palette: QuailThemePalette) -> some View {
    _DashboardSingleTab(palette: palette)
}

private struct _DashboardSingleTab: View {
    let palette: QuailThemePalette
    @EnvironmentObject private var navigator: AppNavigator

    var body: some View {
        VStack(spacing: 0) {
            Rectangle().fill(palette.barDivider).frame(height: 1)
            Button {
                navigator.setRoot(.dashboard)
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: "square.grid.2x2.fill")
                        .font(.system(size: 16, weight: .semibold))
                    Text("Dashboard")
                        .font(.system(size: 15, weight: .bold, design: .rounded))
                }
                .foregroundStyle(palette.chromeIconForeground)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(palette.barBackground)
            }
            .buttonStyle(.plain)
        }
        .safeAreaPadding(.bottom)
        .background(palette.barBackground)
    }
}

private struct DashboardSettingsPageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @EnvironmentObject private var navigator: AppNavigator
    @State private var showGoogleAuth = false

    private let themes: [(String, String)] = [
        ("system", "System"), ("light", "Default (Light)"), ("dark", "Dark"),
        ("oled", "OLED Black"), ("solarized", "Solarized"), ("forest", "Forest"), ("midnight", "Midnight Blue"),
    ]

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        AppChromeFrame(
            title: "Settings",
            badgeValue: nil,
            selectedTab: nil,
            showsBottomBar: false,
            onLeadingTap: { navigator.show(.dashboardSettings) },
            onTrailingTap: { navigator.show(.notifications) },
            onSelectTab: { _ in }
        ) {
            VStack(spacing: 0) {
                AppPageScroll(contentPadding: 12) {
                    VStack(alignment: .leading, spacing: 12) {
                        dsSection(title: "Appearance") {
                            Picker("Color scheme", selection: $themeSelection) {
                                ForEach(themes, id: \.0) { Text($1).tag($0) }
                            }
                            .pickerStyle(.menu)
                            Text("Tip: System follows your device theme.")
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                        }

                        dsSection(title: "Google Gmail") {
                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("OAuth connection").font(.system(size: 14, weight: .semibold, design: .rounded))
                                    Text("Connect your Gmail to enable email transaction parsing.").font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Button { showGoogleAuth = true } label: { dsChip("Connect") }
                                    .buttonStyle(.plain)
                            }
                        }

                        dsSection(title: "Notifications") {
                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Smart notifications").font(.system(size: 14, weight: .semibold, design: .rounded))
                                    Text("Spending, fitness, and vehicle alerts.").font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                                }
                                Spacer()
                                NavigationLink(value: AppRoute.notificationSettings) {
                                    dsChip("Open")
                                }
                                .buttonStyle(.plain)
                            }
                        }

                        dsSection(title: "Advanced") {
                            HStack {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("App Settings").font(.system(size: 14, weight: .semibold, design: .rounded))
                                    Text("Cache, rules, setup, import, and admin tools.").font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                                }
                                Spacer()
                                NavigationLink(value: AppRoute.settings) {
                                    dsChip("Open")
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }

                dashboardSingleTab(palette: palette)
            }
        }
        .sheet(isPresented: $showGoogleAuth) {
            AuthSessionView(
                startURL: AppConfig.url(path: "/gmail/oauth/start", queryItems: [
                    URLQueryItem(name: "next", value: "/settings")
                ]),
                callbackScheme: AppConfig.callbackScheme,
                onAuthenticated: { showGoogleAuth = false },
                onCancel: { showGoogleAuth = false }
            )
        }
    }

    private func dsSection<C: View>(title: String, @ViewBuilder content: () -> C) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return VStack(alignment: .leading, spacing: 8) {
            Text(title.uppercased())
                .font(.system(size: 12, weight: .bold, design: .rounded))
                .foregroundStyle(.secondary)
            content()
                .padding(14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }

    private func dsChip(_ label: String) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return Text(label)
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .padding(.horizontal, 12).padding(.vertical, 10)
            .foregroundStyle(palette.primaryButtonText)
            .background(palette.primaryButton, in: Capsule(style: .continuous))
    }

}

// MARK: - Settings Page

private struct SettingsPageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @EnvironmentObject private var navigator: AppNavigator

    @State private var setupProgressText = "Loading…"
    @State private var setupProgressSubtext = ""
    @State private var setupProgressPercent = 0
    @State private var cacheVersionsText = "Loading…"
    @State private var isOwner = false
    @State private var showAdminPreview = false
    @State private var viewModeText = "Loading…"
    @State private var activeInfo: SettingsInfo?
    @State private var isRefreshingCache = false

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        PageShell(title: "Settings", subtitle: "") {
            VStack(alignment: .leading, spacing: 20) {

                // MARK: Notifications
                settingsSection(title: "Notifications") {
                    settingsRow(
                        icon: "bell.badge.fill", iconColor: .red,
                        title: "Smart Notifications",
                        subtitle: "Spending power, overspending alerts, and savings nudges"
                    ) { navigator.show(.notificationSettings) }
                }

                // MARK: Layout & Cache
                settingsSection(title: "Home") {
                    settingsRow(
                        icon: "square.grid.2x2.fill", iconColor: palette.accent,
                        title: "Customize Layout",
                        subtitle: "Rearrange and show/hide cards on the home screen"
                    ) { activeInfo = .homeLayout }

                    Divider().padding(.leading, 60)

                    settingsRow(
                        icon: "arrow.clockwise", iconColor: .orange,
                        title: "Refresh Cache",
                        subtitle: cacheVersionsText
                    ) { Task { await refreshCache() } }
                    .overlay(alignment: .trailing) {
                        if isRefreshingCache {
                            ProgressView().scaleEffect(0.75).padding(.trailing, 18)
                        }
                    }
                }

                // MARK: Widgets
                settingsSection(title: "Widgets") {
                    settingsRow(
                        icon: "apps.iphone", iconColor: .purple,
                        title: "iOS Widget Setup",
                        subtitle: "Configure home screen widget workflows and preview data"
                    ) { activeInfo = .widgetSetup }
                }

                // MARK: Setup
                settingsSection(title: "Initial Setup") {
                    // Progress bar
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(setupProgressText)
                                .font(.system(size: 13, weight: .semibold, design: .rounded))
                            Spacer()
                            Text("\(setupProgressPercent)%")
                                .font(.system(size: 13, weight: .bold, design: .rounded))
                                .foregroundStyle(setupProgressPercent == 100 ? .green : palette.accent)
                        }
                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                Capsule().fill(palette.border).frame(height: 8)
                                Capsule()
                                    .fill(LinearGradient(colors: [.green, .mint], startPoint: .leading, endPoint: .trailing))
                                    .frame(width: geo.size.width * CGFloat(min(100, setupProgressPercent)) / 100, height: 8)
                            }
                        }.frame(height: 8)
                        if !setupProgressSubtext.isEmpty {
                            Text(setupProgressSubtext)
                                .font(.system(size: 11, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(.bottom, 4)

                    Divider().padding(.leading, 0)

                    settingsRow(
                        icon: "wand.and.stars", iconColor: .indigo,
                        title: "Setup Wizard",
                        subtitle: "Walk through the initial budget and account configuration"
                    ) { activeInfo = .setupWizard }

                    Divider().padding(.leading, 60)

                    settingsRow(
                        icon: "envelope.badge.fill", iconColor: .teal,
                        title: "Email Parser Wizard",
                        subtitle: "Configure automatic transaction parsing from email"
                    ) { activeInfo = .parserWizard }

                    Divider().padding(.leading, 60)

                    settingsRow(
                        icon: "square.and.arrow.down.fill", iconColor: .green,
                        title: "CSV Import",
                        subtitle: "Import transactions from a bank CSV file"
                    ) { navigator.show(.csvImport) }

                    Divider().padding(.leading, 60)

                    settingsRow(
                        icon: "building.columns.fill", iconColor: .blue,
                        title: "Bank Info",
                        subtitle: "View and manage connected bank accounts"
                    ) { navigator.show(.bankInfo) }

                    Divider().padding(.leading, 60)

                    settingsRow(
                        icon: "apps.iphone.badge.plus", iconColor: .gray,
                        title: "External Apps",
                        subtitle: "Connect third-party apps and integrations"
                    ) { activeInfo = .externalApps }
                }

                // MARK: Rules
                settingsSection(title: "Rules") {
                    settingsRow(
                        icon: "text.badge.checkmark", iconColor: .cyan,
                        title: "Category Rules",
                        subtitle: "View matches, test regex, re-apply, disable, or delete rules"
                    ) { navigator.show(.ruleBuilder) }
                }

                // MARK: Admin (owner only)
                if isOwner {
                    settingsSection(title: "Admin") {
                        settingsRow(
                            icon: "eye.fill", iconColor: .secondary,
                            title: showAdminPreview ? "Return to Admin View" : "Preview as Non-Admin",
                            subtitle: viewModeText
                        ) {
                            showAdminPreview.toggle()
                            viewModeText = showAdminPreview ? "Previewing as non-admin" : "Admin view"
                        }

                        Divider().padding(.leading, 60)

                        settingsRow(
                            icon: "shield.lefthalf.filled", iconColor: .red,
                            title: "Owner Admin Console",
                            subtitle: "Tenant management, user approvals, and data purge"
                        ) { activeInfo = .adminConsole }
                    }
                }
            }
        }
        .task { await loadSettings() }
        .sheet(item: $activeInfo) { SettingsInfoSheetView(info: $0) }
    }

    // MARK: - Reusable components

    private func settingsSection<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title.uppercased())
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .tracking(0.5)
                .padding(.leading, 4)
            VStack(spacing: 0) {
                content()
            }
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }

    private func settingsRow(icon: String, iconColor: Color, title: String, subtitle: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 14) {
                ZStack {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(iconColor.opacity(0.15))
                        .frame(width: 38, height: 38)
                    Image(systemName: icon)
                        .font(.system(size: 17, weight: .semibold))
                        .foregroundStyle(iconColor)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                        .foregroundStyle(.primary)
                    Text(subtitle)
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    // MARK: - Data loading

    private func loadSettings() async {
        async let setupFetch: SettingsInitialSetupPayload? = try? SettingsNetworking.fetch("/settings/initial-setup-status", as: SettingsInitialSetupPayload.self)
        async let cacheFetch: SettingsCacheVersionsPayload? = try? SettingsNetworking.fetch("/settings/cache-versions", as: SettingsCacheVersionsPayload.self)
        async let flagsFetch: SettingsViewFlagsPayload? = try? SettingsNetworking.fetch("/settings/view-flags", as: SettingsViewFlagsPayload.self)

        let (setup, cache, flags) = await (setupFetch, cacheFetch, flagsFetch)

        if let s = setup {
            setupProgressPercent = s.percent ?? 0
            let c = s.counts
            setupProgressText = "\(c?.requirementsDone ?? 0) of \(c?.requirementsTotal ?? 0) setup checks complete"
            setupProgressSubtext = "CSV mapping: \(c?.accountsWithCsvMapping ?? 0)/\(c?.accountsTotal ?? 0) · Email parser: \(c?.accountsWithParser ?? 0)/\(c?.accountsExpectEmail ?? 0)"
        } else {
            setupProgressText = "Setup progress unavailable"
        }

        if let cv = cache {
            cacheVersionsText = "Home v\(cv.homeSnapshotVersion ?? 0) · Widget v\(cv.widgetVersion ?? 0)"
        } else {
            cacheVersionsText = "Tap to refresh cache"
        }

        if let f = flags {
            isOwner = f.isOwner ?? false
            viewModeText = isOwner ? "Admin view" : "Non-admin view"
        }
    }

    private func refreshCache() async {
        guard !isRefreshingCache else { return }
        isRefreshingCache = true
        defer { isRefreshingCache = false }
        if let result = try? await SettingsNetworking.fetch("/settings/refresh-home-widget-cache", method: "POST", as: SettingsRefreshCachePayload.self) {
            cacheVersionsText = "Refreshed · Home v\(result.homeSnapshotVersion ?? 0) · Widget v\(result.widgetVersion ?? 0)"
        } else {
            cacheVersionsText = "Refresh failed — tap to retry"
        }
    }
}

private struct NotificationSettingsPageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @State private var selectedTab = "finance"

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        PageShell(title: "Notifications", subtitle: "Alerts and preferences for all sections") {
            VStack(alignment: .leading, spacing: 12) {
                // Tab selector
                HStack(spacing: 6) {
                    ForEach([("finance","Finance","banknote.fill"),("fitness","Fitness","figure.run"),("vehicle","Vehicle","car.fill")], id: \.0) { id, label, icon in
                        let isSelected = selectedTab == id
                        Button { selectedTab = id } label: {
                            HStack(spacing: 5) {
                                Image(systemName: icon).font(.system(size: 12, weight: .semibold))
                                Text(label).font(.system(size: 12, weight: .semibold, design: .rounded))
                            }
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 8)
                            .foregroundStyle(isSelected ? palette.chromeIconForeground : palette.chromeIconForeground.opacity(0.60))
                            .background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(isSelected ? palette.selectedTabFill : .clear))
                            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(isSelected ? palette.border : Color.clear, lineWidth: 1))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(6)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(palette.border, lineWidth: 1))

                switch selectedTab {
                case "fitness":  FitnessNotificationsContent()
                case "vehicle":  VehicleNotificationsContent()
                default:         FinanceNotificationsContent()
                }
            }
        }
    }
}

private struct FinanceNotificationsContent: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @EnvironmentObject private var pushManager: MobilePushManager
    @State private var prefs: [String: Bool] = [:]
    @State private var userKeyStatus = "Loading..."
    @State private var iosPushStatus = "Checking iPhone push..."
    @State private var statusMessage = ""
    @State private var isSaving = false
    @State private var isSendingTest = false
    @State private var probeResult = ""

    private let rows: [(key: String, title: String, subtitle: String)] = [
        ("disable_all", "Disable all", "Turn off all notifications."),
        ("credit_usage", "Credit usage", "Alert on card usage events."),
        ("credit_usage_total", "Credit usage total", "Summarize total card usage."),
        ("budget_over", "Budget over", "Notify when spending exceeds budget."),
        ("safe_to_spend_daily", "Safe to spend daily", "Daily safe-to-spend guidance."),
        ("category_drift", "Category drift", "Watch for category shifts."),
        ("runway_warning", "Runway warning", "Warn when runway gets tight."),
        ("savings_streak", "Savings streak", "Celebrate savings streaks."),
        ("subscription_creep", "Subscription creep", "Spot recurring subscription growth."),
        ("high_spend_cooldown", "High spend cooldown", "Nudge cooldown after large spend."),
        ("small_win_reinforcement", "Small win reinforcement", "Positive reinforcement for progress."),
        ("ios_push", "iPhone push notifications", "Send notifications directly to this iPhone via APNs."),
        ("user_signup_pending", "User signup pending", "Admin notification for pending signups."),
        ("cron_error", "Cron error", "Alert on scheduled job failures."),
    ]

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        VStack(alignment: .leading, spacing: 12) {
            settingsCard(palette: palette) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Smart notifications").font(.system(size: 16, weight: .bold, design: .rounded))
                    Text("Spending power, overspending protection, and savings nudges.")
                        .font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                    Text(userKeyStatus).font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                    if MobilePushManager.isAvailable {
                        Text(iosPushStatus).font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                    } else {
                        Text("iPhone push is turned off in this build.")
                            .font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                    }
                    if MobilePushManager.isAvailable && prefs["ios_push"] == true {
                        Button { Task { await sendTestPush() } } label: {
                            Text(isSendingTest ? "Sending..." : "Send Test Push")
                                .font(.system(size: 13, weight: .semibold, design: .rounded))
                                .frame(maxWidth: .infinity, minHeight: 42)
                                .foregroundStyle(palette.secondaryButtonText)
                                .background(palette.secondaryButton, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                                .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(palette.border, lineWidth: 1))
                        }
                        .buttonStyle(.plain).disabled(isSendingTest).padding(.top, 4)
                        Button { Task { await probeEnvs() } } label: {
                            Text("Probe Environments")
                                .font(.system(size: 13, weight: .semibold, design: .rounded))
                                .frame(maxWidth: .infinity, minHeight: 42)
                                .foregroundStyle(palette.secondaryButtonText)
                                .background(palette.secondaryButton, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                                .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(palette.border, lineWidth: 1))
                        }
                        .buttonStyle(.plain).padding(.top, 4)
                        if !probeResult.isEmpty {
                            Text(probeResult).font(.system(size: 11, design: .monospaced)).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            settingsCard(palette: palette) {
                VStack(spacing: 8) {
                    ForEach(rows, id: \.key) { row in
                        HStack(spacing: 12) {
                            VStack(alignment: .leading, spacing: 3) {
                                Text(row.title).font(.system(size: 13, weight: .semibold, design: .rounded))
                                Text(row.subtitle).font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Toggle("", isOn: Binding(get: { prefs[row.key] ?? false }, set: { v in prefs[row.key] = v; Task { await savePref(key: row.key, value: v) } })).labelsHidden()
                        }
                        .padding(.vertical, 4)
                        if row.key != rows.last?.key { Divider().opacity(0.12) }
                    }
                }
            }
            if !statusMessage.isEmpty {
                Text(statusMessage).font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
            }
        }
        .task { await load() }
    }

    private func settingsCard<C: View>(palette: QuailThemePalette, @ViewBuilder content: () -> C) -> some View {
        content().padding(14).frame(maxWidth: .infinity, alignment: .leading)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func load() async {
        do {
            let out = try await SettingsNetworking.fetch("/settings/notifications", as: SettingsNotificationSettingsPayload.self)
            prefs = out.prefs
            userKeyStatus = (out.pushoverUserKey?.isEmpty == false) ? "Pushover key set." : "Pushover key not set."
            iosPushStatus = MobilePushManager.isAvailable ? iosPushStatusText(from: out) : "iPhone push is unavailable in this build."
            await pushManager.refreshAuthorizationStatus()
            // Auto-register device token if ios_push is enabled but no device registered yet
            if MobilePushManager.isAvailable && prefs["ios_push"] == true && (out.iosPushDeviceCount ?? 0) == 0 {
                _ = await pushManager.requestAuthorizationAndRegister()
            }
        } catch {
            userKeyStatus = "Notification settings unavailable."
            iosPushStatus = MobilePushManager.isAvailable ? "iPhone push status unavailable." : "iPhone push is unavailable in this build."
        }
    }

    private func savePref(key: String, value: Bool) async {
        guard !isSaving else { return }
        if key == "ios_push" && value {
            let granted = await pushManager.requestAuthorizationAndRegister()
            if !granted {
                prefs[key] = false
                iosPushStatus = "Push permission is off in iPhone Settings."
                statusMessage = "Enable notifications for QuailCash in iPhone Settings."
                return
            }
        }
        isSaving = true; defer { isSaving = false }
        do {
            let out = try await SettingsNetworking.fetch("/settings/notifications", method: "POST", jsonBody: [key: value], as: SettingsNotificationSettingsPayload.self)
            iosPushStatus = iosPushStatusText(from: out)
            if key == "ios_push" && !value { await pushManager.unregisterCurrentDevice() }
            statusMessage = "Saved."
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { if statusMessage == "Saved." { statusMessage = "" } }
        } catch { statusMessage = "Failed to save." }
    }

    private func iosPushStatusText(from payload: SettingsNotificationSettingsPayload) -> String {
        let count = max(0, payload.iosPushDeviceCount ?? 0)
        guard payload.iosPushConfigured ?? false else { return "iPhone push server is not configured yet." }
        return count == 0 ? "No iPhone devices registered." : count == 1 ? "1 iPhone registered." : "\(count) iPhones registered."
    }

    private func sendTestPush() async {
        guard !isSendingTest else { return }
        isSendingTest = true; defer { isSendingTest = false }
        do { try await QuailCashAPI.shared.sendIOSTestPush(); statusMessage = "Test push sent." }
        catch { statusMessage = error.localizedDescription.isEmpty ? "Failed to send test push." : error.localizedDescription }
    }

    private func probeEnvs() async {
        probeResult = "Probing..."
        do {
            var req = URLRequest(url: AppConfig.url(path: "/notifications/ios/test-both-envs"))
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Accept")
            if let token = AuthStore.token { req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
            let (data, _) = try await URLSession.shared.data(for: req)
            probeResult = String(data: data, encoding: .utf8) ?? "no response"
        } catch {
            probeResult = error.localizedDescription
        }
    }
}

private struct SettingsInfoSheetView: View {
    let info: SettingsInfo

    var body: some View {
        PageShell(title: info.title, subtitle: info.subtitle) {
            VStack(alignment: .leading, spacing: 12) {
                Text(info.detail)
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                Text("This is a native SwiftUI placeholder for the webapp section.")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
            }
        }
        .presentationDetents([.medium, .large])
    }
}

private enum SettingsInfo: Identifiable {
    case homeLayout
    case widgetSetup
    case setupWizard
    case parserWizard
    case externalApps
    case adminConsole

    var id: String {
        switch self {
        case .homeLayout: return "homeLayout"
        case .widgetSetup: return "widgetSetup"
        case .setupWizard: return "setupWizard"
        case .parserWizard: return "parserWizard"
        case .externalApps: return "externalApps"
        case .adminConsole: return "adminConsole"
        }
    }

    var title: String {
        switch self {
        case .homeLayout: return "Home Page Layout"
        case .widgetSetup: return "Widgets"
        case .setupWizard: return "Setup Wizard"
        case .parserWizard: return "Parser Wizard"
        case .externalApps: return "External Apps"
        case .adminConsole: return "Admin Console"
        }
    }

    var subtitle: String {
        switch self {
        case .homeLayout: return "Customize, reset, and cache refresh."
        case .widgetSetup: return "Widget preview and setup tools."
        case .setupWizard: return "Onboarding and account setup."
        case .parserWizard: return "Email parser rule maintenance."
        case .externalApps: return "Required mobile apps and downloads."
        case .adminConsole: return "Tenant and approval management."
        }
    }

    var detail: String {
        switch self {
        case .homeLayout:
            return "The native home page currently supports the layout and cache controls from the web settings page."
        case .widgetSetup:
            return "Widget setup will be ported here next. For now this is the native placeholder screen."
        case .setupWizard:
            return "The onboarding wizard can be rebuilt here as a native flow."
        case .parserWizard:
            return "Parser rule maintenance can be rebuilt here as a native flow."
        case .externalApps:
            return "This section lists the native app requirements for widget and push workflows."
        case .adminConsole:
            return "The admin console can be rebuilt here as a native flow."
        }
    }

}

private enum SettingsNetworking {
    static func request(path: String, method: String = "GET", jsonBody: [String: Any]? = nil) -> URLRequest {
        let url = AppConfig.url(path: path)
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 30
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token = AuthStore.token, !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let jsonBody {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try? JSONSerialization.data(withJSONObject: jsonBody, options: [])
        }
        return request
    }

    static func fetch<T: Decodable>(_ path: String, method: String = "GET", jsonBody: [String: Any]? = nil, as type: T.Type) async throws -> T {
        let request = request(path: path, method: method, jsonBody: jsonBody)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw QuailCashAPIError.badResponse
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: data)
    }
}

private struct NotificationsPageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @StateObject private var model = NotificationsPageViewModel()
    @State private var selectedNotification: NotificationDetailPayload?
    @State private var selectedError: AdminErrorNotificationPayload?
    @EnvironmentObject private var navigator: AppNavigator

    private var isStandaloneContext: Bool {
        switch navigator.rootRoute {
        case .map, .adminDashboard, .dashboard: return true
        default: return false
        }
    }

    private var isDashboardContext: Bool { navigator.rootRoute == .dashboard }

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        AppChromeFrame(
            title: "Notifications",
            badgeValue: nil,
            selectedTab: isStandaloneContext ? nil : navigator.currentTab,
            showsBottomBar: !isStandaloneContext,
            onLeadingTap: { navigator.goBack() },
            onSelectTab: { tab in
                switch tab {
                case .home: navigator.popToRoot()
                case .spending: navigator.show(.spending)
                case .all: navigator.show(.allTransactions)
                case .analytics: navigator.show(.analytics)
                case .recurring: navigator.show(.recurring)
                }
            }
        ) {
            VStack(spacing: 0) {
            AppPageScroll(refreshAction: { await model.load() }) {
            Group {
                if model.isLoading {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 24)
                } else if let errorMessage = model.errorMessage {
                    Text(errorMessage)
                        .foregroundStyle(.secondary)
                } else {
                    VStack(alignment: .leading, spacing: 12) {
                        if model.canViewErrors {
                            Picker("Notifications Tab", selection: $model.selectedTab) {
                                Text("General").tag(NotificationsPageViewModel.Tab.general)
                                Text("Errors").tag(NotificationsPageViewModel.Tab.errors)
                            }
                            .pickerStyle(.segmented)
                        }

                        HStack(spacing: 8) {
                            Button("Refresh") { Task { await model.load() } }
                                .buttonStyle(.bordered)

                            if model.selectedTab == .general {
                                Button("Mark All Read") { Task { await model.markAllRead() } }
                                    .buttonStyle(.bordered)
                                Button("Clear Read") { Task { await model.clearRead() } }
                                    .buttonStyle(.bordered)
                            } else {
                                Button("Clear Errors") { Task { await model.clearErrors() } }
                                    .buttonStyle(.bordered)
                            }
                        }

                        if model.selectedTab == .general {
                            if model.items.isEmpty {
                                Text("No notifications.")
                                    .foregroundStyle(.secondary)
                            } else {
                                VStack(spacing: 10) {
                                    ForEach(model.items) { item in
                                        Button {
                                            Task { selectedNotification = await model.openNotification(item.id) }
                                        } label: {
                                            notificationRow(item)
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                            }
                        } else if model.errorItems.isEmpty {
                            Text("No captured errors.")
                                .foregroundStyle(.secondary)
                        } else {
                            VStack(spacing: 10) {
                                ForEach(model.errorItems) { item in
                                    Button {
                                        selectedError = item
                                    } label: {
                                        errorRow(item)
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                    }
                }
            }
            }
            if isDashboardContext {
                dashboardSingleTab(palette: palette)
            }
            }
        }
        .task { await model.load() }
        .sheet(item: $selectedNotification) { detail in
            NotificationDetailSheetView(
                detail: detail,
                onDismissNotification: {
                    Task {
                        await model.dismiss(detail.id)
                        selectedNotification = nil
                    }
                },
                onApprovePendingUser: {
                    Task {
                        if let pendingUserID = await model.pendingUserID(for: detail) {
                            await model.approvePendingUser(id: pendingUserID, notificationID: detail.id)
                            selectedNotification = nil
                        }
                    }
                }
            )
        }
        .sheet(item: $selectedError) { error in
            AdminErrorDetailSheetView(error: error)
        }
    }

    private func notificationRow(_ item: NotificationItemPayload) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(item.sender ?? "System")
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)
                Spacer()
                Text(item.createdAtLocal ?? "")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            Text(item.subject ?? "(no subject)")
                .font(.system(size: 14, weight: .semibold, design: .rounded))
                .foregroundStyle(.primary)
                .frame(maxWidth: .infinity, alignment: .leading)
            if let kind = item.kind, !kind.isEmpty {
                Text(kind)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(item.isRead == false ? palette.border.opacity(2.0) : palette.border, lineWidth: 1))
    }

    private func errorRow(_ item: AdminErrorNotificationPayload) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("\(item.statusCode ?? 0) \(item.method ?? "") \(item.path ?? "")")
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                Spacer()
                Text(item.createdAt ?? "")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Text(item.errorMessage ?? "Server error")
                .font(.system(size: 14, weight: .semibold, design: .rounded))
                .foregroundStyle(.primary)
                .frame(maxWidth: .infinity, alignment: .leading)
            Text(item.userEmail ?? "unknown user")
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

@MainActor
private final class NotificationsPageViewModel: ObservableObject {
    enum Tab {
        case general
        case errors
    }

    @Published var items: [NotificationItemPayload] = []
    @Published var errorItems: [AdminErrorNotificationPayload] = []
    @Published var canViewErrors = false
    @Published var selectedTab: Tab = .general
    @Published var errorMessage: String?
    @Published var isLoading = false

    private let api = QuailCashAPI.shared

    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            items = try await api.fetchNotifications(limit: 100)
            do {
                errorItems = try await api.fetchAdminErrorNotifications(limit: 200)
                canViewErrors = true
            } catch QuailCashAPIError.unauthorized {
                canViewErrors = false
                errorItems = []
                selectedTab = .general
            }
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func openNotification(_ id: Int) async -> NotificationDetailPayload? {
        do {
            let detail = try await api.fetchNotificationDetail(id: id)
            try await api.markNotificationRead(id: id)
            if let index = items.firstIndex(where: { $0.id == id }) {
                items[index] = NotificationItemPayload(
                    id: items[index].id,
                    kind: items[index].kind,
                    subject: items[index].subject,
                    sender: items[index].sender,
                    createdAt: items[index].createdAt,
                    createdAtLocal: items[index].createdAtLocal,
                    isRead: true
                )
            }
            return detail
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func markAllRead() async {
        do {
            try await api.markAllNotificationsRead()
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func clearRead() async {
        do {
            try await api.clearReadNotifications()
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func dismiss(_ id: Int) async {
        do {
            try await api.dismissNotification(id: id)
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func clearErrors() async {
        do {
            try await api.clearAdminErrorNotifications()
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func pendingUserID(for detail: NotificationDetailPayload) async -> Int? {
        guard detail.kind == "user_signup_pending" else { return nil }
        if let id = parseUserID(from: detail.body) {
            return id
        }
        guard let email = parseEmail(from: detail.body) else { return nil }
        do {
            let users = try await api.fetchPendingUsers()
            return users.first(where: { ($0.email ?? "").lowercased() == email.lowercased() })?.id
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    func approvePendingUser(id: Int, notificationID: Int) async {
        do {
            try await api.approvePendingUser(id: id)
            try await api.dismissNotification(id: notificationID)
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func parseUserID(from body: String?) -> Int? {
        guard let body else { return nil }
        guard let range = body.range(of: #"User ID:\s*(\d+)"#, options: .regularExpression) else { return nil }
        let match = String(body[range])
        return Int(match.replacingOccurrences(of: "User ID:", with: "").trimmingCharacters(in: .whitespacesAndNewlines))
    }

    private func parseEmail(from body: String?) -> String? {
        guard let body else { return nil }
        guard let range = body.range(of: #"Email:\s*([^\s]+)"#, options: .regularExpression) else { return nil }
        let match = String(body[range])
        return match.replacingOccurrences(of: "Email:", with: "").trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

private struct NotificationDetailSheetView: View {
    let detail: NotificationDetailPayload
    let onDismissNotification: () -> Void
    let onApprovePendingUser: () -> Void

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text(detail.subject ?? "(no subject)")
                        .font(.system(size: 20, weight: .bold, design: .rounded))
                    Text("\(detail.sender ?? "")\(detail.createdAtLocal.map { " | \($0)" } ?? "")")
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                    Text(detail.body ?? "")
                        .font(.system(size: 14, weight: .medium, design: .rounded))
                        .frame(maxWidth: .infinity, alignment: .leading)
                    HStack(spacing: 8) {
                        Button("Dismiss", action: onDismissNotification)
                            .buttonStyle(.bordered)
                        if detail.kind == "user_signup_pending" {
                            Button("Approve", action: onApprovePendingUser)
                                .buttonStyle(.borderedProminent)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(16)
            }
            .navigationTitle("Notification")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

private struct AdminErrorDetailSheetView: View {
    let error: AdminErrorNotificationPayload

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    Text(error.errorMessage ?? "Server error")
                        .font(.system(size: 20, weight: .bold, design: .rounded))
                    detailRow("When", error.createdAt ?? "—")
                    detailRow("User", error.userEmail ?? "—")
                    detailRow("Method", error.method ?? "—")
                    detailRow("Path", error.path ?? "—")
                    detailRow("Query", error.queryString ?? "—")
                    detailRow("Status", error.statusCode.map(String.init) ?? "—")
                    detailRow("Tenant", error.tenantID.map(String.init) ?? "—")
                    detailRow("Referer", error.referer ?? "—")
                    detailRow("Page URL", error.pageURL ?? "—")
                    detailRow("Request ID", error.requestID ?? "—")
                    detailRow("Client IP", error.clientIP ?? "—")
                    detailRow("User Agent", error.userAgent ?? "—")
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(16)
            }
            .navigationTitle("Error Detail")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 14, weight: .medium, design: .rounded))
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

private struct BudgetPageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @State private var monthBudget: MonthBudgetPayload?
    @State private var extraSaved: Double?
    @State private var errorMessage: String?
    @State private var isLoading = true

    var body: some View {
        PageShell(title: "Budget", subtitle: "This month and daily safety numbers") {
            VStack(spacing: 12) {
                if isLoading {
                    ProgressView().padding(.vertical, 24)
                } else if let errorMessage {
                    Text(errorMessage).foregroundStyle(.secondary)
                } else if let monthBudget {
                    budgetCard(monthBudget: monthBudget, extraSaved: extraSaved)
                }
            }
        }
        .navigationTitle("Budget")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func budgetCard(monthBudget: MonthBudgetPayload, extraSaved: Double?) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return VStack(alignment: .leading, spacing: 12) {
            statRow("Safe to spend", nativeMoneyValue(monthBudget.safeToSpend ?? 0))
            statRow("Daily limit", nativeMoneyValue(monthBudget.dailyLimit ?? 0))
            statRow("Income", nativeMoneyValue(monthBudget.expectedIncome ?? 0))
            statRow("Spent so far", nativeMoneyValue(monthBudget.spentSoFar ?? 0))
            statRow("Remaining bills", nativeMoneyValue(monthBudget.billsRemaining ?? 0))
            statRow("Extra saved", nativeMoneyValue(extraSaved ?? 0))
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func statRow(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).font(.system(size: 13, weight: .semibold, design: .rounded))
            Spacer()
            Text(value).font(.system(size: 13, weight: .bold, design: .rounded))
        }
    }

    private func load() async {
        isLoading = true
        do {
            async let budget = QuailCashAPI.shared.fetchMonthBudget()
            async let saved = QuailCashAPI.shared.fetchExtraSaved()
            monthBudget = try await budget
            extraSaved = try? await saved
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}

private struct AnalyticsPageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    var body: some View {
        PageShell(title: "Analytics", subtitle: "Placeholder for chart-heavy views and category analysis") {
            VStack(alignment: .leading, spacing: 10) {
                Text("This page is the native shell for the web app's analytics screens.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                NavigationLink(value: AppRoute.category("Unknown merchants")) { quickLink("Unknown merchants") }
                NavigationLink(value: AppRoute.recurring) { quickLink("Recurring") }
            }
        }
        .navigationTitle("Analytics")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func quickLink(_ title: String) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return HStack {
            Text(title)
            Spacer()
            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

private struct RecurringPageView: View {
    var body: some View {
        PageShell(title: "Recurring", subtitle: "Placeholder for the recurring dashboard and calendar") {
            Text("The web app's recurring page can be ported here next.")
                .font(.system(size: 13, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
        }
        .navigationTitle("Recurring")
        .navigationBarTitleDisplayMode(.inline)
    }
}

private struct AllTransactionsPageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @State private var transactions: [TransactionItem] = []
    @State private var errorMessage: String?
    @State private var isLoading = true

    var body: some View {
        PageShell(title: "All", subtitle: "A native list of your recent transactions") {
            Group {
                if isLoading {
                    ProgressView().padding(.vertical, 24)
                } else if let errorMessage {
                    Text(errorMessage).foregroundStyle(.secondary)
        } else {
                    VStack(spacing: 10) {
                        ForEach(transactions) { tx in
                            transactionRow(tx)
                        }
                    }
                }
            }
        }
        .navigationTitle("All")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func transactionRow(_ tx: TransactionItem) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return HStack {
            VStack(alignment: .leading, spacing: 3) {
                Text(tx.merchant.isEmpty ? "Unknown merchant" : tx.merchant)
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .textCase(.uppercase)
                Text([tx.bank, tx.card].compactMap { $0 }.joined(separator: " • "))
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Text(nativeMoneyValue(tx.amount))
                .font(.system(size: 14, weight: .bold, design: .rounded))
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func load() async {
        isLoading = true
        do {
            transactions = try await QuailCashAPI.shared.fetchTransactions(limit: 100)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}

private struct BankInfoPageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @State private var payload: BankInfoPayload?
    @State private var errorMessage: String?
    @State private var isLoading = true

    var body: some View {
        PageShell(title: "Bank Info", subtitle: "Rates, accounts, and credit cards") {
            Group {
                if isLoading {
                    ProgressView().padding(.vertical, 24)
                } else if let errorMessage {
                    Text(errorMessage).foregroundStyle(.secondary)
                } else if let payload {
                    VStack(alignment: .leading, spacing: 12) {
                        if let lastUpdated = payload.lastUpdated {
                            Text("Last updated: \(lastUpdated)")
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                        bankSection(title: "Accounts", items: payload.accounts.map { "\($0.bank) — \($0.name)" })
                        bankSection(title: "Credit cards", items: payload.creditCards.map { "\($0.bank) — \($0.name)" })
                    }
                }
            }
        }
        .navigationTitle("Bank Info")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func bankSection(title: String, items: [String]) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 16, weight: .bold, design: .rounded))
            ForEach(items, id: \.self) { item in
                Text(item)
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(palette.border, lineWidth: 1))
            }
        }
    }

    private func load() async {
        isLoading = true
        do {
            payload = try await QuailCashAPI.shared.fetchBankInfo()
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}

private struct CsvImportPageView: View {
    var body: some View {
        PageShell(title: "CSV Import", subtitle: "Native shell for the bank file importer") {
            VStack(alignment: .leading, spacing: 10) {
                Text("This is the native redirect target for the Import CSV/Excel button.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                Text("Next step: port the actual mapping and preview modal.")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
            }
        }
        .navigationTitle("CSV Import")
        .navigationBarTitleDisplayMode(.inline)
    }
}

private struct ImportQueuePageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @State private var items: [QueuedCsvImportItem] = []
    @State private var activeIDs: Set<UUID> = []
    @State private var statusMessage = ""

    var body: some View {
        PageShell(title: "Import Queue", subtitle: "Assigned CSV files wait here until you process the whole queue.", refreshAction: load) {
            let palette = QuailTheme.palette(for: themeSelection)
            if items.isEmpty {
                Text("No queued imports yet.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 140)
            } else {
                VStack(spacing: 10) {
                    if items.contains(where: { $0.status == .assigned || $0.status == .failed || $0.status == .needsReview }) {
                        Button {
                            Task { await processAll() }
                        } label: {
                            Text(activeIDs.isEmpty == false ? "Processing..." : "Process All Assigned")
                                .font(.system(size: 13, weight: .bold, design: .rounded))
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(ImportQueueActionButtonStyle(primary: true))
                        .disabled(activeIDs.isEmpty == false)
                    }

                    ForEach(items) { item in
                        VStack(alignment: .leading, spacing: 8) {
                            HStack(spacing: 8) {
                                Text(item.accountLabel)
                                    .font(.system(size: 14, weight: .bold, design: .rounded))
                                Spacer(minLength: 8)
                                statusBadge(for: item.status)
                            }
                            Text(item.originalFileName)
                                .font(.system(size: 12, weight: .semibold, design: .rounded))
                                .foregroundStyle(.secondary)
                            Text(item.detail)
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                            Text(item.queuedAt.formatted(date: .abbreviated, time: .shortened))
                                .font(.system(size: 11, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                            HStack(spacing: 8) {
                                if item.status != .imported {
                                    Button {
                                        Task { await retry(item) }
                                    } label: {
                                        Text(activeIDs.contains(item.id) ? "Processing..." : (item.status == .assigned ? "Process" : "Retry"))
                                            .font(.system(size: 12, weight: .semibold, design: .rounded))
                                            .frame(maxWidth: .infinity)
                                    }
                                    .buttonStyle(ImportQueueActionButtonStyle(primary: true))
                                    .disabled(activeIDs.contains(item.id))
                                }

                                Button(role: .destructive) {
                                    remove(item)
                                } label: {
                                    Text("Remove")
                                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                                        .frame(maxWidth: .infinity)
                                }
                                .buttonStyle(ImportQueueActionButtonStyle(primary: false))
                                .disabled(activeIDs.contains(item.id))
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                        .background(palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(palette.border, lineWidth: 1))
                    }
                }
            }
            if !statusMessage.isEmpty {
                Text(statusMessage)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Import Queue")
        .navigationBarTitleDisplayMode(.inline)
        .task { load() }
    }

    private func load() {
        items = ImportQueueStore.load()
    }

    private func statusBadge(for status: QueuedCsvImportItem.Status) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        let fill: Color
        switch status {
        case .assigned:
            fill = palette.accent.opacity(0.18)
        case .processing:
            fill = palette.accent.opacity(0.28)
        case .imported:
            fill = palette.positive.opacity(0.18)
        case .needsReview:
            fill = Color.orange.opacity(0.18)
        case .failed:
            fill = palette.negative.opacity(0.18)
        }
        return Text(statusLabel(status))
            .font(.system(size: 11, weight: .bold, design: .rounded))
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(fill, in: Capsule())
    }

    private func statusLabel(_ status: QueuedCsvImportItem.Status) -> String {
        switch status {
        case .assigned: return "Assigned"
        case .processing: return "Processing"
        case .imported: return "Imported"
        case .needsReview: return "Needs Review"
        case .failed: return "Failed"
        }
    }

    private func retry(_ item: QueuedCsvImportItem) async {
        activeIDs.insert(item.id)
        defer { activeIDs.remove(item.id) }
        let url = ImportQueueStore.storedFileURL(for: item)
        guard let data = try? Data(contentsOf: url) else {
            ImportQueueStore.updateStatus(id: item.id, status: .failed, detail: "Stored file could not be read.")
            statusMessage = "Stored file missing for \(item.originalFileName)."
            load()
            return
        }
        let summary = await ShortcutImportProcessor.process(
            fileData: data,
            originalName: item.originalFileName,
            accountID: item.accountID,
            accountLabel: item.accountLabel,
            existingQueueID: item.id
        )
        statusMessage = "\(item.originalFileName): \(summary.detail)"
        load()
    }

    private func remove(_ item: QueuedCsvImportItem) {
        ImportQueueStore.remove(id: item.id)
        statusMessage = "Removed \(item.originalFileName)."
        load()
    }

    private func processAll() async {
        activeIDs = Set(items.map(\.id))
        defer { activeIDs.removeAll() }
        let summary = await ShortcutImportProcessor.processAllAssigned()
        statusMessage = "Processed \(summary.processed): \(summary.imported) imported, \(summary.review) need review, \(summary.failed) failed."
        load()
    }
}

private struct ImportQueueActionButtonStyle: ButtonStyle {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"

    let primary: Bool

    func makeBody(configuration: Configuration) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        configuration.label
            .foregroundStyle(primary ? palette.primaryButtonText : palette.secondaryButtonText)
            .frame(height: 36)
            .padding(.horizontal, 12)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(primary ? palette.primaryButton : palette.secondaryButton)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(palette.border.opacity(primary ? 0.0 : 1.0), lineWidth: 1)
            )
            .opacity(configuration.isPressed ? 0.82 : 1.0)
            .scaleEffect(configuration.isPressed ? 0.985 : 1.0)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

private struct RuleBuilderPageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @StateObject private var model = RegexRulesViewModel()
    @State private var activeTestRule: CategoryRuleListRow?

    var body: some View {
        PageShell(
            title: "Regex Rules",
            subtitle: "Edit categories, disable/delete rules, test regex, and re-apply to existing transactions.",
            refreshAction: { await model.reload(reset: true) }
        ) {
            VStack(alignment: .leading, spacing: 12) {
                rulesToolbarCard

                if let summary = model.checkSummary {
                    regexCheckSummaryCard(summary: summary)
                }

                if model.isLoading && model.rules.isEmpty {
                    ProgressView()
                        .frame(maxWidth: .infinity, minHeight: 140)
                } else if let errorMessage = model.errorMessage, model.rules.isEmpty {
                    Text(errorMessage)
                        .font(.system(size: 13, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(.vertical, 28)
                } else {
                    VStack(spacing: 10) {
                        ForEach(model.rules) { rule in
                            RegexRuleCardView(
                                rule: rule,
                                categories: model.categories,
                                onSave: { newCategory in
                                    await model.saveRule(ruleID: rule.id, category: newCategory)
                                },
                                onToggleActive: { isActive in
                                    await model.setRuleActive(ruleID: rule.id, isActive: isActive)
                                },
                                onDelete: {
                                    await model.deleteRule(ruleID: rule.id)
                                },
                                onTest: {
                                    activeTestRule = rule
                                }
                            )
                        }
                    }
                }

                if model.hasMore {
                    Button {
                        Task { await model.loadMore() }
                } label: {
                    let palette = QuailTheme.palette(for: themeSelection)
                    Text(model.isLoadingMore ? "Loading..." : "Load more")
                            .font(.system(size: 13, weight: .semibold, design: .rounded))
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 12)
                            .background(palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(palette.border, lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                    .disabled(model.isLoadingMore)
                }
            }
        }
        .task { await model.startIfNeeded() }
        .sheet(item: $activeTestRule) { rule in
            RegexTestSheetView(
                initialPattern: rule.pattern,
                initialFlags: rule.flags ?? "i",
                ruleID: rule.id
            )
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
        }
        .onChange(of: model.filterRuleID) { _, _ in
            model.scheduleFilteredReload()
        }
        .onChange(of: model.filterKeyword) { _, _ in
            model.scheduleFilteredReload()
        }
        .onChange(of: model.filterCategory) { _, _ in
            model.scheduleFilteredReload()
        }
        .navigationTitle("Regex Rules")
        .navigationBarTitleDisplayMode(.inline)
    }

    private var rulesToolbarCard: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                Button {
                    Task { await model.reload(reset: true) }
                } label: {
                    regexActionButton(model.isLoading ? "Refreshing..." : "Refresh", primary: false)
                }
                .buttonStyle(.plain)
                .disabled(model.isLoading)

                Button {
                    Task { await model.runFullCheck() }
                } label: {
                    regexActionButton(model.isRunningCheck ? "Running..." : "Run full check", primary: false)
                }
                .buttonStyle(.plain)
                .disabled(model.isRunningCheck)
            }

            Toggle("Only uncategorized", isOn: $model.uncategorizedOnly)
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .tint(palette.accent)

            VStack(spacing: 8) {
                TextField("Rule ID", text: $model.filterRuleID)
                    .textInputAutocapitalization(.never)
                    .keyboardType(.numbersAndPunctuation)
                    .font(.system(size: 13, weight: .medium, design: .monospaced))
                    .padding(.horizontal, 12)
                    .frame(height: 38)
                    .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))

                TextField("Keywords / regex", text: $model.filterKeyword)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .padding(.horizontal, 12)
                    .frame(height: 38)
                    .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))

                Menu {
                    Button("All categories") { model.filterCategory = "" }
                    ForEach(model.categories, id: \.self) { category in
                        Button(category) { model.filterCategory = category }
                    }
                } label: {
                    HStack(spacing: 8) {
                        Text(model.filterCategory.isEmpty ? "Category" : model.filterCategory)
                            .font(.system(size: 13, weight: .medium, design: .rounded))
                            .foregroundStyle(model.filterCategory.isEmpty ? .secondary : .primary)
                            .lineLimit(1)
                        Spacer(minLength: 8)
                        Image(systemName: "chevron.down")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(.secondary)
                    }
                    .padding(.horizontal, 12)
                    .frame(height: 38)
                    .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
                .buttonStyle(.plain)
            }

            if !model.statusText.isEmpty {
                Text(model.statusText)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(model.statusIsError ? palette.negative : .secondary)
            }
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func regexCheckSummaryCard(summary: CategoryRulesCheckAllPayload) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return VStack(alignment: .leading, spacing: 8) {
            Text("Full check complete")
                .font(.system(size: 14, weight: .bold, design: .rounded))
            Text("Rules: \(summary.ruleCount ?? 0)   Applied: \(summary.totalApplied ?? 0)")
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
            Text("All matches: \(summary.totalMatchesAllRules ?? 0)   Uncategorized: \(summary.totalUncategorizedMatchesAllRules ?? 0)")
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)

            ForEach(summary.rows.prefix(8)) { row in
                VStack(alignment: .leading, spacing: 4) {
                    Text("#\(row.id) \(row.category)")
                        .font(.system(size: 12, weight: .bold, design: .monospaced))
                    Text("matches=\(row.matches ?? 0) total=\(row.totalMatches ?? 0) uncategorized=\(row.uncategorizedMatches ?? 0) applied=\(row.applied ?? 0)")
                        .font(.system(size: 11, weight: .medium, design: .monospaced))
                        .foregroundStyle(.secondary)
                    if let sample = row.samples.first {
                        Text("sample: #\(sample.id) \(sample.merchant)")
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(10)
                .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func regexActionButton(_ title: String, primary: Bool) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return Text(title)
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .lineLimit(1)
            .minimumScaleFactor(0.82)
            .padding(.horizontal, 12)
            .frame(height: 38)
            .foregroundStyle(primary ? palette.primaryButtonText : palette.secondaryButtonText)
            .background(primary ? palette.primaryButton : palette.secondaryButton, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(primary ? .clear : palette.border, lineWidth: 1)
            )
    }
}

@MainActor
private final class RegexRulesViewModel: ObservableObject {
    @Published var categories: [String] = []
    @Published var rules: [CategoryRuleListRow] = []
    @Published var checkSummary: CategoryRulesCheckAllPayload?
    @Published var filterRuleID: String = ""
    @Published var filterKeyword: String = ""
    @Published var filterCategory: String = ""
    @Published var uncategorizedOnly: Bool = false
    @Published var statusText: String = ""
    @Published var statusIsError = false
    @Published var errorMessage: String?
    @Published var isLoading = false
    @Published var isLoadingMore = false
    @Published var isRunningCheck = false
    @Published var hasMore = false

    private var didStart = false
    private var offset = 0
    private let pageSize = 50
    private var filterTask: Task<Void, Never>?

    func startIfNeeded() async {
        guard !didStart else { return }
        didStart = true
        await loadCategories()
        await reload(reset: true)
    }

    func reload(reset: Bool) async {
        filterTask?.cancel()
        if reset {
            offset = 0
            hasMore = false
            rules = []
        }
        isLoading = true
        errorMessage = nil
        do {
            let payload = try await QuailCashAPI.shared.fetchCategoryRuleList(
                ruleID: filterRuleID,
                keyword: filterKeyword,
                category: filterCategory,
                limit: pageSize,
                offset: 0
            )
            rules = payload.rows
            offset = payload.rows.count
            hasMore = payload.hasMore
            setStatus(payload.rows.isEmpty ? "No matching rules" : "Loaded \(payload.rows.count)\(payload.hasMore ? "+" : "") rule(s)")
        } catch {
            errorMessage = error.localizedDescription
            setStatus("Failed to load rules", isError: true)
        }
        isLoading = false
    }

    func loadMore() async {
        guard hasMore, !isLoadingMore else { return }
        isLoadingMore = true
        do {
            let payload = try await QuailCashAPI.shared.fetchCategoryRuleList(
                ruleID: filterRuleID,
                keyword: filterKeyword,
                category: filterCategory,
                limit: pageSize,
                offset: offset
            )
            rules.append(contentsOf: payload.rows)
            offset += payload.rows.count
            hasMore = payload.hasMore
            setStatus("Loaded \(rules.count)\(payload.hasMore ? "+" : "") rule(s)")
        } catch {
            setStatus("Failed to load more rules", isError: true)
        }
        isLoadingMore = false
    }

    func runFullCheck() async {
        guard !isRunningCheck else { return }
        isRunningCheck = true
        do {
            let payload = try await QuailCashAPI.shared.runCategoryRulesCheckAll(uncategorizedOnly: uncategorizedOnly)
            checkSummary = payload
            setStatus("Check complete: \(payload.ruleCount ?? 0) rules, applied \(payload.totalApplied ?? 0)")
            await reload(reset: true)
        } catch {
            setStatus("Rule check failed", isError: true)
        }
        isRunningCheck = false
    }

    func saveRule(ruleID: Int, category: String) async {
        do {
            let response = try await QuailCashAPI.shared.updateCategoryRule(ruleID: ruleID, category: category)
            if let jobID = response.applyJob?.id {
                setStatus("Saved. Re-apply queued (job #\(jobID))...")
                await reload(reset: true)
                await waitForApplyJob(jobID)
            } else {
                setStatus("Saved + re-applied (\(response.applied ?? 0) transactions)")
                await reload(reset: true)
            }
        } catch {
            setStatus("Save failed", isError: true)
        }
    }

    func setRuleActive(ruleID: Int, isActive: Bool) async {
        do {
            try await QuailCashAPI.shared.setCategoryRuleActive(ruleID: ruleID, isActive: isActive)
            if let index = rules.firstIndex(where: { $0.id == ruleID }) {
                let current = rules[index]
                rules[index] = CategoryRuleListRow(
                    id: current.id,
                    pattern: current.pattern,
                    flags: current.flags,
                    category: current.category,
                    isActive: isActive,
                    matchCount: current.matchCount,
                    regexError: current.regexError
                )
            }
            setStatus(isActive ? "Rule enabled" : "Rule disabled")
        } catch {
            setStatus("Failed to update rule", isError: true)
        }
    }

    func deleteRule(ruleID: Int) async {
        do {
            try await QuailCashAPI.shared.deleteCategoryRule(ruleID: ruleID)
            rules.removeAll { $0.id == ruleID }
            setStatus("Rule deleted")
        } catch {
            setStatus("Delete failed", isError: true)
        }
    }

    func scheduleFilteredReload() {
        filterTask?.cancel()
        filterTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 250_000_000)
            guard let self, !Task.isCancelled else { return }
            await self.reload(reset: true)
        }
    }

    private func loadCategories() async {
        do {
            categories = try await QuailCashAPI.shared.fetchCategories()
        } catch {
            categories = []
        }
    }

    private func waitForApplyJob(_ jobID: Int) async {
        do {
            while true {
                let job = try await QuailCashAPI.shared.fetchCategoryRuleJob(jobID: jobID)
                let status = (job.status ?? "").lowercased()
                if status == "completed" {
                    setStatus("Saved + re-applied (\(job.totalApplied ?? 0) transactions)")
                    await reload(reset: true)
                    return
                }
                if status == "failed" {
                    setStatus("Saved, but re-apply failed", isError: true)
                    return
                }
                setStatus("Re-applying in background (job #\(jobID))...")
                try await Task.sleep(nanoseconds: 1_500_000_000)
            }
        } catch {
            setStatus("Saved, but re-apply failed", isError: true)
        }
    }

    private func setStatus(_ text: String, isError: Bool = false) {
        statusText = text
        statusIsError = isError
    }
}

private struct RegexRuleCardView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    let rule: CategoryRuleListRow
    let categories: [String]
    let onSave: (String) async -> Void
    let onToggleActive: (Bool) async -> Void
    let onDelete: () async -> Void
    let onTest: () -> Void

    @State private var draftCategory: String
    @State private var isSaving = false
    @State private var showCategoryMenu = false

    init(
        rule: CategoryRuleListRow,
        categories: [String],
        onSave: @escaping (String) async -> Void,
        onToggleActive: @escaping (Bool) async -> Void,
        onDelete: @escaping () async -> Void,
        onTest: @escaping () -> Void
    ) {
        self.rule = rule
        self.categories = categories
        self.onSave = onSave
        self.onToggleActive = onToggleActive
        self.onDelete = onDelete
        self.onTest = onTest
        _draftCategory = State(initialValue: rule.category)
    }

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return VStack(alignment: .leading, spacing: 10) {
            Text("#\(rule.id) - \(rule.pattern)")
                .font(.system(size: 13, weight: .bold, design: .monospaced))
                .frame(maxWidth: .infinity, alignment: .leading)

            HStack(alignment: .center, spacing: 10) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("Category")
                        .font(.system(size: 11, weight: .bold, design: .rounded))
                        .foregroundStyle(.secondary)
                    HStack(spacing: 8) {
                        TextField("Category", text: $draftCategory)
                            .textInputAutocapitalization(.words)
                            .font(.system(size: 13, weight: .medium, design: .rounded))
                            .padding(.horizontal, 12)
                            .frame(height: 38)
                            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))

                        Menu {
                            ForEach(categories, id: \.self) { category in
                                Button(category) { draftCategory = category }
                            }
                        } label: {
                            Text("Choose")
                                .font(.system(size: 13, weight: .semibold, design: .rounded))
                                .frame(width: 82, height: 38)
                                .foregroundStyle(palette.secondaryButtonText)
                                .background(palette.secondaryButton, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(palette.border, lineWidth: 1))
                        }
                    }
                }
            }

            HStack(spacing: 10) {
                Label("\(rule.matchCount ?? 0)", systemImage: "number")
                    .font(.system(size: 12, weight: .semibold, design: .monospaced))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                    .background(palette.elevatedSurface, in: Capsule(style: .continuous))

                Toggle("Active", isOn: Binding(
                    get: { rule.isActive },
                    set: { next in
                        Task { await onToggleActive(next) }
                    }
                ))
                .toggleStyle(.switch)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .tint(palette.accent)
            }

            Text("Always re-applies to existing")
                .font(.system(size: 11, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)

            HStack(spacing: 8) {
                Button {
                    guard !isSaving else { return }
                    isSaving = true
                    Task {
                        await onSave(draftCategory)
                        isSaving = false
                    }
                } label: {
                    regexMiniButton(isSaving ? "Saving..." : "Save", danger: false)
                }
                .buttonStyle(.plain)

                Button(action: onTest) {
                    regexMiniButton("Test", danger: false)
                }
                .buttonStyle(.plain)

                Button {
                    Task { await onDelete() }
                } label: {
                    regexMiniButton("Delete", danger: true)
                }
                .buttonStyle(.plain)
            }

            if let regexError = rule.regexError, !regexError.isEmpty {
                Text(regexError)
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.red)
            }
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func regexMiniButton(_ title: String, danger: Bool) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return Text(title)
            .font(.system(size: 12, weight: .semibold, design: .rounded))
            .frame(maxWidth: .infinity)
            .frame(height: 36)
            .foregroundStyle(danger ? Color.red : palette.secondaryButtonText)
            .background(palette.secondaryButton, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(danger ? Color.red.opacity(0.22) : palette.border, lineWidth: 1)
            )
    }
}

private struct RegexTestSheetView: View {
    @Environment(\.dismiss) private var dismiss
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @State private var pattern: String
    @State private var flags: String
    @State private var limitText: String = "50"
    @State private var rows: [CategoryRuleTestRow] = []
    @State private var statusText = ""
    @State private var isRunning = false
    let ruleID: Int

    init(initialPattern: String, initialFlags: String, ruleID: Int) {
        _pattern = State(initialValue: initialPattern)
        _flags = State(initialValue: initialFlags)
        self.ruleID = ruleID
    }

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Test Regex")
                        .font(.system(size: 28, weight: .bold, design: .rounded))
                    Text("Rule #\(ruleID)")
                        .font(.system(size: 13, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text("Regex")
                        .font(.system(size: 12, weight: .bold, design: .rounded))
                    TextField("your regex...", text: $pattern)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .font(.system(size: 13, weight: .medium, design: .monospaced))
                        .padding(.horizontal, 12)
                        .frame(height: 40)
                        .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                }

                HStack(spacing: 10) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Flags")
                            .font(.system(size: 12, weight: .bold, design: .rounded))
                        TextField("i", text: $flags)
                            .textInputAutocapitalization(.never)
                            .font(.system(size: 13, weight: .medium, design: .monospaced))
                            .padding(.horizontal, 12)
                            .frame(height: 40)
                            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    }
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Recent limit")
                            .font(.system(size: 12, weight: .bold, design: .rounded))
                        TextField("50", text: $limitText)
                            .keyboardType(.numberPad)
                            .font(.system(size: 13, weight: .medium, design: .monospaced))
                            .padding(.horizontal, 12)
                            .frame(height: 40)
                            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    }
                }

                HStack(spacing: 8) {
                    Button {
                        Task { await runTest() }
                    } label: {
                        regexSheetPrimaryButton(isRunning ? "Running..." : "Run test", palette: palette)
                    }
                    .buttonStyle(.plain)
                    .disabled(isRunning)

                    Button {
                        dismiss()
                    } label: {
                        regexSheetSecondaryButton("Close", palette: palette)
                    }
                    .buttonStyle(.plain)
                }

                if !statusText.isEmpty {
                    Text(statusText)
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }

                VStack(spacing: 8) {
                    ForEach(rows) { row in
                        HStack(spacing: 10) {
                            Text(row.merchant)
                                .font(.system(size: 13, weight: .semibold, design: .rounded))
                                .frame(maxWidth: .infinity, alignment: .leading)
                            Text("x\(row.count)")
                                .font(.system(size: 12, weight: .medium, design: .monospaced))
                                .foregroundStyle(.secondary)
                            Text(row.matched ? "MATCH" : "-")
                                .font(.system(size: 11, weight: .bold, design: .rounded))
                                .foregroundStyle(row.matched ? .green : .secondary)
                        }
                        .padding(12)
                        .background((row.matched ? palette.elevatedSurface.opacity(1.15) : palette.elevatedSurface), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    }
                }
            }
            .padding(16)
        }
        .background(
            LinearGradient(
                colors: [palette.backgroundTop, palette.backgroundBottom],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()
        )
    }

    private func regexSheetPrimaryButton(_ title: String, palette: QuailThemePalette) -> some View {
        Text(title)
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .frame(maxWidth: .infinity, minHeight: 48)
            .foregroundStyle(palette.primaryButtonText)
            .background(palette.primaryButton, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }

    private func regexSheetSecondaryButton(_ title: String, palette: QuailThemePalette) -> some View {
        Text(title)
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .frame(maxWidth: .infinity, minHeight: 44)
            .foregroundStyle(palette.secondaryButtonText)
            .background(palette.secondaryButton, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func runTest() async {
        guard !isRunning else { return }
        isRunning = true
        defer { isRunning = false }
        do {
            let payload = try await QuailCashAPI.shared.testCategoryRule(
                pattern: pattern,
                flags: flags,
                limit: Int(limitText) ?? 50
            )
            rows = payload.tested
            let matched = payload.tested.filter(\.matched).count
            statusText = "\(matched) / \(payload.tested.count) matched"
        } catch {
            rows = []
            statusText = "Test failed"
        }
    }
}

private struct CategoryPageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    let category: String
    @StateObject private var model: CategoryPageViewModel
    @State private var showAllCategories = false
    @State private var activeTransaction: TransactionItem?

    init(category: String) {
        self.category = category
        _model = StateObject(wrappedValue: CategoryPageViewModel(category: category))
    }

    var body: some View {
        PageShell(title: "Category", subtitle: model.selectedCategory, refreshAction: {
            await model.reload()
        }) {
            categoryChartCard
            categoryTransactionsCard
        }
        .task { model.startIfNeeded() }
        .sheet(isPresented: $showAllCategories) {
            CategoryLifetimeSheet(
                rows: model.lifetimeRows,
                selectedCategory: model.selectedCategory,
                onSelect: { selected in
                    model.selectCategory(selected)
                    showAllCategories = false
                }
            )
            .presentationDetents([.medium, .large])
        }
        .sheet(item: $activeTransaction) { tx in
            SharedTransactionInspectPopupView(
                transaction: tx,
                onDismiss: { activeTransaction = nil },
                onRefresh: { Task { await model.reload() } }
            )
            .presentationDetents([.large])
            .presentationDragIndicator(.visible)
        }
    }

    private var categoryChartCard: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return VStack(alignment: .leading, spacing: 11) {
            HStack(spacing: 8) {
                Spacer(minLength: 0)
                Text(model.selectedCategory)
                    .font(.system(size: 16, weight: .bold, design: .rounded))
                    .multilineTextAlignment(.center)
                    .lineLimit(2)
                Spacer(minLength: 0)
                Button("All Categories") {
                    showAllCategories = true
                }
                .buttonStyle(CategorySecondaryButtonStyle())
            }

            HStack(spacing: 6) {
                categoryMetricPill(title: "% Growth", value: model.growthText, valueColor: model.growthColor)
                categoryMetricPill(title: model.selectedCategory, value: nativeMoneyValue(model.cumulativeTotal), compact: true)
            }

            HStack(spacing: 4) {
                categoryDateField(title: "Start", date: $model.startDate)
                Spacer(minLength: 10)
                categoryDateField(title: "End", date: $model.endDate)
                Spacer(minLength: 4)
                Button("Update") {
                    model.updateFromPickers()
                }
                .buttonStyle(CategoryPrimaryButtonStyle())
                .frame(height: 36)
            }

            HStack(spacing: 5) {
                ForEach(0..<4, id: \.self) { idx in
                    Button("Q\(idx + 1)") { model.setQuarter(idx + 1) }
                        .buttonStyle(CategoryChipButtonStyle())
                }

                Spacer(minLength: 10)

                HStack(spacing: 4) {
                    Button {
                        model.previousYear()
                    } label: {
                        Image(systemName: "arrow.left")
                    }
                    .buttonStyle(CategoryChipButtonStyle())

                    Text(String(model.selectedYear))
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: true, vertical: false)

                    Button {
                        model.nextYear()
                    } label: {
                        Image(systemName: "arrow.right")
                    }
                    .buttonStyle(CategoryChipButtonStyle())
                }
            }

            categoryChartBody

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 7) {
                    ForEach(Array(categoryMonthNames.enumerated()), id: \.offset) { idx, name in
                        Button(name) { model.setMonth(idx) }
                            .buttonStyle(CategoryChipButtonStyle())
                    }
                    Button("Annual") { model.setAnnual() }
                        .buttonStyle(CategoryChipButtonStyle())
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    @ViewBuilder
    private var categoryChartBody: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        if model.isLoading {
            HStack {
                ProgressView()
                Text("Loading category...")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, minHeight: 220, alignment: .center)
            .padding(10)
            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        } else if let errorMessage = model.errorMessage {
            VStack(spacing: 8) {
                Text(errorMessage)
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                Button("Retry") {
                    Task { await model.reload() }
                }
                .buttonStyle(CategorySecondaryButtonStyle())
            }
            .frame(maxWidth: .infinity, minHeight: 220, alignment: .center)
            .padding(10)
            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        } else {
            GeometryReader { proxy in
                Chart {
                    ForEach(model.dailyChartPoints) { point in
                        BarMark(
                            x: .value("Date", point.date),
                            y: .value("Daily", point.daily)
                        )
                        .foregroundStyle(Color(red: 0.23, green: 0.51, blue: 0.96).opacity(0.68))
                        .cornerRadius(3)

                        LineMark(
                            x: .value("Date", point.date),
                            y: .value("Total", point.cumulative)
                        )
                        .foregroundStyle(palette.secondaryButtonText.opacity(0.72))
                        .lineStyle(StrokeStyle(lineWidth: 2))
                        .interpolationMethod(.linear)
                    }
                }
                .chartXAxis(.hidden)
                .chartYAxis {
                    AxisMarks(position: .leading) { _ in
                        AxisGridLine().foregroundStyle(palette.border.opacity(0.75))
                        AxisTick().foregroundStyle(palette.border.opacity(0.9))
                        AxisValueLabel()
                            .font(.system(size: 10, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }
                .frame(width: proxy.size.width, height: 224, alignment: .topLeading)
                .padding(11)
                .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            }
            .frame(height: 224)
        }
    }

    private var categoryTransactionsCard: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return VStack(alignment: .leading, spacing: 10) {
            Text("Transactions")
                .font(.system(size: 16, weight: .bold, design: .rounded))

            if model.isLoading && model.transactions.isEmpty {
                ProgressView().padding(.vertical, 12)
            } else if model.transactions.isEmpty {
                Text("No transactions in this range.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            } else {
                VStack(spacing: 8) {
                    ForEach(model.transactions) { tx in
                        Button {
                            activeTransaction = tx
                        } label: {
                            HStack(alignment: .center, spacing: 12) {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(model.displayDate(for: tx))
                                        .font(.system(size: 12, weight: .bold, design: .rounded))
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                    ZStack {
                                        Circle()
                                            .fill(palette.border.opacity(0.9))
                                            .frame(width: 38, height: 38)
                                        Text(String((tx.merchant.trimmingCharacters(in: .whitespacesAndNewlines).first.map { String($0).uppercased() }) ?? "?"))
                                            .font(.system(size: 14, weight: .bold, design: .rounded))
                                            .foregroundStyle(.primary)
                                    }
                                }
                                .frame(width: 46, alignment: .leading)

                                VStack(alignment: .leading, spacing: 3) {
                                    Text((tx.merchant.isEmpty ? "Unknown merchant" : tx.merchant).uppercased())
                                        .font(.system(size: 14, weight: .bold, design: .rounded))
                                        .foregroundStyle(.primary)
                                        .lineLimit(1)
                                    Text([tx.bank, tx.card].compactMap { $0 }.joined(separator: " • ").isEmpty ? (tx.category ?? "") : [tx.bank, tx.card].compactMap { $0 }.joined(separator: " • "))
                                        .font(.system(size: 11, weight: .medium, design: .rounded))
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                }

                                Spacer(minLength: 8)

                                VStack(alignment: .trailing, spacing: 4) {
                                    Text(nativeMoneyValue(tx.amount))
                                        .font(.system(size: 14, weight: .bold, design: .rounded))
                                        .foregroundStyle(tx.amount >= 0 ? .red : .green)
                                    Text(nativeMoneyValue(model.runningBalance(for: tx.id)))
                                        .font(.system(size: 11, weight: .medium, design: .rounded))
                                        .foregroundStyle(.secondary)
                                }
                            }
                            .padding(.vertical, 10)
                            .padding(.horizontal, 12)
                            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func categoryMetricPill(title: String, value: String, compact: Bool = false, valueColor: Color = .primary) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return VStack(alignment: .leading, spacing: 3) {
            Text(title)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .lineLimit(1)
            Text(value)
                .font(.system(size: compact ? 14 : 16, weight: .bold, design: .rounded))
                .foregroundStyle(valueColor)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func categoryDateField(title: String, date: Binding<Date>) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            DatePicker("", selection: date, displayedComponents: .date)
                .labelsHidden()
                .datePickerStyle(.compact)
                .tint(palette.primaryButton)
        }
    }
}

private struct CategoryChartPoint: Identifiable, Hashable {
    let date: Date
    let daily: Double
    let cumulative: Double
    var id: Date { date }
}

private let categoryMonthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

private struct CategoryTransactionRow: Identifiable, Hashable {
    let transaction: TransactionItem
    let runningBalance: Double
    var id: String { transaction.id }
}

@MainActor
private final class CategoryPageViewModel: ObservableObject {
    @Published var selectedCategory: String
    @Published var startDate: Date
    @Published var endDate: Date
    @Published var selectedYear: Int
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var chartPoints: [CategoryChartPoint] = []
    @Published var transactions: [TransactionItem] = []
    @Published var lifetimeRows: [CategoryLifetimeTotalPayload] = []

    private let api = QuailCashAPI.shared
    private var runningBalancesByID: [String: Double] = [:]
    private var didStart = false

    init(category: String) {
        selectedCategory = category
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

    func reload() async {
        isLoading = true
        defer { isLoading = false }
        errorMessage = nil
        do {
            async let lifetime = api.fetchCategoryLifetimeTotals()
            async let trend = api.fetchCategoryTrend(category: selectedCategory, period: "all")
            async let txs = api.fetchCategoryTransactions(
                category: selectedCategory,
                start: Self.isoDate(startDate),
                end: Self.isoDate(endDate),
                limit: 500
            )
            let (lifetimeRows, trendPayload, transactionItems) = try await (lifetime, trend, txs)
            self.lifetimeRows = lifetimeRows
            chartPoints = Self.buildChartPoints(from: trendPayload.series, start: startDate, end: endDate)
            let sortedRows = Self.buildTransactionRows(from: transactionItems)
            transactions = sortedRows.map(\.transaction)
            runningBalancesByID = Dictionary(uniqueKeysWithValues: sortedRows.map { ($0.transaction.id, $0.runningBalance) })
        } catch is CancellationError {
            return
        } catch QuailCashAPIError.unauthorized {
            errorMessage = "Sign in to load this category."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func selectCategory(_ category: String) {
        selectedCategory = category
        Task { await reload() }
    }

    func updateFromPickers() {
        let range = normalizedRange(start: startDate, end: endDate)
        startDate = range.start
        endDate = range.end
        selectedYear = Calendar.current.component(.year, from: range.start)
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

    func previousYear() {
        setYear(selectedYear - 1)
    }

    func nextYear() {
        setYear(selectedYear + 1)
    }

    func setYear(_ year: Int) {
        let currentYear = Calendar.current.component(.year, from: Date())
        selectedYear = min(year, currentYear)
        let start = Calendar.current.date(from: DateComponents(year: selectedYear, month: 1, day: 1)) ?? startDate
        let end: Date
        if selectedYear == currentYear {
            end = Date()
        } else {
            end = Calendar.current.date(from: DateComponents(year: selectedYear, month: 12, day: 31)) ?? endDate
        }
        setRange(start: start, end: end)
    }

    func runningBalance(for id: String) -> Double {
        runningBalancesByID[id] ?? 0
    }

    func displayDate(for tx: TransactionItem) -> String {
        let raw = tx.postedDate ?? tx.effectiveDate ?? tx.date ?? tx.dateISO ?? ""
        return Self.shortDate(raw)
    }

    func loadTransactionDetail(_ txID: String) async -> TransactionDetailPayload? {
        do {
            return try await api.fetchTransactionDetail(txId: txID)
        } catch {
            return nil
        }
    }

    var dailyChartPoints: [CategoryChartPoint] {
        chartPoints
    }

    var cumulativeTotal: Double {
        chartPoints.last?.cumulative ?? 0
    }

    var growthText: String {
        guard let first = chartPoints.first?.cumulative,
              let last = chartPoints.last?.cumulative,
              abs(first) > 0.0001 else {
            return "—"
        }
        let pct = ((last - first) / abs(first)) * 100.0
        return String(format: "%@%.2f%%", pct >= 0 ? "+" : "", pct)
    }

    var growthColor: Color {
        guard let first = chartPoints.first?.cumulative,
              let last = chartPoints.last?.cumulative,
              abs(first) > 0.0001 else {
            return .primary
        }
        return last >= first ? .red : .green
    }

    private func setRange(start: Date, end: Date) {
        let range = normalizedRange(start: start, end: end)
        startDate = range.start
        endDate = range.end
        selectedYear = Calendar.current.component(.year, from: range.start)
        Task { await reload() }
    }

    private func normalizedRange(start: Date, end: Date) -> (start: Date, end: Date) {
        let cal = Calendar.current
        let s = cal.startOfDay(for: start)
        let e = cal.startOfDay(for: max(start, end))
        return (s, e)
    }

    private static func buildChartPoints(from series: [CategoryTrendPoint], start: Date, end: Date) -> [CategoryChartPoint] {
        let startDay = Calendar.current.startOfDay(for: start)
        let endDay = Calendar.current.startOfDay(for: end)
        let filtered = series.compactMap { point -> (Date, Double)? in
            guard let date = parseDate(point.date) else { return nil }
            let day = Calendar.current.startOfDay(for: date)
            guard day >= startDay, day <= endDay else { return nil }
            return (day, point.amount)
        }
        .sorted { $0.0 < $1.0 }

        var running = 0.0
        return filtered.map { date, value in
            running += value
            return CategoryChartPoint(date: date, daily: value, cumulative: running)
        }
    }

    private static func buildTransactionRows(from transactions: [TransactionItem]) -> [CategoryTransactionRow] {
        let sorted = transactions.sorted {
            let left = $0.dateISO ?? $0.postedDate ?? $0.effectiveDate ?? $0.date ?? ""
            let right = $1.dateISO ?? $1.postedDate ?? $1.effectiveDate ?? $1.date ?? ""
            if left != right { return left < right }
            return $0.id < $1.id
        }
        var running = 0.0
        let runningRows = sorted.map { tx -> CategoryTransactionRow in
            running += tx.amount
            return CategoryTransactionRow(transaction: tx, runningBalance: running)
        }
        return runningRows.reversed()
    }

    private static func isoDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: date)
    }

    private static func parseDate(_ value: String) -> Date? {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.date(from: value)
    }

    private static func shortDate(_ value: String) -> String {
        guard let date = parseDate(value) else { return value }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "MMM d"
        return formatter.string(from: date)
    }
}

private struct CategoryLifetimeSheet: View {
    let rows: [CategoryLifetimeTotalPayload]
    let selectedCategory: String
    let onSelect: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List(rows) { row in
                Button {
                    onSelect(row.category)
                } label: {
                    HStack(spacing: 12) {
                        Text(row.category)
                            .font(.system(size: 14, weight: row.category == selectedCategory ? .bold : .semibold, design: .rounded))
                            .foregroundStyle(.primary)
                            .multilineTextAlignment(.leading)
                        Spacer(minLength: 8)
                        Text(nativeMoneyValue(row.total))
                            .font(.system(size: 13, weight: .bold, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                }
                .buttonStyle(.plain)
            }
            .navigationTitle("All Categories")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Close") { dismiss() }
                }
            }
        }
    }
}

private struct CategoryPrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        let palette = QuailTheme.palette(for: UserDefaults.standard.string(forKey: "quail.settings.theme") ?? "system")
        configuration.label
            .font(.system(size: 12, weight: .semibold, design: .rounded))
            .foregroundStyle(palette.primaryButtonText)
            .padding(.horizontal, 12)
            .frame(height: 36)
            .background(palette.primaryButton.opacity(configuration.isPressed ? 0.82 : 1), in: RoundedRectangle(cornerRadius: 11, style: .continuous))
    }
}

private struct CategorySecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        let palette = QuailTheme.palette(for: UserDefaults.standard.string(forKey: "quail.settings.theme") ?? "system")
        configuration.label
            .font(.system(size: 12, weight: .semibold, design: .rounded))
            .foregroundStyle(palette.secondaryButtonText)
            .padding(.horizontal, 12)
            .frame(height: 36)
            .background(palette.secondaryButton.opacity(configuration.isPressed ? 0.88 : 1), in: RoundedRectangle(cornerRadius: 11, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 11, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

private struct CategoryChipButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        let palette = QuailTheme.palette(for: UserDefaults.standard.string(forKey: "quail.settings.theme") ?? "system")
        configuration.label
            .font(.system(size: 12, weight: .semibold, design: .rounded))
            .foregroundStyle(palette.secondaryButtonText)
            .padding(.horizontal, 10)
            .frame(height: 32)
            .background(palette.secondaryButton.opacity(configuration.isPressed ? 0.72 : 0.92), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

private struct AccountPageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    let account: BankAccountPayload
    let auditMode: Bool

    var body: some View {
        PageShell(title: auditMode ? "Audit" : "Account", subtitle: account.name) {
            VStack(alignment: .leading, spacing: 12) {
                detailRow("Balance", nativeFormatAccountBalance(account.total))
                detailRow("CSV", account.lastCsvUploadAt ?? "—")
                detailRow("Verified", account.lastManualVerifiedAt ?? "—")
                detailRow("Credit limit", account.creditLimit.map { nativeMoneyValue($0) } ?? "—")
                NavigationLink(value: AppRoute.bankInfo) {
                    detailLink("Open bank info")
                }
                NavigationLink(value: AppRoute.csvImport) {
                    detailLink("Import CSV/Excel")
                }
            }
        }
        .navigationTitle(account.name)
        .navigationBarTitleDisplayMode(.inline)
    }

    private func detailRow(_ label: String, _ value: String) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return HStack {
            Text(label)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.system(size: 13, weight: .bold, design: .rounded))
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func detailLink(_ label: String) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return HStack {
            Text(label)
                .font(.system(size: 13, weight: .semibold, design: .rounded))
            Spacer()
            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

func nativeMoneyValue(_ value: Double) -> String {
    let formatter = NumberFormatter()
    formatter.numberStyle = .currency
    formatter.currencyCode = "USD"
    formatter.maximumFractionDigits = 2
    formatter.minimumFractionDigits = 2
    return formatter.string(from: NSNumber(value: value)) ?? "$\(value)"
}

func nativeFormatAccountBalance(_ value: Double) -> String {
    let amount = abs(value)
    let raw = nativeMoneyValue(amount)
    if value > 0 { return raw }
    if value < 0 { return "CR \(raw)" }
    return nativeMoneyValue(0)
}

func nativeIsoToday() -> String {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter.string(from: Date())
}

func nativeShortTransactionDate(_ raw: String?) -> String {
    guard let raw, !raw.isEmpty else { return "Today" }
    let isoDayFormatter = DateFormatter()
    isoDayFormatter.locale = Locale(identifier: "en_US_POSIX")
    isoDayFormatter.calendar = Calendar(identifier: .gregorian)
    isoDayFormatter.timeZone = TimeZone(secondsFromGMT: 0)
    isoDayFormatter.dateFormat = "yyyy-MM-dd"
    if let date = isoDayFormatter.date(from: raw) {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "MMM d"
        return formatter.string(from: date)
    }
    let iso = ISO8601DateFormatter()
    iso.timeZone = TimeZone(secondsFromGMT: 0)
    if let date = iso.date(from: raw) {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "MMM d"
        return formatter.string(from: date)
    }
    return raw
}

func nativeIsoMonthStart() -> String {
    let cal = Calendar(identifier: .gregorian)
    let now = Date()
    let start = cal.date(from: cal.dateComponents([.year, .month], from: now)) ?? now
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.calendar = cal
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter.string(from: start)
}
