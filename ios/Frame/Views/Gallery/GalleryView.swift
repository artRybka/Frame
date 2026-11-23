import SwiftUI

/// "Galeria", the first tab (Mateusz 2026-11-23): works one after another on
/// the whole screen, cut to fill it. A swipe up brings the next, down the one
/// before; the order is the person's own (`GET /api/gallery`: their hearts,
/// works like them, new ones). A tap shows the work's caption on it, a glass
/// heart in the top corner and the tab bar (folding to one button as the
/// works move on); another tap takes them away. The caption opens the
/// work's card; a double tap gives a heart; a hold opens the work's menu.
struct GalleryView: View {
    @Environment(AppModel.self) private var model
    @State private var works: [RemoteItem] = []
    @State private var position: String?
    @State private var chrome = LaunchRoute.screen == "gallery-caption"
    @State private var loading = false
    @State private var failed = false
    @State private var path: [String] = []
    /// The heart that blooms where a double tap gave one.
    @State private var bloom: String?

    /// Works asked for at once, and how near the end the next are asked for.
    private static let batch = 12
    private static let ahead = 4

    private var shown: RemoteItem? {
        works.first { $0.id == position } ?? works.first
    }

    var body: some View {
        NavigationStack(path: $path) {
            pages
                .background(Color.black)
                .overlay(alignment: .bottom) {
                    if chrome, let shown {
                        GalleryCaption(work: shown) { open(shown) }
                            .transition(.opacity)
                    }
                }
                .overlay(alignment: .topTrailing) {
                    if chrome, let shown { heartButton(shown).transition(.opacity) }
                }
                .overlay {
                    if works.isEmpty { emptyState }
                }
                .animation(.easeInOut(duration: 0.2), value: chrome)
                .toolbarVisibility(.hidden, for: .navigationBar)
                .toolbarVisibility(chrome ? .visible : .hidden, for: .tabBar)
                .statusBarHidden(!chrome)
                .navigationDestination(for: String.self) { id in
                    ItemDetailView(itemID: id)
                }
        }
        .task { if works.isEmpty { await more() } }
        .onChange(of: position) { _, id in
            guard let id, let index = works.firstIndex(where: { $0.id == id }) else { return }
            if index >= works.count - Self.ahead { Task { await more() } }
        }
        // Hearts given here change what comes next: a fresh batch is asked
        // for when the library changes, after the works not seen yet.
    }

    private var pages: some View {
        ScrollView(.vertical) {
            LazyVStack(spacing: 0) {
                ForEach(works) { work in
                    GalleryPage(work: work, bloom: bloom == work.id)
                        .containerRelativeFrame([.horizontal, .vertical])
                        .contentShape(Rectangle())
                        .onTapGesture(count: 2) { heart(work) }
                        .onTapGesture { chrome.toggle() }
                        .contextMenu { menu(work) } preview: {
                            ArtImage(ref: .thumb(work.id), contentMode: .fit)
                                .frame(width: 280)
                        }
                        .id(work.id)
                }
            }
            .scrollTargetLayout()
        }
        .scrollTargetBehavior(.paging)
        .scrollPosition(id: $position)
        .scrollIndicators(.hidden)
        .ignoresSafeArea()
    }

    private var emptyState: some View {
        VStack(spacing: 14) {
            if failed {
                Text(bound: "Nie udało się wczytać dzieł.")
                    .foregroundStyle(.white.opacity(0.8))
                Button("Spróbuj ponownie", systemImage: "arrow.clockwise") {
                    Task { await more() }
                }
                .buttonStyle(.glass)
            } else {
                ProgressView().tint(.white)
            }
        }
    }

    private func heartButton(_ work: RemoteItem) -> some View {
        let on = model.liked(work.summary)
        return Button {
            Task { await model.like(work.summary, !on) }
        } label: {
            Image(systemName: on ? "heart.fill" : "heart")
                .font(.title3.weight(.medium))
                .foregroundStyle(on ? Theme.heart : .white)
                .frame(width: 30, height: 30)
                .contentTransition(.symbolEffect(.replace))
        }
        .buttonStyle(.glass)
        .buttonBorderShape(.circle)
        .environment(\.colorScheme, .dark)
        .accessibilityLabel(on ? "Usuń z ulubionych" : "Dodaj do ulubionych")
        .padding(.trailing, Theme.gutter)
        .padding(.top, 4)
    }

    @ViewBuilder
    private func menu(_ work: RemoteItem) -> some View {
        Button("Otwórz kartę dzieła", systemImage: "info.circle") { open(work) }
        let on = model.liked(work.summary)
        Button(on ? "Usuń z ulubionych" : "Dodaj do ulubionych", systemImage: on ? "heart.slash" : "heart") {
            Task { await model.like(work.summary, !on) }
        }
        if !model.isGuest {  // a guest sends nothing to the frame
            Button("Pokaż na ramce", systemImage: "photo") {
                Task { _ = await model.show(itemID: work.id, hold: .untilNextChange) }
            }
            Button("Dodaj do kolejki", systemImage: "text.line.first.and.arrowtriangle.forward") {
                Task { await model.queueNext(itemID: work.id) }
            }
        }
    }

    private func heart(_ work: RemoteItem) {
        let summary = work.summary
        if !model.liked(summary) { Task { await model.like(summary, true) } }
        bloom = work.id
        Task {
            try? await Task.sleep(for: .milliseconds(900))
            if bloom == work.id { bloom = nil }
        }
    }

    private func open(_ work: RemoteItem) {
        ItemPeeks.remember(work.summary, thumb: .thumb(work.id))
        chrome = true  // the tab bar under the card, as elsewhere
        path.append(work.id)
    }

    private func more() async {
        guard !loading else { return }
        loading = true
        defer { loading = false }
        do {
            let next = try await model.backend.gallery(count: Self.batch)
            failed = false
            let have = Set(works.map(\.id))
            works += next.filter { !have.contains($0.id) }
            if position == nil { position = works.first?.id }
        } catch {
            failed = works.isEmpty
        }
    }
}

/// One work on the whole screen, cut to fill it around what draws the eye;
/// its thumbnail first, the full picture over it as it comes.
private struct GalleryPage: View {
    let work: RemoteItem
    var bloom = false

    var body: some View {
        ZStack {
            ArtImage(ref: .thumb(work.id), placeholder: Color.black, contentMode: .fill, subjectFocus: true)
            ArtImage(
                ref: .image(work.id), placeholder: .clear, maxPixel: 2800, contentMode: .fill,
                priority: .high, subjectFocus: true
            )
            if bloom {
                Image(systemName: "heart.fill")
                    .font(.system(size: 96))
                    .foregroundStyle(.white.opacity(0.92))
                    .shadow(color: .black.opacity(0.35), radius: 12)
                    .transition(.scale(scale: 0.4).combined(with: .opacity))
            }
        }
        .animation(.spring(duration: 0.35), value: bloom)
        .clipped()
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(work.item.displayTitle)
    }
}

/// The work's caption laid on its lower part (Mateusz 2026-11-23, variant 2:
/// no card, the text on a shade): the museum, the title with its year, the
/// artist and their nationality and years, as on the work's card. Tapped:
/// the card. The Polish texts are asked for only once the caption is shown.
private struct GalleryCaption: View {
    @Environment(AppModel.self) private var model
    let work: RemoteItem
    let open: () -> Void
    @State private var polish: PolishText?

    private var item: Item { work.item }

    var body: some View {
        Button(action: open) {
            HStack(alignment: .center, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    let held = item.kind == .artwork ? item.heldBy ?? Names.source(item.source) : Names.source(item.source)
                    if !held.isEmpty { Eyebrow(held, color: Theme.vermilion) }
                    TitleWithYear(
                        title: title,
                        date: nonEmpty(polish?.date) ?? item.dateText,
                        font: .serif(26, weight: .semibold)
                    )
                    .fixedSize(horizontal: false, vertical: true)
                    .lineLimit(3)
                    VStack(alignment: .leading, spacing: 0) {
                        if !item.artist.isEmpty {
                            Text(bound: Names.artist(item.artist))
                                .font(.serif(19))
                                .foregroundStyle(Theme.ink)
                                .lineLimit(1)
                        }
                        let bio = nonEmpty(polish?.artistNote) ?? item.artistBio
                        if !bio.isEmpty {
                            Text(bound: bio).font(.subheadline).foregroundStyle(Theme.inkSoft).lineLimit(1)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right")
                    .font(.body.weight(.semibold))
                    .foregroundStyle(Theme.inkSoft)
            }
            .padding(.horizontal, Theme.gutter + 2)
            .padding(.top, 70)
            .padding(.bottom, 12)
            .background(alignment: .bottom) {
                LinearGradient(
                    stops: [
                        .init(color: .black.opacity(0), location: 0),
                        .init(color: .black.opacity(0.55), location: 0.45),
                        .init(color: .black.opacity(0.8), location: 1),
                    ],
                    startPoint: .top, endPoint: .bottom
                )
                .padding(.bottom, -140)  // under the tab bar too
                .allowsHitTesting(false)
            }
        }
        .buttonStyle(.plain)
        // Light text on the shade in both modes.
        .environment(\.colorScheme, .dark)
        .task(id: work.id) { await loadPolish() }
    }

    private var title: String {
        nonEmpty(polish?.title) ?? nonEmpty(work.titlePl)
            ?? (item.displayTitle.isEmpty ? "Bez tytułu" : item.displayTitle)
    }

    private func nonEmpty(_ text: String?) -> String? {
        guard let text, !text.isEmpty else { return nil }
        return text
    }

    private func loadPolish() async {
        polish = ItemPeeks.polish[work.id]
        guard polish == nil, item.kind == .artwork,
              let view = try? await model.backend.polish(itemID: work.id, wait: 0, early: true),
              let text = view.text
        else { return }
        ItemPeeks.keep(text, for: work.id)
        withAnimation(.easeInOut(duration: 0.4)) { polish = text }
    }
}
