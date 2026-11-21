import SwiftUI

/// "Sprawdź kadry" (Konfiguracja → Diagnostyka → "Kadrowanie zdjęć z
/// muzeów"): the museum works the phone's model cut, and those it was unsure
/// of and left whole, one at a time as in "Ucz kadrowania" (Mateusz
/// 2026-11-21 23:34 UTC: „Playlista »kadrowanie« - przenieśmy do
/// diagnostyki do sekcji »kadrowanie zdjęć«. trzeba dostosować wygodę jej
/// używania na wzór ekranu »ucz kadrowania«”). Was the list "Kadrowane" in
/// Playlisty (2026-11-20).
///
/// The museum's photograph with the work's corners and the frame's, the
/// cut's corner large, the work alone and in its frame, and his word under
/// them: "Zatwierdź" (or "Bez kadru"), "Kadr dzieła", "Kadr ramy", "Bez
/// ramy", "Pomiń"; "Cofnij" takes the last approval back. A work leaves once
/// it is approved (also after he set its cut); what it is then is what the
/// model is taught again from (`/api/crops/lessons`).
struct CropCheckView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var part = Part.cut
    /// The works as the server has them now (their cuts), by id.
    @State private var items: [String: Item] = [:]
    /// What he approved, the last first, for "Cofnij".
    @State private var said: [String] = []
    @State private var skipped: Set<String> = []
    /// Shown first whatever its place: the one he is working on (his cut
    /// moves a work the model left whole among the cut ones) or brought
    /// back by "Cofnij".
    @State private var front: String?
    @State private var loading = true
    @State private var busy = false
    @State private var editing: Editing?

    enum Part: Hashable { case cut, unsure }

    /// "Popraw kadr" opened on the work's corners or the frame's.
    struct Editing: Identifiable {
        let item: Item
        let start: CutEditor.Part
        var id: String { item.id }
    }

    private var review: CropReview { model.cropReview ?? CropReview(cut: [], unsure: []) }

    private func queue(_ part: Part) -> [ItemSummary] {
        let all = part == .cut ? review.cut : review.unsure
        var left = all.filter { !skipped.contains($0.id) }
        if let front, let at = left.firstIndex(where: { $0.id == front }) {
            left.insert(left.remove(at: at), at: 0)
        }
        return left
    }

    private var shown: [ItemSummary] { queue(part) }
    private var current: ItemSummary? { shown.first }

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                Picker("Część", selection: $part) {
                    Text(bound: "Wykadrowane \(queue(.cut).count)").tag(Part.cut)
                    Text(bound: "Do wykadrowania \(queue(.unsure).count)").tag(Part.unsure)
                }
                .pickerStyle(.segmented)
                if let current {
                    if let item = items[current.id] {
                        work(current, item)
                        answers(item)
                    } else {
                        Spacer()
                        ProgressView()
                        Spacer()
                    }
                } else if loading {
                    Spacer()
                    ProgressView()
                    Spacer()
                } else {
                    Spacer()
                    EmptyStateView(
                        title: "Nic nie czeka",
                        message: part == .cut
                            ? "Tu trafiają dzieła wykadrowane przez model na iPhonie."
                            : "Tu trafiają dzieła, których model nie był pewny.",
                        systemImage: "crop"
                    )
                    if !skipped.isEmpty {
                        Button {
                            withAnimation(.easeInOut(duration: 0.2)) { skipped = [] }
                        } label: {
                            Text(bound: "Pokaż pominięte (\(skipped.count))").font(.subheadline.weight(.medium))
                        }
                        .buttonStyle(.bordered)
                    }
                    Spacer()
                }
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 12)
            .paperPage()
            .navigationTitle("Sprawdź kadry")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Gotowe") { dismiss() }
                }
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        Task { await undo() }
                    } label: {
                        Label("Cofnij", systemImage: "arrow.uturn.backward")
                    }
                    .disabled(said.isEmpty || busy)
                }
            }
            .task {
                await model.refreshCropReview()
                loading = false
                if review.cut.isEmpty, !review.unsure.isEmpty { part = .unsure }
            }
            // The work shown, as the server has it now, and the next one
            // meanwhile.
            .task(id: shown.prefix(2).map { "\($0.id)|\($0.pictureVersion)" }) {
                for summary in shown.prefix(2) where items[summary.id]?.pictureVersion != summary.pictureVersion {
                    if let fresh = try? await model.backend.item(id: summary.id) { items[summary.id] = fresh }
                }
            }
            .fullScreenCover(item: $editing) { edit in
                CutEditor(item: edit.item, starting: edit.start) { update in await save(edit.item.id, update) }
            }
        }
    }

    private func work(_ summary: ItemSummary, _ item: Item) -> some View {
        VStack(spacing: 8) {
            LinedPhoto(item: item)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .id("\(item.id)|\(item.pictureVersion)")
            HStack(alignment: .top, spacing: 8) {
                CutCornerZoom(item: item)
                if part == .cut {
                    small("Samo dzieło") {
                        ArtImage(
                            ref: item.originalRef, fallback: .thumb(item.id), placeholder: Theme.mat,
                            maxPixel: 600, contentMode: .fit
                        )
                    }
                    small(item.framed?.name ?? "W ramie") {
                        if let look = item.framed {
                            ArtImage(
                                ref: .framed(item.id, side: 600, version: "\(item.pictureVersion)|\(look.kind)\(look.aspect)\(look.inner.minX)\(look.inner.minY)\(look.inner.width)"),
                                placeholder: Theme.mat, maxPixel: 600, contentMode: .fit
                            )
                        } else {
                            RoundedRectangle(cornerRadius: 6, style: .continuous)
                                .strokeBorder(Theme.hairline, lineWidth: 1)
                                .overlay {
                                    Text(bound: "Bez ramy")
                                        .font(.caption.weight(.medium))
                                        .foregroundStyle(Theme.inkSoft)
                                }
                        }
                    }
                } else {
                    Text(bound: "Model nie był pewny i zostawił zdjęcie całe. Powiększony lewy górny róg.")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            HStack(spacing: 6) {
                Text(bound: [summary.artist, summary.shownTitle].filter { !$0.isEmpty }.joined(separator: " · "))
                    .lineLimit(2)
                if let sure = review.sure?.first(where: { $0.id == summary.id })?.sure {
                    Text(bound: "· pewność \(Int((sure * 100).rounded())) %").monospacedDigit().layoutPriority(1)
                }
            }
            .font(.caption)
            .foregroundStyle(Theme.inkSoft)
            .multilineTextAlignment(.center)
        }
    }

    private func small(_ title: String, @ViewBuilder _ picture: () -> some View) -> some View {
        VStack(spacing: 4) {
            picture()
                .frame(maxWidth: .infinity)
                .frame(height: CutCornerZoom.side)
            Text(bound: title)
                .font(.caption2.weight(.medium))
                .foregroundStyle(Theme.inkSoft)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity)
    }

    private func answers(_ item: Item) -> some View {
        let framed = item.cut?.surround != nil
        return VStack(spacing: 10) {
            HStack(spacing: 10) {
                Button {
                    skip(item.id)
                } label: {
                    Text(bound: "Pomiń").font(.subheadline.weight(.medium)).frame(maxWidth: .infinity, minHeight: 52)
                }
                .buttonStyle(.bordered)
                .frame(maxWidth: 110)
                Button {
                    Task { await approve(item.id) }
                } label: {
                    Label((part == .cut ? "Zatwierdź" : "Bez kadru").bound, systemImage: part == .cut ? "checkmark" : "photo")
                        .font(.headline)
                        .frame(maxWidth: .infinity, minHeight: 52)
                }
                .buttonStyle(.borderedProminent)
                .tint(part == .cut ? Theme.vermilion : Theme.inkSoft)
            }
            HStack(spacing: 10) {
                action("Kadr dzieła", "crop") { editing = Editing(item: item, start: .work) }
                action(framed ? "Kadr ramy" : "Dodaj ramę", "square.dashed") { editing = Editing(item: item, start: .frame) }
                if part == .cut {
                    action("Bez ramy", "nosign") { Task { await bare(item.id) } }
                        .disabled(!framed)
                }
            }
        }
        .disabled(busy)
    }

    private func action(_ title: String, _ symbol: String, _ act: @escaping () -> Void) -> some View {
        Button(action: act) {
            VStack(spacing: 4) {
                Image(systemName: symbol).font(.system(size: 18, weight: .medium))
                Text(bound: title).font(.caption.weight(.semibold)).lineLimit(1).minimumScaleFactor(0.8)
            }
            .frame(maxWidth: .infinity, minHeight: 52)
        }
        .buttonStyle(.bordered)
        .tint(Theme.ink)
    }

    /// "Zatwierdź" (or "Bez kadru"): off the list, the next comes up.
    private func approve(_ id: String) async {
        busy = true
        defer { busy = false }
        do {
            let after = try await model.backend.cropFine(itemID: id)
            withAnimation(.easeInOut(duration: 0.2)) {
                model.cropReview = after
                if front == id { front = nil }
            }
            said.insert(id, at: 0)
        } catch {
            model.show(error)
        }
    }

    private func skip(_ id: String) {
        withAnimation(.easeInOut(duration: 0.2)) {
            skipped.insert(id)
            if front == id { front = nil }
        }
    }

    /// "Cofnij": the last approval taken back, the work shown again.
    private func undo() async {
        guard let id = said.first else { return }
        busy = true
        defer { busy = false }
        do {
            let after = try await model.backend.cropUnfine(itemID: id)
            said.removeFirst()
            withAnimation(.easeInOut(duration: 0.2)) {
                model.cropReview = after
                front = id
                skipped.remove(id)
                if after.unsure.contains(where: { $0.id == id }) { part = .unsure }
                if after.cut.contains(where: { $0.id == id }) { part = .cut }
            }
        } catch {
            model.show(error)
        }
    }

    /// "Bez ramy": what is around the work is background.
    private func bare(_ id: String) async {
        busy = true
        defer { busy = false }
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
            // His own corners stay until he approves them; a work the model
            // left whole is among the cut ones now, and stays in front.
            front = id
            await model.refreshCropReview()
            if review.cut.contains(where: { $0.id == id }) { part = .cut }
            return true
        } catch {
            model.show(error)
            return false
        }
    }
}

/// The museum's photograph with the work's corners (amber, as the cut
/// editor's corner in hand) and the frame's (pink); thin, not to hide what
/// they mark (Mateusz 2026-11-20: „Kreski są za grube - zasłaniają sens.
/// Zamiast przerywanej daj różową.”).
struct LinedPhoto: View {
    let item: Item
    var lineWidth: CGFloat = 1

    static let workLine = Color(light: 0xF2B93B, dark: 0xF2C14E)
    static let frameLine = Color(light: 0xFF5FA2, dark: 0xFF7AB4)

    var aspect: CGFloat {
        CGFloat(item.cut.map(\.aspect).flatMap { $0 > 0 ? $0 : nil }
            ?? item.width.flatMap { w in item.height.map { Double(w) / Double(max($0, 1)) } } ?? 4 / 3)
    }

    var body: some View {
        Color.clear
            .aspectRatio(aspect, contentMode: .fit)
            .overlay {
                ArtImage(
                    ref: .museumPhoto(item.id, side: 1600, version: item.pictureVersion),
                    placeholder: Theme.mat, maxPixel: 1600, contentMode: .fit
                )
            }
            .overlay {
                Canvas { context, size in
                    if let frame = item.cut?.surround, frame.count == 4 {
                        context.stroke(Self.quad(frame, size), with: .color(Self.frameLine), lineWidth: lineWidth)
                    }
                    if let work = item.cutShown, work.count == 4 {
                        context.stroke(Self.quad(work, size), with: .color(Self.workLine), lineWidth: lineWidth)
                    }
                }
                .allowsHitTesting(false)
            }
    }

    static func quad(_ corners: [[Double]], _ size: CGSize) -> Path {
        Path { path in
            for (n, c) in corners.enumerated() {
                let p = CGPoint(x: c[0] * size.width, y: c[1] * size.height)
                if n == 0 { path.move(to: p) } else { path.addLine(to: p) }
            }
            path.closeSubpath()
        }
    }
}

/// The cut's top left corner, large, with its lines (as `CornerZoom` in
/// "Ucz kadrowania", where a narrow frame is not seen on the phone's
/// screen): the frame's corner when there is a frame, else the work's;
/// without a cut the photograph's own corner.
struct CutCornerZoom: View {
    let item: Item
    static let side: CGFloat = 112
    /// The share of the photograph's shorter side shown.
    static let share: CGFloat = 0.25

    private var corner: CGPoint {
        let c = item.cut?.surround ?? item.cutShown
        guard let c, c.count == 4 else { return .zero }
        return CGPoint(x: c[0][0], y: c[0][1])
    }

    var body: some View {
        let photo = LinedPhoto(item: item, lineWidth: 1.5)
        let aspect = photo.aspect
        let short = Self.side / Self.share
        let size = aspect >= 1 ? CGSize(width: short * aspect, height: short) : CGSize(width: short, height: short / aspect)
        // The corner in the box's middle, the photograph's edge never inside.
        let x = min(max(corner.x * size.width - Self.side / 2, 0), size.width - Self.side)
        let y = min(max(corner.y * size.height - Self.side / 2, 0), size.height - Self.side)
        VStack(spacing: 4) {
            photo
                .frame(width: size.width, height: size.height)
                .offset(x: -x, y: -y)
                .frame(width: Self.side, height: Self.side, alignment: .topLeading)
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 6, style: .continuous).strokeBorder(Theme.hairline, lineWidth: 1))
            Text(bound: "Róg, powiększony")
                .font(.caption2.weight(.medium))
                .foregroundStyle(Theme.inkSoft)
                .lineLimit(1)
        }
    }
}
