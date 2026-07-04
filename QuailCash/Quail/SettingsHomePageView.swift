import SwiftUI
import UIKit
import Combine

private func settingsThemePalette() -> QuailThemePalette {
    QuailTheme.palette(for: UserDefaults.standard.string(forKey: "quail.settings.theme") ?? "system")
}

struct SettingsHomePageView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var navigator: AppNavigator
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @AppStorage("quail.home.layout.customized") private var homeLayoutCustomized: Bool = false

    @StateObject private var model = SettingsHomeViewModel()
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
    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        AppChromeFrame(
            title: "Settings",
            badgeValue: nil,
            selectedTab: navigator.currentTab,
            showsBottomBar: true,
            onLeadingTap: { navigator.popToRoot() },
            onTrailingTap: { navigator.show(.notifications) },
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
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {

                    // MARK: Appearance
                    settingsSection(title: "Appearance") {
                        HStack(spacing: 14) {
                            settingsIconBadge("paintbrush.fill", color: palette.accent)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Color scheme")
                                    .font(.system(size: 14, weight: .bold, design: .rounded))
                                Text("Controls the app's visual theme")
                                    .font(.system(size: 12, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Picker("", selection: $themeSelection) {
                                ForEach(themes, id: \.0) { Text($1).tag($0) }
                            }
                            .pickerStyle(.menu)
                            .tint(palette.accent)
                        }
                        .padding(.horizontal, 14).padding(.vertical, 12)
                    }

                    // MARK: Notifications
                    settingsSection(title: "Notifications") {
                        settingsRow(icon: "bell.badge.fill", color: .red,
                            title: "Smart Notifications",
                            subtitle: "Spending power, overspending alerts, and savings nudges"
                        ) { navigator.show(.notificationSettings) }
                    }

                    // MARK: Home
                    settingsSection(title: "Home") {
                        settingsRow(icon: "square.grid.2x2.fill", color: palette.accent,
                            title: "Customize Layout",
                            subtitle: "Rearrange and show/hide cards on the home screen"
                        ) { activeSheet = .homeLayout }

                        Divider().padding(.leading, 60)

                        settingsRow(icon: "arrow.clockwise", color: .orange,
                            title: "Refresh Cache",
                            subtitle: model.isRefreshingCache ? "Refreshing…" : model.cacheVersionsText
                        ) { Task { await model.refreshCache() } }
                    }

                    // MARK: Widgets
                    settingsSection(title: "Widgets") {
                        settingsRow(icon: "apps.iphone", color: .purple,
                            title: "iOS Widget Setup",
                            subtitle: "Configure home screen widget workflows"
                        ) { activeSheet = .widgetSetup(.ios) }
                    }

                    // MARK: Initial Setup
                    settingsSection(title: "Initial Setup") {
                        // Progress bar
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text(model.setupProgressText)
                                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                                Spacer()
                                Text("\(model.setupProgressPercent)%")
                                    .font(.system(size: 13, weight: .bold, design: .rounded))
                                    .foregroundStyle(model.setupProgressPercent == 100 ? .green : palette.accent)
                            }
                            GeometryReader { geo in
                                ZStack(alignment: .leading) {
                                    Capsule().fill(palette.border).frame(height: 8)
                                    Capsule()
                                        .fill(LinearGradient(colors: [.green, .mint], startPoint: .leading, endPoint: .trailing))
                                        .frame(width: geo.size.width * CGFloat(min(100, model.setupProgressPercent)) / 100, height: 8)
                                }
                            }.frame(height: 8)
                            if !model.setupProgressSubtext.isEmpty {
                                Text(model.setupProgressSubtext)
                                    .font(.system(size: 11, design: .rounded)).foregroundStyle(.secondary)
                            }
                        }
                        .padding(.horizontal, 14).padding(.top, 14).padding(.bottom, 6)

                        Divider()

                        settingsRow(icon: "wand.and.stars", color: .indigo,
                            title: "Setup Wizard",
                            subtitle: "Walk through the initial budget and account configuration"
                        ) { navigator.show(.setupWizard) }

                        Divider().padding(.leading, 60)

                        settingsRow(icon: "envelope.badge.fill", color: .teal,
                            title: "Email Parser Wizard",
                            subtitle: "Create and maintain live email parser rules"
                        ) { navigator.show(.parserWizard) }

                        Divider().padding(.leading, 60)

                        settingsRow(icon: "tray.and.arrow.down.fill", color: .green,
                            title: "Import Queue",
                            subtitle: "Review Shortcut-driven CSV imports awaiting processing"
                        ) { navigator.show(.importQueue) }

                        Divider().padding(.leading, 60)

                        settingsRow(icon: "dollarsign.circle.fill", color: .mint,
                            title: "Income Wizard",
                            subtitle: "Set up LES, salary, or hourly income settings"
                        ) { navigator.show(.incomeWizard) }

                        Divider().padding(.leading, 60)

                        settingsRow(icon: "apps.iphone.badge.plus", color: .gray,
                            title: "External Apps",
                            subtitle: "Install required apps for widgets and push notifications"
                        ) { activeSheet = .externalApps }

                        Divider().padding(.leading, 60)

                        // Backfill — kept inline, collapsed into a row that expands
                        backfillPanel.padding(.horizontal, 14).padding(.vertical, 10)
                    }

                    // MARK: Rules
                    settingsSection(title: "Rules") {
                        settingsRow(icon: "text.badge.checkmark", color: .cyan,
                            title: "Category Rules",
                            subtitle: "View matches, test regex, re-apply, disable, or delete rules"
                        ) { navigator.show(.ruleBuilder) }
                    }

                    // MARK: Admin
                    settingsSection(title: "Admin") {
                        settingsRow(
                            icon: model.nonAdminPreview ? "eye.slash.fill" : "eye.fill",
                            color: .secondary,
                            title: model.nonAdminPreview ? "Return to Admin View" : "Preview as Non-Admin",
                            subtitle: model.viewModeText
                        ) {
                            model.nonAdminPreview.toggle()
                            model.viewModeText = model.nonAdminPreview ? "Previewing as non-admin" : "Admin view"
                        }

                        if !model.nonAdminPreview {
                            Divider().padding(.leading, 60)
                            settingsRow(icon: "shield.lefthalf.filled", color: .red,
                                title: "Owner Admin Console",
                                subtitle: "Tenant management, user approvals, and data purge"
                            ) { activeSheet = .adminConsole }

                            Divider().padding(.leading, 60)
                            settingsRow(icon: "apps.iphone", color: .purple,
                                title: "Widget Setup Links",
                                subtitle: "Open platform-specific widget setup pages directly"
                            ) { activeSheet = .widgetSetup(.ios) }
                        }
                    }
                }
                .padding(.horizontal, 14)
                .padding(.top, 12)
                .padding(.bottom, 24)
            }
        }
        .task { await model.load() }
        .sheet(item: $activeSheet) { sheet in
            switch sheet {
            case .homeLayout:
                HomeLayoutSheet(homeLayoutCustomized: $homeLayoutCustomized)
            case .widgetSetup(let platform):
                WidgetSetupSheet(platform: platform)
            case .initialSetup:
                InitialSetupSheet(
                    onConnectGoogle: { },
                    onOpenNotifications: { navigator.show(.notifications) },
                    onOpenBankInfo: { navigator.show(.bankInfo) },
                    onOpenCsvImport: { navigator.show(.csvImport) },
                    onOpenIncomeWizard: { navigator.show(.incomeWizard) },
                    onOpenParserWizard: { navigator.show(.parserWizard) },
                    onOpenExternalApps: { activeSheet = .externalApps }
                )
            case .parserWizard:
                ParserWizardSheet()
            case .externalApps:
                ExternalAppsSheet(
                    onOpenIosWidgets: { activeSheet = .widgetSetup(.ios) },
                    onOpenAndroidWidgets: { activeSheet = .widgetSetup(.android) }
                )
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
            Text(title)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .padding(.leading, 4)
            VStack(alignment: .leading, spacing: 0) {
                content()
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }

    @ViewBuilder
    private func settingsRow(icon: String, color: Color, title: String, subtitle: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 14) {
                settingsIconBadge(icon, color: color)
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
            .padding(.horizontal, 14).padding(.vertical, 12)
        }
        .buttonStyle(.plain)
    }

    private func settingsIconBadge(_ icon: String, color: Color) -> some View {
        ZStack {
            RoundedRectangle(cornerRadius: 9, style: .continuous)
                .fill(color.opacity(0.18))
                .frame(width: 36, height: 36)
            Image(systemName: icon)
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(color)
        }
    }

    private func settingsMuted(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 12, weight: .medium, design: .rounded))
            .foregroundStyle(.secondary)
    }

    private func settingsSplitRow(
        title: String,
        subtitle: String,
        primaryAction: (() -> Void)? = nil,
        primaryDestination: AppRoute? = nil,
        primaryLabel: String
    ) -> some View {
        settingsSplitRow(
            title: title,
            subtitle: subtitle,
            primaryAction: primaryAction,
            primaryDestination: primaryDestination,
            primaryLabel: primaryLabel,
            primaryDisabled: false
        )
    }

    private func settingsSplitRow(
        title: String,
        subtitle: String,
        primaryAction: (() -> Void)? = nil,
        primaryDestination: AppRoute? = nil,
        primaryLabel: String,
        primaryDisabled: Bool
    ) -> some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                settingsMuted(subtitle)
            }
            Spacer(minLength: 12)
            if let destination = primaryDestination {
                NavigationLink(value: destination) {
                    settingsPrimaryButton(primaryLabel, width: settingsActionButtonWidth)
                }
                .buttonStyle(.plain)
            } else if let primaryAction {
                Button(action: primaryAction) {
                    settingsPrimaryButton(primaryLabel, width: settingsActionButtonWidth)
                }
                .buttonStyle(.plain)
                .disabled(primaryDisabled)
            }
        }
        .padding(.vertical, 12)
    }

    private func settingsPrimaryButton(_ title: String, width: CGFloat? = nil) -> some View {
        Text(title)
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .lineLimit(1)
            .minimumScaleFactor(0.78)
            .frame(width: width ?? settingsActionButtonWidth, height: settingsActionButtonHeight)
            .foregroundStyle(palette.primaryButtonText)
            .background(palette.primaryButton, in: Capsule(style: .continuous))
    }

    private func settingsSecondaryButton(_ title: String, width: CGFloat? = nil) -> some View {
        Text(title)
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .lineLimit(1)
            .minimumScaleFactor(0.78)
            .frame(width: width ?? settingsActionButtonWidth, height: settingsActionButtonHeight)
            .foregroundStyle(palette.secondaryButtonText)
            .background(palette.secondaryButton, in: Capsule(style: .continuous))
            .overlay(Capsule(style: .continuous).stroke(palette.border, lineWidth: 1))
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

struct InitialSetupPageView: View {
    @EnvironmentObject private var navigator: AppNavigator

    var body: some View {
        PageShell(title: "Setup Wizard", subtitle: "Complete this once per tenant workspace.") {
            InitialSetupContentView(
                showCloseButton: false,
                onConnectGoogle: { navigator.show(.settings) },
                onOpenNotifications: { navigator.show(.notifications) },
                onOpenBankInfo: { navigator.show(.bankInfo) },
                onOpenCsvImport: { navigator.show(.csvImport) },
                onOpenIncomeWizard: { navigator.show(.incomeWizard) },
                onOpenParserWizard: { navigator.show(.parserWizard) },
                onOpenExternalApps: { navigator.show(.settings) }
            )
        }
    }
}

struct ParserWizardPageView: View {
    var body: some View {
        PageShell(title: "Parser Wizard", subtitle: "Manual backfill parse") {
            ParserWizardContentView(showCloseButton: false)
        }
    }
}

struct IncomeWizardPageView: View {
    var body: some View {
        PageShell(title: "Income Wizard", subtitle: "LES profile, paycheck matching, and daily weights") {
            IncomeWizardContentView(showCloseButton: false)
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
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    let title: String
    let subtitle: String
    let content: Content

    init(title: String, subtitle: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.subtitle = subtitle
        self.content = content()
    }

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
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
                colors: [palette.backgroundTop, palette.backgroundBottom],
                startPoint: .top,
                endPoint: .bottom
            )
            .ignoresSafeArea()
        )
    }
}

private struct NotificationSettingsSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
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
        let palette = QuailTheme.palette(for: themeSelection)
        return content()
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
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
        if key == "ios_push" && value {
            let granted = await pushManager.requestAuthorizationAndRegister()
            if !granted {
                prefs[key] = false
                iosPushStatus = "Push permission is off in iPhone Settings."
                statusMessage = "Enable notifications for Quail in iPhone Settings."
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
            try await QuailAPI.shared.sendIOSTestPush()
            statusMessage = "Test push sent."
        } catch {
            statusMessage = error.localizedDescription.isEmpty ? "Failed to send test push." : error.localizedDescription
        }
    }
}

private struct WidgetSetupSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @Environment(\.dismiss) private var dismiss
    let platform: WidgetPlatform
    @State private var statusText = "Loading..."
    @State private var widgetToken = ""
    @State private var widgetURL = ""
    @State private var widgetVersionText = ""

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        SettingsSheetShell(title: platform == .ios ? "iOS Widgets" : "Android Widgets",
                   subtitle: platform == .ios ? "Native home screen and lock screen widget setup" : "KWGT setup and widget URL") {
            VStack(alignment: .leading, spacing: 12) {
                Text(statusText)
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)

                if platform == .ios {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("The native widget uses a widget token instead of Scriptable.")
                            .font(.system(size: 13, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                        Text("1. Generate and copy a widget token.")
                        Text("2. Add the Quail widget to the Home Screen or Lock Screen.")
                        Text("3. Long-press the widget, choose Edit Widget, then paste the token into Widget Token.")
                    }
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)

                    Button {
                        Task { await loadWidgetTokenOnly(copyToClipboardAfterLoad: true) }
                    } label: {
                        settingsSheetPrimaryButton("Generate + Copy Token")
                    }
                    .buttonStyle(.plain)

                    if !widgetToken.isEmpty {
                        Text(widgetToken)
                            .font(.system(size: 11, weight: .regular, design: .monospaced))
                            .textSelection(.enabled)
                            .padding(10)
                            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    }

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
                            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
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
            }
        }
        .task { await load() }
        .presentationDetents([.medium, .large])
    }

    private func load() async {
        switch platform {
        case .ios:
            await loadWidgetTokenOnly(copyToClipboardAfterLoad: false)
        case .android:
            await loadWidgetTokenAndURLOnly()
        }
    }

    private func loadWidgetTokenOnly(copyToClipboardAfterLoad: Bool) async {
        statusText = "Generating widget token..."
        do {
            let out = try await SettingsAPI.fetch("/settings/widget-token", method: "POST", as: SettingsWidgetTokenPayload.self)
            widgetToken = out.widgetToken
            widgetVersionText = "Widget version \(out.widgetVersion ?? 0)"
            statusText = "Widget token ready."
            if copyToClipboardAfterLoad {
                copyToClipboard(out.widgetToken)
            }
        } catch {
            statusText = "Failed to generate widget token."
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
    let onConnectGoogle: () -> Void
    let onOpenNotifications: () -> Void
    let onOpenBankInfo: () -> Void
    let onOpenCsvImport: () -> Void
    let onOpenIncomeWizard: () -> Void
    let onOpenParserWizard: () -> Void
    let onOpenExternalApps: () -> Void

    var body: some View {
        SettingsSheetShell(title: "Workspace Setup Wizard", subtitle: "Complete this once per tenant workspace.") {
            InitialSetupContentView(
                showCloseButton: true,
                onConnectGoogle: onConnectGoogle,
                onOpenNotifications: onOpenNotifications,
                onOpenBankInfo: onOpenBankInfo,
                onOpenCsvImport: onOpenCsvImport,
                onOpenIncomeWizard: onOpenIncomeWizard,
                onOpenParserWizard: onOpenParserWizard,
                onOpenExternalApps: onOpenExternalApps
            )
        }
        .presentationDetents([.medium, .large])
    }
}

private struct InitialSetupContentView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @Environment(\.dismiss) private var dismiss
    let showCloseButton: Bool
    let onConnectGoogle: () -> Void
    let onOpenNotifications: () -> Void
    let onOpenBankInfo: () -> Void
    let onOpenCsvImport: () -> Void
    let onOpenIncomeWizard: () -> Void
    let onOpenParserWizard: () -> Void
    let onOpenExternalApps: () -> Void

    @State private var onboarding: SettingsOnboardingStatusPayload?
    @State private var statusText = "Loading..."
    @State private var addResultText = ""
    @State private var pushoverUserKey = ""
    @State private var pushoverStatusText = ""
    @State private var editingAccountID: Int?
    @State private var institution = ""
    @State private var accountName = ""
    @State private var accountType = "checking"
    @State private var startingDateISO = isoDateString(Date())
    @State private var startingBalanceText = ""
    @State private var creditLimitText = ""
    @State private var apyPercentText = ""
    @State private var interestPostDayText = ""
    @State private var receivesEmails = true
    @State private var isPaycheckAccount = false
    @State private var benefitRows: [SettingsBenefitDraft] = [SettingsBenefitDraft()]

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            setupHeaderCard
            existingAccountsCard
            stepOneAccountCard
            stepTwoImportCard
            stepThreeNotificationsCard
            stepFourParserCard

            if showCloseButton {
                Button { dismiss() } label: { settingsSheetSecondaryButton("Close") }
                    .buttonStyle(.plain)
            }
        }
        .task { await load() }
    }

    private func load() async {
        do {
            onboarding = try await SettingsAPI.fetch("/onboarding/status", as: SettingsOnboardingStatusPayload.self)
            let notificationPayload = try? await SettingsAPI.fetch("/settings/notifications", as: SettingsNotificationSettingsPayload.self)
            pushoverUserKey = notificationPayload?.pushoverUserKey ?? ""
            statusText = ""
            resetFormIfNeeded()
        } catch {
            statusText = "Could not load setup completion status."
        }
    }

    private var setupHeaderCard: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        return VStack(alignment: .leading, spacing: 12) {
            if let onboarding {
                Text(progressSummary)
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 999, style: .continuous)
                            .fill(palette.elevatedSurface)
                        RoundedRectangle(cornerRadius: 999, style: .continuous)
                            .fill(LinearGradient(colors: [palette.positive, palette.accent], startPoint: .leading, endPoint: .trailing))
                            .frame(width: geo.size.width * CGFloat(progressPercent) / 100.0)
                    }
                }
                .frame(height: 10)

                if let counts = onboarding.counts {
                    Text("Accounts: \(counts.accounts) | Starting Balances: \(counts.startingBalances) | Transactions: \(counts.transactions)")
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            } else {
                Text(statusText)
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }

            Button {
                Task { await load() }
            } label: {
                settingsSheetSecondaryButton("Refresh Status")
            }
            .buttonStyle(.plain)
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private var existingAccountsCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            DisclosureGroup {
                if let accounts = onboarding?.accounts, !accounts.isEmpty {
                    VStack(spacing: 10) {
                        ForEach(accounts) { account in
                            VStack(alignment: .leading, spacing: 6) {
                                HStack(alignment: .top, spacing: 10) {
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text("\(account.institution) - \(account.name)")
                                            .font(.system(size: 13, weight: .bold, design: .rounded))
                                        Text("(\(account.accountType))")
                                            .font(.system(size: 11, weight: .medium, design: .rounded))
                                            .foregroundStyle(.secondary)
                                        if let setup = account.setup {
                                            Text(setup.complete ? "Complete" : "Missing: \(setup.missing.joined(separator: ", "))")
                                                .font(.system(size: 11, weight: .medium, design: .rounded))
                                                .foregroundStyle(.secondary)
                                        }
                                        Text("Receives emails: \(account.receivesEmails ? "Yes" : "No") | Paycheck account: \(account.isPaycheckAccount ? "Yes" : "No")")
                                            .font(.system(size: 11, weight: .medium, design: .rounded))
                                            .foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    Button("Edit") { startEdit(account) }
                                        .buttonStyle(.plain)
                                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                                        .padding(.horizontal, 12)
                                        .padding(.vertical, 8)
                                        .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                                        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.10), lineWidth: 1))
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(12)
                            .background(Color.black.opacity(0.03), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        }
                    }
                    .padding(.top, 8)
                } else {
                    Text("No accounts yet.")
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                        .padding(.top, 8)
                }
            } label: {
                HStack {
                    Text("Existing accounts")
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                    Spacer()
                    Text("\(onboarding?.accounts.count ?? 0)")
                        .font(.system(size: 11, weight: .bold, design: .rounded))
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.black.opacity(0.08), in: Capsule(style: .continuous))
                }
            }
        }
        .padding(14)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
    }

    private var stepOneAccountCard: some View {
        setupStepCard(title: "Step 1: Add Account") {
            VStack(alignment: .leading, spacing: 10) {
                settingsTextField("Institution (e.g. Navy Federal)", text: $institution)
                settingsTextField("Account Name (e.g. Active Duty Checking)", text: $accountName)

                Picker("Account Type", selection: $accountType) {
                    Text("checking").tag("checking")
                    Text("savings").tag("savings")
                    Text("credit").tag("credit")
                    Text("investment").tag("investment")
                }
                .pickerStyle(.menu)
                .tint(.black)
                .padding(.horizontal, 10)
                .frame(height: 44)
                .background(Color.black.opacity(0.04), in: RoundedRectangle(cornerRadius: 12, style: .continuous))

                if onboarding?.canSetStartingBalance == true {
                    HStack(spacing: 8) {
                        DatePicker("", selection: Binding(get: {
                            isoDateStringToDate(startingDateISO)
                        }, set: { startingDateISO = isoDateString($0) }), displayedComponents: .date)
                            .labelsHidden()
                            .frame(maxWidth: .infinity)
                            .padding(.horizontal, 10)
                            .frame(height: 44)
                            .background(Color.black.opacity(0.04), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        settingsTextField("Starting Balance", text: $startingBalanceText, keyboard: .decimalPad)
                    }
                }

                if accountType == "credit" {
                    settingsTextField("Credit Limit", text: $creditLimitText, keyboard: .decimalPad)
                }

                if accountType == "checking" || accountType == "savings" || accountType == "investment" {
                    HStack(spacing: 8) {
                        settingsTextField("APY %", text: $apyPercentText, keyboard: .decimalPad)
                        settingsTextField("Interest Post Day", text: $interestPostDayText, keyboard: .numberPad)
                    }
                }

                Toggle("Receives email transaction alerts", isOn: $receivesEmails)
                    .tint(.black)
                    .font(.system(size: 13, weight: .semibold, design: .rounded))

                Toggle("Paycheck deposit account", isOn: $isPaycheckAccount)
                    .tint(.black)
                    .font(.system(size: 13, weight: .semibold, design: .rounded))

                if accountType == "credit" {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Credit Card Benefits (optional)")
                            .font(.system(size: 12, weight: .semibold, design: .rounded))
                            .foregroundStyle(.secondary)
                        ForEach($benefitRows) { $row in
                            HStack(spacing: 8) {
                                settingsTextField("Category", text: $row.category)
                                settingsTextField("Cashback %", text: $row.percentText, keyboard: .decimalPad)
                                Button {
                                    if benefitRows.count > 1 {
                                        benefitRows.removeAll { $0.id == row.id }
                                    } else {
                                        row = SettingsBenefitDraft()
                                    }
                                } label: {
                                    Text("Remove")
                                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                                        .frame(width: 72, height: 44)
                                        .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                                        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.10), lineWidth: 1))
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        Button {
                            benefitRows.append(SettingsBenefitDraft())
                        } label: {
                            settingsSheetSecondaryButton("Add Benefit Row")
                        }
                        .buttonStyle(.plain)
                    }
                }

                Button(editingAccountID == nil ? "Add Account" : "Save Account Changes") {
                    Task { await saveAccount() }
                }
                .buttonStyle(.plain)
                .modifier(SettingsPrimaryActionModifier())

                if editingAccountID != nil {
                    Button("Cancel Edit") {
                        resetForm()
                        addResultText = "Edit cancelled."
                    }
                    .buttonStyle(.plain)
                    .modifier(SettingsSecondaryActionModifier())

                    Button("Delete Account + Transactions") {
                        Task { await deleteEditingAccount() }
                    }
                    .buttonStyle(.plain)
                    .modifier(SettingsSecondaryActionModifier())
                }

                if !addResultText.isEmpty {
                    Text(addResultText)
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private var stepTwoImportCard: some View {
        setupStepCard(title: "Step 2: Import CSV Data") {
            VStack(alignment: .leading, spacing: 10) {
                Text("Drop a CSV or Excel file, preview it, map columns, then import.")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)

                Button("Open Importer") { onOpenCsvImport() }
                    .buttonStyle(.plain)
                    .modifier(SettingsPrimaryActionModifier())

                Button("Open Bank Info") { onOpenBankInfo() }
                    .buttonStyle(.plain)
                    .modifier(SettingsSecondaryActionModifier())

                Button("Income Wizard") { onOpenIncomeWizard() }
                    .buttonStyle(.plain)
                    .modifier(SettingsSecondaryActionModifier())
            }
        }
    }

    private var stepThreeNotificationsCard: some View {
        setupStepCard(title: "Step 3: Notifications (Optional)") {
            VStack(alignment: .leading, spacing: 10) {
                Text("Enter your personal Pushover user key. This key is saved to your user only.")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)

                settingsTextField("Pushover User Key", text: $pushoverUserKey)

                Button("Save Pushover Key") {
                    Task { await savePushoverUserKey() }
                }
                .buttonStyle(.plain)
                .modifier(SettingsPrimaryActionModifier())

                Button("Send Test Notification") {
                    Task { await sendPushoverTest() }
                }
                .buttonStyle(.plain)
                .modifier(SettingsSecondaryActionModifier())

                Button("Open Notifications Page") {
                    onOpenNotifications()
                }
                .buttonStyle(.plain)
                .modifier(SettingsSecondaryActionModifier())

                if !pushoverStatusText.isEmpty {
                    Text(pushoverStatusText)
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private var stepFourParserCard: some View {
        setupStepCard(title: "Step 4: Parser Wizard") {
            VStack(alignment: .leading, spacing: 10) {
                Text("Finish parser setup for accounts that receive email alerts.")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                Button("Open Parser Wizard") {
                    onOpenParserWizard()
                }
                .buttonStyle(.plain)
                .modifier(SettingsPrimaryActionModifier())

                Button("External Apps") {
                    onOpenExternalApps()
                }
                .buttonStyle(.plain)
                .modifier(SettingsSecondaryActionModifier())
            }
        }
    }

    private var progressPercent: Int {
        let steps = onboarding?.steps
        let flags = [
            steps?.accountsAdded == true,
            steps?.startingBalancesAdded == true,
            steps?.transactionsImported == true,
            steps?.pushoverUserKeySet == true
        ]
        let done = flags.filter { $0 }.count
        return Int(round((Double(done) / 4.0) * 100.0))
    }

    private var progressSummary: String {
        "\(progressPercent)% complete"
    }

    private func setupStepCard<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        let palette = settingsThemePalette()
        return VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .font(.system(size: 16, weight: .bold, design: .rounded))
            content()
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func settingsTextField(_ placeholder: String, text: Binding<String>, keyboard: UIKeyboardType = .default) -> some View {
        let palette = settingsThemePalette()
        return TextField(placeholder, text: text)
            .keyboardType(keyboard)
            .padding(.horizontal, 10)
            .frame(height: 44)
            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func resetFormIfNeeded() {
        if editingAccountID == nil && institution.isEmpty && accountName.isEmpty {
            resetForm()
        }
    }

    private func resetForm() {
        editingAccountID = nil
        institution = ""
        accountName = ""
        accountType = "checking"
        startingDateISO = isoDateString(Date())
        startingBalanceText = ""
        creditLimitText = ""
        apyPercentText = ""
        interestPostDayText = ""
        receivesEmails = true
        isPaycheckAccount = false
        benefitRows = [SettingsBenefitDraft()]
    }

    private func startEdit(_ account: SettingsOnboardingAccountPayload) {
        editingAccountID = account.id
        institution = account.institution
        accountName = account.name
        accountType = account.accountType
        creditLimitText = account.creditLimit.map { formatCompactDecimal($0) } ?? ""
        interestPostDayText = account.interestPostDay.map(String.init) ?? ""
        receivesEmails = account.receivesEmails
        isPaycheckAccount = account.isPaycheckAccount
        benefitRows = account.cardBenefits.isEmpty
            ? [SettingsBenefitDraft()]
            : account.cardBenefits.map { SettingsBenefitDraft(category: $0.benefitType, percentText: formatCompactDecimal($0.cashbackPercent)) }
        addResultText = "Editing account #\(account.id)."
    }

    private func saveAccount() async {
        addResultText = ""
        let body = buildAccountRequestBody()
        do {
            if let editingAccountID {
                let out = try await SettingsAPI.fetch("/onboarding/accounts/\(editingAccountID)", method: "PUT", jsonBody: body, as: SettingsOnboardingAccountMutationPayload.self)
                addResultText = "Updated account id \(out.accountID)."
            } else {
                let out = try await SettingsAPI.fetch("/onboarding/accounts", method: "POST", jsonBody: body, as: SettingsOnboardingAccountMutationPayload.self)
                addResultText = "Added account id \(out.accountID)."
            }
            resetForm()
            await load()
        } catch {
            addResultText = "Save failed: \(error.localizedDescription)"
        }
    }

    private func deleteEditingAccount() async {
        guard let editingAccountID else { return }
        do {
            let out = try await SettingsAPI.fetch("/onboarding/accounts/\(editingAccountID)", method: "DELETE", as: SettingsOnboardingAccountDeletePayload.self)
            addResultText = "Deleted account id \(out.accountID). Removed \(out.deletedTransactions) transactions."
            resetForm()
            await load()
        } catch {
            addResultText = "Delete failed: \(error.localizedDescription)"
        }
    }

    private func savePushoverUserKey() async {
        do {
            let out = try await SettingsAPI.fetch("/onboarding/pushover-key", method: "POST", jsonBody: [
                "user_key": pushoverUserKey.trimmingCharacters(in: .whitespacesAndNewlines)
            ], as: SettingsOnboardingPushoverKeyPayload.self)
            pushoverStatusText = out.userKeySet ? "Pushover user key saved." : "Pushover user key cleared."
            await load()
        } catch {
            pushoverStatusText = "Save failed: \(error.localizedDescription)"
        }
    }

    private func sendPushoverTest() async {
        do {
            _ = try await SettingsAPI.fetch("/onboarding/pushover-test", method: "POST", jsonBody: [
                "user_key": pushoverUserKey.trimmingCharacters(in: .whitespacesAndNewlines)
            ], as: SettingsOnboardingPushoverTestPayload.self)
            pushoverStatusText = "Test notification sent."
        } catch {
            pushoverStatusText = "Test failed: \(error.localizedDescription)"
        }
    }

    private func buildAccountRequestBody() -> [String: Any] {
        let benefits = accountType == "credit" ? benefitRows.compactMap { row -> [String: Any]? in
            let name = row.category.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !name.isEmpty else { return nil }
            return [
                "benefit_type": name,
                "cashback_percent": Double(row.percentText.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 0
            ]
        } : []

        var body: [String: Any] = [
            "institution": institution.trimmingCharacters(in: .whitespacesAndNewlines),
            "name": accountName.trimmingCharacters(in: .whitespacesAndNewlines),
            "accounttype": accountType,
            "receives_emails": receivesEmails,
            "is_paycheck_account": isPaycheckAccount,
            "card_benefits": benefits
        ]
        if onboarding?.canSetStartingBalance == true {
            body["starting_date"] = startingDateISO
            if let start = Double(startingBalanceText.trimmingCharacters(in: .whitespacesAndNewlines)) {
                body["starting_balance"] = start
            }
        }
        if let limit = Double(creditLimitText.trimmingCharacters(in: .whitespacesAndNewlines)) {
            body["credit_limit"] = limit
        }
        if let apy = Double(apyPercentText.trimmingCharacters(in: .whitespacesAndNewlines)) {
            body["apy_percent"] = apy
        }
        if let day = Int(interestPostDayText.trimmingCharacters(in: .whitespacesAndNewlines)) {
            body["interest_post_day"] = day
        }
        return body
    }

}

private struct ParserWizardSheet: View {
    var body: some View {
        SettingsSheetShell(title: "Parser Wizard", subtitle: "Build parser configs per account/email scope.") {
            ParserWizardContentView(showCloseButton: true)
        }
        .presentationDetents([.large])
    }
}

private struct ParserWizardContentView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @Environment(\.dismiss) private var dismiss
    let showCloseButton: Bool
    @StateObject private var model = EmailParserWizardViewModel()
    @State private var scopeExpanded = true
    @State private var samplesExpanded = true
    @State private var ruleExpanded = true
    @State private var resultsExpanded = true

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("Build parser configs per account/email scope using parser slots (Parser 1, Parser 2, Parser 3...).")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)

                if !model.statusText.isEmpty {
                    Text(model.statusText)
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                        .foregroundStyle(model.statusIsError ? palette.negative : .secondary)
                }

                parserStepCard("Step 1: Scope", isExpanded: $scopeExpanded) {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(spacing: 10) {
                            parserField("Account") {
                                Picker("Account", selection: $model.accountID) {
                                    Text("Select account").tag(0)
                                    ForEach(model.accounts) { account in
                                        Text(account.displayLabel).tag(account.id)
                                    }
                                }
                                .pickerStyle(.menu)
                            }
                            if model.accountSettings.count > 1 {
                                parserField("Subject setting") {
                                    Picker("Subject setting", selection: $model.selectedDraftID) {
                                        Text("Select parser").tag(0)
                                        ForEach(model.accountSettings) { setting in
                                            Text(setting.subjectSettingLabel).tag(setting.draftID)
                                        }
                                    }
                                    .pickerStyle(.menu)
                                    .onChange(of: model.selectedDraftID) { _, newValue in
                                        model.applySelectedDraft(id: newValue)
                                    }
                                }
                            }
                        }

                        HStack(spacing: 10) {
                            parserField("Sender contains") {
                                TextField("alerts@bank.com", text: $model.senderQuery)
                                    .textInputAutocapitalization(.never)
                                    .autocorrectionDisabled()
                            }
                            parserField("Subject contains") {
                                TextField("Transaction Alert", text: $model.subjectQuery)
                            }
                        }

                        HStack(spacing: 10) {
                            parserField("Lookback days") {
                                TextField("30", text: $model.lookbackDaysText)
                                    .keyboardType(.numberPad)
                            }
                            parserField("Max samples") {
                                TextField("10", text: $model.sampleLimitText)
                                    .keyboardType(.numberPad)
                            }
                        }

                        Toggle("Try HTML body when Merchant/Date/Amount are blank", isOn: $model.tryHTMLOnMissing)
                            .tint(palette.accent)
                            .font(.system(size: 13, weight: .semibold, design: .rounded))

                        Button {
                            Task { await model.loadSamples() }
                        } label: {
                            settingsSheetPrimaryButton(model.isLoadingSamples ? "Loading..." : "Load Samples")
                        }
                        .buttonStyle(.plain)
                        .disabled(model.isLoadingSamples)
                    }
                }

                parserStepCard("Step 2: Candidate Samples", isExpanded: $samplesExpanded) {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(model.samplesMetaText)
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                        if model.samples.isEmpty {
                            parserEmptyState("No samples loaded yet.")
                        } else {
                            ForEach(model.samples) { sample in
                                parserSampleRow(
                                    sample: sample,
                                    isSelected: model.selectedSampleIDs.contains(sample.sampleID),
                                    isPrimary: model.primarySampleID == sample.sampleID,
                                    previewRow: model.previewRow(for: sample.sampleID),
                                    onToggleSelected: { model.toggleSample(sample.sampleID) },
                                    onMakePrimary: { model.primarySampleID = sample.sampleID }
                                )
                            }
                        }
                    }
                }

                parserStepCard("Step 3: Parser Rule", isExpanded: $ruleExpanded) {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack(spacing: 10) {
                            parserField("Parser mode") {
                                Picker("Parser mode", selection: $model.parserMode) {
                                    Text("Guided (No Regex)").tag("guided")
                                    Text("Advanced (Regex)").tag("advanced")
                                }
                                .pickerStyle(.menu)
                            }
                            parserField("Parser slot") {
                                Picker("Parser slot", selection: $model.parserSlot) {
                                    ForEach(1...5, id: \.self) { idx in
                                        Text("Parser \(idx)").tag("parser_\(idx)")
                                    }
                                }
                                .pickerStyle(.menu)
                            }
                        }

                        Toggle("Invert amount before DB insert/update", isOn: $model.invertAmountSign)
                            .tint(.black)
                            .font(.system(size: 13, weight: .semibold, design: .rounded))

                        if model.subjectQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                            parserField("Subject contains (used when Step 1 subject is blank)") {
                                TextField("Transaction Notification", text: $model.subjectFallback)
                            }
                        }

                        if model.parserMode == "guided" {
                            VStack(spacing: 8) {
                                parserGuidedRow(title: "Amount", order: $model.guidedAmountOrder, label: $model.guidedAmountLabel, endMode: $model.guidedAmountEnd, endText: $model.guidedAmountEndText)
                                parserGuidedRow(title: "Merchant", order: $model.guidedMerchantOrder, label: $model.guidedMerchantLabel, endMode: $model.guidedMerchantEnd, endText: $model.guidedMerchantEndText)
                                parserGuidedRow(title: "Date", order: $model.guidedDateOrder, label: $model.guidedDateLabel, endMode: $model.guidedDateEnd, endText: $model.guidedDateEndText)
                                parserGuidedRow(title: "Time", order: $model.guidedTimeOrder, label: $model.guidedTimeLabel, endMode: $model.guidedTimeEnd, endText: $model.guidedTimeEndText)
                            }

                            HStack(spacing: 10) {
                                parserField("Account number before (optional)") {
                                    TextField("", text: $model.guidedAccountBefore)
                                }
                                parserField("Account number exact sequence (optional)") {
                                    TextField("", text: $model.guidedAccountExact)
                                }
                            }
                        } else {
                            parserField("Regex flags") {
                                TextField("i", text: $model.regexFlags)
                                    .textInputAutocapitalization(.never)
                                    .autocorrectionDisabled()
                            }
                            parserField("Body regex") {
                                TextEditor(text: $model.bodyRegex)
                                    .frame(minHeight: 120)
                            }
                            HStack(spacing: 10) {
                                parserField("Amount group") { TextField("1", text: $model.amountGroup).keyboardType(.numberPad) }
                                parserField("Merchant group") { TextField("2", text: $model.merchantGroup).keyboardType(.numberPad) }
                                parserField("Date group") { TextField("3", text: $model.dateGroup).keyboardType(.numberPad) }
                                parserField("Time group") { TextField("0", text: $model.timeGroup).keyboardType(.numberPad) }
                            }
                        }

                        HStack(spacing: 8) {
                            Button {
                                Task { await model.runPreview() }
                            } label: {
                                settingsSheetPrimaryButton(model.isRunningPreview ? "Running..." : "Run Dry-Run Preview")
                            }
                            .buttonStyle(.plain)
                            .disabled(model.isRunningPreview)

                            Button {
                                Task { await model.runParserTest() }
                            } label: {
                                settingsSheetSecondaryButton(model.isRunningParserTest ? "Running..." : "Test All Saved Parsers")
                            }
                            .buttonStyle(.plain)
                            .disabled(model.isRunningParserTest)
                        }

                        VStack(alignment: .leading, spacing: 8) {
                            Text("Live capture preview")
                                .font(.system(size: 13, weight: .bold, design: .rounded))
                            Text(model.liveCaptureStatusText)
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(model.liveCaptureMatched ? .secondary : .secondary)
                            if let capture = model.liveCapture {
                                parserLiveCaptureGrid(capture)
                            }
                            if !model.liveCaptureBody.isEmpty {
                                ScrollView(.horizontal, showsIndicators: false) {
                                    Text(model.liveCaptureBody)
                                        .font(.system(size: 11, weight: .regular, design: .monospaced))
                                        .textSelection(.enabled)
                                        .frame(maxWidth: .infinity, alignment: .leading)
                                        .padding(12)
                                }
                                .background(Color.white, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                                .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
                            }
                            Button {
                                Task { await model.refreshLiveCapture() }
                            } label: {
                                settingsSheetSecondaryButton(model.isRefreshingLiveCapture ? "Refreshing..." : "Refresh Capture Preview")
                            }
                            .buttonStyle(.plain)
                            .disabled(model.isRefreshingLiveCapture)
                        }
                    }
                }

                parserStepCard("Step 4: Preview Results", isExpanded: $resultsExpanded) {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(model.previewSummaryText)
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)

                        if model.previewRows.isEmpty {
                            parserEmptyState("No preview run yet.")
                        } else {
                            ForEach(model.previewRows) { row in
                                parserResultRow(row)
                            }
                        }

                        Text("Parser test report")
                            .font(.system(size: 13, weight: .bold, design: .rounded))

                        Text(model.testSummaryText)
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)

                        if model.testRows.isEmpty {
                            parserEmptyState("No parser test run yet.")
                        } else {
                            ForEach(model.testRows) { row in
                                parserTestRow(row)
                            }
                        }

                        Text("Correlation preview")
                            .font(.system(size: 13, weight: .bold, design: .rounded))

                        HStack(spacing: 10) {
                            parserField("Primary parser") {
                                Picker("Primary parser", selection: $model.correlationPrimaryDraftID) {
                                    Text("Select parser").tag(0)
                                    ForEach(model.accountSettings) { setting in
                                        Text(setting.subjectSettingLabel).tag(setting.draftID)
                                    }
                                }
                                .pickerStyle(.menu)
                            }
                            parserField("Secondary parser") {
                                Picker("Secondary parser", selection: $model.correlationSecondaryDraftID) {
                                    Text("Select parser").tag(0)
                                    ForEach(model.accountSettings) { setting in
                                        Text(setting.subjectSettingLabel).tag(setting.draftID)
                                    }
                                }
                                .pickerStyle(.menu)
                            }
                        }

                        Button {
                            Task { await model.runCorrelationPreview() }
                        } label: {
                            settingsSheetSecondaryButton(model.isRunningCorrelationPreview ? "Running..." : "Run Correlation Preview")
                        }
                        .buttonStyle(.plain)
                        .disabled(model.isRunningCorrelationPreview)

                        Text(model.correlationSummaryText)
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)

                        if model.correlationRows.isEmpty {
                            parserEmptyState("No correlation preview run yet.")
                        } else {
                            ForEach(model.correlationRows) { row in
                                parserCorrelationRow(row)
                            }
                        }

                        HStack(spacing: 8) {
                            Button {
                                Task { await model.saveDraft() }
                            } label: {
                                settingsSheetPrimaryButton(model.isSavingDraft ? "Saving..." : "Save Parser")
                            }
                            .buttonStyle(.plain)
                            .disabled(model.isSavingDraft)

                            Button {
                                Task { await model.deleteCurrentParser() }
                            } label: {
                                settingsSheetSecondaryButton(model.isDeletingDraft ? "Deleting..." : "Delete This Parser")
                            }
                            .buttonStyle(.plain)
                            .disabled(model.isDeletingDraft)
                        }
                    }
                }

                if showCloseButton {
                    Button { dismiss() } label: { settingsSheetSecondaryButton("Close") }
                        .buttonStyle(.plain)
                }
            }
            .padding(.bottom, 10)
        }
        .task {
            await model.loadAccounts()
        }
        .onChange(of: model.accountID) { _, _ in
            Task { await model.loadAccountSettings() }
        }
        .onChange(of: model.primarySampleID) { _, _ in
            Task { await model.refreshLiveCapture() }
        }
    }
}

@MainActor
private final class EmailParserWizardViewModel: ObservableObject {
    @Published var statusText = ""
    @Published var statusIsError = false
    @Published var accounts: [ParserWizardAccount] = []
    @Published var accountID: Int = 0
    @Published var accountSettings: [ParserWizardSetting] = []
    @Published var selectedDraftID: Int = 0
    @Published var senderQuery = ""
    @Published var subjectQuery = ""
    @Published var subjectFallback = ""
    @Published var lookbackDaysText = "30"
    @Published var sampleLimitText = "10"
    @Published var tryHTMLOnMissing = false
    @Published var samples: [ParserWizardSample] = []
    @Published var selectedSampleIDs: Set<String> = []
    @Published var primarySampleID: String = ""
    @Published var parserMode = "guided"
    @Published var parserSlot = "parser_1"
    @Published var invertAmountSign = false
    @Published var regexFlags = "i"
    @Published var bodyRegex = ""
    @Published var amountGroup = "1"
    @Published var merchantGroup = "2"
    @Published var dateGroup = "3"
    @Published var timeGroup = "0"
    @Published var guidedAmountOrder = "3"
    @Published var guidedAmountLabel = ""
    @Published var guidedAmountEnd = "auto"
    @Published var guidedAmountEndText = ""
    @Published var guidedMerchantOrder = "2"
    @Published var guidedMerchantLabel = ""
    @Published var guidedMerchantEnd = "auto"
    @Published var guidedMerchantEndText = ""
    @Published var guidedDateOrder = "1"
    @Published var guidedDateLabel = ""
    @Published var guidedDateEnd = "auto"
    @Published var guidedDateEndText = ""
    @Published var guidedTimeOrder = "0"
    @Published var guidedTimeLabel = ""
    @Published var guidedTimeEnd = "auto"
    @Published var guidedTimeEndText = ""
    @Published var guidedAccountBefore = ""
    @Published var guidedAccountExact = ""
    @Published var previewRows: [ParserWizardPreviewRow] = []
    @Published var testSummary: ParserWizardTestSummary?
    @Published var testRows: [ParserWizardTestRow] = []
    @Published var liveCapture: ParserWizardExtracted?
    @Published var liveCaptureStatusText = "Select a candidate in Step 2 to preview captures."
    @Published var liveCaptureBody = ""
    @Published var liveCaptureMatched = false
    @Published var isRefreshingLiveCapture = false
    @Published var correlationPrimaryDraftID: Int = 0
    @Published var correlationSecondaryDraftID: Int = 0
    @Published var correlationSummary: ParserWizardCorrelationSummary?
    @Published var correlationRows: [ParserWizardCorrelationRow] = []
    @Published var isRunningCorrelationPreview = false
    @Published var isLoadingSamples = false
    @Published var isRunningPreview = false
    @Published var isRunningParserTest = false
    @Published var isSavingDraft = false
    @Published var isDeletingDraft = false

    var samplesMetaText: String {
        if samples.isEmpty { return "No samples loaded yet." }
        return "\(samples.count) samples loaded. \(selectedSampleIDs.count) selected for preview."
    }

    var previewSummaryText: String {
        guard !previewRows.isEmpty else { return "No preview run yet." }
        let matched = previewRows.filter(\.matched).count
        return "Matched \(matched)/\(previewRows.count) samples."
    }

    var testSummaryText: String {
        guard let testSummary else { return "No parser test run yet." }
        return "Emails \(testSummary.emails) | parsers \(testSummary.parsers) | matches \(testSummary.matches) | inserted \(testSummary.inserted) | notifications \(testSummary.notifications)"
    }

    var correlationSummaryText: String {
        guard let correlationSummary else { return "No correlation preview run yet." }
        return "Pending \(correlationSummary.pending) | Resolved \(correlationSummary.resolved) | Immediate notify \(correlationSummary.notifyImmediate) | Skipped notified \(correlationSummary.skipAlreadyNotified)"
    }

    func previewRow(for sampleID: String) -> ParserWizardPreviewRow? {
        previewRows.first(where: { $0.sampleID == sampleID })
    }

    func loadAccounts() async {
        do {
            let out = try await SettingsAPI.fetch("/email-parser/trial/accounts", as: ParserWizardAccountsPayload.self)
            accounts = out.accounts
            setStatus("Connected to parser endpoints.", isError: false)
            if accountID == 0, let first = accounts.first {
                accountID = first.id
                await loadAccountSettings()
            }
        } catch {
            accounts = []
            setStatus("Could not load parser accounts.", isError: true)
        }
    }

    func loadAccountSettings() async {
        guard accountID > 0 else {
            accountSettings = []
            return
        }
        do {
            let out = try await SettingsAPI.fetch("/email-parser/trial/account-settings/\(accountID)", as: ParserWizardSettingsPayload.self)
            accountSettings = out.settings.sorted { $0.parserSlot < $1.parserSlot }
            if let parser1 = accountSettings.first(where: { $0.parserSlot == "parser_1" }) {
                correlationPrimaryDraftID = parser1.draftID
            }
            if let parser2 = accountSettings.first(where: { $0.parserSlot == "parser_2" }) {
                correlationSecondaryDraftID = parser2.draftID
            }
            if accountSettings.count == 1, let first = accountSettings.first {
                applySetting(first)
                selectedDraftID = first.draftID
            } else {
                selectedDraftID = 0
            }
        } catch {
            accountSettings = []
            resetDraftFields()
        }
    }

    func applySelectedDraft(id: Int) {
        guard let draft = accountSettings.first(where: { $0.draftID == id }) else { return }
        applySetting(draft)
    }

    func toggleSample(_ sampleID: String) {
        if selectedSampleIDs.contains(sampleID) {
            selectedSampleIDs.remove(sampleID)
        } else {
            selectedSampleIDs.insert(sampleID)
        }
    }

    func loadSamples() async {
        guard accountID > 0 else {
            setStatus("Select an account first.", isError: true)
            return
        }
        guard !senderQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            setStatus("Enter a sender filter.", isError: true)
            return
        }
        isLoadingSamples = true
        defer { isLoadingSamples = false }
        do {
            let out = try await SettingsAPI.fetch(
                "/email-parser/trial/samples",
                method: "POST",
                jsonBody: [
                    "account_id": accountID,
                    "sender_query": senderQuery.trimmingCharacters(in: .whitespacesAndNewlines),
                    "subject_query": subjectQuery.trimmingCharacters(in: .whitespacesAndNewlines),
                    "try_html_on_missing_fields": tryHTMLOnMissing,
                    "lookback_days": max(1, min(365, Int(lookbackDaysText) ?? 30)),
                    "limit": max(5, min(200, Int(sampleLimitText) ?? 10)),
                ],
                timeout: 90,
                as: ParserWizardSamplesPayload.self
            )
            samples = out.items
            selectedSampleIDs = Set(samples.map(\.sampleID))
            primarySampleID = samples.first?.sampleID ?? ""
            previewRows = []
            correlationRows = []
            correlationSummary = nil
            await refreshLiveCapture()
            setStatus("Loaded \(samples.count) samples.", isError: false)
        } catch {
            setStatus("Could not load samples.", isError: true)
        }
    }

    func runPreview() async {
        guard !selectedSampleIDs.isEmpty else {
            setStatus("Select at least one sample.", isError: true)
            return
        }
        isRunningPreview = true
        defer { isRunningPreview = false }
        do {
            let out = try await SettingsAPI.fetch(
                "/email-parser/trial/preview",
                method: "POST",
                jsonBody: draftPayload(sampleIDs: Array(selectedSampleIDs)),
                timeout: 90,
                as: ParserWizardPreviewPayload.self
            )
            previewRows = out.rows
            await refreshLiveCapture()
            setStatus("Preview complete.", isError: false)
        } catch {
            setStatus("Preview failed.", isError: true)
        }
    }

    func refreshLiveCapture() async {
        guard let primarySampleID = currentPrimarySampleID else {
            liveCapture = nil
            liveCaptureBody = ""
            liveCaptureMatched = false
            liveCaptureStatusText = "Select a candidate in Step 2 to preview captures."
            return
        }
        guard let sample = samples.first(where: { $0.sampleID == primarySampleID }) else { return }
        isRefreshingLiveCapture = true
        defer { isRefreshingLiveCapture = false }
        liveCaptureBody = String(sample.body.prefix(12000))
        do {
            let out = try await SettingsAPI.fetch(
                "/email-parser/trial/preview",
                method: "POST",
                jsonBody: draftPayload(sampleIDs: [primarySampleID]),
                timeout: 90,
                as: ParserWizardPreviewPayload.self
            )
            if let row = out.rows.first, row.matched {
                liveCapture = row.extracted
                liveCaptureMatched = true
                liveCaptureStatusText = sample.body.count > 12000 ? "Matched (body preview truncated)." : "Matched live preview."
            } else {
                let row = out.rows.first
                liveCapture = nil
                liveCaptureMatched = false
                liveCaptureStatusText = row?.error ?? "No match"
            }
        } catch {
            liveCapture = nil
            liveCaptureMatched = false
            liveCaptureStatusText = "Fill rule fields to preview captures."
        }
    }

    func runParserTest() async {
        isRunningParserTest = true
        defer { isRunningParserTest = false }
        do {
            let out = try await SettingsAPI.fetch(
                "/email-parser/trial/test-run",
                method: "POST",
                jsonBody: [
                    "sender_query": "",
                    "subject_query": "",
                    "try_html_on_missing_fields": tryHTMLOnMissing,
                    "lookback_days": 7,
                    "limit": 500,
                ],
                timeout: 120,
                as: ParserWizardTestPayload.self
            )
            testSummary = out.summary
            testRows = out.rows
            setStatus("Parser test complete.", isError: false)
        } catch {
            setStatus("Parser test failed.", isError: true)
        }
    }

    func saveDraft() async {
        guard accountID > 0 else {
            setStatus("Select an account.", isError: true)
            return
        }
        isSavingDraft = true
        defer { isSavingDraft = false }
        do {
            _ = try await SettingsAPI.fetch(
                "/email-parser/trial/save",
                method: "POST",
                jsonBody: draftPayload(sampleIDs: Array(selectedSampleIDs)),
                timeout: 90,
                as: ParserWizardMutationPayload.self
            )
            await loadAccountSettings()
            setStatus("Parser saved.", isError: false)
        } catch {
            setStatus("Save failed.", isError: true)
        }
    }

    func deleteCurrentParser() async {
        guard accountID > 0 else {
            setStatus("Select an account first.", isError: true)
            return
        }
        isDeletingDraft = true
        defer { isDeletingDraft = false }
        do {
            _ = try await SettingsAPI.fetch(
                "/email-parser/trial/draft/delete-one",
                method: "POST",
                jsonBody: [
                    "account_id": accountID,
                    "parser_slot": parserSlot,
                ],
                as: ParserWizardDeletePayload.self
            )
            await loadAccountSettings()
            previewRows = []
            setStatus("Parser deleted.", isError: false)
        } catch {
            setStatus("Delete parser failed.", isError: true)
        }
    }

    func runCorrelationPreview() async {
        guard accountID > 0 else {
            setStatus("Select an account first.", isError: true)
            return
        }
        guard correlationPrimaryDraftID > 0, correlationSecondaryDraftID > 0 else {
            setStatus("Select both Parser 1 and Parser 2.", isError: true)
            return
        }
        guard !selectedSampleIDs.isEmpty else {
            setStatus("Select at least one sample.", isError: true)
            return
        }
        isRunningCorrelationPreview = true
        defer { isRunningCorrelationPreview = false }
        do {
            let out = try await SettingsAPI.fetch(
                "/email-parser/trial/correlation-preview",
                method: "POST",
                jsonBody: [
                    "account_id": accountID,
                    "primary_draft_id": correlationPrimaryDraftID,
                    "secondary_draft_id": correlationSecondaryDraftID,
                    "sample_ids": Array(selectedSampleIDs),
                ],
                timeout: 120,
                as: ParserWizardCorrelationPayload.self
            )
            correlationSummary = out.summary
            correlationRows = out.rows
            setStatus("Correlation preview complete.", isError: false)
        } catch {
            setStatus("Correlation preview failed.", isError: true)
        }
    }

    private func setStatus(_ text: String, isError: Bool) {
        statusText = text
        statusIsError = isError
    }

    private var currentPrimarySampleID: String? {
        let trimmed = primarySampleID.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private func applySetting(_ setting: ParserWizardSetting) {
        senderQuery = setting.senderPattern
        subjectQuery = setting.subjectContains
        subjectFallback = setting.subjectContains
        parserMode = setting.parserMode.isEmpty ? "guided" : setting.parserMode
        parserSlot = setting.parserSlot
        invertAmountSign = setting.invertAmountSign
        bodyRegex = setting.bodyRegex
        regexFlags = setting.flags.isEmpty ? "i" : setting.flags
        amountGroup = "\(setting.fieldMap.amountGroup)"
        merchantGroup = "\(setting.fieldMap.merchantGroup)"
        dateGroup = "\(setting.fieldMap.dateGroup)"
        timeGroup = "\(setting.fieldMap.timeGroup)"
        guidedAmountLabel = setting.guided.amountLabel
        guidedMerchantLabel = setting.guided.merchantLabel
        guidedDateLabel = setting.guided.dateLabel
        guidedTimeLabel = setting.guided.timeLabel
        guidedAmountOrder = "\(setting.guided.amountOrder)"
        guidedMerchantOrder = "\(setting.guided.merchantOrder)"
        guidedDateOrder = "\(setting.guided.dateOrder)"
        guidedTimeOrder = "\(setting.guided.timeOrder)"
        guidedAmountEnd = setting.guided.amountEnd
        guidedMerchantEnd = setting.guided.merchantEnd
        guidedDateEnd = setting.guided.dateEnd
        guidedTimeEnd = setting.guided.timeEnd
        guidedAmountEndText = setting.guided.amountEndText
        guidedMerchantEndText = setting.guided.merchantEndText
        guidedDateEndText = setting.guided.dateEndText
        guidedTimeEndText = setting.guided.timeEndText
        guidedAccountBefore = setting.guided.accountBefore
        guidedAccountExact = setting.guided.accountExact
    }

    private func resetDraftFields() {
        selectedDraftID = 0
        parserMode = "guided"
        parserSlot = "parser_1"
        invertAmountSign = false
        bodyRegex = ""
        regexFlags = "i"
        amountGroup = "1"
        merchantGroup = "2"
        dateGroup = "3"
        timeGroup = "0"
    }

    private func draftPayload(sampleIDs: [String]) -> [String: Any] {
        let selectedAccount = accounts.first(where: { $0.id == accountID })
        let accountLabel = "\(selectedAccount?.institution ?? "Account") \(selectedAccount?.name ?? "")".trimmingCharacters(in: .whitespacesAndNewlines)
        let subjectValue = subjectQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? subjectFallback.trimmingCharacters(in: .whitespacesAndNewlines)
            : subjectQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        let name = "\(accountLabel) \(subjectValue.isEmpty ? "Email Rule" : subjectValue)".trimmingCharacters(in: .whitespacesAndNewlines)
        return [
            "name": name,
            "parser_mode": parserMode,
            "parsing_method": "guided_blocks",
            "parser_slot": parserSlot,
            "invert_amount_sign": invertAmountSign,
            "override_on_primary": false,
            "backup_assume_unknown": false,
            "pending_ttl_minutes": 30,
            "account_id": accountID,
            "sender_pattern": senderQuery.trimmingCharacters(in: .whitespacesAndNewlines),
            "subject_contains": subjectValue,
            "body_regex": parserMode == "advanced" ? bodyRegex : "",
            "flags": regexFlags.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "i" : regexFlags.trimmingCharacters(in: .whitespacesAndNewlines),
            "field_map": [
                "amount_group": Int(amountGroup) ?? 1,
                "merchant_group": Int(merchantGroup) ?? 2,
                "date_group": Int(dateGroup) ?? 3,
                "time_group": Int(timeGroup) ?? 0,
            ],
            "guided": [
                "amount_label": guidedAmountLabel.trimmingCharacters(in: .whitespacesAndNewlines),
                "merchant_label": guidedMerchantLabel.trimmingCharacters(in: .whitespacesAndNewlines),
                "date_label": guidedDateLabel.trimmingCharacters(in: .whitespacesAndNewlines),
                "time_label": guidedTimeLabel.trimmingCharacters(in: .whitespacesAndNewlines),
                "amount_order": Int(guidedAmountOrder) ?? 0,
                "merchant_order": Int(guidedMerchantOrder) ?? 0,
                "date_order": Int(guidedDateOrder) ?? 0,
                "time_order": Int(guidedTimeOrder) ?? 0,
                "amount_end": guidedAmountEnd,
                "merchant_end": guidedMerchantEnd,
                "date_end": guidedDateEnd,
                "time_end": guidedTimeEnd,
                "amount_end_text": guidedAmountEndText.trimmingCharacters(in: .whitespacesAndNewlines),
                "merchant_end_text": guidedMerchantEndText.trimmingCharacters(in: .whitespacesAndNewlines),
                "date_end_text": guidedDateEndText.trimmingCharacters(in: .whitespacesAndNewlines),
                "time_end_text": guidedTimeEndText.trimmingCharacters(in: .whitespacesAndNewlines),
                "account_before": guidedAccountBefore.trimmingCharacters(in: .whitespacesAndNewlines),
                "account_exact": guidedAccountExact.trimmingCharacters(in: .whitespacesAndNewlines),
            ],
            "sample_ids": sampleIDs,
        ]
    }
}

private struct ParserWizardAccountsPayload: Decodable {
    let accounts: [ParserWizardAccount]
}

private struct ParserWizardAccount: Decodable, Identifiable {
    let id: Int
    let institution: String?
    let name: String?
    let hasParserSetting: Bool?

    enum CodingKeys: String, CodingKey {
        case id, institution, name
        case hasParserSetting = "has_parser_setting"
    }

    var displayLabel: String {
        let marker = hasParserSetting == true ? "Configured" : "Needs setup"
        return "\(institution ?? "Unknown") - \(name ?? "Account") [\(marker)]"
    }
}

private struct ParserWizardSettingsPayload: Decodable {
    let settings: [ParserWizardSetting]
}

private struct ParserWizardSetting: Decodable, Identifiable {
    let draftID: Int
    let name: String
    let subjectContains: String
    let senderPattern: String
    let parserMode: String
    let parserSlot: String
    let invertAmountSign: Bool
    let bodyRegex: String
    let flags: String
    let fieldMap: ParserWizardFieldMap
    let guided: ParserWizardGuided

    enum CodingKeys: String, CodingKey {
        case draftID = "draft_id"
        case name
        case subjectContains = "subject_contains"
        case senderPattern = "sender_pattern"
        case parserMode = "parser_mode"
        case parserSlot = "parser_slot"
        case invertAmountSign = "invert_amount_sign"
        case bodyRegex = "body_regex"
        case flags
        case fieldMap = "field_map"
        case guided
    }

    var id: Int { draftID }

    var subjectSettingLabel: String {
        let slotNumber = parserSlot.replacingOccurrences(of: "parser_", with: "")
        return "[Parser \(slotNumber)]"
    }
}

private struct ParserWizardFieldMap: Decodable {
    let amountGroup: Int
    let merchantGroup: Int
    let dateGroup: Int
    let timeGroup: Int

    enum CodingKeys: String, CodingKey {
        case amountGroup = "amount_group"
        case merchantGroup = "merchant_group"
        case dateGroup = "date_group"
        case timeGroup = "time_group"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        amountGroup = (try? container.decode(Int.self, forKey: .amountGroup)) ?? 1
        merchantGroup = (try? container.decode(Int.self, forKey: .merchantGroup)) ?? 2
        dateGroup = (try? container.decode(Int.self, forKey: .dateGroup)) ?? 3
        timeGroup = (try? container.decode(Int.self, forKey: .timeGroup)) ?? 0
    }
}

private struct ParserWizardGuided: Decodable {
    let amountLabel: String
    let merchantLabel: String
    let dateLabel: String
    let timeLabel: String
    let amountOrder: Int
    let merchantOrder: Int
    let dateOrder: Int
    let timeOrder: Int
    let amountEnd: String
    let merchantEnd: String
    let dateEnd: String
    let timeEnd: String
    let amountEndText: String
    let merchantEndText: String
    let dateEndText: String
    let timeEndText: String
    let accountBefore: String
    let accountExact: String

    enum CodingKeys: String, CodingKey {
        case amountLabel = "amount_label"
        case merchantLabel = "merchant_label"
        case dateLabel = "date_label"
        case timeLabel = "time_label"
        case amountOrder = "amount_order"
        case merchantOrder = "merchant_order"
        case dateOrder = "date_order"
        case timeOrder = "time_order"
        case amountEnd = "amount_end"
        case merchantEnd = "merchant_end"
        case dateEnd = "date_end"
        case timeEnd = "time_end"
        case amountEndText = "amount_end_text"
        case merchantEndText = "merchant_end_text"
        case dateEndText = "date_end_text"
        case timeEndText = "time_end_text"
        case accountBefore = "account_before"
        case accountExact = "account_exact"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        amountLabel = (try? c.decode(String.self, forKey: .amountLabel)) ?? ""
        merchantLabel = (try? c.decode(String.self, forKey: .merchantLabel)) ?? ""
        dateLabel = (try? c.decode(String.self, forKey: .dateLabel)) ?? ""
        timeLabel = (try? c.decode(String.self, forKey: .timeLabel)) ?? ""
        amountOrder = (try? c.decode(Int.self, forKey: .amountOrder)) ?? 3
        merchantOrder = (try? c.decode(Int.self, forKey: .merchantOrder)) ?? 2
        dateOrder = (try? c.decode(Int.self, forKey: .dateOrder)) ?? 1
        timeOrder = (try? c.decode(Int.self, forKey: .timeOrder)) ?? 0
        amountEnd = (try? c.decode(String.self, forKey: .amountEnd)) ?? "auto"
        merchantEnd = (try? c.decode(String.self, forKey: .merchantEnd)) ?? "auto"
        dateEnd = (try? c.decode(String.self, forKey: .dateEnd)) ?? "auto"
        timeEnd = (try? c.decode(String.self, forKey: .timeEnd)) ?? "auto"
        amountEndText = (try? c.decode(String.self, forKey: .amountEndText)) ?? ""
        merchantEndText = (try? c.decode(String.self, forKey: .merchantEndText)) ?? ""
        dateEndText = (try? c.decode(String.self, forKey: .dateEndText)) ?? ""
        timeEndText = (try? c.decode(String.self, forKey: .timeEndText)) ?? ""
        accountBefore = (try? c.decode(String.self, forKey: .accountBefore)) ?? ""
        accountExact = (try? c.decode(String.self, forKey: .accountExact)) ?? ""
    }
}

private struct ParserWizardSamplesPayload: Decodable {
    let items: [ParserWizardSample]
}

private struct ParserWizardSample: Decodable, Identifiable {
    let sampleID: String
    let sender: String
    let subject: String
    let receivedAt: String
    let snippet: String
    let body: String

    enum CodingKeys: String, CodingKey {
        case sampleID = "sample_id"
        case sender, subject, snippet, body
        case receivedAt = "received_at"
    }

    var id: String { sampleID }
}

private struct ParserWizardPreviewPayload: Decodable {
    let rows: [ParserWizardPreviewRow]
}

private struct ParserWizardPreviewRow: Decodable, Identifiable {
    let sampleID: String
    let matched: Bool
    let extracted: ParserWizardExtracted?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case sampleID = "sample_id"
        case matched, extracted, error
    }

    var id: String { sampleID }
}

private struct ParserWizardExtracted: Decodable {
    let amount: String?
    let merchant: String?
    let date: String?
    let time: String?
}

private struct ParserWizardTestPayload: Decodable {
    let summary: ParserWizardTestSummary?
    let rows: [ParserWizardTestRow]
}

private struct ParserWizardTestSummary: Decodable {
    let emails: Int
    let parsers: Int
    let matches: Int
    let inserted: Int
    let notifications: Int

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: DynamicCodingKey.self)
        emails = (try? c.decode(Int.self, forKey: DynamicCodingKey("emails"))) ?? 0
        parsers = (try? c.decode(Int.self, forKey: DynamicCodingKey("parsers"))) ?? 0
        matches = (try? c.decode(Int.self, forKey: DynamicCodingKey("matches"))) ?? 0
        inserted = (try? c.decode(Int.self, forKey: DynamicCodingKey("inserted"))) ?? 0
        notifications = (try? c.decode(Int.self, forKey: DynamicCodingKey("notifications"))) ?? 0
    }
}

private struct ParserWizardTestRow: Decodable, Identifiable {
    let id: String
    let subject: String
    let sender: String
    let inserted: Bool
    let notified: Bool
    let skipReason: String?

    enum CodingKeys: String, CodingKey {
        case subject, sender, inserted, notified
        case skipReason = "skip_reason"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        subject = (try? c.decode(String.self, forKey: .subject)) ?? "(no subject)"
        sender = (try? c.decode(String.self, forKey: .sender)) ?? ""
        inserted = (try? c.decode(Bool.self, forKey: .inserted)) ?? false
        notified = (try? c.decode(Bool.self, forKey: .notified)) ?? false
        skipReason = try? c.decode(String.self, forKey: .skipReason)
        id = "\(subject)|\(sender)"
    }
}

private struct ParserWizardMutationPayload: Decodable {
    let ok: Bool?
}

private struct ParserWizardDeletePayload: Decodable {
    let deleted: Int?
}

private struct ParserWizardCorrelationPayload: Decodable {
    let summary: ParserWizardCorrelationSummary?
    let rows: [ParserWizardCorrelationRow]
}

private struct ParserWizardCorrelationSummary: Decodable {
    let pending: Int
    let resolved: Int
    let notifyImmediate: Int
    let skipAlreadyNotified: Int

    enum CodingKeys: String, CodingKey {
        case pending, resolved
        case notifyImmediate = "notify_immediate"
        case skipAlreadyNotified = "skip_already_notified"
    }
}

private struct ParserWizardCorrelationRow: Decodable, Identifiable {
    let subject: String
    let sender: String
    let matchedRule: String?
    let action: String?
    let txAction: String?
    let notify: Bool
    let extracted: ParserWizardExtracted?

    enum CodingKeys: String, CodingKey {
        case subject, sender, action, notify, extracted
        case matchedRule = "matched_rule"
        case txAction = "tx_action"
    }

    var id: String { "\(subject)|\(sender)|\(matchedRule ?? "")" }
}

private struct DynamicCodingKey: CodingKey {
    var stringValue: String
    var intValue: Int?
    init(_ string: String) { self.stringValue = string; self.intValue = nil }
    init?(stringValue: String) { self.stringValue = stringValue; self.intValue = nil }
    init?(intValue: Int) { self.stringValue = "\(intValue)"; self.intValue = intValue }
}

private func parserStepCard<Content: View>(_ title: String, isExpanded: Binding<Bool>, @ViewBuilder content: @escaping () -> Content) -> some View {
    let palette = settingsThemePalette()
    return VStack(alignment: .leading, spacing: 10) {
        DisclosureGroup(isExpanded: isExpanded) {
            VStack(alignment: .leading, spacing: 10) {
                content()
            }
            .padding(.top, 8)
        } label: {
            Text(title)
                .font(.system(size: 16, weight: .black, design: .rounded))
                .foregroundStyle(.primary)
        }
    }
    .padding(14)
    .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(palette.border, lineWidth: 1))
}

private func parserField<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
    let palette = settingsThemePalette()
    return VStack(alignment: .leading, spacing: 6) {
        Text(title)
            .font(.system(size: 12, weight: .bold, design: .rounded))
        content()
            .font(.system(size: 14, weight: .semibold, design: .rounded))
            .padding(.horizontal, 12)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
    .frame(maxWidth: .infinity, alignment: .leading)
}

private func parserGuidedRow(title: String, order: Binding<String>, label: Binding<String>, endMode: Binding<String>, endText: Binding<String>) -> some View {
    let palette = settingsThemePalette()
    return VStack(alignment: .leading, spacing: 8) {
        Text(title)
            .font(.system(size: 13, weight: .bold, design: .rounded))
        HStack(spacing: 8) {
            parserField("Order") { TextField("0", text: order).keyboardType(.numberPad) }
            parserField("Text before") { TextField("", text: label) }
            parserField("Ends at") {
                Picker("Ends at", selection: endMode) {
                    Text("Auto").tag("auto")
                    Text("Comma").tag("comma")
                    Text("Period").tag("period")
                    Text("New line").tag("newline")
                    Text("Sentence end").tag("sentence_end")
                    Text("Text").tag("text")
                }
                .pickerStyle(.menu)
            }
        }
        if endMode.wrappedValue == "text" {
            parserField("End text") { TextField("End at this text", text: endText) }
        }
    }
    .padding(10)
    .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(palette.border, lineWidth: 1))
}

private func parserSampleRow(sample: ParserWizardSample, isSelected: Bool, isPrimary: Bool, previewRow: ParserWizardPreviewRow?, onToggleSelected: @escaping () -> Void, onMakePrimary: @escaping () -> Void) -> some View {
    let palette = settingsThemePalette()
    return VStack(alignment: .leading, spacing: 8) {
        HStack(alignment: .top, spacing: 8) {
            Toggle("", isOn: Binding(get: { isSelected }, set: { _ in onToggleSelected() }))
                .labelsHidden()
                .tint(.black)
            VStack(alignment: .leading, spacing: 4) {
                Text(sample.subject.isEmpty ? "(no subject)" : sample.subject)
                    .font(.system(size: 13, weight: .bold, design: .rounded))
                Text(sample.sender)
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                Text(sample.receivedAt)
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            Button(isPrimary ? "Primary" : "Make Primary", action: onMakePrimary)
                .buttonStyle(.borderless)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
        }
        Text(sample.snippet.isEmpty ? sample.body : sample.snippet)
            .font(.system(size: 12, weight: .medium, design: .rounded))
            .foregroundStyle(.secondary)
            .lineLimit(4)
        if let previewRow {
            Text(previewRow.matched ? "Passed preview rules" : (previewRow.error ?? "Did not match preview rules"))
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(previewRow.matched ? .green : .secondary)
        }
    }
    .padding(12)
    .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(palette.border, lineWidth: 1))
}

private func parserResultRow(_ row: ParserWizardPreviewRow) -> some View {
    let palette = settingsThemePalette()
    return VStack(alignment: .leading, spacing: 4) {
        HStack {
            Text(row.sampleID)
                .font(.system(size: 11, weight: .bold, design: .rounded))
            Spacer()
            Text(row.matched ? "Matched" : "No match")
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(row.matched ? .green : .secondary)
        }
        if let extracted = row.extracted {
            Text("amount=\(extracted.amount ?? "") | merchant=\(extracted.merchant ?? "") | date=\(extracted.date ?? "") | time=\(extracted.time ?? "")")
                .font(.system(size: 11, weight: .regular, design: .monospaced))
                .textSelection(.enabled)
        } else if let error = row.error {
            Text(error)
                .font(.system(size: 11, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
        }
    }
    .padding(12)
    .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(palette.border, lineWidth: 1))
}

private func parserTestRow(_ row: ParserWizardTestRow) -> some View {
    let palette = settingsThemePalette()
    return VStack(alignment: .leading, spacing: 4) {
        HStack {
            Text(row.subject)
                .font(.system(size: 12, weight: .bold, design: .rounded))
            Spacer()
            Text("inserted=\(row.inserted ? "true" : "false") notified=\(row.notified ? "true" : "false")")
                .font(.system(size: 10, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
        }
        if !row.sender.isEmpty {
            Text(row.sender)
                .font(.system(size: 11, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
        }
        if let skipReason = row.skipReason, !skipReason.isEmpty {
            Text(skipReason)
                .font(.system(size: 11, weight: .regular, design: .monospaced))
        }
    }
    .padding(12)
    .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(palette.border, lineWidth: 1))
}

private func parserLiveCaptureGrid(_ extracted: ParserWizardExtracted) -> some View {
    let palette = settingsThemePalette()
    let items = [
        ("Amount", extracted.amount ?? ""),
        ("Merchant", extracted.merchant ?? ""),
        ("Date", extracted.date ?? ""),
        ("Time", extracted.time ?? ""),
    ]
    return LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
        ForEach(items, id: \.0) { item in
            VStack(alignment: .leading, spacing: 4) {
                Text(item.0)
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .foregroundStyle(.secondary)
                Text(item.1)
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(10)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }
}

private func parserCorrelationRow(_ row: ParserWizardCorrelationRow) -> some View {
    let palette = settingsThemePalette()
    return VStack(alignment: .leading, spacing: 4) {
        HStack {
            Text(row.subject.isEmpty ? "(no subject)" : row.subject)
                .font(.system(size: 12, weight: .bold, design: .rounded))
            Spacer()
            Text(row.notify ? "Notify" : "No Notify")
                .font(.system(size: 10, weight: .semibold, design: .rounded))
                .foregroundStyle(row.notify ? .green : .secondary)
        }
        if !row.sender.isEmpty {
            Text(row.sender)
                .font(.system(size: 11, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
        }
        Text("\(row.matchedRule ?? "none") | \(row.action ?? "") | \(row.txAction ?? "")")
            .font(.system(size: 11, weight: .medium, design: .rounded))
            .foregroundStyle(.secondary)
        if let extracted = row.extracted {
            Text("amount=\(extracted.amount ?? "") merchant=\(extracted.merchant ?? "") date=\(extracted.date ?? "") time=\(extracted.time ?? "")")
                .font(.system(size: 11, weight: .regular, design: .monospaced))
                .textSelection(.enabled)
        }
    }
    .padding(12)
    .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(palette.border, lineWidth: 1))
}

private func parserEmptyState(_ text: String) -> some View {
    let palette = settingsThemePalette()
    return Text(text)
        .font(.system(size: 12, weight: .medium, design: .rounded))
        .foregroundStyle(.secondary)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(palette.border, lineWidth: 1))
}

private struct ExternalAppsSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
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

private struct IncomeWizardContentView: View {
    @AppStorage("quail.incomeWizard.type") private var incomeType: String = "les"
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @Environment(\.dismiss) private var dismiss
    let showCloseButton: Bool

    @State private var profile = LESProfile()
    @State private var weekdayPoints = "1"
    @State private var weekendPoints = "2"
    @State private var keywordsText = ""
    @State private var statusText = "Loading..."
    @State private var previewText = ""
    @State private var isSavingProfile = false
    @State private var isSavingWeights = false
    @State private var isSavingMatchers = false

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            incomeTypeCard
            incomeProfileCard
            paycheckMatchersCard
            dailyWeightsCard
            if !statusText.isEmpty {
                Text(statusText)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            if showCloseButton {
                Button { dismiss() } label: { settingsSheetSecondaryButton("Close") }
                    .buttonStyle(.plain)
            }
        }
        .task { await load() }
    }

    private var incomeTypeCard: some View {
        settingsLikeCard {
            VStack(alignment: .leading, spacing: 10) {
                Text("Income Type")
                    .font(.system(size: 16, weight: .bold, design: .rounded))
                HStack(spacing: 8) {
                    incomeTypeButton("LES", value: "les")
                    incomeTypeButton("Salary", value: "salary")
                    incomeTypeButton("Hourly", value: "hourly")
                }
            }
        }
    }

    private var incomeProfileCard: some View {
        settingsLikeCard {
            VStack(alignment: .leading, spacing: 12) {
                Text("Income Profile")
                    .font(.system(size: 16, weight: .bold, design: .rounded))
                if incomeType == "les" {
                    lesProfileForm
                } else {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 8) {
                            Text(incomeType == "salary" ? "Salary Form" : "Hourly Form")
                                .font(.system(size: 14, weight: .semibold, design: .rounded))
                            Text("In progress")
                                .font(.system(size: 11, weight: .semibold, design: .rounded))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(QuailTheme.palette(for: themeSelection).elevatedSurface, in: Capsule(style: .continuous))
                        }
                        Text(incomeType == "salary" ? "Salary wizard fields are scaffolded and will be enabled in a follow-up update." : "Hourly wizard fields are scaffolded and will be enabled in a follow-up update.")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private var lesProfileForm: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                settingsInlineField("Paygrade", text: Binding(
                    get: { profile.paygrade },
                    set: { profile.paygrade = $0 }
                ))
                settingsDateField("Service start", text: Binding(
                    get: { profile.serviceStart },
                    set: { profile.serviceStart = $0 }
                ))
            }
            HStack(spacing: 8) {
                settingsBoolMenu("Dependents", value: Binding(
                    get: { profile.hasDependents },
                    set: { profile.hasDependents = $0 }
                ))
                settingsInlineField("BAH override", text: optionalMoneyBinding(for: \.bahOverride), keyboard: .decimalPad)
            }
            HStack(spacing: 8) {
                settingsInlineField("BAS", text: moneyBinding(for: \.bas), keyboard: .decimalPad)
                settingsInlineField("TSP rate", text: moneyBinding(for: \.tspRate), keyboard: .decimalPad)
            }
            HStack(spacing: 8) {
                settingsInlineField("Mid-month fraction", text: moneyBinding(for: \.midMonthFraction), keyboard: .decimalPad)
                settingsBoolMenu("FICA include special pays", value: Binding(
                    get: { profile.ficaIncludeSpecialPays },
                    set: { profile.ficaIncludeSpecialPays = $0 }
                ))
            }
            HStack(spacing: 8) {
                settingsInlineField("Submarine pay", text: moneyBinding(for: \.submarinePay), keyboard: .decimalPad)
                settingsInlineField("Career sea pay", text: moneyBinding(for: \.careerSeaPay), keyboard: .decimalPad)
            }
            HStack(spacing: 8) {
                settingsInlineField("Special duty pay", text: moneyBinding(for: \.specDutyPay), keyboard: .decimalPad)
                settingsInlineField("Extra withholding", text: moneyBinding(for: \.extraWithholding), keyboard: .decimalPad)
            }
            HStack(spacing: 8) {
                settingsBoolMenu("Meal deduction enabled", value: Binding(
                    get: { profile.mealDeductionEnabled },
                    set: { profile.mealDeductionEnabled = $0 }
                ))
                settingsOptionalDatePickerField("Meal deduction start", text: Binding(
                    get: { profile.mealDeductionStart ?? "" },
                    set: { profile.mealDeductionStart = $0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : $0 }
                ))
            }
            HStack(spacing: 8) {
                settingsInlineField("Meal rate", text: moneyBinding(for: \.mealRate), keyboard: .decimalPad)
                settingsInlineField("Meal end day", text: intBinding(for: \.mealEndDay), keyboard: .numberPad)
            }
            HStack(spacing: 8) {
                settingsInlineField("Allotments total", text: moneyBinding(for: \.allotmentsTotal), keyboard: .decimalPad)
                settingsInlineField("Collections total", text: moneyBinding(for: \.midMonthCollectionsTotal), keyboard: .decimalPad)
            }
            HStack(spacing: 8) {
                settingsMenuField("Filing status", selection: Binding(
                    get: { profile.filingStatus },
                    set: { profile.filingStatus = $0 }
                ), options: [("S", "Single"), ("MFJ", "Married jointly"), ("HOH", "Head of household")])
                settingsBoolMenu("Step 2: multiple jobs", value: Binding(
                    get: { profile.step2MultipleJobs },
                    set: { profile.step2MultipleJobs = $0 }
                ))
            }
            HStack(spacing: 8) {
                settingsInlineField("Dependents under 17", text: intBinding(for: \.depUnder17), keyboard: .numberPad)
                settingsInlineField("Other dependents", text: intBinding(for: \.otherDep), keyboard: .numberPad)
            }
            HStack(spacing: 8) {
                settingsInlineField("Other income", text: moneyBinding(for: \.otherIncomeAnnual), keyboard: .decimalPad)
                settingsInlineField("Other deductions", text: moneyBinding(for: \.otherDeductionsAnnual), keyboard: .decimalPad)
            }
            HStack(spacing: 8) {
                Button {
                    Task { await saveLESProfile() }
                } label: {
                    settingsSheetPrimaryButton(isSavingProfile ? "Saving..." : "Save")
                }
                .buttonStyle(.plain)
                .disabled(isSavingProfile)

                Button {
                    profile = LESProfile()
                    Task { await saveLESProfile() }
                } label: {
                    settingsSheetSecondaryButton("Reset to defaults")
                }
                .buttonStyle(.plain)
                .disabled(isSavingProfile)
            }
        }
    }

    private var paycheckMatchersCard: some View {
        settingsLikeCard {
            VStack(alignment: .leading, spacing: 10) {
                Text("Paycheck Matching")
                    .font(.system(size: 16, weight: .bold, design: .rounded))
                Text("Set merchant keywords used to identify paycheck deposits from last month.")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                TextEditor(text: $keywordsText)
                    .frame(minHeight: 130)
                    .padding(8)
                    .background(Color.black.opacity(0.04), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                Button {
                    Task { await savePaycheckMatchers() }
                } label: {
                    settingsSheetPrimaryButton(isSavingMatchers ? "Saving..." : "Save")
                }
                .buttonStyle(.plain)
                .disabled(isSavingMatchers)
            }
        }
    }

    private var dailyWeightsCard: some View {
        settingsLikeCard {
            VStack(alignment: .leading, spacing: 10) {
                Text("Daily Spending Weights")
                    .font(.system(size: 16, weight: .bold, design: .rounded))
                Text("Set how many points each day type uses when splitting your remaining budget.")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                HStack(spacing: 8) {
                    settingsInlineField("Weekday points", text: $weekdayPoints, keyboard: .numberPad)
                    settingsInlineField("Weekend points", text: $weekendPoints, keyboard: .numberPad)
                }
                Button {
                    Task { await saveDailyWeights() }
                } label: {
                    settingsSheetPrimaryButton(isSavingWeights ? "Saving..." : "Save")
                }
                .buttonStyle(.plain)
                .disabled(isSavingWeights)
                if !previewText.isEmpty {
                    Text(previewText)
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func load() async {
        statusText = "Loading..."
        do {
            let loadedProfile = try await QuailAPI.shared.fetchLESProfile()
            let loadedWeights = try await SettingsAPI.fetch("/settings/daily-weights", as: SettingsDailyWeightsPayload.self)
            let loadedMatchers = try await SettingsAPI.fetch("/settings/paycheck-matchers", as: SettingsPaycheckMatchersPayload.self)
            let loadedBudget = try await QuailAPI.shared.fetchMonthBudget()

            profile = loadedProfile.profile
            weekdayPoints = String(Int(max(1, round(loadedWeights.weekdayPoints ?? 1))))
            weekendPoints = String(Int(max(1, round(loadedWeights.weekendPoints ?? 2))))
            keywordsText = loadedMatchers.keywords.joined(separator: "\n")
            previewText = makeDailyWeightsPreview(from: loadedBudget)
            statusText = ""
        } catch {
            keywordsText = "dfas\npayroll\nsalary\ndirect deposit\nmil pay"
            statusText = "Could not load income settings."
        }
    }

    private func saveLESProfile() async {
        guard !isSavingProfile else { return }
        isSavingProfile = true
        defer { isSavingProfile = false }
        do {
            profile = try await QuailAPI.shared.saveLESProfile(profile).profile
            statusText = "LES profile saved."
        } catch {
            statusText = "Failed to save LES profile."
        }
    }

    private func saveDailyWeights() async {
        guard !isSavingWeights else { return }
        isSavingWeights = true
        defer { isSavingWeights = false }
        let weekday = max(1, min(10, Int(weekdayPoints) ?? 1))
        let weekend = max(1, min(10, Int(weekendPoints) ?? 2))
        weekdayPoints = String(weekday)
        weekendPoints = String(weekend)
        do {
            _ = try await SettingsAPI.fetch("/settings/daily-weights", method: "POST", jsonBody: [
                "weekday_points": weekday,
                "weekend_points": weekend,
            ], as: SettingsDailyWeightsPayload.self)
            _ = try? await QuailAPI.shared.fetchData(path: "/day-limit", queryItems: [URLQueryItem(name: "recalc", value: "1")])
            let monthBudget = try await QuailAPI.shared.fetchMonthBudget()
            previewText = makeDailyWeightsPreview(from: monthBudget)
            statusText = "Daily weights saved."
        } catch {
            statusText = "Failed to save daily weights."
        }
    }

    private func savePaycheckMatchers() async {
        guard !isSavingMatchers else { return }
        isSavingMatchers = true
        defer { isSavingMatchers = false }
        let keywords = normalizedKeywords(from: keywordsText)
        do {
            let out = try await SettingsAPI.fetch("/settings/paycheck-matchers", method: "POST", jsonBody: ["keywords": keywords], as: SettingsPaycheckMatchersPayload.self)
            keywordsText = out.keywords.joined(separator: "\n")
            statusText = "Paycheck matchers saved."
        } catch {
            statusText = "Failed to save paycheck matchers."
        }
    }

    private func makeDailyWeightsPreview(from payload: MonthBudgetPayload) -> String {
        let weekdayDays = max(0, payload.weekdayDaysLeft ?? 0)
        let weekendDays = max(0, payload.weekendDaysLeft ?? 0)
        let safe = payload.safeToSpend ?? 0
        let weekdayPointsValue = max(1, Int(weekdayPoints) ?? 1)
        let weekendPointsValue = max(1, Int(weekendPoints) ?? 2)
        let totalPoints = (weekdayDays * weekdayPointsValue) + (weekendDays * weekendPointsValue)
        let pointValue = totalPoints > 0 ? (safe / Double(totalPoints)) : 0
        let weekdayLimit = pointValue * Double(weekdayPointsValue)
        let weekendLimit = pointValue * Double(weekendPointsValue)
        let today = Calendar.current.component(.weekday, from: Date())
        let isWeekendToday = today == 1 || today == 7
        let todayLimit = isWeekendToday ? weekendLimit : weekdayLimit
        return """
        Safe to spend: \(nativeMoneyValue(safe))
        Days left: \(weekdayDays) weekday, \(weekendDays) weekend
        Weekday limit: \(nativeMoneyValue(weekdayLimit))
        Weekend limit: \(nativeMoneyValue(weekendLimit))
        Today (\(isWeekendToday ? "weekend" : "weekday")) limit: \(nativeMoneyValue(todayLimit))
        """
    }

    private func normalizedKeywords(from raw: String) -> [String] {
        var seen: Set<String> = []
        var out: [String] = []
        for line in raw.split(whereSeparator: \.isNewline) {
            let normalized = line.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard !normalized.isEmpty else { continue }
            let capped = String(normalized.prefix(64))
            guard !seen.contains(capped) else { continue }
            seen.insert(capped)
            out.append(capped)
            if out.count >= 20 { break }
        }
        return out
    }

    private func incomeTypeButton(_ title: String, value: String) -> some View {
        let palette = settingsThemePalette()
        return Button {
            incomeType = value
        } label: {
            Text(title)
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .frame(maxWidth: .infinity, minHeight: 40)
                .foregroundStyle(incomeType == value ? palette.primaryButtonText : palette.secondaryButtonText)
                .background((incomeType == value ? palette.primaryButton : palette.secondaryButton), in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(incomeType == value ? .clear : palette.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    private func settingsLikeCard<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        let palette = settingsThemePalette()
        return content()
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func settingsInlineField(_ title: String, text: Binding<String>, keyboard: UIKeyboardType = .default) -> some View {
        let palette = settingsThemePalette()
        return VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
            TextField(title, text: text)
                .keyboardType(keyboard)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .padding(.horizontal, 10)
                .frame(height: 42)
                .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func settingsDateField(_ title: String, text: Binding<String>) -> some View {
        settingsInlineField(title, text: text)
    }

    private func settingsOptionalDatePickerField(_ title: String, text: Binding<String>) -> some View {
        let palette = settingsThemePalette()
        return VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
            HStack(spacing: 8) {
                DatePicker(
                    "",
                    selection: Binding(
                        get: { isoDateStringToDate(text.wrappedValue.isEmpty ? isoDateString(Date()) : text.wrappedValue) },
                        set: { text.wrappedValue = isoDateString($0) }
                    ),
                    displayedComponents: .date
                )
                .labelsHidden()
                .datePickerStyle(.compact)
                .frame(maxWidth: .infinity, alignment: .leading)

                Button {
                    text.wrappedValue = ""
                } label: {
                    Text("Clear")
                        .font(.system(size: 11, weight: .semibold, design: .rounded))
                        .padding(.horizontal, 10)
                        .frame(height: 30)
                        .background(palette.secondaryButton, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 10)
            .frame(height: 42)
            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func settingsBoolMenu(_ title: String, value: Binding<Bool>) -> some View {
        settingsMenuField(title, selection: Binding(
            get: { value.wrappedValue ? "true" : "false" },
            set: { value.wrappedValue = ($0 == "true") }
        ), options: [("true", "Yes"), ("false", "No")])
    }

    private func settingsMenuField(_ title: String, selection: Binding<String>, options: [(String, String)]) -> some View {
        let palette = settingsThemePalette()
        return VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
            Picker(title, selection: selection) {
                ForEach(options, id: \.0) { option in
                    Text(option.1).tag(option.0)
                }
            }
            .pickerStyle(.menu)
            .padding(.horizontal, 10)
            .frame(height: 42)
            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func moneyBinding(for keyPath: WritableKeyPath<LESProfile, Double>) -> Binding<String> {
        Binding(
            get: { formatCompactDecimal(profile[keyPath: keyPath]) },
            set: { profile[keyPath: keyPath] = Double($0.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 0 }
        )
    }

    private func optionalMoneyBinding(for keyPath: WritableKeyPath<LESProfile, Double?>) -> Binding<String> {
        Binding(
            get: {
                guard let value = profile[keyPath: keyPath] else { return "" }
                return formatCompactDecimal(value)
            },
            set: {
                let trimmed = $0.trimmingCharacters(in: .whitespacesAndNewlines)
                profile[keyPath: keyPath] = trimmed.isEmpty ? nil : Double(trimmed)
            }
        )
    }

    private func intBinding(for keyPath: WritableKeyPath<LESProfile, Int>) -> Binding<String> {
        Binding(
            get: { String(profile[keyPath: keyPath]) },
            set: { profile[keyPath: keyPath] = Int($0.trimmingCharacters(in: .whitespacesAndNewlines)) ?? 0 }
        )
    }
}

private struct AdminConsoleSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
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
    static func request(path: String, method: String = "GET", jsonBody: [String: Any]? = nil, timeout: TimeInterval = 30) -> URLRequest {
        let url = AppConfig.url(path: path)
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = timeout
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

    static func fetch<T: Decodable>(_ path: String, method: String = "GET", jsonBody: [String: Any]? = nil, timeout: TimeInterval = 30, as type: T.Type) async throws -> T {
        let request = request(path: path, method: method, jsonBody: jsonBody, timeout: timeout)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw NSError(domain: "QuailSettings", code: (response as? HTTPURLResponse)?.statusCode ?? -1)
        }
        let decoder = JSONDecoder()
        return try decoder.decode(T.self, from: data)
    }
}

private func settingsSheetPrimaryButton(_ title: String) -> some View {
    SettingsSheetPrimaryButtonView(title: title)
}

private func settingsSheetSecondaryButton(_ title: String) -> some View {
    SettingsSheetSecondaryButtonView(title: title)
}

private struct SettingsPrimaryActionModifier: ViewModifier {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"

    func body(content: Content) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        content
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .frame(maxWidth: .infinity, minHeight: 46)
            .foregroundStyle(palette.primaryButtonText)
            .background(palette.primaryButton, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
    }
}

private struct SettingsSecondaryActionModifier: ViewModifier {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"

    func body(content: Content) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        content
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .frame(maxWidth: .infinity, minHeight: 44)
            .foregroundStyle(palette.secondaryButtonText)
            .background(palette.secondaryButton, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

private struct SettingsSheetPrimaryButtonView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    let title: String

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        Text(title)
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .frame(maxWidth: .infinity, minHeight: 48)
            .foregroundStyle(palette.primaryButtonText)
            .background(palette.primaryButton, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
    }
}

private struct SettingsSheetSecondaryButtonView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    let title: String

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        Text(title)
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .frame(maxWidth: .infinity, minHeight: 44)
            .foregroundStyle(palette.secondaryButtonText)
            .background(palette.secondaryButton, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

private struct SettingsBenefitDraft: Identifiable {
    let id = UUID()
    var category: String = ""
    var percentText: String = ""
}

private func isoDateString(_ date: Date) -> String {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter.string(from: date)
}

private func isoDateStringToDate(_ iso: String) -> Date {
    let formatter = DateFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.timeZone = TimeZone(secondsFromGMT: 0)
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter.date(from: iso) ?? Date()
}

private func formatCompactDecimal(_ value: Double) -> String {
    let formatter = NumberFormatter()
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.numberStyle = .decimal
    formatter.minimumFractionDigits = 0
    formatter.maximumFractionDigits = 3
    return formatter.string(from: NSNumber(value: value)) ?? String(value)
}

private struct SettingsOnboardingStatusPayload: Decodable {
    let canSetStartingBalance: Bool
    let wizardCompleted: Bool
    let steps: SettingsOnboardingStepsPayload?
    let counts: SettingsOnboardingCountsPayload?
    let accounts: [SettingsOnboardingAccountPayload]

    enum CodingKeys: String, CodingKey {
        case canSetStartingBalance = "can_set_starting_balance"
        case wizardCompleted = "wizard_completed"
        case steps
        case counts
        case accounts
    }
}

private struct SettingsOnboardingStepsPayload: Decodable {
    let accountsAdded: Bool
    let startingBalancesAdded: Bool
    let transactionsImported: Bool
    let pushoverUserKeySet: Bool

    enum CodingKeys: String, CodingKey {
        case accountsAdded = "accounts_added"
        case startingBalancesAdded = "starting_balances_added"
        case transactionsImported = "transactions_imported"
        case pushoverUserKeySet = "pushover_user_key_set"
    }
}

private struct SettingsOnboardingCountsPayload: Decodable {
    let accounts: Int
    let startingBalances: Int
    let transactions: Int

    enum CodingKeys: String, CodingKey {
        case accounts
        case startingBalances = "starting_balances"
        case transactions
    }
}

private struct SettingsOnboardingAccountPayload: Decodable, Identifiable {
    let id: Int
    let institution: String
    let name: String
    let accountType: String
    let interestPostDay: Int?
    let creditLimit: Double?
    let receivesEmails: Bool
    let isPaycheckAccount: Bool
    let cardBenefits: [SettingsOnboardingBenefitPayload]
    let setup: SettingsOnboardingAccountSetupPayload?

    enum CodingKeys: String, CodingKey {
        case id
        case institution
        case name
        case accountType = "accounttype"
        case interestPostDay = "interest_post_day"
        case creditLimit = "credit_limit"
        case receivesEmails = "receives_emails"
        case isPaycheckAccount = "is_paycheck_account"
        case cardBenefits = "card_benefits"
        case setup
    }
}

private struct SettingsOnboardingBenefitPayload: Decodable {
    let benefitType: String
    let cashbackPercent: Double

    enum CodingKeys: String, CodingKey {
        case benefitType = "benefit_type"
        case cashbackPercent = "cashback_percent"
    }
}

private struct SettingsOnboardingAccountSetupPayload: Decodable {
    let complete: Bool
    let missing: [String]
}

private struct SettingsOnboardingAccountMutationPayload: Decodable {
    let ok: Bool?
    let accountID: Int

    enum CodingKeys: String, CodingKey {
        case ok
        case accountID = "account_id"
    }
}

private struct SettingsOnboardingAccountDeletePayload: Decodable {
    let ok: Bool?
    let accountID: Int
    let deletedTransactions: Int

    enum CodingKeys: String, CodingKey {
        case ok
        case accountID = "account_id"
        case deletedTransactions = "deleted_transactions"
    }
}

private struct SettingsOnboardingPushoverKeyPayload: Decodable {
    let ok: Bool?
    let userKeySet: Bool

    enum CodingKeys: String, CodingKey {
        case ok
        case userKeySet = "user_key_set"
    }
}

private struct SettingsOnboardingPushoverTestPayload: Decodable {
    let ok: Bool?
    let sent: Bool?
}

private func copyToClipboard(_ text: String) {
    UIPasteboard.general.string = text
}
