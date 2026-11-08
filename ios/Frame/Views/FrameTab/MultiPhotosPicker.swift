import SwiftUI

/// Ramka → Zdjęcia → Multi: the photos the grids are tried on in the
/// preview, at most eight, in the order chosen (Mateusz 2026-11-08: "a
/// możemy ustalić 8 zdjęć 'demo' które będą tworzyć te układy?").
struct MultiPhotosRow: View {
    @Binding var photos: [String]
    @State private var choosing = false

    var body: some View {
        Button {
            choosing = true
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("Zdjęcia do podglądu")
                        .foregroundStyle(Theme.ink)
                    Spacer()
                    Text(photos.isEmpty ? "Wybierz" : "\(photos.count) z \(MultiPhotosPicker.most)")
                        .monospacedDigit()
                        .foregroundStyle(Theme.inkSoft)
                    Image(systemName: "chevron.right")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(Theme.inkSoft)
                }
                if photos.isEmpty {
                    Text("Wybierz do ośmiu zdjęć, na których podgląd pokaże każdy układ.")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .fixedSize(horizontal: false, vertical: true)
                } else {
                    HStack(spacing: 4) {
                        ForEach(photos, id: \.self) { id in
                            ArtImage(ref: .thumb(id), placeholder: Theme.mat, maxPixel: 160)
                                .aspectRatio(1, contentMode: .fit)
                                .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                        }
                        ForEach(min(photos.count, MultiPhotosPicker.most) ..< MultiPhotosPicker.most, id: \.self) { _ in
                            RoundedRectangle(cornerRadius: 4, style: .continuous)
                                .strokeBorder(Theme.ink.opacity(0.12), style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
                                .aspectRatio(1, contentMode: .fit)
                        }
                    }
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .sheet(isPresented: $choosing) {
            MultiPhotosPicker(chosen: $photos)
        }
    }
}

/// The library's photos and those sent once, the newest first; a tap
/// chooses one (its number shows the order) or takes it back.
struct MultiPhotosPicker: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Binding var chosen: [String]
    @State private var pool: [String] = []
    @State private var loading = true

    static let most = 8

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Podgląd układów Multi pokaże te zdjęcia, w kolejności wyboru: przy czterech zdjęciach na planszy cztery pierwsze. Ramka dalej bierze zdjęcia z playlisty.")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .fixedSize(horizontal: false, vertical: true)
                    if loading {
                        ProgressView().frame(maxWidth: .infinity).padding(.top, 40)
                    } else if pool.isEmpty {
                        Text("Brak zdjęć w bibliotece")
                            .font(.subheadline)
                            .foregroundStyle(Theme.inkSoft)
                            .frame(maxWidth: .infinity)
                            .padding(.top, 40)
                    } else {
                        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 4), count: 4), spacing: 4) {
                            ForEach(pool, id: \.self) { id in
                                tile(id)
                            }
                        }
                    }
                }
                .pageWidth()
                .padding(.horizontal, Theme.gutter)
                .padding(.top, 8)
                .padding(.bottom, 40)
            }
            .paperPage()
            .navigationTitle("Zdjęcia do podglądu")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Wyczyść") { withAnimation(.snappy) { chosen = [] } }
                        .disabled(chosen.isEmpty)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Gotowe") { dismiss() }
                }
            }
        }
        .task { await load() }
    }

    private func tile(_ id: String) -> some View {
        let number = chosen.firstIndex(of: id).map { $0 + 1 }
        let full = number == nil && chosen.count >= Self.most
        return Button {
            withAnimation(.snappy) {
                if let index = chosen.firstIndex(of: id) {
                    chosen.remove(at: index)
                } else if !full {
                    chosen.append(id)
                }
            }
        } label: {
            ArtImage(ref: .thumb(id), placeholder: Theme.mat, maxPixel: 240)
                .aspectRatio(1, contentMode: .fit)
                .clipShape(RoundedRectangle(cornerRadius: 4, style: .continuous))
                .overlay {
                    if number != nil {
                        RoundedRectangle(cornerRadius: 4, style: .continuous)
                            .strokeBorder(Theme.ink, lineWidth: 3)
                    }
                }
                .overlay(alignment: .bottomTrailing) {
                    if let number {
                        Text("\(number)")
                            .font(.caption.weight(.bold))
                            .monospacedDigit()
                            .foregroundStyle(.white)
                            .frame(width: 22, height: 22)
                            .background(Theme.ink, in: Circle())
                            .padding(4)
                    }
                }
                .opacity(full ? 0.4 : 1)
        }
        .buttonStyle(.plain)
        .disabled(full)
        .accessibilityLabel(number.map { "Zdjęcie \($0) do podglądu" } ?? "Zdjęcie")
        .accessibilityAddTraits(number != nil ? .isSelected : [])
    }

    private func load() async {
        defer { loading = false }
        var query = LibraryQuery()
        query.kinds = [.photo]
        query.sort = "recent"
        query.limit = 500
        var ids = (try? await model.backend.items(query).items.map(\.id)) ?? []
        // Photos sent once are not in the library's lists, only in theirs.
        if let sent = model.playlists.first(where: { $0.name == PlaylistSummary.sentName && $0.isMine }) {
            let more = (try? await model.backend.playlist(id: sent.id).itemIds) ?? []
            ids += more.filter { !ids.contains($0) }
        }
        // Chosen ones first stay in view even when no longer listed.
        pool = chosen.filter { !ids.contains($0) } + ids
    }
}
