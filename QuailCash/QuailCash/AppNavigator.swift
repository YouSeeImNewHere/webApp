import SwiftUI
import Combine

@MainActor
final class AppNavigator: ObservableObject {
    @Published var rootRoute: AppRoute = .dashboard
    @Published var path: [AppRoute] = []
    @Published var currentTab: BottomTab = .home
    @Published var unreadCount: Int = 0

    private var lastUnreadRefreshAt: Date?

    func show(_ route: AppRoute) {
        currentTab = tab(for: route)
        if isRootCandidate(route) {
            setRoot(route)
            return
        }
        if path.last == route { return }
        path.append(route)
    }

    func replaceTop(with route: AppRoute) {
        currentTab = tab(for: route)
        if isRootCandidate(route) {
            setRoot(route)
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
        currentTab = tab(for: rootRoute)
        path = []
    }

    func setRoot(_ route: AppRoute) {
        rootRoute = route
        currentTab = tab(for: route)
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
        case .dashboard, .dashboardSettings:
            return .home
        case .home:
            return .home
        case .fitness, .fitnessSettings, .fitnessNotifications, .fitnessGoals,
             .vehicle, .vehicleSettings, .vehicleNotifications:
            return .home
        case .spending:
            return .spending
        case .map, .mapSettings, .adminDashboard:
            return .home
        case .budget:
            return .spending
        case .allTransactions:
            return .all
        case .analytics:
            return .analytics
        case .recurring:
            return .recurring
        case .settings, .setupWizard, .parserWizard, .incomeWizard, .notificationSettings, .notifications, .bankInfo, .csvImport, .importQueue, .ruleBuilder, .category, .account:
            return .home
        }
    }

    private func isRootCandidate(_ route: AppRoute) -> Bool {
        switch route {
        case .dashboard, .home, .fitness, .vehicle:
            return true
        default:
            return false
        }
    }
}
