import AVFoundation
import CoreMotion
import ImageIO
import PhotosUI
import SwiftUI
import UIKit
import Vision

/// What the camera gives the steps after it: the first photograph, those
/// taken from either side of the work (the scan, for the glare), and
/// the LiDAR's depth for the size (Mateusz 2026-11-16 chose "Wymiar + skan
/// z 3 zdjęć + 48 MP").
struct OwnShots {
    var first: UIImage
    var sides: [UIImage] = []
    /// From how far to the side each side photograph was taken (degrees;
    /// negative: from the work's left), as the phone counted it.
    var angles: [Double] = []
    /// What the camera noted of the scan as it went (seconds after the
    /// first photograph its marks came, how fast the phone turned at each
    /// side one…): it goes to the server with the scan, for the tuning.
    var trace: [String: Double] = [:]
    var depth: OwnDepth? = nil
    /// The photographs' own files, the first's and then the sides': every
    /// pixel as the camera wrote them (48 MP), which is what the server is
    /// sent (Mateusz 2026-11-16: "zdecydowanie wyższą jakość niż 4000px").
    /// The pictures above are small copies for the screen. Empty for the
    /// demo's photographs.
    var files: [Data] = []
    /// The rectangle the camera followed when the first photograph was
    /// taken (its corners 0–1 across and down the photograph, from the top
    /// left round by the right): where the work is when the server's
    /// model has no answer. Most often the frame's outer edge.
    var outline: [[Double]]? = nil

    /// The file of the `index`-th photograph (0, the first), if it has one.
    func file(_ index: Int) -> Data? {
        files.count == sides.count + 1 && files.indices.contains(index) ? files[index] : nil
    }

    /// From how far to the side the `index`-th side photograph was taken,
    /// when the phone said.
    func angle(_ index: Int) -> Double? {
        angles.count == sides.count && angles.indices.contains(index) ? angles[index] : nil
    }
}

/// "Dodaj własne dzieło" opening straight on the camera (Mateusz
/// 2026-11-15: "Po wybraniu „Dodaj własne dzieło” najlepiej byłoby od
/// razu pokazać aparat ale z dodatkową krótką instrukcją"): the picture
/// as it will be taken (3 : 4, nothing cut off), the work's outline as the
/// camera finds it, a word of advice, and Photos beside it. The first
/// photograph is taken from the front, by itself once the work is whole
/// in the picture, large enough and still; then he walks round the work
/// in one arc, to the left and to the right in whichever order, and one
/// from each side takes itself where the phone slows some 30° off
/// (`OwnScanArc`; Mateusz 2026-11-16: "pierwsze zdjęcie na wprost, a
/// kolejne pod większym kątem"; no shutter, "skoro zdjęcie robi się
/// samo", but when the work's edges are not found; 2026-11-18, the one
/// arc: "może da się to zbudować jeszcze lepiej, intuicyjniej i
/// szybciej"). The simulator has no camera: the demo shows its wall
/// photograph and a shutter.
struct OwnCamera: View {
    /// Leaves the steps (the back arrow at the top left).
    let close: () -> Void
    /// The photographs taken, or the one picked.
    let took: (OwnShots) -> Void
    /// A scan's photographs so far, when one is taken and more are to
    /// come (nil: the scan is begun anew): they can be on their way to the
    /// server while he walks to the side.
    var early: ((OwnShots?) -> Void)? = nil
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
    /// The scan under way: the first photograph taken, the sides to come.
    @State private var scan: OwnShots?
    /// The side photographs so far: which sides are done.
    @State private var arc = OwnScanArc()
    /// What the hand feels on the way to a side and when it is done.
    @State private var haptics = OwnScanHaptics()
    /// When the first photograph was taken, and what the scan has noted
    /// of itself since (`OwnShots.trace`).
    @State private var began: Date?
    @State private var trace: [String: Double] = [:]
    /// No photographs in passing: one could not be taken, or the server
    /// is one from before it took them (`OwnScanArc.extras`).
    @State private var plain = false
    /// One is being taken in passing: nothing shows of it.
    @State private var quiet = false
    @State private var guide = OwnScanGuide()
    /// The work's outline as the camera sees it now (0–1 on the screen's
    /// picture).
    @State private var outline: [CGPoint]?
    /// Since when no outline has been seen.
    @State private var lostSince: Date? = .now
    /// The outline at the first photograph, as the world stands.
    @State private var front: [CGPoint]?
    /// Since when all has been as the next photograph needs it.
    @State private var holdSince: Date?
    /// The shutter is out: the work's edges were not found for a while.
    @State private var manual = false
    /// Since when he has stood where a side photograph is taken with the
    /// work's corners not found.
    @State private var blindSince: Date?
    /// The camera has little light.
    @State private var dim = false
    /// What is drawn over the picture and said under it.
    @State private var look = OwnScanLook()
    /// What the helper says, held until something else has been true a moment.
    @State private var steady = OwnScanSteady()
    /// Where the phone stands: the gyroscope and the work's outline as one.
    @State private var stands = OwnScanAngle()
    /// How the phone was held at the first photograph (`quarter`).
    @State private var heldAs = 0
    /// The phone's AR session, which pins the work in the room after the
    /// first photograph and takes the side ones (`OwnArSession`).
    @State private var ar = OwnArSession()
    /// The side photographs go through the AR session: the picture is its.
    @State private var pinning = false
    /// The AR session's picture has come (the camera changes hands after
    /// the first photograph and is dark for a moment: until then the
    /// photograph just taken stays).
    @State private var arLive = false
    /// The pinned work as the AR session sees it now; nil until it is pinned.
    @State private var sight: OwnArSight?

    /// Without an outline for this long, he takes the photograph himself.
    private static let patience: TimeInterval = 5
    /// Standing where a side photograph is taken without the work's
    /// corners for this long, the same.
    private static let blind: TimeInterval = 3
    /// One more photograph is taken in passing only while the phone
    /// turns slower than this (radians a second).
    private static let passing = 0.6

    private var demo: UIImage? { access == .ready ? nil : (model.demoMode ? DemoOwn.photo() : nil) }

    /// Which step of the scan this is (1: the first photograph; 2: the
    /// ones from the sides).
    private var number: Int { scan == nil ? 1 : 2 }

    // MARK: What the camera sees

    /// How the phone is held: 0 upright, 1 its top to the left, -1 to the right.
    private var quarter: Int { tilt > 45 ? 1 : tilt < -45 ? -1 : 0 }
    /// The picture as the world stands: tall, or wide with the phone on its side.
    private var aspect: Double { quarter == 0 ? 0.75 : 4.0 / 3 }
    private var focal: Double { quarter == 0 ? camera.focal : camera.focal * 0.75 }
    /// Where the phone stands by the gyroscope since the first photograph
    /// (degrees; negative: to the left of the work, aiming at it).
    private var turned: Double { guide.turned * 180 / .pi }

    /// The outline as the world stands.
    private var upright: [CGPoint]? {
        outline.map { corners in OwnScanView.ordered(corners.map { OwnScanView.upright($0, quarter: quarter) }) }
    }

    /// What the camera and the gyroscope say now. The angle is the
    /// gyroscope's count drawn towards the outline's (`stands`), so the
    /// dot on the plan goes evenly and stays true. `fresh`: the camera
    /// has just looked at its picture.
    private func reading(fresh: Bool = false) -> OwnScanLook {
        var look = OwnScanLook(number: number)
        look.manual = manual
        look.dim = dim
        look.quarter = quarter
        guard scan != nil else {
            look.live = outline
            look.advice = OwnScanView.first(upright, aspect: aspect)
            return look
        }
        look.left = arc.done(left: true)
        look.right = arc.done(left: false)
        look.shots = arc.taken
        look.filled = [arc.filled(left: true), arc.filled(left: false)]
        let angle: Double
        var away = 1.0
        // The work's outline as the world stands, when it is seen.
        let work: [CGPoint]?
        let seen: Bool
        var stray = 0.0
        if pinning, let sight {
            // The work is pinned in the room: where the phone stands and
            // where the work's corners are on the picture are known,
            // whatever the camera makes of the picture.
            angle = sight.angle
            away = sight.away
            work = upright
            seen = work != nil
            look.live = outline
        } else {
            // Until then (and without an AR session): the gyroscope's
            // count, drawn towards what the work's outline says.
            var outlines: Double?
            if let upright, let front, let shape = OwnScanView.shape(of: front, aspect: aspect),
               let now = OwnScanView.turn(of: upright, shape: shape, aspect: aspect, focal: focal),
               let then = OwnScanView.turn(of: front, shape: shape, aspect: aspect, focal: focal),
               let far = OwnScanView.away(upright, front: front, aspect: aspect) {
                outlines = now - then
                away = far
            }
            let fused = stands.fuse(gyro: guide.available ? turned : nil, seen: outlines, fresh: fresh)
            guard let counted = fused.angle else {
                look.advice = .lost
                return look
            }
            angle = counted
            // How far away, whether it is whole: only of an outline that is the work's.
            work = fused.seen ? upright : nil
            if work == nil { away = 1 }
            look.live = fused.seen ? outline : nil
            // Its corners are waited for where the camera found them at
            // the first photograph.
            seen = work != nil || front == nil
            stray = fused.stray
        }
        look.angle = angle
        let fits = work.map(OwnScanView.fits) ?? true
        if let target = arc.target(at: angle) {
            look.advice = OwnScanView.side(
                target: target, angle: angle, away: away, fits: fits,
                // The whole work in the picture is enough: its middle
                // need not be in the picture's (the one arc, 2026-11-18).
                aim: fits ? 0 : work.map { OwnScanView.offAim($0, aspect: aspect) } ?? 0,
                seen: seen, held: steady.said == .hold, stray: stray
            )
        } else {
            // In front of the work with the first photograph taken: round
            // it now, either way.
            look.advice = fits ? .either : .farther
        }
        // All are taken with the phone held one way.
        if quarter != heldAs { look.advice = .rolled }
        return look
    }

    /// The camera's and the gyroscope's news onto the screen: the word
    /// only once it has been true a moment, the rest at once.
    private func refresh(fresh: Bool = false) {
        guard finding == nil else { return }
        var next = reading(fresh: fresh)
        // (One taken in passing stops nothing: he walks on.)
        let busy = shooting && !quiet
        if !busy { next.advice = steady.take(next.advice) } else { next.advice = look.advice }
        if next.advice == .corners {
            // Standing right and the corners not found for a while (a dark
            // frame on a dark wall): he takes the photograph himself.
            let since = blindSince ?? .now
            blindSince = since
            // (Not with the work pinned: it is known to be out of the picture.)
            if !manual, sight == nil, Date.now.timeIntervalSince(since) > Self.blind {
                withAnimation(.easeInOut(duration: 0.25)) { manual = true }
                next.manual = true
            }
        } else if blindSince != nil {
            blindSince = nil
        }
        if scan != nil, !busy, let angle = next.angle {
            // The way to the side's photograph ticks, faster and faster.
            haptics.walked(to: angle, target: arc.target(at: angle))
            // And the plan's way fills up to where he has been.
            var walked = arc
            walked.walked(to: angle)
            if walked != arc {
                arc = walked
                next.filled = [arc.filled(left: true), arc.filled(left: false)]
            }
        }
        if next != look { look = next }
        watch()
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
            if scan != nil { refresh() }
        }
        .onChange(of: quarter) { _, now in
            guide.quarter = now
            refresh()
        }
        .sensoryFeedback(.impact(weight: .medium), trigger: look.matched) { _, now in now }
        .task {
            // Screenshots of the later steps take the demo's photograph at once.
            guard !["own-cut", "own-balance", "own-describe", "own-card"].contains(LaunchRoute.screen) else { return }
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
            ar.stop()
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
                Text(bound: "Krok \(number) z 2")
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

    /// The picture as it will be taken, with the work's outline and the
    /// way round it over it.
    private var viewfinder: some View {
        ZStack {
            if let finding {
                // A wide photograph (the phone held on its side) whole, not cut to the tall frame.
                Image(uiImage: finding).resizable()
                    .aspectRatio(contentMode: finding.size.width > finding.size.height ? .fit : .fill)
            } else if access == .ready, pinning {
                OwnArPreview(session: ar.tracking)
                if !arLive, let first = scan?.first {
                    OwnStill(image: first, quarter: heldAs).transition(.opacity)
                }
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
                OwnScanOverlay(look: look, holding: shooting ? nil : holdSince, taking: shooting && !quiet)
            } else if finding == nil, demo != nil {
                // Without a camera (the demo): where they are taken from.
                OwnScanPlan(
                    front: scan != nil, left: arc.done(left: true), right: arc.done(left: false),
                    shots: arc.taken, filled: [arc.filled(left: true), arc.filled(left: false)],
                    angle: nil, matched: false
                )
                    .frame(height: 64)
                    .frame(maxWidth: 340)
                    .padding(.horizontal, 30)
                    .frame(maxHeight: .infinity, alignment: .bottom)
                    .padding(.bottom, 18)
            }
            if finding != nil {
                ProgressView().tint(.white).controlSize(.large)
            }
            if flash { Color.white.transition(.opacity) }
        }
        .aspectRatio(3 / 4, contentMode: .fit)
        // Across the whole screen, square (Mateusz 2026-11-16 16:44 UTC:
        // "Na pełną szerokość ekranu? Może bez wyoblonych narożników?").
        .clipped()
        .animation(.easeOut(duration: 0.25), value: finding == nil)
    }

    @ViewBuilder
    private var caption: some View {
        if finding != nil {
            line(findingText)
        } else if access == .ready {
            OwnScanCaption(look: look)
        } else if scan != nil {
            line(arc.done(left: true) ? "Zdjęcie z prawej strony dzieła" : "Zdjęcie z lewej strony dzieła")
        } else {
            line("Umieść całe dzieło w kadrze")
        }
    }

    private func line(_ text: String) -> some View {
        Text(bound: text)
            .font(.subheadline.weight(.medium))
            .foregroundStyle(.white.opacity(0.85))
            .multilineTextAlignment(.center)
    }

    // MARK: The watch

    /// What the camera found in its latest picture: the work's outline, or none.
    private func see(_ found: [CGPoint]?) {
        guard finding == nil, !shooting || quiet else { return }
        if let found {
            if let old = outline, OwnScanView.off(found, frame: old) < 0.1 {
                // Its corners tremble from picture to picture.
                outline = zip(old, found).map { CGPoint(x: $0.x + ($1.x - $0.x) * 0.6, y: $0.y + ($1.y - $0.y) * 0.6) }
            } else {
                outline = found
            }
            lostSince = nil
            note("outline")
        } else {
            let since = lostSince ?? .now
            lostSince = since
            let gone = Date.now.timeIntervalSince(since)
            if gone > 0.6 { outline = nil }
            if gone > Self.patience, !manual, look.advice == .lost {
                withAnimation(.easeInOut(duration: 0.25)) { manual = true }
            }
        }
        refresh(fresh: found != nil)
    }

    /// All as the next photograph needs it: the ring fills (`OwnShotRing`),
    /// and once it is full and the phone still, the photograph is taken.
    /// A side one is taken as soon as the phone is still where it is
    /// meant from (he slows there and walks on), or, as it always was,
    /// held there a moment and steady enough.
    private func watch() {
        // All taken (and sent, or failing to be): nothing more to take.
        guard finding == nil, !shooting, access == .ready, !arc.finished else { return }
        if scan != nil, !plain, case .go = look.advice, let angle = look.angle, arc.early(at: angle),
           look.live.map(OwnScanView.fits) == true, guide.available, guide.rate < Self.passing {
            // On the way out to a side: one more, in passing.
            shoot(passing: true)
            return
        }
        guard look.advice == .hold else {
            if holdSince != nil { withAnimation(.easeOut(duration: 0.2)) { holdSince = nil } }
            return
        }
        guard let since = holdSince else {
            withAnimation(.easeOut(duration: 0.2)) { holdSince = .now }
            return
        }
        let held = Date.now.timeIntervalSince(since) >= OwnShotRing.time && (guide.steady || !guide.available)
        if held || (scan != nil && guide.calm) { shoot() }
    }

    /// Before the next photograph: nothing held over from the last.
    private func rest() {
        holdSince = nil
        lostSince = .now
        blindSince = nil
        manual = access == .ready && !camera.sees
        steady = OwnScanSteady()
        // The phone's turns away from the work are counted from here.
        stands.rest(gyro: turned)
        look = reading()
    }

    private func startAgain() {
        unpin()
        camera.hold(false)
        front = nil
        stands = OwnScanAngle()
        arc = OwnScanArc()
        haptics.rest()
        began = nil
        trace = [:]
        plain = false
        withAnimation(.easeInOut(duration: 0.25)) { scan = nil }
        early?(nil)
        rest()
    }

    /// The photographs taken so far go on.
    private func finish() {
        guard var done = scan else { return }
        done.trace = trace
        took(done)
    }

    /// The scan notes when something first came, in seconds after its
    /// first photograph.
    private func note(_ what: String) {
        guard let began, trace[what] == nil else { return }
        trace[what] = (Date.now.timeIntervalSince(began) * 100).rounded() / 100
    }

    // MARK: The work pinned in the room

    /// After the first photograph: the camera goes to the phone's AR
    /// session, which looks for the work once more and pins it in the
    /// room (Mateusz 2026-11-18 08:22 UTC: "znaczniki… naniesione na
    /// ścianę lub przyklejone do jego ramy"). Its corners then stay on it
    /// and the angle is the phone's place in the room. He is not kept
    /// waiting for that: the session only finds its place in the room
    /// once the phone moves (13:35 UTC: "znaczniki co prawda nie
    /// pojawiają się od razu, ale dopiero gdy stanę pod kątem"), so the
    /// corners are drawn at once from what its camera sees and the angle
    /// is the gyroscope's count, as without it, until the work is pinned.
    private func pin() {
        sight = nil
        outline = nil
        dim = false
        arLive = false
        let held = heldAs
        ar.began = { tinted in
            guard pinning else { return }
            note("ar_picture")
            trace["white_held"] = tinted ? 1 : 0
            withAnimation(.easeOut(duration: 0.15)) { arLive = true }
        }
        ar.seen = { now in
            guard pinning else { return }
            if now.tracking { note("ar_tracking") }
            if let pinned = now.sight {
                note("pinned")
                sight = pinned
                outline = pinned.outline
                refresh(fresh: true)
            } else if sight == nil {
                see(now.found)
            }
        }
        ar.failed = { unpin() }
        withAnimation(.easeInOut(duration: 0.2)) { pinning = true }
        // The side photographs in the first one's white balance: the
        // session's camera is given what the camera has now.
        camera.leave { white in
            // (Unless he has begun anew meanwhile.)
            guard pinning else { return }
            note("ar_start")
            if let white, white.count == 3, white[1] > 0 {
                trace["white_red"] = Double((white[0] / white[1] * 1000).rounded() / 1000)
                trace["white_blue"] = Double((white[2] / white[1] * 1000).rounded() / 1000)
            }
            ar.start(quarter: held, white: white)
        }
    }

    /// Back to the camera's own session: the scan is begun anew, or the
    /// AR session cannot go on.
    private func unpin() {
        guard pinning else { return }
        ar.stop()
        pinning = false
        arLive = false
        sight = nil
        outline = nil
        Task { access = await camera.start() }
    }

    // MARK: The bottom

    /// Photos before the first photograph, and the shutter when the
    /// photograph does not take itself. (The three photographs' small
    /// pictures were here, Mateusz 2026-11-16 15:02 UTC: "nie pokazujmy
    /// miniaturki 3 miejsc na zdjęcia - niewiele wnosi, a dezorientuje";
    /// the plan of where to stand is over the picture now.)
    private var bottom: some View {
        ZStack {
            HStack {
                if scan == nil {
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
            }
            if byHand {
                OwnShutter { shoot() }
            }
        }
        .frame(height: 82)
        .disabled(shooting || finding != nil)
        // Nothing to press while the photographs are sent and made one
        // (Mateusz 2026-11-16 16:55 UTC: "na tym etapie na pewno nie
        // powinno być guzika robienia zdjęcia").
        .opacity(finding == nil ? 1 : 0)
        .padding(.horizontal, 32)
        .padding(.bottom, 12)
    }

    /// The next photograph. `passing`: one more on the way out to a side,
    /// taken without a word.
    private func shoot(passing: Bool = false) {
        guard !shooting else { return }
        if let scan, arc.finished {
            // They could not be sent a moment ago: once more.
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
                shots.angles.append(arc.next)
                arc.took(arc.next)
                if arc.finished {
                    took(shots)
                } else {
                    scan = shots
                    early?(shots)
                }
            } else {
                took(OwnShots(first: demo))
            }
            return
        }
        // The ring turns until the camera has written the photograph.
        shooting = true
        quiet = passing
        holdSince = nil
        if var shots = scan {
            // From where: the phone's count, or (he pressed the shutter
            // with none) the side that is next.
            let at = look.angle ?? arc.next
            let rate = guide.rate, pinned = sight != nil
            let taken: (UIImage?, Data?) -> Void = { image, file in
                shooting = false
                guard let image else {
                    if passing { plain = true } else { model.notices.warn("Nie udało się zrobić zdjęcia") }
                    return
                }
                let had = [arc.done(left: true), arc.done(left: false)]
                shots.sides.append(image)
                shots.angles.append(at)
                if let file { shots.files.append(file) }
                arc.took(at)
                let name = "side\(shots.sides.count)"
                note(name)
                trace[name + "_rate"] = (rate * 100).rounded() / 100
                trace[name + "_pinned"] = pinned ? 1 : 0
                shots.trace = trace
                if had != [arc.done(left: true), arc.done(left: false)] {
                    // The side is done (14:03 UTC: "potwierdzenie
                    // wykonania danej strony").
                    blink()
                    haptics.done()
                } else if !passing {
                    blink()
                }
                if arc.finished {
                    scan = shots
                    rest()
                    // All are taken: the AR session rests, its last picture stays.
                    if pinning { ar.stop() }
                    finish()
                } else {
                    withAnimation(.easeInOut(duration: 0.25)) { scan = shots }
                    early?(shots)
                    // (One taken in passing: he walks on as he was.)
                    if !passing { rest() }
                }
            }
            if pinning {
                ar.shoot(quarter: heldAs, taken)
            } else {
                camera.shoot { image, file, _ in taken(image, file) }
            }
            return
        }
        // The work as it is seen from the front, and the angles counted from here.
        let seen = upright
        guide.zero()
        stands = OwnScanAngle()
        heldAs = quarter
        camera.shootFirst { image, file, depth in
            shooting = false
            guard let image else {
                model.notices.warn("Nie udało się zrobić zdjęcia")
                return
            }
            blink()
            front = seen
            arc = OwnScanArc()
            haptics.rest()
            began = .now
            trace = [:]
            plain = !OwnScanArc.extras(server: model.serverUpdate?.version)
            let shots = OwnShots(
                first: image, depth: depth, files: file.map { [$0] } ?? [],
                outline: seen.map { $0.map { [Double($0.x), Double($0.y)] } }
            )
            withAnimation(.easeInOut(duration: 0.25)) { scan = shots }
            if OwnArSession.supported {
                pin()
            } else {
                // The side photographs in the first one's light, so that only the reflections differ.
                camera.hold(true)
            }
            early?(shots)
            rest()
        }
    }

    /// The photograph is taken: the picture blinks white.
    private func blink() {
        withAnimation(.easeOut(duration: 0.08)) { flash = true }
        Task {
            try? await Task.sleep(for: .milliseconds(90))
            withAnimation(.easeIn(duration: 0.2)) { flash = false }
        }
    }
}

/// How far the phone has turned about the picture's upright since the
/// first photograph of the three (gyroscope). Walking to the left while
/// aiming at the work turns it to the right: the angle between the two
/// views. Before a wall the picture's upright is the gravity's line, so
/// held upright or on its side alike; over a work lying on a table (the
/// phone looking down) it is the phone's own upright as it is held, which
/// the gravity's line says nothing of (his folder on the desk,
/// 2026-11-16). It keeps the count between the camera's looks at the
/// work's outline, and says when the phone is still.
@Observable
final class OwnScanGuide {
    /// Radians to the left (negative: to the right).
    var turned = 0.0
    /// Not turning just now (the photograph will not blur).
    var steady = false
    /// How the phone is held: 0 upright, 1 its top to the left, -1 to the right.
    @ObservationIgnored var quarter = 0
    /// How fast the phone turns now, about any line (radians a second).
    @ObservationIgnored private(set) var rate = 0.0
    /// Since when (the gyroscope's clock) it has turned slower than
    /// `quiet`, and that clock now.
    @ObservationIgnored private var quietSince: TimeInterval?
    @ObservationIgnored private var clock: TimeInterval = 0

    /// Slower than this (radians a second) for `quietTime`, the phone is
    /// still: a side photograph is taken at once, with no holding it
    /// there (the one arc, 2026-11-18).
    static let quiet = 0.12
    static let quietTime: TimeInterval = 0.15

    /// How long the phone has been still, by its samples' clock.
    static func still(since: TimeInterval?, now: TimeInterval) -> Bool {
        since.map { now - $0 >= quietTime } ?? false
    }

    /// Still, and has been for a moment.
    var calm: Bool { Self.still(since: quietSince, now: clock) }

    /// How fast the phone turns to the left about the picture's upright
    /// (radians a second). `gravity` and `rate` as the phone has them: x
    /// to its right, y to its top, z out of its screen.
    static func turning(rate r: (x: Double, y: Double, z: Double), gravity g: (x: Double, y: Double, z: Double), quarter: Int) -> Double? {
        let length = (g.x * g.x + g.y * g.y + g.z * g.z).squareRoot()
        guard length > 0.5 else { return nil }
        if abs(g.z) / length > 0.75 {
            // Looking down (or up): about the phone's own upright as it is held.
            return quarter == 0 ? r.y : quarter == 1 ? r.x : -r.x
        }
        // Before a wall: about the upright, against gravity.
        return -(r.x * g.x + r.y * g.y + r.z * g.z) / length
    }

    /// One for the app, as Apple asks (the view's state is made anew often).
    private static let motion = CMMotionManager()
    @ObservationIgnored private var last: TimeInterval?
    private var motion: CMMotionManager { Self.motion }

    var available: Bool { motion.isDeviceMotionAvailable }

    func start() {
        turned = 0
        last = nil
        rate = 0
        quietSince = nil
        guard available else { return }
        motion.stopDeviceMotionUpdates()
        motion.deviceMotionUpdateInterval = 1.0 / 30
        motion.startDeviceMotionUpdates(to: .main) { [weak self] data, _ in
            guard let self, let data else { return }
            let g = data.gravity, r = data.rotationRate
            guard let about = Self.turning(rate: (r.x, r.y, r.z), gravity: (g.x, g.y, g.z), quarter: quarter) else { return }
            if let last { turned += about * (data.timestamp - last) }
            last = data.timestamp
            let all = (r.x * r.x + r.y * r.y + r.z * r.z).squareRoot()
            rate = all
            clock = data.timestamp
            if all < Self.quiet { quietSince = quietSince ?? data.timestamp } else { quietSince = nil }
            let still = all < 0.25
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
    /// Looks in a row in which the work was not found and a part of it was.
    private var missed = 0
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
        let (found, paper) = Self.looked(at: picture)
        let (outline, slipped) = Self.kept(Self.work(among: found, paper: paper, last: last), was: last, missed: missed)
        last = outline
        missed = slipped
        // A long exposure or a high gain: the photograph will be blurred or grainy.
        let device = (connection.inputPorts.first?.input as? AVCaptureDeviceInput)?.device
        let dark = device.map { $0.exposureDuration.seconds >= 0.05 || $0.iso >= 1600 } ?? false
        DispatchQueue.main.async { [weak self] in self?.seen?(outline, dark) }
    }

    /// The rectangles in one of the camera's pictures and what Vision
    /// takes for a sheet lying before it (0–1 across and down the upright
    /// screen's picture, each from the top left round by the right).
    static func looked(at picture: CVPixelBuffer) -> (found: [[CGPoint]], paper: [CGPoint]?) {
        let request = VNDetectRectanglesRequest()
        request.maximumObservations = 8
        request.minimumConfidence = 0.5
        request.minimumSize = 0.2
        request.minimumAspectRatio = 0.2
        // A work hung high and photographed from below: its corners are
        // well off square (30 lost his painting of bottles in most looks).
        request.quadratureTolerance = 40
        // A canvas with no frame about it: its edge against the wall is
        // soft and the painting's own lines are not, so the rectangles are
        // parts of the painting or none (Mateusz 2026-11-18, his landscape
        // with a bridge: "ani z jednego ani drugiego kąta dzieło nie
        // zostało wykryte automatycznie"). What Vision takes for a sheet
        // lying before the camera is the canvas then.
        let sheet = VNDetectDocumentSegmentationRequest()
        // The sensor's picture lies on its side when the phone (and the screen) is upright.
        let handler = VNImageRequestHandler(cvPixelBuffer: picture, orientation: .right, options: [:])
        try? handler.perform([request])
        try? handler.perform([sheet])
        // Vision counts up from the bottom.
        func corners(_ box: VNRectangleObservation) -> [CGPoint] {
            [box.topLeft, box.topRight, box.bottomRight, box.bottomLeft].map { CGPoint(x: $0.x, y: 1 - $0.y) }
        }
        return ((request.results ?? []).map(corners), sheet.results?.first.map(corners))
    }

    /// Which of the rectangles in the picture is the work: the one that
    /// was it a moment ago, else the largest that is wholly in the picture.
    ///
    /// The one followed gives way in two cases (Mateusz 2026-11-16 16:44
    /// UTC, his painting of bottles photographed from below, "bywa że
    /// przy robieniu pierwszego zdjęcia program nie łapie kształtu
    /// obrazu"): it lies within a clearly larger one (it was the blue
    /// rectangle painted in the middle of the work), or it runs out of the
    /// picture while another does not (it was the wall about the work with
    /// its shadow).
    static func work(among found: [[CGPoint]], last: [CGPoint]?) -> [CGPoint]? {
        let seen = found.filter(whole)
        let largest = (seen.isEmpty ? found : seen).max { area($0) < area($1) }
        guard let last, let same = found.min(by: { OwnScanView.off($0, frame: last) < OwnScanView.off($1, frame: last) }),
              OwnScanView.off(same, frame: last) < 0.12
        else { return largest }
        guard let largest, whole(largest) else { return same }
        if !whole(same) || part(same, of: largest) { return largest }
        return same
    }

    /// The work among the rectangles and what Vision takes for a sheet
    /// lying before the camera (`paper`). The rectangles come first, as
    /// they did: about a framed work the sheet is now the frame, now the
    /// picture in it, now the frame with the one hanging beside it. The
    /// sheet is the work where the rectangles find nothing (his canvas
    /// with no frame, 2026-11-18: none in most looks from the front and
    /// from either side, the sheet in every one) or only a part of it
    /// (the upper half of a relief, down to the glasses on it). Of his 27
    /// kept scans' photographs, looked at in four sizes, it changed 23
    /// looks of 324, each for the better.
    static func work(among found: [[CGPoint]], paper: [CGPoint]?, last: [CGPoint]?) -> [CGPoint]? {
        let seen = work(among: found, last: last)
        guard let paper, paper.count == 4, whole(paper), large(paper) else { return seen }
        guard let seen else { return paper }
        return part(seen, of: paper) ? paper : seen
    }

    /// As large as a rectangle is looked for (`minimumSize`): across and down.
    static func large(_ q: [CGPoint]) -> Bool {
        let xs = q.map(\.x), ys = q.map(\.y)
        guard let left = xs.min(), let right = xs.max(), let top = ys.min(), let bottom = ys.max() else { return false }
        return right - left >= 0.2 && bottom - top >= 0.2
    }

    /// Nearer the picture's edge than this (of its side), a corner is
    /// taken to lie beyond it.
    static let edge: CGFloat = 0.015
    /// So many times the area of the one followed, a rectangle about it
    /// is the work and the one followed a part of it. (A frame about its
    /// canvas is less: the outline does not jump between the two.)
    static let outgrown = 1.5

    /// All of the outline is in the picture.
    static func whole(_ q: [CGPoint]) -> Bool {
        q.allSatisfy { min($0.x, $0.y, 1 - $0.x, 1 - $0.y) > edge }
    }

    /// `inner` lies within `outer` and is clearly smaller.
    static func part(_ inner: [CGPoint], of outer: [CGPoint]) -> Bool {
        guard outer.count == 4, area(outer) > area(inner) * outgrown else { return false }
        // A little more about its middle: the two are seen a few pixels apart.
        let m = OwnScanView.middle(outer)
        let wide = outer.map { CGPoint(x: m.x + ($0.x - m.x) * 1.04, y: m.y + ($0.y - m.y) * 1.04) }
        return inner.allSatisfy { point in
            let turns = wide.indices.map { index -> CGFloat in
                let a = wide[index], b = wide[(index + 1) % wide.count]
                return (b.x - a.x) * (point.y - a.y) - (b.y - a.y) * (point.x - a.x)
            }
            return turns.allSatisfy { $0 >= 0 } || turns.allSatisfy { $0 <= 0 }
        }
    }

    /// The outline to show after a look that found `now`, when `was` was
    /// shown before it: the work itself slips a look now and then (seen
    /// from below, its corners are far from square) while a part of it is
    /// still found, and for `patience` looks the work stays.
    static func kept(_ now: [CGPoint]?, was: [CGPoint]?, missed: Int) -> (outline: [CGPoint]?, missed: Int) {
        guard let now, let was, missed < patience, part(now, of: was) else { return (now, 0) }
        return (was, missed + 1)
    }

    /// Looks (of `pace`) the work is kept for when only a part of it is found.
    static let patience = 4

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

    /// `then` (on the main thread): the camera is free for another session.
    func stop(then: (() -> Void)? = nil) {
        queue.async { [session] in
            if session.isRunning { session.stopRunning() }
            if let then { DispatchQueue.main.async(execute: then) }
        }
    }

    /// The camera stopped for another session to have it, which is told
    /// (`then`, on the main thread) the white balance this one had at the
    /// last: its gains for red, green and blue, nil when it has no camera.
    func leave(then: @escaping ([Float]?) -> Void) {
        queue.async { [self] in
            let gains = session.isRunning ? current?.deviceWhiteBalanceGains : nil
            let white = gains.map { [$0.redGain, $0.greenGain, $0.blueGain] }
            if session.isRunning { session.stopRunning() }
            DispatchQueue.main.async { then(white) }
        }
    }

    /// The first photograph, with the depth when there is a LiDAR, and
    /// then the same view again at once without it when the photograph
    /// with the depth has fewer pixels than the camera can give: the
    /// first photographs of his scans of 2026-11-16 were 12 MP beside side
    /// ones of 48 MP (a photograph with depth is never the full 48 MP),
    /// and every detail of the scan is the first photograph's. With the
    /// sharper camera, when the LiDAR's own has fewer pixels.
    func shootFirst(_ took: @escaping (UIImage?, Data?, OwnDepth?) -> Void) {
        let angle = rotation?.videoRotationAngleForHorizonLevelCapture ?? 90
        queue.async { [self] in
            let measuring = lidar != nil && current == lidar && output.isDepthDataDeliveryEnabled
            let view = current?.activeFormat.videoFieldOfView
            capture(angle, depth: measuring) { [self] photo in
                let file = photo?.fileDataRepresentation()
                let image = file.flatMap(Self.picture)
                let depth = photo.flatMap { Self.depth(of: $0, angle: angle, fieldOfView: view, image: image) }
                guard let photo, image != nil else {
                    DispatchQueue.main.async { took(image, file, depth) }
                    return
                }
                if let sharper { use(sharper, depth: false) }
                guard sharper != nil || Self.pixels(photo.resolvedSettings.photoDimensions) * 3 < Self.pixels(output.maxPhotoDimensions) * 2
                else {
                    DispatchQueue.main.async { took(image, file, depth) }
                    return
                }
                // Another camera needs a moment for its focus and light.
                again(angle, after: sharper != nil ? 0.7 : 0.05, tries: 3) { sharp in
                    let sharpFile = sharp?.fileDataRepresentation()
                    if let sharpFile, let picture = Self.picture(sharpFile) {
                        DispatchQueue.main.async { took(picture, sharpFile, depth) }
                    } else {
                        DispatchQueue.main.async { took(image, file, depth) }
                    }
                }
            }
        }
    }

    /// On the camera's queue: a photograph without depth, asked for again
    /// while the camera is not ready to give one.
    private func again(_ angle: CGFloat, after wait: TimeInterval, tries: Int, _ done: @escaping (AVCapturePhoto?) -> Void) {
        queue.asyncAfter(deadline: .now() + wait) { [self] in
            capture(angle, depth: false) { [self] photo in
                if photo != nil || tries <= 1 {
                    done(photo)
                } else {
                    again(angle, after: 0.5, tries: tries - 1, done)
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
        // What the camera says of how its lens bent this photograph.
        var bend: (table: Data, centre: CGPoint, reference: CGSize)?
        if let calibration = data.cameraCalibrationData {
            let m = calibration.intrinsicMatrix
            let reference = calibration.intrinsicMatrixReferenceDimensions
            guard reference.width > 0, reference.height > 0 else { return nil }
            if let table = calibration.lensDistortionLookupTable {
                bend = (table, calibration.lensDistortionCenter, reference)
            }
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
        let lens = bend.flatMap {
            OwnLens(table: $0.table, centre: $0.centre, reference: $0.reference, orientation: orientation)
        }
        return OwnDepth(
            width: width, height: height, values: values, fx: fx, fy: fy, cx: cx, cy: cy, orientation: orientation,
            lens: lens
        )
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

/// The photograph just taken, standing as the camera's picture did, until
/// the AR session's picture comes: the camera changes hands after the
/// first photograph and is dark for a moment.
private struct OwnStill: View {
    let image: UIImage
    /// How the phone was held when it was taken.
    let quarter: Int

    var body: some View {
        GeometryReader { geo in
            let turned = quarter != 0
            Image(uiImage: image).resizable().scaledToFill()
                .frame(width: turned ? geo.size.height : geo.size.width, height: turned ? geo.size.width : geo.size.height)
                .clipped()
                // As the world stands, on a screen that stays upright.
                .rotationEffect(.degrees(Double(quarter) * 90))
                .frame(width: geo.size.width, height: geo.size.height)
        }
        .accessibilityHidden(true)
    }
}

/// What the hand feels while the scan's side photographs are taken
/// (Mateusz 2026-11-18 14:03 UTC: "dodaj haptykę - coraz szybsze tykanie i
/// potwierdzenie wykonania danej strony. Zaczyna tykać gdy zaczyna się
/// ruch w porządanym kierunku. (jak przy szukaniu airtaga)"): a tick at
/// each place along the way to a side (`OwnScanTicks`), stronger the
/// nearer, and the system's "done" when the side has its photograph.
@MainActor
final class OwnScanHaptics {
    private let tick = UIImpactFeedbackGenerator(style: .rigid)
    private let finished = UINotificationFeedbackGenerator()
    private var ticks = OwnScanTicks()

    /// The phone stands at `angle` on its way to the side whose
    /// photograph is meant from `target` (nil: none just now).
    func walked(to angle: Double, target: Double?) {
        guard let strength = ticks.walked(to: angle, target: target) else { return }
        tick.impactOccurred(intensity: strength)
        tick.prepare()
    }

    /// A side has its photograph.
    func done() {
        finished.notificationOccurred(.success)
        tick.prepare()
    }

    /// The scan is begun (anew): the way starts in front of the work.
    func rest() {
        ticks = OwnScanTicks()
        tick.prepare()
    }
}
