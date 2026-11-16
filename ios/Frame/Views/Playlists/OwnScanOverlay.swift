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
    /// The work's outline as the camera sees it now (0–1 on the screen's picture).
    var live: [CGPoint]?
    /// Where it should lie for the side photograph.
    var helper: [CGPoint]?
    /// The work has not been seen for a while: he takes the photograph himself.
    var manual = false
    /// Little light: the photograph may come out blurred or grainy.
    var dim = false

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
        case 2: return "Przejdź w lewo, aż dzieło wypełni ramkę"
        default: return "Teraz w prawo, aż dzieło wypełni ramkę"
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
                : "Celuj cały czas w dzieło. Zdjęcie zrobi się samo."
        }
    }
}

/// The helper frame, the work's outline, the arrow and the word, over the
/// camera's picture.
struct OwnScanOverlay: View {
    let look: OwnScanLook

    var body: some View {
        ZStack {
            GeometryReader { geo in
                if let helper = look.helper {
                    // The helper frame: where the work should lie.
                    OutlineShape(corners: helper)
                        .fill(.white.opacity(look.matched ? 0 : 0.10))
                    OutlineShape(corners: helper)
                        .stroke(look.matched ? OwnScanLook.good : .white,
                                style: StrokeStyle(lineWidth: look.matched ? 4 : 3, lineCap: .round, lineJoin: .round, dash: look.matched ? [] : [10, 8]))
                        .shadow(color: .black.opacity(0.45), radius: 3)
                    if !look.matched, let live = look.live {
                        // The work as the camera sees it now, and which way to go.
                        OutlineShape(corners: live)
                            .stroke(OwnScanLook.wait, style: StrokeStyle(lineWidth: 2, lineJoin: .round))
                    }
                    if case .go(let left) = look.advice {
                        Image(systemName: left ? "arrow.left" : "arrow.right")
                            .font(.system(size: 30, weight: .bold))
                            .foregroundStyle(.white)
                            .shadow(color: .black.opacity(0.55), radius: 4)
                            .position(x: geo.size.width * (left ? 0.085 : 0.915), y: geo.size.height * 0.5)
                    }
                } else if let live = look.live {
                    OutlineShape(corners: live)
                        .stroke(look.matched ? OwnScanLook.good : OwnScanLook.wait,
                                style: StrokeStyle(lineWidth: look.matched ? 4 : 2.5, lineJoin: .round))
                        .shadow(color: .black.opacity(0.45), radius: 3)
                }
            }
            if let pill = look.pill {
                Label(pill.text, systemImage: pill.symbol)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.black)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(pill.colour, in: Capsule())
                    .frame(maxHeight: .infinity, alignment: .bottom)
                    .padding(.bottom, 18)
                    .transition(.opacity)
            }
        }
        .animation(.easeOut(duration: 0.2), value: look.advice)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(look.pill?.text ?? look.line)
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

/// An outline through four corners given as fractions of the view.
struct OutlineShape: Shape {
    let corners: [CGPoint]

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
