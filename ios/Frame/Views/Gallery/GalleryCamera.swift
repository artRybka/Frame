import SwiftUI
import UIKit

/// The grid's own measures (Mateusz 2026-11-24 18:31, 18:51: two views
/// only, the work on the whole screen and the grid): three columns of
/// small screens from edge to edge, thin gaps between them, three rows to
/// a screen. Every tile is the screen's own shape and cut as its page is
/// cut, so the way between a page and its tile is one picture growing or
/// shrinking, nothing swapped on the way.
struct GridMetrics: Equatable {
    static let columns = 3
    static let gap: CGFloat = 2
    /// Rows the grid is laid out for above the screen's top: the work
    /// drawn back in a quick run of swipes is past the top by the time it
    /// is a tile (`GalleryView.sweep`), and the wall round it is seen
    /// before that.
    static let rowsAbove = 4

    let area: CGSize
    let tile: CGSize

    init(area: CGSize, scale: CGFloat = 3) {
        self.area = area
        let columns = CGFloat(Self.columns)
        let width = max((area.width - Self.gap * (columns - 1)) / columns, 0)
        let height = area.width > 0 ? width * area.height / area.width : 0
        let scale = max(scale, 1)
        // A whole number of pixels: every row lies on the pixel grid.
        tile = CGSize(width: width, height: (height * scale).rounded() / scale)
    }

    /// From one row's top to the next.
    var pitch: CGFloat { tile.height + Self.gap }
    var above: CGFloat { CGFloat(Self.rowsAbove) * pitch }

    /// Where the nth cell lies in the grid, its first row's top at 0.
    func cell(_ n: Int) -> CGRect {
        let n = max(n, 0)
        return CGRect(
            x: CGFloat(n % Self.columns) * (tile.width + Self.gap), y: CGFloat(n / Self.columns) * pitch,
            width: tile.width, height: tile.height
        )
    }

    /// The cell at a point of the grid; nil in a gap or outside it.
    func index(at point: CGPoint) -> Int? {
        guard tile.width > 0, pitch > 0, point.x >= 0, point.y >= 0 else { return nil }
        let column = Int(point.x / (tile.width + Self.gap)), row = Int(point.y / pitch)
        guard column < Self.columns else { return nil }
        let n = row * Self.columns + column
        return cell(n).contains(point) ? n : nil
    }
}

/// Where the work shown lies between its page and its tile. The pages and
/// the grid are both drawn through it: the grid grown about the work's
/// tile till the tile is where the work is (`WallZoom`), the pages shrunk
/// into the same place over it (`WindowZoom`). One rectangle moves and
/// both follow, so the two can never part (Mateusz 2026-11-24 17:23:
/// "Powrót z siatki … bardzo skacze"; they were two layers set to meet by
/// two reckonings).
@MainActor @Observable final class GalleryCamera {
    /// The pages and the grid are drawn through it.
    var on = false
    /// The screen, and the work's tile where the grid has it at rest.
    var screen = CGRect.zero
    var tile = CGRect.zero
    /// Where the work's page lies now, the grid drawn round it.
    var hero = CGRect.zero
    /// Where the pages' window lies now: the page's own place, but for the
    /// page still on its way in from below (`GalleryView.sweep`).
    var window = CGRect.zero

    /// How far between the page (0) and the tile (1), and how far below
    /// that a finger has dragged it.
    @ObservationIgnored private(set) var z: CGFloat = 0
    @ObservationIgnored private(set) var drop: CGFloat = 0

    func pose(_ z: CGFloat, drop: CGFloat = 0) {
        self.z = min(max(z, 0), 1)
        self.drop = drop
        let rect = Self.between(screen, tile, self.z).offsetBy(dx: 0, dy: drop)
        hero = rect
        window = rect
    }

    /// The page drawn back `z` of the way into its tile: its width shrinks
    /// evenly to the eye (by the same share each moment), and it moves as
    /// it shrinks, about the one point that is the same in both.
    nonisolated static func between(_ page: CGRect, _ tile: CGRect, _ z: CGFloat) -> CGRect {
        guard page.width > 0, tile.width > 0, abs(page.width - tile.width) > 0.01 else { return z >= 0.5 ? tile : page }
        let z = min(max(z, 0), 1)
        let width = page.width * pow(tile.width / page.width, z)
        let share = (page.width - width) / (page.width - tile.width)
        let height = page.height + (tile.height - page.height) * share
        let middle = CGPoint(
            x: page.midX + (tile.midX - page.midX) * share, y: page.midY + (tile.midY - page.midY) * share
        )
        return CGRect(x: middle.x - width / 2, y: middle.y - height / 2, width: width, height: height)
    }

    /// Slow at both ends.
    nonisolated static func ease(_ t: CGFloat) -> CGFloat {
        let t = min(max(t, 0), 1)
        return t * t * (3 - 2 * t)
    }

    /// Quick, then settling.
    nonisolated static func out(_ t: CGFloat, power: CGFloat = 5) -> CGFloat {
        1 - pow(1 - min(max(t, 0), 1), power)
    }
}

/// The grid grown about the work's tile, the tile where the work is.
struct WallZoom: ViewModifier {
    let camera: GalleryCamera

    func body(content: Content) -> some View {
        let tile = camera.tile, hero = camera.hero, screen = camera.screen
        let on = camera.on && tile.width > 0 && screen.width > 0 && screen.height > 0
        content.modifier(
            Seen(
                scale: on ? hero.width / tile.width : 1,
                anchor: on
                    ? UnitPoint(x: (tile.midX - screen.minX) / screen.width, y: (tile.midY - screen.minY) / screen.height)
                    : .center,
                moved: on ? CGSize(width: hero.midX - tile.midX, height: hero.midY - tile.midY) : .zero
            ).ignoredByLayout()
        )
    }
}

/// Scaled about a point of its own and moved, to the eye only. With
/// `scaleEffect` and `offset` a scroll view near the screen's edges took
/// the way it had been moved for the safe area's: for the last tenth of
/// a second of the way from a tile the pages had 47 points, then 2, then
/// none above them, and were scrolled as far out of place (the probe's
/// trace of 2026-11-24).
private struct Seen: GeometryEffect {
    var scale: CGFloat
    var anchor: UnitPoint
    var moved: CGSize

    func effectValue(size: CGSize) -> ProjectionTransform {
        let about = CGPoint(x: anchor.x * size.width, y: anchor.y * size.height)
        return ProjectionTransform(
            CGAffineTransform(translationX: about.x + moved.width, y: about.y + moved.height)
                .scaledBy(x: scale, y: scale)
                .translatedBy(x: -about.x, y: -about.y)
        )
    }
}

/// The pages shrunk into the work's place.
struct WindowZoom: ViewModifier {
    let camera: GalleryCamera

    func body(content: Content) -> some View {
        let window = camera.window, screen = camera.screen
        let on = camera.on && window.width > 0 && screen.width > 0
        content.modifier(
            Seen(
                scale: on ? window.width / screen.width : 1, anchor: .center,
                moved: on ? CGSize(width: window.midX - screen.midX, height: window.midY - screen.midY) : .zero
            ).ignoredByLayout()
        )
    }
}

/// How fast the pages are swiped (points a second, down the works) and
/// where they are, for the grid to flow on as fast (Mateusz 2026-11-24
/// 14:06: "Prędkość powinna być zgodna z ostatnim machnięciem").
@MainActor final class SwipeFlow {
    private var samples: [(time: CFTimeInterval, speed: CGFloat)] = []
    private var last: (time: CFTimeInterval, y: CGFloat)?
    /// How far the pages are scrolled now.
    private(set) var y: CGFloat = 0

    func note(_ y: CGFloat) {
        let now = CACurrentMediaTime()
        if let last, now - last.time > 0.001 {
            samples.append((now, (y - last.y) / CGFloat(now - last.time)))
            samples.removeAll { now - $0.time > Self.window }
        }
        last = (now, y)
        self.y = y
    }

    /// The speed of the last moments, down the works (0 the other way).
    var speed: CGFloat {
        let now = CACurrentMediaTime()
        let late = samples.filter { now - $0.time <= Self.window }.map(\.speed)
        guard !late.isEmpty else { return 0 }
        return max(late.reduce(0, +) / CGFloat(late.count), 0)
    }

    private static let window: CFTimeInterval = 0.07
}

/// A step each frame of the screen: the work drawn back, the grid flowing
/// on after a swipe and slowing as a flicked list does.
@MainActor final class Coast: NSObject {
    private var link: CADisplayLink?
    private var start: CFTimeInterval = 0
    private var step: ((CFTimeInterval) -> Bool)?

    /// `step` is given the seconds since the start; false ends it.
    func run(_ step: @escaping (CFTimeInterval) -> Bool) {
        stop()
        self.step = step
        start = CACurrentMediaTime()
        let link = CADisplayLink(target: self, selector: #selector(tick))
        link.preferredFrameRateRange = CAFrameRateRange(minimum: 60, maximum: 120, preferred: 120)
        link.add(to: .main, forMode: .common)
        self.link = link
    }

    func stop() {
        link?.invalidate()
        link = nil
        step = nil
    }

    var running: Bool { link != nil }

    @objc private func tick(_ link: CADisplayLink) {
        guard let step else { return }
        let ran = self.link
        // Ended, unless the step started another run itself.
        if !step(max(link.targetTimestamp - start, 0)), self.link === ran { stop() }
    }
}

/// Telling swiping past from looking: so many works in a row, each left
/// this soon (Mateusz 2026-11-24 08:30: "nie pojedyncze dzieło tylko
/// serię"). Each left within a second and a half: no work is looked at
/// that soon (12:06: "dzieła nie da się obejrzeć w 0,8 sekundy"; six
/// under 0.8 s was too slow to come). Eight of them: four came too soon
/// (17:23: "po 2x większej ilości szybkooglądanych dzieł niż teraz").
struct SwipeSpeed {
    static let run = 8
    static let quick: TimeInterval = 1.5

    private var times: [Date] = []

    /// A work reached; true when the run is quick enough for the grid.
    mutating func reached(at now: Date = .now) -> Bool {
        times.append(now)
        if times.count > Self.run { times.removeFirst(times.count - Self.run) }
        guard times.count == Self.run else { return false }
        return zip(times, times.dropFirst()).allSatisfy { $1.timeIntervalSince($0) < Self.quick }
    }

    mutating func reset() { times = [] }
}

/// The works swiped to one after another, told from the pages' scroll
/// itself: a work is reached once most of it is in, still on its way, so
/// the grid can come while the pages move (Mateusz 2026-11-24 19:12: the
/// drawing back "w biegu").
@MainActor final class SwipeRun {
    /// How much of a page is in when it counts as reached.
    static let reachedAt: CGFloat = 0.65

    private var speed = SwipeSpeed()
    private var last = 0

    /// The pages scrolled to `y`, each `height` tall: the page reached when
    /// that ends a quick run down the works, else nil.
    func scrolled(to y: CGFloat, height: CGFloat, at now: Date = .now) -> Int? {
        guard height > 0 else { return nil }
        let at = Int((y / height + (1 - Self.reachedAt)).rounded(.down))
        guard at != last else { return nil }
        let forward = at > last
        last = at
        guard forward else {
            speed.reset()
            return nil
        }
        return speed.reached(at: now) ? at : nil
    }

    func reset(at index: Int) {
        speed.reset()
        last = index
    }
}

/// Where on the screen a swipe down asks for the grid (Mateusz 2026-11-24
/// 19:28: "machnięcie w dół może mieć dwie funkcje - w zależności od tego
/// z którego punktu przeciągamy"; 19:30: "blisko górną połowę ekranu";
/// 19:31: "ustalać te granice na podstawie pierwszych machnięć do góry …
/// sprawdzić gdzie jest granica powyżej nich"): above the line the grid,
/// below it the work before, as ever. The line is learnt from where the
/// swipes up start, the thumb's own place: a little above the highest of
/// them, and never outside a sensible band, so the grid can always be
/// reached and a swipe from the thumb's place never brings it.
enum SwipeZone {
    static let key = "gallery.swipe.starts"
    /// Swipes remembered, and how many it takes before they move the line.
    static let kept = 40
    static let few = 6
    /// The line before anything is learnt, as a share of the screen's
    /// height from its top, and the band it stays in.
    static let first = 0.45
    static let band = 0.25 ... 0.5
    /// How far above the swipes the line is put.
    static let margin = 0.06

    /// The line for swipes up that started at these shares of the height.
    static func line(_ starts: [Double]) -> Double {
        guard starts.count >= few else { return first }
        let sorted = starts.sorted()
        // The highest of them, but for a stray one in ten.
        let high = sorted[min(Int(Double(sorted.count) * 0.1), sorted.count - 1)]
        return min(max(high - margin, band.lowerBound), band.upperBound)
    }

    @MainActor private static var starts: [Double] = (UserDefaults.standard.array(forKey: key) as? [Double]) ?? []

    /// The line as learnt so far.
    @MainActor static var current: Double { line(starts) }

    /// A swipe up started at this share of the screen's height.
    @MainActor static func note(_ share: Double) {
        guard share > 0, share < 1 else { return }
        starts.append(share)
        if starts.count > kept { starts.removeFirst(starts.count - kept) }
        UserDefaults.standard.set(starts, forKey: key)
    }
}

/// `-galleryLog <path>` (the simulator's probe, `GalleryProbeTests`): what
/// Galeria did and when, a line each.
enum GalleryLog {
    @MainActor private static let path = UserDefaults.standard.string(forKey: "galleryLog")
    /// Every frame of a move, with `-galleryTrace YES` beside the log.
    @MainActor private static let traced = UserDefaults.standard.bool(forKey: "galleryTrace")

    @MainActor static func trace(_ what: @autoclosure () -> String) {
        if traced { note(what()) }
    }

    @MainActor static func note(_ what: @autoclosure () -> String) {
        guard let path else { return }
        // The clock's own time, as the probe's steps and the film have it.
        let line = String(format: "%.3f %@\n", Date().timeIntervalSince1970, what())
        guard let data = line.data(using: .utf8) else { return }
        if let file = FileHandle(forWritingAtPath: path) {
            file.seekToEndOfFile()
            file.write(data)
            try? file.close()
        } else {
            FileManager.default.createFile(atPath: path, contents: data)
        }
    }
}
