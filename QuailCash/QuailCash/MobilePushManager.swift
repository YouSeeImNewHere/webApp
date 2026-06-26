import Foundation
import Combine
import UIKit
import UserNotifications

@MainActor
final class MobilePushManager: NSObject, ObservableObject {
    static let shared = MobilePushManager()
    static let isAvailable = true

    @Published private(set) var authorizationStatus: UNAuthorizationStatus = .notDetermined
    @Published private(set) var deviceToken: String = ""

    private weak var navigator: AppNavigator?

    func attach(navigator: AppNavigator) {
        self.navigator = navigator
    }

    func bootstrap() async {
        UNUserNotificationCenter.current().delegate = self
        guard Self.isAvailable else { return }
        await refreshAuthorizationStatus()
        if authorizationStatus == .authorized || authorizationStatus == .provisional || authorizationStatus == .ephemeral {
            UIApplication.shared.registerForRemoteNotifications()
        }
    }

    func refreshAuthorizationStatus() async {
        guard Self.isAvailable else {
            authorizationStatus = .denied
            return
        }
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        authorizationStatus = settings.authorizationStatus
    }

    func requestAuthorizationAndRegister() async -> Bool {
        guard Self.isAvailable else { return false }
        do {
            let granted = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound])
            await refreshAuthorizationStatus()
            guard granted else { return false }
            UIApplication.shared.registerForRemoteNotifications()
            return true
        } catch {
            await refreshAuthorizationStatus()
            return false
        }
    }

    func registerDeviceToken(_ data: Data) {
        guard Self.isAvailable else { return }
        let token = data.map { String(format: "%02x", $0) }.joined()
        deviceToken = token
        Task {
            try? await QuailCashAPI.shared.registerIOSPushDevice(
                token: token,
                environment: apnsEnvironment,
                deviceName: UIDevice.current.name,
                bundleID: Bundle.main.bundleIdentifier,
                appVersion: appVersion
            )
        }
    }

    func unregisterCurrentDevice() async {
        guard Self.isAvailable else { return }
        guard !deviceToken.isEmpty else { return }
        try? await QuailCashAPI.shared.unregisterIOSPushDevice(token: deviceToken)
    }

    func handleRegistrationFailure(_ error: Error) {
        print("[QuailCash] APNs registration failed: \(error.localizedDescription)")
    }

    private var appVersion: String? {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
        let build = Bundle.main.object(forInfoDictionaryKey: kCFBundleVersionKey as String) as? String
        if let version, let build, !version.isEmpty, !build.isEmpty {
            return "\(version) (\(build))"
        }
        return version ?? build
    }

    private var apnsEnvironment: String {
        #if DEBUG
        return "sandbox"
        #else
        return "production"
        #endif
    }
}

extension MobilePushManager: UNUserNotificationCenterDelegate {
    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        return [.banner, .badge, .sound]
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse
    ) async {
        await MainActor.run {
            self.navigator?.show(.notifications)
        }
    }
}

final class QuailCashAppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = MobilePushManager.shared
        return true
    }

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        Task { @MainActor in
            MobilePushManager.shared.registerDeviceToken(deviceToken)
        }
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        Task { @MainActor in
            MobilePushManager.shared.handleRegistrationFailure(error)
        }
    }
}
