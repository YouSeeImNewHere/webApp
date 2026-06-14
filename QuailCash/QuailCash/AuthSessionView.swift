import AuthenticationServices
import SwiftUI
import Combine
import UIKit

struct AuthSessionView: View {
    let startURL: URL
    let callbackScheme: String
    let onAuthenticated: () -> Void
    let onCancel: () -> Void

    @StateObject private var model = AuthSessionViewModel()

    var body: some View {
        VStack(spacing: 18) {
            Spacer()

            VStack(spacing: 8) {
                Text("Sign in to QuailCash")
                    .font(.system(size: 22, weight: .bold, design: .rounded))
                Text(model.statusText)
                    .font(.system(size: 14, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            if let error = model.errorMessage {
                Text(error)
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 16)
            }

            Button {
                model.start(
                    startURL: startURL,
                    callbackScheme: callbackScheme,
                    onAuthenticated: onAuthenticated,
                    onCancel: onCancel
                )
            } label: {
                Text("Continue with Google")
                    .font(.system(size: 16, weight: .semibold, design: .rounded))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
            }
            .buttonStyle(AuthButtonStyle())
            .padding(.horizontal, 16)

            Spacer()
        }
        .onAppear {
            // Give the sheet one runloop to finish attaching to a real window
            // before starting ASWebAuthenticationSession.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                model.start(
                    startURL: startURL,
                    callbackScheme: callbackScheme,
                    onAuthenticated: onAuthenticated,
                    onCancel: onCancel
                )
            }
        }
    }
}

private struct AuthButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(.white)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(.black)
                    .opacity(configuration.isPressed ? 0.78 : 1.0)
            )
    }
}

@MainActor
final class AuthSessionViewModel: NSObject, ObservableObject, ASWebAuthenticationPresentationContextProviding {
    @Published var statusText: String = "Opening secure sign-in..."
    @Published var errorMessage: String?

    private var session: ASWebAuthenticationSession?
    private var didStart = false

    func start(
        startURL: URL,
        callbackScheme: String,
        onAuthenticated: @escaping () -> Void,
        onCancel: @escaping () -> Void
    ) {
        guard !didStart else { return }
        didStart = true
        errorMessage = nil
        statusText = "Waiting for Google sign-in..."
        print("[QuailCash] AuthSessionViewModel.start() startURL=\(startURL.absoluteString)")

        let authSession = ASWebAuthenticationSession(
            url: startURL,
            callbackURLScheme: callbackScheme
        ) { [weak self] callbackURL, error in
            guard let self else { return }
            self.session = nil
            self.didStart = false

            if let callbackURL {
                print("[QuailCash] AuthSessionViewModel.callbackURL=\(callbackURL.absoluteString)")
                let comps = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false)
                let items = comps?.queryItems ?? []
                let token = items.first(where: { $0.name == "token" })?.value ?? ""
                let email = items.first(where: { $0.name == "email" })?.value ?? ""
                let tenantIDRaw = items.first(where: { $0.name == "tenant_id" })?.value ?? ""
                let tenantID = Int(tenantIDRaw)
                if !token.isEmpty {
                    AuthStore.token = token
                    AuthStore.email = email
                    AuthStore.tenantID = tenantID
                    self.statusText = "Signed in."
                    print("[QuailCash] AuthSessionViewModel authenticated email=\(email) tenantID=\(tenantID ?? 0)")
                    onAuthenticated()
                    return
                }
                print("[QuailCash] AuthSessionViewModel callback missing token")
            }

            if let nsError = error as NSError?, nsError.domain == ASWebAuthenticationSessionError.errorDomain {
                print("[QuailCash] AuthSessionViewModel ASWebAuthenticationSession error code=\(nsError.code) desc=\(nsError.localizedDescription)")
                switch ASWebAuthenticationSessionError.Code(rawValue: nsError.code) {
                case .canceledLogin:
                    self.statusText = "Sign-in canceled."
                    onCancel()
                default:
                    self.errorMessage = nsError.localizedDescription
                    self.statusText = "Sign-in failed."
                }
            } else {
                print("[QuailCash] AuthSessionViewModel non-session error=\(error?.localizedDescription ?? "nil")")
                self.errorMessage = error?.localizedDescription ?? "Unknown sign-in error."
                self.statusText = "Sign-in failed."
            }
        }
        authSession.presentationContextProvider = self
        authSession.prefersEphemeralWebBrowserSession = false
        self.session = authSession
        let started = authSession.start()
        print("[QuailCash] AuthSessionViewModel.start() returned \(started)")
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        let windows = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap { $0.windows }
        return windows.first(where: { $0.isKeyWindow }) ?? windows.first ?? ASPresentationAnchor()
    }
}
