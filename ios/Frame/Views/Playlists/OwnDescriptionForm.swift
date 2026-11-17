import SwiftUI

/// What the owner writes of a work of his own, laid out as the work's card
/// (Mateusz 2026-11-16 chose sketch C: "od razu wpisane"): the title, the
/// author and the date in the card's serif with no boxes, the rest as the
/// card's facts, the note under them. What was read off the picture is
/// written into the empty fields at once, a small sparkle beside each while
/// the field still says it, and one line takes it all back ("Wyczyść").
struct OwnDescriptionForm: View {
    @Binding var text: OwnDescription
    /// The work as cut, at the top.
    var picture: UIImage? = nil
    /// The picture's width / height as the corners give it, to check the
    /// size against; the picture takes the size's shape (`OwnWork.ratio`).
    var aspect: Double? = nil
    var hints: OwnHints? = nil
    var readingHints = false
    /// Where his other works hang.
    var places: [String] = []
    /// The size the LiDAR measured, written in when the fields are empty.
    var measured: OwnDepth.Size? = nil

    @State private var heightText = ""
    @State private var widthText = ""
    /// What was written into the fields from the picture: marked while the
    /// field still says it.
    @State private var filled: [String: String] = [:]
    @State private var started = false
    /// The size written in from the LiDAR: marked while the fields still say it.
    @State private var measuredIn: OwnDepth.Size?

    var body: some View {
        VStack(alignment: .leading, spacing: 26) {
            if let picture {
                Image(uiImage: picture)
                    .resizable()
                    .aspectRatio(shape(of: picture), contentMode: .fit)
                    .frame(maxWidth: .infinity, maxHeight: 260)
                    .animation(.easeOut(duration: 0.25), value: shape(of: picture))
                    .shadow(color: .black.opacity(0.18), radius: 12, y: 8)
                    .padding(.top, 8)
            }
            if readingHints && hints == nil {
                Label("Czytam sygnaturę i technikę z obrazu…", systemImage: "sparkles")
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
                    .transition(.opacity)
            } else if !marked.isEmpty {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Image(systemName: "sparkles").foregroundStyle(Theme.inkSoft)
                    Text("Uzupełnione z obrazu. Popraw, jeśli trzeba.")
                        .foregroundStyle(Theme.inkSoft)
                    Spacer(minLength: 8)
                    Button("Wyczyść", action: clearFilled)
                        .font(.footnote.weight(.semibold))
                }
                .font(.footnote)
                .transition(.opacity)
            }
            VStack(alignment: .leading, spacing: 10) {
                serifField("Tytuł", text: $text.title, key: "title", size: 26, weight: .semibold, ink: Theme.ink)
                serifField("Autor", text: $text.artist, key: "artist", size: 18, ink: Theme.ink)
                serifField("Data", text: $text.dateText, key: "date", size: 18, ink: Theme.inkSoft)
            }
            Card {
                factRow("Technika") {
                    HStack(spacing: 6) {
                        trailingField("np. olej na płótnie", text: $text.medium, key: "medium")
                        techniqueMenu
                    }
                }
                Divider()
                VStack(alignment: .leading, spacing: 8) {
                    factRow("Rozmiar") { sizeFields }
                    if sizeMarked {
                        Text("Zmierzone LiDAR-em, bez ramy, ±1–2 cm.")
                            .font(.caption)
                            .foregroundStyle(Theme.inkSoft)
                            .frame(maxWidth: .infinity, alignment: .trailing)
                            .multilineTextAlignment(.trailing)
                            .transition(.opacity)
                    }
                    if let warning = sizeWarning { warningLine(warning) }
                }
                .id("size")
                Divider()
                factRow("Gdzie wisi") {
                    HStack(spacing: 6) {
                        trailingField("np. Salon", text: $text.hangs, key: "hangs")
                        if !places.isEmpty { placesMenu }
                    }
                }
                Divider()
                factRow("Skąd") { trailingField("prezent, po dziadku…", text: $text.origin, key: "origin") }
            }
            VStack(alignment: .leading, spacing: 10) {
                Eyebrow("Notatka")
                TextField("Historia dzieła, co warto pamiętać", text: $text.description, axis: .vertical)
                    .font(.serif(17))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(2 ... 10)
            }
        }
        .onAppear(perform: start)
        .onChange(of: hints) { _, hints in
            if let hints { fill(from: hints) }
        }
        .onChange(of: measured) { _, size in
            if let size { fill(from: size) }
        }
        .onChange(of: heightText) { _, value in text.heightCm = Self.number(value) }
        .onChange(of: widthText) { _, value in text.widthCm = Self.number(value) }
        .onChange(of: text.heightCm) { _, value in
            if Self.number(heightText) != value { heightText = value.map(OwnWork.number) ?? "" }
        }
        .onChange(of: text.widthCm) { _, value in
            if Self.number(widthText) != value { widthText = value.map(OwnWork.number) ?? "" }
        }
        .animation(.easeOut(duration: 0.25), value: hints)
        .animation(.easeOut(duration: 0.2), value: sizeWarning)
    }

    private func start() {
        guard !started else { return }
        started = true
        heightText = text.heightCm.map(OwnWork.number) ?? ""
        widthText = text.widthCm.map(OwnWork.number) ?? ""
        if let hints { fill(from: hints) }
        if let measured { fill(from: measured) }
    }

    // MARK: Fields

    private func serifField(
        _ prompt: String, text value: Binding<String>, key: String, size: CGFloat,
        weight: Font.Weight = .regular, ink: Color
    ) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            TextField(prompt, text: value)
                .font(.serif(size, weight: weight))
                .foregroundStyle(ink)
            filledMark(key)
        }
    }

    @ViewBuilder
    private func filledMark(_ key: String) -> some View {
        if marked.contains(key) {
            Image(systemName: "sparkles")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
                .accessibilityLabel("odczytane z obrazu")
                .transition(.opacity)
        }
    }

    private func factRow<Value: View>(_ title: String, @ViewBuilder value: () -> Value) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(bound: title).foregroundStyle(Theme.inkSoft)
            Spacer(minLength: 16)
            value()
        }
        .font(.subheadline)
    }

    private func trailingField(_ prompt: String, text value: Binding<String>, key: String) -> some View {
        HStack(spacing: 4) {
            TextField(prompt, text: value)
                .multilineTextAlignment(.trailing)
                .foregroundStyle(Theme.ink)
            filledMark(key)  // after the value, as by the title
        }
    }

    private var sizeFields: some View {
        HStack(spacing: 6) {
            // Both numbers against the "×": "65 × 81", not "65 ×     81".
            sizeField("wys.", text: $heightText, alignment: .trailing)
            Text("×").foregroundStyle(Theme.inkSoft)
            sizeField("szer.", text: $widthText, alignment: .leading)
            Text("cm").foregroundStyle(Theme.inkSoft)
            if sizeMarked {
                Image(systemName: "ruler")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .accessibilityLabel("zmierzone")
                    .transition(.opacity)
            }
        }
    }

    private func sizeField(_ prompt: String, text value: Binding<String>, alignment: TextAlignment) -> some View {
        // No prompt once a number is in: a field keeps its prompt's width.
        TextField(value.wrappedValue.isEmpty ? prompt : "", text: value)
            .keyboardType(.decimalPad)
            .multilineTextAlignment(alignment)
            .foregroundStyle(Theme.ink)
            .fixedSize()  // as wide as its number (or "wys."): no gap before "cm"
            .frame(minWidth: 24, alignment: alignment == .trailing ? .trailing : .leading)
    }

    private func warningLine(_ warning: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Image(systemName: "exclamationmark.triangle")
                .foregroundStyle(Theme.warn)
            Text(bound: warning)
                .foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            if swapFits {
                Button("Zamień") {
                    let height = heightText
                    heightText = widthText
                    widthText = height
                }
                .font(.caption.weight(.semibold))
            }
        }
        .font(.caption)
        .transition(.opacity)
    }

    /// The techniques and supports, as a menu by the field.
    private var techniqueMenu: some View {
        Menu {
            Section("Technika") {
                ForEach(OwnTechnique.techniques, id: \.key) { item in
                    Button(item.name) { setTechnique(item.key) }
                }
            }
            Section("Podłoże") {
                ForEach(OwnTechnique.supports, id: \.key) { item in
                    Button(item.name) { setSupport(item.key) }
                }
            }
        } label: {
            Image(systemName: "chevron.up.chevron.down")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Theme.inkSoft)
                .frame(width: 24, height: 24)
        }
        .accessibilityLabel("Wybierz technikę")
    }

    private var placesMenu: some View {
        Menu {
            ForEach(places, id: \.self) { place in
                Button(place) { text.hangs = place }
            }
        } label: {
            Image(systemName: "chevron.up.chevron.down")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Theme.inkSoft)
                .frame(width: 24, height: 24)
        }
        .accessibilityLabel("Gdzie wiszą inne")
    }

    private func setTechnique(_ key: String) {
        let support = OwnTechnique.read(text.medium)?.support
        text.medium = OwnTechnique.medium(technique: key, support: support)
    }

    private func setSupport(_ key: String) {
        let technique = OwnTechnique.read(text.medium)?.technique
        text.medium = OwnTechnique.medium(technique: technique, support: key)
    }

    // MARK: Filled from the picture

    private static let fields: [(key: String, path: WritableKeyPath<OwnDescription, String>)] = [
        ("title", \.title), ("artist", \.artist), ("date", \.dateText), ("medium", \.medium),
    ]

    /// The fields that still say what was read off the picture.
    private var marked: Set<String> {
        Set(Self.fields.filter { field in filled[field.key].map { $0 == text[keyPath: field.path] } ?? false }.map(\.key))
    }

    private func fill(from hints: OwnHints) {
        let medium = hints.technique.isEmpty || hints.technique == "unknown" ? ""
            : OwnTechnique.medium(technique: hints.technique, support: hints.support == "unknown" ? nil : hints.support)
        let read = ["title": hints.title, "artist": hints.artist, "date": hints.date, "medium": medium]
        var done: [String: String] = [:]
        withAnimation(.easeOut(duration: 0.25)) {
            for field in Self.fields {
                guard let value = read[field.key], !value.isEmpty,
                      text[keyPath: field.path].trimmingCharacters(in: .whitespaces).isEmpty
                else { continue }
                text[keyPath: field.path] = value
                done[field.key] = value
            }
            filled = done
        }
    }

    private func clearFilled() {
        let keys = marked
        withAnimation(.easeOut(duration: 0.2)) {
            for field in Self.fields where keys.contains(field.key) { text[keyPath: field.path] = "" }
            filled = [:]
        }
    }

    // MARK: The size

    /// The fields still say what the LiDAR measured.
    private var sizeMarked: Bool {
        guard let measuredIn else { return false }
        return text.heightCm == measuredIn.heightCm && text.widthCm == measuredIn.widthCm
    }

    /// The measured size into empty fields (his numbers stay his).
    private func fill(from size: OwnDepth.Size) {
        guard text.heightCm == nil, text.widthCm == nil else { return }
        withAnimation(.easeOut(duration: 0.25)) {
            text.heightCm = size.heightCm
            text.widthCm = size.widthCm
            measuredIn = size
        }
    }

    /// The picture as it will be kept: in the shape of his size when he
    /// gave one near enough the photograph's, as the server cuts it.
    private func shape(of picture: UIImage) -> Double {
        let measured = aspect ?? Double(picture.size.width / max(picture.size.height, 1))
        return OwnWork.ratio(heightCm: text.heightCm, widthCm: text.widthCm, measured: measured) ?? measured
    }

    /// His size against the picture's shape: a size of another shape is
    /// most often height and width swapped, or the frame measured.
    private var sizeWarning: String? {
        guard let aspect, aspect > 0, let height = text.heightCm, let width = text.widthCm, height > 0 else { return nil }
        let given = width / height
        guard abs(given - aspect) / aspect > 0.12 else { return nil }
        if swapFits {
            return "Na zdjęciu dzieło jest \(aspect > 1 ? "poziome" : "pionowe"). Może wysokość i szerokość są zamienione?"
        }
        return OwnWork.ratio(heightCm: height, widthCm: width, measured: aspect) != nil
            ? "Proporcje różnią się od zdjęcia: dzieło dostanie proporcje z tego wymiaru. Mierzysz bez ramy?"
            : "Wymiar bardzo odbiega od zdjęcia, więc dzieło zostaje w proporcjach zdjęcia. Sprawdź liczby."
    }

    private var swapFits: Bool {
        guard let aspect, let height = text.heightCm, let width = text.widthCm, width > 0 else { return false }
        return abs(height / width - aspect) / aspect <= 0.12
    }

    static func number(_ text: String) -> Double? {
        let value = Double(text.replacingOccurrences(of: ",", with: ".").trimmingCharacters(in: .whitespaces))
        return value.flatMap { $0 > 0 ? $0 : nil }
    }
}

/// "Edytuj opis" on the card of a work of his own.
struct OwnDescriptionSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let item: Item
    let saved: (Item) -> Void
    @State private var text: OwnDescription
    @State private var saving = false

    init(item: Item, saved: @escaping (Item) -> Void) {
        self.item = item
        self.saved = saved
        _text = State(initialValue: OwnDescription(item))
    }

    private var places: [String] {
        var seen = Set<String>()
        return model.ownWorks.compactMap { $0.own?.hangs }.filter { !$0.isEmpty && seen.insert($0).inserted }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                OwnDescriptionForm(
                    text: $text, aspect: item.cornersAspect ?? item.width.flatMap { w in item.height.map { Double(w) / Double(max($0, 1)) } },
                    places: places
                )
                .pageWidth()
                .padding(.horizontal, Theme.gutter)
                .padding(.vertical, 16)
            }
            .scrollDismissesKeyboard(.interactively)
            .paperPage()
            .navigationTitle("Edytuj opis")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Anuluj") { dismiss() }
                        .disabled(saving)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button {
                        Task { await save() }
                    } label: {
                        if saving { ProgressView() } else { Text("Zapisz") }
                    }
                    .disabled(saving || text.trimmed == OwnDescription(item))
                }
            }
        }
    }

    private func save() async {
        saving = true
        defer { saving = false }
        do {
            let updated = try await model.backend.describeOwnWork(itemID: item.id, text.trimmed)
            model.ownWorkChanged(updated)
            saved(updated)
            dismiss()
        } catch {
            model.show(error)
        }
    }
}
