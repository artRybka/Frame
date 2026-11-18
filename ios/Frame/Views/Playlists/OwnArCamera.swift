import ARKit
import AVFoundation
import CoreImage
import SceneKit
import SwiftUI
import UIKit

/// The phone's AR session for the side photographs of a scan: it knows
/// where the phone is in the room, so once the work is pinned there
/// (`OwnArWork`) its corners stay on it whatever the camera makes of the
/// picture, and the angle to the side is the phone's place, not a count
/// of its turns. Until it is pinned the session tells of the outline its
/// camera finds, as the camera's own way does. The first photograph
/// stays the camera's own (48 MP, the LiDAR's depth); these come from the
/// session's sharpest frame (12 MP), which is plenty for what they are
/// for: telling a reflection from the work. Only on a phone, never in the
/// simulator (`supported`).
final class OwnArSession: NSObject, ARSessionDelegate, @unchecked Sendable {
    /// The phone can follow itself about the room.
    static var supported: Bool { ARWorldTrackingConfiguration.isSupported }

    /// Made when first asked for: the view's state is made anew often,
    /// and most of those never come to the side photographs.
    private(set) lazy var tracking = ARSession()
    /// It has been run (on the main thread).
    private var ran = false
    private let looking = DispatchQueue(label: "own-ar-looking")
    /// What the latest picture has: the work's outline while it is being
    /// pinned, the pinned work after (on the main thread).
    var seen: ((OwnArLook) -> Void)?
    /// The session's first picture has come, and whether its camera was
    /// given the first photograph's white balance (on the main thread).
    var began: ((Bool) -> Void)?
    /// The session cannot go on: the camera's own way takes over (on the
    /// main thread).
    var failed: (() -> Void)?

    /// On the looking queue: the work once pinned, when the picture was
    /// last looked at or told of, the outline in the last look, and in
    /// how many looks in a row it has lain where it lay.
    private var work: OwnArWork?
    private var looked = Date.distantPast
    private var last: [CGPoint]?
    private var settled = 0
    private var quarter = 0
    /// Also there: for how many looks the outline shown has been kept
    /// with only a part of it found, when the first picture came, and
    /// whether the camera's light is held.
    private var missed = 0
    private var first: Date?
    private var held = false
    /// And the first photograph's white balance (the camera's gains for
    /// red, green and blue) when it could be told, and whether the
    /// session's camera has been given it.
    private var white: [Float]?
    private var tinted = false

    /// How often the picture is looked at for the work, and how often
    /// the pinned work is told of.
    private static let pace: TimeInterval = 0.12
    private static let telling: TimeInterval = 0.04
    /// The outline lies where it lay in this many looks before it is pinned.
    private static let looks = 2
    /// This long after its first picture the session's camera has
    /// settled on the light, and keeps it.
    private static let settling: TimeInterval = 0.6

    /// `quarter`: how the phone was held at the first photograph;
    /// `white`: the white balance its camera had then.
    func start(quarter: Int, white: [Float]? = nil) {
        looking.async { [self] in
            work = nil
            last = nil
            settled = 0
            missed = 0
            first = nil
            held = false
            tinted = false
            looked = .distantPast
            self.quarter = quarter
            self.white = white
        }
        let configuration = ARWorldTrackingConfiguration()
        configuration.planeDetection = [.vertical, .horizontal]
        if let sharp = ARWorldTrackingConfiguration.recommendedVideoFormatForHighResolutionFrameCapturing {
            configuration.videoFormat = sharp
        } else if let wide = ARWorldTrackingConfiguration.supportedVideoFormats.first(where: {
            abs($0.imageResolution.width / max($0.imageResolution.height, 1) - 4.0 / 3) < 0.01
        }) {
            // The picture as the camera's own: 4 : 3.
            configuration.videoFormat = wide
        }
        ran = true
        tracking.delegate = self
        tracking.delegateQueue = looking
        tracking.run(configuration, options: [.resetTracking, .removeExistingAnchors])
    }

    func stop() {
        guard ran else { return }
        ran = false
        tracking.pause()
        hold(false)
        looking.async { [self] in work = nil }
    }

    // MARK: The work in the room

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        let now = Date.now
        let camera = frame.camera
        let place = camera.transform.columns.3
        let eye = SIMD3<Float>(place.x, place.y, place.z)
        if let first {
            // The side photographs in one light, as the work is seen from
            // the front: he has hardly left it yet.
            if !held, now.timeIntervalSince(first) >= Self.settling {
                held = true
                hold(true)
            }
        } else {
            first = now
            tinted = tint(white)
            let given = tinted
            DispatchQueue.main.async { [weak self] in self?.began?(given) }
        }
        if let work {
            guard now.timeIntervalSince(looked) >= Self.telling else { return }
            looked = now
            let sight = OwnArSight(angle: work.angle(from: eye), away: work.away(from: eye), outline: Self.outline(of: work, in: camera))
            DispatchQueue.main.async { [weak self] in self?.seen?(OwnArLook(sight: sight, tracking: true)) }
            return
        }
        guard now.timeIntervalSince(looked) >= Self.pace else { return }
        looked = now
        // The work's outline is found and shown at once, as the camera's
        // own way shows it (Mateusz 2026-11-18 13:35 UTC: "znaczniki co
        // prawda nie pojawiają się od razu, ale dopiero gdy stanę pod
        // kątem"): the session knows where the phone is only after it
        // has moved a little, and until then nothing can be pinned.
        let (found, paper) = OwnCameraSession.looked(at: frame.capturedImage)
        let fresh = OwnCameraSession.work(among: found, paper: paper, last: last)
        if let fresh, let last, OwnScanView.off(fresh, frame: last) < 0.04 { settled += 1 } else { settled = 0 }
        let (outline, slipped) = OwnCameraSession.kept(fresh, was: last, missed: missed)
        last = outline
        missed = slipped
        var tracking = false
        if case .normal = camera.trackingState { tracking = true }
        if tracking, let fresh, OwnCameraSession.whole(fresh), settled >= Self.looks,
           let pinned = pin(fresh, frame: frame, session: session, eye: eye) {
            work = pinned
            if !held {
                held = true
                hold(true)
            }
            let sight = OwnArSight(angle: pinned.angle(from: eye), away: pinned.away(from: eye), outline: Self.outline(of: pinned, in: camera))
            DispatchQueue.main.async { [weak self] in self?.seen?(OwnArLook(sight: sight, tracking: true)) }
            return
        }
        DispatchQueue.main.async { [weak self] in self?.seen?(OwnArLook(found: outline, tracking: tracking)) }
    }

    /// The outline found in `frame` (on the upright screen's picture) as
    /// the work in the room: the wall is felt for under four places
    /// within it, and its corners are where their rays meet that plane.
    private func pin(_ outline: [CGPoint], frame: ARFrame, session: ARSession, eye: SIMD3<Float>) -> OwnArWork? {
        // Top left, top right… as the world stands, however the phone is held.
        let corners = OwnScanView.ordered(outline.map { OwnScanView.upright($0, quarter: quarter) })
            .map { OwnScanView.shown($0, quarter: quarter) }
        var hits: [SIMD3<Float>] = []
        for point in OwnArWork.felt(corners) {
            let query = frame.raycastQuery(from: OwnArWork.sensor(point), allowing: .estimatedPlane, alignment: .any)
            guard let hit = session.raycast(query).first else { return nil }
            let at = hit.worldTransform.columns.3
            hits.append(SIMD3<Float>(at.x, at.y, at.z))
        }
        guard let plane = OwnArWork.plane(through: hits) else { return nil }
        var places: [SIMD3<Float>] = []
        for point in corners {
            let query = frame.raycastQuery(from: OwnArWork.sensor(point), allowing: .estimatedPlane, alignment: .any)
            guard let at = OwnArWork.hit(origin: query.origin, direction: query.direction, plane: plane) else { return nil }
            places.append(at)
        }
        return OwnArWork(corners: places, from: eye)
    }

    /// The pinned work's corners on the upright screen's picture (0–1),
    /// nil when one of them is behind the phone.
    private static func outline(of work: OwnArWork, in camera: ARCamera) -> [CGPoint]? {
        let inverse = camera.transform.inverse
        var points: [CGPoint] = []
        for corner in work.corners {
            // The camera looks down its own -z.
            let local = inverse * SIMD4<Float>(corner.x, corner.y, corner.z, 1)
            guard local.z < -0.02 else { return nil }
            // The app's screen stays upright, and the picture on it is 3 : 4.
            let at = camera.projectPoint(corner, orientation: .portrait, viewportSize: CGSize(width: 3, height: 4))
            points.append(CGPoint(x: at.x / 3, y: at.y / 4))
        }
        return points
    }

    func session(_ session: ARSession, didFailWithError error: Error) {
        DispatchQueue.main.async { [weak self] in self?.failed?() }
    }

    /// The session's camera keeps the light and the colour it has now
    /// (so that only the reflections differ between the photographs), or
    /// follows them again. The colour it was given (`tint`) it has already.
    private func hold(_ locked: Bool) {
        guard let device = ARWorldTrackingConfiguration.configurableCaptureDeviceForPrimaryCamera,
              (try? device.lockForConfiguration()) != nil
        else { return }
        defer { device.unlockForConfiguration() }
        let exposure: AVCaptureDevice.ExposureMode = locked ? .locked : .continuousAutoExposure
        if device.isExposureModeSupported(exposure) { device.exposureMode = exposure }
        guard !locked || !tinted else { return }
        let white: AVCaptureDevice.WhiteBalanceMode = locked ? .locked : .continuousAutoWhiteBalance
        if device.isWhiteBalanceModeSupported(white) { device.whiteBalanceMode = white }
    }

    /// The session's camera in the first photograph's white balance
    /// (`gains`: red, green, blue, as that camera had them), and whether
    /// it could be given it. The session's camera settles on the light by
    /// itself in its first half second, elsewhere than the camera that
    /// took the first photograph had: on his scans of 2026-11-18 (16:11
    /// UTC, "w Test i Test 4 które są za szybą mogłoby być lepiej") the
    /// side photographs had 0.74 to 0.86 of the first's red against the
    /// green and 1.09 to 1.33 of its blue, more than the server evens out
    /// between two photographs of one wall.
    private func tint(_ gains: [Float]?) -> Bool {
        guard let gains, gains.count == 3, gains.allSatisfy({ $0.isFinite }),
              let device = ARWorldTrackingConfiguration.configurableCaptureDeviceForPrimaryCamera,
              device.isWhiteBalanceModeSupported(.locked),
              device.isLockingWhiteBalanceWithCustomDeviceGainsSupported,
              device.maxWhiteBalanceGain >= 1,
              (try? device.lockForConfiguration()) != nil
        else { return false }
        defer { device.unlockForConfiguration() }
        // Gains beyond what this camera has are an exception, not an error.
        let within = gains.map { min(max($0, 1), device.maxWhiteBalanceGain) }
        device.setWhiteBalanceModeLocked(
            with: AVCaptureDevice.WhiteBalanceGains(redGain: within[0], greenGain: within[1], blueGain: within[2]),
            completionHandler: nil
        )
        return true
    }

    // MARK: The photograph

    private static let context = CIContext()

    /// A photograph from the session's sharpest frame, upright as the
    /// phone is held (`quarter`), with its file as the server is sent it.
    func shoot(quarter: Int, _ took: @escaping (UIImage?, Data?) -> Void) {
        tracking.captureHighResolutionFrame { [self] frame, _ in
            // Without a sharper one: the running picture.
            let picture = frame?.capturedImage ?? tracking.currentFrame?.capturedImage
            looking.async {
                let file = picture.flatMap { Self.file($0, quarter: quarter) }
                let image = file.flatMap { OwnPicture.shown($0) ?? UIImage(data: $0) }
                DispatchQueue.main.async { took(image, file) }
            }
        }
    }

    /// The sensor's picture as a JPEG standing as the world does: the
    /// sensor lies on its side when the phone is upright.
    static func file(_ picture: CVPixelBuffer, quarter: Int) -> Data? {
        let image = CIImage(cvPixelBuffer: picture).oriented(turn(quarter))
        guard let space = CGColorSpace(name: CGColorSpace.displayP3) ?? CGColorSpace(name: CGColorSpace.sRGB) else { return nil }
        return context.jpegRepresentation(
            of: image, colorSpace: space,
            options: [kCGImageDestinationLossyCompressionQuality as CIImageRepresentationOption: 0.92]
        )
    }

    /// How the sensor's picture is turned to stand upright with the phone
    /// held upright (0), its top to the left (1) or to the right (-1): as
    /// `OwnCameraSession.orientation` turns the camera's own photographs.
    static func turn(_ quarter: Int) -> CGImagePropertyOrientation {
        quarter == 0 ? .right : quarter == 1 ? .up : .down
    }
}

/// What the AR session's camera sees, filling a 3 : 4 frame.
struct OwnArPreview: UIViewRepresentable {
    let session: ARSession

    func makeUIView(context: Context) -> ARSCNView {
        let view = ARSCNView(frame: .zero)
        view.session = session
        view.scene = SCNScene()
        view.automaticallyUpdatesLighting = false
        view.rendersCameraGrain = false
        view.rendersMotionBlur = false
        view.isUserInteractionEnabled = false
        return view
    }

    func updateUIView(_ view: ARSCNView, context: Context) {}
}
