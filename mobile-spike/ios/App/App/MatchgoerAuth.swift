import UIKit
import AuthenticationServices
import Capacitor
import CryptoKit
import Security

// App-local bridge: external system authentication, code-only PKCE return.
@objc(MatchgoerAuthPlugin)
public class MatchgoerAuthPlugin: CAPPlugin, CAPBridgedPlugin, ASWebAuthenticationPresentationContextProviding, ASAuthorizationControllerDelegate, ASAuthorizationControllerPresentationContextProviding {
    public let identifier = "MatchgoerAuthPlugin"
    public let jsName = "MatchgoerAuth"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "signInWithApple", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "authenticate", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "getPendingReturn", returnType: CAPPluginReturnPromise)
    ]
    private var appleCall: CAPPluginCall?
    private var appleNonce: String?
    private var appleController: ASAuthorizationController?
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
    @objc func signInWithApple(_ call: CAPPluginCall) {
        DispatchQueue.main.async {
            guard self.appleCall == nil, self.session == nil,
                  let window = self.bridge?.viewController?.view.window else {
                call.reject("Authentication is not ready", "NOT_READY"); return
            }
            var bytes = [UInt8](repeating: 0, count: 32)
            guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else {
                call.reject("Secure authentication could not start", "AUTH_FAILED"); return
            }
            let nonce = bytes.map { String(format: "%02x", $0) }.joined()
            let request = ASAuthorizationAppleIDProvider().createRequest()
            request.requestedScopes = [.email]
            request.nonce = SHA256.hash(data: Data(nonce.utf8)).map { String(format: "%02x", $0) }.joined()
            self.anchor = window; self.appleCall = call; self.appleNonce = nonce
            let controller = ASAuthorizationController(authorizationRequests: [request])
            controller.delegate = self; controller.presentationContextProvider = self
            self.appleController = controller; controller.performRequests()
        }
    }
    public func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        return anchor ?? ASPresentationAnchor()
    }
    public func authorizationController(controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization) {
        defer { appleCall = nil; appleNonce = nil; appleController = nil }
        guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
              let tokenData = credential.identityToken,
              let token = String(data: tokenData, encoding: .utf8), let nonce = appleNonce else {
            appleCall?.reject("Apple authentication did not return safely", "AUTH_FAILED"); return
        }
        appleCall?.resolve(["identityToken": token, "nonce": nonce, "authorizationCode": credential.authorizationCode.flatMap { String(data: $0, encoding: .utf8) } ?? ""])
    }
    public func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        let cancelled = (error as? ASAuthorizationError)?.code == .canceled
        appleCall?.reject(cancelled ? "Authentication cancelled" : "Apple authentication failed", cancelled ? "USER_CANCELLED" : "AUTH_FAILED")
        appleCall = nil; appleNonce = nil; appleController = nil
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
            guard self.session == nil, self.appleCall == nil, let window = self.bridge?.viewController?.view.window else {
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
