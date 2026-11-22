import SwiftUI
import AVFoundation
import WebKit

@main
struct TECHVISTRAFoodDeskApp: App {
    var body: some Scene {
        WindowGroup { FoodDeskHomeView() }
    }
}

struct FoodDeskHomeView: View {
    @State private var address = UserDefaults.standard.string(forKey: "fooddesk_laptop_url") ?? ""
    @State private var connectedURL: URL?
    @State private var errorText = ""

    var body: some View {
        Group {
            if let connectedURL {
                FoodDeskBrowserView(url: connectedURL) {
                    self.connectedURL = nil
                }
            } else {
                NavigationStack {
                    Form {
                        Section {
                            TextField("192.168.1.50", text: $address)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
                                .keyboardType(.URL)
                                .submitLabel(.go)
                                .onSubmit(connect)
                            Button("Connect to offline food desk", action: connect)
                                .fontWeight(.bold)
                        } header: {
                            Text("Event laptop address")
                        } footer: {
                            Text("Enter your laptop's local IP, e.g. 192.168.1.50. The app uses port 8787 and does not need HTTPS or internet. Do not enter localhost on a phone.")
                        }
                        Section("Staff workflow") {
                            Label("Join the same private Wi-Fi as the laptop", systemImage: "wifi")
                            Label("Sign in with your food-counter account", systemImage: "person.crop.circle")
                            Label("Tap SCAN QR WITH PHONE CAMERA", systemImage: "qrcode.viewfinder")
                            Label("Check the student, then tap Give Food", systemImage: "checkmark.shield")
                        }
                        if !errorText.isEmpty {
                            Section { Text(errorText).foregroundStyle(.red) }
                        }
                    }
                    .navigationTitle("TECHVISTRA '26")
                }
            }
        }
        .tint(.indigo)
    }

    private func connect() {
        let input = address.trimmingCharacters(in: .whitespacesAndNewlines)
        let formatted = input.contains("://") ? input : "http://\(input)"
        guard let parts = URLComponents(string: formatted),
              parts.scheme == "http" || parts.scheme == "https",
              let host = parts.host, isPrivateIPv4(host),
              parts.user == nil, parts.password == nil,
              (parts.path.isEmpty || parts.path == "/"),
              parts.query == nil, parts.fragment == nil else {
            errorText = "Enter a valid private LAN address like 192.168.1.50 (no localhost, public IP, or URL path)."
            return
        }
        let port = parts.port ?? 8787
        guard port > 0 && port < 65536,
              let url = URL(string: "\(parts.scheme!)://\(host):\(port)/") else {
            errorText = "Check the port number. The default is 8787."
            return
        }
        UserDefaults.standard.set(url.absoluteString, forKey: "fooddesk_laptop_url")
        address = url.absoluteString
        errorText = ""
        connectedURL = url
    }

    private func isPrivateIPv4(_ host: String) -> Bool {
        let parts = host.split(separator: ".")
        guard parts.count == 4 else { return false }
        let numbers = parts.compactMap { UInt8(String($0)) }
        guard numbers.count == 4 else { return false }
        let a = numbers[0], b = numbers[1]
        return a == 10 || (a == 172 && b >= 16 && b <= 31) ||
               (a == 192 && b == 168) || (a == 169 && b == 254)
    }
}

struct FoodDeskBrowserView: View {
    let url: URL
    let disconnect: () -> Void
    @StateObject private var model: FoodDeskWebModel

    init(url: URL, disconnect: @escaping () -> Void) {
        self.url = url
        self.disconnect = disconnect
        _model = StateObject(wrappedValue: FoodDeskWebModel(url: url))
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 9) {
                Image(systemName: "wifi").foregroundStyle(.green)
                Text(url.host ?? "Offline laptop")
                    .font(.caption).lineLimit(1)
                Spacer()
                Button("Change server", action: disconnect).font(.caption).fontWeight(.medium)
            }
            .padding(.horizontal, 14).padding(.vertical, 9)
            .background(Color(uiColor: .secondarySystemBackground))
            FoodDeskWebView(model: model)
                .ignoresSafeArea(edges: .bottom)
        }
        .overlay(alignment: .bottom) {
            if let errorText = model.loadError {
                VStack(spacing: 8) {
                    Text("Cannot reach the food desk").bold()
                    Text(errorText).font(.caption).multilineTextAlignment(.center)
                    Button("Retry") { model.reload() }.buttonStyle(.borderedProminent)
                    Button("Change server", action: disconnect).font(.caption)
                }
                .padding(20)
                .frame(maxWidth: .infinity)
                .background(.regularMaterial)
            }
        }
        .sheet(isPresented: $model.showScanner) {
            NativeQRScannerView { code in
                model.showScanner = false
                model.receiveQR(code)
            }
        }
    }
}

struct FoodDeskWebView: UIViewRepresentable {
    @ObservedObject var model: FoodDeskWebModel
    func makeUIView(context: Context) -> WKWebView { model.webView }
    func updateUIView(_ uiView: WKWebView, context: Context) { }
}

final class FoodDeskWebModel: NSObject, ObservableObject, WKScriptMessageHandler, WKNavigationDelegate {
    @Published var showScanner = false
    @Published var loadError: String?
    let webView: WKWebView
    let baseURL: URL

    init(url: URL) {
        baseURL = url
        let config = WKWebViewConfiguration()
        config.websiteDataStore = .default()
        let controller = WKUserContentController()
        // The browser page only sees a native scanner action; it receives a QR string
        // after AVFoundation reads the code. No browser getUserMedia() is required.
        controller.addUserScript(WKUserScript(source: "window.TECHVISTRA_NATIVE_SCANNER=true;",
                                              injectionTime: .atDocumentStart,
                                              forMainFrameOnly: true))
        config.userContentController = controller
        webView = WKWebView(frame: .zero, configuration: config)
        super.init()
        controller.add(self, name: "techvistraScanner")
        webView.navigationDelegate = self
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.load(URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData))
    }

    deinit {
        webView.configuration.userContentController.removeScriptMessageHandler(forName: "techvistraScanner")
    }

    func userContentController(_ userContentController: WKUserContentController,
                               didReceive message: WKScriptMessage) {
        guard message.name == "techvistraScanner", message.frameInfo.isMainFrame,
              let action = message.body as? String, action == "open" else { return }
        DispatchQueue.main.async { self.showScanner = true }
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let next = navigationAction.request.url else { decisionHandler(.cancel); return }
        // Prevent remote pages or redirects from receiving the native scanning bridge.
        let allowed = next.scheme == baseURL.scheme && next.host == baseURL.host &&
                      (next.port ?? 8787) == (baseURL.port ?? 8787)
        decisionHandler(allowed ? .allow : .cancel)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        loadError = nil
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!,
                 withError error: Error) {
        loadError = "Check the laptop server, Wi-Fi, and IP address. (\(error.localizedDescription))"
    }

    func reload() {
        loadError = nil
        webView.load(URLRequest(url: baseURL, cachePolicy: .reloadIgnoringLocalCacheData))
    }

    func receiveQR(_ scanned: String) {
        // JSONEncoder safely escapes QR strings before inserting them as JS args.
        guard let data = try? JSONEncoder().encode(scanned),
              let argument = String(data: data, encoding: .utf8) else { return }
        webView.evaluateJavaScript("window.techvistraReceiveNativeQR(\(argument));") { _, error in
            if let error { print("QR bridge error: \(error.localizedDescription)") }
        }
    }
}
