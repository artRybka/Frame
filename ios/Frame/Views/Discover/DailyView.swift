import SwiftUI
import UniformTypeIdentifiers

/// The study of the day at the top of Odkrywaj: a band of the picture
/// (cropped around the place Claude named, else what draws the eye), its
/// title and one sentence written to fit two lines, an arrow in the corner;
/// the whole tile opens its page. Kept low, so the themes start right below it.
/// The picture sits a little deeper than the card (`parallax()`); like the
/// "Pod lupą" cards it is brighter (HDR), glossy and lifted over the page.
/// Held, the owner can draw another one (`drawDailyAgainMenu`).
struct DailyTile: View {
    let work: DailyWork

    private var byline: String {
        [Names.artist(work.item.item.artist), work.item.item.dateText].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    /// Where Claude said the picture is about, to crop around.
    private var focus: UnitPoint? { work.focus.map { UnitPoint(x: $0.x, y: $0.y) } }

    /// The HDR lift of "Pod lupą" cards (`WorkTile`): full over the top
    /// third, a tenth of it at the caption (Mateusz 2026-11-12).
    static let glowFade = 0.1
    static let glowHold = 0.3
    static let glowBoost = 1.35

    /// The work's original, the sharper copy its card found too, as the
    /// study's page asks for it (`DailyView.originalRef`).
    static func originalRef(_ work: DailyWork) -> ImageRef {
        let item = work.item.item
        if item.sharper == nil, let card = ItemPeeks.cards[item.id], card.sharper != nil {
            return card.originalRef
        }
        return item.originalRef
    }

    var body: some View {
        NavigationLink(value: DailyRoute(day: nil)) {
            VStack(alignment: .leading, spacing: 0) {
                Color.clear
                    .frame(height: 130)
                    .frame(maxWidth: .infinity)
                    .overlay {
                        ZStack {
                            ArtImage(
                                ref: work.item.thumb,
                                fallback: work.item.thumbFallback,
                                placeholder: work.item.item.placeholderColor,
                                maxPixel: 1000,
                                priority: .high,
                                subjectFocus: true,
                                focusPoint: focus,
                                brighten: true,
                                glowFade: Self.glowFade,
                                glowHold: Self.glowHold,
                                glowBoost: Self.glowBoost
                            )
                            // The thumbnail (640 px) is stretched over the
                            // band's ~1050: blurry (Mateusz 2026-11-12). The
                            // original fades in over it, at the size the
                            // study's page asks for, so the page has it at once.
                            if work.item.inLibrary {
                                ArtImage(
                                    ref: Self.originalRef(work),
                                    placeholder: .clear,
                                    maxPixel: DailyView.originalPixels,
                                    priority: .high,
                                    subjectFocus: true,
                                    focusPoint: focus,
                                    crossfade: true,
                                    brighten: true,
                                    glowFade: Self.glowFade,
                                    glowHold: Self.glowHold,
                                    glowBoost: Self.glowBoost
                                )
                            }
                        }
                        // A touch bigger than the band, so it can drift in it.
                        .padding(.horizontal, -Parallax.side)
                        .padding(.vertical, -Parallax.top)
                        .parallax()
                    }
                    .clipped()
                VStack(alignment: .leading, spacing: 2) {
                    Text(work.title)
                        .font(.serif(19, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                    Text(byline)
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(1)
                    HStack(alignment: .bottom, spacing: 10) {
                        Text(work.teaser)
                            .font(.serif(14))
                            .foregroundStyle(Theme.ink.opacity(0.85))
                            .lineLimit(2)
                            .minimumScaleFactor(0.9)
                            .multilineTextAlignment(.leading)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        // Only a hint: the whole card opens the study.
                        CardArrow()
                    }
                    .padding(.top, 4)
                }
                .padding(.horizontal, 12)
                .padding(.top, 10)
                .padding(.bottom, 11)
            }
            .background(Theme.card, in: RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
            .clipShape(RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: Theme.corner, style: .continuous).strokeBorder(Theme.hairline))
            // The glossy coat of "Pod lupą": a diagonal streak that runs
            // with the phone's turn (Mateusz 2026-11-12).
            .overlay {
                GlassSheen(peak: 0.65)
                    .clipShape(RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
            }
            .contentShape(RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
            // Standing a little over the page, as "Pod lupą" cards do.
            .liftedCard(cornerRadius: Theme.corner)
        }
        .buttonStyle(.plain)
        .accessibilityHint("Studium dnia")
        .drawDailyAgainMenu()
    }
}

/// A work's study: why today (on its day, for the study of the day), the
/// text under its own title, a note about the artist, the composition drawn
/// over the picture, colour, works like it, what it led to, other works by
/// the artist and, last, how it fares on the frame with the buttons to show
/// or queue it. Written by Claude once a day for the study of the day (while
/// it writes, or without a key, the museum's text stands in), or when asked
/// for on a work's card (`route.study`). A tap on the picture opens it on the
/// whole screen to zoom into.
struct DailyView: View {
    @Environment(AppModel.self) private var model
    let route: DailyRoute
    @State private var work: DailyWork?
    @State private var failed = false
    @State private var take = LaunchRoute.take
    @State private var sending = false
    @State private var sent: Bool?
    @State private var queueTaps = 0
    /// The page's width: the picture takes all of it, whatever loads first.
    @State private var pageWidth: CGFloat = 0
    @State private var zoomed = false
    /// When each work's palette under "Kolor i światło" began to be
    /// painted: its paints' swatches follow it.
    @State private var painted: [String: (at: Date, takes: Double)] = [:]
    /// The work as its card has it, for the heart and "…" top right.
    @State private var card: Item?
    @State private var addingToPlaylist = false
    @State private var savingPhoto = false
    @State private var findingCopies = false
    /// "Wczytaj kupioną kopię": the file picker for a copy bought in Alamy.
    @State private var bringingCopy = false
    /// How far the page is scrolled, for the glow at the top.
    @State private var scrolled: CGFloat = 0
    /// The title held once: the museum's own shows until held again ("Tytuł w oryginale").
    @State private var peeking = false
    /// The picture the whole-screen viewer grows out of.
    @Namespace private var zoomSpace
    /// "Na Twojej ramce" opens cropping, as on Teraz and the work's card.
    @State private var draft = FramingDraft()
    /// Crops saved here: the preview asks for them by name, as the one
    /// cached from before shows the old crop.
    @State private var applied: FramingCrops?
    /// The preview last loaded: cropping waits for it.
    @State private var loadedPreview: ImageRef?
    @State private var cropping = false
    /// Cropping's frame has left the preview (`CropScreen.onOpen`): only
    /// then is the preview hidden under it.
    @State private var cropAway = false
    /// Where the preview is on the screen, for cropping's frame to fly from.
    @State private var cropHome: CGRect?
    /// Held open, the preview had grown a touch: the frame starts that size.
    @State private var cropGrow: CGFloat = 1
    /// "Wykonaj ponowną analizę" sent: how many analyses the page had
    /// before, to tell once the new one is here (or came to nothing).
    @State private var analysingFrom: Int?
    /// "Popraw detale" sent: Claude is checking the details (until the
    /// server says it is done).
    @State private var mending = false
    /// The work's fragments (a scroll's parts, a Commons tile set), once
    /// asked; none for most works.
    @State private var fragments: FragmentsView?

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                // One over the other while the page fades in over its placeholder.
                ZStack(alignment: .top) { page }
                    // Full width from the first frame, also while loading: a
                    // lone spinner made the page (and its paper) a narrow strip.
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .animation(.easeOut(duration: 0.3), value: work == nil)
            }
            .glowLift($scrolled)
            .onChange(of: work) { _, work in
                if let work { DailyPeeks.keep(work, for: route) }
            }
            .onChange(of: work?.day) {
                guard let target = LaunchRoute.scroll else { return }  // CI screenshots: "composition", "details", "end"
                Task {
                    try? await Task.sleep(for: .seconds(1))
                    // "journey-end": the section's lower part.
                    let lower = target != "end" && target.hasSuffix("-end")
                    proxy.scrollTo(lower ? String(target.dropLast(4)) : target, anchor: target == "end" || lower ? .bottom : .top)
                }
            }
        }
        .paperPage(glow: glow, lift: scrolled)
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { pageWidth = $0 }
        .navigationTitle("Studium dzieła")
        .navigationBarTitleDisplayMode(.inline)
        // No title in the bar, only its buttons over the page (Mateusz
        // 2026-11-03); the title stays for the back button's menu and VoiceOver.
        .toolbar(removing: .title)
        .toolbar {
            if let card {
                ItemToolbar(
                    model: model, item: card, changed: { self.card = $0 },
                    addingToPlaylist: $addingToPlaylist, savingPhoto: $savingPhoto,
                    findingCopies: $findingCopies,
                    keepOwn: {
                        Task {
                            let id = card.id
                            do {
                                self.card = try await model.chooseCopy(itemID: id, copyID: id)
                                model.notices.done("Przywrócono zdjęcie muzeum")
                            } catch {
                                model.show(error)
                            }
                        }
                    },
                    bringCopy: { bringingCopy = true }
                )
            }
        }
        .fileImporter(isPresented: $bringingCopy, allowedContentTypes: [.image]) { result in
            guard case let .success(url) = result, let id = card?.id else { return }
            Task {
                model.notices.info("Wczytuję kopię…")
                do {
                    self.card = try await model.bringCopy(itemID: id, from: url, origin: "Alamy")
                    model.notices.info("Zdjęcie podmienione")
                } catch {
                    if !error.isCancellation { model.show(error) }
                }
            }
        }
        .task(id: route) {
            await load()
            await followLegacy()
        }
        .task(id: work?.item.id) { await loadCard() }
        .task(id: work?.item.id) { await loadFragments() }
        .sheet(isPresented: $addingToPlaylist) {
            if let card { AddToPlaylistSheet(item: card) }
        }
        .sheet(isPresented: $findingCopies) {
            if let card {
                CopiesSheet(item: card) { updated in
                    self.card = updated
                    model.notices.done("Zdjęcie podmienione", "Ramka pokaże je przy następnej zmianie.")
                }
            }
        }
        .onAppear {
            if let id = route.study { model.studyOpened(itemID: id) }
        }
        .fullScreenCover(isPresented: $zoomed) {
            if let work {
                OriginalViewer(item: work.item.item)
                    .navigationTransition(.zoom(sourceID: "picture", in: zoomSpace))
            }
        }
        .fullScreenCover(isPresented: $cropping) {
            if let work {
                CropScreen(
                    itemID: work.item.id, preview: previewRef,
                    aspectRatio: model.isPortrait ? 9.0 / 16.0 : 16.0 / 9.0,
                    placeholder: work.item.item.placeholderColor,
                    onFrame: model.player?.current?.item?.id == work.item.id,
                    draft: $draft, save: saveCrop, home: cropHome, previewLoaded: loadedPreview,
                    onOpen: { cropAway = true }, onClose: { cropping = false }, homeGrow: cropGrow
                )
            }
        }
        .task(id: cropKey) { await loadFraming() }
        .task(id: work?.compositionPending == true || analysingFrom != nil) { await followAnalysis() }
        .task(id: work?.detailsPending == true || mending) { await followMending() }
    }

    @ViewBuilder
    private var page: some View {
        if work != nil || !failed {
            // The picture stays put while the page fades in under it: the
            // placeholder's thumbnail and the page's picture, faded one over
            // the other, blinked it.
            // The label 12 pt under the picture (6 here, 6 its own).
            VStack(alignment: .leading, spacing: 6) {
                picture(work)
                ZStack(alignment: .top) {
                    if let work {
                        content(work)
                            .transition(.opacity)
                    } else {
                        loading
                            .transition(.opacity)
                    }
                }
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 40)
        } else {
            VStack(spacing: 16) {
                EmptyStateView(
                    title: "Nie ma jeszcze studium",
                    message: route.study == nil
                        ? "Serwer nie ma studium na ten dzień."
                        : "Przygotuj je na karcie dzieła, pod opisem.",
                    systemImage: "photo.fill"
                )
                Button("Spróbuj ponownie", systemImage: "arrow.clockwise") {
                    Task { await load() }
                }
                .buttonStyle(ActionButtonStyle(wide: false))
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 80)
        }
    }

    /// The colours glowing at the top: those of the tile or card it was
    /// opened from until the page is here, so the glow is there from the
    /// first frame instead of coming in with the page (a blink at the top).
    private var glow: [ColorSwatch] {
        for colors in [work?.item.item.colors, card?.colors, peek?.item.colors] {
            if let colors, !colors.isEmpty { return colors }
        }
        return peek.map { PageGlow.colours(of: $0.thumb, backend: model.backend) } ?? []
    }

    // MARK: Loading

    /// What is known of the page before it loads: the card of "Studia
    /// dzieł" it was opened from, or the work's card.
    private var peek: DailyPeeks.Peek? {
        guard let id = route.study else { return nil }
        if let brief = model.studyList?.first(where: { $0.id == id }) {
            return DailyPeeks.Peek(
                item: brief.item.item, title: brief.title, thumb: brief.item.thumb, fallback: brief.item.thumbFallback
            )
        }
        if let item = ItemPeeks.cards[id] {
            return DailyPeeks.Peek(
                item: item, title: item.title, thumb: ItemPeeks.tiles[id]?.thumb ?? .thumb(id), fallback: nil
            )
        }
        return nil
    }

    /// The page under the picture before it is here, laid out as it will
    /// be: the title when known, else quiet shapes, and the text's place
    /// breathing.
    private var loading: some View {
        let peek = peek
        return VStack(alignment: .leading, spacing: 26) {
            Group {
                if let peek {
                    // The artist alone: the date in Polish comes with the page.
                    StudyLabel(
                        title: peek.title.isEmpty ? "Bez tytułu" : peek.title,
                        byline: StudyLabel.byline(peek.item, date: "")
                    )
                } else {
                    TitleSkeleton().padding(.top, 8)
                }
            }
            VStack(alignment: .leading, spacing: 9) {
                ForEach(0 ..< 5, id: \.self) { line in
                    Capsule().fill(Theme.mat).frame(height: 10)
                        .padding(.trailing, line == 4 ? 120 : CGFloat(line % 2) * 18)
                }
            }
            .breathing()
            .accessibilityHidden(true)
            HStack(spacing: 8) {
                ProgressView().controlSize(.small)
                Text("Wczytuję studium…")
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
            }
        }
    }

    private func load() async {
        failed = false
        if let id = route.study {
            await loadStudy(id)
            // A server from before the day's page became the work's study.
            if work == nil, route.day != nil {
                failed = false
                await loadDay()
            }
            return
        }
        await loadDay()
    }

    /// The work for the heart and "…": the page's copy at once, then the
    /// server's (the page's may be from before a heart was given).
    private func loadCard() async {
        guard let work else { return }
        if card?.id != work.item.id { card = work.item.item }
        if let fresh = try? await model.backend.item(id: work.item.id) {
            card = fresh
            model.pictureSeen(fresh.id, copy: fresh.sharper?.itemId ?? "")
        }
    }

    /// Today's as Discover has it (another day's as last seen), then fresh;
    /// a page being written is waited for a few times.
    private func loadDay() async {
        if route.day == nil, let shown = model.daily { work = shown }
        if let day = route.day, work == nil { work = DailyPeeks.days[day] }
        for attempt in 0..<5 {
            do {
                let fresh = try await model.backend.daily(day: route.day, wait: attempt == 0 ? 0 : 60)
                work = fresh
                if route.day == nil { model.daily = fresh }
                guard fresh.writing else { return }
            } catch {
                if work == nil {
                    failed = true
                    if !error.isCancellation { model.show(error) }
                }
                return
            }
        }
    }

    /// The later works' pictures, looked up in the museums by the server
    /// once the page is written: asked for again a few times while they are.
    private func followLegacy() async {
        for _ in 0..<6 {
            guard work?.legacyPending == true else { return }
            try? await Task.sleep(for: .seconds(5))
            if Task.isCancelled { return }
            let fresh: DailyWork?
            if let id = route.study, route.day == nil || work?.day.isEmpty == true {
                fresh = try? await model.backend.study(itemID: id, wait: 0).work
            } else {
                fresh = try? await model.backend.daily(day: route.day, wait: 0)
            }
            guard let fresh else { return }
            work = fresh
            if route.day == nil, route.study == nil { model.daily = fresh }
        }
    }

    /// A study, as the card last heard it (or as last seen), then fresh;
    /// one still on its way (its card at the bottom says how far) is waited
    /// for. The text first, which the server has at once; the lists under
    /// it (similar works, what it led to, other works by the artist), which
    /// take it a few seconds, with the next answer.
    private func loadStudy(_ id: String) async {
        if let shown = model.studies[id]?.work ?? DailyPeeks.studies[id] { work = shown }
        for attempt in 0..<12 {
            do {
                let view = try await model.backend.study(itemID: id, wait: attempt == 0 ? 0 : 25, lists: false)
                if let fresh = view.work {
                    show(fresh)
                    break
                }
                guard view.isPending else { break }
            } catch {
                if work == nil, !error.isCancellation { model.show(error) }
                break
            }
        }
        guard work != nil else {
            failed = true
            return
        }
        // A server from before the text came apart sends the whole page.
        guard work?.partial == true else { return }
        do {
            if let whole = try await model.backend.study(itemID: id, wait: 0).work { work = whole }
        } catch {
            if !error.isCancellation { work?.partial = nil }  // no lists, and no spinner for them
        }
    }

    /// The page's text, fresh; the lists already on the page stay until
    /// the fresh ones come.
    private func show(_ fresh: DailyWork) {
        // The size found while the page is open (a work studied before the
        // sizes were looked up, once) fades in instead of jumping in.
        if let shown = work, shown.item.id == fresh.item.id,
           (shown.size == nil && fresh.size != nil) || (shown.journey == nil && fresh.journey != nil) {
            withAnimation(.easeOut(duration: 0.4)) { merge(fresh) }
        } else {
            merge(fresh)
        }
    }

    private func merge(_ fresh: DailyWork) {
        guard fresh.partial == true, let shown = work, shown.item.id == fresh.item.id, shown.partial != true else {
            work = fresh
            return
        }
        var merged = fresh
        merged.similar = shown.similar
        merged.legacy = shown.legacy
        merged.byArtist = shown.byArtist
        merged.sameTime = shown.sameTime
        if merged.size == nil { merged.size = shown.size }
        if merged.journey == nil { merged.journey = shown.journey }
        work = merged
    }

    /// Whether the lists under the text are still to come.
    private func listsComing(_ work: DailyWork) -> Bool {
        work.partial == true && work.similar.isEmpty && work.legacy.isEmpty && (work.byArtist ?? []).isEmpty
            && (work.sameTime ?? []).isEmpty
    }

    @ViewBuilder
    private func content(_ work: DailyWork) -> some View {
        // A little more air after each section (Mateusz 2026-11-03); a
        // little less after the title's label.
        VStack(alignment: .leading, spacing: 24) {
            VStack(alignment: .leading, spacing: 14) {
                header(work)
                if !work.whyToday.isEmpty { whyToday(work.whyToday) }
                if work.writing {
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.small)
                        Text("Claude pisze opis i analizę kompozycji…")
                            .font(.footnote)
                            .foregroundStyle(Theme.inkSoft)
                    }
                }
            }
            VStack(alignment: .leading, spacing: 36) {
                if !work.context.isEmpty {
                    section(work.headline ?? "Co mówi muzeum") {
                        ForEach(Array(work.context.enumerated()), id: \.offset) { _, paragraph in
                            prose(paragraph)
                        }
                    }
                }
                // Also over the museum's text alone: the only place the artist is named.
                if !(work.artist ?? "").isEmpty || !Names.person(work.item.item.artist).isEmpty {
                    author(work, work.artist ?? "").id("author")
                }
                if let takes = work.composition?.takes, !takes.isEmpty {
                    compositionSection(work, takes).id("composition")
                }
                if !work.colour.isEmpty || !work.item.item.colors.isEmpty || !(work.pigments ?? []).isEmpty {
                    section("Kolor i światło") {
                        // Painted in the work's own technique (Mateusz
                        // 2026-11-11 11:09: „tak żeby paleta odpowiadała
                        // rzeczywistej technice dzieła”): oil, watercolour
                        // or pastel; a print or a drawing in its lines or
                        // its inks (2026-11-12 07:26); any other keeps
                        // the flat palette.
                        let item = work.item.item
                        let style = PaintStyle.of(item)
                        let strokes = style == nil ? 0 : PaintedStrip.shares(item.colors).count
                        if !item.colors.isEmpty {
                            if let style, strokes > 0 {
                                PaintedStrip(swatches: item.colors, style: style, seed: Paint.seed(item.id),
                                             began: { painted[item.id] = ($0, $1) }, relief: Paint.relief(item))
                            } else {
                                PaletteStrip(swatches: item.colors, height: 26, cornerRadius: 6)
                            }
                        }
                        if !work.colour.isEmpty { prose(work.colour) }
                        if let pigments = work.pigments, !pigments.isEmpty {
                            // The paints begin while the bar is painted; with no bar, at once.
                            self.pigments(pigments, style: style, seed: Paint.seed(item.id), relief: Paint.relief(item),
                                          began: strokes > 0 ? painted[item.id]?.at : .distantPast,
                                          bar: strokes > 0 ? painted[item.id]?.takes ?? 0 : 0)
                        }
                    }
                    .id("colour")
                }
                if let details = work.details, !details.isEmpty {
                    detailsSection(work, details).id("details")
                }
                // After "Detale", ahead of the size (Mateusz 2026-11-09).
                // A tile set is looked at in full screen, not listed.
                if let fragments, !fragments.fragments.isEmpty, !fragments.tiled {
                    fragmentsSection(work, fragments.fragments)
                        .id("fragments")
                        .transition(.opacity)
                }
                // Right after "Detale", ahead of the lists (Mateusz 2026-11-03).
                if let size = work.size, size.height > 0, size.width > 0 {
                    section("Rozmiar obrazu") {
                        RealSizeDrawing(work: work.item, height: size.height, width: size.width, column: columnWidth)
                            .padding(.top, 4)
                    }
                    .id("size")
                    // A work studied before the sizes were looked up gets its
                    // size a moment later, once: it fades in, no jump.
                    .transition(.opacity)
                }
                // "Droga dzieła" (Mateusz 2026-11-10, "S1"), after the size
                // (15:21; not "Losy dzieła", next to "Dalsze losy"): looked up
                // when the page first opens, so it fades in.
                // "Dalsze losy" right under it, as the road going on
                // (Mateusz 2026-11-11 10:20: „dodać sekcje „Dalsze losy”
                // jako kontynuację linii Drogi dzieła… Na pewno zostawiamy
                // nagłówek sekcji Dalsze losy”): the road draws that
                // section itself, heading and all. A work with no road
                // keeps the plain time line, in the same place.
                if let journey = work.journey, journey.stops.count >= 2 {
                    section("Droga dzieła") {
                        JourneyRoad(journey: journey, seed: work.item.item.id, later: work.legacy,
                                    told: { AnyView(laterTold($0)) })
                    }
                    .id("journey")
                    .transition(.opacity)
                } else if !work.legacy.isEmpty {
                    section("Dalsze losy") { legacy(work.legacy) }.id("legacy")
                }
                if !similarWorks(work).isEmpty { section("Podobne dzieła") { similar(similarWorks(work)) } }
                if let others = work.byArtist, !others.isEmpty {
                    section("Inne prace artysty") { byArtist(Array(others.prefix(Self.byArtistShown))) }.id("artist")
                }
                if let then = work.sameTime, !then.isEmpty {
                    section("Inni w tym samym czasie") { sameTime(then) }.id("sametime")
                }
                if listsComing(work) {
                    HStack(spacing: 8) {
                        ProgressView().controlSize(.small)
                        Text("Wczytuję podobne i inne prace artysty…")
                            .font(.footnote)
                            .foregroundStyle(Theme.inkSoft)
                    }
                    .transition(.opacity)
                }
                section("Na Twojej ramce") { onFrame(work) }
                footer(work).id("end")
            }
        }
    }

    // MARK: Top

    private func aspect(_ item: Item) -> CGFloat {
        guard let width = item.width, let height = item.height, width > 0, height > 0 else { return 1.5 }
        return CGFloat(width) / CGFloat(height)
    }

    /// The picture's box: the page's whole width (less its margins) and
    /// as tall as the picture's shape makes it. Sized from the page itself,
    /// not from what the column around it holds yet: laid out by the shape
    /// alone it loaded narrower than the page and sometimes stayed so.
    @ViewBuilder
    private func pictureBox(_ ratio: CGFloat) -> some View {
        let width = pageWidth - 2 * Theme.gutter
        if width > 0 {
            Color.clear.frame(width: width, height: width / ratio)
        } else {
            Color.clear.frame(maxWidth: .infinity).aspectRatio(ratio, contentMode: .fit)
        }
    }

    /// The picture on the page's whole width; tapping it opens it on the
    /// whole screen to zoom into, as on the work's card. Before the page is
    /// here, the thumbnail of the tile or card it was opened from; the
    /// original, once the page is, fades in over it (as on the card, and
    /// from memory at once when the card showed it).
    private func picture(_ work: DailyWork?) -> some View {
        let peek = peek
        let under = peek?.thumb ?? work?.item.thumb
        let underFallback = peek != nil ? peek?.fallback : work?.item.thumbFallback
        let item = work?.item.item ?? peek?.item
        return pictureBox(item.map { aspect($0) } ?? 1.5)
            .overlay {
                if let under {
                    ArtImage(
                        ref: under, fallback: underFallback, placeholder: item?.placeholderColor ?? Theme.mat,
                        maxPixel: 700, priority: .high, brighten: true
                    )
                } else {
                    Rectangle().fill(Theme.mat).breathing()
                }
            }
            .overlay {
                if let work {
                    ArtImage(
                        ref: work.item.inLibrary ? originalRef(work) : work.item.thumb,
                        fallback: .thumb(work.item.id),
                        placeholder: .clear,
                        maxPixel: Self.originalPixels,
                        priority: .high,
                        crossfade: true,
                        brighten: true
                    )
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
            // The whole screen grows out of it ("pop").
            .matchedTransitionSource(id: "picture", in: zoomSpace) {
                $0.clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
            }
            .picturePress(enabled: work != nil) { zoomed = true }
            .accessibilityAddTraits(work != nil ? .isButton : [])
            .accessibilityHint(Text(work != nil ? "Otwiera obraz na całym ekranie" : ""))
            .padding(.top, 6)
    }

    /// As the work's card asks for its original, so the one it showed is
    /// the one in memory here.
    static let originalPixels: CGFloat = 1800

    /// The work's original; the sharper copy its card found since the study
    /// was written, too, so the study shows the picture the card did.
    private func originalRef(_ work: DailyWork) -> ImageRef {
        let item = work.item.item
        if item.sharper == nil, let card = ItemPeeks.cards[item.id] ?? self.card, card.id == item.id, card.sharper != nil {
            return card.originalRef
        }
        return item.originalRef
    }

    /// The title under the picture, the artist and the date under it, in
    /// letters only (Mateusz 2026-11-03).
    private func header(_ work: DailyWork) -> some View {
        let item = work.item.item
        let original = OriginalTitle.of(item.title, shown: work.title)
        return StudyLabel(
            title: peeking ? original ?? work.title : work.title,
            byline: StudyLabel.byline(item, date: work.date),
            peekable: original != nil,
            peeking: $peeking,
            onArtist: item.artist.isEmpty ? nil : { model.artistSearch = item.artist }
        )
    }

    /// "Pokaż na ramce" (held: for longer), at the end by "Na Twojej ramce".
    private func showButton(_ work: DailyWork) -> some View {
        // Sent while the frame sleeps: says when it shows until it does.
        let waiting = sending ? nil : model.waitingLabel(for: work.item.id)
        return Button {
            Task { await show(work, .untilNextChange) }
        } label: {
            Label {
                Text(sending ? "Wysyłam…" : waiting ?? (sent == true ? "Wysłano" : "Pokaż na ramce"))
            } icon: {
                if sending {
                    ProgressView().tint(Theme.paper)
                } else {
                    Image(systemName: waiting != nil ? "clock" : sent == true ? "checkmark" : "photo.fill")
                }
            }
        }
        .buttonStyle(ActionButtonStyle(prominent: true))
        .labelButtonMenu {
            ForEach(HoldSpec.allCases) { spec in
                Button(spec.label) { Task { await show(work, spec) } }
            }
        }
        .disabled(sending)
        .sensoryFeedback(.impact(weight: .medium), trigger: sending) { _, now in now }
    }

    /// "Dodaj do kolejki": shown at the next change; once it is first in
    /// line, the button says so.
    private func queueButton(_ work: DailyWork) -> some View {
        let next = model.player?.queued?.first == work.item.id
        return Button {
            queueTaps += 1
            Task { await model.queueNext(itemID: work.item.id) }
        } label: {
            Label(next ? "Następne na ramce" : "Dodaj do kolejki", systemImage: next ? "checkmark" : QueueButton.symbol)
                .contentTransition(.symbolEffect(.replace))
        }
        .buttonStyle(ActionButtonStyle())
        .disabled(next)
        .sensoryFeedback(.impact(weight: .light), trigger: queueTaps)
    }

    private func show(_ work: DailyWork, _ hold: HoldSpec) async {
        sending = true
        sent = nil
        sent = await model.show(itemID: work.item.id, hold: hold)
        sending = false
        guard sent == true else { return }
        try? await Task.sleep(for: .seconds(2.5))
        sent = nil
    }

    /// "Dlaczego dziś" on a slip of paper: white in the light style, black
    /// in the dark one, lifted a little off the page.
    private func whyToday(_ text: String) -> some View {
        let shape = RoundedRectangle(cornerRadius: 10, style: .continuous)
        return VStack(alignment: .leading, spacing: 5) {
            Eyebrow("Dlaczego dziś", color: Theme.inkSoft)
            prose(text, size: 15)
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background {
            shape.fill(Self.slip).shadow(color: .black.opacity(0.08), radius: 6, y: 2)
        }
        .overlay(shape.strokeBorder(Theme.hairline.opacity(0.7)))
    }

    private static let slip = Color(light: 0xFFFFFF, dark: 0x000000)

    // MARK: Sections

    private func section<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.serif(20, weight: .semibold))
                .foregroundStyle(Theme.ink)
            content()
        }
    }

    /// "O autorze" with the artist's name in it, plain and large, first
    /// name first ("Gogh, Vincent van" is Vincent van Gogh here), and the
    /// years of their life when the museum gives them; then the note.
    /// Held, the name looks for their other works on Szukaj, as the line
    /// under the title does.
    private func author(_ work: DailyWork, _ note: String) -> some View {
        let item = work.item.item
        let name = Names.person(item.artist)
        let life = lifeSpan(work).map { "\($0.born)–\($0.died)" }
        return VStack(alignment: .leading, spacing: 10) {
            if name.isEmpty {
                Text("O autorze")
                    .font(.serif(20, weight: .semibold))
                    .foregroundStyle(Theme.ink)
            } else {
                VStack(alignment: .leading, spacing: 3) {
                    Eyebrow("O autorze")
                    // In the pencil's hand, as the composition's notes
                    // (Mateusz 2026-11-03; then 40% larger).
                    Text(name)
                        .font(.hand(35))
                        .foregroundStyle(Theme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                        .artistPress { model.artistSearch = item.artist }
                    if let life {
                        Text(life)
                            .font(.subheadline)
                            .monospacedDigit()
                            .foregroundStyle(Theme.inkSoft)
                    }
                }
                .accessibilityElement(children: .combine)
            }
            if !note.isEmpty { prose(note) }
            // After the note (Mateusz 2026-11-03), each mark named under it.
            if let span = lifeSpan(work) {
                LifeLine(
                    born: span.born, died: span.died,
                    work: item.year.map { LifeLine.Work(year: $0, title: work.title) },
                    milestones: work.milestones ?? [],
                    events: work.events ?? []
                )
                .padding(.top, 6)
            }
        }
    }

    /// The artist's years: the server's (the museum's line about them, else
    /// the page's), else read from the line or the name here (older servers).
    private func lifeSpan(_ work: DailyWork) -> (born: Int, died: Int)? {
        if let born = work.born, let died = work.died, died > born { return (born, died) }
        let item = work.item.item
        return Names.life(item.artistBio) ?? Names.life(item.artist)
    }

    /// The paints the work is made with: each on its own swatch, its name,
    /// where it is in the picture and a line about it.
    /// `style`: the work's technique, each swatch painted in it (nil: a
    /// plain round one); `began`: when the palette bar's first stroke
    /// began (nil: not yet) and `bar`: how long its paint takes from
    /// then (0: no bar), the swatches after that; `relief`: how high
    /// an oil paint stands.
    private func pigments(_ pigments: [DailyWork.Pigment], style: PaintStyle? = nil, seed: Int = 0,
                          relief: Double = Paint.calm.plain, began: Date? = nil, bar: Double = 0) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Array(pigments.enumerated()), id: \.element.name) { index, pigment in
                HStack(alignment: .top, spacing: 12) {
                    Group {
                        if let style {
                            let lead = style.swatchDelay(bar: bar, index: index)
                            PaintedSwatch(hex: pigment.hex, index: index, style: style, seed: seed,
                                          after: began?.addingTimeInterval(lead), lead: lead, relief: relief)
                        } else {
                            Circle()
                                .fill(Color(hexString: pigment.hex) ?? Theme.mat)
                                .overlay(Circle().strokeBorder(.black.opacity(0.12), lineWidth: 0.5))
                        }
                    }
                    // A likely paint, not one the sources name: a dashed ring round
                    // the plain swatch. A painted one has no ring (Mateusz 2026-11-11
                    // 13:44: „kropki niepewnych kolorów bez przerywanego okręgu
                    // dookoła”) and is as big as a sure one (18:39: „zawsze duże
                    // (nawet gdy niepewne)”): its line says how sure it is.
                    .overlay {
                        if pigment.sure == false, style == nil {
                            Circle()
                                .strokeBorder(Theme.inkSoft, style: StrokeStyle(lineWidth: 1, dash: [2.5, 2]))
                                .padding(-3)
                        }
                    }
                    .frame(width: 26, height: 26)
                    .padding(.top, 1)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(pigment.name)
                            .font(.serif(15, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                        let line = [pigment.`where`, pigment.text].filter { !$0.isEmpty }.joined(separator: ". ")
                        if !line.isEmpty {
                            Text(line)
                                .font(.serif(14))
                                .foregroundStyle(Theme.inkSoft)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
                .accessibilityElement(children: .combine)
            }
        }
        .padding(.top, 4)
    }

    private func prose(_ text: String, size: CGFloat = 16) -> some View {
        Text(text)
            .font(.serif(size))
            .lineSpacing(3)
            .foregroundStyle(Theme.ink.opacity(0.9))
            .fixedSize(horizontal: false, vertical: true)
    }

    /// The take as pencil over the picture in full colour ("Analiza
    /// kompozycji"; chips to switch only when an older server sends more
    /// than one); the take's text under it in the page's own type. The
    /// owner holds the title for a menu: the analysis made anew, and once
    /// there are several, the one the page shows (Mateusz 2026-11-03).
    private func compositionSection(_ work: DailyWork, _ takes: [DailyWork.Take]) -> some View {
        let shown = takes[min(take, takes.count - 1)]
        return VStack(alignment: .leading, spacing: 10) {
            compositionTitle(work)
            if work.compositionPending == true || analysingFrom != nil {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Claude analizuje kompozycję od nowa…")
                        .font(.footnote)
                        .foregroundStyle(Theme.inkSoft)
                }
                .transition(.opacity)
            }
            if takes.count > 1 {
                HStack(spacing: 6) {
                    ForEach(Array(takes.enumerated()), id: \.offset) { index, each in
                        let on = index == min(take, takes.count - 1)
                        Button {
                            withAnimation(.easeInOut(duration: 0.2)) { take = index }
                        } label: {
                            Text(each.title)
                                .font(.caption.weight(.semibold))
                                .padding(.horizontal, 11)
                                .padding(.vertical, 6)
                                .foregroundStyle(on ? Theme.paper : Theme.inkSoft)
                                .background(on ? Theme.ink : Theme.card, in: Capsule())
                                .overlay(Capsule().strokeBorder(on ? Color.clear : Theme.hairline))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            // The sheet is made for the first take's field: a take with
            // another field (older analyses had two) goes on the picture.
            CompositionSketch(
                item: work.item, aspect: aspect(work.item.item), take: shown,
                sheet: shown.field == takes.first?.field ? work.compositionSheet ?? "" : "",
                layers: work.compositionLayers == true,
                bleed: CGFloat(work.compositionBleed ?? 0),
                width: pageWidth > 0 ? pageWidth - 2 * Theme.gutter : nil
            )
                .padding(.top, 4)
            if !shown.text.isEmpty { prose(shown.text, size: 15) }
        }
        .animation(.easeOut(duration: 0.25), value: work.compositionPending == true || analysingFrom != nil)
    }

    /// "Analiza kompozycji": for the owner, held, a menu to make it anew
    /// and to pick among the analyses made; for the household, a title.
    @ViewBuilder
    private func compositionTitle(_ work: DailyWork) -> some View {
        let title = Text("Analiza kompozycji")
            .font(.serif(20, weight: .semibold))
            .foregroundStyle(Theme.ink)
        if model.isOwner, work.written, work.compositionVersions != nil {
            title
                .contentShape(.contextMenuPreview, RoundedRectangle(cornerRadius: 8, style: .continuous))
                .contextMenu { compositionMenu(work) }
                .accessibilityAction(named: "Wykonaj ponowną analizę") { analyseAgain(work) }
        } else {
            title
        }
    }

    @ViewBuilder
    private func compositionMenu(_ work: DailyWork) -> some View {
        let versions = work.compositionVersions ?? []
        let busy = work.compositionPending == true || analysingFrom != nil
        Button("Wykonaj ponowną analizę", systemImage: "arrow.clockwise") { analyseAgain(work) }
            .disabled(busy)
        if versions.count > 1 {
            Section("Wersje analizy") {
                ForEach(Array(versions.enumerated()).reversed(), id: \.offset) { index, version in
                    let label = ["Analiza \(index + 1)", When.past(version.made)].compactMap { $0 }.joined(separator: " · ")
                    Button {
                        pickAnalysis(work, index)
                    } label: {
                        if version.shown { Label(label, systemImage: "checkmark") } else { Text(label) }
                    }
                }
            }
        }
    }

    /// Asks the server for the analysis anew; the page shows it is on its
    /// way (minutes: Claude looks long) and follows it (`followAnalysis`).
    private func analyseAgain(_ work: DailyWork) {
        let before = max((work.compositionVersions ?? []).count, 1)
        Task {
            do {
                _ = try await model.backend.compositionAgain(itemID: work.item.id)
                analysingFrom = before
                await refreshPage()
            } catch {
                model.show(error)
            }
        }
    }

    /// The owner's pick: the page shows that analysis from now on.
    private func pickAnalysis(_ work: DailyWork, _ index: Int) {
        guard work.compositionVersions?.indices.contains(index) == true,
              work.compositionVersions?[index].shown != true else { return }
        Task {
            do {
                _ = try await model.backend.pickComposition(itemID: work.item.id, shown: index)
                take = 0
                await refreshPage()
            } catch {
                model.show(error)
            }
        }
    }

    /// While the analysis asked for anew is being made: asked after every
    /// few seconds, the page fetched again once it is here.
    private func followAnalysis() async {
        guard let id = work?.item.id, work?.compositionPending == true || analysingFrom != nil else { return }
        for _ in 0..<120 {  // ten minutes; the page says it is still on its way after
            try? await Task.sleep(for: .seconds(5))
            if Task.isCancelled { return }
            guard let state = try? await model.backend.compositionState(itemID: id) else { continue }
            guard !state.pending else { continue }
            let before = analysingFrom
            await refreshPage()
            analysingFrom = nil
            if let before {
                if state.versions > before {
                    model.notices.done("Nowa analiza kompozycji")
                } else {
                    model.notices.fail("Nie udało się wykonać analizy", "Poprzednia analiza zostaje.")
                }
            }
            return
        }
        analysingFrom = nil
    }

    /// The page's text fetched again (the lists on it stay).
    private func refreshPage() async {
        let fresh: DailyWork?
        if let id = route.study, route.day == nil || work?.day.isEmpty == true {
            fresh = try? await model.backend.study(itemID: id, wait: 0, lists: false).work
        } else {
            fresh = try? await model.backend.daily(day: route.day, wait: 0, lists: false)
        }
        guard let fresh else { return }
        withAnimation(.easeInOut(duration: 0.25)) { show(fresh) }
        if route.day == nil, route.study == nil, let work { model.daily = work }
    }

    /// "Detale"; the owner holds the title for "Popraw detale" (Mateusz
    /// 2026-11-03: "Na żądanie, przytrzymaniem"): Claude checks each
    /// fragment over its cut and draws anew a box that misses.
    private func detailsSection(_ work: DailyWork, _ details: [DailyWork.Detail]) -> some View {
        let busy = work.detailsPending == true || mending
        return VStack(alignment: .leading, spacing: 10) {
            detailsTitle(work, busy: busy)
            if busy {
                HStack(spacing: 8) {
                    ProgressView().controlSize(.small)
                    Text("Claude sprawdza kadry detali…")
                        .font(.footnote)
                        .foregroundStyle(Theme.inkSoft)
                }
                .transition(.opacity)
            }
            self.details(work, details)
        }
        .animation(.easeOut(duration: 0.25), value: busy)
    }

    @ViewBuilder
    private func detailsTitle(_ work: DailyWork, busy: Bool) -> some View {
        let title = Text("Detale")
            .font(.serif(20, weight: .semibold))
            .foregroundStyle(Theme.ink)
        // Servers before 1.92.0 send no `detailsPending`: nothing to hold.
        if model.isOwner, work.written, work.detailsPending != nil {
            title
                .contentShape(.contextMenuPreview, RoundedRectangle(cornerRadius: 8, style: .continuous))
                .contextMenu {
                    Button("Popraw detale", systemImage: "crop") { mendDetails(work) }
                        .disabled(busy)
                }
                .accessibilityAction(named: "Popraw detale") { mendDetails(work) }
        } else {
            title
        }
    }

    /// Asks the server to check the details; the page shows it is on its
    /// way and follows it (`followMending`).
    private func mendDetails(_ work: DailyWork) {
        Task {
            do {
                _ = try await model.backend.detailsAgain(itemID: work.item.id)
                mending = true
                await refreshPage()
            } catch {
                model.show(error)
            }
        }
    }

    /// While the details are being checked: asked after every few seconds,
    /// the page fetched again once they are done (the fragments cut anew).
    private func followMending() async {
        guard let id = work?.item.id, work?.detailsPending == true || mending else { return }
        for _ in 0..<60 {  // five minutes
            try? await Task.sleep(for: .seconds(5))
            if Task.isCancelled { return }
            guard let state = try? await model.backend.detailsState(itemID: id) else { continue }
            guard !state.pending else { continue }
            let asked = mending
            await refreshPage()
            mending = false
            if asked {
                switch state.moved {
                case nil:
                    model.notices.fail("Nie udało się sprawdzić detali", "Detale zostają jak były.")
                case let moved? where moved.isEmpty:
                    model.notices.done("Detale są dobrze wykadrowane")
                case let moved?:
                    let count = BatteryText.count(Double(moved.count), one: "detal", few: "detale", many: "detali")
                    model.notices.done("Poprawiono \(count)", moved.joined(separator: ", "))
                }
            }
            return
        }
        mending = false
    }

    private func loadFragments() async {
        guard let id = work?.item.id else { return }
        let found = await Fragments.load(id, backend: model.backend)
        guard work?.item.id == id else { return }
        withAnimation(.easeOut(duration: 0.25)) { fragments = found }
    }

    /// The museum's own photographs of the work's parts, large, to swipe
    /// through as "Detale"; a tap opens a fragment's card, a hold sends it
    /// to the frame or the queue.
    private func fragmentsSection(_ work: DailyWork, _ parts: [RemoteItem]) -> some View {
        let scroll = work.item.item.source == "cma"
        return section(scroll ? "Fragmenty zwoju" : "Fragmenty") {
            prose(
                scroll
                    ? "Muzeum sfotografowało zwój w \(parts.count) częściach. Każdą można pokazać na ramce osobno, w pełnej ostrości."
                    : "Dzieło jest dostępne także w \(parts.count) kaflach w pełnej rozdzielczości. Każdy można pokazać na ramce osobno.",
                size: 15
            )
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 12) {
                    ForEach(Array(parts.enumerated()), id: \.element.id) { index, part in
                        let shape = CGFloat(max(0.75, min(2.6, part.summary.aspectRatio)))
                        NavigationLink(value: part.id) {
                            VStack(alignment: .leading, spacing: 5) {
                                ArtImage(ref: part.thumb, placeholder: part.item.placeholderColor, maxPixel: 1000, brighten: true)
                                    .frame(width: 170 * shape, height: 170)
                                    .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                                Text("Fragment \(index + 1) z \(parts.count)")
                                    .font(.caption)
                                    .foregroundStyle(Theme.inkSoft)
                            }
                        }
                        .buttonStyle(.plain)
                        .contextMenu {
                            Button("Pokaż na ramce", systemImage: "photo") {
                                Task { _ = await model.show(itemID: part.id, hold: .untilNextChange) }
                            }
                            Button("Dodaj do kolejki", systemImage: QueueButton.symbol) {
                                Task { await model.queueNext(itemID: part.id) }
                            }
                        }
                    }
                }
                .scrollTargetLayout()
            }
            .scrollTargetBehavior(.viewAligned)
            .scrollClipDisabled()
        }
    }

    /// Fragments cut from the original, side by side to swipe through (the
    /// next one peeks in from the right), each with its title and a line or two.
    private func details(_ work: DailyWork, _ details: [DailyWork.Detail]) -> some View {
        let item = work.item.item
        let whole = aspect(item)
        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(alignment: .top, spacing: 12) {
                ForEach(details, id: \.image) { detail in
                    let shape = max(0.75, min(1.34, whole * detail.w / max(detail.h, 0.01)))
                    let width = max(236, 250 * shape)
                    VStack(alignment: .leading, spacing: 3) {
                        Color.clear
                            .frame(width: width, height: 250)
                            .overlay {
                                ArtImage(ref: .path(detail.image), placeholder: item.placeholderColor, maxPixel: 1200, brighten: true)
                            }
                            .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                            .padding(.bottom, 5)
                        Text(detail.title)
                            .font(.serif(16, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                        if !detail.text.isEmpty { prose(detail.text, size: 15) }
                    }
                    .frame(width: width, alignment: .leading)
                }
            }
            .scrollTargetLayout()
        }
        .scrollTargetBehavior(.viewAligned)
        .scrollClipDisabled()
    }

    /// How the work fares on the frame, then the buttons to show or queue it.
    /// The frame drawn as on the work's card: across the page when it hangs
    /// landscape, beside the text when it hangs portrait.
    private func onFrame(_ work: DailyWork) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            if model.isPortrait {
                HStack(alignment: .top, spacing: 14) {
                    if work.item.inLibrary { framePreview(work, width: 0.42 * columnWidth) }
                    if !work.onFrame.isEmpty { prose(work.onFrame, size: 15) }
                }
            } else {
                if work.item.inLibrary { framePreview(work, width: columnWidth) }
                if !work.onFrame.isEmpty { prose(work.onFrame, size: 15) }
            }
            HStack(spacing: 12) {
                showButton(work)
                queueButton(work)
            }
            .labelStyle(ActionLabelStyle())
        }
    }

    /// The page's column, less its margins; a guess before the page is measured.
    private var columnWidth: CGFloat {
        pageWidth > 0 ? pageWidth - 2 * Theme.gutter : 340
    }

    /// The work framed as the frame will show it, in the frame's shape and
    /// at a size fixed here: sized by the picture inside a row of text, it
    /// was squeezed to a sliver of white with a small picture in it. With
    /// the settings in the address, so a turned frame or another
    /// presentation is a new picture, not the old one from memory.
    private func framePreview(_ work: DailyWork, width: CGFloat) -> some View {
        let ratio: CGFloat = model.isPortrait ? 9.0 / 16.0 : 16.0 / 9.0
        let ref = previewRef
        return FramedArtwork(ref: ref, aspectRatio: ratio, placeholder: work.item.item.placeholderColor)
        .environment(\.artImageLoaded) { loaded in
            guard loaded == previewRef else { return }
            loadedPreview = loaded
        }
        .frame(width: width, height: Moulding.height(width: width, aspect: ratio))
        // Under the crop screen's frame while it is open: that one flies.
        .opacity(cropping && cropAway ? 0 : 1)
        // Tap or hold (the phone taps closer and closer), as on Teraz and the card.
        .picturePress(enabled: canCrop) { held in
            cropGrow = held ? PressHold.pictureGrow : 1
            CropScreen.present {
                cropAway = false
                cropping = true
            }
        }
        // Cropping's frame comes out of it and goes back onto it. Out here,
        // so the place is the preview's own, not grown by the press.
        .onGeometryChange(for: CGRect.self) { $0.frame(in: .global) } action: { cropHome = $0 }
        .padding(.bottom, 6)  // room for the frame's shadow
        .accessibilityLabel(Text("Podgląd na ramce"))
        .accessibilityAddTraits(canCrop ? .isButton : [])
        .accessibilityHint(Text(canCrop ? "Otwiera kadrowanie na całym ekranie" : ""))
    }

    // MARK: Crop

    /// The work, orientation and presentation: a crop belongs to all three.
    private var cropKey: String {
        guard let work, work.item.inLibrary else { return "" }
        return [work.item.id, model.settings?.presentationKey ?? ""].joined(separator: "|")
    }

    /// The crop and its preview are loaded.
    private var canCrop: Bool {
        !cropKey.isEmpty && draft.key == cropKey && draft.view?.windows.isEmpty == false
            && previewRef != nil && loadedPreview == previewRef
    }

    /// With the settings in the address, so a turned frame or another
    /// presentation is a new picture, not the old one from memory; with the
    /// crop tried or saved here once there is one.
    private var previewRef: ImageRef? {
        guard let work else { return nil }
        let current = !cropKey.isEmpty && draft.key == cropKey
        return .framePreview(work.item.id, settings: model.settings, framing: current ? draft.trial ?? applied : nil)
    }

    /// The crop as the server has it, for the work and presentation shown.
    private func loadFraming() async {
        let key = cropKey
        guard !key.isEmpty, draft.key != key, let work else { return }
        draft = FramingDraft()
        applied = nil
        let orientation = model.settings?.orientation ?? "landscape"
        guard let loaded = await FramingDraft.load(model.backend, itemID: work.item.id, orientation: orientation, key: key),
              key == cropKey
        else { return }
        draft = loaded
    }

    /// "Zapisz kadr" on the crop screen; the picture on the frame now is
    /// redrawn with it there. False if it failed, so the screen stays.
    private func saveCrop() async -> Bool {
        guard let work, draft.key == cropKey, let change = draft.change else { return true }
        let itemID = work.item.id
        let onFrame = model.player?.current?.item?.id == itemID
        let key = draft.key
        do {
            let saved = try await model.applyFraming(itemID: itemID, change)
            guard key == draft.key else { return true }
            draft = FramingDraft(saved: saved, key: key)
            applied = draft.savedCrops
        } catch {
            model.show(error)
            return false
        }
        if onFrame {
            Task { await model.followPlayer() }  // the send bar shows the redraw
        } else {
            model.notices.done("Zapisano kadr")
        }
        return true
    }

    /// "Podobne dzieła" without the artist's own works, which are under
    /// "Inne prace artysty" (a server before 1.80 still sends them).
    private func similarWorks(_ work: DailyWork) -> [DailyWork.Similar] {
        let artist = work.item.item.artist
        guard !artist.isEmpty else { return work.similar }
        return work.similar.filter { $0.item.item.artist != artist }
    }

    /// Two to a row, as "Inne prace artysty".
    private static let gridColumns = [GridItem(.flexible(), spacing: 12, alignment: .top), GridItem(.flexible(), spacing: 12, alignment: .top)]
    /// "Inne prace artysty": two rows of two, as "Podobne dzieła".
    private static let byArtistShown = 4

    /// A work's picture in the two grids at the end: cropped to the tile
    /// around its faces (or what draws the eye), not through the middle,
    /// so a portrait keeps its head.
    private func gridPicture(_ work: RemoteItem, height: CGFloat = 124) -> some View {
        Color.clear
            .frame(height: height)
            .frame(maxWidth: .infinity)
            .overlay {
                ArtImage(
                    ref: work.thumb,
                    fallback: work.thumbFallback,
                    placeholder: work.item.placeholderColor,
                    maxPixel: 500,
                    subjectFocus: true
                )
            }
            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
    }

    private func similar(_ works: [DailyWork.Similar]) -> some View {
        LazyVGrid(columns: Self.gridColumns, alignment: .leading, spacing: 16) {
            ForEach(works, id: \.item.id) { work in
                NavigationLink(value: work.item.id) {
                    VStack(alignment: .leading, spacing: 4) {
                        gridPicture(work.item)
                        Text(work.item.item.title)
                            .font(.serif(14, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                            .lineLimit(2)
                            .multilineTextAlignment(.leading)
                        Text([Names.artist(work.item.item.artist), work.item.item.dateText].filter { !$0.isEmpty }.joined(separator: ", "))
                            .font(.caption)
                            .foregroundStyle(Theme.inkSoft)
                            .lineLimit(1)
                        if !work.why.isEmpty {
                            // A quiet note, like a pencilled line beside a
                            // museum label: italic serif in soft ink behind
                            // a thin rule, no colour and no chip.
                            Text(work.why)
                                .font(.serif(13).italic())
                                .foregroundStyle(Theme.inkSoft)
                                .multilineTextAlignment(.leading)
                                .fixedSize(horizontal: false, vertical: true)
                                .padding(.leading, 7)
                                .overlay(alignment: .leading) {
                                    Rectangle().fill(Theme.hairline).frame(width: 1.5)
                                }
                                .padding(.top, 2)
                        }
                    }
                    .frame(maxHeight: .infinity, alignment: .top)
                }
                .buttonStyle(.plain)
            }
        }
    }

    /// Later works on a line through time, each with its picture when the
    /// catalogue or a museum has it (opening its card).
    private func legacy(_ entries: [DailyWork.Legacy]) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(entries.enumerated()), id: \.offset) { index, entry in
                HStack(alignment: .top, spacing: 12) {
                    VStack(spacing: 0) {
                        Circle()
                            .strokeBorder(Theme.vermilion, lineWidth: 2)
                            .frame(width: 11, height: 11)
                            .padding(.top, 3)
                        if index < entries.count - 1 {
                            Rectangle().fill(Theme.hairline).frame(width: 2).frame(maxHeight: .infinity)
                        }
                    }
                    .frame(width: 11)
                    VStack(alignment: .leading, spacing: 4) {
                        Text(entry.year)
                            .font(.caption.weight(.bold))
                            .foregroundStyle(Theme.vermilion)
                        Text(entry.title.isEmpty ? Names.artist(entry.who) : "\(Names.artist(entry.who)), „\(entry.title)”")
                            .font(.serif(16, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                            .fixedSize(horizontal: false, vertical: true)
                        if !entry.quote.isEmpty { laterQuote(entry) }
                        HStack(alignment: .top, spacing: 12) {
                            laterPicture(entry)
                            prose(entry.text, size: 15)
                        }
                    }
                    .padding(.bottom, 16)
                }
            }
        }
    }

    /// What a later work's maker said of this one.
    private func laterQuote(_ entry: DailyWork.Legacy) -> some View {
        Text("„\(entry.quote)”")
            .font(.serif(15).italic())
            .foregroundStyle(Theme.ink.opacity(0.9))
            .padding(.leading, 9)
            .overlay(alignment: .leading) { Rectangle().fill(Theme.vermilion).frame(width: 3) }
            .fixedSize(horizontal: false, vertical: true)
    }

    /// What is told of a later work under its year and name where "Dalsze
    /// losy" is the road going on (`JourneyRoad`): the quote, the picture
    /// and a few words, on the paper as on the time line.
    private func laterTold(_ entry: DailyWork.Legacy) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            if !entry.quote.isEmpty { laterQuote(entry) }
            HStack(alignment: .top, spacing: 12) {
                laterPicture(entry)
                prose(entry.text, size: 15)
            }
        }
    }

    /// The later work's picture when the catalogue or a museum has it:
    /// it opens the work's card.
    @ViewBuilder
    private func laterPicture(_ entry: DailyWork.Legacy) -> some View {
        if let later = entry.item {
            NavigationLink(value: later.id) {
                ArtImage(ref: later.thumb, fallback: later.thumbFallback, placeholder: later.item.placeholderColor, maxPixel: 300)
                    .frame(width: 72, height: 88)
                    .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            }
            .buttonStyle(.plain)
        }
    }

    /// Four other works by the artist, two to a row as "Podobne dzieła";
    /// each opens its card.
    private func byArtist(_ works: [RemoteItem]) -> some View {
        LazyVGrid(columns: Self.gridColumns, alignment: .leading, spacing: 16) {
            ForEach(works, id: \.id) { other in
                NavigationLink(value: other.id) {
                    VStack(alignment: .leading, spacing: 4) {
                        gridPicture(other)
                        Text(other.item.title.isEmpty ? "Bez tytułu" : other.item.title)
                            .font(.serif(14, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                            .lineLimit(2)
                            .multilineTextAlignment(.leading)
                        if !other.item.dateText.isEmpty {
                            Text(other.item.dateText)
                                .font(.caption)
                                .foregroundStyle(Theme.inkSoft)
                                .lineLimit(1)
                        }
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                }
                .buttonStyle(.plain)
            }
        }
    }

    /// "Inni w tym samym czasie": works made a few years either side of this
    /// one, elsewhere and by others, in one row scrolled sideways (Mateusz
    /// 2026-11-03: more of them, one row); each opens its card.
    private func sameTime(_ works: [RemoteItem]) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(alignment: .top, spacing: 10) {
                ForEach(works, id: \.id) { other in
                    NavigationLink(value: other.id) {
                        VStack(alignment: .leading, spacing: 3) {
                            gridPicture(other, height: 104)
                            Text(other.item.title.isEmpty ? "Bez tytułu" : other.item.title)
                                .font(.serif(13, weight: .semibold))
                                .foregroundStyle(Theme.ink)
                                .lineLimit(2)
                                .multilineTextAlignment(.leading)
                            Text(Names.artist(other.item.artist))
                                .font(.caption2)
                                .foregroundStyle(Theme.inkSoft)
                                .lineLimit(1)
                            if !other.item.dateText.isEmpty {
                                Text(other.item.dateText)
                                    .font(.caption2)
                                    .foregroundStyle(Theme.inkSoft)
                                    .lineLimit(1)
                            }
                        }
                        .frame(width: Self.sameTimeWidth, alignment: .topLeading)
                    }
                    .buttonStyle(.plain)
                }
            }
            .scrollTargetLayout()
        }
        .scrollTargetBehavior(.viewAligned)
        .scrollClipDisabled()
    }

    /// One work of "Inni w tym samym czasie": three and a bit to a screen,
    /// the next peeking in.
    private static let sameTimeWidth: CGFloat = 104

    /// The very end: one small star, where the note on who wrote the text
    /// used to be, and nothing else: no stars by the sections, no date,
    /// medium or museum (Mateusz 2026-11-03).
    private func footer(_ work: DailyWork) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Divider()
            AiMark()
        }
    }
}

/// What the app already knows of a day's page before it loads: the days'
/// pages seen, so one opens again on its picture and title instead of an
/// empty page.
@MainActor
enum DailyPeeks {
    struct Peek {
        var item: Item
        var title: String
        var thumb: ImageRef
        var fallback: ImageRef?
    }

    private(set) static var days: [String: DailyWork] = [:]
    /// Studies seen whole, by their work: one opens again at once.
    private(set) static var studies: [String: DailyWork] = [:]

    static func keep(_ work: DailyWork, for route: DailyRoute) {
        if route.study == nil, !work.day.isEmpty {
            if days.count > 60 { days.removeAll() }
            days[work.day] = work
        }
        if let id = route.study, work.partial != true, work.item.id == id {
            if studies.count > 60 { studies.removeAll() }
            studies[id] = work
        }
    }
}

/// The study's label under the picture, letters only, like a museum's
/// wall label: no band, ink on the page's paper (Mateusz 2026-11-03, "same
/// litery", variant 1, after 1.92.0's black slip looked too heavy). The
/// title in the buttons' letters (plain, semibold, capitals, spaced out),
/// smaller than the sections' serif headings; under it, finer and grey, the
/// artist and the date. Held, the title turns into the museum's own; a long
/// one (some run to 150 characters) is in plain letters, hard to read in
/// capitals. Held, the artist looks for their other works on Szukaj, as in
/// "O autorze".
struct StudyLabel: View {
    var title: String
    var byline: String
    var peekable = false
    var peeking: Binding<Bool> = .constant(false)
    var onArtist: (() -> Void)?

    /// Up to this many characters, the title is in capitals.
    static let capitals = 60

    /// "Katsushika Hokusai · ok. 1830–1832": first name first, then the
    /// date the page gives (in Polish once the work's texts are), else
    /// the museum's; "" leaves it out.
    static func byline(_ item: Item, date: String?) -> String {
        let date = date ?? item.dateText
        return [Names.person(item.artist), date].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    var body: some View {
        let plain = title.count > Self.capitals
        VStack(alignment: .leading, spacing: 3) {
            Text(plain ? title : title.uppercased(with: Locale(identifier: "pl_PL")))
                .font(.system(size: plain ? 13.5 : 12.5, weight: .semibold))
                .tracking(plain ? 0 : 1.6)
                .lineSpacing(plain ? 1 : 2)
                .foregroundStyle(Theme.ink)
                .fixedSize(horizontal: false, vertical: true)
                .contentTransition(.opacity)
                // Held: the museum's own, until held again.
                .titlePeek(enabled: peekable, peeking: peeking)
            if !byline.isEmpty { bylineText }
        }
        .padding(.top, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .animation(.easeInOut(duration: 0.3), value: title)
    }

    @ViewBuilder
    private var bylineText: some View {
        let text = Text(byline)
            .font(.system(size: 13, weight: .light))
            .foregroundStyle(Theme.inkSoft)
            .fixedSize(horizontal: false, vertical: true)
        if let onArtist {
            text.artistPress(onArtist)
        } else {
            text
        }
    }
}

/// A study opened from "Studium dzieła gotowe" at the bottom, over whatever
/// was open.
struct StudySheet: View {
    @Environment(\.dismiss) private var dismiss
    let itemID: String
    @State private var path = NavigationPath()

    var body: some View {
        NavigationStack(path: $path) {
            DailyView(route: DailyRoute(day: nil, study: itemID))
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Zamknij") { dismiss() }
                    }
                }
                .navigationDestination(for: String.self) { id in
                    ItemDetailView(itemID: id)
                }
                .navigationDestination(for: DailyRoute.self) { route in
                    DailyView(route: route)
                }
        }
        .opensStudies(on: $path)
    }
}
