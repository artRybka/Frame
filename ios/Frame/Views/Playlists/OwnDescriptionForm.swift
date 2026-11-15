import SwiftUI

/// What the owner writes of a work of his own: title, author, date,
/// technique (chips or his own words), size, where it hangs, where it came
/// from, a note. What was read off the picture waits beside each field as
/// a dashed chip: a tap takes it, nothing is filled in by itself.
struct OwnDescriptionForm: View {
    @Binding var text: OwnDescription
    /// The work as cut, at the top.
    var picture: UIImage? = nil
    /// The picture's width / height, to check the size against.
    var aspect: Double? = nil
    var hints: OwnHints? = nil
    var readingHints = false
    /// Where his other works hang.
    var places: [String] = []
    @State private var technique: String?
    @State private var support: String?
    @State private var heightText = ""
    @State private var widthText = ""
    @State private var started = false

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            if let picture {
                Image(uiImage: picture)
                    .resizable()
                    .scaledToFit()
                    .frame(maxWidth: .infinity, maxHeight: 220)
                    .shadow(color: .black.opacity(0.18), radius: 12, y: 8)
                    .padding(.top, 4)
            }
            if readingHints || hints != nil {
                hintsBanner
            }
            field("Tytuł", text: $text.title, prompt: "np. Pejzaż z klifem") {
                hint(hints?.title, label: hints.map { "„\($0.title)”" }) { text.title = $0 }
            }
            field("Autor", text: $text.artist, prompt: "Imię i nazwisko") {
                hint(hints?.artist) { text.artist = $0 }
            }
            field("Data", text: $text.dateText, prompt: "np. 1965, ok. 1930, lata 70.") {
                hint(hints?.date) { text.dateText = $0 }
            }
            techniqueSection
            sizeSection
            VStack(alignment: .leading, spacing: 10) {
                Eyebrow("Więcej")
                field("Gdzie wisi", text: $text.hangs, prompt: "np. Salon") {
                    ForEach(places.filter { $0 != text.hangs }.prefix(4), id: \.self) { place in
                        chip(place, dashed: false) { text.hangs = place }
                    }
                }
                field("Skąd", text: $text.origin, prompt: "Kupione, prezent, po dziadku…") { EmptyView() }
                VStack(alignment: .leading, spacing: 6) {
                    label("Notatka")
                    TextField("Historia dzieła, co warto pamiętać", text: $text.description, axis: .vertical)
                        .lineLimit(3 ... 10)
                        .textFieldStyle(.plain)
                        .padding(12)
                        .background(Theme.card, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(Theme.hairline))
                }
            }
        }
        .onAppear(perform: start)
        .onChange(of: heightText) { _, value in text.heightCm = Self.number(value) }
        .onChange(of: widthText) { _, value in text.widthCm = Self.number(value) }
        .onChange(of: text.heightCm) { _, value in
            if Self.number(heightText) != value { heightText = value.map(OwnWork.number) ?? "" }
        }
        .onChange(of: text.widthCm) { _, value in
            if Self.number(widthText) != value { widthText = value.map(OwnWork.number) ?? "" }
        }
        .onChange(of: text.medium) { _, value in
            // Typed or filled: the chips as the line says.
            if let read = OwnTechnique.read(value) {
                technique = read.technique
                support = read.support
            } else {
                technique = nil
                support = nil
            }
        }
    }

    private func start() {
        guard !started else { return }
        started = true
        heightText = text.heightCm.map(OwnWork.number) ?? ""
        widthText = text.widthCm.map(OwnWork.number) ?? ""
        if let read = OwnTechnique.read(text.medium) {
            technique = read.technique
            support = read.support
        }
    }

    // MARK: Hints

    private var hintsBanner: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "sparkles")
                .foregroundStyle(Theme.vermilion)
            VStack(alignment: .leading, spacing: 3) {
                if readingHints && hints == nil {
                    Text("Czytam sygnaturę i technikę z obrazu…")
                        .font(.subheadline.weight(.medium))
                } else if let hints {
                    Text("Podpowiedzi z obrazu")
                        .font(.subheadline.weight(.medium))
                    if !hints.signature.isEmpty {
                        Text("Sygnatura: „\(hints.signature)”\(hints.sure ? "" : " (niepewna)")")
                            .font(.caption)
                            .foregroundStyle(Theme.inkSoft)
                    }
                    Text("Dotknij podpowiedzi przy polu, żeby ją wpisać.")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
            }
            .foregroundStyle(Theme.ink)
            Spacer(minLength: 0)
            if readingHints && hints == nil { ProgressView().controlSize(.small) }
        }
        .padding(12)
        .background(Theme.card, in: RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Theme.corner, style: .continuous).strokeBorder(Theme.hairline))
        .transition(.opacity)
    }

    /// A hint not taken yet, as a dashed chip.
    @ViewBuilder
    private func hint(_ value: String?, label: String? = nil, take: @escaping (String) -> Void) -> some View {
        if let value, !value.isEmpty {
            chip(label ?? value, dashed: true) { take(value) }
        }
    }

    private func chip(_ title: String, dashed: Bool, selected: Bool = false, action: @escaping () -> Void) -> some View {
        Button {
            withAnimation(.easeOut(duration: 0.2)) { action() }
        } label: {
            HStack(spacing: 5) {
                if dashed { Image(systemName: "sparkles").font(.caption2) }
                Text(title).lineLimit(1)
            }
            .font(.subheadline)
            .foregroundStyle(selected ? Theme.paper : Theme.ink)
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(selected ? Theme.ink : (dashed ? Color.clear : Theme.card), in: Capsule())
            .overlay {
                if dashed {
                    Capsule().strokeBorder(Theme.vermilion.opacity(0.7), style: StrokeStyle(lineWidth: 1, dash: [4, 3]))
                } else if !selected {
                    Capsule().strokeBorder(Theme.hairline)
                }
            }
        }
        .buttonStyle(.plain)
    }

    // MARK: Fields

    private func label(_ title: String) -> some View {
        Text(title)
            .font(.caption.weight(.semibold))
            .foregroundStyle(Theme.inkSoft)
            .textCase(.uppercase)
            .tracking(0.6)
    }

    private func field<Chips: View>(
        _ title: String, text value: Binding<String>, prompt: String, @ViewBuilder chips: () -> Chips
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            label(title)
            TextField(prompt, text: value)
                .textFieldStyle(.plain)
                .font(.body)
                .padding(12)
                .background(Theme.card, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(Theme.hairline))
            ChipFlow { chips() }
        }
    }

    private var techniqueSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            field("Technika", text: $text.medium, prompt: "np. olej na płótnie") {
                if let hints, !hints.technique.isEmpty, hints.technique != "unknown" {
                    let line = OwnTechnique.medium(technique: hints.technique, support: hints.support == "unknown" ? nil : hints.support)
                    if !line.isEmpty, line != text.medium {
                        hint(line) { text.medium = $0 }
                    }
                }
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    ForEach(OwnTechnique.techniques, id: \.key) { item in
                        chip(item.name, dashed: false, selected: technique == item.key) {
                            technique = technique == item.key ? nil : item.key
                            text.medium = OwnTechnique.medium(technique: technique, support: support)
                        }
                    }
                }
            }
            .scrollClipDisabled()
            HStack(spacing: 6) {
                ForEach(OwnTechnique.supports, id: \.key) { item in
                    chip(item.name, dashed: false, selected: support == item.key) {
                        support = support == item.key ? nil : item.key
                        text.medium = OwnTechnique.medium(technique: technique, support: support)
                    }
                }
            }
        }
    }

    private var sizeSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            label("Rozmiar (bez ramy)")
            HStack(spacing: 10) {
                sizeField("wys.", text: $heightText)
                Text("×").foregroundStyle(Theme.inkSoft)
                sizeField("szer.", text: $widthText)
                Text("cm").foregroundStyle(Theme.inkSoft)
            }
            if let warning = sizeWarning {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .foregroundStyle(Theme.warn)
                    Text(warning)
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
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
                .transition(.opacity)
            }
        }
        .animation(.easeOut(duration: 0.2), value: sizeWarning)
    }

    private func sizeField(_ prompt: String, text value: Binding<String>) -> some View {
        TextField(prompt, text: value)
            .keyboardType(.decimalPad)
            .multilineTextAlignment(.center)
            .textFieldStyle(.plain)
            .padding(.vertical, 12)
            .frame(width: 92)
            .background(Theme.card, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(Theme.hairline))
    }

    /// His size against the picture's shape: a size of another shape is
    /// most often height and width swapped, or the frame measured.
    private var sizeWarning: String? {
        guard let aspect, aspect > 0, let height = text.heightCm, let width = text.widthCm, height > 0 else { return nil }
        let given = width / height
        guard abs(given - aspect) / aspect > 0.12 else { return nil }
        return swapFits
            ? "Na zdjęciu dzieło jest \(aspect > 1 ? "poziome" : "pionowe"). Może wysokość i szerokość są zamienione?"
            : "Proporcje nie zgadzają się ze zdjęciem. Mierzysz bez ramy?"
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

/// Chips in rows, as many to a row as fit.
private struct ChipFlow<Content: View>: View {
    @ViewBuilder let content: () -> Content

    var body: some View {
        FlowLayout(spacing: 6) { content() }
    }
}

private struct FlowLayout: Layout {
    var spacing: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(subviews, width: proposal.width ?? .infinity)
        let height = rows.last.map { $0.y + $0.height } ?? 0
        let width = rows.map(\.width).max() ?? 0
        return CGSize(width: proposal.width ?? width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let rows = arrange(subviews, width: bounds.width)
        for row in rows {
            var x = bounds.minX
            for index in row.items {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(at: CGPoint(x: x, y: bounds.minY + row.y), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
        }
    }

    private struct Row {
        var items: [Int] = []
        var y: CGFloat = 0
        var width: CGFloat = 0
        var height: CGFloat = 0
    }

    private func arrange(_ subviews: Subviews, width: CGFloat) -> [Row] {
        var rows: [Row] = []
        var row = Row()
        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            if !row.items.isEmpty, row.width + spacing + size.width > width {
                rows.append(row)
                row = Row(y: row.y + row.height + spacing)
            }
            row.width += (row.items.isEmpty ? 0 : spacing) + size.width
            row.height = max(row.height, size.height)
            row.items.append(index)
        }
        if !row.items.isEmpty { rows.append(row) }
        return rows
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
                    text: $text, aspect: item.cutAspect ?? item.width.flatMap { w in item.height.map { Double(w) / Double(max($0, 1)) } },
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
