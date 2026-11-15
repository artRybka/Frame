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

    private var demo: UIImage? { access == .ready ? nil : (model.demoMode ? DemoOwn.photo() : nil) }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            VStack(spacing: 0) {
                top
                Spacer(minLength: 12)
                viewfinder
                Spacer(minLength: 12)
                bottom
            }
        }
        .preferredColorScheme(.dark)
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
        .task { access = await camera.start() }
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
                Image(uiImage: finding).resizable().scaledToFill()
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
            VStack {
                Text(finding == nil ? "Całe dzieło z kawałkiem ściany, na wprost, bez lampy" : "Szukam dzieła na zdjęciu…")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.white)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .glassEffect(.regular, in: .capsule)
                    .padding(.top, 14)
                    .padding(.horizontal, 20)
                Spacer()
                if finding != nil {
                    ProgressView().tint(.white).controlSize(.large).padding(.bottom, 40)
                }
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

/// The back camera, for photographs (`AVCapturePhotoOutput`).
final class OwnCameraSession: NSObject, AVCapturePhotoCaptureDelegate, @unchecked Sendable {
    enum Access { case none, ready, denied }

    let session = AVCaptureSession()
    private let output = AVCapturePhotoOutput()
    private let queue = DispatchQueue(label: "own-camera")
    private var took: ((UIImage?) -> Void)?

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

    func stop() {
        queue.async { [session] in
            if session.isRunning { session.stopRunning() }
        }
    }

    /// A photograph, upright as the phone is held (portrait).
    func shoot(_ took: @escaping (UIImage?) -> Void) {
        queue.async { [self] in
            self.took = took
            if let connection = output.connection(with: .video), connection.isVideoRotationAngleSupported(90) {
                connection.videoRotationAngle = 90
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
