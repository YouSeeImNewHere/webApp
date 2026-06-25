import SwiftUI
@main
struct QuailCashApp: App {
    @UIApplicationDelegateAdaptor(QuailCashAppDelegate.self) private var appDelegate
    @StateObject private var navigator = AppNavigator()
    @StateObject private var pushManager = MobilePushManager.shared
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"

    var body: some Scene {
        WindowGroup {
            NavigationStack(path: $navigator.path) {
                NativePageView(route: navigator.rootRoute)
                    .navigationDestination(for: AppRoute.self) { route in
                        NativePageView(route: route)
                    }
            }
            .environmentObject(navigator)
            .environmentObject(pushManager)
            .preferredColorScheme(QuailThemeMode(rawValue: themeSelection).preferredColorScheme)
            .task {
                pushManager.attach(navigator: navigator)
                await pushManager.bootstrap()
            }
        }
    }
}
