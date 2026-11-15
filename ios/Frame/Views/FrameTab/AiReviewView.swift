import SwiftUI

/// Konfiguracja → Model językowy → „Do sprawdzenia": what the catalogue's
/// gatekeeper set aside at night (a stamp, a page of text, a photograph of
/// a gallery's wall…), each with „Przywróć", and what the night audit found
/// that does not add up in a work's title, date, Polish text or picture.
/// Both were confirmed by a second model before they came here.
struct AiReviewView: View {
    @Environment(AppModel.self) private var model
    @State private var review: AiReview?
    @State private var failed = false
    /// Works whose answer the server is still taking.
    @State private var busy: Set<String> = []
    /// The picture open on the whole screen (tap on a thumbnail; Mateusz
    /// 2026-11-15 „Z miniatury nic nie widzę").
    @State private var opened: Item?
    /// The thumbnail whose work is being fetched for the viewer.
    @State private var opening: String?
    /// The work's card, opened from its title.
    @State private var card: String?
    @Namespace private var zoomSpace
    @MainActor private static var openedOnce = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                header
                if let review {
                    if review.isEmpty {
                        EmptyStateView(
                            title: "Nic do sprawdzenia",
                            message: "Strażnik katalogu i nocny przegląd nie znalazły nic nowego.",
                            systemImage: "checkmark.seal"
                        )
                    }
                    if !review.setAside.isEmpty {
                        section(
                            "Odłożone przez strażnika",
                            note: "Nie pokazują się w katalogu ani w Szukaj. „Przywróć” wraca dzieło na stałe.",
                            entries: review.setAside
                        )
                    }
                    if !review.findings.isEmpty {
                        section(
                            "Znalezione w nocnym przeglądzie",
                            note: "Nic nie zostało zmienione. Wystarczy przejrzeć i odhaczyć.",
                            entries: review.findings
                        )
                    }
                } else if failed {
                    EmptyStateView(
                        title: "Nie udało się wczytać",
                        message: "Serwer nie odpowiedział. Spróbuj za chwilę.",
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
        .navigationTitle("Do sprawdzenia")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task { await load() }
        .fullScreenCover(item: $opened) { item in
            OriginalViewer(item: item)
                .navigationTransition(.zoom(sourceID: item.id, in: zoomSpace))
        }
        .navigationDestination(item: $card) { id in
            ItemDetailView(itemID: id)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            Eyebrow("Claude w nocy", color: Theme.vermilion)
            Text("Do sprawdzenia")
                .font(.serif(32, weight: .semibold))
                .foregroundStyle(Theme.ink)
            Text("Haiku przegląda w nocy obrazy z Commons, Europeany, Openverse i WikiArt oraz 30 losowych dzieł katalogu. Każdą decyzję potwierdza drugi model.")
                .font(.serif(17))
                .foregroundStyle(Theme.inkSoft)
        }
    }

    private func section(_ title: String, note: String, entries: [AiReview.Entry]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: title, subtitle: note)
            Card {
                ForEach(Array(entries.enumerated()), id: \.element.id) { index, entry in
                    if index > 0 { Divider() }
                    row(entry)
                }
            }
        }
    }

    private func row(_ entry: AiReview.Entry) -> some View {
        HStack(alignment: .top, spacing: 12) {
            thumbnail(entry)
            VStack(alignment: .leading, spacing: 4) {
                Button { card = entry.item.id } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("\(Text(entry.item.title.isEmpty ? "Bez tytułu" : entry.item.title)) \(Text(Image(systemName: "chevron.right")).font(.caption.weight(.semibold)).foregroundStyle(Theme.inkSoft))")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(Theme.ink)
                            .lineLimit(2)
                            .multilineTextAlignment(.leading)
                        if !entry.item.artist.isEmpty {
                            Text(Names.artist(entry.item.artist))
                                .font(.caption)
                                .foregroundStyle(Theme.inkSoft)
                                .lineLimit(1)
                        }
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityHint(Text("Otwiera kartę dzieła"))
                if !entry.seenAsName.isEmpty {
                    Text(entry.seenAsName)
                        .font(.caption.weight(.medium))
                        .foregroundStyle(Theme.vermilion)
                }
                if !entry.why.isEmpty {
                    Text(entry.why)
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
                ForEach(entry.problems, id: \.self) { problem in
                    Text("\(Text(problem.name + ":").fontWeight(.semibold)) \(problem.problem)")
                        .font(.caption)
                        .foregroundStyle(Theme.ink)
                }
                HStack(spacing: 16) {
                    if entry.by == "gatekeeper" {
                        Button("Przywróć") { act(entry) { try await model.backend.bringBack(itemID: entry.item.id) } }
                        Button("Zgadza się") { act(entry) { try await model.backend.dismissReview(itemID: entry.item.id) } }
                    } else {
                        Button("Sprawdzone") { act(entry) { try await model.backend.dismissReview(itemID: entry.item.id) } }
                    }
                    if busy.contains(entry.id) { ProgressView().controlSize(.small) }
                }
                .font(.subheadline.weight(.semibold))
                .buttonStyle(.borderless)
                .tint(Theme.ink)
                .disabled(busy.contains(entry.id))
                .padding(.top, 2)
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 4)
    }

    /// The picture, bigger than before and with a magnifier: a tap opens it
    /// on the whole screen, to zoom into (a ruler, a colour chart, a cut
    /// edge are seen there, not on a thumbnail).
    private func thumbnail(_ entry: AiReview.Entry) -> some View {
        Button { open(entry.item.id) } label: {
            ArtImage(ref: .thumb(entry.item.id), placeholder: entry.item.placeholderColor, maxPixel: 360)
                .frame(width: 88, height: 88)
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                .overlay(alignment: .bottomTrailing) {
                    Group {
                        if opening == entry.item.id {
                            ProgressView().controlSize(.mini).tint(.white)
                        } else {
                            Image(systemName: "arrow.up.left.and.arrow.down.right")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundStyle(.white)
                        }
                    }
                    .frame(width: 22, height: 22)
                    .background(.black.opacity(0.45), in: Circle())
                    .padding(4)
                }
                .matchedTransitionSource(id: entry.item.id, in: zoomSpace) {
                    $0.clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(Text(entry.item.title.isEmpty ? "Obraz" : entry.item.title))
        .accessibilityHint(Text("Otwiera obraz na całym ekranie"))
    }

    private func open(_ id: String) {
        guard opening == nil else { return }
        opening = id
        Task {
            defer { opening = nil }
            do {
                opened = try await model.backend.item(id: id)
            } catch {
                model.notices.warn("Nie udało się otworzyć obrazu", error.localizedDescription)
            }
        }
    }

    private func load() async {
        do {
            review = try await model.backend.aiReview()
            failed = false
            // Screenshots: `-reviewOpen YES` opens the first picture by itself.
            if UserDefaults.standard.bool(forKey: "reviewOpen"), !Self.openedOnce,
               let first = (review?.findings.first ?? review?.setAside.first) {
                Self.openedOnce = true
                open(first.item.id)
            }
        } catch {
            if review == nil { failed = true }
        }
    }

    private func act(_ entry: AiReview.Entry, _ call: @escaping () async throws -> AiReview) {
        busy.insert(entry.id)
        Task {
            defer { busy.remove(entry.id) }
            do {
                let updated = try await call()
                withAnimation(.snappy) { review = updated }
                await model.loadAiSettings()
            } catch {
                model.notices.warn("Nie udało się", error.localizedDescription)
            }
        }
    }
}
