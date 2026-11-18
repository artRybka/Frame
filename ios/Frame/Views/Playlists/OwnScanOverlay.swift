import SwiftUI

/// What the scan's camera draws over its picture and says under it
/// (Mateusz 2026-11-16: "pierwsze zdjęcie na wprost, a kolejne pod większym
/// kątem z ramką pomocniczą na ekranie pokazująca gdzie ma się znajdować
/// dzieło"; 09:52 UTC: no shutter, "skoro zdjęcie robi się samo", and the
/// helper says to come nearer or step back). The camera fills it from what
/// it sees, the screenshots' scene from a look's name.
struct OwnScanLook: Equatable {
    /// Which step of the scan this is: 1, the first photograph from the
    /// front; 2, the ones from the sides, taken on one walk round the
    /// work (`OwnScanArc`).
    var number = 1
    var advice = OwnScanAdvice.lost
    /// The work's outline as the camera sees it now (0–1 on the screen's
    /// picture): drawn whole before the first photograph, as its four
    /// corners before a side one.
    var live: [CGPoint]?
    /// The left side has its photograph, and the right.
    var left = false
    var right = false
    /// From how far to the side the side photographs so far were taken.
    var shots: [Double] = []
    /// How much of the way to the left and to the right is walked
    /// (degrees from the front, `OwnScanArc.filled`).
    var filled = [0.0, 0.0]
    /// The work has not been seen for a while: he takes the photograph himself.
    var manual = false
    /// Little light: the photograph may come out blurred or grainy.
    var dim = false
    /// Where the phone stands, in degrees to the side of the work
    /// (negative: to its left); nil before the first photograph.
    var angle: Double?
    /// How the phone is held: 0 upright, 1 its top to the left, -1 to the
    /// right. The app's screen stays upright, so what is said over the
    /// picture is turned to be read.
    var quarter = 0

    static let good = Color(red: 0.36, green: 0.86, blue: 0.48)
    static let wait = Color(red: 1.0, green: 0.80, blue: 0.30)

    var matched: Bool { advice == .hold }

    /// Which way he is to walk now (true: to the left); nil when not.
    var walk: Bool? {
        switch advice {
        case .go(let left), .turned(let left): number > 1 ? left : nil
        default: nil
        }
    }

    /// He is to walk round the work now, whichever way.
    var either: Bool { number > 1 && advice == .either }

    /// Beyond where a side's photograph is taken, and told to come back.
    private var beyond: Bool {
        guard case .go(let left) = advice, let angle else { return false }
        return abs(angle) > OwnScanView.near.upperBound && left == (angle > 0)
    }

    /// The word over the picture.
    var pill: (text: String, symbol: String, colour: Color)? {
        switch advice {
        case .hold: ("Nie ruszaj", "camera.aperture", Self.good)
        case .nearer: ("Podejdź bliżej", "arrow.up.left.and.arrow.down.right", Self.wait)
        case .farther: ("Odsuń się", "arrow.down.right.and.arrow.up.left", Self.wait)
        case .straight: ("Stań na wprost", "arrow.left.and.right", Self.wait)
        case .level: ("Trzymaj telefon prosto", "iphone", Self.wait)
        case .aim: ("Wyceluj w dzieło", "scope", Self.wait)
        case .turned: ("Nie obracaj telefonu", "iphone", Self.wait)
        case .rolled: ("Nie obracaj telefonu", "iphone", Self.wait)
        case .corners: ("Pokaż całe dzieło", "viewfinder", Self.wait)
        case .lost where manual: ("Nie widzę krawędzi dzieła", "viewfinder", .white)
        default: nil
        }
    }

    /// The line under the picture.
    var line: String {
        let side = (angle ?? 0) < 0 ? "lewej" : "prawej"
        switch advice {
        case .hold: return number == 1 ? "Dobrze. Robię zdjęcie na wprost" : "Dobrze. Robię zdjęcie z \(side)"
        case .nearer: return "Dzieło jest za małe w kadrze"
        case .farther: return "Dzieło nie mieści się w kadrze"
        case .straight: return "Dzieło widać z boku"
        case .level: return "Telefon jest pochylony"
        case .aim: return "Dzieło ucieka z kadru"
        case .turned(let left): return "Zrób krok w \(left ? "lewo" : "prawo"), a telefon skieruj na dzieło"
        case .rolled: return "Trzymaj telefon tak jak przy pierwszym zdjęciu"
        case .corners where manual: return "Zrób zdjęcie sam, gdy całe dzieło jest w kadrze"
        case .corners: return "Nie widzę wszystkich narożników dzieła"
        case .lost where manual: return "Zrób zdjęcie sam"
        case .go where number > 1 && beyond: return "Za daleko w bok, wróć trochę"
        case .go(let to) where number > 1:
            let way = to ? "lewo" : "prawo"
            // One side has its photograph: the other now.
            if left != right { return "\(left ? "Lewa" : "Prawa") strona gotowa, teraz w \(way)" }
            return "Przejdź łukiem w \(way), celując w dzieło"
        default: break
        }
        return number == 1 ? "Stań na wprost dzieła, całe w kadrze" : "Przejdź łukiem w lewo albo w prawo"
    }

    /// The smaller line under it.
    var note: String {
        switch advice {
        case .nearer: "Im bliżej, tym więcej szczegółów na zdjęciu."
        case .farther: "Całe ma być widoczne, z kawałkiem ściany wokół."
        case .straight: "Przesuń się tak, żeby lewy i prawy bok dzieła były równej wysokości."
        case .level: "Trzymaj go pionowo, na wysokości środka dzieła."
        case .aim: "Obróć telefon tak, żeby całe dzieło było w kadrze."
        case .turned: "Dzieło trzeba zobaczyć z boku. Sam obrót telefonu tego nie da."
        case .rolled: "Wszystkie zdjęcia mają być zrobione tak samo: pionowo albo poziomo."
        case .corners: "Cztery narożniki mają być w kadrze, z kawałkiem ściany wokół."
        case _ where dim: "Mało światła, zdjęcie może wyjść nieostre. Zapal światło, jeśli możesz."
        case .lost where manual: "Tak bywa przy ciemnej ramie na ciemnej ścianie albo w słabym świetle."
        default:
            number == 1
                ? "Zdjęcie zrobi się samo, gdy obrys zrobi się zielony."
                : "Zwolnij, gdy kropka wejdzie na jasny pas. Zdjęcie zrobi się samo."
        }
    }
}

/// What is drawn over the camera's picture: before the first photograph
/// the work's outline as the camera finds it; before a side one its four
/// corners. Under them the way round the work seen from above
/// (`OwnScanPlan`), on which a dot goes where the phone goes, to the
/// stretch on either side where a photograph is taken (Mateusz
/// 2026-11-16 12:58 UTC: "może wpadniesz na jakiś jeszcze lepszy - np.
/// celowanie AR? jakieś znaczniki? chciałbym żeby było to możliwie
/// intuicyjne": one thing to watch, moved by the one thing he does,
/// walking). Arrows the way to walk, and a ring that fills while the
/// photograph is taken ("trzeba dodać jakiś wskaźnik
/// wykonywania zdjęcia - np. wypełniający się okrąg?").
struct OwnScanOverlay: View {
    let look: OwnScanLook
    /// Since when all has been as the photograph needs it.
    var holding: Date? = nil
    /// The camera is taking the photograph.
    var taking = false

    /// The word over the picture: on its side the phone's own lines under
    /// the picture lie sideways (and are not shown: Mateusz 2026-11-16
    /// 15:02 UTC "tekst u dołu ekranu się nie obraca i zostaje bokiem"),
    /// so the line is said here too, with the smaller one under it.
    private var word: (text: String, symbol: String?, colour: Color)? {
        if let pill = look.pill { return (pill.text, pill.symbol, pill.colour) }
        return look.quarter == 0 ? nil : (look.line, nil, .white)
    }

    var body: some View {
        GeometryReader { geo in
            let turned = look.quarter != 0
            ZStack {
                // In the picture's own frame: with the phone on its side
                // what is said below is as wide as the picture is tall, the
                // stack grew to that, and the outline, drawn across all it
                // is given, came out a third longer than the work each way
                // (Mateusz 2026-11-16 18:49 UTC: "błędna (za wysoka) ramka
                // wykrycia dzieła dotyczy robienia skanu w poziomie").
                ZStack { drawn(geo.size) }
                    .frame(width: geo.size.width, height: geo.size.height)
                // As the world stands, whichever way the phone is held.
                said
                    .frame(width: turned ? geo.size.height : geo.size.width, height: turned ? geo.size.width : geo.size.height)
                    .rotationEffect(.degrees(Double(look.quarter) * 90))
            }
            .frame(width: geo.size.width, height: geo.size.height)
        }
        .animation(.easeOut(duration: 0.2), value: look.advice)
        .animation(.easeInOut(duration: 0.3), value: look.quarter)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(look.pill?.text ?? look.line)
    }

    /// The outlines, where they are on the screen.
    @ViewBuilder
    private func drawn(_ size: CGSize) -> some View {
        if look.number == 1, let live = look.live {
            OutlineShape(corners: live)
                .stroke(look.matched ? OwnScanLook.good : OwnScanLook.wait,
                        style: StrokeStyle(lineWidth: look.matched ? 4 : 2.5, lineJoin: .round))
                .shadow(color: .black.opacity(0.45), radius: 3)
                // From one look of the camera to the next, not in jumps.
                .animation(.linear(duration: 0.14), value: live)
                .transition(.opacity)
        } else if look.number > 1 {
            if let live = look.live {
                // The four corners the photograph must hold.
                let whole = OwnScanView.fits(live)
                OutlineShape(corners: live, marks: 0.2)
                    .stroke(look.matched ? OwnScanLook.good : whole ? .white : OwnScanLook.wait,
                            style: StrokeStyle(lineWidth: look.matched ? 5 : 4, lineCap: .round, lineJoin: .round))
                    .shadow(color: .black.opacity(0.45), radius: 3)
                    .animation(.linear(duration: 0.14), value: live)
                    .transition(.opacity)
            }
        }
    }

    /// The arrows, the ring, the plan and the word.
    private var said: some View {
        let turned = look.quarter != 0
        return ZStack {
            // Which way to walk; both ways while either will do.
            ForEach([true, false], id: \.self) { left in
                if look.either || look.walk == left {
                    OwnScanArrows(left: left)
                        .frame(maxWidth: .infinity, alignment: left ? .leading : .trailing)
                        .padding(.horizontal, 12)
                        .transition(.opacity)
                }
            }
            if holding != nil || taking {
                OwnShotRing(since: holding, taking: taking)
            }
            VStack(spacing: turned ? 8 : 10) {
                OwnScanPlan(
                    front: look.number > 1, left: look.left, right: look.right, shots: look.shots,
                    filled: look.filled, angle: look.angle, matched: look.matched
                )
                    .frame(height: turned ? 56 : 64)
                    .frame(maxWidth: 340)
                    .padding(.horizontal, 30)
                // Its room is kept, so the plan stays where it is.
                ZStack { spoken(turned: turned) }
                    .frame(minHeight: 36)
            }
            .frame(maxHeight: .infinity, alignment: .bottom)
            .padding(.bottom, turned ? 12 : 18)
        }
    }

    /// The word, and on a phone held on its side the smaller line with it.
    @ViewBuilder
    private func spoken(turned: Bool) -> some View {
        if let word {
            VStack(spacing: 2) {
                Label {
                    Text(bound: word.text)
                } icon: {
                    if let symbol = word.symbol { Image(systemName: symbol) }
                }
                .font(.subheadline.weight(.semibold))
                if turned, !look.matched {
                    Text(bound: look.note)
                        .font(.caption)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                        .opacity(0.75)
                }
            }
            .foregroundStyle(.black)
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(word.colour, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .frame(maxWidth: 440)
            .transition(.opacity)
        }
    }
}

/// Which way to walk: three arrowheads, lit one after another that way.
/// (A walking figure went before them for a day, against the arrowheads
/// being read as "turn the phone that way"; Mateusz 2026-11-16 16:44
/// UTC: "bez ikonki ludzika".)
struct OwnScanArrows: View {
    let left: Bool

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 20)) { time in
            let phase = time.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1.2) / 1.2
            HStack(spacing: -6) {
                ForEach(0 ..< 3, id: \.self) { index in
                    Image(systemName: left ? "chevron.left" : "chevron.right")
                        .font(.system(size: 30, weight: .heavy))
                        .opacity(Self.lit(left ? 2 - index : index, at: phase))
                }
            }
            .foregroundStyle(.white)
            .shadow(color: .black.opacity(0.55), radius: 4)
        }
        .accessibilityHidden(true)
    }

    /// How bright the `step`-th arrowhead along the way is at `phase`
    /// (0–1) of the wave.
    static func lit(_ step: Int, at phase: Double) -> Double {
        let off = abs(phase - Double(step) / 3)
        return 0.3 + 0.7 * max(0, 1 - min(off, 1 - off) * 3)
    }
}

/// The photograph being taken: a ring that fills while the phone is held
/// as it should be, and turns while the camera writes the photograph.
struct OwnShotRing: View {
    /// Since when all has been as the photograph needs it.
    let since: Date?
    /// The camera is taking it.
    let taking: Bool

    /// How long the phone is held before the photograph is taken.
    static let time: TimeInterval = 0.7

    /// How full the ring is `now`.
    static func filled(since: Date?, taking: Bool, now: Date) -> Double {
        if taking { return 1 }
        guard let since else { return 0 }
        return min(1, max(0, now.timeIntervalSince(since) / time))
    }

    var body: some View {
        TimelineView(.animation) { now in
            ZStack {
                Circle().fill(.black.opacity(0.4))
                Circle().stroke(.white.opacity(0.35), lineWidth: 6).padding(5)
                Circle()
                    .trim(from: 0, to: Self.filled(since: since, taking: taking, now: now.date))
                    .stroke(OwnScanLook.good, style: StrokeStyle(lineWidth: 6, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .padding(5)
                if taking {
                    ProgressView().tint(.white)
                } else {
                    Image(systemName: "camera.fill").font(.title3).foregroundStyle(.white)
                }
            }
            .frame(width: 84, height: 84)
        }
        .transition(.opacity.combined(with: .scale(scale: 0.8)))
        .accessibilityLabel("Robię zdjęcie")
    }
}

/// The way round the work seen from above: the work as a bar at the top,
/// the place in front of it at the bottom, and up the arc to either side
/// the stretch where that side's photograph is taken; a dot goes along
/// the arc as the phone goes round the work, with a line from it to the
/// work it aims at. The same drawing through the whole scan (Mateusz
/// 2026-11-16 15:02 UTC, of the plan that was under the first photograph
/// only: "nie ma swojej kontynuacji na kolejnych ekranach"). A stretch
/// turns green when its side has its photograph, whichever comes first,
/// and every side photograph leaves a small mark where it was taken
/// (the one arc, 2026-11-18).
struct OwnScanPlan: View {
    /// The photograph from the front is taken.
    let front: Bool
    /// The left side has its photograph, and the right.
    var left = false
    var right = false
    /// From how far to the side the side photographs were taken.
    var shots: [Double] = []
    /// How much of the way to the left and to the right he has walked
    /// (degrees from the front): so much of it is green.
    var filled = [0.0, 0.0]
    /// Where the phone stands, in degrees to the side of the work; nil
    /// before the first photograph.
    let angle: Double?
    /// It stands where a photograph is being taken.
    let matched: Bool

    /// How far round the drawn arc the side places are, in degrees: the
    /// way is drawn wider than it is, to be read.
    static let spread = 58.0
    /// The dot goes this far beyond the side places.
    static let most = OwnScanView.side * 1.25
    /// Where the work's bar is from the top, and how much room the place
    /// in front has under it.
    static let top = 5.0
    static let foot = 17.0

    /// Where `degrees` to the side of the work is on a plan of `size`.
    static func place(_ degrees: Double, in size: CGSize) -> CGPoint {
        let turn = max(-most, min(most, degrees)) / OwnScanView.side * spread * .pi / 180
        return CGPoint(
            x: Double(size.width) * (0.5 + 0.46 * sin(turn)),
            y: top + (Double(size.height) - top - foot) * cos(turn)
        )
    }

    /// The arc between two places.
    static func way(from: Double, to: Double, in size: CGSize) -> Path {
        var path = Path()
        let steps = 24
        for step in 0 ... steps {
            let point = place(from + (to - from) * Double(step) / Double(steps), in: size)
            if step == 0 { path.move(to: point) } else { path.addLine(to: point) }
        }
        return path
    }

    /// How a side's stretch is drawn: green with its photograph taken or
    /// being taken, bright once the first photograph is, faint before.
    private func stretch(left side: Bool) -> Color {
        let here = matched && front && angle.map { ($0 < 0) == side } == true
        if (side ? left : right) || here { return OwnScanLook.good }
        return .white.opacity(front ? 0.9 : 0.4)
    }

    var body: some View {
        GeometryReader { geo in
            let size = geo.size
            let work = CGPoint(x: size.width / 2, y: Self.top)
            let before = Self.place(0, in: size)
            Self.way(from: -Self.most, to: Self.most, in: size)
                .stroke(.white.opacity(0.55), style: StrokeStyle(lineWidth: 3, lineCap: .round))
                .shadow(color: .black.opacity(0.5), radius: 2)
            // Where a side's photograph is taken: from 22° to 38°.
            ForEach([true, false], id: \.self) { side in
                let to: Double = side ? -1 : 1
                Self.way(from: to * OwnScanView.near.lowerBound, to: to * OwnScanView.near.upperBound, in: size)
                    .stroke(stretch(left: side), style: StrokeStyle(lineWidth: 9, lineCap: .round))
                    .shadow(color: .black.opacity(0.35), radius: 2)
            }
            // The way fills up as he walks it, as the ring does when a
            // face is first shown to the phone (Mateusz 2026-11-18 16:11
            // UTC): thin up to where a side's photograph is taken, and
            // as wide as that place within it.
            ForEach([true, false], id: \.self) { side in
                let to: Double = side ? -1 : 1
                let far = min(filled[side ? 0 : 1], OwnScanView.near.upperBound)
                let band = OwnScanView.near.lowerBound
                if far > 0.5 {
                    Self.way(from: 0, to: to * min(far, band), in: size)
                        .stroke(OwnScanLook.good, style: StrokeStyle(lineWidth: 5, lineCap: .round))
                }
                if far > band {
                    Self.way(from: to * band, to: to * far, in: size)
                        .stroke(OwnScanLook.good, style: StrokeStyle(lineWidth: 9, lineCap: .round))
                }
            }
            // From where he stands (before the first photograph: is to
            // stand) to the work he aims at.
            let from = angle.map { Self.place($0, in: size) } ?? before
            Path { path in
                path.move(to: from)
                path.addLine(to: work)
            }
            .stroke(.white.opacity(0.75), style: StrokeStyle(lineWidth: 1.5, dash: [3, 4]))
            .shadow(color: .black.opacity(0.5), radius: 2)
            // The work.
            Capsule().fill(.white)
                .frame(width: size.width * 0.3, height: 5)
                .position(work)
                .shadow(color: .black.opacity(0.5), radius: 2)
            mark.position(before)
            // Where each side photograph was taken.
            ForEach(Array(shots.enumerated()), id: \.offset) { _, shot in
                Circle().fill(.white)
                    .overlay(Circle().strokeBorder(.black.opacity(0.35), lineWidth: 0.5))
                    .frame(width: 5, height: 5)
                    .position(Self.place(shot, in: size))
            }
            if let angle {
                // The phone.
                Circle().fill(.white)
                    .frame(width: 18, height: 18)
                    .shadow(color: .black.opacity(0.6), radius: 3)
                    .position(Self.place(angle, in: size))
                    .animation(.linear(duration: 0.1), value: angle)
            }
        }
        .animation(.easeOut(duration: 0.2), value: matched)
        .animation(.easeOut(duration: 0.25), value: left)
        .animation(.easeOut(duration: 0.25), value: right)
        .accessibilityHidden(true)
    }

    /// The place in front of the work: where the first photograph is
    /// taken from, or was.
    private var mark: some View {
        ZStack {
            Circle().fill(front ? OwnScanLook.good : .black.opacity(0.45))
            Circle().strokeBorder(front || matched ? OwnScanLook.good : .white, lineWidth: front ? 2 : 3)
            if front { Image(systemName: "checkmark").font(.system(size: 11, weight: .heavy)).foregroundStyle(.black) }
        }
        .frame(width: front ? 22 : 34, height: front ? 22 : 34)
        .shadow(color: .black.opacity(0.4), radius: 2)
    }
}

/// The two lines under the camera's picture.
struct OwnScanCaption: View {
    let look: OwnScanLook

    var body: some View {
        VStack(spacing: 4) {
            Text(bound: look.line)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.white.opacity(0.9))
                .multilineTextAlignment(.center)
            Text(bound: look.note)
                .font(.caption)
                .foregroundStyle(.white.opacity(0.55))
                .multilineTextAlignment(.center)
        }
        // With the phone on its side these would lie sideways: they are
        // said over the picture, turned.
        .opacity(look.quarter == 0 ? 1 : 0)
        .animation(.easeInOut(duration: 0.3), value: look.quarter)
    }
}

/// Four corners as one value a drawing can pass through on its way from
/// one outline to the next.
struct OutlineCorners: VectorArithmetic {
    var values = [Double](repeating: 0, count: 8)

    init() {}

    init(_ corners: [CGPoint]) {
        for (index, corner) in corners.prefix(4).enumerated() {
            values[index * 2] = Double(corner.x)
            values[index * 2 + 1] = Double(corner.y)
        }
    }

    var corners: [CGPoint] {
        (0 ..< 4).map { CGPoint(x: values[$0 * 2], y: values[$0 * 2 + 1]) }
    }

    static var zero: OutlineCorners { OutlineCorners() }

    static func + (a: OutlineCorners, b: OutlineCorners) -> OutlineCorners {
        var sum = a
        for index in sum.values.indices { sum.values[index] += b.values[index] }
        return sum
    }

    static func - (a: OutlineCorners, b: OutlineCorners) -> OutlineCorners {
        var difference = a
        for index in difference.values.indices { difference.values[index] -= b.values[index] }
        return difference
    }

    mutating func scale(by factor: Double) {
        for index in values.indices { values[index] *= factor }
    }

    var magnitudeSquared: Double { values.reduce(0) { $0 + $1 * $1 } }
}

/// An outline through four corners given as fractions of the view.
struct OutlineShape: Shape {
    var corners: [CGPoint]
    /// Nil, the outline whole; else only its corners, each with so much
    /// of its two sides (0–0.5).
    var marks: Double? = nil

    var animatableData: OutlineCorners {
        get { OutlineCorners(corners) }
        set { if corners.count == 4 { corners = newValue.corners } }
    }

    func path(in rect: CGRect) -> Path {
        var path = Path()
        guard let first = corners.first else { return path }
        func point(_ p: CGPoint) -> CGPoint { CGPoint(x: rect.minX + p.x * rect.width, y: rect.minY + p.y * rect.height) }
        if let marks {
            let places = corners.map(point)
            for (index, corner) in places.enumerated() {
                let before = places[(index + places.count - 1) % places.count]
                let after = places[(index + 1) % places.count]
                path.move(to: CGPoint(x: corner.x + (before.x - corner.x) * marks, y: corner.y + (before.y - corner.y) * marks))
                path.addLine(to: corner)
                path.addLine(to: CGPoint(x: corner.x + (after.x - corner.x) * marks, y: corner.y + (after.y - corner.y) * marks))
            }
            return path
        }
        path.move(to: point(first))
        for corner in corners.dropFirst() { path.addLine(to: point(corner)) }
        path.closeSubpath()
        return path
    }
}

/// The shutter, for when the photograph does not take itself.
struct OwnShutter: View {
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            ZStack {
                Circle().strokeBorder(.white, lineWidth: 4).frame(width: 78, height: 78)
                Circle().fill(.white).frame(width: 64, height: 64)
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Zrób zdjęcie")
    }
}
