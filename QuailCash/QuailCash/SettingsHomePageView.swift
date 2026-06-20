import SwiftUI
import UIKit
import Combine

struct SettingsHomePageView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var navigator: AppNavigator
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @AppStorage("quail.home.layout.customized") private var homeLayoutCustomized: Bool = false

    @StateObject private var model = SettingsHomeViewModel()
    @State private var showGoogleAuth = false
    @State private var activeSheet: SettingsSheet?
    @State private var backfillDaysText = "7"
    @State private var backfillIncludeProcessed = true
    @State private var backfillStatus = ""
    @State private var backfillLog = ""
    @State private var backfillRows: [SettingsBackfillRow] = []

    private let themes: [(String, String)] = [
        ("system", "System"),
        ("light", "Default (Light)"),
        ("dark", "Dark"),
        ("oled", "OLED Black"),
        ("solarized", "Solarized"),
        ("forest", "Forest"),
        ("midnight", "Midnight Blue"),
    ]
    private let settingsActionButtonWidth: CGFloat = 160
    private let settingsActionButtonHeight: CGFloat = 42

    var body: some View {
        AppChromeFrame(
            title: "Settings",
            badgeValue: nil,
            selectedTab: navigator.currentTab,
            onLeadingTap: { navigator.popToRoot() },
            onTrailingTap: { navigator.show(.notifications) },
            onSelectTab: { tab in
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
        ) {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    settingsSection(title: "Appearance") {
                        VStack(alignment: .leading, spacing: 10) {
                            HStack(alignment: .bottom, spacing: 12) {
                                VStack(alignment: .leading, spacing: 6) {
                                    Text("Color scheme")
                                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                                    Picker("Color scheme", selection: $themeSelection) {
                                        ForEach(themes, id: \.0) { theme in
                                            Text(theme.1).tag(theme.0)
                                        }
                                    }
                                    .pickerStyle(.menu)
                                    .tint(.black)
                                    .frame(maxWidth: 150, alignment: .leading)
                                }
                                Spacer(minLength: 0)
                            }

                            Text("Tip: System follows your device theme.")
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                    }

                    settingsSection(title: "Google Gmail") {
                        VStack(alignment: .leading, spacing: 10) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("OAuth connection")
                                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                                Text(model.googleStatusText)
                                    .font(.system(size: 12, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                            Button {
                                showGoogleAuth = true
                            } label: {
                                settingsPrimaryButton(model.googleStatusText.hasPrefix("Connected") ? "Reconnect Google" : "Connect Google")
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    settingsSection(title: "Notifications") {
                        VStack(alignment: .leading, spacing: 10) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Smart notifications")
                                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                                Text("Spending power, overspending protection, and savings nudges.")
                                    .font(.system(size: 12, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                            Button {
                                navigator.show(.notifications)
                            } label: {
                                settingsPrimaryButton("Open Page")
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    settingsSection(title: "Home Page Layout") {
                        VStack(alignment: .leading, spacing: 0) {
                            VStack(alignment: .leading, spacing: 10) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Customize home layout")
                                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                                    Text("Drag cards and sections around, then press Done.")
                                        .font(.system(size: 12, weight: .medium, design: .rounded))
                                        .foregroundStyle(.secondary)
                                }
                                Button {
                                    activeSheet = .homeLayout
                                } label: {
                                    settingsPrimaryButton("Customize Home Layout")
                                }
                                .buttonStyle(.plain)
                            }

                            Divider().opacity(0.18)

                            VStack(alignment: .leading, spacing: 10) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Reset layout")
                                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                                    Text("Return to the default page arrangement.")
                                        .font(.system(size: 12, weight: .medium, design: .rounded))
                                        .foregroundStyle(.secondary)
                                }
                                Button {
                                    homeLayoutCustomized = false
                                    model.layoutStatus = "Layout reset to default."
                                } label: {
                                    settingsSecondaryButton("Reset")
                                }
                                .buttonStyle(.plain)
                            }

                            if !model.layoutStatus.isEmpty {
                                Divider().opacity(0.18)
                                Text(model.layoutStatus)
                                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                                    .foregroundStyle(.secondary)
                                    .padding(.top, 10)
                            }

                            Divider().opacity(0.18)

                            VStack(alignment: .leading, spacing: 10) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("Cache refresh")
                                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                                    Text("Force rebuild and push latest home and widget values into cache now.")
                                        .font(.system(size: 12, weight: .medium, design: .rounded))
                                        .foregroundStyle(.secondary)
                                }
                                Button {
                                    Task { await model.refreshCache() }
                                } label: {
                                    settingsSecondaryButton(model.isRefreshingCache ? "Refreshing..." : "Cache Refresh")
                                }
                                .buttonStyle(.plain)
                                .disabled(model.isRefreshingCache)
                            }

                            Text(model.cacheVersionsText)
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                                .padding(.top, 8)
                        }
                    }

                    settingsSection(title: "Widgets") {
                        VStack(alignment: .leading, spacing: 10) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Widget setup")
                                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                                Text("Open iPhone widget setup.")
                                    .font(.system(size: 12, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                            Button {
                                activeSheet = .widgetSetup(.ios)
                            } label: {
                                settingsPrimaryButton("Open Page")
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    settingsSection(title: "Initial Setup") {
                        VStack(alignment: .leading, spacing: 10) {
                            setupProgressView

                            setupActionRow(
                                title: "Setup wizard",
                                subtitle: "Open the onboarding wizard anytime.",
                                buttonTitle: "Open Wizard",
                                action: { activeSheet = .initialSetup }
                            )

                            Divider().opacity(0.18)

                            setupActionRow(
                                title: "Parser wizard",
                                subtitle: "Create and maintain live parser rules.",
                                buttonTitle: "Open Wizard",
                                action: { activeSheet = .parserWizard }
                            )

                            Divider().opacity(0.18)

                            setupActionRow(
                                title: "External apps",
                                subtitle: "Install required mobile apps for widgets and push notifications.",
                                buttonTitle: "Open Page",
                                action: { activeSheet = .externalApps }
                            )

                            backfillPanel

                            Divider().opacity(0.18)

                            setupActionRow(
                                title: "Income wizard",
                                subtitle: "Set up LES, salary, or hourly income settings on a dedicated page.",
                                buttonTitle: "Open Page",
                                action: { activeSheet = .incomeWizard }
                            )

                            Text(model.setupProgressSubtext)
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                    }

                    settingsSection(title: "Rules") {
                        VStack(alignment: .leading, spacing: 10) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Category regex rules")
                                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                                Text("View matches, test regex, re-apply, disable, or delete rules.")
                                    .font(.system(size: 12, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                            NavigationLink(value: AppRoute.ruleBuilder) {
                                settingsPrimaryButton("Open Page")
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    if model.isOwner {
                        settingsSection(title: "Admin") {
                            VStack(alignment: .leading, spacing: 0) {
                                VStack(alignment: .leading, spacing: 10) {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text("View mode")
                                            .font(.system(size: 14, weight: .semibold, design: .rounded))
                                        Text(model.viewModeText)
                                            .font(.system(size: 12, weight: .medium, design: .rounded))
                                            .foregroundStyle(.secondary)
                                    }
                                    Button {
                                        model.nonAdminPreview.toggle()
                                        model.viewModeText = model.nonAdminPreview ? "Previewing as non-admin." : "Admin view."
                                    } label: {
                                        settingsSecondaryButton(model.nonAdminPreview ? "Return to Admin View" : "Preview as Non-Admin")
                                    }
                                    .buttonStyle(.plain)
                                }

                                if !model.nonAdminPreview {
                                    Divider().opacity(0.18)

                                    VStack(alignment: .leading, spacing: 10) {
                                        VStack(alignment: .leading, spacing: 4) {
                                            Text("Owner admin console")
                                                .font(.system(size: 14, weight: .semibold, design: .rounded))
                                            Text("Tenant management, pending user approvals, and tenant data purge.")
                                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                                .foregroundStyle(.secondary)
                                        }
                                        Button {
                                            activeSheet = .adminConsole
                                        } label: {
                                            settingsPrimaryButton("Open Admin Console")
                                        }
                                        .buttonStyle(.plain)
                                    }

                                    Divider().opacity(0.18)

                                    VStack(alignment: .leading, spacing: 10) {
                                        VStack(alignment: .leading, spacing: 4) {
                                            Text("Widget setup links")
                                                .font(.system(size: 14, weight: .semibold, design: .rounded))
                                            Text("Open platform-specific widget setup pages directly.")
                                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                                .foregroundStyle(.secondary)
                                        }
                                        VStack(alignment: .leading, spacing: 8) {
                                            Button { activeSheet = .widgetSetup(.ios) } label: { settingsSecondaryButton("iOS Widgets") }
                                            Button { activeSheet = .widgetSetup(.android) } label: { settingsSecondaryButton("Android Widgets") }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                .padding(.horizontal, 10)
                .padding(.top, 12)
                .padding(.bottom, 18)
            }
        }
        .task {
            await model.load()
        }
        .sheet(isPresented: $showGoogleAuth) {
            AuthSessionView(
                startURL: AppConfig.url(path: "/gmail/oauth/start", queryItems: [
                    URLQueryItem(name: "next", value: "/settings")
                ]),
                callbackScheme: AppConfig.callbackScheme,
                onAuthenticated: {
                    Task {
                        await model.reloadGoogleStatus()
                        await model.loadUnreadCount()
                    }
                },
                onCancel: {}
            )
        }
        .sheet(item: $activeSheet) { sheet in
            switch sheet {
            case .homeLayout:
                HomeLayoutSheet(homeLayoutCustomized: $homeLayoutCustomized)
            case .widgetSetup(let platform):
                WidgetSetupSheet(platform: platform)
            case .initialSetup:
                InitialSetupSheet(
                    onConnectGoogle: { showGoogleAuth = true },
                    onOpenNotifications: { navigator.show(.notifications) },
                    onOpenBankInfo: { activeSheet = .bankInfo },
                    onOpenCsvImport: { activeSheet = .csvImport },
                    onOpenIncomeWizard: { activeSheet = .incomeWizard },
                    onOpenParserWizard: { activeSheet = .parserWizard },
                    onOpenExternalApps: { activeSheet = .externalApps }
                )
            case .parserWizard:
                ParserWizardSheet(backfillDaysText: $backfillDaysText,
                                  includeProcessed: $backfillIncludeProcessed,
                                  status: $backfillStatus,
                                  logText: $backfillLog,
                                  rows: $backfillRows)
            case .externalApps:
                ExternalAppsSheet(
                    onOpenIosWidgets: { activeSheet = .widgetSetup(.ios) },
                    onOpenAndroidWidgets: { activeSheet = .widgetSetup(.android) }
                )
            case .incomeWizard:
                IncomeWizardSheet()
            case .adminConsole:
                AdminConsoleSheet(
                    nonAdminPreview: $model.nonAdminPreview,
                    viewModeText: $model.viewModeText,
                    onOpenIosWidgets: { activeSheet = .widgetSetup(.ios) },
                    onOpenAndroidWidgets: { activeSheet = .widgetSetup(.android) }
                )
            case .bankInfo, .csvImport, .ruleBuilder:
                EmptyView()
            }
        }
    }

    private var setupProgressView: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(model.setupProgressText)
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
                        .frame(width: max(0, geo.size.width * CGFloat(max(0, min(100, model.setupProgressPercent))) / 100.0), height: 10)
                }
            }
            .frame(height: 10)
        }
    }

    private var backfillPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            Divider().opacity(0.18)

            VStack(alignment: .leading, spacing: 4) {
                Text("Manual backfill parse")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                Text("Re-scan previous emails and insert missing transactions.")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }

            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    Text("Lookback days")
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                    TextField("7", text: $backfillDaysText)
                        .keyboardType(.numberPad)
                        .multilineTextAlignment(.center)
                        .frame(width: 56, height: 26)
                        .background(Color.black.opacity(0.08), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                }
                .font(.system(size: 13, weight: .medium, design: .rounded))

                Button {
                    Task { await runBackfillParse() }
                } label: {
                    settingsSecondaryButton("Run", width: 84)
                }
                .buttonStyle(.plain)
            }

            Toggle("Include already processed", isOn: $backfillIncludeProcessed)
                .tint(.black)
                .font(.system(size: 13, weight: .semibold, design: .rounded))

            if !backfillStatus.isEmpty {
                Text(backfillStatus)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }

            if !backfillLog.isEmpty {
                Text(backfillLog)
                    .font(.system(size: 11, weight: .regular, design: .monospaced))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
                    .background(Color.black.opacity(0.04), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }

            if !backfillRows.isEmpty {
                VStack(spacing: 8) {
                    ForEach(backfillRows) { row in
                        VStack(alignment: .leading, spacing: 6) {
                            HStack {
                                Text(row.title)
                                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                                Spacer()
                                Text(row.statusText)
                                    .font(.system(size: 11, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                            Text(row.subject)
                                .font(.system(size: 11, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                            if let preview = row.preview, !preview.isEmpty {
                                Text(preview)
                                    .font(.system(size: 11, weight: .regular, design: .monospaced))
                                    .lineLimit(4)
                            }
                        }
                        .padding(12)
                        .background(Color.black.opacity(0.04), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    }
                }
            }
        }
    }

    private func setupActionRow(title: String, subtitle: String, buttonTitle: String, action: @escaping () -> Void) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                Text(subtitle)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            Button(action: action) {
                settingsSecondaryButton(buttonTitle)
            }
            .buttonStyle(.plain)
        }
    }

    private func settingsSection<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title.uppercased())
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .padding(.leading, 4)
            settingsCard(content: content)
        }
    }

    private func settingsCard<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        content()
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
    }

    private func settingsPrimaryButton(_ title: String, width: CGFloat? = nil) -> some View {
        Text(title)
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .lineLimit(1)
            .minimumScaleFactor(0.78)
            .frame(width: width ?? settingsActionButtonWidth, height: settingsActionButtonHeight)
            .foregroundStyle(.white)
            .background(Color.black, in: Capsule(style: .continuous))
    }

    private func settingsSecondaryButton(_ title: String, width: CGFloat? = nil) -> some View {
        Text(title)
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .lineLimit(1)
            .minimumScaleFactor(0.78)
            .frame(width: width ?? settingsActionButtonWidth, height: settingsActionButtonHeight)
            .foregroundStyle(.primary)
            .background(Color.white, in: Capsule(style: .continuous))
            .overlay(Capsule(style: .continuous).stroke(.black.opacity(0.10), lineWidth: 1))
    }

    private func runBackfillParse() async {
        let days = max(1, min(99, Int(backfillDaysText.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 7))
        backfillStatus = "Starting parser backfill..."
        backfillLog = ""
        backfillRows = []
        do {
            let startOut = try await SettingsAPI.fetch("/settings/email-parser/run/start", method: "POST", jsonBody: [
                "days": days,
                "include_processed": backfillIncludeProcessed,
                "max_emails": 5000,
            ], as: SettingsBackfillStartPayload.self)
            guard let jobID = startOut.jobID else { throw NSError(domain: "backfill", code: 0) }
            while true {
                try await Task.sleep(nanoseconds: 900_000_000)
                let poll = try await SettingsAPI.fetch("/settings/email-parser/run/status?job_id=\(jobID)", as: SettingsBackfillStatusPayload.self)
                if poll.status == "done" {
                    let result = poll.result
                    backfillStatus = "Backfill complete."
                    backfillLog = formatBackfillLog(result)
                    backfillRows = formatBackfillRows(result)
                    break
                } else if poll.status == "failed" {
                    backfillStatus = "Backfill failed."
                    break
                } else {
                    backfillStatus = "Running parser backfill..."
                }
            }
        } catch {
            backfillStatus = "Backfill failed."
        }
    }

    private func formatBackfillLog(_ out: SettingsBackfillResultPayload?) -> String {
        guard let out else { return "" }
        let summary = out.summary
        return [
            "lookback_days=\(summary?.lookbackDays ?? 0)",
            "fetched=\(summary?.fetched ?? 0)",
            "matched=\(summary?.matched ?? 0)",
            "inserted=\(summary?.inserted ?? 0)",
            "notified=\(summary?.notified ?? 0)",
            "skipped=\(summary?.skipped ?? 0)",
        ].joined(separator: " | ")
    }

    private func formatBackfillRows(_ out: SettingsBackfillResultPayload?) -> [SettingsBackfillRow] {
        guard let rowsOut = out?.rows else { return [] }
        return rowsOut.enumerated().map { index, item in
            SettingsBackfillRow(
                id: "\(index)-\(item.subject ?? "")",
                title: (item.matched ?? false) ? "MATCH" : "SKIP",
                statusText: "inserted=\(item.inserted == true) notified=\(item.notified == true)",
                subject: item.subject ?? "(no subject)",
                preview: item.bodyExcerpt ?? ""
            )
        }
    }
}

@MainActor
final class SettingsHomeViewModel: ObservableObject {
    @Published var unreadCount: Int = 0
    @Published var googleStatusText: String = "Checking connection..."
    @Published var setupProgressText: String = "Loading setup progress..."
    @Published var setupProgressSubtext: String = ""
    @Published var setupProgressPercent: Int = 0
    @Published var cacheVersionsText: String = "Loading current versions..."
    @Published var viewModeText: String = "Loading view mode..."
    @Published var isOwner: Bool = false
    @Published var nonAdminPreview: Bool = false
    @Published var isRefreshingCache: Bool = false
    @Published var layoutStatus: String = ""

    func load() async {
        await loadUnreadCount()
        await reloadGoogleStatus()
        await loadInitialSetup()
        await loadCacheVersions()
        await loadViewFlags()
    }

    func loadUnreadCount() async {
        do {
            let out = try await SettingsAPI.fetch("/notifications/unread-count", as: SettingsUnreadCountPayload.self)
            unreadCount = max(0, out.unread)
        } catch {
            unreadCount = 0
        }
    }

    func reloadGoogleStatus() async {
        do {
            let out = try await SettingsAPI.fetch("/gmail/oauth/status", as: SettingsGoogleOAuthStatusPayload.self)
            if out.connected == true {
                let email = out.email?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                googleStatusText = email.isEmpty ? "Connected" : "Connected as \(email)"
            } else {
                googleStatusText = "Not connected"
            }
        } catch {
            googleStatusText = "Connection status unavailable."
        }
    }

    func loadInitialSetup() async {
        do {
            let out = try await SettingsAPI.fetch("/settings/initial-setup-status", as: SettingsInitialSetupPayload.self)
            setupProgressPercent = out.percent ?? 0
            let counts = out.counts
            setupProgressText = "\(setupProgressPercent)% complete (\(counts?.requirementsDone ?? 0)/\(counts?.requirementsTotal ?? 0) setup checks)"
            setupProgressSubtext = "CSV mapping: \(counts?.accountsWithCsvMapping ?? 0)/\(counts?.accountsTotal ?? 0) | Email parser: \(counts?.accountsWithParser ?? 0)/\(counts?.accountsExpectEmail ?? 0)"
        } catch {
            setupProgressText = "Setup progress unavailable"
            setupProgressSubtext = "Could not load setup completion status."
        }
    }

    func loadCacheVersions() async {
        do {
            let out = try await SettingsAPI.fetch("/settings/cache-versions", as: SettingsCacheVersionsPayload.self)
            cacheVersionsText = "Current versions: Home v\(out.homeSnapshotVersion ?? 0), Widget v\(out.widgetVersion ?? 0)."
        } catch {
            cacheVersionsText = "Current versions unavailable."
        }
    }

    func loadViewFlags() async {
        do {
            let out = try await SettingsAPI.fetch("/settings/view-flags", as: SettingsViewFlagsPayload.self)
            isOwner = out.isOwner ?? false
            viewModeText = isOwner ? "Admin view." : "Non-admin view."
        } catch {
            isOwner = false
            viewModeText = "View mode unavailable."
        }
    }

    func refreshCache() async {
        guard !isRefreshingCache else { return }
        isRefreshingCache = true
        defer { isRefreshingCache = false }
        do {
            let result = try await SettingsAPI.fetch("/settings/refresh-home-widget-cache", method: "POST", as: SettingsRefreshCachePayload.self)
            cacheVersionsText = "Cache refreshed. Home v\(result.homeSnapshotVersion ?? 0), Widget v\(result.widgetVersion ?? 0)."
        } catch {
            cacheVersionsText = "Refresh failed: \(error.localizedDescription)"
        }
    }
}

private enum SettingsSheet: Hashable, Identifiable {
    case homeLayout
    case widgetSetup(WidgetPlatform)
    case initialSetup
    case parserWizard
    case externalApps
    case incomeWizard
    case adminConsole
    case bankInfo
    case csvImport
    case ruleBuilder

    var id: String {
        switch self {
        case .homeLayout: return "homeLayout"
        case .widgetSetup(let platform): return "widgetSetup-\(platform.rawValue)"
        case .initialSetup: return "initialSetup"
        case .parserWizard: return "parserWizard"
        case .externalApps: return "externalApps"
        case .incomeWizard: return "incomeWizard"
        case .adminConsole: return "adminConsole"
        case .bankInfo: return "bankInfo"
        case .csvImport: return "csvImport"
        case .ruleBuilder: return "ruleBuilder"
        }
    }
}

private enum WidgetPlatform: String {
    case ios
    case android

    var displayName: String {
        switch self {
        case .ios: return "iPhone"
        case .android: return "Android"
        }
    }
}

private struct HomeLayoutSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var homeLayoutCustomized: Bool

    var body: some View {
        SettingsSheetShell(title: "Home Layout", subtitle: "Customize cards and section order") {
            VStack(alignment: .leading, spacing: 12) {
                Text("The native home layout editor is being rebuilt. This toggle persists the customized layout state for the home screen.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)

                Toggle("Use customized home layout", isOn: $homeLayoutCustomized)
                    .tint(.black)
                    .font(.system(size: 13, weight: .semibold, design: .rounded))

                Button {
                    homeLayoutCustomized = false
                } label: {
                    settingsSheetPrimaryButton("Reset to Default")
                }
                .buttonStyle(.plain)

                Button {
                    dismiss()
                } label: {
                    settingsSheetSecondaryButton("Done")
                }
                .buttonStyle(.plain)
            }
        }
        .presentationDetents([.medium])
    }
}

private struct SettingsSheetShell<Content: View>: View {
    let title: String
    let subtitle: String
    let content: Content

    init(title: String, subtitle: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.subtitle = subtitle
        self.content = content()
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(.system(size: 28, weight: .bold, design: .rounded))
                    Text(subtitle)
                        .font(.system(size: 13, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }

                content
            }
            .padding(16)
        }
        .background(
            LinearGradient(
                colors: [
                    Color(red: 0.98, green: 0.98, blue: 0.99),
                    Color(red: 0.94, green: 0.95, blue: 0.97)
                ],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()
        )
    }
}

private struct NotificationSettingsSheet: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var pushManager: MobilePushManager
    @State private var prefs: [String: Bool] = [:]
    @State private var userKeyStatus = "Loading..."
    @State private var iosPushStatus = "Checking iPhone push..."
    @State private var statusMessage = ""
    @State private var isSaving = false
    @State private var isSendingTest = false

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
        SettingsSheetShell(title: "Notifications", subtitle: "Smart notifications and alert preferences") {
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
                        if MobilePushManager.isAvailable {
                            Text(iosPushStatus)
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                        } else {
                            Text("iPhone push is turned off in this build while you test without a paid Apple Developer account.")
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                        if MobilePushManager.isAvailable && prefs["ios_push"] == true {
                            Button {
                                Task { await sendTestPush() }
                            } label: {
                                settingsSheetSecondaryButton(isSendingTest ? "Sending..." : "Send Test Push")
                            }
                            .buttonStyle(.plain)
                            .disabled(isSendingTest)
                            .padding(.top, 4)
                        }
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
                Button {
                    dismiss()
                } label: {
                    settingsSheetSecondaryButton("Close")
                }
                .buttonStyle(.plain)
            }
        }
        .task { await load() }
        .presentationDetents([.large])
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
            let out = try await SettingsAPI.fetch("/settings/notifications", as: SettingsNotificationSettingsPayload.self)
            prefs = out.prefs
            prefs["ios_push"] = false
            if let key = out.pushoverUserKey, !key.isEmpty {
                userKeyStatus = "Pushover key set."
            } else {
                userKeyStatus = "Pushover key not set."
            }
            iosPushStatus = MobilePushManager.isAvailable ? iosPushStatusText(from: out) : "iPhone push is unavailable in this build."
            await pushManager.refreshAuthorizationStatus()
        } catch {
            userKeyStatus = "Notification settings unavailable."
            iosPushStatus = MobilePushManager.isAvailable ? "iPhone push status unavailable." : "iPhone push is unavailable in this build."
        }
    }

    private func savePref(key: String, value: Bool) async {
        guard !isSaving else { return }
        guard key != "ios_push" else {
            prefs[key] = false
            statusMessage = "iPhone push is disabled in this build."
            return
        }
        if key == "ios_push" && value {
            let granted = await pushManager.requestAuthorizationAndRegister()
            if !granted {
                prefs[key] = false
                iosPushStatus = "Push permission is off in iPhone Settings."
                statusMessage = "Enable notifications for QuailCash in iPhone Settings."
                return
            }
        }
        isSaving = true
        defer { isSaving = false }
        do {
            let out = try await SettingsAPI.fetch("/settings/notifications", method: "POST", jsonBody: [key: value], as: SettingsNotificationSettingsPayload.self)
            iosPushStatus = iosPushStatusText(from: out)
            if key == "ios_push" && !value {
                await pushManager.unregisterCurrentDevice()
            }
            statusMessage = "Saved."
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
                if statusMessage == "Saved." { statusMessage = "" }
            }
        } catch {
            statusMessage = "Failed to save."
        }
    }

    private func iosPushStatusText(from payload: SettingsNotificationSettingsPayload) -> String {
        let count = max(0, payload.iosPushDeviceCount ?? 0)
        let configured = payload.iosPushConfigured ?? false
        if !configured {
            return "iPhone push server is not configured yet."
        }
        if count == 0 {
            return "No iPhone devices registered."
        }
        return count == 1 ? "1 iPhone registered." : "\(count) iPhones registered."
    }

    private func sendTestPush() async {
        guard !isSendingTest else { return }
        isSendingTest = true
        defer { isSendingTest = false }
        do {
            try await QuailCashAPI.shared.sendIOSTestPush()
            statusMessage = "Test push sent."
        } catch {
            statusMessage = error.localizedDescription.isEmpty ? "Failed to send test push." : error.localizedDescription
        }
    }
}

private struct WidgetSetupSheet: View {
    @Environment(\.dismiss) private var dismiss
    let platform: WidgetPlatform
    @State private var statusText = "Loading..."
    @State private var widgetScript = ""
    @State private var widgetURL = ""
    @State private var widgetVersionText = ""

    var body: some View {
        SettingsSheetShell(title: platform == .ios ? "iOS Widgets" : "Android Widgets",
                   subtitle: platform == .ios ? "Scriptable setup and widget script" : "KWGT setup and widget URL") {
            VStack(alignment: .leading, spacing: 12) {
                Text(statusText)
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)

                if platform == .ios {
                    Text("Paste the generated Scriptable code into a new script on your phone.")
                        .font(.system(size: 13, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                    Button {
                        Task { await loadWidgetScript() }
                    } label: {
                        settingsSheetPrimaryButton("Copy Script")
                    }
                    .buttonStyle(.plain)
                    Button {
                        dismiss()
                    } label: {
                        settingsSheetSecondaryButton("Close")
                    }
                    .buttonStyle(.plain)
                } else {
                    Text("Use the KWGT template and the generated widget URL.")
                        .font(.system(size: 13, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)

                    Button {
                        Task { await loadWidgetTokenAndCopyURL() }
                    } label: {
                        settingsSheetPrimaryButton("Copy Widget URL")
                    }
                    .buttonStyle(.plain)

                    Button {
                        openKWGTTemplate()
                    } label: {
                        settingsSheetSecondaryButton("Open KWGT Template")
                    }
                    .buttonStyle(.plain)

                    if !widgetURL.isEmpty {
                        Text(widgetURL)
                            .font(.system(size: 11, weight: .regular, design: .monospaced))
                            .textSelection(.enabled)
                            .padding(10)
                            .background(Color.black.opacity(0.04), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    }

                    Button {
                        dismiss()
                    } label: {
                        settingsSheetSecondaryButton("Close")
                    }
                    .buttonStyle(.plain)
                }

                if !widgetVersionText.isEmpty {
                    Text(widgetVersionText)
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }

                if !widgetScript.isEmpty && platform == .ios {
                    Text(widgetScript)
                        .font(.system(size: 11, weight: .regular, design: .monospaced))
                        .lineLimit(10)
                        .textSelection(.enabled)
                        .padding(10)
                        .background(Color.black.opacity(0.04), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
            }
        }
        .task { await load() }
        .presentationDetents([.medium, .large])
    }

    private func load() async {
        switch platform {
        case .ios:
            await loadWidgetScript()
        case .android:
            await loadWidgetTokenAndURLOnly()
        }
    }

    private func loadWidgetScript() async {
        statusText = "Generating script..."
        do {
            let out = try await SettingsAPI.fetch("/settings/widget-script", method: "POST", as: SettingsWidgetScriptPayload.self)
            widgetScript = out.script
            widgetVersionText = "Widget version \(out.widgetVersion ?? 0)"
            statusText = "Script ready."
            copyToClipboard(out.script)
        } catch {
            statusText = "Failed to generate script."
        }
    }

    private func loadWidgetTokenAndURLOnly() async {
        statusText = "Loading widget URL..."
        do {
            let tokenOut = try await SettingsAPI.fetch("/settings/widget-token", method: "POST", as: SettingsWidgetTokenPayload.self)
            let base = AppConfig.url(path: "/widget/summary")
            var comps = URLComponents(url: base, resolvingAgainstBaseURL: false)
            comps?.queryItems = [
                URLQueryItem(name: "widget_token", value: tokenOut.widgetToken),
                URLQueryItem(name: "widget_script_version", value: "3"),
            ]
            let url = comps?.url?.absoluteString ?? ""
            widgetURL = url
            statusText = "Widget URL ready."
            widgetVersionText = "Widget version \(tokenOut.widgetVersion ?? 0)"
            copyToClipboard(url)
        } catch {
            statusText = "Failed to generate widget URL."
        }
    }

    private func loadWidgetTokenAndCopyURL() async {
        await loadWidgetTokenAndURLOnly()
    }

    private func openKWGTTemplate() {
        if let url = URL(string: AppConfig.url(path: "/settings/external-apps/kwgt-template").absoluteString) {
            UIApplication.shared.open(url)
        }
    }
}

private struct InitialSetupSheet: View {
    @Environment(\.dismiss) private var dismiss
    let onConnectGoogle: () -> Void
    let onOpenNotifications: () -> Void
    let onOpenBankInfo: () -> Void
    let onOpenCsvImport: () -> Void
    let onOpenIncomeWizard: () -> Void
    let onOpenParserWizard: () -> Void
    let onOpenExternalApps: () -> Void

    @State private var setup: SettingsInitialSetupPayload?
    @State private var statusText = "Loading..."

    var body: some View {
        SettingsSheetShell(title: "Setup Wizard", subtitle: "Onboarding checklist and setup shortcuts") {
            VStack(alignment: .leading, spacing: 12) {
                if let setup {
                    setupProgressView(setup)

                    Button { onOpenCsvImport() } label: { settingsSheetPrimaryButton("CSV Import") }
                        .buttonStyle(.plain)
                    Button { onOpenBankInfo() } label: { settingsSheetPrimaryButton("Bank Info") }
                        .buttonStyle(.plain)
                    Button { onOpenIncomeWizard() } label: { settingsSheetPrimaryButton("Income Wizard") }
                        .buttonStyle(.plain)
                    Button { onConnectGoogle() } label: { settingsSheetSecondaryButton("Reconnect Google") }
                        .buttonStyle(.plain)

                    if let counts = setup.counts {
                        Text("CSV mapping: \(counts.accountsWithCsvMapping ?? 0)/\(counts.accountsTotal ?? 0) | Email parser: \(counts.accountsWithParser ?? 0)/\(counts.accountsExpectEmail ?? 0)")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                } else {
                    Text(statusText)
                        .font(.system(size: 13, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }

                Button { onOpenExternalApps() } label: { settingsSheetSecondaryButton("External Apps") }
                    .buttonStyle(.plain)

                Button {
                    dismiss()
                } label: {
                    settingsSheetSecondaryButton("Close")
                }
                .buttonStyle(.plain)
            }
        }
        .task { await load() }
        .presentationDetents([.medium, .large])
    }

    private func load() async {
        do {
            setup = try await SettingsAPI.fetch("/settings/initial-setup-status", as: SettingsInitialSetupPayload.self)
            statusText = ""
        } catch {
            statusText = "Could not load setup completion status."
        }
    }

    private func setupProgressView(_ setup: SettingsInitialSetupPayload) -> some View {
        let pct = max(0, min(100, setup.percent ?? 0))
        return VStack(alignment: .leading, spacing: 8) {
            Text("\(pct)% complete")
                .font(.system(size: 13, weight: .semibold, design: .rounded))
            Capsule(style: .continuous)
                .fill(Color.black.opacity(0.08))
                .overlay(
                    Capsule(style: .continuous)
                        .fill(LinearGradient(colors: [Color.green, Color.mint], startPoint: .leading, endPoint: .trailing))
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.trailing, max(0, 1 - CGFloat(pct) / 100.0) * 0)
            )
            .frame(height: 10)
        }
    }

}

private struct ParserWizardSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var backfillDaysText: String
    @Binding var includeProcessed: Bool
    @Binding var status: String
    @Binding var logText: String
    @Binding var rows: [SettingsBackfillRow]

    var body: some View {
        SettingsSheetShell(title: "Parser Wizard", subtitle: "Manual backfill parse") {
            VStack(alignment: .leading, spacing: 12) {
                Text("Re-scan previous emails and insert missing transactions.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)

                HStack(spacing: 10) {
                    Text("Lookback days")
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                    TextField("7", text: $backfillDaysText)
                        .keyboardType(.numberPad)
                        .multilineTextAlignment(.center)
                        .frame(width: 56, height: 26)
                        .background(Color.black.opacity(0.08), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                    Spacer()
                    Button {
                        Task { await runBackfill() }
                    } label: {
                        settingsSheetSecondaryButton("Run")
                    }
                    .buttonStyle(.plain)
                }

                Toggle("Include already processed", isOn: $includeProcessed)
                    .tint(.black)
                    .font(.system(size: 13, weight: .semibold, design: .rounded))

                if !status.isEmpty {
                    Text(status)
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }

                if !logText.isEmpty {
                    Text(logText)
                        .font(.system(size: 11, weight: .regular, design: .monospaced))
                        .lineLimit(14)
                        .textSelection(.enabled)
                        .padding(10)
                        .background(Color.black.opacity(0.04), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                }

                if !rows.isEmpty {
                    VStack(spacing: 8) {
                        ForEach(rows) { row in
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Text(row.title)
                                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                                    Spacer()
                                    Text(row.statusText)
                                        .font(.system(size: 11, weight: .medium, design: .rounded))
                                        .foregroundStyle(.secondary)
                                }
                                Text(row.subject)
                                    .font(.system(size: 11, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                                if let preview = row.preview {
                                    Text(preview)
                                        .font(.system(size: 11, weight: .regular, design: .monospaced))
                                        .lineLimit(4)
                                }
                            }
                            .padding(12)
                            .background(Color.black.opacity(0.04), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        }
                    }
                }

                Button { dismiss() } label: { settingsSheetSecondaryButton("Close") }
                    .buttonStyle(.plain)
            }
        }
        .presentationDetents([.medium, .large])
    }

    private func runBackfill() async {
        let days = max(1, min(99, Int(backfillDaysText.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 7))
        status = "Starting parser backfill..."
        logText = ""
        rows = []
        do {
            let startOut = try await SettingsAPI.fetch("/settings/email-parser/run/start", method: "POST", jsonBody: [
                "days": days,
                "include_processed": includeProcessed,
                "max_emails": 5000,
            ], as: SettingsBackfillStartPayload.self)
            guard let jobID = startOut.jobID else { throw NSError(domain: "backfill", code: 0) }
            while true {
                try await Task.sleep(nanoseconds: 900_000_000)
                let poll = try await SettingsAPI.fetch("/settings/email-parser/run/status?job_id=\(jobID)", as: SettingsBackfillStatusPayload.self)
                if poll.status == "done" {
                    let result = poll.result
                    status = "Backfill complete."
                    logText = formatBackfillLog(result)
                    rows = formatBackfillRows(result)
                    break
                } else if poll.status == "failed" {
                    status = "Backfill failed."
                    break
                } else {
                    status = "Running parser backfill..."
                }
            }
        } catch {
            status = "Backfill failed."
        }
    }

    private func formatBackfillLog(_ out: SettingsBackfillResultPayload?) -> String {
        guard let out else { return "" }
        let summary = out.summary
        let head = [
            "lookback_days=\(summary?.lookbackDays ?? 0)",
            "fetched=\(summary?.fetched ?? 0)",
            "matched=\(summary?.matched ?? 0)",
            "inserted=\(summary?.inserted ?? 0)",
            "notified=\(summary?.notified ?? 0)",
            "skipped=\(summary?.skipped ?? 0)",
        ].joined(separator: " | ")
        return head
    }

    private func formatBackfillRows(_ out: SettingsBackfillResultPayload?) -> [SettingsBackfillRow] {
        guard let rowsOut = out?.rows else { return [] }
        return rowsOut.enumerated().map { index, item in
            SettingsBackfillRow(
                id: "\(index)-\(item.subject ?? "")",
                title: (item.matched ?? false) ? "MATCH" : "SKIP",
                statusText: "inserted=\(item.inserted == true) notified=\(item.notified == true)",
                subject: item.subject ?? "(no subject)",
                preview: item.bodyExcerpt ?? ""
            )
        }
    }
}

private struct ExternalAppsSheet: View {
    @Environment(\.dismiss) private var dismiss
    let onOpenIosWidgets: () -> Void
    let onOpenAndroidWidgets: () -> Void

    var body: some View {
        SettingsSheetShell(title: "External Apps", subtitle: "Required mobile apps and downloads") {
            VStack(alignment: .leading, spacing: 12) {
                Text("Install the companion apps used for widgets and push alerts.")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                Button { onOpenIosWidgets() } label: { settingsSheetPrimaryButton("iOS Widgets") }
                    .buttonStyle(.plain)
                Button { onOpenAndroidWidgets() } label: { settingsSheetPrimaryButton("Android Widgets") }
                    .buttonStyle(.plain)
                Button {
                    if let url = URL(string: AppConfig.url(path: "/settings/external-apps/kwgt-template").absoluteString) {
                        UIApplication.shared.open(url)
                    }
                } label: {
                    settingsSheetSecondaryButton("Download KWGT Template")
                }
                .buttonStyle(.plain)
                Button { dismiss() } label: { settingsSheetSecondaryButton("Close") }
                    .buttonStyle(.plain)
            }
        }
        .presentationDetents([.medium])
    }
}

private struct IncomeWizardSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var weekdayPoints: String = "1"
    @State private var weekendPoints: String = "2"
    @State private var keywordsText: String = ""
    @State private var statusText: String = ""

    var body: some View {
        SettingsSheetShell(title: "Income Wizard", subtitle: "Paycheck matching and daily spending weights") {
            VStack(alignment: .leading, spacing: 12) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Daily spending weights")
                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                    HStack(spacing: 10) {
                        labelField(title: "Weekday", text: $weekdayPoints)
                        labelField(title: "Weekend", text: $weekendPoints)
                    }
                    Button {
                        Task { await saveDailyWeights() }
                    } label: {
                        settingsSheetPrimaryButton("Save Weights")
                    }
                    .buttonStyle(.plain)
                }

                Divider().opacity(0.18)

                VStack(alignment: .leading, spacing: 8) {
                    Text("Paycheck matching")
                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                    TextEditor(text: $keywordsText)
                        .frame(minHeight: 120)
                        .padding(8)
                        .background(Color.black.opacity(0.04), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    Button {
                        Task { await savePaycheckMatchers() }
                    } label: {
                        settingsSheetSecondaryButton("Save Keywords")
                    }
                    .buttonStyle(.plain)
                }

                if !statusText.isEmpty {
                    Text(statusText)
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }

                Button { dismiss() } label: { settingsSheetSecondaryButton("Close") }
                    .buttonStyle(.plain)
            }
        }
        .task { await load() }
        .presentationDetents([.medium, .large])
    }

    private func load() async {
        do {
            let weights = try await SettingsAPI.fetch("/settings/daily-weights", as: SettingsDailyWeightsPayload.self)
            weekdayPoints = String(Int(max(1, round(weights.weekdayPoints ?? 1))))
            weekendPoints = String(Int(max(1, round(weights.weekendPoints ?? 2))))
        } catch { }

        do {
            let out = try await SettingsAPI.fetch("/settings/paycheck-matchers", as: SettingsPaycheckMatchersPayload.self)
            keywordsText = out.keywords.joined(separator: "\n")
        } catch {
            keywordsText = "dfas\npayroll\nsalary\ndirect deposit\nmil pay"
        }
    }

    private func saveDailyWeights() async {
        let weekday = max(1, min(10, Int(weekdayPoints) ?? 1))
        let weekend = max(1, min(10, Int(weekendPoints) ?? 2))
        do {
            _ = try await SettingsAPI.fetch("/settings/daily-weights", method: "POST", jsonBody: [
                "weekday_points": weekday,
                "weekend_points": weekend,
            ], as: SettingsDailyWeightsPayload.self)
            statusText = "Daily weights saved."
        } catch {
            statusText = "Failed to save daily weights."
        }
    }

    private func savePaycheckMatchers() async {
        let keywords = keywordsText
            .split(whereSeparator: \.isNewline)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        do {
            _ = try await SettingsAPI.fetch("/settings/paycheck-matchers", method: "POST", jsonBody: ["keywords": keywords], as: SettingsPaycheckMatchersPayload.self)
            statusText = "Paycheck matchers saved."
        } catch {
            statusText = "Failed to save paycheck matchers."
        }
    }

    private func labelField(title: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
            TextField(title, text: text)
                .keyboardType(.numberPad)
                .frame(maxWidth: .infinity)
                .padding(.horizontal, 10)
                .padding(.vertical, 10)
                .background(Color.black.opacity(0.04), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
    }
}

private struct AdminConsoleSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var nonAdminPreview: Bool
    @Binding var viewModeText: String
    let onOpenIosWidgets: () -> Void
    let onOpenAndroidWidgets: () -> Void

    var body: some View {
        SettingsSheetShell(title: "Admin", subtitle: "Owner tools and widget links") {
            VStack(alignment: .leading, spacing: 12) {
                Text(viewModeText)
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                Button {
                    nonAdminPreview.toggle()
                    viewModeText = nonAdminPreview ? "Previewing as non-admin." : "Admin view."
                } label: {
                    settingsSheetSecondaryButton(nonAdminPreview ? "Return to Admin View" : "Preview as Non-Admin")
                }
                .buttonStyle(.plain)
                Button { onOpenIosWidgets() } label: { settingsSheetPrimaryButton("iOS Widgets") }
                    .buttonStyle(.plain)
                Button { onOpenAndroidWidgets() } label: { settingsSheetPrimaryButton("Android Widgets") }
                    .buttonStyle(.plain)
                Button { dismiss() } label: { settingsSheetSecondaryButton("Close") }
                    .buttonStyle(.plain)
            }
        }
        .presentationDetents([.medium])
    }
}

private struct SettingsBackfillRow: Identifiable {
    let id: String
    let title: String
    let statusText: String
    let subject: String
    let preview: String?
}

private struct SettingsUnreadCountPayload: Decodable {
    let unread: Int
}

private struct SettingsWidgetScriptPayload: Decodable {
    let ok: Bool?
    let widgetVersion: Int?
    let script: String

    enum CodingKeys: String, CodingKey {
        case ok
        case widgetVersion = "widget_version"
        case script
    }
}

private struct SettingsWidgetTokenPayload: Decodable {
    let ok: Bool?
    let widgetToken: String
    let tenantID: Int?
    let widgetVersion: Int?

    enum CodingKeys: String, CodingKey {
        case ok
        case widgetToken = "widget_token"
        case tenantID = "tenant_id"
        case widgetVersion = "widget_version"
    }
}

private struct SettingsPaycheckMatchersPayload: Decodable {
    let keywords: [String]
}

private struct SettingsBackfillStartPayload: Decodable {
    let ok: Bool?
    let jobID: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case jobID = "job_id"
    }
}

private struct SettingsBackfillStatusPayload: Decodable {
    let ok: Bool?
    let jobID: String?
    let status: String
    let result: SettingsBackfillResultPayload?

    enum CodingKeys: String, CodingKey {
        case ok
        case jobID = "job_id"
        case status
        case result
    }
}

private struct SettingsBackfillResultPayload: Decodable {
    let ok: Bool?
    let summary: SettingsBackfillSummaryPayload?
    let rows: [SettingsBackfillResultRowPayload]?
}

private struct SettingsBackfillSummaryPayload: Decodable {
    let lookbackDays: Int?
    let fetched: Int?
    let matched: Int?
    let inserted: Int?
    let notified: Int?
    let skipped: Int?

    enum CodingKeys: String, CodingKey {
        case lookbackDays = "lookback_days"
        case fetched
        case matched
        case inserted
        case notified
        case skipped
    }
}

private struct SettingsBackfillResultRowPayload: Decodable {
    let matched: Bool?
    let inserted: Bool?
    let notified: Bool?
    let subject: String?
    let sender: String?
    let bodyExcerpt: String?

    enum CodingKeys: String, CodingKey {
        case matched
        case inserted
        case notified
        case subject
        case sender
        case bodyExcerpt = "body_excerpt"
    }
}

private enum SettingsAPI {
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
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw NSError(domain: "QuailCashSettings", code: (response as? HTTPURLResponse)?.statusCode ?? -1)
        }
        let decoder = JSONDecoder()
        return try decoder.decode(T.self, from: data)
    }
}

private func settingsSheetPrimaryButton(_ title: String) -> some View {
    Text(title)
        .font(.system(size: 13, weight: .semibold, design: .rounded))
        .frame(maxWidth: .infinity, minHeight: 48)
        .foregroundStyle(.white)
        .background(Color.black, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
}

private func settingsSheetSecondaryButton(_ title: String) -> some View {
    Text(title)
        .font(.system(size: 13, weight: .semibold, design: .rounded))
        .frame(maxWidth: .infinity, minHeight: 44)
        .foregroundStyle(.primary)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(.black.opacity(0.10), lineWidth: 1))
}

private func copyToClipboard(_ text: String) {
    UIPasteboard.general.string = text
}
