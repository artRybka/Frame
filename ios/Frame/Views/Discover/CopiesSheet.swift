import SwiftUI

/// "Szukaj lepszej kopii": every copy of a work's picture the server's
/// sources have, as they answer, the sharpest on the frame first. A tap
/// opens one spot of both pictures at the frame's scale; "Użyj tej kopii"
/// puts the copy in the work's place (the work keeps its id, hearts,
/// playlists and crops).
struct CopiesSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let item: Item
    /// Told the work with its new picture once one is picked.
    let picked: (Item) -> Void

    @State private var copies: [CopyView] = []
    @State private var sources: [String] = []
    /// Sources that answered: how many copies they had, nil when they failed.
    @State private var answered: [String: Int?] = [:]
    @State private var done = false
    @State private var failed = false
    /// "Nie pasują" opened or closed by hand; nil until then.
    @State private var showOff: Bool?
    @State private var path: [CopyView] = []

    private var current: CopyView? { copies.first(where: \.isCurrent) }
    private var better: [CopyView] {
        copies.filter { !$0.isCurrent && ($0.verdict == "better" || $0.verdict == "warn") }
            .sorted { a, b in
                if (a.verdict == "better") != (b.verdict == "better") { return a.verdict == "better" }
                // A tile set first: sharp far closer in, in full screen.
                if a.hasTiles != b.hasTiles { return a.hasTiles }
                return (a.gain ?? 0) > (b.gain ?? 0)
            }
    }
    private var checking: [CopyView] { copies.filter { $0.verdict == "checking" } }
    private var others: [CopyView] {
        copies.filter { !$0.isCurrent && $0.verdict == "worse" }
            .sorted { a, b in a.isOwn != b.isOwn ? a.isOwn : a.side > b.side }
    }
    private var off: [CopyView] { copies.filter { $0.verdict == "off" } }
    private var failedSources: [String] { sources.filter { answered[$0] == .some(nil) } }

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if let current {
                        Eyebrow("Teraz na karcie i ramce")
                        CopyRow(copy: current, work: item)
                    } else if !failed {
                        CopyRow.placeholder
                    }
                    if !done && !failed { progress }
                    if failed { failure }
                    if !better.isEmpty {
                        header("Lepsze · \(better.count)", trailing: done ? summary : nil)
                        ForEach(Array(better.enumerated()), id: \.element.id) { index, copy in
                            link(copy, best: index == 0)
                        }
                    } else if done {
                        bestAlready
                    }
                    if !checking.isEmpty {
                        header("Porównuję · \(checking.count)")
                        ForEach(checking) { CopyRow(copy: $0, work: item) }
                    }
                    if !others.isEmpty {
                        header("Inne kopie · \(others.count)")
                        ForEach(others) { link($0) }
                    }
                    if !off.isEmpty { offSection }
                    if item.sharper != nil, let own = copies.first(where: \.isOwn) {
                        Button("Przywróć zdjęcie muzeum") { path.append(own) }
                            .buttonStyle(SecondaryButtonStyle())
                            .padding(.top, 6)
                    }
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, 30)
                .pageWidth()
                .animation(.snappy, value: copies)
            }
            .paperPage()
            .navigationTitle("Kopie dzieła")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Zamknij", systemImage: "xmark") { dismiss() }
                }
            }
            .navigationDestination(for: CopyView.self) { copy in
                CopyCompare(item: item, copy: copy, current: current) { updated in
                    picked(updated)
                    dismiss()
                }
            }
        }
        .task { await look() }
    }

    // MARK: Parts

    private func link(_ copy: CopyView, best: Bool = false) -> some View {
        NavigationLink(value: copy) {
            CopyRow(copy: copy, work: item, best: best, chevron: true)
        }
        .buttonStyle(.plain)
    }

    private func header(_ title: String, trailing: String? = nil) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Eyebrow(title)
            Spacer()
            if let trailing {
                Text(trailing).font(.caption).foregroundStyle(Theme.inkSoft)
            }
        }
        .padding(.top, 6)
    }

    private var progress: some View {
        let count = answered.count
        return VStack(alignment: .leading, spacing: 8) {
            HStack {
                Eyebrow(sources.isEmpty ? "Szukam" : "Szukam w \(sources.count) \(Self.sourcesWord(sources.count))")
                Spacer()
                if !sources.isEmpty {
                    Text("\(count) / \(sources.count)")
                        .font(.caption.monospacedDigit()).foregroundStyle(Theme.inkSoft)
                }
            }
            ProgressView(value: Double(count), total: Double(max(sources.count, 1)))
                .tint(Theme.ink)
            FlowLayout(spacing: 5) {
                ForEach(sources, id: \.self) { key in sourceChip(key) }
            }
        }
        .padding(.top, 4)
    }

    private func sourceChip(_ key: String) -> some View {
        let name = Self.shortName(key)
        let state = answered[key]
        let found = state.flatMap { $0 } ?? 0
        let text: String = switch state {
        case .none: name
        case .some(nil): "\(name) ✕"
        case .some: found > 0 ? "\(name) · \(found)" : "\(name) ✓"
        }
        let hit = found > 0
        let gone = state == .some(nil)
        return Text(text)
            .font(.caption2.weight(.medium))
            .foregroundStyle(hit ? Theme.paper : gone ? Theme.vermilion : state == nil ? Theme.inkSoft : Theme.ink)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Capsule().fill(hit ? Theme.ink : gone ? Color.clear : Theme.mat))
            .overlay(Capsule().strokeBorder(gone ? Theme.vermilion.opacity(0.4) : .clear, lineWidth: 1))
    }

    private var summary: String {
        let missing = failedSources.count
        let all = "\(sources.count) \(Self.sourcesWord(sources.count, nominative: true))"
        return missing == 0 ? all : "\(all), \(missing) bez odpowiedzi"
    }

    private var bestAlready: some View {
        VStack(spacing: 6) {
            Image(systemName: "checkmark.circle")
                .font(.system(size: 30, weight: .light))
                .foregroundStyle(Theme.good)
            Text("To najlepsza kopia")
                .font(.title3.weight(.semibold))
                .fontDesign(.serif)
            Text(bestNote)
                .font(.footnote)
                .foregroundStyle(Theme.inkSoft)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
    }

    private var bestNote: String {
        var note = sources.isEmpty
            ? "Żadne źródło nie ma ostrzejszej."
            : "Żadne z \(sources.count) \(Self.sourcesWord(sources.count)) nie ma ostrzejszej."
        let missing = failedSources.map(Self.shortName)
        if !missing.isEmpty {
            note += " Bez odpowiedzi: \(missing.joined(separator: ", ")). Zapytam przy następnym razie."
        }
        return note
    }

    private var failure: some View {
        VStack(spacing: 10) {
            Text("Nie udało się zapytać źródeł")
                .font(.headline)
            Button("Spróbuj ponownie", systemImage: "arrow.clockwise") {
                Task { await look() }
            }
            .buttonStyle(SecondaryButtonStyle())
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
    }

    /// "Nie pasują" opens by itself when it holds all a search found.
    private var offOpen: Bool { showOff ?? (better.isEmpty && others.isEmpty && checking.isEmpty) }

    private var offSection: some View {
        let open = offOpen
        return VStack(alignment: .leading, spacing: 10) {
            Button {
                withAnimation(.snappy) { showOff = !open }
            } label: {
                HStack {
                    Eyebrow("Nie pasują · \(off.count)")
                    Spacer()
                    Image(systemName: "chevron.down")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(Theme.inkSoft)
                        .rotationEffect(.degrees(open ? 180 : 0))
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .padding(.top, 8)
            .overlay(alignment: .top) { Rectangle().fill(Theme.hairline).frame(height: 1) }
            if open {
                ForEach(off) { copy in
                    if copy.comparable {
                        NavigationLink(value: copy) {
                            CopyRow(copy: copy, work: item, chevron: true).opacity(0.6)
                        }
                        .buttonStyle(.plain)
                    } else if let page = URL(string: copy.url), !copy.url.isEmpty {
                        // No picture to compare: its page at the source.
                        Link(destination: page) {
                            CopyRow(copy: copy, work: item, chevron: true).opacity(0.6)
                        }
                        .buttonStyle(.plain)
                    } else {
                        CopyRow(copy: copy, work: item).opacity(0.6)
                    }
                }
            }
        }
    }

    // MARK: Loading

    private func look() async {
        failed = false
        done = false
        copies = []
        answered = [:]
        do {
            for try await line in try await model.backend.copies(itemID: item.id) {
                apply(line)
            }
            done = true
        } catch {
            guard !error.isCancellation else { return }
            if copies.isEmpty { failed = true } else { done = true }
        }
    }

    private func apply(_ line: CopyLine) {
        switch line.kind {
        case "start":
            sources = line.sources ?? []
        case "copy":
            guard let copy = line.copy else { return }
            if let index = copies.firstIndex(where: { $0.id == copy.id }) {
                copies[index] = copy
            } else {
                copies.append(copy)
            }
        case "drop":
            copies.removeAll { $0.id == line.itemId }
        case "source":
            guard let key = line.source else { return }
            answered[key] = line.failed == true ? .some(nil) : .some(line.found ?? 0)
        case "end":
            done = true
        default:
            break
        }
    }

    // MARK: Words

    /// "źródeł"/"źródłach" after a count.
    static func sourcesWord(_ count: Int, nominative: Bool = false) -> String {
        if nominative {
            if count == 1 { return "źródło" }
            let tens = count % 100 / 10, ones = count % 10
            return tens != 1 && (2 ... 4).contains(ones) ? "źródła" : "źródeł"
        }
        return count == 1 ? "źródle" : "źródłach"
    }

    /// A source's name, short enough for a chip.
    static func shortName(_ key: String) -> String {
        switch key {
        case "met": "Met"
        case "cma": "Cleveland"
        case "aic": "Chicago"
        case "smk": "SMK"
        case "nga": "NGA"
        case "mnw": "MNW"
        case "mnk": "MNK"
        case "vam": "V&A"
        case "wellcome": "Wellcome"
        case "courtauld": "Courtauld"
        case "louvre": "Luwr"
        case "loc": "LoC"
        case "getty": "Getty"
        default: Names.source(key)
        }
    }
}

/// One copy in the list: its thumbnail, where it is from, its size, how
/// much of the frame's 2560 px it gives, and why it is better or not.
struct CopyRow: View {
    let copy: CopyView
    let work: Item
    var best = false
    var chevron = false

    static let frameSide = 2560

    var body: some View {
        HStack(spacing: 12) {
            ArtImage(ref: .thumb(copy.isMuseums ? work.id : copy.itemId), placeholder: Theme.mat, maxPixel: 240)
                .frame(width: 74, height: 56)
                .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 4) {
                    Text(Self.place(copy)).font(.subheadline.weight(.semibold)).lineLimit(1)
                    if copy.isCurrent {
                        Text("· obecne").font(.subheadline).foregroundStyle(Theme.inkSoft)
                    }
                }
                Text(Self.size(copy))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(Theme.inkSoft)
                if copy.side > 0 && copy.verdict != "off" {
                    FrameBar(fraction: Double(min(copy.side, Self.frameSide)) / Double(Self.frameSide))
                }
                FlowLayout(spacing: 4) {
                    ForEach(Self.tags(copy), id: \.text) { CopyTag(tag: $0) }
                }
            }
            Spacer(minLength: 0)
            if chevron {
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Theme.inkSoft)
            }
        }
        .padding(8)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(copy.isCurrent ? Color.clear : Theme.card)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .strokeBorder(
                    best ? Theme.ink : Theme.hairline,
                    style: StrokeStyle(lineWidth: best ? 1.5 : 1, dash: copy.isCurrent ? [4, 3] : [])
                )
        )
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    static var placeholder: some View {
        RoundedRectangle(cornerRadius: 10, style: .continuous)
            .fill(Theme.mat.opacity(0.6))
            .frame(height: 74)
    }

    static func place(_ copy: CopyView) -> String {
        copy.museum.isEmpty ? Names.source(copy.source) : copy.museum
    }

    static func size(_ copy: CopyView) -> String {
        guard copy.width > 0, copy.height > 0 else { return "rozmiar nieznany" }
        var text = "\(copy.width) × \(copy.height) px"
        if copy.isOwn { text += " · zdjęcie muzeum" }
        if copy.isLarger { text += " · plik z muzeum" }
        return text
    }

    static func times(_ value: Double) -> String {
        "×" + value.formatted(.number.precision(.fractionLength(1)).locale(Locale(identifier: "pl_PL")))
    }

    static func tags(_ copy: CopyView) -> [CopyTag.Tag] {
        var tags: [CopyTag.Tag] = []
        if copy.isCurrent {
            if copy.side >= frameSide {
                tags.append(.init(text: "Pełna ostrość na ramce", tone: .good))
            } else if copy.side > 0 {
                tags.append(.init(text: "Mniej niż ramka (2560)", tone: .plain))
            }
            if copy.hasTiles, let tag = noteTag("tiles") { tags.append(tag) }
            if copy.chosen { tags.append(.init(text: "Wybrana przez Ciebie", tone: .plain)) }
            return tags
        }
        switch copy.verdict {
        case "checking":
            return [.init(text: "Porównuję…", tone: .plain)]
        case "better", "warn":
            // Offered for its tiles, about as sharp on the frame: no "×1,0".
            if let gain = copy.gain, !(copy.hasTiles && gain < 1.05) {
                tags.append(.init(text: "Ostrzejsza \(times(gain))", tone: .good))
            }
        case "worse":
            if copy.isOwn {
                tags.append(.init(text: "Zdjęcie muzeum", tone: .plain))
            } else if let gain = copy.gain, gain < 0.95 {
                tags.append(.init(text: "Mniejsza", tone: .plain))
            } else {
                tags.append(.init(text: "Nie ostrzejsza", tone: .plain))
            }
        default:
            break
        }
        for note in copy.notes {
            guard let tag = noteTag(note) else { continue }
            if copy.verdict == "off" && tag.tone == .good { continue }
            tags.append(tag)
        }
        return tags
    }

    static func noteTag(_ note: String) -> CopyTag.Tag? {
        switch note {
        case "whole": CopyTag.Tag(text: "Całość", tone: .good)
        case "colours": CopyTag.Tag(text: "Te kolory", tone: .good)
        case "colour-off": CopyTag.Tag(text: "Inne kolory", tone: .warn)
        case "fragment": CopyTag.Tag(text: "Tylko fragment", tone: .bad)
        case "page": CopyTag.Tag(text: "Z marginesem", tone: .bad)
        case "turned": CopyTag.Tag(text: "Obrócona", tone: .bad)
        case "grey": CopyTag.Tag(text: "Czarno-biała", tone: .bad)
        case "coloured": CopyTag.Tag(text: "Pokolorowana", tone: .bad)
        case "reproduction": CopyTag.Tag(text: "Reprodukcja", tone: .bad)
        case "other": CopyTag.Tag(text: "Inne dzieło", tone: .bad)
        case "unseen": CopyTag.Tag(text: "Nie udało się porównać", tone: .bad)
        case "larger": CopyTag.Tag(text: "Większe zdjęcie muzeum", tone: .good)
        case "tiles": CopyTag.Tag(text: "Kafle przy powiększeniu", tone: .good)
        default: nil
        }
    }
}

/// How much of the frame's 2560 px a picture gives.
struct FrameBar: View {
    let fraction: Double

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule().fill(Theme.hairline)
                Capsule()
                    .fill(fraction >= 1 ? Theme.ink : Theme.inkSoft)
                    .frame(width: geo.size.width * min(max(fraction, 0), 1))
            }
        }
        .frame(height: 4)
        .padding(.top, 2)
        .accessibilityHidden(true)
    }
}

/// A small capital label: why a copy is better, or what is wrong with it.
struct CopyTag: View {
    struct Tag: Hashable {
        enum Tone { case good, warn, bad, plain }
        var text: String
        var tone: Tone
    }

    let tag: Tag

    private var color: Color {
        switch tag.tone {
        case .good: Theme.good
        case .warn: Theme.warn
        case .bad: Theme.bad
        case .plain: Theme.inkSoft
        }
    }

    var body: some View {
        Text(tag.text)
            .font(.system(size: 9.5, weight: .bold))
            .tracking(0.6)
            .textCase(.uppercase)
            .foregroundStyle(color)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .overlay(
                RoundedRectangle(cornerRadius: 3, style: .continuous)
                    .strokeBorder(tag.tone == .plain ? Theme.hairline : color.opacity(0.5), lineWidth: 1)
            )
    }
}

/// One copy against the picture shown now: the same spot of both at the
/// frame's scale under a slider, their numbers, and "Użyj tej kopii".
struct CopyCompare: View {
    @Environment(AppModel.self) private var model
    let item: Item
    let copy: CopyView
    let current: CopyView?
    let chosen: (Item) -> Void

    @State private var spot: CopySpot?
    @State private var failed = false
    @State private var split: CGFloat = 0.5
    @State private var picking = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                closeUp
                Text("Ten sam fragment, w skali ramki. Przesuń suwak; dotknij miniatury, by obejrzeć inne miejsce.")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: .infinity)
                numbers
                if copy.choosable {
                    if !copy.fits {
                        Text(Self.misfit(copy))
                            .font(.footnote)
                            .foregroundStyle(Theme.inkSoft)
                    }
                    if copy.fits {
                        chooseButton.buttonStyle(PrimaryButtonStyle())
                    } else {
                        chooseButton.buttonStyle(SecondaryButtonStyle())
                    }
                }
                if let url = URL(string: copy.url), !copy.url.isEmpty {
                    Link(destination: url) {
                        Text("Otwórz w źródle")
                            .labelButtonType()
                            .foregroundStyle(Theme.ink)
                            .underline(color: Theme.hairline)
                    }
                    .frame(maxWidth: .infinity)
                }
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 30)
            .pageWidth()
        }
        .paperPage()
        .navigationTitle(CopyRow.place(copy))
        .navigationBarTitleDisplayMode(.inline)
        .task { await load(x: nil, y: nil) }
    }

    private var otherLabel: String {
        copy.isOwn ? "Zdjęcie muzeum" : copy.isLarger ? "Większe zdjęcie" : "Ta kopia"
    }

    private var chooseLabel: String {
        if copy.isOwn { return "Przywróć zdjęcie muzeum" }
        if copy.isLarger { return "Pobierz większe zdjęcie" }
        return copy.fits ? "Użyj tej kopii" : "Użyj mimo to"
    }

    private var chooseButton: some View {
        Button {
            Task { await choose() }
        } label: {
            HStack(spacing: 8) {
                if picking { ProgressView().tint(copy.fits ? Theme.paper : Theme.ink) }
                Text(chooseLabel)
            }
        }
        .disabled(picking)
    }

    /// Why a copy that does not fit may still be wanted, and what to expect.
    static func misfit(_ copy: CopyView) -> String {
        if copy.notes.contains("other") {
            return "Wygląda na inne dzieło o podobnym tytule. Jeśli to jednak ten sam obraz, możesz go użyć."
        }
        if copy.notes.contains("page") {
            return "To zdjęcie ma wokół obrazu margines. Możesz go użyć i przyciąć w Kadrowaniu."
        }
        if copy.notes.contains("fragment") {
            return "To tylko fragment obrazu. Na ramce zobaczysz tylko tę część."
        }
        return "Ta kopia różni się od zdjęcia muzeum. Możesz jej użyć mimo to."
    }

    private var closeUp: some View {
        GeometryReader { geo in
            let width = geo.size.width
            ZStack {
                if let spot, let here = UIImage(data: spot.current), let there = UIImage(data: spot.copy) {
                    Image(uiImage: here).resizable().interpolation(.high).scaledToFill()
                        .frame(width: width, height: width)
                    Image(uiImage: there).resizable().interpolation(.high).scaledToFill()
                        .frame(width: width, height: width)
                        .mask(alignment: .trailing) {
                            Rectangle().frame(width: width * (1 - split))
                        }
                    Rectangle().fill(.white).frame(width: 2)
                        .shadow(color: .black.opacity(0.3), radius: 1)
                        .position(x: width * split, y: width / 2)
                    Image(systemName: "chevron.left.chevron.right")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(Color(white: 0.1))
                        .frame(width: 32, height: 32)
                        .background(Circle().fill(.white).shadow(color: .black.opacity(0.35), radius: 4, y: 2))
                        .position(x: width * split, y: width / 2)
                    caption("Obecne").position(x: 44, y: width - 18)
                    caption(otherLabel).position(x: width - 54, y: width - 18)
                } else if failed {
                    VStack(spacing: 8) {
                        Text("Nie udało się pobrać zbliżenia").font(.subheadline)
                        Button("Spróbuj ponownie") { Task { await load(x: nil, y: nil) } }
                            .buttonStyle(SecondaryButtonStyle())
                            .frame(maxWidth: 220)
                    }
                } else {
                    Theme.mat
                    ProgressView()
                }
                if spot != nil { minimap.position(x: width - 48, y: 44) }
            }
            .frame(width: width, height: width)
            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0).onChanged { value in
                    split = min(max(value.location.x / max(width, 1), 0), 1)
                }
            )
        }
        .aspectRatio(1, contentMode: .fit)
        .accessibilityLabel("Porównanie fragmentu: obecne zdjęcie i \(otherLabel.lowercased())")
    }

    private func caption(_ text: String) -> some View {
        Text(text)
            .font(.system(size: 10, weight: .bold))
            .tracking(1)
            .textCase(.uppercase)
            .foregroundStyle(.white)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(RoundedRectangle(cornerRadius: 3).fill(.black.opacity(0.5)))
            .fixedSize()
    }

    /// The whole picture, small, with the spot on it; a tap picks another.
    private var minimap: some View {
        let ratio = CGFloat(item.width ?? 4) / CGFloat(max(item.height ?? 3, 1))
        let w: CGFloat = ratio >= 1 ? 76 : 76 * ratio
        let h: CGFloat = ratio >= 1 ? 76 / ratio : 76
        return ArtImage(ref: .thumb(item.id), placeholder: Theme.mat, maxPixel: 240, contentMode: .fill)
            .frame(width: w, height: h)
            .clipped()
            .overlay(alignment: .topLeading) {
                if let spot {
                    Rectangle()
                        .strokeBorder(.white, lineWidth: 1.5)
                        .shadow(color: .black.opacity(0.5), radius: 1)
                        .frame(width: max(w * spot.w, 6), height: max(h * spot.h, 6))
                        .offset(x: w * (spot.x - spot.w / 2), y: h * (spot.y - spot.h / 2))
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 3))
            .shadow(color: .black.opacity(0.4), radius: 4, y: 2)
            .contentShape(Rectangle())
            .highPriorityGesture(
                SpatialTapGesture().onEnded { tap in
                    let x = min(max(tap.location.x / w, 0), 1), y = min(max(tap.location.y / h, 0), 1)
                    Task { await load(x: x, y: y) }
                }
            )
            .accessibilityLabel("Miniatura: dotknij, by wybrać inne miejsce")
    }

    private var numbers: some View {
        Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 8) {
            GridRow {
                Text("")
                Text("Obecne").labelButtonType().foregroundStyle(Theme.inkSoft)
                Text(otherLabel).labelButtonType().foregroundStyle(Theme.inkSoft)
            }
            Divider()
            row("Plik", current.map(CopyRow.size(_:)) ?? "—", CopyRow.size(copy))
            Divider()
            row("Na ramce", current.map(onFrame) ?? "—", onFrame(copy))
            Divider()
            row("Kadr", "—", crop)
            Divider()
            row("Kolory", "—", colours)
        }
        .font(.subheadline)
    }

    private func row(_ label: String, _ here: String, _ there: String) -> some View {
        GridRow {
            Text(label).foregroundStyle(Theme.inkSoft)
            Text(here).foregroundStyle(Theme.ink)
            Text(there).foregroundStyle(Theme.ink).fontWeight(.semibold)
        }
    }

    private func onFrame(_ view: CopyView) -> String {
        guard view.side > 0 else { return "—" }
        if view.side >= CopyRow.frameSide { return "pełna ostrość" }
        return "powiększone \(CopyRow.times(Double(CopyRow.frameSide) / Double(view.side)))"
    }

    private var crop: String {
        if copy.notes.contains("whole") || copy.isMuseums { return "cały obraz" }
        for note in ["fragment", "page", "turned"] where copy.notes.contains(note) {
            return CopyRow.noteTag(note)?.text.lowercased() ?? note
        }
        return "—"
    }

    private var colours: String {
        if copy.notes.contains("colours") || copy.isMuseums { return "zgodne" }
        for note in ["colour-off", "grey", "coloured"] where copy.notes.contains(note) {
            return CopyRow.noteTag(note)?.text.lowercased() ?? note
        }
        return "—"
    }

    private func load(x: Double?, y: Double?) async {
        failed = false
        do {
            let found = try await model.backend.copySpot(itemID: item.id, copyID: copy.itemId, x: x, y: y)
            withAnimation(.easeInOut(duration: 0.25)) { spot = found }
        } catch {
            guard !error.isCancellation else { return }
            if spot == nil { failed = true } else { model.show(error) }
        }
    }

    private func choose() async {
        picking = true
        defer { picking = false }
        do {
            let updated = try await model.chooseCopy(itemID: item.id, copyID: copy.itemId)
            chosen(updated)
        } catch {
            model.show(error)
        }
    }
}
