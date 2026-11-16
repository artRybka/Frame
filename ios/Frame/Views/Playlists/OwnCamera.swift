import AVFoundation
import PhotosUI
import SwiftUI
import UIKit

/// "Dodaj własne dzieło" opening straight on the camera (Mateusz
/// 2026-11-15: "Po wybraniu „Dodaj własne dzieło” najlepiej byłoby od
/// razu pokazać aparat ale z dodatkową krótką instrukcją"): the picture
/// as it will be taken (3 : 4, nothing cut off), corner marks to put the
/// work between, one line of advice, the shutter, and Photos beside it.
/// The simulator has no camera: the demo shows its wall photograph.
struct OwnCamera: View {
    /// Leaves the steps (the back arrow at the top left).
    let close: () -> Void
    /// The photograph taken or picked.
    let took: (UIImage) -> Void
    /// The server is looking at the photograph: it stays, frozen, under a word.
    var finding: UIImage? = nil

    @Environment(AppModel.self) private var model
    @State private var camera = OwnCameraSession()
    @State private var access = OwnCameraSession.Access.none
    @State private var shooting = false
    @State private var library = false
    @State private var picked: PhotosPickerItem?
    @State private var flash = false
    /// How far the buttons' icons turn to stay upright: the screen stays
    /// upright (the app is portrait), the phone may be held sideways for a
    /// wide work (Mateusz 2026-11-16: "działa tylko w pionie").
    @State private var tilt: Double = 0

    private var demo: UIImage? { access == .ready ? nil : (model.demoMode ? DemoOwn.photo() : nil) }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            VStack(spacing: 0) {
                top
                Spacer(minLength: 12)
                viewfinder
                Text(finding == nil ? "Umieść całe dzieło w kadrze" : "Szukam dzieła na zdjęciu…")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.white.opacity(0.85))
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, Theme.gutter)
                    .padding(.top, 14)
                Spacer(minLength: 12)
                bottom
            }
        }
        .environment(\.colorScheme, .dark)  // the camera's own, the steps after it keep his
        .photosPicker(isPresented: $library, selection: $picked, matching: .images)
        .onChange(of: picked) { _, item in
            guard let item else { return }
            picked = nil
            Task {
                guard let data = try? await item.loadTransferable(type: Data.self), let image = UIImage(data: data) else {
                    model.notices.warn("Nie udało się wczytać zdjęcia")
                    return
                }
                took(image)
            }
        }
        .task {
            // Screenshots of the later steps take the demo's photograph at once.
            guard !["own-cut", "own-describe", "own-card"].contains(LaunchRoute.screen) else { return }
            camera.turned = { angle in
                withAnimation(.easeInOut(duration: 0.3)) { tilt = OwnCameraSession.tilt(angle) }
            }
            access = await camera.start()
        }
        .onDisappear { camera.stop() }
    }

    private var top: some View {
        HStack {
            Button(action: close) {
                Image(systemName: "chevron.backward")
                    .font(.body.weight(.semibold))
                    .frame(width: 44, height: 44)
            }
            .buttonStyle(.glass)
            .buttonBorderShape(.circle)
            .accessibilityLabel("Zamknij")
            Spacer()
        }
        .padding(.horizontal, Theme.gutter)
        .padding(.top, 4)
    }

    /// The picture as it will be taken, the marks over it, the advice on it.
    private var viewfinder: some View {
        ZStack {
            if let finding {
                // A wide photograph (the phone held on its side) whole, not cut to the tall frame.
                Image(uiImage: finding).resizable()
                    .aspectRatio(contentMode: finding.size.width > finding.size.height ? .fit : .fill)
            } else if access == .ready {
                OwnCameraPreview(session: camera.session)
            } else if let demo {
                Image(uiImage: demo).resizable().scaledToFill()
            } else {
                Color(white: 0.08)
                if access == .denied {
                    VStack(spacing: 10) {
                        Text("Aplikacja nie ma dostępu do aparatu.")
                            .font(.subheadline)
                            .foregroundStyle(.white)
                        Button("Otwórz Ustawienia") {
                            if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
                        }
                        .buttonStyle(.glass)
                    }
                    .padding(24)
                }
            }
            CornerMarks()
                .stroke(.white.opacity(0.9), style: StrokeStyle(lineWidth: 3, lineCap: .round))
                .padding(28)
                .opacity(finding == nil ? 1 : 0)
            if finding != nil {
                ProgressView().tint(.white).controlSize(.large)
            }
            if flash { Color.white.transition(.opacity) }
        }
        .aspectRatio(3 / 4, contentMode: .fit)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .padding(.horizontal, 8)
        .animation(.easeOut(duration: 0.25), value: finding == nil)
    }

    private var bottom: some View {
        HStack {
            Button { library = true } label: {
                Image(systemName: "photo.on.rectangle")
                    .font(.title3)
                    .rotationEffect(.degrees(tilt))
                    .frame(width: 52, height: 52)
            }
            .buttonStyle(.glass)
            .buttonBorderShape(.circle)
            .accessibilityLabel("Wybierz ze Zdjęć")
            Spacer()
            Button(action: shoot) {
                ZStack {
                    Circle().strokeBorder(.white, lineWidth: 4).frame(width: 78, height: 78)
                    Circle().fill(.white).frame(width: 64, height: 64)
                }
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Zrób zdjęcie")
            Spacer()
            Color.clear.frame(width: 52, height: 52)
        }
        .disabled(shooting || finding != nil)
        .opacity(finding == nil ? 1 : 0.4)
        .padding(.horizontal, 32)
        .padding(.bottom, 12)
    }

    private func shoot() {
        if access != .ready {
            if let demo { took(demo) } else { library = true }
            return
        }
        shooting = true
        withAnimation(.easeOut(duration: 0.08)) { flash = true }
        Task {
            try? await Task.sleep(for: .milliseconds(90))
            withAnimation(.easeIn(duration: 0.2)) { flash = false }
        }
        camera.shoot { image in
            shooting = false
            if let image { took(image) } else { model.notices.warn("Nie udało się zrobić zdjęcia") }
        }
    }
}

/// Four corners to put the work between.
private struct CornerMarks: Shape {
    func path(in rect: CGRect) -> Path {
        let arm = min(rect.width, rect.height) * 0.09
        var path = Path()
        let corners: [(CGPoint, CGFloat, CGFloat)] = [
            (CGPoint(x: rect.minX, y: rect.minY), 1, 1), (CGPoint(x: rect.maxX, y: rect.minY), -1, 1),
            (CGPoint(x: rect.maxX, y: rect.maxY), -1, -1), (CGPoint(x: rect.minX, y: rect.maxY), 1, -1),
        ]
        for (point, dx, dy) in corners {
            path.move(to: CGPoint(x: point.x + dx * arm, y: point.y))
            path.addLine(to: point)
            path.addLine(to: CGPoint(x: point.x, y: point.y + dy * arm))
        }
        return path
    }
}

/// The back camera, for photographs (`AVCapturePhotoOutput`), upright
/// as the phone is held: on its side for a wide work, a wide photograph.
final class OwnCameraSession: NSObject, AVCapturePhotoCaptureDelegate, @unchecked Sendable {
    enum Access { case none, ready, denied }

    let session = AVCaptureSession()
    private let output = AVCapturePhotoOutput()
    private let queue = DispatchQueue(label: "own-camera")
    private var took: ((UIImage?) -> Void)?
    /// How the phone is held, by the horizon (also lying flat over a work
    /// on the table: the last way it was held).
    private var rotation: AVCaptureDevice.RotationCoordinator?
    private var watching: NSKeyValueObservation?
    /// The photograph's turn changed (on the main thread).
    var turned: ((CGFloat) -> Void)?

    /// The capture's turn as the icons' counter-turn: 90° is the phone
    /// upright, 0° on its left side (top to the left), 180° on its right.
    static func tilt(_ angle: CGFloat) -> Double {
        let turn = Double(90 - angle)
        return turn > 180 ? turn - 360 : turn < -180 ? turn + 360 : turn
    }

    func start() async -> Access {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized: break
        case .notDetermined:
            guard await AVCaptureDevice.requestAccess(for: .video) else { return .denied }
        default: return .denied
        }
        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
              let input = try? AVCaptureDeviceInput(device: device)
        else { return .none }
        await MainActor.run { follow(device) }
        return await withCheckedContinuation { (done: CheckedContinuation<Access, Never>) in
            queue.async { [self] in
                if session.inputs.isEmpty {
                    session.beginConfiguration()
                    session.sessionPreset = .photo
                    if session.canAddInput(input) { session.addInput(input) }
                    if session.canAddOutput(output) { session.addOutput(output) }
                    output.maxPhotoQualityPrioritization = .quality
                    session.commitConfiguration()
                }
                if !session.isRunning { session.startRunning() }
                done.resume(returning: session.isRunning ? .ready : .none)
            }
        }
    }

    @MainActor
    private func follow(_ device: AVCaptureDevice) {
        guard rotation == nil else { return }
        let rotation = AVCaptureDevice.RotationCoordinator(device: device, previewLayer: nil)
        self.rotation = rotation
        watching = rotation.observe(\.videoRotationAngleForHorizonLevelCapture, options: [.new]) { [weak self] coordinator, _ in
            let angle = coordinator.videoRotationAngleForHorizonLevelCapture
            DispatchQueue.main.async { self?.turned?(angle) }
        }
        turned?(rotation.videoRotationAngleForHorizonLevelCapture)
    }

    func stop() {
        queue.async { [session] in
            if session.isRunning { session.stopRunning() }
        }
    }

    /// A photograph, upright as the phone is held: tall held upright,
    /// wide held on its side.
    func shoot(_ took: @escaping (UIImage?) -> Void) {
        let angle = rotation?.videoRotationAngleForHorizonLevelCapture ?? 90
        queue.async { [self] in
            self.took = took
            if let connection = output.connection(with: .video), connection.isVideoRotationAngleSupported(angle) {
                connection.videoRotationAngle = angle
            }
            let settings = AVCapturePhotoSettings()
            settings.photoQualityPrioritization = .quality
            output.capturePhoto(with: settings, delegate: self)
        }
    }

    func photoOutput(_ output: AVCapturePhotoOutput, didFinishProcessingPhoto photo: AVCapturePhoto, error: Error?) {
        let image = photo.fileDataRepresentation().flatMap { UIImage(data: $0) }
        let took = self.took
        self.took = nil
        DispatchQueue.main.async { took?(image) }
    }
}

/// What the back camera sees, filling a 3 : 4 frame as the photograph will.
private struct OwnCameraPreview: UIViewRepresentable {
    let session: AVCaptureSession

    func makeUIView(context: Context) -> PreviewView {
        let view = PreviewView()
        view.preview.session = session
        view.preview.videoGravity = .resizeAspectFill
        return view
    }

    func updateUIView(_ view: PreviewView, context: Context) {}

    final class PreviewView: UIView {
        override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
        // swiftlint:disable:next force_cast
        var preview: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }

        override func layoutSubviews() {
            super.layoutSubviews()
            if let connection = preview.connection, connection.isVideoRotationAngleSupported(90) {
                connection.videoRotationAngle = 90
            }
        }
    }
}
