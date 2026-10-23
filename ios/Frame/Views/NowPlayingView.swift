import SwiftUI
import UIKit

/// What the frame shows right now: simulated preview + description.
struct NowPlayingView: View {
    @Environment(AppModel.self) private var model
    @State private var pushing = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    previewCard
                    if let now = model.nowPlaying {
                        details(now)
                    } else if !model.isLoading {
                        ContentUnavailableView(
                            "Brak danych",
                            systemImage: "wifi.exclamationmark",
                            description: Text(model.lastError ?? "Połącz się z serwerem ramki.")
                        )
                    }
                }
                .padding()
            }
            .navigationTitle("Na ramce")
            .refreshable { await model.refresh() }
            .task { await model.refresh() }
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        Task { await pushAgain() }
                    } label: {
                        Label("Wyślij ponownie", systemImage: "arrow.clockwise.circle")
                    }
                    .disabled(pushing || model.api == nil)
                }
            }
        }
    }

    @ViewBuilder
    private var previewCard: some View {
        if let data = model.preview, let image = UIImage(data: data) {
            Image(uiImage: image)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .clipShape(RoundedRectangle(cornerRadius: 4))
                .overlay(RoundedRectangle(cornerRadius: 4).stroke(Color.secondary.opacity(0.4)))
                .shadow(radius: 6, y: 3)
                .accessibilityLabel(model.nowPlaying?.title ?? "Podgląd")
        } else if model.isLoading {
            ProgressView().frame(maxWidth: .infinity, minHeight: 200)
        }
    }

    private func details(_ now: NowPlaying) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(now.title.isEmpty ? "Bez tytułu" : now.title)
                .font(.title2.weight(.semibold))
            if !now.description.isEmpty {
                Text(now.description)
                    .font(.body)
                    .foregroundStyle(.secondary)
            }
            LabeledContent("Źródło", value: now.source)
            LabeledContent("Wysłano", value: now.created)
        }
    }

    private func pushAgain() async {
        guard let api = model.api else { return }
        pushing = true
        defer { pushing = false }
        do {
            _ = try await api.pushAgain()
        } catch {
            model.lastError = error.localizedDescription
        }
    }
}
