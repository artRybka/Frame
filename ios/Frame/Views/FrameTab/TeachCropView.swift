import SwiftUI

/// "Ucz kadrowania" (Mateusz 2026-11-21 00:47 UTC: „przygotuj mi ekran gdzie
/// dam mu dane startowe - ocenę czy trzeba kadrować i jeżeli tak, to czy jest
/// rama”): catalogue photographs one at a time, as the museum photographed
/// them, and his word on each at a glance: no cut, a cut, a cut with a
/// frame or passe-partout round the work. One kind at a time (00:48:
/// „oddzielnie malarstwem, rysunkiem i grafiką. Będzie mi łatwiej”). What
/// he says is what the phone's model is taught from next (`/api/crops/told`).
/// Those the model can least tell of come first (15:01: „Tak, jeżeli to
/// pomoże, to poproszę”): the phone's own model looks at each thumbnail
/// before it is shown, so each word of his teaches it the most.
struct TeachCropView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var kind = 0
    @State private var queue: [ItemSummary] = []
    /// What he said, the last first, for "Cofnij".
    @State private var said: [ItemSummary] = []
    @State private var skipped: Set<String> = []
    @State private var told: Int?
    /// The kind whose photographs are being asked for and looked at.
    @State private var loading: Int?
    @State private var sending = false
    /// How far the model is from wavering on each photograph: 0 where it
    /// cannot tell whether to cut, 0.5 where it is sure; 1 not looked at.
    @State private var doubt: [String: Double] = [:]

    static let kinds = [(0, "Malarstwo"), (1, "Rysunek"), (2, "Grafika")]
    /// Photographs asked of the server at a time, and how few left asks again.
    static let page = 40
    static let low = 5
    /// Looked at before the first is shown.
    static let weighed = 8

    private var current: ItemSummary? { queue.first }

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Picker("Rodzaj", selection: $kind) {
                    ForEach(Self.kinds, id: \.0) { Text(bound: $0.1).tag($0.0) }
                }
                .pickerStyle(.segmented)
                if let told {
                    Text(bound: "Ocenione \(told)")
                        .font(.subheadline.weight(.medium).monospacedDigit())
                        .foregroundStyle(Theme.inkSoft)
                }
                if let current {
                    photograph(current)
                    answers
                } else if loading == kind {
                    Spacer()
                    ProgressView()
                    Spacer()
                } else {
                    Spacer()
                    EmptyStateView(
                        title: "Nic nie czeka",
                        message: "Wszystkie zdjęcia tego rodzaju są ocenione.",
                        systemImage: "crop"
                    )
                    Spacer()
                }
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 12)
            .paperPage()
            .navigationTitle("Ucz kadrowania")
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
                    .disabled(said.isEmpty || sending)
                }
            }
            .task(id: kind) {
                queue = []
                said = []
                doubt = [:]
                await more()
            }
        }
    }

    private func photograph(_ work: ItemSummary) -> some View {
        VStack(spacing: 8) {
            ArtImage(ref: .thumb(work.id), placeholder: Theme.mat, maxPixel: 1200, contentMode: .fit, priority: .high)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .id(work.id)
            CornerZoom(work: work)
                .id("corner-\(work.id)")
            Text(bound: [work.artist, work.title].filter { !$0.isEmpty }.joined(separator: " · "))
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
                .lineLimit(2)
                .multilineTextAlignment(.center)
            // The next one loads meanwhile.
            if queue.count > 1 {
                ArtImage(ref: .thumb(queue[1].id), placeholder: .clear, maxPixel: 1200, contentMode: .fit)
                    .frame(width: 1, height: 1)
                    .opacity(0)
                    .accessibilityHidden(true)
            }
        }
    }

    private var answers: some View {
        VStack(spacing: 10) {
            HStack(spacing: 10) {
                answer("Bez kadru", "photo", .whole)
                if kind == 0 {
                    answer("Kadr", "crop", .cut)
                    answer("Kadr z ramą", "square.dashed", .framed)
                } else {
                    // A drawing or print is cut to its sheet, with no frame
                    // or passe-partout (Mateusz 2026-11-21 17:48 UTC: „Dla
                    // rysunku i grafiki zostawimy tylko jedno kadrowanie -
                    // »do kartki«”).
                    answer("Kadr do kartki", "crop", .cut)
                }
            }
            Button {
                skip()
            } label: {
                Text(bound: "Pomiń").font(.subheadline.weight(.medium)).frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
        }
        .disabled(sending)
    }

    private func answer(_ title: String, _ symbol: String, _ value: CropTeach.Answer) -> some View {
        Button {
            Task { await tell(value) }
        } label: {
            VStack(spacing: 6) {
                Image(systemName: symbol).font(.system(size: 22, weight: .medium))
                Text(bound: title).font(.subheadline.weight(.semibold)).multilineTextAlignment(.center)
            }
            .frame(maxWidth: .infinity, minHeight: 64)
        }
        .buttonStyle(.borderedProminent)
        .tint(value == .whole ? Theme.inkSoft : Theme.vermilion)
    }

    private func tell(_ value: CropTeach.Answer) async {
        guard let work = current else { return }
        sending = true
        defer { sending = false }
        do {
            told = try await model.backend.cropTell(itemID: work.id, value).told
            withAnimation(.easeInOut(duration: 0.2)) { _ = queue.removeFirst() }
            said.insert(work, at: 0)
            if queue.count < Self.low { await more() }
        } catch {
            model.show(error)
        }
    }

    private func skip() {
        guard let work = current else { return }
        skipped.insert(work.id)
        withAnimation(.easeInOut(duration: 0.2)) { _ = queue.removeFirst() }
        if queue.count < Self.low { Task { await more() } }
    }

    private func undo() async {
        guard let work = said.first else { return }
        sending = true
        defer { sending = false }
        do {
            told = try await model.backend.cropTell(itemID: work.id, nil).told
            said.removeFirst()
            withAnimation(.easeInOut(duration: 0.2)) { queue.insert(work, at: 0) }
        } catch {
            model.show(error)
        }
    }

    private func more() async {
        let asked = kind
        guard loading != asked else { return }
        loading = asked
        defer { if loading == asked { loading = nil } }
        do {
            let page = try await model.backend.cropTeach(kind: asked, limit: min(100, Self.page + skipped.count + queue.count))
            guard asked == kind else { return }
            told = page.told
            let have = Set(queue.map(\.id))
            // With nothing shown yet, the first few looked at are weighed
            // together, so the first shown is not just the first loaded.
            var held: [(ItemSummary, Double)] = []
            for work in page.works where !have.contains(work.id) && !skipped.contains(work.id) {
                let far = await farFromDoubt(work, kind: asked)
                guard asked == kind else { return }
                if queue.isEmpty, held.count < Self.weighed - 1 {
                    held.append((work, far))
                    continue
                }
                for (one, its) in held { place(one, its) }
                held = []
                place(work, far)
            }
            for (one, its) in held { place(one, its) }
        } catch {
            model.show(error)
        }
    }

    /// `work` into the queue by how sure the model is of it, the least sure
    /// first; the one shown stays where it is.
    private func place(_ work: ItemSummary, _ far: Double) {
        guard !queue.contains(where: { $0.id == work.id }) else { return }
        doubt[work.id] = far
        let from = queue.isEmpty ? 0 : 1
        let at = queue[from...].firstIndex { (doubt[$0.id] ?? 1) > far } ?? queue.count
        withAnimation(.easeInOut(duration: 0.2)) { queue.insert(work, at: at) }
    }

    /// The model's answer on the thumbnail he will see (`MuseumCrop.ask`,
    /// read as `.thumb` at the size shown, so it is kept for showing):
    /// how far its "a cut is wanted" is from a toss of a coin.
    private func farFromDoubt(_ work: ItemSummary, kind: Int) async -> Double {
        guard let request = model.backend.request(for: .thumb(work.id)),
              let image = try? await ImageLoader.shared.image(for: request, maxPixel: 1200),
              let picture = image.cgImage,
              let photo = try? MuseumCrop.pixels(of: picture)
        else { return 1 }
        let sure = try? await Task.detached(priority: .userInitiated) { try MuseumCrop.ask(photo, kind: kind).sure }.value
        return sure.map { abs($0 - 0.5) } ?? 1
    }
}

/// The photograph's top left corner, large (Mateusz 2026-11-21 00:54 UTC:
/// „pokazuj mi powiększenie jednego z narożników prezentowanego dzieła
/// (czasami ramy są wąskie i nie widać ich na małym ekranie telefonu”):
/// a quarter of its shorter side, from the thumbnail (00:55: „może być z
/// miniatury”: every work, not only those with an original kept).
struct CornerZoom: View {
    let work: ItemSummary
    static let side: CGFloat = 132
    /// The share of the photograph's shorter side shown.
    static let share: CGFloat = 0.25

    private var aspect: CGFloat {
        if let a = work.aspect, a > 0 { return CGFloat(a) }
        if let w = work.width, let h = work.height, h > 0 { return CGFloat(w) / CGFloat(h) }
        return 0.75
    }

    var body: some View {
        // The whole photograph drawn so large that a quarter of its shorter
        // side fills the box, its top left corner in the box's.
        let short = Self.side / Self.share
        let size = aspect >= 1 ? CGSize(width: short * aspect, height: short) : CGSize(width: short, height: short / aspect)
        HStack(spacing: 10) {
            ArtImage(
                ref: .thumb(work.id), placeholder: Theme.mat, maxPixel: 1200, contentMode: .fit
            )
            .frame(width: size.width, height: size.height)
            .frame(width: Self.side, height: Self.side, alignment: .topLeading)
            .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 6, style: .continuous).strokeBorder(Theme.hairline, lineWidth: 1))
            Text(bound: "Lewy górny róg, powiększony")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
            Spacer(minLength: 0)
        }
    }
}
