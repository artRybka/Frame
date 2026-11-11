import SwiftUI

/// Zadania nocne → Powtórki i jakość → „Co zmieniła noc" (Mateusz
/// 2026-11-11: "potrzebne są jakieś podsumowania wykonanych prac,
/// szczególnie przy usuniętych duplikatach, przynajmniej tych, gdzie były
/// wątpliwości"): the pictures the night made a copy, a detail or a
/// photograph on a wall of another work. First what the judge settled (the
/// pictures alone could not), each with what the judge and its critic said,
/// then, folded, what the pictures settled. „To nie to samo" takes a change
/// back and keeps the two apart for good.
struct TidyChangesView: View {
    @Environment(AppModel.self) private var model
    @State private var changes: TidyChanges?
    @State private var failed = false
    @State private var showSure = false
    /// Pairs whose answer the server is still taking.
    @State private var busy: Set<String> = []
    @State private var confirming: TidyChanges.Change?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                header
                if let changes {
                    if changes.isEmpty {
                        EmptyStateView(
                            title: "Nic nie zmieniono",
                            message: "Noc nie połączyła jeszcze żadnych kopii ani detali.",
                            systemImage: "checkmark.seal"
                        )
                    }
                    if !changes.doubtful.isEmpty {
                        section(
                            "Z wątpliwościami",
                            note: "Obraz nie rozstrzygał, więc decydował sędzia, a krytyk potwierdził. Warto przejrzeć.",
                            entries: changes.doubtful
                        )
                    }
                    if !changes.sure.isEmpty {
                        sureSection(changes.sure)
                    }
                } else if failed {
                    EmptyStateView(
                        title: "Nie udało się wczytać",
                        message: "Serwer nie odpowiedział. Starszy serwer nie zapisuje zmian.",
                        systemImage: "wifi.exclamationmark"
                    )
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 40)
                }
            }
            .pageWidth()
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 40)
        }
        .paperPage()
        .navigationTitle("Co zmieniła noc")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task { await load() }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            Eyebrow("Powtórki i jakość", color: Theme.vermilion)
            Text("Co zmieniła noc")
                .font(.serif(32, weight: .semibold))
                .foregroundStyle(Theme.ink)
            Text("Nic nie jest usuwane. Kopia zostaje w bibliotece, a pokazuje się najlepsza z nich. Detal i zdjęcie na ścianie nie pojawiają się w listach obok dzieła. „To nie to samo” rozdziela parę na stałe.")
                .font(.serif(17))
                .foregroundStyle(Theme.inkSoft)
        }
    }

    private func section(_ title: String, note: String, entries: [TidyChanges.Change]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: title, subtitle: note)
            Card {
                ForEach(Array(entries.enumerated()), id: \.element.id) { index, change in
                    if index > 0 { Divider() }
                    row(change)
                }
            }
        }
    }

    private func sureSection(_ entries: [TidyChanges.Change]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "Pewne", subtitle: "Rozstrzygnął sam obraz: ten sam odcisk albo dopasowanie w całości.")
            Card {
                Button {
                    withAnimation(.snappy) { showSure.toggle() }
                } label: {
                    HStack {
                        Text(showSure ? "Schowaj" : "Pokaż (\(entries.count))")
                            .font(.subheadline)
                        Spacer()
                        Image(systemName: "chevron.down")
                            .font(.footnote.weight(.semibold))
                            .rotationEffect(.degrees(showSure ? 180 : 0))
                    }
                    .foregroundStyle(Theme.inkSoft)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                if showSure {
                    ForEach(entries) { change in
                        Divider()
                        row(change)
                    }
                }
            }
        }
    }

    private func row(_ change: TidyChanges.Change) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 10) {
                picture(change.a, caption: change.relation == "copy" ? "Kopia" : change.relation == "detail" ? "Detal" : "Zdjęcie")
                Image(systemName: "arrow.right")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(Theme.inkSoft)
                    .padding(.top, 30)
                picture(change.b, caption: "Dzieło")
            }
            Text(change.relationName)
                .font(.caption.weight(.semibold))
                .foregroundStyle(change.by == "judge" ? Theme.vermilion : Theme.ink)
            Text(titleLine(change.b))
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
                .lineLimit(2)
            if !change.why.isEmpty {
                Text("\(Text("Sędzia:").fontWeight(.semibold)) \(change.why)")
                    .font(.caption)
                    .foregroundStyle(Theme.ink)
            }
            if !change.critic.isEmpty {
                Text("\(Text("Krytyk:").fontWeight(.semibold)) \(change.critic)")
                    .font(.caption)
                    .foregroundStyle(Theme.ink)
            }
            HStack(spacing: 12) {
                Text(byText(change))
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                Spacer()
                if busy.contains(change.id) { ProgressView().controlSize(.small) }
                Button("To nie to samo") { confirming = change }
                    .font(.subheadline.weight(.semibold))
                    .buttonStyle(.borderless)
                    .tint(Theme.ink)
                    .disabled(busy.contains(change.id))
                    .confirmationDialog(
                        "Rozdzielić te dwa obrazy?",
                        isPresented: Binding(
                            get: { confirming?.id == change.id },
                            set: { if !$0 { confirming = nil } }
                        ),
                        titleVisibility: .visible
                    ) {
                        Button("Rozdziel na stałe") { separate(change) }
                        Button("Anuluj", role: .cancel) {}
                    } message: {
                        Text("Oba wrócą jako osobne dzieła i noc nie połączy ich ponownie.")
                    }
            }
        }
        .padding(.vertical, 4)
    }

    private func picture(_ item: ItemSummary, caption: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ArtImage(ref: .thumb(item.id), placeholder: item.placeholderColor, maxPixel: 360)
                .frame(maxWidth: .infinity)
                .frame(height: 110)
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            Text(caption)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(Theme.inkSoft)
            Text(Names.source(item.source))
                .font(.caption2)
                .foregroundStyle(Theme.inkSoft)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func titleLine(_ item: ItemSummary) -> String {
        let title = item.title.isEmpty ? "Bez tytułu" : item.title
        return item.artist.isEmpty ? title : "\(title) · \(Names.artist(item.artist))"
    }

    private func byText(_ change: TidyChanges.Change) -> String {
        let how = switch change.by {
        case "judge": "sędzia i krytyk"
        case "hash": "odcisk obrazu"
        default: "dopasowanie obrazów"
        }
        let when = When.past(change.at) ?? ""
        return [when, how].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    private func load() async {
        do {
            changes = try await model.backend.tidyChanges()
            failed = false
        } catch {
            if changes == nil { failed = true }
        }
    }

    private func separate(_ change: TidyChanges.Change) {
        busy.insert(change.id)
        Task {
            defer { busy.remove(change.id) }
            do {
                let updated = try await model.backend.keepApart(TidyApart(a: change.a.id, b: change.b.id))
                withAnimation(.snappy) { changes = updated }
                model.notices.done("Rozdzielone")
            } catch {
                model.notices.warn("Nie udało się", error.localizedDescription)
            }
        }
    }
}
