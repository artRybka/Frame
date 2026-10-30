import SwiftUI

/// The work of the day at the top of Propozycje: a band of the picture, its
/// title and two lines that invite to read; the whole tile opens its page.
/// Kept low, so the themes start right below it.
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
                            subjectFocus: true
                        )
                    }
                    .clipped()
                VStack(alignment: .leading, spacing: 2) {
                    Text(work.title)
                        .font(.serif(19, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                    if !byline.isEmpty {
                        Text(byline)
                            .font(.caption)
                            .foregroundStyle(Theme.inkSoft)
                            .lineLimit(1)
                    }
                    HStack(alignment: .lastTextBaseline, spacing: 10) {
                        Text(work.teaser)
                            .font(.serif(14))
                            .foregroundStyle(Theme.ink.opacity(0.85))
                            .lineLimit(2)
                            .multilineTextAlignment(.leading)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Text("Czytaj dalej ›")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(Theme.accent)
                            .fixedSize()
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

/// The work of the day's own page: why today, the context, the composition
/// drawn over the picture, colour, how it fares on the frame, works like it,
/// what it led to and the days before. Written by Claude once a day; while
/// it writes (or without a key) the museum's text stands in.
struct DailyView: View {
    @Environment(AppModel.self) private var model
    let route: DailyRoute
    @State private var work: DailyWork?
    @State private var failed = false
    @State private var showLines = true
    @State private var selected: Int?
    @State private var sending = false
    @State private var sent: Bool?

    var body: some View {
        ScrollView {
            if let work {
                content(work)
                    .padding(.horizontal, Theme.gutter)
                    .padding(.bottom, 40)
            } else if failed {
                EmptyStateView(
                    title: "Nie ma tego dzieła",
                    message: "Serwer nie ma dzieła dnia na ten dzień.",
                    systemImage: "photo.artframe"
                )
                .padding(.top, 80)
            } else {
                ProgressView().padding(.top, 120)
            }
        }
        .background(Theme.paper)
        .navigationTitle("Dzieło dnia")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: route) { await load() }
    }

    /// Today's as Discover has it, then fresh; a page being written is
    /// waited for a few times.
    private func load() async {
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

    @ViewBuilder
    private func content(_ work: DailyWork) -> some View {
        VStack(alignment: .leading, spacing: 26) {
            VStack(alignment: .leading, spacing: 14) {
                picture(work)
                header(work)
                actions(work)
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
                section("Kontekst") {
                    ForEach(Array(work.context.enumerated()), id: \.offset) { _, paragraph in
                        prose(paragraph)
                    }
                }
            }
            if !work.facts.isEmpty { section("W skrócie") { facts(work.facts) } }
            if let composition = work.composition, !composition.points.isEmpty {
                compositionSection(work, composition)
            }
            if !work.colour.isEmpty || !work.item.item.colors.isEmpty {
                section("Kolor i światło") {
                    if !work.item.item.colors.isEmpty { PaletteStrip(swatches: work.item.item.colors, height: 26, cornerRadius: 6) }
                    if !work.colour.isEmpty { prose(work.colour) }
                }
            }
            if !work.onFrame.isEmpty { section("Na Twojej ramce") { onFrame(work) } }
            if !work.similar.isEmpty { section("Podobne dzieła") { similar(work.similar) } }
            if !work.legacy.isEmpty { section("Co z niego wyrosło") { legacy(work.legacy) } }
            if !work.previous.isEmpty { section("Poprzednie dzieła dnia") { previous(work.previous) } }
            footer(work)
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

    /// "Pokaż na ramce" (held: for longer) and the work's own card.
    private func actions(_ work: DailyWork) -> some View {
        HStack(spacing: 12) {
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
            NavigationLink(value: work.item.id) {
                Label("O dziele", systemImage: "info.circle")
            }
            .buttonStyle(ActionButtonStyle())
        }
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

    private func facts(_ facts: [DailyWork.Fact]) -> some View {
        LazyVGrid(columns: [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)], spacing: 8) {
            ForEach(facts, id: \.self) { fact in
                VStack(alignment: .leading, spacing: 3) {
                    Text(fact.label.uppercased())
                        .font(.system(size: 10.5, weight: .semibold))
                        .tracking(0.6)
                        .foregroundStyle(Theme.inkSoft)
                    Text(fact.value)
                        .font(.subheadline)
                        .foregroundStyle(Theme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(10)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                .background(Theme.card, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).strokeBorder(Theme.hairline))
            }
        }
    }

    private func compositionSection(_ work: DailyWork, _ composition: DailyWork.Composition) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Analiza kompozycji")
                    .font(.serif(20, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                Spacer()
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) { showLines.toggle() }
                } label: {
                    Label("Linie", systemImage: showLines ? "checkmark" : "eye.slash")
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .foregroundStyle(showLines ? Theme.paper : Theme.inkSoft)
                        .background(showLines ? Theme.accent : Theme.card, in: Capsule())
                        .overlay(Capsule().strokeBorder(showLines ? Color.clear : Theme.hairline))
                }
                .buttonStyle(.plain)
            }
            CompositionPicture(
                item: work.item,
                aspect: aspect(work.item.item),
                composition: composition,
                showLines: showLines,
                selected: $selected
            )
            Text("Dotknij numeru, by zaznaczyć opis. „Linie” chowa rysunek.")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
            ForEach(Array(composition.points.enumerated()), id: \.offset) { index, point in
                Button {
                    withAnimation(.easeInOut(duration: 0.2)) { selected = selected == index ? nil : index }
                } label: {
                    HStack(alignment: .top, spacing: 10) {
                        NumberBadge(number: index + 1, highlighted: selected == index)
                        (Text(point.title + ". ").font(.serif(15, weight: .semibold))
                            + Text(point.text).font(.serif(15)))
                            .foregroundStyle(Theme.ink.opacity(0.9))
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .padding(6)
                    .background(
                        selected == index ? Theme.vermilion.opacity(0.1) : Color.clear,
                        in: RoundedRectangle(cornerRadius: 8, style: .continuous)
                    )
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func onFrame(_ work: DailyWork) -> some View {
        HStack(alignment: .top, spacing: 12) {
            if work.item.inLibrary {
                ArtImage(ref: .framePreview(work.item.id), placeholder: work.item.item.placeholderColor, maxPixel: 400, contentMode: .fit)
                    .frame(width: 96)
                    .whiteFrame(3)
            }
            prose(work.onFrame, size: 15)
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
    /// catalogue has it.
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
                        HStack(alignment: .top, spacing: 10) {
                            if let later = entry.item {
                                NavigationLink(value: later.id) {
                                    ArtImage(ref: later.thumb, fallback: later.thumbFallback, placeholder: later.item.placeholderColor, maxPixel: 300)
                                        .frame(width: 64, height: 78)
                                        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                                }
                                .buttonStyle(.plain)
                            }
                            prose(entry.text, size: 15)
                        }
                    }
                    .padding(.bottom, 16)
                }
            }
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
            text = "Opis muzeum. Kontekst i analizę kompozycji pisze Claude, gdy w Konfiguracji jest klucz i włączone „Dzieło dnia”."
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

/// The picture with the composition drawn over it: the lines the model saw,
/// dashed, and numbered points where each remark is about.
struct CompositionPicture: View {
    let item: RemoteItem
    let aspect: CGFloat
    let composition: DailyWork.Composition
    let showLines: Bool
    @Binding var selected: Int?

    var body: some View {
        Color.clear
            .aspectRatio(aspect, contentMode: .fit)
            .overlay {
                ArtImage(
                    ref: item.inLibrary ? .image(item.id) : item.thumb,
                    fallback: .thumb(item.id),
                    placeholder: item.item.placeholderColor,
                    maxPixel: 1600
                )
            }
            .overlay {
                if showLines {
                    GeometryReader { geo in
                        ForEach(Array(composition.lines.enumerated()), id: \.offset) { _, line in
                            Self.path(line.points, in: geo.size)
                                .stroke(Color.black.opacity(0.35), style: StrokeStyle(lineWidth: 4, lineCap: .round))
                            Self.path(line.points, in: geo.size)
                                .stroke(Theme.vermilion, style: StrokeStyle(lineWidth: 2.5, lineCap: .round, dash: [8, 6]))
                        }
                        ForEach(Array(composition.points.enumerated()), id: \.offset) { index, point in
                            Button {
                                withAnimation(.easeInOut(duration: 0.2)) { selected = selected == index ? nil : index }
                            } label: {
                                NumberBadge(number: index + 1, highlighted: selected == index)
                                    .shadow(color: .black.opacity(0.4), radius: 2)
                                    .padding(8)  // a bigger target than the badge
                                    .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                            .position(x: point.x * geo.size.width, y: point.y * geo.size.height)
                        }
                    }
                    .transition(.opacity)
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
    }

    /// A smooth line through the points (fractions of the picture).
    static func path(_ spots: [DailyWork.Spot], in size: CGSize) -> Path {
        let points = spots.map { CGPoint(x: $0.x * size.width, y: $0.y * size.height) }
        var path = Path()
        guard let first = points.first, let last = points.last, points.count > 1 else { return path }
        path.move(to: first)
        if points.count > 2 {
            for index in 1 ..< points.count - 1 {
                let next = points[index + 1]
                let middle = CGPoint(x: (points[index].x + next.x) / 2, y: (points[index].y + next.y) / 2)
                path.addQuadCurve(to: middle, control: points[index])
            }
        }
        path.addLine(to: last)
        return path
    }
}

/// A numbered point of the composition, on the picture and by its remark.
struct NumberBadge: View {
    let number: Int
    var highlighted = false

    var body: some View {
        Text("\(number)")
            .font(.system(size: 12, weight: .bold))
            .foregroundStyle(Color(hex: 0x1A0F0B))
            .frame(width: 22, height: 22)
            .background(Theme.vermilion, in: Circle())
            .overlay(Circle().strokeBorder(.white.opacity(highlighted ? 0.95 : 0), lineWidth: 2))
            .scaleEffect(highlighted ? 1.2 : 1)
    }
}
