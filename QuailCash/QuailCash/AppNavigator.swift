import SwiftUI
import Combine

@MainActor
final class AppNavigator: ObservableObject {
    @Published var path: [AppRoute] = []
    @Published var currentTab: BottomTab = .home
    @Published var unreadCount: Int = 0

    private var lastUnreadRefreshAt: Date?

    func show(_ route: AppRoute) {
        currentTab = tab(for: route)
        if route == .home {
            popToRoot()
            return
        }
        if path.last == route { return }
        path.append(route)
    }

    func replaceTop(with route: AppRoute) {
        currentTab = tab(for: route)
        if route == .home {
            popToRoot()
            return
        }
        if path.isEmpty {
            path = [route]
        } else {
            path[path.count - 1] = route
        }
    }

    func goBack() {
        guard !path.isEmpty else { return }
        path.removeLast()
        currentTab = path.last.map(tab(for:)) ?? .home
    }

    func popToRoot() {
        currentTab = .home
        path = []
    }

    func refreshUnreadCountIfNeeded(force: Bool = false) async {
        if !force,
           let lastUnreadRefreshAt,
           Date().timeIntervalSince(lastUnreadRefreshAt) < 20 {
            return
        }
        do {
            unreadCount = try await QuailCashAPI.shared.fetchNotificationsUnreadCount()
            lastUnreadRefreshAt = Date()
        } catch {
            if unreadCount == 0 {
                lastUnreadRefreshAt = Date()
            }
        }
    }

    private func tab(for route: AppRoute) -> BottomTab {
        switch route {
        case .home:
            return .home
        case .spending:
            return .spending
        case .budget:
            return .spending
        case .allTransactions:
            return .all
        case .analytics:
            return .analytics
        case .recurring:
            return .recurring
        case .settings, .notificationSettings, .notifications, .bankInfo, .csvImport, .ruleBuilder, .category, .account:
            return .home
        }
    }
}
