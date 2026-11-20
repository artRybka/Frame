import SwiftUI

/// Opens "Kadrowane" within Playlisty.
struct CroppedRoute: Hashable {}

/// "Kadrowane" (the owner's; Mateusz 2026-11-20: „album »kadrowane« gdzie
/// trafiałyby dzieła kadrowane przez model (i te które model nie wiedział
/// jak zrobić), ja mógłbym je korygować ręcznie”): the museum works the
/// phone's model cut, and those it was unsure of and left whole.
///
/// Checked one under another, each the width of the page (Mateusz
/// 2026-11-20 17:34 UTC, sketch accepted 17:42): the museum's photograph
/// with the work's corners and the frame's, the work alone and the work in
/// its frame, and "Zatwierdź", "Kadr dzieła", "Kadr ramy", "Bez ramy" under
/// them. A work leaves the list once it is approved or its cut is his own;
/// both are what the model is taught again from (`/api/crops/lessons`).
struct CroppedWorksView: View {
    @Environment(AppModel.self) private var model
    @State private var loading = false
    @State private var part = Part.cut
    /// The works as the server has them now (their cuts), by id.
    @State private var items: [String: Item] = [:]
    @State private var editing: Editing?

    enum Part: Hashable { case cut, unsure }

    /// "Popraw kadr" opened from a row, on the work's corners or the frame's.
    struct Editing: Identifiable {
        let item: Item
        let start: CutEditor.Part
        var id: String { item.id }
    }

    private var review: CropReview { model.cropReview ?? CropReview(cut: [], unsure: []) }
    private var shown: [ItemSummary] { part == .cut ? review.cut : review.unsure }

    var body: some View {
        ScrollViewReader { proxy in
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 22) {
                header
                if !review.isEmpty {
                    Picker("Część", selection: $part) {
                        Text(bound: "Wykadrowane").tag(Part.cut)
                        Text(bound: "Do wykadrowania").tag(Part.unsure)
                    }
                    .pickerStyle(.segmented)
                }
                ForEach(shown) { summary in
                    CropCheckRow(
                        summary: summary, item: items[summary.id], sure: review.sure?.first { $0.id == summary.id }?.sure,
                        unsure: part == .unsure,
                        loaded: { items[summary.id] = $0 },
                        edit: { item, start in editing = Editing(item: item, start: start) },
                        approve: { await approve(summary.id) },
                        bare: { await bare(summary.id) }
                    )
                    .id(summary.id)
                    Divider().overlay(Theme.hairline)
                }
                if shown.isEmpty {
                    if loading {
                        GridSkeleton(count: 2)
                    } else {
                        EmptyStateView(
                            title: "Nic nie czeka",
                            message: part == .cut
                                ? "Tu trafiają dzieła wykadrowane przez model na iPhonie."
                                : "Tu trafiają dzieła, których model nie był pewny.",
                            systemImage: "crop"
                        )
                    }
                }
            }
            .pageWidth()
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 40)
        }
        .paperPage()
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await model.refreshCropReview() }
        .task(id: model.libraryRevision) {
            loading = model.cropReview == nil
            await model.refreshCropReview()
            loading = false
            if review.cut.isEmpty, !review.unsure.isEmpty { part = .unsure }
            // CI screenshots: `-scroll second`, the second work at the top.
            if LaunchRoute.scroll == "second", shown.count > 1 {
                try? await Task.sleep(for: .seconds(5))
                withAnimation { proxy.scrollTo(shown[1].id, anchor: .top) }
            }
        }
        .fullScreenCover(item: $editing) { edit in
            CutEditor(item: edit.item, starting: edit.start) { update in await save(edit.item.id, update) }
        }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            Eyebrow("Model na iPhonie", color: Theme.vermilion)
            Text(bound: "Kadrowane")
                .font(.serif(32, weight: .semibold))
                .foregroundStyle(Theme.ink)
            Text(bound: "Do sprawdzenia \(review.cut.count + review.unsure.count) · wykadrowane \(review.cut.count) · bez kadru \(review.unsure.count)")
                .font(.subheadline.weight(.medium).monospacedDigit())
                .foregroundStyle(Theme.inkSoft)
        }
    }

    /// "Zatwierdź" (or "Bez kadru"): off the list, the next comes up.
    private func approve(_ id: String) async {
        do {
            let after = try await model.backend.cropFine(itemID: id)
            withAnimation(.easeInOut(duration: 0.3)) { model.cropReview = after }
            items[id] = nil
        } catch {
            model.show(error)
        }
    }

    /// "Bez ramy": what is around the work is background; the row shows it.
    private func bare(_ id: String) async {
        do {
            let updated = try await model.backend.setCut(itemID: id, update: CutUpdate(noFrame: true))
            withAnimation(.easeInOut(duration: 0.25)) { items[id] = updated }
            model.cardShows(updated, changed: true)
        } catch {
            model.show(error)
        }
    }

    private func save(_ id: String, _ update: CutUpdate) async -> Bool {
        do {
            let updated = try await model.backend.setCut(itemID: id, update: update)
            items[id] = updated
            model.cardShows(updated, changed: true)
            // His own corners: corrected, off the list.
            await model.refreshCropReview()
            return true
        } catch {
            model.show(error)
            return false
        }
    }
}

/// One work on "Kadrowane": the three views and what to do with it.
struct CropCheckRow: View {
    @Environment(AppModel.self) private var model
    let summary: ItemSummary
    let item: Item?
    let sure: Double?
    let unsure: Bool
    let loaded: (Item) -> Void
    let edit: (Item, CutEditor.Part) -> Void
    let approve: () async -> Void
    let bare: () async -> Void
    @State private var busy = false

    /// The work's corners: amber, as the cut editor's corner in hand.
    static let workLine = Color(light: 0xF2B93B, dark: 0xF2C14E)

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(bound: summary.shownTitle)
                        .font(.serif(21, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                        .lineLimit(2)
                    Text(bound: summary.artist)
                        .font(.subheadline)
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(1)
                }
                Spacer(minLength: 8)
                if let sure {
                    Text(bound: "pewność \(Int((sure * 100).rounded())) %")
                        .font(.caption.weight(.medium).monospacedDigit())
                        .foregroundStyle(Theme.inkSoft)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(Theme.mat, in: Capsule())
                }
            }
            if let item {
                photograph(item)
                legend(item)
                if !unsure { views(item) }
                buttons(item)
            } else {
                RoundedRectangle(cornerRadius: 8).fill(Theme.mat).aspectRatio(4 / 3, contentMode: .fit)
            }
        }
        .task(id: summary.pictureVersion) {
            if let fresh = try? await model.backend.item(id: summary.id) { loaded(fresh) }
        }
    }

    /// The museum's photograph with the work's corners and the frame's.
    private func photograph(_ item: Item) -> some View {
        let aspect = item.cut.map(\.aspect).flatMap { $0 > 0 ? $0 : nil } ?? 4 / 3
        return Color.clear
            .aspectRatio(CGFloat(aspect), contentMode: .fit)
            .overlay {
                ArtImage(
                    ref: .museumPhoto(item.id, side: 1600, version: item.pictureVersion),
                    placeholder: Theme.mat, maxPixel: 1600, contentMode: .fit
                )
            }
            .overlay {
                Canvas { context, size in
                    if let frame = item.cut?.surround, frame.count == 4 {
                        context.stroke(
                            quad(frame, size), with: .color(.white),
                            style: StrokeStyle(lineWidth: 2, dash: [6, 4])
                        )
                    }
                    if let work = item.cutShown, work.count == 4 {
                        context.stroke(quad(work, size), with: .color(Self.workLine), lineWidth: 2.5)
                    }
                }
                .allowsHitTesting(false)
            }
            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
    }

    private func quad(_ corners: [[Double]], _ size: CGSize) -> Path {
        Path { path in
            for (n, c) in corners.enumerated() {
                let p = CGPoint(x: c[0] * size.width, y: c[1] * size.height)
                if n == 0 { path.move(to: p) } else { path.addLine(to: p) }
            }
            path.closeSubpath()
        }
    }

    private func legend(_ item: Item) -> some View {
        HStack(spacing: 16) {
            if item.cutShown != nil {
                HStack(spacing: 6) {
                    Capsule().fill(Self.workLine).frame(width: 18, height: 3)
                    Text(bound: "dzieło")
                }
            }
            if item.cut?.surround != nil {
                HStack(spacing: 6) {
                    Rectangle()
                        .stroke(Theme.inkSoft, style: StrokeStyle(lineWidth: 2, dash: [4, 3]))
                        .frame(width: 18, height: 0.5)
                    Text(bound: "rama albo passe-partout")
                }
            } else if !unsure {
                Text(bound: "bez ramy")
            }
            if unsure { Text(bound: "Model nie był pewny, zostawił zdjęcie całe.") }
        }
        .font(.caption)
        .foregroundStyle(Theme.inkSoft)
    }

    /// The work alone, and the work in its frame (or no frame).
    private func views(_ item: Item) -> some View {
        HStack(alignment: .top, spacing: 12) {
            small("Samo dzieło") {
                ArtImage(
                    ref: item.originalRef, fallback: .thumb(item.id), placeholder: Theme.mat,
                    maxPixel: 900, contentMode: .fit
                )
            }
            small(item.framed?.name ?? "W ramie") {
                if let look = item.framed {
                    ArtImage(
                        ref: .framed(item.id, side: 900, version: "\(item.pictureVersion)|\(look.kind)\(look.aspect)\(look.inner.minX)\(look.inner.minY)\(look.inner.width)"),
                        placeholder: Theme.mat, maxPixel: 900, contentMode: .fit
                    )
                } else {
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .strokeBorder(Theme.hairline, lineWidth: 1)
                        .overlay {
                            Text(bound: "Bez ramy")
                                .font(.subheadline.weight(.medium))
                                .foregroundStyle(Theme.inkSoft)
                        }
                }
            }
        }
    }

    private func small(_ title: String, @ViewBuilder _ picture: () -> some View) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            picture()
                .frame(maxWidth: .infinity)
                .frame(height: 150)
            Text(bound: title)
                .font(.caption.weight(.medium))
                .foregroundStyle(Theme.inkSoft)
        }
        .frame(maxWidth: .infinity)
    }

    private func buttons(_ item: Item) -> some View {
        HStack(spacing: 8) {
            if unsure {
                action("Bez kadru", "checkmark", main: true) { await run(approve) }
                action("Kadruj", "crop") { edit(item, .work) }
            } else {
                let framed = item.cut?.surround != nil
                action("Zatwierdź", "checkmark", main: true) { await run(approve) }
                action("Kadr dzieła", "crop") { edit(item, .work) }
                action(framed ? "Kadr ramy" : "Dodaj ramę", "square.dashed") { edit(item, .frame) }
                action("Bez ramy", "nosign", chosen: !framed) { await run(bare) }
                    .disabled(!framed)
            }
        }
        .disabled(busy)
    }

    private func run(_ step: () async -> Void) async {
        busy = true
        await step()
        busy = false
    }

    private func action(
        _ title: String, _ symbol: String, main: Bool = false, chosen: Bool = false,
        _ act: @escaping () async -> Void
    ) -> some View {
        Button {
            Task { await act() }
        } label: {
            VStack(spacing: 6) {
                Image(systemName: symbol).font(.system(size: 18, weight: .medium))
                Text(bound: title).font(.caption.weight(.semibold)).lineLimit(1).minimumScaleFactor(0.8)
            }
            .foregroundStyle(main ? Theme.paper : Theme.ink)
            .frame(maxWidth: .infinity, minHeight: 58)
            .background(main ? Theme.ink : Theme.mat, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay {
                if chosen {
                    RoundedRectangle(cornerRadius: 12, style: .continuous).strokeBorder(Theme.ink, lineWidth: 1.5)
                }
            }
        }
        .buttonStyle(.plain)
    }
}

/// "Kadrowane" among the playlists: the works waiting there.
struct CroppedCard: View {
    let review: CropReview

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            FrostedCover(itemIDs: (review.cut + review.unsure).prefix(4).map(\.id))
                .aspectRatio(1, contentMode: .fit)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                .overlay(alignment: .bottomTrailing) {
                    GlassBadge(systemImage: "crop")
                        .padding(9)
                }
                .shadow(color: .black.opacity(0.12), radius: 10, y: 6)
            CardCaption {
                Text(bound: "Kadrowane")
                    .font(.serif(16, weight: .semibold))
                    .foregroundStyle(Theme.ink)
                Text(bound: "\(review.cut.count) wykadrowane · \(review.unsure.count) do wykadrowania")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityHint("Otwiera dzieła wykadrowane przez model i te do ręcznego kadrowania")
    }
}
