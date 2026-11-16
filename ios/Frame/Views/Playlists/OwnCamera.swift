import AVFoundation
import CoreMotion
import ImageIO
import PhotosUI
import SwiftUI
import UIKit
import Vision

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
/// as it will be taken (3 : 4, nothing cut off), the work's outline as the
/// camera finds it, a word of advice, and Photos beside it. The first
/// photograph is taken from the front, by itself once the work is whole
/// in the picture, large enough and still; then two more from some 30° to
/// the left and to the right, each when the work lies in the helper frame
/// drawn for it (Mateusz 2026-11-16: "pierwsze zdjęcie na wprost, a
/// kolejne pod większym kątem z ramką pomocniczą na ekranie"; no shutter,
/// "skoro zdjęcie robi się samo", but when the work's edges are not
/// found). The simulator has no camera: the demo shows its wall
/// photograph and a shutter.
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
    /// The work's outline as the camera sees it now (0–1 on the screen's
    /// picture), a little smoothed.
    @State private var outline: [CGPoint]?
    /// Since when no outline has been seen.
    @State private var lostSince: Date? = .now
    /// The outline at the first photograph, as the world stands.
    @State private var front: [CGPoint]?
    /// Since when all has been as the next photograph needs it.
    @State private var holdSince: Date?
    /// The shutter is out: the work's edges were not found for a while.
    @State private var manual = false
    /// The camera has little light.
    @State private var dim = false

    /// Without an outline for this long, he takes the photograph himself.
    private static let patience: TimeInterval = 5

    private var demo: UIImage? { access == .ready ? nil : (model.demoMode ? DemoOwn.photo() : nil) }

    /// Which photograph of the three is next (1: the first).
    private var number: Int { scan.map { min($0.sides.count + 2, 3) } ?? 1 }

    // MARK: What the camera sees

    /// How the phone is held: 0 upright, 1 its top to the left, -1 to the right.
    private var quarter: Int { tilt > 45 ? 1 : tilt < -45 ? -1 : 0 }
    /// The picture as the world stands: tall, or wide with the phone on its side.
    private var aspect: Double { quarter == 0 ? 0.75 : 4.0 / 3 }
    private var focal: Double { quarter == 0 ? camera.focal : camera.focal * 0.75 }
    /// From where the next side photograph is meant: the left first.
    private var target: Double { number == 2 ? -OwnScanView.side : OwnScanView.side }
    /// Where the phone stands by the gyroscope since the first photograph
    /// (degrees; negative: to the left of the work, aiming at it).
    private var turned: Double { guide.turned * 180 / .pi }

    /// The outline as the world stands.
    private var upright: [CGPoint]? {
        outline.map { corners in OwnScanView.ordered(corners.map { OwnScanView.upright($0, quarter: quarter) }) }
    }

    /// The work at the first photograph; a plain one in the middle when
    /// its edges were not found then.
    private var base: [CGPoint] {
        front ?? [CGPoint(x: 0.2, y: 0.25), CGPoint(x: 0.8, y: 0.25), CGPoint(x: 0.8, y: 0.75), CGPoint(x: 0.2, y: 0.75)]
    }

    private func onScreen(_ corners: [CGPoint]) -> [CGPoint] {
        corners.map { OwnScanView.shown($0, quarter: quarter) }
    }

    /// What is drawn over the picture and said under it.
    private var look: OwnScanLook {
        var look = OwnScanLook(number: number)
        look.manual = manual
        look.dim = dim
        guard scan != nil else {
            look.live = outline
            look.advice = OwnScanView.first(upright, aspect: aspect)
            return look
        }
        look.helper = onScreen(OwnScanView.seen(base, from: target, aspect: aspect, focal: focal))
        if let upright, let front, let shape = OwnScanView.shape(of: front, aspect: aspect),
           let now = OwnScanView.turn(of: upright, shape: shape, aspect: aspect, focal: focal),
           let then = OwnScanView.turn(of: front, shape: shape, aspect: aspect, focal: focal),
           let away = OwnScanView.away(upright, front: front, aspect: aspect),
           // Another rectangle on the wall is not the work: the gyroscope must agree.
           !guide.available || abs(now - then - turned) < 20 {
            look.live = outline
            look.advice = OwnScanView.side(target: target, angle: now - then, away: away, fits: OwnScanView.fits(upright))
        } else if guide.available {
            // The work's edges are not seen: where the phone has turned to.
            look.live = onScreen(OwnScanView.seen(base, from: turned, aspect: aspect, focal: focal))
            look.advice = OwnScanView.side(target: target, angle: turned)
        } else {
            look.advice = .lost
        }
        return look
    }

    /// The shutter shows: no camera (the demo), or the work is not found.
    private var byHand: Bool { manual || access != .ready }

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
        .onChange(of: guide.turned) { _, _ in
            // Between the camera's looks (and without them) the gyroscope keeps the watch.
            if scan != nil { watch() }
        }
        .sensoryFeedback(.impact(weight: .medium), trigger: look.matched) { _, now in now }
        .task {
            // Screenshots of the later steps take the demo's photograph at once.
            guard !["own-cut", "own-describe", "own-card"].contains(LaunchRoute.screen) else { return }
            camera.turned = { angle in
                withAnimation(.easeInOut(duration: 0.3)) { tilt = OwnCameraSession.tilt(angle) }
            }
            camera.seen = { found, dark in
                if dark != dim { dim = dark }
                see(found)
            }
            access = await camera.start()
            // No pictures to look for the work in: he presses the shutter.
            if access == .ready, !camera.sees { manual = true }
            guide.start()
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
            if finding == nil, access == .ready || scan != nil {
                Text("Zdjęcie \(number) z 3")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .glassEffect()
                Spacer()
                if scan != nil {
                    // Enough: the photographs taken so far.
                    Button("Pomiń") { finish() }
                        .buttonStyle(.glass)
                        .disabled(shooting)
                } else {
                    Color.clear.frame(width: 44, height: 44)
                }
            }
        }
        .padding(.horizontal, Theme.gutter)
        .padding(.top, 4)
    }

    /// The picture as it will be taken, the work's outline and the helper
    /// frame over it.
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
            if finding == nil, access == .ready {
                OwnScanOverlay(look: look)
            }
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

    @ViewBuilder
    private var caption: some View {
        if finding != nil {
            line(findingText)
        } else if access == .ready {
            OwnScanCaption(look: look)
        } else if scan != nil {
            line(number == 2 ? "Zdjęcie z lewej strony dzieła" : "Zdjęcie z prawej strony dzieła")
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

    // MARK: The watch

    /// What the camera found in its latest picture: the work's outline, or none.
    private func see(_ found: [CGPoint]?) {
        guard finding == nil, !shooting else { return }
        if let found {
            if let old = outline, OwnScanView.off(found, frame: old) < 0.1 {
                // Its corners tremble from picture to picture.
                outline = zip(old, found).map { CGPoint(x: $0.x + ($1.x - $0.x) * 0.6, y: $0.y + ($1.y - $0.y) * 0.6) }
            } else {
                outline = found
            }
            lostSince = nil
        } else {
            let since = lostSince ?? .now
            lostSince = since
            let gone = Date.now.timeIntervalSince(since)
            if gone > 0.6 { outline = nil }
            if gone > Self.patience, !manual, look.advice == .lost {
                withAnimation(.easeInOut(duration: 0.25)) { manual = true }
            }
        }
        watch()
    }

    /// All as the next photograph needs it, and still, for a good half second:
    /// it is taken.
    private func watch() {
        // All three taken (and sent, or failing to be): nothing more to take.
        guard finding == nil, !shooting, access == .ready, (scan?.sides.count ?? 0) < 2 else { return }
        guard look.advice == .hold, guide.steady || !guide.available else {
            holdSince = nil
            return
        }
        guard let since = holdSince else {
            holdSince = .now
            return
        }
        if Date.now.timeIntervalSince(since) > 0.6 { shoot() }
    }

    /// Before the next photograph: nothing held over from the last.
    private func rest() {
        holdSince = nil
        lostSince = .now
        manual = access == .ready && !camera.sees
    }

    private func startAgain() {
        camera.hold(false)
        front = nil
        rest()
        withAnimation(.easeInOut(duration: 0.25)) { scan = nil }
    }

    /// The photographs taken so far go on.
    private func finish() {
        guard let done = scan else { return }
        took(done)
    }

    // MARK: The bottom

    private var bottom: some View {
        ZStack {
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
                if byHand {
                    StandPlan(taken: number - 1).frame(width: 74, height: 52)
                }
            }
            if byHand {
                OwnShutter(action: shoot)
            } else {
                // Where to stand: the photographs take themselves.
                StandPlan(taken: number - 1).frame(width: 116, height: 78)
            }
        }
        .frame(height: 82)
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
        if let scan, scan.sides.count >= 2 {
            // The three could not be sent a moment ago: once more.
            took(scan)
            return
        }
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
        holdSince = nil
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
                rest()
                if shots.sides.count >= 2 {
                    scan = shots
                    finish()
                } else {
                    withAnimation(.easeInOut(duration: 0.25)) { scan = shots }
                }
            }
            return
        }
        // The work as it is seen from the front, for the helper frames.
        let seen = upright
        camera.shootFirst { image, file, depth in
            shooting = false
            guard let image else {
                model.notices.warn("Nie udało się zrobić zdjęcia")
                return
            }
            front = seen
            guide.zero()
            // The side photographs in the first one's light, so that only the reflections differ.
            camera.hold(true)
            rest()
            withAnimation(.easeInOut(duration: 0.25)) {
                scan = OwnShots(first: image, depth: depth, files: file.map { [$0] } ?? [])
            }
        }
    }
}

/// How far the phone has turned about the upright since the first
/// photograph of the three (gyroscope, about the gravity's line, so held
/// upright or on its side alike). Walking to the left while aiming at the
/// work turns it to the right: the angle between the two views. It stands
/// in for the work's outline when the camera does not find its edges, and
/// says when the phone is still.
@Observable
final class OwnScanGuide {
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
        motion.deviceMotionUpdateInterval = 1.0 / 30
        motion.startDeviceMotionUpdates(to: .main) { [weak self] data, _ in
            guard let self, let data else { return }
            let g = data.gravity, r = data.rotationRate
            let length = (g.x * g.x + g.y * g.y + g.z * g.z).squareRoot()
            guard length > 0.5 else { return }
            // About the upright (against gravity), positive to the left.
            let rate = -(r.x * g.x + r.y * g.y + r.z * g.z) / length
            if let last { turned += rate * (data.timestamp - last) }
            last = data.timestamp
            let still = (r.x * r.x + r.y * r.y + r.z * r.z).squareRoot() < 0.25
            if still != steady { steady = still }
        }
    }

    /// From here: the first photograph is taken.
    func zero() {
        turned = 0
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
final class OwnCameraSession: NSObject, AVCapturePhotoCaptureDelegate, AVCaptureVideoDataOutputSampleBufferDelegate,
    @unchecked Sendable {
    enum Access { case none, ready, denied }

    let session = AVCaptureSession()
    private let output = AVCapturePhotoOutput()
    private let queue = DispatchQueue(label: "own-camera")
    /// The camera's running picture, in which the work's outline is looked for.
    private let frames = AVCaptureVideoDataOutput()
    private let looking = DispatchQueue(label: "own-camera-looking")
    /// The work's outline in the latest picture looked at (0–1 across and
    /// down the upright screen's picture: top left, top right, bottom
    /// right, bottom left), or none, and whether the camera has little
    /// light (on the main thread).
    var seen: (([CGPoint]?, Bool) -> Void)?
    /// The running picture is looked at (else there is no outline, ever).
    private(set) var sees = false
    /// The camera's focal length in half-widths of the upright screen's picture.
    private(set) var focal = OwnScanView.focal
    /// On the looking queue: when the last picture was looked at, and the
    /// outline found in it.
    private var looked = Date.distantPast
    private var last: [CGPoint]?
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
        if !session.outputs.contains(frames), session.canAddOutput(frames) {
            // Small pictures, the newest only: the outline is all they are for.
            frames.alwaysDiscardsLateVideoFrames = true
            frames.automaticallyConfiguresOutputBufferDimensions = false
            frames.deliversPreviewSizedOutputBuffers = true
            frames.setSampleBufferDelegate(self, queue: looking)
            session.addOutput(frames)
            sees = true
        }
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
        // Across the sensor's long side, which stands upright on the screen.
        let view = Double(device.activeFormat.videoFieldOfView)
        if view > 20, view < 150 { focal = 4.0 / 3 / tan(view * .pi / 360) }
    }

    /// The side photographs in the first one's light and colour (so that
    /// only the reflections differ between them), or the camera's own
    /// again.
    func hold(_ locked: Bool) {
        queue.async { [self] in
            guard let device = current, (try? device.lockForConfiguration()) != nil else { return }
            defer { device.unlockForConfiguration() }
            let exposure: AVCaptureDevice.ExposureMode = locked ? .locked : .continuousAutoExposure
            if device.isExposureModeSupported(exposure) { device.exposureMode = exposure }
            let white: AVCaptureDevice.WhiteBalanceMode = locked ? .locked : .continuousAutoWhiteBalance
            if device.isWhiteBalanceModeSupported(white) { device.whiteBalanceMode = white }
        }
    }

    // MARK: The work's outline

    /// How often the running picture is looked at.
    private static let pace: TimeInterval = 0.11

    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard Date.now.timeIntervalSince(looked) >= Self.pace, let picture = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        looked = .now
        let request = VNDetectRectanglesRequest()
        request.maximumObservations = 6
        request.minimumConfidence = 0.5
        request.minimumSize = 0.2
        request.minimumAspectRatio = 0.2
        request.quadratureTolerance = 30
        // The sensor's picture lies on its side when the phone (and the screen) is upright.
        let handler = VNImageRequestHandler(cvPixelBuffer: picture, orientation: .right, options: [:])
        try? handler.perform([request])
        let found = (request.results ?? []).map { box in
            // Vision counts up from the bottom.
            [box.topLeft, box.topRight, box.bottomRight, box.bottomLeft].map { CGPoint(x: $0.x, y: 1 - $0.y) }
        }
        let outline = Self.work(among: found, last: last)
        last = outline
        // A long exposure or a high gain: the photograph will be blurred or grainy.
        let device = (connection.inputPorts.first?.input as? AVCaptureDeviceInput)?.device
        let dark = device.map { $0.exposureDuration.seconds >= 0.05 || $0.iso >= 1600 } ?? false
        DispatchQueue.main.async { [weak self] in self?.seen?(outline, dark) }
    }

    /// Which of the rectangles in the picture is the work: the one that
    /// was it a moment ago, else the largest.
    static func work(among found: [[CGPoint]], last: [CGPoint]?) -> [CGPoint]? {
        if let last, let same = found.min(by: { OwnScanView.off($0, frame: last) < OwnScanView.off($1, frame: last) }),
           OwnScanView.off(same, frame: last) < 0.12 {
            return same
        }
        return found.max { area($0) < area($1) }
    }

    /// The area within an outline (the shoelace's).
    static func area(_ q: [CGPoint]) -> Double {
        guard q.count > 2 else { return 0 }
        var sum = 0.0
        for index in q.indices {
            let a = q[index], b = q[(index + 1) % q.count]
            sum += Double(a.x * b.y - b.x * a.y)
        }
        return abs(sum) / 2
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
