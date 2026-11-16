import SwiftUI

/// Sketches of the description step in the app's own look (Mateusz
/// 2026-11-16: "Zaproponuj inny wygląd kroku 3… Szczególnie niepasują
/// wizualnie podpowiadane treści"), shown with `-descLook a|b|c` instead of
/// `OwnDescriptionForm`; the one he picks takes its place.
///
/// - A, "jak karta dzieła": the title and author in the card's serif, no
///   boxes (as a playlist's name), the rest as the card's facts; a hint is
///   a grey tag under its field, as the card's tags.
/// - B, "jak Konfiguracja": cards of rows, each a label over a plain field;
///   a hint is one grey line under its field with "Wpisz".
/// - C, "uzupełnione z obrazu": A's look, what was read written into the
///   fields at once with a small mark, and one line to take it all back.
struct OwnDescriptionLook: View {
    enum Look: String { case a, b, c }

    let look: Look
    @Binding var text: OwnDescription
    var picture: UIImage?
    var aspect: Double?
    var hints: OwnHints?
    var readingHints = false
    var places: [String] = []

    @State private var heightText = ""
    @State private var widthText = ""
    /// (C) What was written into the fields from the picture: marked
    /// while the field still says it.
    @State private var filled: [String: String] = [:]
    @State private var started = false

    var body: some View {
        VStack(alignment: .leading, spacing: look == .b ? 22 : 26) {
            if let picture {
                Image(uiImage: picture)
                    .resizable()
                    .aspectRatio(shape(of: picture), contentMode: .fit)
                    .frame(maxWidth: .infinity, maxHeight: look == .b ? 200 : 260)
                    .shadow(color: .black.opacity(0.18), radius: 12, y: 8)
                    .padding(.top, 8)
            }
            if readingHints && hints == nil {
                Label("Czytam sygnaturę i technikę z obrazu…", systemImage: "sparkles")
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
                    .transition(.opacity)
            }
            switch look {
            case .a, .c: editorial
            case .b: cards
            }
        }
        .onAppear(perform: start)
        .onChange(of: hints) { _, hints in
            if look == .c, let hints { fill(from: hints) }
        }
        .onChange(of: heightText) { _, value in text.heightCm = OwnDescriptionForm.number(value) }
        .onChange(of: widthText) { _, value in text.widthCm = OwnDescriptionForm.number(value) }
        .onChange(of: text.heightCm) { _, value in
            if OwnDescriptionForm.number(heightText) != value { heightText = value.map(OwnWork.number) ?? "" }
        }
        .onChange(of: text.widthCm) { _, value in
            if OwnDescriptionForm.number(widthText) != value { widthText = value.map(OwnWork.number) ?? "" }
        }
        .animation(.easeOut(duration: 0.25), value: hints)
    }

    private func start() {
        guard !started else { return }
        started = true
        heightText = text.heightCm.map(OwnWork.number) ?? ""
        widthText = text.widthCm.map(OwnWork.number) ?? ""
        if look == .c, let hints { fill(from: hints) }
    }

    // MARK: A and C: as the work's card

    private var editorial: some View {
        VStack(alignment: .leading, spacing: 26) {
            if look == .c, !marked.isEmpty {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Image(systemName: "sparkles").foregroundStyle(Theme.inkSoft)
                    Text("Uzupełnione z obrazu. Popraw, jeśli trzeba.")
                        .foregroundStyle(Theme.inkSoft)
                    Spacer(minLength: 8)
                    Button("Wyczyść") { clearFilled() }
                        .font(.footnote.weight(.semibold))
                }
                .font(.footnote)
                .transition(.opacity)
            }
            VStack(alignment: .leading, spacing: 10) {
                serifField("Tytuł", text: $text.title, key: "title", size: 26, weight: .semibold, ink: Theme.ink)
                tagHint(hints?.title, taken: text.title, quoted: true) { text.title = $0 }
                serifField("Autor", text: $text.artist, key: "artist", size: 18, ink: Theme.ink)
                tagHint(hints?.artist, taken: text.artist) { text.artist = $0 }
                serifField("Data", text: $text.dateText, key: "date", size: 18, ink: Theme.inkSoft)
                tagHint(hints?.date, taken: text.dateText) { text.dateText = $0 }
            }
            Card {
                factRow("Technika") {
                    HStack(spacing: 6) {
                        trailingField("np. olej na płótnie", text: $text.medium, key: "medium")
                        techniqueMenu
                    }
                }
                if let line = techniqueHint, look == .a {
                    HStack { Spacer(); tagHint(line, taken: text.medium) { text.medium = $0 } }
                }
                Divider()
                factRow("Rozmiar") { sizeFields }
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
    }

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

    /// A hint as one of the card's tags; a tap writes it in.
    @ViewBuilder
    private func tagHint(_ value: String?, taken: String, quoted: Bool = false, take: @escaping (String) -> Void) -> some View {
        if look == .a, let value, !value.isEmpty, value != taken.trimmingCharacters(in: .whitespaces) {
            Button {
                withAnimation(.easeOut(duration: 0.2)) { take(value) }
            } label: {
                TagLabel(text: quoted ? "„\(value)”" : value, systemImage: "sparkles")
            }
            .buttonStyle(.plain)
            .accessibilityHint("Wpisuje odczytane z obrazu")
            .transition(.opacity)
        }
    }

    @ViewBuilder
    private func filledMark(_ key: String) -> some View {
        if look == .c, marked.contains(key) {
            Image(systemName: "sparkles")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
                .accessibilityLabel("odczytane z obrazu")
        }
    }

    private func factRow<Value: View>(_ title: String, @ViewBuilder value: () -> Value) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).foregroundStyle(Theme.inkSoft)
            Spacer(minLength: 16)
            value()
        }
        .font(.subheadline)
    }

    private func trailingField(_ prompt: String, text value: Binding<String>, key: String) -> some View {
        HStack(spacing: 4) {
            filledMark(key)
            TextField(prompt, text: value)
                .multilineTextAlignment(.trailing)
                .foregroundStyle(Theme.ink)
        }
    }

    private var sizeFields: some View {
        HStack(spacing: 6) {
            sizeField("wys.", text: $heightText)
            Text("×").foregroundStyle(Theme.inkSoft)
            sizeField("szer.", text: $widthText)
            Text("cm").foregroundStyle(Theme.inkSoft)
        }
    }

    private func sizeField(_ prompt: String, text value: Binding<String>) -> some View {
        TextField(prompt, text: value)
            .keyboardType(.decimalPad)
            .multilineTextAlignment(.trailing)
            .foregroundStyle(Theme.ink)
            .frame(width: 48)
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

    private var techniqueHint: String? {
        guard let hints, !hints.technique.isEmpty, hints.technique != "unknown" else { return nil }
        let line = OwnTechnique.medium(technique: hints.technique, support: hints.support == "unknown" ? nil : hints.support)
        return line.isEmpty ? nil : line
    }

    private func setTechnique(_ key: String) {
        let support = OwnTechnique.read(text.medium)?.support
        text.medium = OwnTechnique.medium(technique: key, support: support)
    }

    private func setSupport(_ key: String) {
        let technique = OwnTechnique.read(text.medium)?.technique
        text.medium = OwnTechnique.medium(technique: technique, support: key)
    }

    // MARK: C: filled in at once

    private static let fields: [(key: String, path: WritableKeyPath<OwnDescription, String>)] = [
        ("title", \.title), ("artist", \.artist), ("date", \.dateText), ("medium", \.medium),
    ]

    /// The fields that still say what was read off the picture.
    private var marked: Set<String> {
        Set(Self.fields.filter { field in filled[field.key].map { $0 == text[keyPath: field.path] } ?? false }.map(\.key))
    }

    private func fill(from hints: OwnHints) {
        let read = ["title": hints.title, "artist": hints.artist, "date": hints.date, "medium": techniqueHint ?? ""]
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

    // MARK: B: as Konfiguracja

    private var cards: some View {
        VStack(alignment: .leading, spacing: 22) {
            section("Dzieło") {
                row("Tytuł", text: $text.title, prompt: "np. Pejzaż z klifem", hint: hints?.title)
                Divider()
                row("Autor", text: $text.artist, prompt: "Imię i nazwisko", hint: hints?.artist)
                Divider()
                row("Data", text: $text.dateText, prompt: "np. 1965, ok. 1930", hint: hints?.date)
            }
            section("Wykonanie") {
                VStack(alignment: .leading, spacing: 6) {
                    rowLabel("Technika")
                    HStack {
                        TextField("np. olej na płótnie", text: $text.medium)
                        techniqueMenu
                    }
                    lineHint(techniqueHint, taken: text.medium) { text.medium = $0 }
                }
                Divider()
                VStack(alignment: .leading, spacing: 6) {
                    rowLabel("Rozmiar bez ramy")
                    HStack(spacing: 6) {
                        sizeField("wys.", text: $heightText).multilineTextAlignment(.leading)
                        Text("×").foregroundStyle(Theme.inkSoft)
                        sizeField("szer.", text: $widthText).multilineTextAlignment(.leading)
                        Text("cm").foregroundStyle(Theme.inkSoft)
                        Spacer()
                    }
                }
            }
            section("U Ciebie") {
                VStack(alignment: .leading, spacing: 6) {
                    rowLabel("Gdzie wisi")
                    HStack {
                        TextField("np. Salon", text: $text.hangs)
                        if !places.isEmpty { placesMenu }
                    }
                }
                Divider()
                row("Skąd", text: $text.origin, prompt: "Kupione, prezent, po dziadku…", hint: nil)
                Divider()
                VStack(alignment: .leading, spacing: 6) {
                    rowLabel("Notatka")
                    TextField("Historia dzieła, co warto pamiętać", text: $text.description, axis: .vertical)
                        .lineLimit(2 ... 10)
                }
            }
        }
    }

    private func section<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Eyebrow(title)
            Card(padding: 16) { content() }
        }
    }

    private func rowLabel(_ title: String) -> some View {
        Text(title).font(.footnote).foregroundStyle(Theme.inkSoft)
    }

    private func row(_ title: String, text value: Binding<String>, prompt: String, hint: String?) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            rowLabel(title)
            TextField(prompt, text: value).foregroundStyle(Theme.ink)
            lineHint(hint, taken: value.wrappedValue) { value.wrappedValue = $0 }
        }
    }

    /// A hint as Konfiguracja's notes are: one grey line, "Wpisz" at its end.
    @ViewBuilder
    private func lineHint(_ value: String?, taken: String, take: @escaping (String) -> Void) -> some View {
        if let value, !value.isEmpty, value != taken.trimmingCharacters(in: .whitespaces) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Image(systemName: "sparkles")
                Text("Z obrazu: \(value)").lineLimit(1)
                Spacer(minLength: 8)
                Button("Wpisz") { withAnimation(.easeOut(duration: 0.2)) { take(value) } }
                    .font(.caption.weight(.semibold))
            }
            .font(.caption)
            .foregroundStyle(Theme.inkSoft)
            .transition(.opacity)
        }
    }

    // MARK: The picture

    private func shape(of picture: UIImage) -> Double {
        let measured = aspect ?? Double(picture.size.width / max(picture.size.height, 1))
        return OwnWork.ratio(heightCm: text.heightCm, widthCm: text.widthCm, measured: measured) ?? measured
    }
}
