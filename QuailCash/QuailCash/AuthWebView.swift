import SwiftUI
import WebKit

struct AuthWebView: UIViewRepresentable {
    let startURL: URL
    let onAuthenticated: ([HTTPCookie]) -> Void
    let onCancel: () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onAuthenticated: onAuthenticated)
    }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()

        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = false
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.load(URLRequest(url: startURL))
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate {
        private let onAuthenticated: ([HTTPCookie]) -> Void
        private var didComplete = false

        init(onAuthenticated: @escaping ([HTTPCookie]) -> Void) {
            self.onAuthenticated = onAuthenticated
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            guard !didComplete else { return }
            guard let url = webView.url else { return }
            guard let host = url.host?.lowercased(), host == AppConfig.apiBaseURL.host?.lowercased() else {
                return
            }

            let path = url.path
            guard path == "/" || path == "/page/home" else {
                return
            }

            didComplete = true
            webView.configuration.websiteDataStore.httpCookieStore.getAllCookies { cookies in
                let hostCookies = cookies.filter { cookie in
                    let domain = cookie.domain.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "."))
                    let targetHost = AppConfig.apiBaseURL.host?.lowercased() ?? ""
                    return domain == targetHost || domain.hasSuffix("." + targetHost)
                }
                self.onAuthenticated(hostCookies)
            }
        }
    }
}
