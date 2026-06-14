import Foundation

enum AuthStore {
    private static let tokenKey = "quail.mobile.api.token"
    private static let emailKey = "quail.mobile.api.email"
    private static let tenantIDKey = "quail.mobile.api.tenant_id"

    static var token: String? {
        get {
            let value = UserDefaults.standard.string(forKey: tokenKey) ?? ""
            return value.isEmpty ? nil : value
        }
        set {
            UserDefaults.standard.setValue(newValue ?? "", forKey: tokenKey)
        }
    }

    static var email: String? {
        get {
            let value = UserDefaults.standard.string(forKey: emailKey) ?? ""
            return value.isEmpty ? nil : value
        }
        set {
            UserDefaults.standard.setValue(newValue ?? "", forKey: emailKey)
        }
    }

    static var tenantID: Int? {
        get {
            let value = UserDefaults.standard.integer(forKey: tenantIDKey)
            return value > 0 ? value : nil
        }
        set {
            UserDefaults.standard.set(newValue ?? 0, forKey: tenantIDKey)
        }
    }

    static func clear() {
        token = nil
        email = nil
        tenantID = nil
    }
}
