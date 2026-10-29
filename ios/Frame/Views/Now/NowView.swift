import CoreLocation
import SwiftUI

/// Home: the picture on the frame, presented like an exhibit. The arrows
/// browse what was and what will be on the frame without sending anything,
/// and "Teraz" jumps back to the one on it; a tap on the picture opens
/// it on the crop screen, and "Pokaż na ramce" sends the one browsed to.
/// A picture that did not reach the frame says so, with the one the frame
/// still shows and a way to send it again. While a picture goes to the
/// frame, "Teraz" shows only what the frame shows, and the e-paper's redraw
/// as the old picture going over to the new one.
struct NowView: View {
    @Environment(AppModel.self) private var model
    @State private var showingSend = LaunchRoute.screen == "send"
    @State private var path = NavigationPath()
    /// The picture browsed to; nil is the one on the frame.
    @State private var browsed: Browsed?
    @State private var details: [String: Item] = [:]
    @State private var draft = FramingDraft()
    /// Crops saved here, by draft key: the preview of a picture browsed to
    /// asks for them by name, as the one cached from before shows the old crop.
    @State private var applied: [String: FramingCrops] = [:]
    @State private var cropping = false
    @State private var sending = false
    @State private var routed = false
    /// The hero picture last loaded: cropping waits for it, so a half-loaded
    /// preview never opens.
    @State private var loadedHero: ImageRef?
    /// What the panel shows, kept while a new picture is on its way.
    @State private var frameShows: NowShowing?
    /// The picture on its way, for the swap: loaded, and in the panel's inks.
    @State private var swapImage: (url: String, image: UIImage, inks: InkGrid)?
    /// The bar's fraction when the panel began its redraw.
    @State private var redrawFrom: Double?

    struct Browsed: Equatable {
        let summary: ItemSummary
        let offset: Int  // where it was when browsed to: −n back, +n ahead
    }

    private var current: NowShowing? { model.player?.current }
    private var item: Item? { current?.item }
    private var history: [ItemSummary] { model.player?.history ?? [] }  // newest first
    private var upcoming: [ItemSummary] { model.player?.upcoming ?? [] }

    /// The picture on the frame, as the server has it, is not on the panel:
    /// sent and never downloaded, waiting for it to wake, or on its way.
    private var undelivered: Delivery? {
        guard offset == 0, let delivery = model.player?.delivery, !delivery.isShown else { return nil }
        return delivery
    }

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

    // MARK: A picture on its way

    /// A picture is on its way to the frame (or the request just went):
    /// no arrows and no buttons, only what the frame shows.
    private var inFlight: Bool {
        if let progress = model.displayProgress { return progress.active }
        return sending
    }

    private var redrawing: Bool {
        model.displayProgress.map { $0.active && $0.stage == "refreshing" } ?? false
    }

    /// How far the panel's redraw is, 0…1, from when it began.
    private var redrawProgress: Double? {
        guard redrawing, let fraction = model.displayProgress?.fraction else { return nil }
        let from = min(redrawFrom ?? fraction, 0.99)
        return min(max((fraction - from) / (1 - from), 0), 1)
    }

    /// The picture "Teraz" shows as on the frame: while one is on its way,
    /// the one the panel still has.
    private var heroShowing: NowShowing? {
        inFlight ? frameShows ?? current : current
    }

    /// What the panel shows, as far as the server knows; nil while a
    /// picture is on its way and the server no longer says.
    private var panelShows: NowShowing? {
        if let onFrame = model.player?.delivery?.onFrame { return onFrame }
        return inFlight ? nil : current
    }

    /// The picture whose texts and colours are shown below.
    private var shownItem: Item? {
        offset == 0 ? heroShowing?.item : selectedItem
    }

    private var draftKey: String {
        guard let selectedID else { return "" }
        return [selectedID, model.settings?.presentationKey ?? ""].joined(separator: "|")
    }

    var body: some View {
        NavigationStack(path: $path) {
            ZStack {
                AmbientBackground(swatches: shownItem?.colors ?? browsed?.summary.colors ?? [])
                ScrollView {
                    VStack(alignment: .leading, spacing: 22) {
                        hero
                        if let progress = model.displayProgress {
                            DisplayProgressBar(progress: progress)
                                .frame(maxWidth: model.isPortrait ? 420 : .infinity)
                                .frame(maxWidth: .infinity)
                                .transition(.opacity.combined(with: .move(edge: .top)))
                        }
                        if !inFlight {
                            controls
                        }
                        if !inFlight, let onFrame = undelivered?.onFrame {
                            OnFrameNote(showing: onFrame)
                                .transition(.opacity)
                        }
                        if offset == 0, undelivered == nil, let device = model.status?.device,
                           device.powerState == "deep_sleep" {
                            FrameAsleepNote()
                                .transition(.opacity)
                        }
                        if offset == 0, let device = model.status?.device, let pending = modePendingText(device) {
                            NoticeRow(icon: "clock.arrow.circlepath", color: Theme.accent, text: pending)
                        }
                        if let shownItem {
                            ArtworkInfo(item: shownItem, polish: offset == 0 ? heroShowing?.polish : nil)
                                .id(shownItem.id)
                        } else if offset == 0, let current = heroShowing {
                            Card {
                                Text(current.title.isEmpty ? "Bez tytułu" : current.title)
                                    .font(.serif(26, weight: .semibold))
                                if !current.description.isEmpty {
                                    Text(current.description).foregroundStyle(Theme.inkSoft)
                                }
                            }
                        }
                        if !upcoming.isEmpty {
                            Strip(title: "Następne", items: upcoming, queued: Set(model.player?.queued ?? []))
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
                .refreshable { await Task { await model.refreshAll() }.value }
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
            .fullScreenCover(isPresented: $cropping) {
                if let id = selectedID {
                    CropScreen(
                        itemID: id, preview: heroRef,
                        aspectRatio: model.isPortrait ? 9.0 / 16.0 : 16.0 / 9.0,
                        placeholder: selectedItem?.placeholderColor ?? browsed?.summary.placeholderColor ?? Theme.mat,
                        onFrame: offset == 0,
                        draft: $draft, save: saveCrop
                    )
                }
            }
            .onChange(of: canCrop) { _, can in
                // CI screenshots: `-screen crop` opens the crop screen.
                guard LaunchRoute.screen == "crop", !routed, can else { return }
                routed = true
                cropping = true
            }
            .onChange(of: item?.id) { _, id in
                // The picture sent has arrived: back to "on the frame now".
                if browsed?.summary.id == id { browsed = nil }
            }
            .onChange(of: inFlight) { _, flying in
                // Only the picture on the frame while another is on its way.
                if flying { withAnimation(.easeInOut(duration: 0.25)) { browsed = nil } }
            }
            .onChange(of: panelShows?.previewUrl, initial: true) {
                if let panelShows { frameShows = panelShows }
            }
            .onChange(of: redrawing, initial: true) { _, now in
                redrawFrom = now ? model.displayProgress?.fraction : nil
            }
            .task(id: inFlight ? current?.previewUrl : nil) { await loadSwap() }
            .onChange(of: upcoming.first?.id, initial: true) { _, first in
                // CI screenshots: `-screen browse` starts at the next picture.
                guard LaunchRoute.screen == "browse", !routed, let first else { return }
                routed = true
                if let next = upcoming.first, next.id == first { browsed = Browsed(summary: next, offset: 1) }
            }
            .task(id: browsed?.summary.id) { await loadDetails() }
            .task(id: draftKey) { await loadFraming() }
            // Once the picture looked at is in, and again with a new presentation.
            .task(id: heroReady ? draftKey : "") { await prefetchNeighbours() }
        }
    }

    // MARK: Hero

    private var heroRef: ImageRef? {
        if let id = selectedID, let trial = draft.trial, draft.key == draftKey {
            return .framePreview(id, settings: model.settings, framing: trial)  // the mat with the new window
        }
        // With the settings in the address, a new presentation redraws the
        // pictures still to come instead of showing the ones cached before.
        if offset != 0, let browsed {
            return .framePreview(browsed.summary.id, settings: model.settings, framing: applied[draftKey])
        }
        if let showing = heroShowing { return .path(showing.previewUrl) }
        return nil
    }

    /// The new picture laid over the old one while the panel redraws; once
    /// it is done, whole until the hero itself has the new picture, so the
    /// old one never shows again for a moment.
    private var swapOverlay: FrameSwap? {
        guard offset == 0, let current else { return nil }
        let loaded = swapImage?.url == current.previewUrl ? swapImage : nil
        if let progress = redrawProgress, current.previewUrl != heroShowing?.previewUrl {
            return FrameSwap(image: loaded?.image, inks: loaded?.inks, progress: progress)
        }
        if !inFlight, let loaded, loadedHero != heroRef {
            return FrameSwap(image: loaded.image, inks: loaded.inks, progress: 1)
        }
        return nil
    }

    /// The server is still making the preview, or it is on its way.
    private var heroLoading: Bool { heroRef != nil && loadedHero != heroRef }
    private var heroReady: Bool { heroRef != nil && loadedHero == heroRef }

    /// The crop of the picture shown is loaded, and so is its preview.
    private var canCrop: Bool {
        selectedID != nil && draft.key == draftKey && draft.view?.windows.isEmpty == false
            && heroRef != nil && loadedHero == heroRef && !inFlight
    }

    private var hero: some View {
        let aspect: CGFloat = model.isPortrait ? 9.0 / 16.0 : 16.0 / 9.0
        return HStack(spacing: 0) {
            arrow(-1)
            Spacer(minLength: 2)
            FramedArtwork(
                ref: heroRef, aspectRatio: aspect,
                placeholder: shownItem?.placeholderColor ?? browsed?.summary.placeholderColor ?? Theme.mat
            ) {
                if let swapOverlay {
                    // The bar is asked once a second: glide between answers.
                    swapOverlay.animation(.linear(duration: 1), value: swapOverlay.progress)
                }
            }
            .environment(\.artImageLoaded) { ref in
                guard ref == heroRef else { return }
                withAnimation(.easeOut(duration: 0.3)) { loadedHero = ref }
            }
            .contentShape(Rectangle())
            .onTapGesture {
                if canCrop, !sending { cropping = true }
            }
            .accessibilityAddTraits(canCrop ? .isButton : [])
            .accessibilityHint(Text(canCrop ? "Otwiera kadrowanie na całym ekranie" : ""))
            .accessibilityValue(Text(redrawing ? "Ramka zmienia obraz" : ""))
            // A fresh picture for each one browsed to; the one on the frame
            // keeps its view, so the swap ends without a blink.
            .id(offset == 0 ? "now" : selectedID ?? "")
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
        .disabled(!enabled || inFlight)
        .opacity(inFlight ? 0 : enabled ? 1 : 0.2)
        .animation(.easeInOut(duration: 0.3), value: inFlight)
        .accessibilityLabel(direction < 0 ? "Poprzedni" : "Następny")
    }

    // MARK: Controls

    /// Under the picture: on the frame, only when it changes next; browsed
    /// to, where it is in the queue (the next one also says when, on the
    /// same line), with "Teraz" back to it and "Pokaż na ramce". A picture that did
    /// not reach the frame says why and what can be done.
    private var controls: some View {
        VStack(spacing: 12) {
            // Every minute: the countdown to the frame's next wake.
            TimelineView(.everyMinute) { _ in
                VStack(spacing: 3) {
                    if let placeLine {
                        let place = Text(placeLine).fontWeight(.semibold).foregroundStyle(Theme.vermilion)
                        let when = Text(nextChange.map { " · \($0)" } ?? "").foregroundStyle(Theme.inkSoft)
                        Text("\(place)\(when)")
                            .font(.footnote)
                            .multilineTextAlignment(.center)
                    }
                    if let undelivered {
                        Text(undelivered.explanation)
                            .font(.caption)
                            .foregroundStyle(Theme.inkSoft)
                            .multilineTextAlignment(.center)
                    } else if offset == 0 {
                        schedule
                    }
                }
                .contentTransition(.opacity)
            }
            if offset != 0 {
                HStack(spacing: canSkip ? 10 : 12) {
                    backToNow
                    if canSkip {
                        skipButton
                    }
                    Button {
                        Task { await primaryAction() }
                    } label: {
                        Label {
                            Text("Pokaż na ramce")
                        } icon: {
                            if sending {
                                ProgressView().tint(Theme.paper)
                            } else {
                                Image(systemName: "photo.artframe")
                            }
                        }
                    }
                    .buttonStyle(ActionButtonStyle(prominent: true, fillsHeight: canSkip))
                    .disabled(!primaryEnabled || sending)
                    .opacity(primaryEnabled || sending ? 1 : 0.45)
                }
                .fixedSize(horizontal: false, vertical: true)  // the narrow buttons as tall as the wide one
                .frame(maxWidth: model.isPortrait ? 420 : .infinity)
                .transition(.opacity)
            } else if undelivered != nil && !asleep || primaryEnabled || sending {
                Button {
                    Task { await primaryAction() }
                } label: {
                    HStack(spacing: 10) {
                        if sending { ProgressView().tint(Theme.paper) }
                        Text(primaryTitle)
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(!primaryEnabled || sending)
                .opacity(primaryEnabled || sending ? 1 : 0.45)
                .frame(maxWidth: model.isPortrait ? 420 : .infinity)
                .transition(.opacity)
            }
            if undelivered != nil {
                schedule
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, -12)  // the caption close under the frame
    }

    /// When the frame changes next, or how long the picture is pinned.
    private var schedule: some View {
        VStack(spacing: 4) {
            HStack(spacing: 8) {
                Text(scheduleLine)
                if model.player?.hold != nil {
                    Button("Odepnij") { Task { await model.releaseHold() } }
                        .fontWeight(.semibold)
                }
            }
            if let wakeLine {
                Text(wakeLine)
            }
        }
        .font(.footnote)
        .foregroundStyle(Theme.inkSoft)
    }

    /// Back to the picture on the frame from wherever the arrows went.
    private var backToNow: some View {
        Button {
            withAnimation(.easeInOut(duration: 0.25)) { browsed = nil }
        } label: {
            Label("Teraz", systemImage: offset > 0 ? "arrow.uturn.left" : "arrow.uturn.right")
        }
        .buttonStyle(ActionButtonStyle(wide: false, stacked: canSkip))
        .disabled(sending)
        .accessibilityLabel("Wróć do obrazu na ramce")
        .transition(.opacity)
    }

    /// A picture waiting in the queue can be skipped, unless it is the
    /// only one (it would come straight back).
    private var canSkip: Bool {
        guard offset > 0, let id = browsed?.summary.id else { return false }
        return model.isQueued(id) || upcoming.count > 1
    }

    /// "Pomiń": the picture browsed to leaves the queue for this round; the
    /// one after it takes its place here.
    private var skipButton: some View {
        Button {
            Task { await skip() }
        } label: {
            Label("Pomiń", systemImage: "forward.end")
        }
        .buttonStyle(ActionButtonStyle(wide: false, stacked: true))
        .disabled(sending)
        .accessibilityLabel("Pomiń ten obraz w kolejce")
        .transition(.opacity)
    }

    private func skip() async {
        guard let browsed else { return }
        let place = offset
        guard await model.skip(browsed.summary) else { return }
        withAnimation(.easeInOut(duration: 0.25)) {
            self.browsed = summary(at: place).map { Browsed(summary: $0, offset: place) }
        }
    }

    private var canSend: Bool {
        guard selectedID != nil, !model.working else { return false }
        return offset != 0 || draft.change != nil && draft.key == draftKey
    }

    /// Not on the panel and nothing else to send: send it again, or wake
    /// the frame it waits for (not in deep sleep: Wake-on-LAN cannot reach it).
    private var retry: Bool { !canSend && undelivered?.isFailed == true }
    private var wakeUp: Bool { !canSend && undelivered?.isWaiting == true && undelivered?.asleepUntil == nil }
    /// Waiting for the frame's own alarm: no button can bring it sooner.
    private var asleep: Bool { undelivered?.isWaiting == true && undelivered?.asleepUntil != nil }

    private var primaryEnabled: Bool { (canSend || retry || wakeUp) && !model.working }

    private var primaryTitle: String {
        if canSend || sending { return "Pokaż na ramce" }
        if retry { return "Wyślij ponownie" }
        if wakeUp { return "Obudź ramkę" }
        if let undelivered { return undelivered.isWaiting ? "Czeka na ramkę" : "Wysyłam…" }
        return "Jest na ramce"
    }

    private func primaryAction() async {
        if canSend {
            await send()
        } else if retry {
            await model.pushAgain()
        } else if wakeUp {
            await model.wake()
            // Once awake, the waiting picture goes out on its own.
            model.trackProgress(expectingStart: true)
            await model.refreshPlayer()
        }
    }

    /// Where the picture browsed to is; nil for the one on the frame.
    private var placeLine: String? {
        switch offset {
        case 0: undelivered?.headline
        case -1: "Poprzednio na ramce"
        case ..<0: "Wcześniej na ramce"
        case 1: "Następny w kolejce" + addedLine
        default: "W kolejce, za \(offset) \(Names.changes(offset))" + addedLine
        }
    }

    /// When the next one in the queue goes on the frame; for a picture
    /// waiting for the frame's alarm, how long until it rings.
    private var nextChange: String? {
        if offset == 0, let undelivered, undelivered.missedWakeAt == nil {
            return When.countdown(undelivered.asleepUntilAt)
        }
        guard offset == 1, let player = model.player else { return nil }
        if let hold = player.hold {
            return hold.forever ? "po odpięciu" : When.schedule(hold.until)
        }
        return When.schedule(player.nextChangeAt)
    }

    private var addedLine: String {
        guard let id = browsed?.summary.id, model.isQueued(id) else { return "" }
        return " · dodany przez Ciebie"
    }

    private var scheduleLine: String {
        guard let player = model.player else { return " " }
        if let hold = player.hold {
            if hold.forever { return "Przypięty na stałe" }
            if let until = When.schedule(hold.until) { return "Przypięty do: \(until)" }
        }
        if let next = When.schedule(player.nextChangeAt) {
            // Economy: the frame sleeps until then, so how long it is matters.
            let countdown = model.settings?.isEconomy == true && undelivered == nil
                ? When.countdown(player.nextChangeAt).map { " · \($0)" } ?? "" : ""
            return "Następna zmiana: \(next)\(countdown)"
        }
        return " "
    }

    /// The frame's alarm when it sleeps with the Wi-Fi off and wakes before
    /// the next change (a check between changes, "Sprawdzaj też co"): the
    /// "Ramka śpi" card below no longer says when.
    private var wakeLine: String? {
        guard offset == 0, let device = model.status?.device, device.powerState == "deep_sleep",
              let wake = When.date(device.wakeAt), let at = When.schedule(device.wakeAt)
        else { return nil }
        let player = model.player
        if player?.hold == nil, let next = When.date(player?.nextChangeAt),
           wake.timeIntervalSince(next) > -60 {
            return nil  // it wakes for the change itself
        }
        let countdown = When.countdown(device.wakeAt).map { " · \($0)" } ?? ""
        return "Pobudka ramki: \(at)\(countdown)"
    }

    // MARK: Loading and sending

    /// The previews one back and one ahead, so the server makes them while
    /// this one is looked at and the arrows show them at once. Only after
    /// the one looked at: it goes first.
    private func prefetchNeighbours() async {
        guard heroReady else { return }
        for target in [offset + 1, offset - 1] where target != 0 {
            guard let id = summary(at: target)?.id,
                  let request = model.backend.request(for: .framePreview(id, settings: model.settings))
            else { continue }
            // As FramedArtwork loads it.
            _ = try? await ImageLoader.shared.image(for: request, maxPixel: 1600, priority: .high)
        }
    }

    /// The picture on its way, ahead of the redraw: as the hero loads it,
    /// and cut into squares of ink.
    private func loadSwap() async {
        guard inFlight, let url = current?.previewUrl, swapImage?.url != url,
              let request = model.backend.request(for: .path(url)),
              let image = try? await ImageLoader.shared.image(for: request, maxPixel: 1600, priority: .high),
              !Task.isCancelled, let inks = InkGrid(image: image, portrait: model.isPortrait)
        else { return }
        swapImage = (url, image, inks)
    }

    private func loadDetails() async {
        guard let id = browsed?.summary.id, details[id] == nil else { return }
        if let loaded = try? await model.backend.item(id: id) { details[id] = loaded }
    }

    /// The crop of the picture browsed to, as the server has it.
    private func loadFraming() async {
        let key = draftKey
        draft = FramingDraft(key: "")
        guard let id = selectedID else { return }
        let orientation = model.settings?.orientation ?? "landscape"
        guard let loaded = await FramingDraft.load(model.backend, itemID: id, orientation: orientation, key: key),
              key == draftKey
        else { return }
        draft = loaded
    }

    /// "Zapisz kadr" on the crop screen: the picture on the frame now is
    /// redrawn with it there, one browsed to keeps it for when it is shown.
    private func saveCrop() async -> Bool {
        guard let id = selectedID, draft.key == draftKey, let change = draft.change else { return true }
        let key = draft.key
        let onFrame = offset == 0
        do {
            let saved = try await model.applyFraming(itemID: id, change)
            if key == draft.key {
                draft = FramingDraft(saved: saved, key: key)
                applied[key] = draft.savedCrops
            }
        } catch {
            model.show(error)
            return false
        }
        if onFrame {
            model.toast = "Nowy kadr — ramka odświeża obraz"
            Task { await model.followPlayer() }
        } else {
            model.toast = "Zapisano kadr"
        }
        return true
    }

    private func send() async {
        guard let id = selectedID else { return }
        sending = true
        defer { sending = false }
        let change = draft.key == draftKey ? draft.change : nil
        guard await model.present(itemID: id, offset: offset, framing: change) else { return }
        await model.followPlayer()
        if browsed?.summary.id == model.player?.current?.item?.id { browsed = nil }
        if change != nil {
            draft = FramingDraft()
            await loadFraming()  // as saved now
        }
    }
}

/// What the frame still shows while the picture above did not reach it.
struct OnFrameNote: View {
    let showing: NowShowing

    var body: some View {
        Card(padding: 14) {
            HStack(spacing: 14) {
                ArtImage(
                    ref: .path(showing.previewUrl),
                    placeholder: showing.item?.placeholderColor ?? Theme.mat,
                    maxPixel: 300
                )
                .frame(width: 64, height: 64)
                .clipShape(RoundedRectangle(cornerRadius: 5, style: .continuous))
                VStack(alignment: .leading, spacing: 3) {
                    Eyebrow("Na ramce nadal")
                    Text(showing.title.isEmpty ? "Bez tytułu" : showing.title)
                        .font(.serif(17, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                        .lineLimit(2)
                    if let artist = showing.item?.artist, !artist.isEmpty {
                        Text(artist)
                            .font(.subheadline)
                            .foregroundStyle(Theme.inkSoft)
                            .lineLimit(1)
                    }
                }
            }
        }
        .accessibilityElement(children: .combine)
    }
}

/// The frame sleeps with its Wi-Fi off: nothing sent reaches it before its
/// alarm, unless its button wakes it. When the alarm rings is in the lines
/// above ("Następna zmiana", "Pobudka ramki").
struct FrameAsleepNote: View {
    var body: some View {
        Card(padding: 14) {
            HStack(alignment: .top, spacing: 14) {
                Image(systemName: "moon.zzz")
                    .font(.title2)
                    .foregroundStyle(Theme.accent)
                    .frame(width: 32)
                VStack(alignment: .leading, spacing: 4) {
                    Eyebrow("Ramka śpi")
                    Text("Aby zmienić obraz wcześniej, naciśnij guzik na ramce")
                        .font(.serif(17, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
        }
        .accessibilityElement(children: .combine)
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

/// Museum-label style description of the current picture, in Polish once
/// the work's Polish texts are written ("Polskie tytuły i opisy").
struct ArtworkInfo: View {
    @Environment(AppModel.self) private var model
    let item: Item
    /// As the player gave it for the picture on the frame; else asked for.
    var polish: PolishText?
    @State private var asked: PolishText?
    @State private var expanded = false
    @State private var favorite: Bool?

    private var shown: PolishText? { asked ?? polish }
    private var title: String {
        nonEmpty(shown?.title) ?? (item.title.isEmpty ? "Bez tytułu" : item.title)
    }
    private var about: String { nonEmpty(shown?.full) ?? item.description }
    private var artistNote: String { nonEmpty(shown?.artistNote) ?? item.artistBio }
    private var facts: String {
        [nonEmpty(shown?.date) ?? item.dateText, nonEmpty(shown?.medium) ?? item.medium]
            .filter { !$0.isEmpty }.joined(separator: " · ")
    }

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
            // The title opens the work's card, like "Szczegóły" below.
            NavigationLink(value: item.id) {
                Text(title)
                    .font(.serif(28, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(3)
                    .minimumScaleFactor(0.75)
                    .multilineTextAlignment(.leading)
            }
            .buttonStyle(.plain)
            .accessibilityHint(Text("Otwiera kartę dzieła"))
            if item.kind == .photo {
                PhotoFacts(item: item)
            } else {
                VStack(alignment: .leading, spacing: 3) {
                    if !item.artist.isEmpty {
                        // Their other works, on Discover's search.
                        Button {
                            model.artistSearch = item.artist
                        } label: {
                            HStack(alignment: .firstTextBaseline, spacing: 6) {
                                Text(item.artist).font(.serif(18)).foregroundStyle(Theme.ink)
                                Image(systemName: "magnifyingglass")
                                    .font(.footnote.weight(.semibold))
                                    .foregroundStyle(Theme.inkSoft)
                            }
                            .multilineTextAlignment(.leading)
                        }
                        .buttonStyle(.plain)
                        .accessibilityHint(Text("Szuka innych dzieł tego autora"))
                    }
                    if !artistNote.isEmpty {
                        Text(artistNote).font(.subheadline).foregroundStyle(Theme.inkSoft)
                    }
                }
                Text(facts)
                    .font(.subheadline)
                    .foregroundStyle(Theme.inkSoft)
            }
            if !item.colors.isEmpty {
                PaletteStrip(swatches: item.colors)
                    .padding(.vertical, 4)
            }
            if !about.isEmpty {
                Text(about)
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
        .task(id: item.id) { await loadPolish() }
    }

    /// The work's Polish texts, when the player did not bring them: at once
    /// if written, else asked for ahead of the background and waited for a
    /// few times. Without a key or with the switch off: the museum's own.
    private func loadPolish() async {
        guard polish == nil, item.kind != .photo else { return }
        for attempt in 0 ..< 4 {
            guard let view = try? await model.backend.polish(itemID: item.id, wait: attempt == 0 ? 0 : 20),
                  !Task.isCancelled
            else { return }
            if let text = view.text {
                withAnimation(.easeInOut) { asked = text }
                return
            }
            if view.status != "waiting" { return }
        }
    }

    private func nonEmpty(_ text: String?) -> String? {
        guard let text, !text.isEmpty else { return nil }
        return text
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

/// Horizontal row of small pictures; a long press queues one next, or
/// takes back one added with "Dodaj do kolejki" (marked in the corner).
struct Strip: View {
    @Environment(AppModel.self) private var model
    let title: String
    let items: [ItemSummary]
    var queued: Set<String> = []

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
                                    .overlay(alignment: .topLeading) {
                                        if queued.contains(item.id) {
                                            Image(systemName: QueueButton.symbol)
                                                .font(.caption2.weight(.bold))
                                                .foregroundStyle(.white)
                                                .padding(5)
                                                .background(Theme.vermilion, in: Circle())
                                                .padding(5)
                                                .accessibilityLabel("Dodane do kolejki")
                                        }
                                    }
                                    .shadow(color: .black.opacity(0.12), radius: 6, y: 4)
                                Text(item.shownTitle)
                                    .font(.serif(13, weight: .medium))
                                    .foregroundStyle(Theme.ink)
                                    .lineLimit(2)
                                    .frame(width: 120, alignment: .leading)
                            }
                        }
                        .buttonStyle(.plain)
                        .contextMenu {
                            if queued.contains(item.id) {
                                Button("Usuń z kolejki", systemImage: "minus.circle", role: .destructive) {
                                    Task { await model.dequeue(itemID: item.id) }
                                }
                            } else {
                                QueueButton(itemID: item.id)
                            }
                        }
                    }
                }
                .padding(.vertical, 4)
            }
            .scrollClipDisabled()
        }
    }
}
