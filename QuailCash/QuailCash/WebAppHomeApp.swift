import SwiftUI

@main
struct QuailCashApp: App {
    @StateObject private var navigator = AppNavigator()

    var body: some Scene {
        WindowGroup {
            NavigationStack(path: $navigator.path) {
                NativePageView(route: .home)
                    .navigationDestination(for: AppRoute.self) { route in
                        NativePageView(route: route)
                    }
            }
            .environmentObject(navigator)
            .preferredColorScheme(.light)
        }
    }
}
