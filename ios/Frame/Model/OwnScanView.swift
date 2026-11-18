import CoreGraphics
import Foundation

/// Where a flat work on the wall shows in the camera's picture when the
/// phone stands off to the side of it, as far away and aiming at its
/// middle (the scan of three, Mateusz 2026-11-16: "pierwsze zdjęcie na
/// wprost, a kolejne pod większym kątem z ramką pomocniczą na ekranie
/// pokazująca gdzie ma się znajdować dzieło"). From the work's outline in
/// the first photograph comes the helper frame for the side ones: the
/// shape that outline takes from 30° to the left and to the right.
enum OwnScanView {
    /// How far to the side the side photographs are taken, in degrees: a
    /// lamp's reflection moves about a third of a metre across the work
    /// from a metre away, while the work's far side is 13 % narrower.
    static let side = 30.0
    /// The side photograph is taken between these (the frame is a guide,
    /// not a gauge).
    static let near = 22.0 ... 38.0
    /// The main camera's focal length in half-widths of the upright picture
    /// (26 mm equivalent: 69° across the sensor's long side).
    static let focal = 1.94

    /// A point of the front view (0–1 across and down a picture `aspect`
    /// wide to high) as seen from `degrees` to the side: negative from
    /// the left, where the work's left side comes nearer and taller.
    /// `centre`: the work's middle in the front view, which the camera
    /// keeps aiming at.
    static func seen(
        _ point: CGPoint, from degrees: Double, centre: CGPoint, aspect: Double = 0.75, focal: Double = OwnScanView.focal
    ) -> CGPoint {
        let turn = degrees * .pi / 180
        // Across and down from the middle, in focal lengths.
        let a = Double(point.x - centre.x) * 2 / focal
        let b = Double(point.y - centre.y) * 2 / aspect / focal
        let depth = max(1 - a * sin(turn), 0.05)
        return CGPoint(
            x: Double(centre.x) + a * cos(turn) / depth * focal / 2,
            y: Double(centre.y) + b / depth * focal * aspect / 2
        )
    }

    /// The outline `corners` (top left, top right, bottom right, bottom
    /// left, 0–1) as seen from `degrees` to the side.
    static func seen(
        _ corners: [CGPoint], from degrees: Double, aspect: Double = 0.75, focal: Double = OwnScanView.focal
    ) -> [CGPoint] {
        guard !corners.isEmpty else { return [] }
        let centre = middle(corners)
        return corners.map { seen($0, from: degrees, centre: centre, aspect: aspect, focal: focal) }
    }

    static func middle(_ corners: [CGPoint]) -> CGPoint {
        let n = CGFloat(max(corners.count, 1))
        return CGPoint(x: corners.map(\.x).reduce(0, +) / n, y: corners.map(\.y).reduce(0, +) / n)
    }

    /// From how far to the side an outline is seen, in degrees (negative:
    /// from the left), by how much taller its left side is than its right:
    /// the opposite of `seen`. `front`: the same outline from the front.
    static func angle(of outline: [CGPoint], front: [CGPoint], aspect: Double = 0.75) -> Double? {
        guard outline.count == 4, front.count == 4 else { return nil }
        func lean(_ q: [CGPoint]) -> Double {
            let left = Double(hypot(q[3].x - q[0].x, q[3].y - q[0].y))
            let right = Double(hypot(q[2].x - q[1].x, q[2].y - q[1].y))
            return right > 0 ? log(left / right) : 0
        }
        let seenLean = lean(outline) - lean(front)
        // The lean grows evenly enough with the angle to look it up.
        var best: (angle: Double, off: Double)?
        for step in -120 ... 120 {
            let degrees = Double(step) / 2
            let off = abs(lean(seen(front, from: degrees, aspect: aspect)) - lean(front) - seenLean)
            if best == nil || off < best!.off { best = (degrees, off) }
        }
        return best?.angle
    }

    // MARK: Reading an outline

    /// Four corners in the order top left, top right, bottom right,
    /// bottom left, whatever order they came in.
    static func ordered(_ corners: [CGPoint]) -> [CGPoint] {
        guard corners.count == 4 else { return corners }
        let sums = corners.map { $0.x + $0.y }, differences = corners.map { $0.x - $0.y }
        let topLeft = sums.indices.min { sums[$0] < sums[$1] }!, bottomRight = sums.indices.max { sums[$0] < sums[$1] }!
        let topRight = differences.indices.max { differences[$0] < differences[$1] }!
        let bottomLeft = differences.indices.min { differences[$0] < differences[$1] }!
        guard Set([topLeft, topRight, bottomRight, bottomLeft]).count == 4 else { return corners }
        return [corners[topLeft], corners[topRight], corners[bottomRight], corners[bottomLeft]]
    }

    /// The outline's sides in half-widths of the picture (`aspect` wide to high).
    static func sides(_ q: [CGPoint], aspect: Double = 0.75) -> (left: Double, right: Double, top: Double, bottom: Double) {
        func length(_ a: CGPoint, _ b: CGPoint) -> Double {
            hypot(Double(a.x - b.x) * 2, Double(a.y - b.y) * 2 / aspect)
        }
        return (length(q[0], q[3]), length(q[1], q[2]), length(q[0], q[1]), length(q[3], q[2]))
    }

    /// The work's height to its width, from its outline seen from the front.
    static func shape(of front: [CGPoint], aspect: Double = 0.75) -> Double? {
        guard front.count == 4 else { return nil }
        let s = sides(front, aspect: aspect)
        guard s.top + s.bottom > 0 else { return nil }
        return (s.left + s.right) / (s.top + s.bottom)
    }

    /// From how far to the side an outline is seen, in degrees (negative:
    /// from the left). A side's height on the picture says how far away it
    /// is; the work's `shape` (height to width) says how far apart its two
    /// sides are, so the difference of their depths is the angle's sine,
    /// whatever the distance.
    static func turn(of outline: [CGPoint], shape: Double, aspect: Double = 0.75, focal: Double = OwnScanView.focal) -> Double? {
        guard outline.count == 4 else { return nil }
        let s = sides(outline, aspect: aspect)
        guard s.left > 0, s.right > 0 else { return nil }
        let sine = -shape * focal * (1 / s.right - 1 / s.left)
        return asin(max(-1, min(1, sine))) * 180 / .pi
    }

    /// How far the phone is from the work now, in its distances at the
    /// front photograph (1: as far).
    static func away(_ outline: [CGPoint], front: [CGPoint], aspect: Double = 0.75) -> Double? {
        guard outline.count == 4, front.count == 4 else { return nil }
        let now = sides(outline, aspect: aspect), then = sides(front, aspect: aspect)
        guard now.left > 0, now.right > 0 else { return nil }
        return (then.left + then.right) / 2 * (1 / now.left + 1 / now.right) / 2
    }

    /// All of the outline is in the picture, a little off its edges.
    static func fits(_ outline: [CGPoint]) -> Bool {
        outline.allSatisfy { (0.015 ... 0.985).contains($0.x) && (0.015 ... 0.985).contains($0.y) }
    }

    // MARK: The phone on its side

    /// A point of the screen's picture (the app stays upright) where it is
    /// in the picture as the world stands. `quarter`: 0 the phone upright,
    /// 1 its top to the left, -1 to the right. With the top to the left
    /// the screen's top edge is the world's left and its right edge the
    /// world's top (they were the other way round until 1.145.189, which
    /// turned the world upside down: Mateusz 2026-11-16 "Nie obsługuje
    /// robienia zdjęcia w poziomie").
    static func upright(_ p: CGPoint, quarter: Int) -> CGPoint {
        switch quarter {
        case 1: CGPoint(x: p.y, y: 1 - p.x)
        case -1: CGPoint(x: 1 - p.y, y: p.x)
        default: p
        }
    }

    /// The opposite of `upright`: back onto the screen.
    static func shown(_ p: CGPoint, quarter: Int) -> CGPoint {
        switch quarter {
        case 1: CGPoint(x: 1 - p.y, y: p.x)
        case -1: CGPoint(x: p.y, y: 1 - p.x)
        default: p
        }
    }

    // MARK: What to say

    /// Before the first photograph: the work whole in the picture, large
    /// enough, seen from the front.
    static func first(_ outline: [CGPoint]?, aspect: Double = 0.75) -> OwnScanAdvice {
        guard let outline, outline.count == 4 else { return .lost }
        guard fits(outline) else { return .farther }
        let xs = outline.map(\.x), ys = outline.map(\.y)
        if xs.max()! - xs.min()! < small, ys.max()! - ys.min()! < small { return .nearer }
        let s = sides(outline, aspect: aspect)
        guard s.left > 0, s.right > 0, s.top > 0, s.bottom > 0 else { return .lost }
        // One side taller: seen from the side. The top or the bottom wider:
        // the phone leans back or forth.
        if abs(log(s.left / s.right)) > askew { return .straight }
        if abs(log(s.top / s.bottom)) > askew { return .level }
        return .hold
    }

    /// Before a side photograph meant from `target` degrees: the phone
    /// stands at `angle`, `away` times as far as at the front one.
    /// `held`: the photograph is being taken already, which a little
    /// more to either side or a step back does not stop.
    /// `aim`: how far the work's middle is from the picture's (`offAim`;
    /// 0 when the camera does not see the work). `seen`: the camera sees
    /// the work's four corners now (true where it never did, and there is
    /// nothing to wait for). `stray`: how far the phone has turned since
    /// the camera last found the work (degrees, as the angle counts).
    static func side(
        target: Double, angle: Double, away: Double = 1, fits: Bool = true, aim: Double = 0, seen: Bool = true,
        held: Bool = false, stray: Double = 0
    ) -> OwnScanAdvice {
        // Cut off because the phone looks past it, or because it is too near.
        guard fits else { return aim > aimed ? .aim : .farther }
        if away > (held ? far + give / 20 : far) { return .nearer }
        let range = held ? (near.lowerBound - give) ... (near.upperBound + give) : near
        if (angle < 0) == (target < 0), range.contains(abs(angle)) {
            // Standing right: the whole work in the picture, its middle in
            // the picture's (Mateusz 2026-11-16 13:36 UTC: "łapanie
            // narożników, żeby na pewno ująć cały obraz przy zdjęciu pod
            // kątem").
            guard seen else { return .corners }
            return aim > (held ? aimed + aimGive : aimed) ? .aim : .hold
        }
        // Walking to the left while aiming at the work turns the phone to
        // the right. Turned the way the arrows point instead, it looks
        // away from the work and stands where it stood (Mateusz
        // 2026-11-16 15:02 UTC: "Odruchem przy pokazanych strzałkach jest
        // samo przekręcenie telefonu w lewo gdy strzałki pokazują żeby
        // przejść w lewo").
        let left = angle > target
        if (left ? stray : -stray) > strayed { return .turned(left: left) }
        return .go(left: left)
    }

    /// Turned so far (degrees) the wrong way since the camera last found
    /// the work, the phone was turned where he was to walk.
    static let strayed = 10.0

    /// How far the work's middle may be from the picture's at a side
    /// photograph, in the picture's short sides: the sight's ring.
    static let aimed = 0.11
    /// How much farther a photograph being taken goes on.
    static let aimGive = 0.04

    /// How far the middle of an outline is from the picture's middle, in
    /// the picture's short sides (`aspect` wide to high). Walking to the
    /// side with the phone looking straight on, the work leaves the
    /// picture; it is to be aimed at (Mateusz 2026-11-16 13:35 UTC:
    /// "jakiś znacznik (celownik) powinien trzymać środek dzieła przy
    /// robieniu zdjęć pod kątem").
    static func offAim(_ outline: [CGPoint], aspect: Double = 0.75) -> Double {
        let m = middle(outline)
        return hypot(Double(m.x - 0.5) * max(1, aspect), Double(m.y - 0.5) * max(1, 1 / aspect))
    }

    /// How far beyond `near` (degrees) a photograph being taken goes on.
    static let give = 3.0

    /// The work takes less of the picture than this across and down: come nearer.
    static let small = 0.5
    /// Opposite sides differ by more than this (their ratio's logarithm):
    /// it is not seen from the front.
    static let askew = 0.08
    /// Farther than at the front photograph by more than this: come nearer.
    static let far = 1.3

    /// How well a live outline lies in the helper frame: the largest
    /// distance between their corners, in picture widths.
    static func off(_ outline: [CGPoint], frame: [CGPoint]) -> Double {
        guard outline.count == frame.count, !outline.isEmpty else { return 1 }
        return zip(outline, frame).map { Double(hypot($0.x - $1.x, $0.y - $1.y)) }.max() ?? 1
    }
}

/// Where the phone stands, in degrees to the side of the work: the
/// gyroscope's smooth count, drawn slowly towards what the work's outline
/// says whenever the two agree (the gyroscope drifts and knows nothing of
/// where he aims; the outline trembles and is not always seen).
struct OwnScanAngle: Equatable {
    /// What the outline has added to the gyroscope's count so far.
    private(set) var offset = 0.0
    /// The gyroscope's count when the camera last found the work (or the
    /// last photograph was taken).
    private(set) var sighted = 0.0

    /// The outline is believed when it is this near the count (another
    /// rectangle on the wall is not the work).
    static let agree = 20.0
    /// How much of the difference one look at the outline takes away.
    static let pull = 0.25

    /// The angle now, whether the outline was believed, and how far the
    /// phone has turned since the camera last found the work. `gyro`: the
    /// gyroscope's count (nil without one); `seen`: the outline's;
    /// `fresh`: the camera has just looked (between its looks the outline
    /// is the last one, which the count must not be drawn to: turned
    /// away from the work in that while, the phone seemed to stand
    /// still and the count went wrong for good).
    mutating func fuse(gyro: Double?, seen: Double?, fresh: Bool = true) -> (angle: Double?, seen: Bool, stray: Double) {
        guard let gyro else { return (seen, seen != nil, 0) }
        guard let seen, abs(seen - gyro - offset) < Self.agree else { return (gyro + offset, false, gyro - sighted) }
        if fresh {
            offset += (seen - gyro - offset) * Self.pull
            sighted = gyro
        }
        return (gyro + offset, true, gyro - sighted)
    }

    /// A photograph is taken with the gyroscope's count at `gyro`: the
    /// phone's turns are counted from here.
    mutating func rest(gyro: Double) {
        sighted = gyro
    }
}

/// What the helper says, held until something else has been true for a
/// moment: at the edge of "come nearer" or of the side photograph's angle
/// the word under the picture flickered between two (Mateusz 2026-11-16:
/// "ramki podpowiedzi, ich skakanie").
struct OwnScanSteady: Equatable {
    private(set) var said = OwnScanAdvice.lost
    private var next: OwnScanAdvice?
    private var since = Date.distantPast

    /// How long something else must be true before it is said.
    static let settle: TimeInterval = 0.25

    mutating func take(_ advice: OwnScanAdvice, at now: Date = .now) -> OwnScanAdvice {
        guard advice != said else {
            next = nil
            return said
        }
        if next != advice {
            next = advice
            since = now
        }
        if now.timeIntervalSince(since) >= Self.settle {
            said = advice
            next = nil
        }
        return said
    }
}

/// What the camera's helper says of the work as the phone sees it.
enum OwnScanAdvice: Equatable {
    /// No outline of the work is seen.
    case lost
    case nearer
    case farther
    /// Stand in front of it.
    case straight
    /// Hold the phone upright, at the work's height: it leans back or forth.
    case level
    /// Walk on, to the left or to the right.
    case go(left: Bool)
    /// The phone was turned where he was to walk (to the left or to
    /// the right): it looks away from the work.
    case turned(left: Bool)
    /// The phone is held another way (upright, on its side) than at the
    /// first photograph.
    case rolled
    /// Standing right, but the phone looks past the work: aim at it.
    case aim
    /// Standing right, but the work's four corners are not all seen.
    case corners
    /// The first photograph is taken: round the work now, to the left or
    /// to the right, whichever he likes.
    case either
    /// As it should be: keep still, the photograph is being taken.
    case hold
}

/// The side photographs of a scan, taken as the phone goes round the work
/// in one arc (Mateusz 2026-11-18 13:35 UTC, after the marks pinned to
/// the work: "może da się to zbudować jeszcze lepiej, intuicyjniej i
/// szybciej… Może kolejne zdjęcia nie muszą być dokładnie pod 30° i
/// trzeba pozwolić na więcej skanów pod różnymi kątami?"; he chose "Jeden
/// łuk", and 14:03 UTC: "po zdjęciu na wprost można pójść w lewo albo w
/// prawo"). A side is done with a photograph from where the scan's were
/// always taken (`OwnScanView.near`), whichever side comes first; on the
/// way out to it one more is taken in passing, from nearer the front. The
/// server makes the scan of the one nearest 30° from each side and keeps
/// the others, to learn from how small an angle is enough.
struct OwnScanArc: Equatable {
    /// From how far to the side each side photograph was taken (degrees;
    /// negative: from the work's left), in the order they were taken.
    private(set) var taken: [Double] = []

    /// Where the one more is taken on the way out to a side.
    static let early = 12.0 ... 20.0
    /// Nearer the front than this with neither side done, he has not
    /// chosen a side yet.
    static let undecided = 6.0

    /// The side has its photograph.
    func done(left: Bool) -> Bool {
        taken.contains { ($0 < 0) == left && OwnScanView.near.contains(abs($0)) }
    }

    var finished: Bool { done(left: true) && done(left: false) }

    /// The side meant now, as the place its photograph is meant from
    /// (∓`OwnScanView.side`): with one side done the other, with neither
    /// the one he is walking to. Nil in front of the work with neither
    /// done (either way will do), and with both.
    func target(at angle: Double) -> Double? {
        let left = done(left: true), right = done(left: false)
        if left, right { return nil }
        if left { return OwnScanView.side }
        if right { return -OwnScanView.side }
        guard abs(angle) >= Self.undecided else { return nil }
        return angle < 0 ? -OwnScanView.side : OwnScanView.side
    }

    /// Where a photograph is taken from when the phone cannot say where
    /// it stands (he presses the shutter): the left, then the right.
    var next: Double { done(left: true) ? OwnScanView.side : -OwnScanView.side }

    /// The server takes more than two side photographs, and makes the
    /// scan of the right ones, from this version. One before it took the
    /// first two that came, whichever they were: it is sent no extra
    /// ones (nor is one whose version is not known).
    static let server = "1.145.241"

    static func extras(server version: String?) -> Bool {
        version.map { !ServerUpdatePrompt.isOlder($0, than: server) } ?? false
    }

    /// One more photograph is wanted here, in passing: on the way out to
    /// a side that has none yet.
    func early(at angle: Double) -> Bool {
        let left = angle < 0
        return Self.early.contains(abs(angle)) && !taken.contains { ($0 < 0) == left }
    }

    mutating func took(_ angle: Double) {
        taken.append(angle)
    }
}

/// The ticking on the way to a side (Mateusz 2026-11-18 14:03 UTC: "dodaj
/// haptykę - coraz szybsze tykanie i potwierdzenie wykonania danej strony.
/// Zaczyna tykać gdy zaczyna się ruch w porządanym kierunku. (jak przy
/// szukaniu airtaga)"). A tick is felt at each of the places along the
/// way, and they lie closer and closer together towards where the
/// photograph is taken: walking on, the ticks come faster and faster;
/// standing, or walking the other way, there are none.
struct OwnScanTicks: Equatable {
    /// Each place leaves this much of the way that was left at the one before.
    static let ratio = 0.8
    /// The places along one way.
    static let most = 16
    /// No two ticks nearer than this (seconds): the last ones run together.
    static let gap: TimeInterval = 0.055

    /// How many of the places lie behind one who has gone `part` (0–1)
    /// of the way.
    static func behind(_ part: Double) -> Int {
        guard part > 0 else { return 0 }
        guard part < 1 else { return most }
        return min(most, Int(log(1 - part) / log(ratio)))
    }

    private var target: Double?
    /// Where the way began (degrees to the side of the work).
    private var from = 0.0
    private var heard = 0
    private var last = Date.distantPast

    /// The phone stands at `angle` on its way to the side whose
    /// photograph is meant from `target` (nil: none is meant just now).
    /// How strong a tick is to be felt now (0–1), or none.
    mutating func walked(to angle: Double, target: Double?, at now: Date = .now) -> Double? {
        guard let target else {
            if self.target != nil { self = OwnScanTicks() }
            return nil
        }
        if target != self.target {
            // From the front at first; to the other side, from where he stands.
            from = self.target == nil ? 0 : angle
            self.target = target
            heard = 0
        }
        let edge = target < 0 ? -OwnScanView.near.lowerBound : OwnScanView.near.lowerBound
        // Gone the other way first: the way is counted from the farthest he went.
        if (angle - from) * (edge - from) < 0 { from = angle }
        let way = edge - from
        guard abs(way) > 1 else { return nil }
        let part = (angle - from) / way
        let behind = Self.behind(part)
        // Walked back a stretch: it ticks again when he goes on.
        if behind < heard - 1 { heard = behind }
        guard behind > heard, now.timeIntervalSince(last) >= Self.gap else { return nil }
        heard = behind
        last = now
        return 0.35 + 0.65 * min(1, max(0, part))
    }
}
