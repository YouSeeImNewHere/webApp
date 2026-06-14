import SwiftUI
import Combine

@MainActor
final class AppNavigator: ObservableObject {
    @Published var path = NavigationPath()
    @Published var currentTab: BottomTab = .home

    func show(_ route: AppRoute) {
        currentTab = tab(for: route)
        path = NavigationPath()
        path.append(route)
    }

    func popToRoot() {
        currentTab = .home
        path = NavigationPath()
    }

    private func tab(for route: AppRoute) -> BottomTab {
        switch route {
        case .home:
            return .home
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
