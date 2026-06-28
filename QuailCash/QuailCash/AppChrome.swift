import SwiftUI
import UIKit

enum BottomTab: String, CaseIterable, Identifiable {
    case home
    case spending
    case all
    case analytics
    case recurring

    var id: String { rawValue }

    var title: String {
        switch self {
        case .home: return "Home"
        case .spending: return "Spending"
        case .all: return "All"
        case .analytics: return "Analytics"
        case .recurring: return "Recurring"
        }
    }

    var systemImage: String {
        switch self {
        case .home: return "house.fill"
        case .spending: return "banknote.fill"
        case .all: return "magnifyingglass"
        case .analytics: return "chart.bar.fill"
        case .recurring: return "arrow.triangle.2.circlepath"
        }
    }
}

struct AppTopBar: View {
    let title: String
    let badgeValue: Int?
    let palette: QuailThemePalette
    let onLeadingTap: () -> Void
    let onTrailingTap: () -> Void
    var trailingIcon: String = "bell.fill"
    var extraTrailingAction: (() -> Void)? = nil
    var extraTrailingIcon: String = "plus"
    var extraTrailingAction2: (() -> Void)? = nil
    var extraTrailingIcon2: String = "bookmark.fill"

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

            Spacer(minLength: 8)

            Text(title)
                .font(.system(size: 16, weight: .semibold, design: .rounded))
                .foregroundStyle(palette.chromeIconForeground)

            Spacer(minLength: 8)

            BugReportFAB(palette: palette)

            if let extraAction2 = extraTrailingAction2 {
                Button(action: extraAction2) {
                    Image(systemName: extraTrailingIcon2)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(palette.chromeIconForeground)
                        .frame(width: 36, height: 36)
                        .background(palette.chromeIconBackground, in: Circle())
                        .overlay(Circle().stroke(palette.border, lineWidth: 1))
                }
            }
            if let extraAction = extraTrailingAction {
                Button(action: extraAction) {
                    Image(systemName: extraTrailingIcon)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(palette.chromeIconForeground)
                        .frame(width: 36, height: 36)
                        .background(palette.chromeIconBackground, in: Circle())
                        .overlay(Circle().stroke(palette.border, lineWidth: 1))
                }
            }

            Button(action: onTrailingTap) {
                ZStack(alignment: .topTrailing) {
                    Image(systemName: trailingIcon)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(palette.chromeIconForeground)
                        .frame(width: 36, height: 36)
                        .background(palette.chromeIconBackground, in: Circle())
                        .overlay(Circle().stroke(palette.border, lineWidth: 1))

                    if trailingIcon == "bell.fill", let badgeValue, badgeValue > 0 {
                        Text(badgeValue > 9 ? "9+" : "\(badgeValue)")
                            .font(.system(size: 10, weight: .bold, design: .rounded))
                            .foregroundStyle(.white)
                            .frame(minWidth: 16, minHeight: 16)
                            .padding(.horizontal, 4)
                            .background(Color.red, in: Capsule(style: .continuous))
                            .offset(x: 4, y: -4)
                    }
                }
            }
            .accessibilityLabel(trailingIcon == "bell.fill" ? "Notifications" : "Action")
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

struct AppBottomBar: View {
    let selectedTab: BottomTab?
    let palette: QuailThemePalette
    let onSelectTab: (BottomTab) -> Void
    let onDashboardTap: () -> Void

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(alignment: .center, spacing: 6) {
                ForEach(BottomTab.allCases) { tab in
                    Button {
                        onSelectTab(tab)
                    } label: {
                        VStack(spacing: 4) {
                            Image(systemName: tab.systemImage)
                                .font(.system(size: 16, weight: .semibold))
                            Text(tab.title)
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                        }
                        .frame(minWidth: 84)
                        .padding(.vertical, 8)
                        .foregroundStyle(selectedTab == tab ? palette.chromeIconForeground : palette.chromeIconForeground.opacity(0.72))
                        .background(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .fill(selectedTab == tab ? palette.selectedTabFill : .clear)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .stroke(selectedTab == tab ? palette.border : .clear, lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                }

                Button(action: onDashboardTap) {
                    VStack(spacing: 4) {
                        Image(systemName: "square.grid.2x2.fill")
                            .font(.system(size: 16, weight: .semibold))
                        Text("Dashboard")
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                    }
                    .frame(minWidth: 108)
                    .padding(.vertical, 8)
                    .foregroundStyle(palette.primaryButtonText)
                    .background(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .fill(palette.primaryButton)
                    )
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 8)
            .padding(.top, 6)
            .padding(.bottom, 2)
        }
        .background(palette.barBackground)
        .overlay(
            Rectangle()
                .fill(palette.barDivider)
                .frame(height: 1),
            alignment: .top
        )
    }
}

struct MapReturnBar: View {
    let palette: QuailThemePalette
    let onMapTap: () -> Void
    let onHomeTap: () -> Void

    var body: some View {
        HStack {
            Spacer()
            Button(action: onMapTap) {
                HStack(spacing: 6) {
                    Image(systemName: "map.fill")
                        .font(.system(size: 15, weight: .semibold))
                    Text("Map")
                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                }
                .foregroundStyle(palette.primaryButtonText)
                .padding(.horizontal, 24)
                .padding(.vertical, 10)
                .background(palette.primaryButton, in: Capsule())
            }
            .buttonStyle(.plain)
            Spacer()
            Button(action: onHomeTap) {
                HStack(spacing: 6) {
                    Image(systemName: "house.fill")
                        .font(.system(size: 15, weight: .semibold))
                    Text("Home")
                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                }
                .foregroundStyle(palette.chromeIconForeground)
                .padding(.horizontal, 24)
                .padding(.vertical, 10)
                .background(palette.chromeIconBackground, in: Capsule())
                .overlay(Capsule().stroke(palette.border, lineWidth: 1))
            }
            .buttonStyle(.plain)
            Spacer()
        }
        .padding(.vertical, 10)
        .background(palette.barBackground)
        .overlay(Rectangle().fill(palette.barDivider).frame(height: 1), alignment: .top)
    }
}

struct AppStandaloneBar: View {
    let palette: QuailThemePalette
    let onHomeTap: () -> Void

    var body: some View {
        HStack {
            Spacer()
            Button(action: onHomeTap) {
                HStack(spacing: 6) {
                    Image(systemName: "house.fill")
                        .font(.system(size: 15, weight: .semibold))
                    Text("Home")
                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                }
                .foregroundStyle(palette.primaryButtonText)
                .padding(.horizontal, 24)
                .padding(.vertical, 10)
                .background(palette.primaryButton, in: Capsule())
            }
            .buttonStyle(.plain)
            Spacer()
        }
        .padding(.vertical, 10)
        .background(palette.barBackground)
        .overlay(Rectangle().fill(palette.barDivider).frame(height: 1), alignment: .top)
    }
}

struct AppChromeFrame<Content: View>: View {
    @EnvironmentObject private var navigator: AppNavigator
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    let title: String
    let badgeValue: Int?
    let selectedTab: BottomTab?
    let showsBottomBar: Bool
    let showsStandaloneBar: Bool
    let onLeadingTap: () -> Void
    let onTrailingTap: (() -> Void)?
    let onSelectTab: (BottomTab) -> Void
    var trailingIcon: String = "bell.fill"
    var extraTrailingAction: (() -> Void)? = nil
    var extraTrailingIcon: String = "plus"
    var extraTrailingAction2: (() -> Void)? = nil
    var extraTrailingIcon2: String = "bookmark.fill"
    let content: Content

    init(
        title: String,
        badgeValue: Int?,
        selectedTab: BottomTab?,
        showsBottomBar: Bool = true,
        showsStandaloneBar: Bool = false,
        onLeadingTap: @escaping () -> Void,
        onTrailingTap: (() -> Void)? = nil,
        onSelectTab: @escaping (BottomTab) -> Void = { _ in },
        trailingIcon: String = "bell.fill",
        extraTrailingAction: (() -> Void)? = nil,
        extraTrailingIcon: String = "plus",
        extraTrailingAction2: (() -> Void)? = nil,
        extraTrailingIcon2: String = "bookmark.fill",
        @ViewBuilder content: () -> Content
    ) {
        self.title = title
        self.badgeValue = badgeValue
        self.selectedTab = selectedTab
        self.showsBottomBar = showsBottomBar
        self.showsStandaloneBar = showsStandaloneBar
        self.onLeadingTap = onLeadingTap
        self.onTrailingTap = onTrailingTap
        self.onSelectTab = onSelectTab
        self.trailingIcon = trailingIcon
        self.extraTrailingAction = extraTrailingAction
        self.extraTrailingIcon = extraTrailingIcon
        self.extraTrailingAction2 = extraTrailingAction2
        self.extraTrailingIcon2 = extraTrailingIcon2
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
        .background(InteractivePopGestureEnabler())
        .safeAreaInset(edge: .top, spacing: 0) {
            AppTopBar(
                title: title,
                badgeValue: badgeValue ?? navigator.unreadCount,
                palette: palette,
                onLeadingTap: onLeadingTap,
                onTrailingTap: onTrailingTap ?? { navigator.show(.notifications) },
                trailingIcon: trailingIcon,
                extraTrailingAction: extraTrailingAction,
                extraTrailingIcon: extraTrailingIcon,
                extraTrailingAction2: extraTrailingAction2,
                extraTrailingIcon2: extraTrailingIcon2
            )
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if showsBottomBar {
                AppBottomBar(
                    selectedTab: selectedTab,
                    palette: palette,
                    onSelectTab: onSelectTab,
                    onDashboardTap: { navigator.setRoot(.dashboard) }
                )
            } else if showsStandaloneBar {
                AppStandaloneBar(palette: palette, onHomeTap: { navigator.setRoot(.dashboard) })
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .toolbar(.hidden, for: .navigationBar)
        .task {
            await navigator.refreshUnreadCountIfNeeded()
        }
    }
}

private struct InteractivePopGestureEnabler: UIViewControllerRepresentable {
    func makeUIViewController(context: Context) -> Controller {
        Controller()
    }

    func updateUIViewController(_ uiViewController: Controller, context: Context) {
        uiViewController.enableInteractivePop()
    }

    final class Controller: UIViewController {
        override func viewDidAppear(_ animated: Bool) {
            super.viewDidAppear(animated)
            enableInteractivePop()
        }

        func enableInteractivePop() {
            guard let navigationController else { return }
            navigationController.interactivePopGestureRecognizer?.isEnabled = true
            navigationController.interactivePopGestureRecognizer?.delegate = nil
        }
    }
}

struct AppPageScroll<Content: View>: View {
    let content: Content
    let contentPadding: CGFloat
    let refreshAction: (() async -> Void)?

    init(contentPadding: CGFloat = 12, refreshAction: (() async -> Void)? = nil, @ViewBuilder content: () -> Content) {
        self.contentPadding = contentPadding
        self.refreshAction = refreshAction
        self.content = content()
    }

    var body: some View {
        Group {
            if let refreshAction {
                scrollBody
                    .refreshable {
                        await refreshAction()
                    }
            } else {
                scrollBody
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
    }

    private var scrollBody: some View {
        GeometryReader { proxy in
            ScrollView(.vertical, showsIndicators: false) {
                VStack(alignment: .leading, spacing: 12) {
                    content
                }
                .frame(width: max(0, proxy.size.width - (contentPadding * 2)), alignment: .leading)
                .padding(contentPadding)
            }
            .scrollBounceBehavior(.basedOnSize, axes: .vertical)
        }
        .clipped()
    }
}
