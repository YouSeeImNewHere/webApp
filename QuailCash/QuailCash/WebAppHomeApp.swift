import SwiftUI

@main
struct QuailCashApp: App {
    @UIApplicationDelegateAdaptor(QuailCashAppDelegate.self) private var appDelegate
    @StateObject private var navigator = AppNavigator()
    @StateObject private var pushManager = MobilePushManager.shared

    var body: some Scene {
        WindowGroup {
            NavigationStack(path: $navigator.path) {
                NativePageView(route: .home)
                    .navigationDestination(for: AppRoute.self) { route in
                        NativePageView(route: route)
                    }
            }
            .environmentObject(navigator)
            .environmentObject(pushManager)
            .preferredColorScheme(.light)
            .task {
                pushManager.attach(navigator: navigator)
                await pushManager.bootstrap()
            }
        }
    }
}
