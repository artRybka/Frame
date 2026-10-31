import SwiftUI

/// The work of the day at the top of Propozycje: a band of the picture
/// (cropped around the place Claude named, else what draws the eye), its
/// title and one sentence written to fit two lines, an arrow in the corner;
/// the whole tile opens its page. Kept low, so the themes start right below it.
struct DailyTile: View {
    let work: DailyWork

    private var byline: String {
        [work.item.item.artist, work.item.item.dateText].filter { !$0.isEmpty }.joined(separator: " · ")
    }

    var body: some View {
        NavigationLink(value: DailyRoute(day: nil)) {
            VStack(alignment: .leading, spacing: 0) {
                Color.clear
                    .frame(height: 130)
                    .frame(maxWidth: .infinity)
                    .overlay {
                        ArtImage(
                            ref: work.item.thumb,
                            fallback: work.item.thumbFallback,
                            placeholder: work.item.item.placeholderColor,
                            maxPixel: 1000,
                            priority: .high,
                            subjectFocus: true,
                            focusPoint: work.focus.map { UnitPoint(x: $0.x, y: $0.y) }
                        )
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
                    HStack(alignment: .lastTextBaseline, spacing: 10) {
                        Text(work.teaser)
                            .font(.serif(14))
                            .foregroundStyle(Theme.ink.opacity(0.85))
                            .lineLimit(2)
                            .minimumScaleFactor(0.9)
                            .multilineTextAlignment(.leading)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Image(systemName: "arrow.right")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(Theme.accent)
                            .accessibilityHidden(true)
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
            .contentShape(RoundedRectangle(cornerRadius: Theme.corner, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityHint("Dzieło dnia")
    }
}

/// The work of the day's own page: why today, the text under its own title,
/// a note about the artist, the composition drawn over the picture, colour,
/// works like it, what it led to, the days before and, last, how it fares on
/// the frame with the buttons to show or queue it. Written by Claude once a day; while
/// it writes (or without a key) the museum's text stands in. The same page is a
/// study of any work (`route.study`), written when asked for on its card.
struct DailyView: View {
    @Environment(AppModel.self) private var model
    let route: DailyRoute
    @State private var work: DailyWork?
    @State private var failed = false
    @State private var take = 0
    @State private var sending = false
    @State private var sent: Bool?
    @State private var queueTaps = 0

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                page
            }
            .onChange(of: work?.day) {
                guard let target = LaunchRoute.scroll else { return }  // CI screenshots: "composition", "details", "end"
                Task {
                    try? await Task.sleep(for: .seconds(1))
                    proxy.scrollTo(target, anchor: target == "end" ? .bottom : .top)
                }
            }
        }
        .background(Theme.paper)
        .navigationTitle(route.study == nil ? "Dzieło dnia" : "Studium dzieła")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: route) {
            await load()
            await followLegacy()
        }
        .onAppear {
            if let id = route.study { model.studyOpened(itemID: id) }
        }
    }

    @ViewBuilder
    private var page: some View {
        if let work {
            content(work)
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, 40)
        } else if failed {
            EmptyStateView(
                title: route.study == nil ? "Nie ma tego dzieła" : "Nie ma jeszcze studium",
                message: route.study == nil
                    ? "Serwer nie ma dzieła dnia na ten dzień."
                    : "Przygotuj je na karcie dzieła, pod opisem.",
                systemImage: "photo.artframe"
            )
            .padding(.top, 80)
        } else {
            ProgressView().padding(.top, 120)
        }
    }

    /// Today's as Discover has it, then fresh; a page being written is
    /// waited for a few times.
    private func load() async {
        if let id = route.study {
            await loadStudy(id)
            return
        }
        if route.day == nil, let shown = model.daily { work = shown }
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
            if let id = route.study {
                fresh = try? await model.backend.study(itemID: id, wait: 0).work
            } else {
                fresh = try? await model.backend.daily(day: route.day, wait: 0)
            }
            guard let fresh else { return }
            work = fresh
            if route.day == nil, route.study == nil { model.daily = fresh }
        }
    }

    /// A study, as the card last heard it, then fresh; one still on its way
    /// (its card at the bottom says how far) is waited for.
    private func loadStudy(_ id: String) async {
        if let shown = model.studies[id]?.work { work = shown }
        for attempt in 0..<12 {
            do {
                let view = try await model.backend.study(itemID: id, wait: attempt == 0 ? 0 : 25)
                if let fresh = view.work {
                    work = fresh
                    return
                }
                guard view.isPending else { break }
            } catch {
                if work == nil, !error.isCancellation { model.show(error) }
                break
            }
        }
        if work == nil { failed = true }
    }

    @ViewBuilder
    private func content(_ work: DailyWork) -> some View {
        VStack(alignment: .leading, spacing: 26) {
            VStack(alignment: .leading, spacing: 14) {
                picture(work)
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
            if !work.context.isEmpty {
                section(work.headline ?? "Co mówi muzeum") {
                    ForEach(Array(work.context.enumerated()), id: \.offset) { _, paragraph in
                        prose(paragraph)
                    }
                }
            }
            if let artist = work.artist, !artist.isEmpty { section("O autorze") { prose(artist) } }
            if let takes = work.composition?.takes, !takes.isEmpty {
                compositionSection(work, takes).id("composition")
            }
            if !work.colour.isEmpty || !work.item.item.colors.isEmpty {
                section("Kolor i światło") {
                    if !work.item.item.colors.isEmpty { PaletteStrip(swatches: work.item.item.colors, height: 26, cornerRadius: 6) }
                    if !work.colour.isEmpty { prose(work.colour) }
                }
            }
            if let details = work.details, !details.isEmpty {
                section("Detale") { self.details(work, details) }.id("details")
            }
            if !work.similar.isEmpty { section("Podobne dzieła") { similar(work.similar) } }
            if !work.legacy.isEmpty { section("Dalsze losy") { legacy(work.legacy) }.id("legacy") }
            if !work.previous.isEmpty { section("Poprzednie dzieła dnia") { previous(work.previous) } }
            section("Na Twojej ramce") { onFrame(work) }
            footer(work).id("end")
        }
    }

    // MARK: Top

    private func aspect(_ item: Item) -> CGFloat {
        guard let width = item.width, let height = item.height, width > 0, height > 0 else { return 1.5 }
        return CGFloat(width) / CGFloat(height)
    }

    /// The picture as large as the width allows; tapping it opens the work's
    /// card (the original, the frame preview, the playlists).
    private func picture(_ work: DailyWork) -> some View {
        NavigationLink(value: work.item.id) {
            Color.clear
                .aspectRatio(aspect(work.item.item), contentMode: .fit)
                .overlay {
                    ArtImage(
                        ref: work.item.inLibrary ? .image(work.item.id) : work.item.thumb,
                        fallback: .thumb(work.item.id),
                        placeholder: work.item.item.placeholderColor,
                        maxPixel: 1600,
                        priority: .high
                    )
                }
                .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
        }
        .buttonStyle(.plain)
        .padding(.top, 6)
    }

    private func header(_ work: DailyWork) -> some View {
        let item = work.item.item
        let byline = [item.artist, item.dateText].filter { !$0.isEmpty }.joined(separator: " · ")
        let where_ = [item.medium, item.museum].filter { !$0.isEmpty }.joined(separator: " · ")
        return VStack(alignment: .leading, spacing: 4) {
            Text(work.title)
                .font(.serif(26, weight: .semibold))
                .foregroundStyle(Theme.ink)
                .fixedSize(horizontal: false, vertical: true)
            if !byline.isEmpty { Text(byline).font(.subheadline).foregroundStyle(Theme.ink) }
            if !where_.isEmpty { Text(where_).font(.caption).foregroundStyle(Theme.inkSoft) }
        }
    }

    /// "Pokaż na ramce" (held: for longer), at the end by "Na Twojej ramce".
    private func showButton(_ work: DailyWork) -> some View {
        Button {
            Task { await show(work, .untilNextChange) }
        } label: {
            Label {
                Text(sending ? "Wysyłam…" : sent == true ? "Wysłano" : "Pokaż na ramce")
            } icon: {
                if sending {
                    ProgressView().tint(Theme.paper)
                } else {
                    Image(systemName: sent == true ? "checkmark" : "photo.artframe")
                }
            }
        }
        .buttonStyle(ActionButtonStyle(prominent: true))
        .contextMenu {
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

    private func whyToday(_ text: String) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            Eyebrow("Dlaczego dziś", color: Theme.vermilion)
            prose(text, size: 15)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.vermilion.opacity(0.1), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(Theme.vermilion.opacity(0.3)))
    }

    // MARK: Sections

    private func section<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.serif(20, weight: .semibold))
                .foregroundStyle(Theme.ink)
            content()
        }
    }

    private func prose(_ text: String, size: CGFloat = 16) -> some View {
        Text(text)
            .font(.serif(size))
            .lineSpacing(3)
            .foregroundStyle(Theme.ink.opacity(0.9))
            .fixedSize(horizontal: false, vertical: true)
    }

    /// The takes as pencil over the picture in full colour, one at a time:
    /// "Spojrzenie", "Geometria"; the take's summary under it in the page's
    /// own type.
    private func compositionSection(_ work: DailyWork, _ takes: [DailyWork.Take]) -> some View {
        let shown = takes[min(take, takes.count - 1)]
        return section("Analiza kompozycji") {
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
            CompositionSketch(item: work.item, aspect: aspect(work.item.item), take: shown)
                .padding(.top, 4)
            if !shown.text.isEmpty { prose(shown.text, size: 15) }
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
                                ArtImage(ref: .path(detail.image), placeholder: item.placeholderColor, maxPixel: 1200)
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
    private func onFrame(_ work: DailyWork) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            if work.item.inLibrary || !work.onFrame.isEmpty {
                HStack(alignment: .top, spacing: 12) {
                    if work.item.inLibrary {
                        ArtImage(ref: .framePreview(work.item.id), placeholder: work.item.item.placeholderColor, maxPixel: 400, contentMode: .fit)
                            .frame(width: 96)
                            .whiteFrame(3)
                    }
                    if !work.onFrame.isEmpty { prose(work.onFrame, size: 15) }
                }
            }
            HStack(spacing: 12) {
                showButton(work)
                queueButton(work)
            }
            .labelStyle(ActionLabelStyle())
        }
    }

    private func similar(_ works: [DailyWork.Similar]) -> some View {
        LazyVGrid(columns: [GridItem(.flexible(), spacing: 12), GridItem(.flexible(), spacing: 12)], alignment: .leading, spacing: 16) {
            ForEach(works, id: \.item.id) { work in
                NavigationLink(value: work.item.id) {
                    VStack(alignment: .leading, spacing: 4) {
                        Color.clear
                            .frame(height: 110)
                            .frame(maxWidth: .infinity)
                            .overlay {
                                ArtImage(
                                    ref: work.item.thumb,
                                    fallback: work.item.thumbFallback,
                                    placeholder: work.item.item.placeholderColor,
                                    maxPixel: 500
                                )
                            }
                            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                        Text(work.item.item.title)
                            .font(.serif(14, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                            .lineLimit(2)
                            .multilineTextAlignment(.leading)
                        Text([work.item.item.artist, work.item.item.dateText].filter { !$0.isEmpty }.joined(separator: ", "))
                            .font(.caption)
                            .foregroundStyle(Theme.inkSoft)
                            .lineLimit(1)
                        if !work.why.isEmpty {
                            Text(work.why)
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(Theme.accent)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Theme.accent.opacity(0.12), in: RoundedRectangle(cornerRadius: 5))
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
                        Text(entry.title.isEmpty ? entry.who : "\(entry.who), „\(entry.title)”")
                            .font(.serif(16, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                            .fixedSize(horizontal: false, vertical: true)
                        if !entry.quote.isEmpty {
                            Text("„\(entry.quote)”")
                                .font(.serif(15).italic())
                                .foregroundStyle(Theme.ink.opacity(0.9))
                                .padding(.leading, 9)
                                .overlay(alignment: .leading) { Rectangle().fill(Theme.accent).frame(width: 3) }
                                .fixedSize(horizontal: false, vertical: true)
                        }
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

    private func previous(_ days: [DailyWork.Brief]) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(days, id: \.day) { brief in
                    NavigationLink(value: DailyRoute(day: brief.day)) {
                        VStack(alignment: .leading, spacing: 4) {
                            ArtImage(ref: brief.item.thumb, fallback: brief.item.thumbFallback, placeholder: brief.item.item.placeholderColor, maxPixel: 300)
                                .frame(width: 112, height: 76)
                                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                            Text(Self.dayName(brief.day))
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(Theme.inkSoft)
                            Text(brief.title)
                                .font(.caption)
                                .foregroundStyle(Theme.ink)
                                .lineLimit(1)
                        }
                        .frame(width: 112, alignment: .leading)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .scrollClipDisabled()
    }

    /// "2026-10-29" → "czw., 29 paź".
    static func dayName(_ iso: String) -> String {
        let parts = iso.split(separator: "-").compactMap { Int($0) }
        guard parts.count == 3,
              let date = Calendar.current.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2]))
        else { return iso }
        return date.formatted(.dateTime.weekday(.abbreviated).day().month(.abbreviated).locale(Locale(identifier: "pl_PL")))
    }

    private func footer(_ work: DailyWork) -> some View {
        let text: String
        if work.written {
            let from = work.sources.isEmpty ? "" : " na podstawie: \(work.sources.joined(separator: ", "))"
            text = "Tekst napisał Claude\(from). Może zawierać błędy."
        } else {
            text = "Opis muzeum. Tekst, notkę o autorze i analizę kompozycji pisze Claude, gdy w Konfiguracji jest klucz i włączone „Dzieło dnia”."
        }
        return VStack(alignment: .leading, spacing: 10) {
            Divider()
            Text(text)
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

/// A study opened from "Studium dzieła gotowe" at the bottom, over whatever
/// was open.
struct StudySheet: View {
    @Environment(\.dismiss) private var dismiss
    let itemID: String

    var body: some View {
        NavigationStack {
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
    }
}
