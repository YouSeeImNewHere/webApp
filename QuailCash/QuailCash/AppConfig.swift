import Foundation

enum AppConfig {
    static let callbackScheme = "quailcash"

    static let apiBaseURL: URL = {
        let raw = ProcessInfo.processInfo.environment["QUAIL_API_BASE_URL"]
            ?? defaultBaseURLString
        return URL(string: raw) ?? URL(string: defaultBaseURLString)!
    }()

    private static var defaultBaseURLString: String {
        #if targetEnvironment(simulator)
        return "http://127.0.0.1:8000"
        #else
        return "https://homelab.taileb5ffb.ts.net"
        #endif
    }

    static func loginURL(next: String = "/page/home") -> URL {
        url(path: "/login", queryItems: [
            URLQueryItem(name: "next", value: next),
        ])
    }

    static func homeURL(txLimit: Int = 15) -> URL {
        url(path: "/page/home", queryItems: [
            URLQueryItem(name: "tx_limit", value: String(txLimit)),
        ])
    }

    static func mobileAuthStartURL() -> URL {
        url(path: "/gmail/oauth/start", queryItems: [
            URLQueryItem(name: "callback", value: "\(callbackScheme)://auth"),
            URLQueryItem(name: "next", value: "/page/home"),
        ])
    }

    static func url(path: String, queryItems: [URLQueryItem] = []) -> URL {
        var components = URLComponents(url: apiBaseURL, resolvingAgainstBaseURL: false) ?? URLComponents()
        components.scheme = apiBaseURL.scheme
        components.host = apiBaseURL.host
        components.port = apiBaseURL.port
        components.path = path
        components.queryItems = queryItems.isEmpty ? nil : queryItems
        return components.url ?? apiBaseURL
    }
}
