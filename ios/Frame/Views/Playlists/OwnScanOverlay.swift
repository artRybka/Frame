import SwiftUI

/// What the scan's camera draws over its picture and says under it
/// (Mateusz 2026-11-16: "pierwsze zdjęcie na wprost, a kolejne pod większym
/// kątem z ramką pomocniczą na ekranie pokazująca gdzie ma się znajdować
/// dzieło"; 09:52 UTC: no shutter, "skoro zdjęcie robi się samo", and the
/// helper says to come nearer or step back). The camera fills it from what
/// it sees, the screenshots' scene from a look's name.
struct OwnScanLook: Equatable {
    /// Which photograph of the three is next (1: the first).
    var number = 1
    var advice = OwnScanAdvice.lost
    /// The work's outline as the camera sees it now (0–1 on the screen's
    /// picture): drawn whole before the first photograph, as its four
    /// corners before a side one.
    var live: [CGPoint]?
    /// The work has not been seen for a while: he takes the photograph himself.
    var manual = false
    /// Little light: the photograph may come out blurred or grainy.
    var dim = false
    /// Where the phone stands, in degrees to the side of the work
    /// (negative: to its left); nil before the first photograph.
    var angle: Double?
    /// The middle of the work on the screen's picture (0–1) before a side
    /// photograph, when the camera sees the work: what the sight follows.
    var aim: CGPoint?
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
        case .pinning: ("Przypinam znaczniki", "pin.fill", .white)
        case .lost where manual: ("Nie widzę krawędzi dzieła", "viewfinder", .white)
        default: nil
        }
    }

    /// The line under the picture.
    var line: String {
        let side = number == 2 ? "lewej" : "prawej"
        switch advice {
        case .hold: return number == 1 ? "Dobrze. Robię zdjęcie na wprost" : "Dobrze. Robię zdjęcie z \(side)"
        case .nearer: return "Dzieło jest za małe w kadrze"
        case .farther: return "Dzieło nie mieści się w kadrze"
        case .straight: return "Dzieło widać z boku"
        case .level: return "Telefon jest pochylony"
        case .aim: return "Dzieło ucieka ze środka kadru"
        case .turned(let left): return "Zrób krok w \(left ? "lewo" : "prawo"), a telefon skieruj na dzieło"
        case .rolled: return "Trzymaj telefon tak jak przy pierwszym zdjęciu"
        case .corners where manual: return "Zrób zdjęcie sam, gdy całe dzieło jest w kadrze"
        case .corners: return "Nie widzę wszystkich narożników dzieła"
        case .pinning: return "Jeszcze chwila na wprost dzieła"
        case .lost where manual: return "Zrób zdjęcie sam"
        case .go(let left) where number > 1 && left != (number == 2):
            return "Za daleko w bok, wróć trochę"
        default: break
        }
        switch number {
        case 1: return "Stań na wprost dzieła, całe w kadrze"
        case 2: return "Zrób krok w lewo, celując w dzieło"
        default: return "Teraz przejdź w prawo, celując w dzieło"
        }
    }

    /// The smaller line under it.
    var note: String {
        switch advice {
        case .nearer: "Im bliżej, tym więcej szczegółów na zdjęciu."
        case .farther: "Całe ma być widoczne, z kawałkiem ściany wokół."
        case .straight: "Przesuń się tak, żeby lewy i prawy bok dzieła były równej wysokości."
        case .level: "Trzymaj go pionowo, na wysokości środka dzieła."
        case .aim: "Obróć telefon tak, żeby znacznik dzieła wszedł w celownik na środku."
        case .turned: "Dzieło trzeba zobaczyć z boku. Sam obrót telefonu tego nie da."
        case .rolled: "Trzy zdjęcia mają być zrobione tak samo: wszystkie pionowo albo wszystkie poziomo."
        case .corners: "Cztery narożniki mają być w kadrze, z kawałkiem ściany wokół."
        case .pinning: "Znaczniki zostaną na narożnikach dzieła, gdy pójdziesz w bok."
        case _ where dim: "Mało światła, zdjęcie może wyjść nieostre. Zapal światło, jeśli możesz."
        case .lost where manual: "Tak bywa przy ciemnej ramie na ciemnej ścianie albo w słabym świetle."
        default:
            number == 1
                ? "Zdjęcie zrobi się samo, gdy obrys zrobi się zielony."
                : "Zdjęcie zrobi się samo, gdy kropka dojdzie do kółka."
        }
    }
}

/// What is drawn over the camera's picture: before the first photograph
/// the work's outline as the camera finds it; before a side one its four
/// corners and the sight. Under them, on all three, the way round the
/// work seen from above (`OwnScanPlan`), on which a dot goes where the
/// phone goes, to the ring where the photograph is taken (Mateusz
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
            if holding == nil, !taking {
                OwnScanSight(aim: look.aim, size: size)
            }
        }
    }

    /// The arrows, the ring, the plan and the word.
    private var said: some View {
        let turned = look.quarter != 0
        return ZStack {
            if let left = look.walk {
                OwnScanArrows(left: left)
                    .frame(maxWidth: .infinity, alignment: left ? .leading : .trailing)
                    .padding(.horizontal, 12)
                    .transition(.opacity)
            }
            if holding != nil || taking {
                OwnShotRing(since: holding, taking: taking)
            }
            VStack(spacing: turned ? 8 : 10) {
                OwnScanPlan(taken: look.number - 1, angle: look.angle, matched: look.matched)
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

/// The sight before a side photograph: a ring in the picture's middle
/// and a mark on the work's middle as the camera follows it. The
/// photograph is taken with the mark in the ring, so the work is in the
/// picture's middle from the side too (Mateusz 2026-11-16 13:35 UTC:
/// "inaczej przechodząc w bok dzieło nie będzie w środku kadru"). Without
/// the mark (the camera does not find the work's edges) the ring alone
/// says where to aim.
struct OwnScanSight: View {
    /// The work's middle on the picture (0–1), when it is seen.
    let aim: CGPoint?
    let size: CGSize

    /// The ring's radius: how far the work's middle may be off.
    static func radius(in size: CGSize) -> Double {
        OwnScanView.aimed * Double(min(size.width, size.height))
    }

    /// The mark is in the ring.
    static func inside(_ aim: CGPoint, size: CGSize) -> Bool {
        hypot(Double(aim.x - 0.5) * size.width, Double(aim.y - 0.5) * size.height) <= radius(in: size)
    }

    var body: some View {
        let r = Self.radius(in: size)
        let centre = CGPoint(x: size.width / 2, y: size.height / 2)
        let good = aim.map { Self.inside($0, size: size) } ?? false
        ZStack {
            Circle()
                .stroke(good ? OwnScanLook.good : .white.opacity(0.85), lineWidth: good ? 3 : 2)
                .frame(width: r * 2, height: r * 2)
                .position(centre)
            // The cross in its middle.
            Path { path in
                path.move(to: CGPoint(x: centre.x - 7, y: centre.y))
                path.addLine(to: CGPoint(x: centre.x + 7, y: centre.y))
                path.move(to: CGPoint(x: centre.x, y: centre.y - 7))
                path.addLine(to: CGPoint(x: centre.x, y: centre.y + 7))
            }
            .stroke(.white.opacity(0.85), lineWidth: 1.5)
            if let aim {
                let at = CGPoint(x: aim.x * size.width, y: aim.y * size.height)
                if !good {
                    // From the work to where it should be.
                    Path { path in
                        path.move(to: at)
                        path.addLine(to: centre)
                    }
                    .stroke(OwnScanLook.wait.opacity(0.8), style: StrokeStyle(lineWidth: 2, lineCap: .round, dash: [2, 6]))
                }
                ZStack {
                    Circle().fill(good ? OwnScanLook.good : OwnScanLook.wait)
                    Circle().strokeBorder(.black.opacity(0.35), lineWidth: 1)
                }
                .frame(width: 20, height: 20)
                .position(at)
                .animation(.linear(duration: 0.14), value: aim)
            }
        }
        .shadow(color: .black.opacity(0.5), radius: 3)
        .animation(.easeOut(duration: 0.15), value: good)
        .transition(.opacity)
        .accessibilityHidden(true)
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
/// the place in front of it at the bottom, the places to its left and
/// right up the arc to either side, each with the stretch about it where
/// the photograph is taken; a dot goes along the arc as the phone goes
/// round the work, with a line from it to the work it aims at. The same
/// drawing on all three photographs (Mateusz 2026-11-16 15:02 UTC, of the
/// plan that was under the first one only: "nie ma swojej kontynuacji na
/// kolejnych ekranach"): it was a straight track before the side ones,
/// which did not say that the way goes round the work.
struct OwnScanPlan: View {
    /// How many photographs are taken (front, left, right in turn).
    let taken: Int
    /// Where the phone stands, in degrees to the side of the work; nil
    /// before the first photograph.
    let angle: Double?
    /// It stands where the next photograph is taken.
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

    var body: some View {
        GeometryReader { geo in
            let size = geo.size
            let work = CGPoint(x: size.width / 2, y: Self.top)
            // Front, left, right: the order they are taken in.
            let places = [0, -OwnScanView.side, OwnScanView.side].map { Self.place($0, in: size) }
            Self.way(from: -Self.most, to: Self.most, in: size)
                .stroke(.white.opacity(0.55), style: StrokeStyle(lineWidth: 3, lineCap: .round))
                .shadow(color: .black.opacity(0.5), radius: 2)
            if (1 ... 2).contains(taken) {
                // Where the next one is taken: from 22° to 38°.
                let to: Double = taken == 1 ? -1 : 1
                Self.way(from: to * OwnScanView.near.lowerBound, to: to * OwnScanView.near.upperBound, in: size)
                    .stroke(matched ? OwnScanLook.good : .white.opacity(0.9), style: StrokeStyle(lineWidth: 9, lineCap: .round))
            }
            // From where he stands (before the first photograph: is to
            // stand) to the work he aims at.
            let from = angle.map { Self.place($0, in: size) } ?? places[min(max(taken, 0), 2)]
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
            ForEach(0 ..< 3, id: \.self) { index in
                mark(index).position(places[index])
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
        .accessibilityHidden(true)
    }

    /// A place a photograph is taken from: done, next, or to come.
    private func mark(_ index: Int) -> some View {
        let done = index < taken, next = index == taken
        return ZStack {
            Circle().fill(done ? OwnScanLook.good : .black.opacity(0.45))
            Circle().strokeBorder(done || (next && matched) ? OwnScanLook.good : .white.opacity(next ? 1 : 0.5), lineWidth: next ? 3 : 2)
            if done { Image(systemName: "checkmark").font(.system(size: 11, weight: .heavy)).foregroundStyle(.black) }
        }
        .frame(width: next ? 34 : 22, height: next ? 34 : 22)
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
