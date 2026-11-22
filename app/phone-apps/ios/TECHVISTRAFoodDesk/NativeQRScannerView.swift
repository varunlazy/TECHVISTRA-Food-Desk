import SwiftUI
import UIKit
import AVFoundation

struct NativeQRScannerView: View {
    let onScan: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            CameraCaptureView(onScan: onScan)
                .ignoresSafeArea()
            VStack {
                HStack {
                    Button { dismiss() } label: {
                        Label("Close", systemImage: "xmark.circle.fill")
                            .padding(11).background(.thinMaterial, in: Capsule())
                    }
                    .tint(.primary)
                    Spacer()
                    Text("LIVE QR SCANNER")
                        .font(.caption.weight(.black))
                        .foregroundStyle(.white)
                    Spacer()
                }.padding(16)
                Spacer()
                Image(systemName: "viewfinder")
                    .resizable().scaledToFit().frame(width: 225, height: 225)
                    .foregroundStyle(.white.opacity(0.85))
                    .shadow(radius: 10)
                Spacer()
                Text("Point the camera at a student's food QR")
                    .font(.subheadline.bold())
                    .foregroundStyle(.white)
                    .padding(15)
                    .background(.black.opacity(0.65), in: Capsule())
                    .padding(.bottom, 32)
            }
        }
        .preferredColorScheme(.dark)
    }
}

struct CameraCaptureView: UIViewControllerRepresentable {
    let onScan: (String) -> Void
    func makeUIViewController(context: Context) -> QRScannerController {
        QRScannerController(onScan: onScan)
    }
    func updateUIViewController(_ controller: QRScannerController, context: Context) { }
    static func dismantleUIViewController(_ controller: QRScannerController, coordinator: ()) {
        controller.shutdown()
    }
}

final class QRPreviewView: UIView {
    override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
    var previewLayer: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }
}

final class QRScannerController: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    private let onScan: (String) -> Void
    private let session = AVCaptureSession()
    private let sessionQueue = DispatchQueue(label: "org.techvistra.qrCamera")
    private var scanned = false

    init(onScan: @escaping (String) -> Void) {
        self.onScan = onScan
        super.init(nibName: nil, bundle: nil)
    }
    required init?(coder: NSCoder) { fatalError("Use init(onScan:)") }

    override func loadView() {
        let preview = QRPreviewView()
        preview.previewLayer.session = session
        preview.previewLayer.videoGravity = .resizeAspectFill
        view = preview
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            startCamera()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                if granted { self?.startCamera() }
                else { DispatchQueue.main.async { self?.showCameraError("Allow camera access in iPhone Settings to scan food QR codes.") } }
            }
        default:
            showCameraError("Camera permission denied. Enable Camera for TECHVISTRA Food Desk in Settings.")
        }
    }

    private func startCamera() {
        sessionQueue.async { [weak self] in
            guard let self else { return }
            guard let camera = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
                  let input = try? AVCaptureDeviceInput(device: camera) else {
                DispatchQueue.main.async { self.showCameraError("The back camera is unavailable.") }
                return
            }
            self.session.beginConfiguration()
            self.session.sessionPreset = .high
            guard self.session.canAddInput(input) else {
                self.session.commitConfiguration()
                DispatchQueue.main.async { self.showCameraError("Camera input could not start.") }
                return
            }
            self.session.addInput(input)
            let output = AVCaptureMetadataOutput()
            guard self.session.canAddOutput(output) else {
                self.session.commitConfiguration()
                DispatchQueue.main.async { self.showCameraError("QR reading could not start.") }
                return
            }
            self.session.addOutput(output)
            output.setMetadataObjectsDelegate(self, queue: .main)
            if output.availableMetadataObjectTypes.contains(.qr) { output.metadataObjectTypes = [.qr] }
            self.session.commitConfiguration()
            self.session.startRunning()
        }
    }

    func metadataOutput(_ output: AVCaptureMetadataOutput,
                        didOutput metadataObjects: [AVMetadataObject],
                        from connection: AVCaptureConnection) {
        guard !scanned else { return }
        guard let value = metadataObjects.compactMap({ $0 as? AVMetadataMachineReadableCodeObject })
            .first(where: { $0.type == .qr })?.stringValue,
              !value.isEmpty else { return }
        scanned = true
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        onScan(value)
    }

    private func showCameraError(_ message: String) {
        let alert = UIAlertController(title: "Camera not available", message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default))
        present(alert, animated: true)
    }

    func shutdown() {
        sessionQueue.async { [weak self] in
            guard let self, self.session.isRunning else { return }
            self.session.stopRunning()
        }
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        shutdown()
    }
}
