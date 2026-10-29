import UIKit
import AuthenticationServices
import Capacitor

// App-local bridge: external system authentication, code-only PKCE return.
@objc(MatchgoerAuthPlugin)
public class MatchgoerAuthPlugin: CAPPlugin, CAPBridgedPlugin, ASWebAuthenticationPresentationContextProviding {
    public let identifier = "MatchgoerAuthPlugin"
    public let jsName = "MatchgoerAuth"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "authenticate", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getPendingReturn", returnType: CAPPluginReturnPromise)
    ]
    private var session: ASWebAuthenticationSession?
    private var anchor: UIWindow?
    private static weak var current: MatchgoerAuthPlugin?
    private static var pendingURL: String?
    public override func load() { Self.current = self }
    static func receive(_ url: URL) {
        guard url.scheme == "com.matchgoer.app", url.host == "auth", url.path == "/callback" else { return }
        pendingURL = url.absoluteString
        current?.notifyListeners("authReturn", data: ["url": url.absoluteString], retainUntilConsumed: true)
    }
    @objc func getPendingReturn(_ call: CAPPluginCall) {
        if let url = Self.pendingURL { Self.pendingURL = nil; call.resolve(["url": url]) }
        else { call.resolve() }
    }
    public func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        return anchor ?? ASPresentationAnchor()
    }
    @objc func authenticate(_ call: CAPPluginCall) {
        guard let raw = call.getString("url"), let url = URL(string: raw),
              let parts = URLComponents(url: url, resolvingAgainstBaseURL: false),
              url.scheme == "https", url.host == "xqnjayincslrlyfuvdys.supabase.co",
              url.port == nil, url.user == nil, url.password == nil, url.path == "/auth/v1/authorize" else {
            call.reject("Invalid authentication destination", "INVALID_DESTINATION"); return
        }
        let query = parts.queryItems ?? []
        guard ["provider", "redirect_to", "code_challenge", "code_challenge_method"].allSatisfy({ name in query.filter({ $0.name == name }).count == 1 }),
              query.first(where: { $0.name == "provider" })?.value == "google",
              query.first(where: { $0.name == "redirect_to" })?.value == "com.matchgoer.app://auth/callback",
              query.first(where: { $0.name == "code_challenge_method" })?.value == "s256",
              let challenge = query.first(where: { $0.name == "code_challenge" })?.value,
              challenge.count == 43 else { call.reject("PKCE required", "INVALID_DESTINATION"); return }
        DispatchQueue.main.async {
            guard self.session == nil, let window = self.bridge?.viewController?.view.window else {
                call.reject("Authentication is not ready", "NOT_READY"); return
            }
            self.anchor = window
            let session = ASWebAuthenticationSession(url: url, callbackURLScheme: "com.matchgoer.app") { [weak self] callback, error in
                self?.session = nil
                if let error = error as? ASWebAuthenticationSessionError, error.code == .canceledLogin {
                    call.reject("Authentication cancelled", "USER_CANCELLED"); return
                }
                guard error == nil, let callback = callback, callback.scheme == "com.matchgoer.app",
                      callback.host == "auth", callback.path == "/callback" else {
                    call.reject("Authentication did not return safely", "AUTH_FAILED"); return
                }
                call.resolve(["url": callback.absoluteString])
            }
            session.presentationContextProvider = self
            self.session = session
            if !session.start() { self.session = nil; call.reject("Authentication could not start", "AUTH_FAILED") }
        }
    }
}

class MatchgoerViewController: CAPBridgeViewController {
    override func capacitorDidLoad() { bridge?.registerPluginInstance(MatchgoerAuthPlugin()) }
}
