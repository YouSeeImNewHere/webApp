import SwiftUI
import WebKit

enum AppRoute: Hashable {
    case home
    case settings
    case notificationSettings
    case notifications
    case budget
    case analytics
    case recurring
    case allTransactions
    case bankInfo
    case csvImport
    case ruleBuilder
    case category(String)
    case account(BankAccountPayload, audit: Bool)
}

struct NativePageView: View {
    let route: AppRoute

    var body: some View {
        Group {
            switch route {
            case .home:
                HomeView()
            case .settings:
                SettingsHomePageView()
            case .notificationSettings:
                NotificationSettingsPageView()
            case .notifications:
                NotificationsPageView()
            case .budget:
                BudgetPageView()
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
            case .ruleBuilder:
                RuleBuilderPageView()
            case .category(let name):
                CategoryPageView(category: name)
            case .account(let account, let audit):
                AccountPageView(account: account, auditMode: audit)
            }
        }
        .navigationBarBackButtonHidden(true)
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
    let content: Content

    @EnvironmentObject private var navigator: AppNavigator
    init(title: String, subtitle: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.subtitle = subtitle
        self.content = content()
    }

    var body: some View {
        AppChromeFrame(
            title: title,
            badgeValue: nil,
            selectedTab: navigator.currentTab,
            onLeadingTap: { navigator.show(.settings) },
            onTrailingTap: { navigator.show(.notifications) },
            onSelectTab: handleTabSelect
        ) {
            AppPageScroll {
                content
            }
        }
    }

    private func handleTabSelect(_ tab: BottomTab) {
        switch tab {
        case .home:
            navigator.popToRoot()
        case .spending:
            navigator.show(.budget)
        case .all:
            navigator.show(.allTransactions)
        case .analytics:
            navigator.show(.analytics)
        case .recurring:
            navigator.show(.recurring)
        }
    }
}

private struct SettingsPageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @Environment(\.openURL) private var openURL

    @State private var googleStatusText = "Checking connection..."
    @State private var setupProgressText = "Loading setup progress..."
    @State private var setupProgressSubtext = ""
    @State private var cacheVersionsText = "Loading current versions..."
    @State private var viewModeText = "Loading view mode..."
    @State private var isOwner = false
    @State private var showAdminPreview = false
    @State private var layoutStatus = ""
    @State private var activeInfo: SettingsInfo?
    @State private var isRefreshingCache = false
    @State private var isLoading = true
    @State private var setupProgressPercent = 0

    private let themes: [(String, String)] = [
        ("system", "System"),
        ("light", "Default (Light)"),
        ("dark", "Dark"),
        ("oled", "OLED Black"),
        ("solarized", "Solarized"),
        ("forest", "Forest"),
        ("midnight", "Midnight Blue"),
    ]

    var body: some View {
        PageShell(title: "Settings", subtitle: "App-level shortcuts and account tools") {
            VStack(alignment: .leading, spacing: 12) {
                settingsSection(title: "Appearance") {
                    VStack(alignment: .leading, spacing: 10) {
                        Picker("Color scheme", selection: $themeSelection) {
                            ForEach(themes, id: \.0) { theme in
                                Text(theme.1).tag(theme.0)
                            }
                        }
                        .pickerStyle(.menu)

                        Text("Tip: System follows your device theme.")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }

                settingsSection(title: "Google Gmail") {
                    HStack(alignment: .center, spacing: 12) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("OAuth connection")
                                .font(.system(size: 14, weight: .semibold, design: .rounded))
                            Text(googleStatusText)
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button {
                            if let url = URL(string: AppConfig.url(path: "/gmail/oauth/start", queryItems: [
                                URLQueryItem(name: "next", value: "/settings")
                            ]).absoluteString) {
                                openURL(url)
                            }
                        } label: {
                            Text(googleStatusText.contains("Connected") ? "Reconnect Google" : "Connect Google")
                                .font(.system(size: 13, weight: .semibold, design: .rounded))
                                .padding(.horizontal, 12)
                                .padding(.vertical, 10)
                                .background(Color.black, in: Capsule(style: .continuous))
                                .foregroundStyle(.white)
                        }
                        .buttonStyle(.plain)
                    }
                }

                settingsSection(title: "Notifications") {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(alignment: .center, spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Smart notifications")
                                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                                Text("Spending power, overspending protection, and savings nudges.")
                                    .font(.system(size: 12, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            NavigationLink(value: AppRoute.notificationSettings) {
                                settingsActionChip("Open Page")
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }

                settingsSection(title: "Home Page Layout") {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(spacing: 8) {
                            Button {
                                activeInfo = .homeLayout
                            } label: { settingsActionChip("Customize Home Layout") }
                            .buttonStyle(.plain)

                            Button {
                                layoutStatus = "Layout reset is managed on the home screen."
                            } label: { settingsActionChip("Reset layout to default") }
                            .buttonStyle(.plain)
                        }

                        Text("Tip: tap Customize Home Layout, drag cards/sections around, then press Done.")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)

                        if !layoutStatus.isEmpty {
                            Text(layoutStatus)
                                .font(.system(size: 12, weight: .semibold, design: .rounded))
                                .foregroundStyle(.secondary)
                        }

                        Divider().opacity(0.14)

                        HStack(alignment: .center, spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Cache refresh")
                                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                                Text("Force rebuild and push latest home and widget values into cache now.")
                                    .font(.system(size: 12, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button {
                                Task { await refreshCache() }
                            } label: {
                                settingsActionChip(isRefreshingCache ? "Refreshing..." : "Cache Refresh")
                            }
                            .buttonStyle(.plain)
                            .disabled(isRefreshingCache)
                        }

                        Text(cacheVersionsText)
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }

                settingsSection(title: "Widgets") {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(alignment: .center, spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Widget setup")
                                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                                Text("Configure iOS widget workflows and preview data.")
                                    .font(.system(size: 12, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button { activeInfo = .widgetSetup } label: {
                                settingsActionChip("Open Page")
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }

                settingsSection(title: "Initial Setup") {
                    VStack(alignment: .leading, spacing: 10) {
                        setupProgressView

                        HStack(spacing: 8) {
                            Button { activeInfo = .setupWizard } label: { settingsActionChip("Open Wizard") }
                            Button { activeInfo = .parserWizard } label: { settingsActionChip("Parser Wizard") }
                            Button { activeInfo = .externalApps } label: { settingsActionChip("External Apps") }
                        }
                        .buttonStyle(.plain)

                        HStack(spacing: 8) {
                            NavigationLink(value: AppRoute.csvImport) { settingsActionChip("CSV Import") }
                            NavigationLink(value: AppRoute.bankInfo) { settingsActionChip("Bank Info") }
                        }
                        .buttonStyle(.plain)

                        Text(setupProgressSubtext)
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }

                settingsSection(title: "Rules") {
                    HStack(alignment: .center, spacing: 12) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Category regex rules")
                                .font(.system(size: 14, weight: .semibold, design: .rounded))
                            Text("View matches, test regex, re-apply, disable, or delete rules.")
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        NavigationLink(value: AppRoute.ruleBuilder) {
                            settingsActionChip("Open Page")
                        }
                        .buttonStyle(.plain)
                    }
                }

                if isOwner {
                    settingsSection(title: "Admin") {
                        VStack(alignment: .leading, spacing: 10) {
                            HStack(alignment: .center, spacing: 12) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("View mode")
                                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                                    Text(viewModeText)
                                        .font(.system(size: 12, weight: .medium, design: .rounded))
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Button {
                                    showAdminPreview.toggle()
                                    viewModeText = showAdminPreview ? "Previewing as non-admin." : "Admin view."
                                } label: {
                                    settingsActionChip(showAdminPreview ? "Return to Admin View" : "Preview as Non-Admin")
                                }
                                .buttonStyle(.plain)
                            }

                            Divider().opacity(0.14)

                            HStack(alignment: .center, spacing: 12) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Owner admin console")
                                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                                    Text("Tenant management, pending user approvals, and tenant data purge.")
                                        .font(.system(size: 12, weight: .medium, design: .rounded))
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Button {
                                    activeInfo = .adminConsole
                                } label: {
                                    settingsActionChip("Open Admin Console")
                                }
                                .buttonStyle(.plain)
                            }

                            Divider().opacity(0.14)

                            HStack(alignment: .center, spacing: 12) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Widget setup links")
                                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                                    Text("Open platform-specific widget setup pages directly.")
                                        .font(.system(size: 12, weight: .medium, design: .rounded))
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                HStack(spacing: 8) {
                                    Button { activeInfo = .widgetSetup } label: { settingsActionChip("iOS Widgets") }
                                    Button { activeInfo = .externalApps } label: { settingsActionChip("Android Widgets") }
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle("Settings")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await loadSettings()
        }
        .sheet(item: $activeInfo) { info in
            SettingsInfoSheetView(info: info)
        }
    }

    private func settingsSection<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title.uppercased())
                .font(.system(size: 12, weight: .bold, design: .rounded))
                .foregroundStyle(.secondary)
                .tracking(0.6)
            VStack(alignment: .leading, spacing: 12) {
                content()
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
        }
    }

    private var setupProgressView: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(setupProgressText)
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                Spacer()
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule(style: .continuous)
                        .fill(Color.black.opacity(0.08))
                        .frame(height: 10)
                    Capsule(style: .continuous)
                        .fill(LinearGradient(colors: [Color.green, Color.mint], startPoint: .leading, endPoint: .trailing))
                        .frame(width: max(0, geo.size.width * CGFloat(max(0, min(100, setupProgressPercent))) / 100.0), height: 10)
                }
            }
            .frame(height: 10)
        }
    }

    private func settingsActionChip(_ title: String) -> some View {
        Text(title)
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .lineLimit(1)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .foregroundStyle(.white)
            .background(Color.black, in: Capsule(style: .continuous))
    }

    private func loadSettings() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let googleOut = try await SettingsNetworking.fetch("/gmail/oauth/status", as: SettingsGoogleOAuthStatusPayload.self)
            if googleOut.connected == true {
                googleStatusText = googleOut.email.flatMap { "Connected as \($0)" } ?? "Connected"
            } else {
                googleStatusText = "Not connected"
            }
        } catch {
            googleStatusText = "Connection status unavailable"
        }

        do {
            let setupOut = try await SettingsNetworking.fetch("/settings/initial-setup-status", as: SettingsInitialSetupPayload.self)
            setupProgressPercent = setupOut.percent ?? 0
            let counts = setupOut.counts
            setupProgressText = "\(setupProgressPercent)% complete (\(counts?.requirementsDone ?? 0)/\(counts?.requirementsTotal ?? 0) setup checks)"
            setupProgressSubtext = "CSV mapping: \(counts?.accountsWithCsvMapping ?? 0)/\(counts?.accountsTotal ?? 0) | Email parser: \(counts?.accountsWithParser ?? 0)/\(counts?.accountsExpectEmail ?? 0)"
        } catch {
            setupProgressText = "Setup progress unavailable"
            setupProgressSubtext = "Could not load setup completion status."
        }

        do {
            let cacheOut = try await SettingsNetworking.fetch("/settings/cache-versions", as: SettingsCacheVersionsPayload.self)
            cacheVersionsText = "Current versions: Home v\(cacheOut.homeSnapshotVersion ?? 0), Widget v\(cacheOut.widgetVersion ?? 0)."
        } catch {
            cacheVersionsText = "Current versions unavailable."
        }

        do {
            let flagsOut = try await SettingsNetworking.fetch("/settings/view-flags", as: SettingsViewFlagsPayload.self)
            isOwner = flagsOut.isOwner ?? false
            viewModeText = isOwner ? "Admin view." : "Non-admin view."
        } catch {
            isOwner = false
            viewModeText = "View mode unavailable."
        }
    }

    private func refreshCache() async {
        guard !isRefreshingCache else { return }
        isRefreshingCache = true
        defer { isRefreshingCache = false }
        do {
            let result = try await SettingsNetworking.fetch("/settings/refresh-home-widget-cache", method: "POST", as: SettingsRefreshCachePayload.self)
            cacheVersionsText = "Cache refreshed. Home v\(result.homeSnapshotVersion ?? 0), Widget v\(result.widgetVersion ?? 0)."
        } catch {
            cacheVersionsText = "Refresh failed: \(error.localizedDescription)"
        }
    }
}

private struct NotificationSettingsPageView: View {
    @State private var prefs: [String: Bool] = [:]
    @State private var userKeyStatus = "Loading..."
    @State private var statusMessage = ""
    @State private var isSaving = false

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
        ("user_signup_pending", "User signup pending", "Admin notification for pending signups."),
        ("cron_error", "Cron error", "Alert on scheduled job failures."),
    ]

    var body: some View {
        PageShell(title: "Notifications", subtitle: "Smart notifications and alert preferences") {
            VStack(alignment: .leading, spacing: 12) {
                settingsCard {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Smart notifications")
                            .font(.system(size: 16, weight: .bold, design: .rounded))
                        Text("Spending power, overspending protection, and savings nudges.")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                        Text(userKeyStatus)
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }

                settingsCard {
                    VStack(spacing: 8) {
                        ForEach(rows, id: \.key) { row in
                            HStack(alignment: .center, spacing: 12) {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(row.title)
                                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                                    Text(row.subtitle)
                                        .font(.system(size: 12, weight: .medium, design: .rounded))
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Toggle("", isOn: Binding(
                                    get: { prefs[row.key] ?? false },
                                    set: { newValue in
                                        prefs[row.key] = newValue
                                        Task { await savePref(key: row.key, value: newValue) }
                                    }
                                ))
                                .labelsHidden()
                            }
                            .padding(.vertical, 4)
                            if row.key != rows.last?.key {
                                Divider().opacity(0.12)
                            }
                        }
                    }
                }
                if !statusMessage.isEmpty {
                    Text(statusMessage)
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
        }
        .task { await load() }
    }

    private func settingsCard<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        content()
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
    }

    private func load() async {
        do {
            let out = try await SettingsNetworking.fetch("/settings/notifications", as: SettingsNotificationSettingsPayload.self)
            prefs = out.prefs
            if let key = out.pushoverUserKey, !key.isEmpty {
                userKeyStatus = "Pushover key set."
            } else {
                userKeyStatus = "Pushover key not set."
            }
        } catch {
            userKeyStatus = "Notification settings unavailable."
        }
    }

    private func savePref(key: String, value: Bool) async {
        guard !isSaving else { return }
        isSaving = true
        defer { isSaving = false }
        do {
            _ = try await SettingsNetworking.fetch("/settings/notifications", method: "POST", jsonBody: [key: value], as: SettingsNotificationSettingsPayload.self)
            statusMessage = "Saved."
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                if statusMessage == "Saved." { statusMessage = "" }
            }
        } catch {
            statusMessage = "Failed to save."
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
    @State private var items: [NotificationItemPayload] = []
    @State private var errorMessage: String?
    @State private var isLoading = true

    var body: some View {
        PageShell(title: "Notifications", subtitle: "The same unread drawer as the web app") {
            Group {
                if isLoading {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 24)
                } else if let errorMessage {
                    Text(errorMessage)
                        .foregroundStyle(.secondary)
                } else if items.isEmpty {
                    Text("No notifications.")
                        .foregroundStyle(.secondary)
                } else {
                    VStack(spacing: 10) {
                        ForEach(items) { item in
                            VStack(alignment: .leading, spacing: 4) {
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
                                Text(item.kind ?? "")
                                    .font(.system(size: 12, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                            .padding(14)
                            .background(Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
                        }
                    }
                }
            }
        }
        .navigationTitle("Notifications")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func load() async {
        isLoading = true
        do {
            items = try await QuailCashAPI.shared.fetchNotifications(limit: 100)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}

private struct BudgetPageView: View {
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
        VStack(alignment: .leading, spacing: 12) {
            statRow("Safe to spend", nativeMoneyValue(monthBudget.safeToSpend ?? 0))
            statRow("Daily limit", nativeMoneyValue(monthBudget.dailyLimit ?? 0))
            statRow("Income", nativeMoneyValue(monthBudget.expectedIncome ?? 0))
            statRow("Spent so far", nativeMoneyValue(monthBudget.spentSoFar ?? 0))
            statRow("Remaining bills", nativeMoneyValue(monthBudget.billsRemaining ?? 0))
            statRow("Extra saved", nativeMoneyValue(extraSaved ?? 0))
        }
        .padding(14)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
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
        HStack {
            Text(title)
            Spacer()
            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
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
        HStack {
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
        .background(Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
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
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.system(size: 16, weight: .bold, design: .rounded))
            ForEach(items, id: \.self) { item in
                Text(item)
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
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

private struct RuleBuilderPageView: View {
    var body: some View {
        PageShell(title: "Unassigned", subtitle: "Create a category rule for uncategorized transactions") {
            VStack(alignment: .leading, spacing: 12) {
                Text("This is the native redirect target for the Unassigned row.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                Text("Next step: port the original rule form and keyword matcher here.")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                NavigationLink(value: AppRoute.analytics) {
                    settingsRow(title: "Go to Analytics", subtitle: "See the category context")
                }
            }
        }
        .navigationTitle("Unassigned")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func settingsRow(title: String, subtitle: String) -> some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.system(size: 15, weight: .semibold, design: .rounded))
                Text(subtitle)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
    }
}

private struct CategoryPageView: View {
    let category: String
    @State private var transactions: [TransactionItem] = []
    @State private var errorMessage: String?
    @State private var isLoading = true

    var body: some View {
        PageShell(title: category, subtitle: "Category transactions and totals") {
            Group {
                if isLoading {
                    ProgressView().padding(.vertical, 24)
                } else if let errorMessage {
                    Text(errorMessage).foregroundStyle(.secondary)
                } else {
                    VStack(spacing: 10) {
                        ForEach(transactions) { tx in
                            HStack {
                                VStack(alignment: .leading, spacing: 3) {
                                    Text(tx.merchant.isEmpty ? "Unknown merchant" : tx.merchant)
                                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                                        .textCase(.uppercase)
                                    Text([tx.bank, tx.card].compactMap { $0 }.joined(separator: " • "))
                                        .font(.system(size: 11, weight: .medium, design: .rounded))
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                let amountText = nativeMoneyValue(tx.amount)
                                Text(amountText)
                                    .font(.system(size: 14, weight: .bold, design: .rounded))
                            }
                            .padding(14)
                            .background(Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
                        }
                    }
                }
            }
        }
        .navigationTitle(category)
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func load() async {
        isLoading = true
        do {
            let start = nativeIsoMonthStart()
            let end = nativeIsoToday()
            transactions = try await QuailCashAPI.shared.fetchCategoryTransactions(category: category, start: start, end: end, limit: 100)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}

private struct AccountPageView: View {
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
        HStack {
            Text(label)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.system(size: 13, weight: .bold, design: .rounded))
        }
        .padding(14)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
    }

    private func detailLink(_ label: String) -> some View {
        HStack {
            Text(label)
                .font(.system(size: 13, weight: .semibold, design: .rounded))
            Spacer()
            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
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
    if value < 0 { return raw }
    if value > 0 { return "CR \(raw)" }
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
