import CoreLocation
import SwiftUI

/// Home: the picture on the frame, presented like an exhibit. The arrows
/// browse what was and what will be on the frame without sending anything;
/// the picture is cropped right on it, and "Pokaż na ramce" sends the one
/// browsed to with its crop.
struct NowView: View {
    @Environment(AppModel.self) private var model
    @State private var showingSend = LaunchRoute.screen == "send"
    @State private var path = NavigationPath()
    /// The picture browsed to; nil is the one on the frame.
    @State private var browsed: Browsed?
    @State private var details: [String: Item] = [:]
    @State private var draft = FramingDraft()
    /// Unsent crops of pictures browsed away from, by draft key.
    @State private var drafts: [String: FramingDraft] = [:]
    @State private var sending = false
    @State private var routed = false
    /// The hero picture last loaded, and the picture it was of: the crop
    /// windows wait for it, so a half-loaded preview never shows.
    @State private var loadedHero: ImageRef?
    @State private var loadedFor: String?

    struct Browsed: Equatable {
        let summary: ItemSummary
        let offset: Int  // where it was when browsed to: −n back, +n ahead
    }

    private var current: NowShowing? { model.player?.current }
    private var item: Item? { current?.item }
    private var history: [ItemSummary] { model.player?.history ?? [] }  // newest first
    private var upcoming: [ItemSummary] { model.player?.upcoming ?? [] }

    private func summary(at offset: Int) -> ItemSummary? {
        if offset < 0, -offset <= history.count { return history[-offset - 1] }
        if offset > 0, offset <= upcoming.count { return upcoming[offset - 1] }
        return nil
    }

    /// Places from the picture on the frame to the one browsed to. The lists
    /// move when the frame changes, so the picture is looked up again.
    private var offset: Int {
        guard let browsed else { return 0 }
        let id = browsed.summary.id
        if id == item?.id { return 0 }
        if summary(at: browsed.offset)?.id == id { return browsed.offset }
        if let index = upcoming.firstIndex(where: { $0.id == id }) { return index + 1 }
        if let index = history.firstIndex(where: { $0.id == id }) { return -(index + 1) }
        return browsed.offset  // on its way to the frame
    }

    private var selectedID: String? { offset == 0 ? item?.id : browsed?.summary.id }
    private var selectedItem: Item? {
        offset == 0 ? item : browsed.flatMap { details[$0.summary.id] }
    }

    private var draftKey: String {
        guard let selectedID else { return "" }
        return [selectedID, model.settings?.presentationKey ?? ""].joined(separator: "|")
    }

    var body: some View {
        NavigationStack(path: $path) {
            ZStack {
                AmbientBackground(swatches: selectedItem?.colors ?? browsed?.summary.colors ?? [])
                ScrollView {
                    VStack(alignment: .leading, spacing: 22) {
                        hero
                        if let progress = model.displayProgress {
                            DisplayProgressBar(progress: progress)
                                .frame(maxWidth: model.isPortrait ? 420 : .infinity)
                                .frame(maxWidth: .infinity)
                                .transition(.opacity.combined(with: .move(edge: .top)))
                        }
                        controls
                        if let selectedItem {
                            ArtworkInfo(item: selectedItem)
                                .id(selectedItem.id)
                        } else if offset == 0, let current {
                            Card {
                                Text(current.title.isEmpty ? "Bez tytułu" : current.title)
                                    .font(.serif(26, weight: .semibold))
                                if !current.description.isEmpty {
                                    Text(current.description).foregroundStyle(Theme.inkSoft)
                                }
                            }
                        }
                        if !upcoming.isEmpty {
                            Strip(title: "Następne", items: upcoming)
                        }
                        if !history.isEmpty {
                            Strip(title: "Ostatnio na ramce", items: history)
                        }
                    }
                    .padding(.horizontal, Theme.gutter)
                    .padding(.top, 4)
                    .padding(.bottom, 40)
                    .animation(.easeInOut, value: model.displayProgress == nil)
                }
                .refreshable { await model.refreshAll() }
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showingSend = true
                    } label: {
                        Image(systemName: "square.and.arrow.up")
                            .font(.headline)
                            .offset(y: -1)
                            .frame(width: 34, height: 34)
                            .background(.ultraThinMaterial, in: Circle())
                    }
                    .accessibilityLabel("Wyślij zdjęcie na ramkę")
                }
            }
            .toolbarTitleDisplayMode(.inline)
            .navigationDestination(for: String.self) { id in
                ItemDetailView(itemID: id)
            }
            .sheet(isPresented: $showingSend) {
                SendSheet()
            }
            .onChange(of: item?.id) { _, id in
                // The picture sent has arrived: back to "on the frame now".
                if browsed?.summary.id == id { browsed = nil }
            }
            .onChange(of: upcoming.first?.id, initial: true) { _, first in
                // CI screenshots: `-screen browse` starts at the next picture.
                guard LaunchRoute.screen == "browse", !routed, let first else { return }
                routed = true
                if let next = upcoming.first, next.id == first { browsed = Browsed(summary: next, offset: 1) }
            }
            .task(id: browsed?.summary.id) { await loadDetails() }
            .task(id: draftKey) { await loadFraming() }
            .task(id: selectedID) { await prefetchNeighbours() }
        }
    }

    // MARK: Hero

    private var heroRef: ImageRef? {
        if let id = selectedID, let trial = draft.trial, draft.key == draftKey {
            return .framePreview(id, framing: trial)  // the mat with the new window
        }
        if offset != 0, let browsed { return .framePreview(browsed.summary.id) }
        if let current { return .path(current.previewUrl) }
        return nil
    }

    /// The server is still making the preview, or it is on its way.
    private var heroLoading: Bool { heroRef != nil && loadedHero != heroRef }

    private var hero: some View {
        let aspect: CGFloat = model.isPortrait ? 9.0 / 16.0 : 16.0 / 9.0
        return HStack(spacing: 0) {
            arrow(-1)
            Spacer(minLength: 2)
            FramedArtwork(
                ref: heroRef, aspectRatio: aspect,
                placeholder: selectedItem?.placeholderColor ?? browsed?.summary.placeholderColor ?? Theme.mat
            ) {
                if let id = selectedID, draft.key == draftKey, loadedFor == id {
                    CropWindows(itemID: id, draft: $draft)
                        .transition(.opacity)
                }
            }
            .environment(\.artImageLoaded) { ref in
                guard ref == heroRef else { return }
                withAnimation(.easeOut(duration: 0.3)) {
                    loadedHero = ref
                    loadedFor = selectedID
                }
            }
            .id(selectedID ?? "")  // a fresh picture for each one browsed to
            .overlay {
                if heroRef == nil, model.connection != .connected {
                    ProgressView()
                }
            }
            .overlay {
                // Servers that report no progress: a spinner instead of the bar.
                if model.displayProgress == nil, offset == 0, model.working || model.player?.busy == true {
                    LoadingBadge(text: "Przygotowuję obraz…")
                } else if heroLoading {
                    LoadingBadge(text: "Wczytuję podgląd…")
                }
            }
            .frame(maxWidth: model.isPortrait ? 290 : .infinity)
            Spacer(minLength: 2)
            arrow(1)
        }
        .padding(.horizontal, -Theme.gutter + 2)  // the arrows at the sides of the screen
        .animation(.easeInOut, value: model.working)
    }

    /// Browse one picture back (−1) or ahead (+1); nothing is sent.
    private func arrow(_ direction: Int) -> some View {
        let target = offset + direction
        let enabled = target == 0 || summary(at: target) != nil
        return Button {
            withAnimation(.easeInOut(duration: 0.25)) {
                browsed = target == 0 ? nil : summary(at: target).map { Browsed(summary: $0, offset: target) }
            }
        } label: {
            Image(systemName: direction < 0 ? "chevron.left" : "chevron.right")
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(Theme.ink.opacity(0.75))
                .frame(width: 34, height: 72)
                .contentShape(Rectangle())
        }
        .buttonStyle(PressableStyle())
        .disabled(!enabled || sending)
        .opacity(enabled ? 1 : 0.2)
        .accessibilityLabel(direction < 0 ? "Poprzedni" : "Następny")
    }

    // MARK: Controls

    private var controls: some View {
        VStack(spacing: 12) {
            VStack(spacing: 3) {
                Text(placeLine)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(offset == 0 ? Theme.ink : Theme.vermilion)
                Text(hintLine)
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .multilineTextAlignment(.center)
            }
            .contentTransition(.opacity)
            if draft.key == draftKey, let id = selectedID, draft.view?.windows.isEmpty == false {
                CropTools(itemID: id, draft: $draft).disabled(sending)
            }
            Button {
                Task { await send() }
            } label: {
                HStack(spacing: 10) {
                    if sending { ProgressView().tint(Theme.paper) }
                    Text(canSend || sending ? "Pokaż na ramce" : "Jest na ramce")
                }
            }
            .buttonStyle(PrimaryButtonStyle())
            .disabled(!canSend || sending)
            .opacity(canSend || sending ? 1 : 0.45)
            .frame(maxWidth: model.isPortrait ? 420 : .infinity)
            HStack(spacing: 8) {
                Text(scheduleLine)
                if model.player?.hold != nil {
                    Button("Odepnij") { Task { await model.releaseHold() } }
                        .fontWeight(.semibold)
                }
            }
            .font(.footnote)
            .foregroundStyle(Theme.inkSoft)
        }
        .frame(maxWidth: .infinity)
    }

    private var canSend: Bool {
        guard selectedID != nil, !model.working else { return false }
        return offset != 0 || draft.change != nil && draft.key == draftKey
    }

    private var placeLine: String {
        switch offset {
        case 0: "Teraz na ramce"
        case -1: "Poprzednio na ramce"
        case ..<0: "Wcześniej na ramce"
        case 1: "Następny w kolejce"
        default: "W kolejce, za \(offset) \(Names.changes(offset))"
        }
    }

    private var hintLine: String {
        if draft.key == draftKey, draft.view?.windows.isEmpty == false {
            return draft.changed
                ? "Nowy kadr trafi na ramkę po „Pokaż na ramce”."
                : "Przesuń obraz palcem albo rozsuń dwa palce, żeby go wykadrować."
        }
        return offset == 0 ? " " : "Na ramkę trafi po „Pokaż na ramce”."
    }

    private var scheduleLine: String {
        guard let player = model.player else { return " " }
        if let hold = player.hold {
            if hold.forever { return "Przypięty na stałe" }
            if let until = When.schedule(hold.until) { return "Przypięty do: \(until)" }
        }
        if let next = When.schedule(player.nextChangeAt) { return "Następna zmiana: \(next)" }
        return " "
    }

    // MARK: Loading and sending

    /// The previews one back and one ahead, so the server makes them while
    /// this one is looked at and the arrows show them at once.
    private func prefetchNeighbours() async {
        for target in [offset + 1, offset - 1] where target != 0 {
            guard let id = summary(at: target)?.id,
                  let request = model.backend.request(for: .framePreview(id))
            else { continue }
            _ = try? await ImageLoader.shared.image(for: request, maxPixel: 1600)  // as FramedArtwork loads it
        }
    }

    private func loadDetails() async {
        guard let id = browsed?.summary.id, details[id] == nil else { return }
        if let loaded = try? await model.backend.item(id: id) { details[id] = loaded }
    }

    /// The crop of the picture browsed to: an unsent one kept from before,
    /// else as the server has it.
    private func loadFraming() async {
        let key = draftKey
        if draft.key != key, draft.changed, !draft.key.isEmpty { drafts[draft.key] = draft }
        if let kept = drafts[key] {
            draft = kept
            return
        }
        draft = FramingDraft(key: "")
        guard let id = selectedID else { return }
        let orientation = model.settings?.orientation ?? "landscape"
        guard let loaded = await FramingDraft.load(model.backend, itemID: id, orientation: orientation, key: key),
              key == draftKey
        else { return }
        draft = loaded
    }

    private func send() async {
        guard let id = selectedID else { return }
        sending = true
        defer { sending = false }
        let change = draft.key == draftKey ? draft.change : nil
        guard await model.present(itemID: id, offset: offset, framing: change) else { return }
        drafts[draftKey] = nil
        await model.followPlayer()
        if browsed?.summary.id == model.player?.current?.item?.id { browsed = nil }
        if change != nil {
            draft = FramingDraft()
            await loadFraming()  // as saved now
        }
    }
}

/// A spinner with a line of text, laid over the picture while it loads.
struct LoadingBadge: View {
    let text: String

    var body: some View {
        VStack(spacing: 10) {
            ProgressView().tint(.white)
            Text(text)
                .font(.footnote.weight(.medium))
                .foregroundStyle(.white)
        }
        .padding(18)
        .background(.black.opacity(0.45), in: RoundedRectangle(cornerRadius: 14))
        .allowsHitTesting(false)
        .transition(.opacity)
    }
}

/// Museum-label style description of the current picture.
struct ArtworkInfo: View {
    @Environment(AppModel.self) private var model
    let item: Item
    @State private var expanded = false
    @State private var favorite: Bool?

    var body: some View {
        Card(padding: 22) {
            HStack(alignment: .top) {
                Eyebrow(Names.kind(item.kind), color: Theme.vermilion)
                Spacer()
                Button {
                    Task {
                        let new = !(favorite ?? item.favorite)
                        favorite = new
                        _ = await model.setFavorite(item.id, new)
                    }
                } label: {
                    Image(systemName: (favorite ?? item.favorite) ? "heart.fill" : "heart")
                        .font(.title3)
                        .foregroundStyle((favorite ?? item.favorite) ? Theme.vermilion : Theme.inkSoft)
                        .contentTransition(.symbolEffect(.replace))
                }
                .accessibilityLabel("Ulubione")
            }
            Text(item.title.isEmpty ? "Bez tytułu" : item.title)
                .font(.serif(28, weight: .semibold))
                .foregroundStyle(Theme.ink)
                .lineLimit(3)
                .minimumScaleFactor(0.75)
            if item.kind == .photo {
                PhotoFacts(item: item)
            } else {
                VStack(alignment: .leading, spacing: 3) {
                    if !item.artist.isEmpty {
                        Text(item.artist).font(.serif(18)).foregroundStyle(Theme.ink)
                    }
                    if !item.artistBio.isEmpty {
                        Text(item.artistBio).font(.subheadline).foregroundStyle(Theme.inkSoft)
                    }
                }
                Text([item.dateText, item.medium].filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(.subheadline)
                    .foregroundStyle(Theme.inkSoft)
            }
            if !item.colors.isEmpty {
                PaletteStrip(swatches: item.colors)
                    .padding(.vertical, 4)
            }
            if !item.description.isEmpty {
                Text(item.description)
                    .font(.serif(16))
                    .lineSpacing(4)
                    .foregroundStyle(Theme.ink.opacity(0.88))
                    .lineLimit(expanded ? nil : 5)
                Button(expanded ? "Zwiń" : "Czytaj więcej") {
                    withAnimation(.easeInOut) { expanded.toggle() }
                }
                .font(.subheadline.weight(.semibold))
            }
            HStack {
                if !item.museum.isEmpty {
                    Label(item.museum, systemImage: "building.columns")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(1)
                }
                Spacer()
                NavigationLink(value: item.id) {
                    Text("Szczegóły")
                        .font(.subheadline.weight(.semibold))
                }
            }
        }
    }
}

/// Date, place and who added a family photo.
struct PhotoFacts: View {
    let item: Item
    @State private var place: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let taken = When.long(item.photo?.takenAt) ?? (item.dateText.isEmpty ? nil : item.dateText) {
                Label(taken, systemImage: "calendar")
            }
            if let place {
                Label(place, systemImage: "mappin.and.ellipse")
            }
            if let who = item.photo?.contributor ?? (item.artist.isEmpty ? nil : item.artist) {
                Label("Dodał(a): \(who)", systemImage: "person.crop.circle")
            }
            if let caption = item.photo?.caption, !caption.isEmpty {
                Text("„\(caption)”").font(.serif(17)).italic()
            }
        }
        .font(.subheadline)
        .foregroundStyle(Theme.ink)
        .task(id: item.id) { await geocode() }
    }

    private func geocode() async {
        guard let lat = item.photo?.latitude, let lon = item.photo?.longitude else { return }
        let marks = try? await CLGeocoder().reverseGeocodeLocation(
            CLLocation(latitude: lat, longitude: lon), preferredLocale: Locale(identifier: "pl_PL")
        )
        if let mark = marks?.first {
            place = [mark.locality ?? mark.name, mark.country].compactMap { $0 }.joined(separator: ", ")
        }
    }
}

/// Horizontal row of small pictures.
struct Strip: View {
    let title: String
    let items: [ItemSummary]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Eyebrow(title)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 14) {
                    ForEach(items) { item in
                        NavigationLink(value: item.id) {
                            VStack(alignment: .leading, spacing: 6) {
                                ArtImage(ref: .thumb(item.id), placeholder: item.placeholderColor, maxPixel: 400)
                                    .frame(width: 120, height: 92)
                                    .clipShape(RoundedRectangle(cornerRadius: 5, style: .continuous))
                                    .shadow(color: .black.opacity(0.12), radius: 6, y: 4)
                                Text(item.title)
                                    .font(.serif(13, weight: .medium))
                                    .foregroundStyle(Theme.ink)
                                    .lineLimit(2)
                                    .frame(width: 120, alignment: .leading)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.vertical, 4)
            }
            .scrollClipDisabled()
        }
    }
}
