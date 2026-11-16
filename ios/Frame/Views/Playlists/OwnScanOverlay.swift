import CoreImage
import CoreImage.CIFilterBuiltins
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
    /// picture), before the first photograph.
    var live: [CGPoint]?
    /// Where it should lie for the side photograph: the helper frame, when
    /// that is how the way is shown (`-scanGuide frame`); nil with the
    /// track.
    var helper: [CGPoint]?
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

    /// The word over the picture.
    var pill: (text: String, symbol: String, colour: Color)? {
        switch advice {
        case .hold: ("Nie ruszaj", "camera.aperture", Self.good)
        case .nearer: ("Podejdź bliżej", "arrow.up.left.and.arrow.down.right", Self.wait)
        case .farther: ("Odsuń się", "arrow.down.right.and.arrow.up.left", Self.wait)
        case .straight: ("Stań na wprost", "arrow.left.and.right", Self.wait)
        case .level: ("Trzymaj telefon prosto", "iphone", Self.wait)
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
        case .lost where manual: return "Zrób zdjęcie sam"
        case .go(let left) where number > 1 && left != (number == 2):
            return "Za daleko w bok, wróć trochę"
        default: break
        }
        switch number {
        case 1: return "Stań na wprost dzieła, całe w kadrze"
        case 2: return helper == nil ? "Przejdź w lewo, celując w dzieło" : "Przejdź w lewo, aż dzieło wypełni ramkę"
        default: return helper == nil ? "Teraz w prawo, celując w dzieło" : "Teraz w prawo, aż dzieło wypełni ramkę"
        }
    }

    /// The smaller line under it.
    var note: String {
        switch advice {
        case .nearer: "Im bliżej, tym więcej szczegółów na zdjęciu."
        case .farther: "Całe ma być widoczne, z kawałkiem ściany wokół."
        case .straight: "Przesuń się tak, żeby lewy i prawy bok dzieła były równej wysokości."
        case .level: "Trzymaj go pionowo, na wysokości środka dzieła."
        case _ where dim: "Mało światła, zdjęcie może wyjść nieostre. Zapal światło, jeśli możesz."
        case .lost where manual: "Tak bywa przy ciemnej ramie na ciemnej ścianie albo w słabym świetle."
        default:
            number == 1
                ? "Zdjęcie zrobi się samo, gdy obrys zrobi się zielony."
                : helper == nil
                    ? "Zdjęcie zrobi się samo, gdy kropka dojdzie do kółka."
                    : "Celuj cały czas w dzieło. Zdjęcie zrobi się samo."
        }
    }
}

/// What is drawn over the camera's picture: before the first photograph
/// the work's outline as the camera finds it; before a side one a track
/// as the iPhone's panorama has, on which a dot goes where the phone goes,
/// to the ring where the photograph is taken (Mateusz 2026-11-16 12:58
/// UTC: "może wpadniesz na jakiś jeszcze lepszy - np. celowanie AR? jakieś
/// znaczniki? chciałbym żeby było to możliwie intuicyjne": one thing to
/// watch, moved by the one thing he does, walking); or, as the other way
/// shown him to choose from, the helper frame with the work from the
/// first photograph faint in it ("Może Jesteśmy w stanie pokazać zamiast
/// ramki wycięty, przezroczysty fragment z 1 zdjęcia?"). Arrows the way
/// to walk, and a ring that fills while the photograph is taken ("trzeba
/// dodać jakiś wskaźnik wykonywania zdjęcia - np. wypełniający się
/// okrąg?").
struct OwnScanOverlay: View {
    let look: OwnScanLook
    /// The work of the first photograph as it shows in the helper frame
    /// (a picture as large as the camera's, clear around it).
    var ghost: UIImage? = nil
    /// Since when all has been as the photograph needs it.
    var holding: Date? = nil
    /// The camera is taking the photograph.
    var taking = false

    /// The word over the picture: on its side the phone's own lines under
    /// the picture lie sideways, so the line is said here too.
    private var word: (text: String, symbol: String?, colour: Color)? {
        if let pill = look.pill { return (pill.text, pill.symbol, pill.colour) }
        return look.quarter == 0 ? nil : (look.line, nil, .white)
    }

    var body: some View {
        GeometryReader { geo in
            let turned = look.quarter != 0
            ZStack {
                drawn(geo.size)
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
        if let helper = look.helper {
            if let ghost {
                Image(uiImage: ghost).resizable()
                    .frame(width: size.width, height: size.height)
                    .opacity(look.matched ? 0.3 : 0.5)
            } else {
                OutlineShape(corners: helper).fill(.white.opacity(look.matched ? 0 : 0.10))
            }
            OutlineShape(corners: helper)
                .stroke(look.matched ? OwnScanLook.good : .white,
                        style: StrokeStyle(lineWidth: look.matched ? 4 : 3, lineCap: .round, lineJoin: .round, dash: look.matched ? [] : [10, 8]))
                .shadow(color: .black.opacity(0.45), radius: 3)
        } else if let live = look.live {
            OutlineShape(corners: live)
                .stroke(look.matched ? OwnScanLook.good : OwnScanLook.wait,
                        style: StrokeStyle(lineWidth: look.matched ? 4 : 2.5, lineJoin: .round))
                .shadow(color: .black.opacity(0.45), radius: 3)
                // From one look of the camera to the next, not in jumps.
                .animation(.linear(duration: 0.14), value: live)
                .transition(.opacity)
        }
    }

    /// The arrows, the ring and the word.
    private var said: some View {
        ZStack {
            if look.number > 1, look.helper == nil {
                OwnScanTrack(taken: look.number - 1, angle: look.angle, matched: look.matched)
                    .frame(height: 44)
                    .padding(.horizontal, 30)
                    .frame(maxHeight: .infinity, alignment: .bottom)
                    .padding(.bottom, 64)
            }
            if case .go(let left) = look.advice, look.number > 1 {
                OwnScanArrows(left: left)
                    .frame(maxWidth: .infinity, alignment: left ? .leading : .trailing)
                    .padding(.horizontal, 12)
                    .transition(.opacity)
            }
            if holding != nil || taking {
                OwnShotRing(since: holding, taking: taking)
            }
            if let word {
                Label {
                    Text(word.text)
                } icon: {
                    if let symbol = word.symbol { Image(systemName: symbol) }
                }
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.black)
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(word.colour, in: Capsule())
                .frame(maxHeight: .infinity, alignment: .bottom)
                .padding(.bottom, 18)
                .transition(.opacity)
            }
        }
    }
}

/// Which way to walk: three arrowheads, lit one after another that way.
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

/// The way round the work as a track across the picture, as the iPhone's
/// panorama has: the place in front in its middle, the places to the left
/// and right at its ends, each with the stretch about it where the
/// photograph is taken; a dot goes along it as the phone goes round the
/// work.
struct OwnScanTrack: View {
    /// How many photographs are taken (front, left, right in turn).
    let taken: Int
    /// Where the phone stands, in degrees to the side of the work.
    let angle: Double?
    /// It stands where the next photograph is taken.
    let matched: Bool

    /// How much of the track's half a degree takes: the side places are
    /// at four fifths of the way to its ends.
    static let reach = 0.8 / OwnScanView.side

    /// Where `degrees` is along a track `width` wide.
    static func place(_ degrees: Double, width: Double) -> Double {
        width * (0.5 + 0.5 * max(-1, min(1, degrees * reach)))
    }

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width, y = geo.size.height / 2
            // Front, left, right: the order they are taken in.
            let places = [0, -OwnScanView.side, OwnScanView.side].map { Self.place($0, width: w) }
            Capsule().fill(.white.opacity(0.55))
                .frame(width: w, height: 3)
                .position(x: w / 2, y: y)
                .shadow(color: .black.opacity(0.5), radius: 2)
            if (1 ... 2).contains(taken) {
                // Where the next one is taken: from 22° to 38°.
                let from = Self.place((taken == 1 ? -1 : 1) * OwnScanView.near.lowerBound, width: w)
                let to = Self.place((taken == 1 ? -1 : 1) * OwnScanView.near.upperBound, width: w)
                Capsule().fill(matched ? OwnScanLook.good : .white.opacity(0.9))
                    .frame(width: abs(to - from), height: 9)
                    .position(x: (from + to) / 2, y: y)
            }
            ForEach(0 ..< 3, id: \.self) { index in
                let done = index < taken, next = index == taken
                ZStack {
                    Circle().fill(done ? OwnScanLook.good : .black.opacity(0.45))
                    Circle().strokeBorder(done || (next && matched) ? OwnScanLook.good : .white.opacity(next ? 1 : 0.5), lineWidth: next ? 3 : 2)
                    if done { Image(systemName: "checkmark").font(.system(size: 11, weight: .heavy)).foregroundStyle(.black) }
                }
                .frame(width: next ? 34 : 22, height: next ? 34 : 22)
                .position(x: places[index], y: y)
                .shadow(color: .black.opacity(0.4), radius: 2)
            }
            if let angle {
                // The phone.
                Circle().fill(.white)
                    .frame(width: 18, height: 18)
                    .shadow(color: .black.opacity(0.6), radius: 3)
                    .position(x: Self.place(angle, width: w), y: y)
                    .animation(.linear(duration: 0.1), value: angle)
            }
        }
        .animation(.easeOut(duration: 0.2), value: matched)
        .accessibilityHidden(true)
    }
}

/// The work of the first photograph as it will show in the helper frame.
enum OwnScanGhost {
    private static let context = CIContext()
    /// The picture's size: the camera's 3 : 4 on the screen.
    static let size = CGSize(width: 720, height: 960)

    /// `photo` (upright as it was held) cut to `corners` (its work: top
    /// left, top right, bottom right, bottom left, 0–1) and laid onto
    /// `frame` (the same corners on the screen's picture), clear around.
    static func picture(of photo: UIImage, corners: [CGPoint], onto frame: [CGPoint]) -> UIImage? {
        guard corners.count == 4, frame.count == 4 else { return nil }
        let work = OwnPicture.cut(photo, corners: corners.map { [Double($0.x), Double($0.y)] })
        guard let source = CIImage(image: work) else { return nil }
        // CI's origin is bottom left.
        func point(_ p: CGPoint) -> CGPoint { CGPoint(x: p.x * size.width, y: (1 - p.y) * size.height) }
        let lay = CIFilter.perspectiveTransform()
        lay.inputImage = source
        lay.topLeft = point(frame[0])
        lay.topRight = point(frame[1])
        lay.bottomRight = point(frame[2])
        lay.bottomLeft = point(frame[3])
        let whole = CGRect(origin: .zero, size: size)
        let clear = CIImage(color: .clear).cropped(to: whole)
        guard let out = lay.outputImage?.composited(over: clear),
              let cg = context.createCGImage(out, from: whole)
        else { return nil }
        return UIImage(cgImage: cg)
    }
}

/// The two lines under the camera's picture.
struct OwnScanCaption: View {
    let look: OwnScanLook

    var body: some View {
        VStack(spacing: 4) {
            Text(look.line)
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.white.opacity(0.9))
                .multilineTextAlignment(.center)
            Text(look.note)
                .font(.caption)
                .foregroundStyle(.white.opacity(0.55))
                .multilineTextAlignment(.center)
        }
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

    var animatableData: OutlineCorners {
        get { OutlineCorners(corners) }
        set { if corners.count == 4 { corners = newValue.corners } }
    }

    func path(in rect: CGRect) -> Path {
        var path = Path()
        guard let first = corners.first else { return path }
        func point(_ p: CGPoint) -> CGPoint { CGPoint(x: rect.minX + p.x * rect.width, y: rect.minY + p.y * rect.height) }
        path.move(to: point(first))
        for corner in corners.dropFirst() { path.addLine(to: point(corner)) }
        path.closeSubpath()
        return path
    }
}

/// Where to stand, seen from above: the work as a bar at the top, the
/// three places before it; those done are filled, the next one is ringed.
struct StandPlan: View {
    /// How many photographs are taken (front, left, right in turn).
    let taken: Int
    var good = OwnScanLook.good

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width, h = geo.size.height
            let work = CGPoint(x: w / 2, y: 7)
            // Front, left, right: the order they are taken in.
            let places = [CGPoint(x: w / 2, y: h - 9), CGPoint(x: w * 0.14, y: h - 20), CGPoint(x: w * 0.86, y: h - 20)]
            Capsule().fill(.white).frame(width: w * 0.42, height: 4).position(work)
            ForEach(0 ..< 3, id: \.self) { index in
                Path { path in
                    path.move(to: places[index])
                    path.addLine(to: work)
                }
                .stroke(.white.opacity(index == taken ? 0.7 : 0.2), style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
                Circle()
                    .fill(index < taken ? good : .clear)
                    .overlay(Circle().strokeBorder(index < taken ? good : .white.opacity(index == taken ? 1 : 0.4), lineWidth: 2))
                    .frame(width: index == taken ? 16 : 12, height: index == taken ? 16 : 12)
                    .position(places[index])
            }
        }
        .accessibilityHidden(true)
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
