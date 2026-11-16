import SwiftUI

/// Sketches only (`-screen own-scan -scanLook measure|glare|guided|merged`),
/// for Mateusz's question of 2026-11-16: "Czy aparat … mógłby korzystając z
/// możliwości iOS pobierać jego szacowany wymiar? … Zdjęcia pod różnym
/// kątem dla uniknięcia odbić i refleksów, podniesienia jakości". Nothing
/// here measures or merges anything: the demo's photograph, drawn over as
/// the screens would look. Removed once he picks.
struct OwnScanSketch: View {
    enum Look: String { case measure, glare, guided, merged }

    @Environment(\.dismiss) private var dismiss
    private let look = Look(rawValue: UserDefaults.standard.string(forKey: "scanLook") ?? "") ?? .measure
    private let photo = DemoOwn.photo()
    private let clean = DemoOwn.photo(glare: false)

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if look == .merged {
                merged
            } else {
                camera
            }
        }
        .environment(\.colorScheme, .dark)
    }

    // MARK: The camera

    private var camera: some View {
        VStack(spacing: 0) {
            HStack {
                Button { dismiss() } label: {
                    Image(systemName: "chevron.backward")
                        .font(.body.weight(.semibold))
                        .frame(width: 44, height: 44)
                }
                .buttonStyle(.glass)
                .buttonBorderShape(.circle)
                Spacer()
                if look == .guided {
                    Text("Zdjęcie 2 z 3")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .glassEffect()
                }
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.top, 4)
            Spacer(minLength: 12)
            viewfinder
            caption
                .padding(.horizontal, Theme.gutter)
                .padding(.top, 14)
            Spacer(minLength: 12)
            bottom
        }
    }

    private var viewfinder: some View {
        ZStack {
            if let photo {
                Image(uiImage: look == .guided ? (clean ?? photo) : photo)
                    .resizable()
                    .scaledToFill()
                    .offset(x: look == .guided ? 26 : 0)
            }
            GeometryReader { geo in
                let size = geo.size
                switch look {
                case .measure:
                    WorkOutline(corners: DemoOwn.work)
                        .stroke(.white, style: StrokeStyle(lineWidth: 2.5, lineJoin: .round))
                        .shadow(color: .black.opacity(0.4), radius: 3)
                    // The size where the work is, as Miarka shows it.
                    sizeTag
                        .position(x: size.width * 0.5, y: size.height * 0.75)
                case .glare:
                    Ellipse()
                        .stroke(.yellow, style: StrokeStyle(lineWidth: 2.5, dash: [7, 5]))
                        .frame(width: size.width * 0.36, height: size.height * 0.2)
                        .position(x: size.width * 0.7, y: size.height * 0.38)
                case .guided:
                    // Move until the dot is in the ring: the shot is taken by itself.
                    Circle()
                        .stroke(.white, lineWidth: 3)
                        .frame(width: 58, height: 58)
                        .position(x: size.width * 0.18, y: size.height * 0.5)
                    Circle()
                        .fill(.white)
                        .frame(width: 22, height: 22)
                        .shadow(color: .black.opacity(0.4), radius: 3)
                        .position(x: size.width * 0.5, y: size.height * 0.5)
                    Image(systemName: "arrow.left")
                        .font(.title3.weight(.bold))
                        .foregroundStyle(.white)
                        .shadow(color: .black.opacity(0.5), radius: 3)
                        .position(x: size.width * 0.34, y: size.height * 0.5)
                case .merged:
                    EmptyView()
                }
            }
        }
        .aspectRatio(3 / 4, contentMode: .fit)
        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        .padding(.horizontal, 8)
    }

    private var sizeTag: some View {
        HStack(spacing: 6) {
            Image(systemName: "ruler")
            Text("ok. 65 × 81 cm")
        }
        .font(.subheadline.weight(.semibold))
        .foregroundStyle(.white)
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .glassEffect()
    }

    @ViewBuilder
    private var caption: some View {
        switch look {
        case .measure:
            VStack(spacing: 4) {
                Text("Umieść całe dzieło w kadrze")
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.white.opacity(0.85))
                Text("Wymiar mierzy czujnik LiDAR, bez ramy")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.55))
            }
        case .glare:
            VStack(alignment: .leading, spacing: 12) {
                Label("Na szybie jest odblask", systemImage: "sun.max")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.white)
                Text("Zrób drugie zdjęcie trochę z boku, a połączę oba bez odblasku.")
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.75))
                    .fixedSize(horizontal: false, vertical: true)
                HStack(spacing: 10) {
                    Button("Zostaw tak") {}
                        .buttonStyle(.glass)
                    Button("Zrób drugie") {}
                        .buttonStyle(.glassProminent)
                }
                .controlSize(.large)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        case .guided:
            Text("Przesuń telefon w lewo, aż kropka wejdzie w kółko")
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.white.opacity(0.85))
                .multilineTextAlignment(.center)
        case .merged:
            EmptyView()
        }
    }

    @ViewBuilder
    private var bottom: some View {
        switch look {
        case .measure:
            shutterRow
        case .glare:
            Color.clear.frame(height: 90)
        case .guided:
            // The three shots: the first taken, this one, the last.
            HStack(spacing: 14) {
                ForEach(0 ..< 3) { index in
                    ZStack {
                        if index == 0, let photo {
                            Image(uiImage: photo).resizable().scaledToFill()
                        } else {
                            RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .strokeBorder(.white.opacity(index == 1 ? 0.9 : 0.35), style: StrokeStyle(lineWidth: 2, dash: [5, 4]))
                        }
                    }
                    .frame(width: 54, height: 72)
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                }
            }
            .padding(.bottom, 20)
        case .merged:
            EmptyView()
        }
    }

    private var shutterRow: some View {
        HStack {
            Image(systemName: "photo.on.rectangle")
                .font(.title3)
                .frame(width: 52, height: 52)
                .glassEffect(in: .circle)
            Spacer()
            ZStack {
                Circle().strokeBorder(.white, lineWidth: 4).frame(width: 78, height: 78)
                Circle().fill(.white).frame(width: 64, height: 64)
            }
            Spacer()
            Color.clear.frame(width: 52, height: 52)
        }
        .padding(.horizontal, 32)
        .padding(.bottom, 12)
    }

    // MARK: Merged

    /// The work from two shots: the glare gone, before and after side by side.
    private var merged: some View {
        VStack(spacing: 18) {
            HStack {
                Button { dismiss() } label: {
                    Image(systemName: "chevron.backward")
                        .font(.body.weight(.semibold))
                        .frame(width: 44, height: 44)
                }
                .buttonStyle(.glass)
                .buttonBorderShape(.circle)
                Spacer()
            }
            .padding(.horizontal, Theme.gutter)
            Spacer(minLength: 0)
            if let photo, let clean {
                let before = DemoOwn.cut(photo, corners: DemoOwn.work, own: nil)
                let after = DemoOwn.cut(clean, corners: DemoOwn.work, own: nil)
                VStack(spacing: 10) {
                    comparison(before: before, after: after)
                        .padding(.horizontal, Theme.gutter)
                    HStack {
                        Text("Jedno zdjęcie").frame(maxWidth: .infinity, alignment: .leading)
                        Text("Z dwóch zdjęć").frame(maxWidth: .infinity, alignment: .trailing)
                    }
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.6))
                    .padding(.horizontal, Theme.gutter)
                }
            }
            Label("Odblask usunięty", systemImage: "sparkles")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.white)
            Spacer(minLength: 0)
            Button {} label: {
                Text("Dalej").frame(maxWidth: .infinity)
            }
            .buttonStyle(.glassProminent)
            .controlSize(.large)
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 12)
        }
    }

    /// The left half from one shot, the right from two, a line between.
    private func comparison(before: UIImage, after: UIImage) -> some View {
        Image(uiImage: after)
            .resizable()
            .aspectRatio(contentMode: .fit)
            .overlay {
                GeometryReader { geo in
                    Image(uiImage: before)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .mask(alignment: .leading) {
                            Rectangle().frame(width: geo.size.width * 0.5)
                        }
                    Rectangle()
                        .fill(.white)
                        .frame(width: 2)
                        .position(x: geo.size.width * 0.5, y: geo.size.height * 0.5)
                        .frame(height: geo.size.height)
                }
            }
    }
}

/// The work's outline, from fractions of the photograph.
private struct WorkOutline: Shape {
    let corners: [[Double]]

    func path(in rect: CGRect) -> Path {
        var path = Path()
        guard corners.count == 4 else { return path }
        // The photograph fills a 3 : 4 frame as it was taken (1200 × 1600).
        let points = corners.map { CGPoint(x: rect.minX + $0[0] * rect.width, y: rect.minY + $0[1] * rect.height) }
        path.move(to: points[0])
        for point in points.dropFirst() { path.addLine(to: point) }
        path.closeSubpath()
        return path
    }
}
