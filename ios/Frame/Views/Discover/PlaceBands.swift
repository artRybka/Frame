import SwiftUI

/// Szukaj's "Muzeum" (szkic 4, Mateusz 2026-11-08): the museums where the
/// works are, each a band with one of its works behind its name and town.
/// A museum the catalogue has nothing of yet shows a work Wikidata knows
/// there; one with none, a soft mesh of earth colours, always the same for
/// the same museum. No icon: every name starts at the same place (Mateusz). Picked ones get a tick ("Wybrane") or, left out, a red
/// minus, the band greyed and the name struck through ("Wykluczone").
struct PlaceBands: View {
    @Environment(AppModel.self) private var model
    @Binding var tokens: [SearchToken]
    /// Picked museums are left out, not asked alone.
    let out: Bool
    /// The search field's words while the group is open ("Muzeum albo
    /// miasto"): the museums the server finds for them.
    var filter: String = ""

    @State private var places: [PlaceHit] = []
    @State private var loading = false
    /// Pictures Wikidata gave for museums with no work in the catalogue
    /// ("" none), by key.
    @State private var pictures: [String: String] = [:]

    private var pickedKeys: [String] {
        tokens.filter { $0.kind == "museum" || $0.kind == SearchToken.museumOut }.map(\.key)
    }

    /// The list: picked museums the list doesn't hold first (one held on a
    /// work's card, an older search's), then the server's.
    private var rows: [PlaceHit] {
        let listed = Set(places.map(\.key))
        let wanted = filter.trimmingCharacters(in: .whitespaces)
        let missing = wanted.isEmpty
            ? pickedKeys.filter { !listed.contains($0) }.map { PlaceHit(key: $0, name: model.placeName($0)) }
            : []
        return missing + places
    }

    var body: some View {
        LazyVStack(spacing: 8) {
            ForEach(rows) { place in
                band(place)
            }
            if !filter.isEmpty, rows.isEmpty, !loading {
                Text("Żadne muzeum ani miasto nie pasuje do „\(filter)”.")
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .task(id: filter) {
            // The list as last seen, at once; the server's comes after.
            if filter.isEmpty, places.isEmpty { places = model.placeList }
            // Typing: a moment's pause before the server (and Wikidata) is asked.
            if !filter.isEmpty { try? await Task.sleep(for: .milliseconds(300)) }
            guard !Task.isCancelled else { return }
            await load()
        }
    }

    private func load() async {
        loading = true
        defer { loading = false }
        let asked = filter
        guard let found = try? await model.backend.places(query: asked), !Task.isCancelled, asked == filter else {
            return
        }
        if asked.isEmpty {
            model.placesLoaded(found)
        } else {
            for place in found { model.placeNames[place.key] = place.name }
        }
        withAnimation(.snappy(duration: 0.2)) { places = found }
    }

    private func picked(_ key: String) -> Bool {
        tokens.contains { ($0.kind == "museum" || $0.kind == SearchToken.museumOut) && $0.key == key }
    }

    private func toggle(_ place: PlaceHit) {
        model.placeNames[place.key] = place.name
        withAnimation(.snappy(duration: 0.2)) {
            if picked(place.key) {
                tokens.removeAll { ($0.kind == "museum" || $0.kind == SearchToken.museumOut) && $0.key == place.key }
            } else {
                tokens.append(SearchToken.museum(place.key, name: place.name, out: out))
            }
        }
    }

    /// The work behind a museum's name: the catalogue's, else Wikidata's.
    private func picture(_ place: PlaceHit) -> ImageRef? {
        if !place.itemId.isEmpty { return .thumb(place.itemId) }
        let address = place.picture.isEmpty ? pictures[place.key] ?? "" : place.picture
        return URL(string: address).map(ImageRef.url)
    }

    private func band(_ place: PlaceHit) -> some View {
        let on = picked(place.key)
        return Button { toggle(place) } label: {
            PlaceBand(place: place, picture: picture(place), on: on, out: out)
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.selection, trigger: on)
        .accessibilityLabel(on && out ? "\(place.name), \(place.city), wykluczone" : "\(place.name), \(place.city)")
        .accessibilityAddTraits(on ? .isSelected : [])
        .task(id: place.key) {
            // A museum with no work here: Wikidata's picture, once.
            guard place.itemId.isEmpty, place.picture.isEmpty, pictures[place.key] == nil,
                  SearchToken.isPlace(place.key), !place.key.hasPrefix("name:") else { return }
            let found = (try? await model.backend.placePicture(key: place.key))?.picture ?? ""
            if !Task.isCancelled { withAnimation(.easeOut(duration: 0.3)) { pictures[place.key] = found } }
        }
    }
}

/// One museum's band: the mesh first; the work's picture, once it is in,
/// fades in over it (Mateusz 2026-11-08: "wejdzie płynnie"), under the
/// same shade from the left and white name. A picture that never comes
/// leaves the mesh, with nothing blinking.
struct PlaceBand: View {
    @Environment(AppModel.self) private var model
    let place: PlaceHit
    let picture: ImageRef?
    let on: Bool
    let out: Bool

    /// The picture is in (for `picture`).
    @State private var shownRef: ImageRef?

    private var struck: Bool { on && out }
    private var pictured: Bool { picture != nil && shownRef == picture }

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(place.name)
                    .font(.serif(18))
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
                    .strikethrough(struck)
                if !place.city.isEmpty {
                    Text(place.city.uppercased())
                        .font(.caption2.weight(.medium))
                        .tracking(1.1)
                        .opacity(0.85)
                        .strikethrough(struck)
                }
            }
            .foregroundStyle(.white)
            .opacity(struck ? 0.75 : 1)
            Spacer(minLength: 4)
            mark
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 9)
        .frame(maxWidth: .infinity, minHeight: 62, alignment: .leading)
        .background { backdrop }
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .contentShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        // Scrolled back to: a picture already in memory shows at once.
        .onAppear { if inMemory(picture) { shownRef = picture } }
        .environment(\.artImageLoaded) { ref in
            // Told also when it gave up: only a picture really in counts.
            guard ref == picture, inMemory(ref) else { return }
            withAnimation(.easeOut(duration: 0.4)) { shownRef = ref }
        }
    }

    private static let maxPixel: CGFloat = 720

    private func inMemory(_ ref: ImageRef?) -> Bool {
        guard let ref, let request = model.backend.request(for: ref) else { return false }
        return ImageLoader.inMemory(for: request, maxPixel: Self.maxPixel) != nil
    }

    @ViewBuilder private var mark: some View {
        Image(systemName: on ? (out ? "minus.circle.fill" : "checkmark.circle.fill") : "circle")
            .font(.title3)
            .symbolRenderingMode(.palette)
            .foregroundStyle(
                on ? (out ? Color.white : Color(hex: 0x1D1B18)) : Color.white.opacity(0.8),
                on ? (out ? Theme.vermilion : Color.white) : Color.clear
            )
            .contentTransition(.symbolEffect(.replace))
    }

    private var backdrop: some View {
        ZStack {
            OrganicMesh(seed: place.key + place.name)
                .opacity(struck ? 0.7 : 1)
            if let picture {
                // Cropped around the faces or what draws the eye, as the
                // tiles are (Mateusz 2026-11-08).
                ArtImage(ref: picture, placeholder: .clear, maxPixel: Self.maxPixel, subjectFocus: true)
                    .opacity(pictured ? 1 : 0)
            }
            // The same shade from the left on every band, picture or mesh,
            // and white names on all (Mateusz: "żeby wyglądało spójnie").
            LinearGradient(
                stops: [
                    .init(color: .black.opacity(struck ? 0.8 : 0.62), location: 0),
                    .init(color: .black.opacity(struck ? 0.6 : 0.15), location: 0.75),
                ],
                startPoint: .leading, endPoint: .trailing
            )
        }
        .grayscale(struck ? 1 : 0)
    }
}

/// A soft mesh of three muted earth colours (ochre, terracotta, sage,
/// dusty blue, heather, straw) over the mat: the same for the same seed,
/// deeper in the dark (Mateusz 2026-11-08: "delikatny gradient organiczny").
struct OrganicMesh: View {
    @Environment(\.colorScheme) private var scheme
    let seed: String

    /// (light, dark) of each colour.
    private static let tones: [(UInt32, UInt32)] = [
        (0xDEC4A0, 0x785C3A),  // ochre
        (0xD6AC96, 0x764634),  // terracotta
        (0xB8C4AA, 0x465842),  // sage
        (0xAABACA, 0x3A4C62),  // dusty blue
        (0xCCB6C4, 0x60465A),  // heather
        (0xE2D2AC, 0x6E623C),  // straw
    ]

    /// The seed's bytes mixed (FNV-1a): Swift's own hash changes each launch.
    private var digest: [UInt8] {
        var hash: UInt64 = 0xCBF2_9CE4_8422_2325
        var out: [UInt8] = []
        for round in 0 ..< 3 {
            for byte in seed.utf8 {
                hash = (hash ^ UInt64(byte)) &* 0x100_0000_01B3
            }
            hash = (hash ^ UInt64(round)) &* 0x100_0000_01B3
            out += withUnsafeBytes(of: hash.littleEndian) { Array($0) }
        }
        return out
    }

    var body: some View {
        let dark = scheme == .dark
        MeshGradient(width: 3, height: 3, points: points, colors: colours(dark: dark))
            .opacity(dark ? 0.9 : 0.95)
            .background(Self.base(dark: dark))
    }

    private static func base(dark: Bool) -> Color { Color(hex: dark ? 0x262320 : 0xEFE8DC) }

    /// The mesh's points, its middles nudged a little by the seed.
    private var points: [SIMD2<Float>] {
        let bytes = digest
        func nudge(_ i: Int) -> Float { Float(Int(bytes[3 + i]) % 30 - 15) / 100 }
        return [
            [0, 0], [0.5 + nudge(0), 0], [1, 0],
            [0, 0.5 + nudge(1)], [0.5 + nudge(2), 0.5 + nudge(3)], [1, 0.5 + nudge(4)],
            [0, 1], [0.5 + nudge(5), 1], [1, 1],
        ]
    }

    /// Three of the tones and the mat, laid out one of two ways.
    private func colours(dark: Bool) -> [Color] {
        let bytes = digest
        let base = Self.base(dark: dark)
        let picks = (0 ..< 3).map { Self.tones[Int(bytes[$0]) % Self.tones.count] }
        let c = picks.map { Color(hex: dark ? $0.1 : $0.0) }
        return Int(bytes[9]) % 2 == 0
            ? [c[0], base, c[2], c[0], c[1], base, base, c[1], c[2]]
            : [base, c[1], c[0], c[2], c[1], c[0], c[2], base, c[1]]
    }
}
