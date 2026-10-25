import SwiftUI

/// What Discover opens with: rows of works the server picked for the frame,
/// the theme of the day and the best on e-paper, then every theme to browse.
struct SuggestionsView: View {
    @Environment(AppModel.self) private var model
    @State private var rows: [SuggestionRow] = []
    @State private var themes: [ArtTheme] = []
    @State private var loading = false

    var body: some View {
        VStack(alignment: .leading, spacing: 28) {
            if rows.isEmpty && !loading {
                EmptyStateView(
                    title: "Propozycje są w drodze",
                    message: "Serwer dobiera dzieła z muzeów w tle. Zajrzyj za chwilę albo przejrzyj motywy.",
                    systemImage: "sparkles"
                )
            }
            ForEach(rows) { row in
                SuggestionRowView(row: row, theme: themes.first { $0.key == row.theme })
            }
            if !themes.isEmpty {
                VStack(alignment: .leading, spacing: 12) {
                    Eyebrow("Motywy")
                    ForEach(themes) { theme in
                        NavigationLink(value: theme) {
                            HStack(alignment: .firstTextBaseline) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(theme.name)
                                        .font(.serif(17, weight: .medium))
                                        .foregroundStyle(Theme.ink)
                                    Text(theme.description)
                                        .font(.footnote)
                                        .foregroundStyle(Theme.inkSoft)
                                        .multilineTextAlignment(.leading)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.footnote.weight(.semibold))
                                    .foregroundStyle(Theme.inkSoft)
                            }
                            .padding(14)
                            .background(Theme.card, in: RoundedRectangle(cornerRadius: 12))
                            .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Theme.hairline))
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
        .overlay(alignment: .top) {
            if loading && rows.isEmpty { ProgressView().padding(.top, 60) }
        }
        .task { await load() }
    }

    private func load() async {
        loading = true
        defer { loading = false }
        do {
            async let found = model.backend.suggestions()
            async let all = model.backend.themes()
            (rows, themes) = try await (found, all)
        } catch is CancellationError {
        } catch {
            model.show(error)
        }
    }
}

/// One horizontal row of works.
struct SuggestionRowView: View {
    let row: SuggestionRow
    /// The theme behind the row, to browse further.
    var theme: ArtTheme?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(row.title)
                        .font(.serif(20, weight: .medium))
                        .foregroundStyle(Theme.ink)
                    if !row.subtitle.isEmpty {
                        Text(row.subtitle)
                            .font(.footnote)
                            .foregroundStyle(Theme.inkSoft)
                    }
                }
                Spacer()
                if let theme {
                    NavigationLink("Więcej", value: theme)
                        .font(.subheadline.weight(.semibold))
                }
            }
            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(alignment: .top, spacing: 14) {
                    ForEach(row.items) { remote in
                        NavigationLink(value: remote.id) {
                            ArtCard(item: remote.item.summary, ref: remote.thumb)
                                .frame(width: 150)
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

/// A theme browsed page by page, straight from the museums.
struct ThemeView: View {
    @Environment(AppModel.self) private var model
    let theme: ArtTheme
    @State private var items: [RemoteItem] = []
    @State private var page = 0
    @State private var more = true
    @State private var loading = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(theme.description)
                    .font(.serif(17))
                    .foregroundStyle(Theme.inkSoft)
                MasonryGrid(items: items.map(\.item.summary)) { summary in
                    NavigationLink(value: summary.id) {
                        ArtCard(item: summary, ref: items.first { $0.id == summary.id }?.thumb)
                    }
                    .buttonStyle(.plain)
                }
                if more {
                    Button {
                        Task { await loadMore() }
                    } label: {
                        HStack(spacing: 8) {
                            if loading { ProgressView().controlSize(.small) }
                            Text(items.isEmpty ? "Wczytuję…" : "Więcej")
                        }
                        .font(.subheadline.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(Theme.card, in: RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(Theme.hairline))
                    }
                    .disabled(loading)
                }
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 32)
        }
        .background(Theme.paper)
        .navigationTitle(theme.name)
        .navigationBarTitleDisplayMode(.inline)
        .task { if items.isEmpty { await loadMore() } }
    }

    private func loadMore() async {
        guard !loading else { return }
        loading = true
        defer { loading = false }
        do {
            let found = try await model.backend.themePage(key: theme.key, page: page + 1)
            let known = Set(items.map(\.id))
            items += found.items.filter { !known.contains($0.id) }
            page += 1
            more = found.more
        } catch {
            model.show(error)
        }
    }
}
