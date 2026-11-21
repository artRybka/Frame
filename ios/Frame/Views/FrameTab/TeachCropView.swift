import SwiftUI

/// "Ucz kadrowania" (Mateusz 2026-11-21 00:47 UTC: „przygotuj mi ekran gdzie
/// dam mu dane startowe - ocenę czy trzeba kadrować i jeżeli tak, to czy jest
/// rama”): catalogue photographs one at a time, as the museum photographed
/// them, and his word on each at a glance: no cut, a cut, a cut with a
/// frame or passe-partout round the work. One kind at a time (00:48:
/// „oddzielnie malarstwem, rysunkiem i grafiką. Będzie mi łatwiej”). What
/// he says is what the phone's model is taught from next (`/api/crops/told`).
struct TeachCropView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var kind = 0
    @State private var queue: [ItemSummary] = []
    /// What he said, the last first, for "Cofnij".
    @State private var said: [ItemSummary] = []
    @State private var skipped: Set<String> = []
    @State private var told: Int?
    @State private var loading = false
    @State private var sending = false

    static let kinds = [(0, "Malarstwo"), (1, "Rysunek"), (2, "Grafika")]
    /// Photographs asked of the server at a time, and how few left asks again.
    static let page = 30
    static let low = 5

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
                } else if loading {
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
            .background(Theme.paper.ignoresSafeArea())
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
                await more()
            }
        }
    }

    private func photograph(_ work: ItemSummary) -> some View {
        VStack(spacing: 8) {
            ArtImage(ref: .thumb(work.id), placeholder: Theme.mat, maxPixel: 1200, contentMode: .fit, priority: .high)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .id(work.id)
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
                answer("Kadr", "crop", .cut)
                answer("Kadr z ramą", "square.dashed", .framed)
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
        guard !loading else { return }
        loading = true
        defer { loading = false }
        do {
            let asked = kind
            let page = try await model.backend.cropTeach(kind: asked, limit: Self.page + skipped.count + queue.count)
            guard asked == kind else { return }
            told = page.told
            let have = Set(queue.map(\.id))
            queue += page.works.filter { !have.contains($0.id) && !skipped.contains($0.id) }
        } catch {
            model.show(error)
        }
    }
}
