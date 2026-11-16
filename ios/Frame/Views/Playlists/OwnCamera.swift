import AVFoundation
import CoreMotion
import ImageIO
import PhotosUI
import SwiftUI
import UIKit

/// What the camera gives the steps after it: the first photograph, the two
/// taken a little from each side (the scan of three, for the glare), and
/// the LiDAR's depth for the size (Mateusz 2026-11-16 chose "Wymiar + skan
/// z 3 zdjęć + 48 MP").
struct OwnShots {
    var first: UIImage
    var sides: [UIImage] = []
    var depth: OwnDepth? = nil
    /// The photographs' own files, the first's and then the sides': every
    /// pixel as the camera wrote them (48 MP), which is what the server is
    /// sent (Mateusz 2026-11-16: "zdecydowanie wyższą jakość niż 4000px").
    /// The pictures above are small copies for the screen. Empty for the
    /// demo's photographs.
    var files: [Data] = []

    /// The file of the `index`-th photograph (0, the first), if it has one.
    func file(_ index: Int) -> Data? {
        files.count == sides.count + 1 && files.indices.contains(index) ? files[index] : nil
    }
}

/// "Dodaj własne dzieło" opening straight on the camera (Mateusz
/// 2026-11-15: "Po wybraniu „Dodaj własne dzieło” najlepiej byłoby od
/// razu pokazać aparat ale z dodatkową krótką instrukcją"): the picture
/// as it will be taken (3 : 4, nothing cut off), corner marks to put the
/// work between, one line of advice, the shutter, and Photos beside it.
/// After the first photograph, two more from a little to the left and to
/// the right: a dot to bring into a ring, each taken by itself once it is
/// there. The simulator has no camera: the demo shows its wall photograph.
struct OwnCamera: View {
    /// Leaves the steps (the back arrow at the top left).
    let close: () -> Void
    /// The photographs taken, or the one picked.
    let took: (OwnShots) -> Void
    /// The server is looking at the photograph: it stays, frozen, under a word.
    var finding: UIImage? = nil
    var findingText = "Szukam dzieła na zdjęciu…"

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
    /// The scan of three under way: the first photograph taken, the sides to come.
    @State private var scan: OwnShots?
    @State private var guide = OwnScanGuide()
    /// Since when the dot has been still in the ring.
    @State private var inRingSince: Date?

    private var demo: UIImage? { access == .ready ? nil : (model.demoMode ? DemoOwn.photo() : nil) }

    /// Which photograph of the three is next (1: the first).
    private var number: Int { scan.map { $0.sides.count + 2 } ?? 1 }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            VStack(spacing: 0) {
                top
                Spacer(minLength: 12)
                viewfinder
                caption
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
                guard let data = try? await item.loadTransferable(type: Data.self),
                      let image = OwnPicture.shown(data) ?? UIImage(data: data)
                else {
                    model.notices.warn("Nie udało się wczytać zdjęcia")
                    return
                }
                // As it is in Photos when the server reads such files, else drawn anew.
                took(OwnShots(first: image, files: OwnPicture.sendable(data) ? [data] : []))
            }
        }
        .onChange(of: guide.turned) { _, _ in watchRing() }
        .sensoryFeedback(.impact(weight: .medium), trigger: inRing) { _, now in now }
        .task {
            // Screenshots of the later steps take the demo's photograph at once.
            guard !["own-cut", "own-describe", "own-card"].contains(LaunchRoute.screen) else { return }
            camera.turned = { angle in
                withAnimation(.easeInOut(duration: 0.3)) { tilt = OwnCameraSession.tilt(angle) }
            }
            access = await camera.start()
            if LaunchRoute.screen == "own-scan", access != .ready, let demo {
                // CI screenshot: the second photograph on its way, the dot halfway to the ring.
                scan = OwnShots(first: demo)
                guide.turned = -0.55 * OwnScanGuide.step
            }
        }
        .onDisappear {
            camera.stop()
            guide.stop()
        }
    }

    private var top: some View {
        HStack {
            Button(action: scan == nil ? close : startAgain) {
                Image(systemName: "chevron.backward")
                    .font(.body.weight(.semibold))
                    .frame(width: 44, height: 44)
            }
            .buttonStyle(.glass)
            .buttonBorderShape(.circle)
            .accessibilityLabel(scan == nil ? "Zamknij" : "Od nowa")
            Spacer()
            if scan != nil, finding == nil {
                Text("Zdjęcie \(number) z 3")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .glassEffect()
                Spacer()
                // Enough: the photographs taken so far.
                Button("Pomiń") { finish() }
                    .buttonStyle(.glass)
                    .disabled(shooting)
            }
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
                .opacity(finding == nil && scan == nil ? 1 : 0)
            if scan != nil, finding == nil { ring }
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

    // MARK: The scan of three

    /// Where the phone should turn to for the next side photograph: a step
    /// to the left first (the phone turns right to keep the work in view),
    /// then past the middle to the right.
    private var target: Double { number == 2 ? -OwnScanGuide.step : OwnScanGuide.step }

    private var inRing: Bool {
        scan != nil && abs(guide.turned - target) < OwnScanGuide.near
    }

    /// The ring where the dot should go, the dot as the phone turns, an arrow between.
    private var ring: some View {
        GeometryReader { geo in
            let mid = geo.size.width / 2, reach = geo.size.width * 0.32, y = geo.size.height / 2
            let ringX = mid + reach * (target > 0 ? 1 : -1)
            let dotX = mid + reach * max(-1.5, min(1.5, guide.turned / OwnScanGuide.step))
            Circle()
                .stroke(.white, lineWidth: 3)
                .background(Circle().fill(.white.opacity(inRing ? 0.35 : 0)))
                .frame(width: 58, height: 58)
                .position(x: ringX, y: y)
            if !inRing, abs(ringX - dotX) > 70 {
                Image(systemName: ringX < dotX ? "arrow.left" : "arrow.right")
                    .font(.title3.weight(.bold))
                    .foregroundStyle(.white)
                    .shadow(color: .black.opacity(0.5), radius: 3)
                    .position(x: (ringX + dotX) / 2, y: y)
            }
            Circle()
                .fill(.white)
                .frame(width: 22, height: 22)
                .shadow(color: .black.opacity(0.4), radius: 3)
                .position(x: dotX, y: y)
        }
        .animation(.interactiveSpring, value: guide.turned)
    }

    @ViewBuilder
    private var caption: some View {
        if finding != nil {
            line(findingText)
        } else if scan != nil {
            VStack(spacing: 4) {
                line(number == 2
                    ? "Zrób krok w lewo, celując w dzieło, aż kropka wejdzie w kółko"
                    : "Teraz w prawo, za środek, aż kropka wejdzie w kółko")
                Text("Zdjęcie zrobi się samo. Z trzech usunę odblaski.")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.55))
            }
        } else {
            line("Umieść całe dzieło w kadrze")
        }
    }

    private func line(_ text: String) -> some View {
        Text(text)
            .font(.subheadline.weight(.medium))
            .foregroundStyle(.white.opacity(0.85))
            .multilineTextAlignment(.center)
    }

    /// The dot still in the ring a moment: the photograph is taken.
    private func watchRing() {
        guard scan != nil, !shooting, finding == nil else { return }
        guard inRing, guide.steady else {
            inRingSince = nil
            return
        }
        guard let since = inRingSince else {
            inRingSince = .now
            return
        }
        if Date.now.timeIntervalSince(since) > 0.35 { shoot() }
    }

    private func startAgain() {
        guide.stop()
        withAnimation(.easeInOut(duration: 0.25)) { scan = nil }
    }

    /// The photographs taken so far go on.
    private func finish() {
        guard let done = scan else { return }
        guide.stop()
        took(done)
    }

    // MARK: The shutter

    private var bottom: some View {
        HStack {
            if let scan {
                thumbs(scan)
            } else {
                Button { library = true } label: {
                    Image(systemName: "photo.on.rectangle")
                        .font(.title3)
                        .rotationEffect(.degrees(tilt))
                        .frame(width: 52, height: 52)
                }
                .buttonStyle(.glass)
                .buttonBorderShape(.circle)
                .accessibilityLabel("Wybierz ze Zdjęć")
            }
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

    /// The three photographs: the ones taken, the next one marked.
    private func thumbs(_ scan: OwnShots) -> some View {
        let taken = [scan.first] + scan.sides
        return HStack(spacing: 4) {
            ForEach(0 ..< 3, id: \.self) { index in
                ZStack {
                    if index < taken.count {
                        Image(uiImage: taken[index]).resizable().scaledToFill()
                    } else {
                        RoundedRectangle(cornerRadius: 5, style: .continuous)
                            .strokeBorder(.white.opacity(index == taken.count ? 0.9 : 0.35), style: StrokeStyle(lineWidth: 1.5, dash: [4, 3]))
                    }
                }
                .frame(width: 22, height: 30)
                .clipShape(RoundedRectangle(cornerRadius: 5, style: .continuous))
            }
        }
        .frame(width: 74, height: 52, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Zrobione \(taken.count) z 3")
    }

    private func shoot() {
        guard !shooting else { return }
        if access != .ready {
            guard let demo else {
                library = true
                return
            }
            if var shots = scan {
                shots.sides.append(demo)
                if shots.sides.count >= 2 { took(shots) } else { scan = shots }
            } else {
                took(OwnShots(first: demo))
            }
            return
        }
        shooting = true
        inRingSince = nil
        withAnimation(.easeOut(duration: 0.08)) { flash = true }
        Task {
            try? await Task.sleep(for: .milliseconds(90))
            withAnimation(.easeIn(duration: 0.2)) { flash = false }
        }
        if var shots = scan {
            camera.shoot { image, file, _ in
                shooting = false
                guard let image else {
                    model.notices.warn("Nie udało się zrobić zdjęcia")
                    return
                }
                shots.sides.append(image)
                if let file { shots.files.append(file) }
                if shots.sides.count >= 2 {
                    scan = shots
                    finish()
                } else {
                    withAnimation(.easeInOut(duration: 0.25)) { scan = shots }
                }
            }
            return
        }
        camera.shootFirst { image, file, depth in
            shooting = false
            guard let image else {
                model.notices.warn("Nie udało się zrobić zdjęcia")
                return
            }
            let first = OwnShots(first: image, depth: depth, files: file.map { [$0] } ?? [])
            // Without the motion sensors there is no dot to follow: one photograph.
            guard guide.available else {
                took(first)
                return
            }
            guide.start()
            withAnimation(.easeInOut(duration: 0.25)) { scan = first }
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

/// How far the phone has turned about the upright since the first
/// photograph of the three (gyroscope, about the gravity's line, so held
/// upright or on its side alike). Walking a step to the left while aiming
/// at the work turns it to the right: the angle between the two views.
@Observable
final class OwnScanGuide {
    /// About ten degrees: some 20 cm to the side a metre from the work,
    /// enough for a lamp's reflection to move off the place it hid.
    static let step = 10.0 * .pi / 180
    /// Near enough the ring.
    static let near = 3.0 * .pi / 180

    /// Radians to the left (negative: to the right).
    var turned = 0.0
    /// Not turning just now (the photograph will not blur).
    var steady = false

    /// One for the app, as Apple asks (the view's state is made anew often).
    private static let motion = CMMotionManager()
    @ObservationIgnored private var last: TimeInterval?
    private var motion: CMMotionManager { Self.motion }

    var available: Bool { motion.isDeviceMotionAvailable }

    func start() {
        turned = 0
        last = nil
        guard available else { return }
        motion.stopDeviceMotionUpdates()
        motion.deviceMotionUpdateInterval = 1.0 / 60
        motion.startDeviceMotionUpdates(to: .main) { [weak self] data, _ in
            guard let self, let data else { return }
            let g = data.gravity, r = data.rotationRate
            let length = (g.x * g.x + g.y * g.y + g.z * g.z).squareRoot()
            guard length > 0.5 else { return }
            // About the upright (against gravity), positive to the left.
            let rate = -(r.x * g.x + r.y * g.y + r.z * g.z) / length
            if let last { turned += rate * (data.timestamp - last) }
            last = data.timestamp
            steady = (r.x * r.x + r.y * r.y + r.z * r.z).squareRoot() < 0.25
        }
    }

    func stop() {
        motion.stopDeviceMotionUpdates()
    }
}

/// The back camera, for photographs (`AVCapturePhotoOutput`) at the most
/// pixels it has (48 MP on recent iPhones), upright as the phone is held:
/// on its side for a wide work, a wide photograph. On an iPhone Pro the
/// first photograph comes with the LiDAR's depth, for the work's size; when
/// the LiDAR's photographs have fewer pixels, it is taken once more at once
/// with the sharper camera, which takes the rest.
final class OwnCameraSession: NSObject, AVCapturePhotoCaptureDelegate, @unchecked Sendable {
    enum Access { case none, ready, denied }

    let session = AVCaptureSession()
    private let output = AVCapturePhotoOutput()
    private let queue = DispatchQueue(label: "own-camera")
    /// The photograph being taken, on the camera's queue.
    private var pending: ((AVCapturePhoto?) -> Void)?
    /// How the phone is held, by the horizon (also lying flat over a work
    /// on the table: the last way it was held).
    private var rotation: AVCaptureDevice.RotationCoordinator?
    private var watching: NSKeyValueObservation?
    /// The photograph's turn changed (on the main thread).
    var turned: ((CGFloat) -> Void)?
    /// The LiDAR camera (iPhone Pro), for the depth; nil without one.
    private var lidar: AVCaptureDevice?
    /// The camera with more pixels than the LiDAR's photographs, taking all
    /// but the depth; nil when the LiDAR's are as sharp (or there is none).
    private var sharper: AVCaptureDevice?
    private var current: AVCaptureDevice?

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
        let lidar = AVCaptureDevice.default(.builtInLiDARDepthCamera, for: .video, position: .back)
        let wide = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back)
        guard let first = lidar ?? wide else { return .none }
        await MainActor.run { follow(first) }
        return await withCheckedContinuation { (done: CheckedContinuation<Access, Never>) in
            queue.async { [self] in
                if current == nil {
                    self.lidar = lidar
                    use(first, depth: lidar != nil)
                    if let lidar, let wide, lidar == current,
                       Self.pixels(Self.sharpest(wide)?.size) > Self.pixels(output.maxPhotoDimensions) * 3 / 2 {
                        sharper = wide
                    }
                }
                if !session.isRunning { session.startRunning() }
                done.resume(returning: session.isRunning ? .ready : .none)
            }
        }
    }

    /// The camera in the session, at its most pixels; with the depth when asked and it can.
    private func use(_ device: AVCaptureDevice, depth: Bool) {
        guard let input = try? AVCaptureDeviceInput(device: device) else { return }
        session.beginConfiguration()
        defer { session.commitConfiguration() }
        session.inputs.forEach { session.removeInput($0) }
        session.sessionPreset = .photo
        guard session.canAddInput(input) else { return }
        session.addInput(input)
        if session.outputs.isEmpty, session.canAddOutput(output) { session.addOutput(output) }
        // The photo preset may give a format with fewer pixels than the camera has.
        if let best = Self.sharpest(device, depth: depth),
           Self.pixels(best.size) > Self.pixels(Self.largest(device.activeFormat)),
           (try? device.lockForConfiguration()) != nil {
            device.activeFormat = best.format
            device.unlockForConfiguration()
        }
        if let largest = Self.largest(device.activeFormat) { output.maxPhotoDimensions = largest }
        output.maxPhotoQualityPrioritization = .quality
        output.isDepthDataDeliveryEnabled = depth && output.isDepthDataDeliverySupported
        current = device
    }

    private static func pixels(_ size: CMVideoDimensions?) -> Int {
        size.map { Int($0.width) * Int($0.height) } ?? 0
    }

    private static func largest(_ format: AVCaptureDevice.Format) -> CMVideoDimensions? {
        format.supportedMaxPhotoDimensions.max { pixels($0) < pixels($1) }
    }

    /// The camera's 4 : 3 format with the most photograph pixels (with
    /// depth, when asked); of those, the one with the most video pixels.
    private static func sharpest(_ device: AVCaptureDevice, depth: Bool = false) -> (format: AVCaptureDevice.Format, size: CMVideoDimensions)? {
        var found: (format: AVCaptureDevice.Format, size: CMVideoDimensions, video: Int)?
        for format in device.formats {
            if depth, format.supportedDepthDataFormats.isEmpty { continue }
            let video = CMVideoFormatDescriptionGetDimensions(format.formatDescription)
            guard video.height > 0, abs(Double(video.width) / Double(video.height) - 4.0 / 3.0) < 0.01,
                  let size = largest(format)
            else { continue }
            let better = found.map { pixels(size) > pixels($0.size) || (pixels(size) == pixels($0.size) && pixels(video) > $0.video) } ?? true
            if better { found = (format, size, pixels(video)) }
        }
        return found.map { ($0.format, $0.size) }
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

    /// The first photograph, with the depth when there is a LiDAR (and,
    /// when the LiDAR's photographs have fewer pixels, the same view again
    /// at once with the sharper camera).
    func shootFirst(_ took: @escaping (UIImage?, Data?, OwnDepth?) -> Void) {
        let angle = rotation?.videoRotationAngleForHorizonLevelCapture ?? 90
        queue.async { [self] in
            let measuring = lidar != nil && current == lidar && output.isDepthDataDeliveryEnabled
            let view = current?.activeFormat.videoFieldOfView
            capture(angle, depth: measuring) { [self] photo in
                let file = photo?.fileDataRepresentation()
                let image = file.flatMap(Self.picture)
                let depth = photo.flatMap { Self.depth(of: $0, angle: angle, fieldOfView: view, image: image) }
                guard let sharper, image != nil else {
                    DispatchQueue.main.async { took(image, file, depth) }
                    return
                }
                use(sharper, depth: false)
                // A moment for the new camera's focus and light.
                queue.asyncAfter(deadline: .now() + 0.7) { [self] in
                    capture(angle, depth: false) { again in
                        let sharpFile = again?.fileDataRepresentation()
                        if let sharpFile, let sharp = Self.picture(sharpFile) {
                            DispatchQueue.main.async { took(sharp, sharpFile, depth) }
                        } else {
                            DispatchQueue.main.async { took(image, file, depth) }
                        }
                    }
                }
            }
        }
    }

    /// The photograph for the screen: upright, far smaller than its file.
    private static func picture(_ file: Data) -> UIImage? {
        OwnPicture.shown(file) ?? UIImage(data: file)
    }

    /// A photograph, upright as the phone is held: tall held upright,
    /// wide held on its side.
    func shoot(_ took: @escaping (UIImage?, Data?, OwnDepth?) -> Void) {
        let angle = rotation?.videoRotationAngleForHorizonLevelCapture ?? 90
        queue.async { [self] in
            capture(angle, depth: false) { photo in
                let file = photo?.fileDataRepresentation()
                let image = file.flatMap(Self.picture)
                DispatchQueue.main.async { took(image, file, nil) }
            }
        }
    }

    /// On the camera's queue.
    private func capture(_ angle: CGFloat, depth: Bool, _ done: @escaping (AVCapturePhoto?) -> Void) {
        pending = done
        if let connection = output.connection(with: .video), connection.isVideoRotationAngleSupported(angle) {
            connection.videoRotationAngle = angle
        }
        let settings = AVCapturePhotoSettings()
        settings.photoQualityPrioritization = .quality
        settings.maxPhotoDimensions = output.maxPhotoDimensions
        if depth, output.isDepthDataDeliveryEnabled {
            settings.isDepthDataDeliveryEnabled = true
            settings.isDepthDataFiltered = true
            settings.embedsDepthDataInPhoto = false
        }
        output.capturePhoto(with: settings, delegate: self)
    }

    func photoOutput(_ output: AVCapturePhotoOutput, didFinishProcessingPhoto photo: AVCapturePhoto, error: Error?) {
        queue.async { [self] in
            let done = pending
            pending = nil
            done?(error == nil ? photo : nil)
        }
    }

    /// The LiDAR's depth of the photograph, with its lens and turn.
    private static func depth(of photo: AVCapturePhoto, angle: CGFloat, fieldOfView: Float?, image: UIImage?) -> OwnDepth? {
        guard var data = photo.depthData else { return nil }
        if data.depthDataType != kCVPixelFormatType_DepthFloat32 {
            data = data.converting(toDepthDataType: kCVPixelFormatType_DepthFloat32)
        }
        let map = data.depthDataMap
        CVPixelBufferLockBaseAddress(map, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(map, .readOnly) }
        let width = CVPixelBufferGetWidth(map), height = CVPixelBufferGetHeight(map)
        let row = CVPixelBufferGetBytesPerRow(map)
        guard width > 0, height > 0, let base = CVPixelBufferGetBaseAddress(map) else { return nil }
        var values = [Float](repeating: 0, count: width * height)
        for y in 0 ..< height {
            let line = base.advanced(by: y * row).assumingMemoryBound(to: Float32.self)
            for x in 0 ..< width { values[y * width + x] = line[x] }
        }

        let fx, fy, cx, cy: Double
        if let calibration = data.cameraCalibrationData {
            let m = calibration.intrinsicMatrix
            let reference = calibration.intrinsicMatrixReferenceDimensions
            guard reference.width > 0, reference.height > 0 else { return nil }
            let sx = Double(width) / Double(reference.width), sy = Double(height) / Double(reference.height)
            fx = Double(m.columns.0.x) * sx
            fy = Double(m.columns.1.y) * sy
            cx = Double(m.columns.2.x) * sx
            cy = Double(m.columns.2.y) * sy
        } else if let fieldOfView, fieldOfView > 1 {
            // The lens from the format's field of view, across the sensor's long side.
            fx = Double(width) / 2 / tan(Double(fieldOfView) * .pi / 360)
            fy = fx
            cx = Double(width) / 2
            cy = Double(height) / 2
        } else {
            return nil
        }

        // The photograph's own turn; if it was turned in its pixels (no
        // turn in its metadata, but standing otherwise than the map), the
        // capture's.
        let written = (photo.metadata[kCGImagePropertyOrientation as String] as? NSNumber)
            .flatMap { CGImagePropertyOrientation(rawValue: $0.uint32Value) } ?? .up
        var orientation = written
        if written == .up, let image, (image.size.width > image.size.height) != (width > height) {
            orientation = Self.orientation(angle)
        }
        return OwnDepth(width: width, height: height, values: values, fx: fx, fy: fy, cx: cx, cy: cy, orientation: orientation)
    }

    /// The capture's turn as the photograph's metadata says it.
    static func orientation(_ angle: CGFloat) -> CGImagePropertyOrientation {
        switch (Int(angle.rounded()) % 360 + 360) % 360 {
        case 90: .right
        case 180: .down
        case 270: .left
        default: .up
        }
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
