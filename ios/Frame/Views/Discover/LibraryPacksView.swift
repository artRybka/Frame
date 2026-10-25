import SwiftUI

/// Polls a server import until it finishes, reporting progress on the way.
@MainActor
func watchJob(
    _ id: String, backend: any FrameBackend, progress: (JobStatus) -> Void
) async throws -> JobStatus {
    while true {
        let status = try await backend.job(id: id)
        progress(status)
        if status.finished { return status }
        try await Task.sleep(for: .seconds(1.5))
    }
}

/// "X of Y" while an import runs.
func jobProgress(_ job: JobStatus?) -> String {
    guard let job, job.total > 0 else { return "Wyszukiwanie…" }
    return "Dodawanie \(job.done + job.failed) z \(job.total)…"
}

/// Themed packs of museum works that grow the library in one tap.
struct LibraryPacksSection: View {
    @Environment(AppModel.self) private var model
    @State private var packs: [LibraryPack] = []
    @State private var running: [String: JobStatus?] = [:]
    @State private var drawing = false
    @State private var drawJob: JobStatus?? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if !packs.isEmpty {
                Eyebrow("Rozszerz bibliotekę")
                drawCard
                ForEach(packs) { pack in
                    Card(padding: 14) {
                        HStack(alignment: .top, spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(pack.name).font(.serif(17, weight: .medium))
                                Text(pack.description)
                                    .font(.footnote)
                                    .foregroundStyle(Theme.inkSoft)
                                    .fixedSize(horizontal: false, vertical: true)
                                if let job = running[pack.key] {
                                    Text(jobProgress(job))
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(Theme.accent)
                                }
                            }
                            Spacer(minLength: 0)
                            addButton(pack)
                        }
                    }
                }
                Text("Dzieła, które już masz, są pomijane, więc pakiet można dodać ponownie.")
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
            }
        }
        .sheet(isPresented: $drawing) {
            RandomDrawSheet { request in Task { await draw(request) } }
        }
        .task {
            guard packs.isEmpty else { return }
            packs = (try? await model.backend.packs()) ?? []
            for pack in packs where pack.importing {
                Task { await add(pack) }
            }
        }
    }

    private var drawCard: some View {
        Button {
            drawing = true
        } label: {
            Card(padding: 14) {
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: "dice")
                        .font(.title3)
                        .foregroundStyle(Theme.accent)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Losuj do biblioteki").font(.serif(17, weight: .medium))
                        Text("Wybierz okres, styl i rodzaj, a serwer wylosuje dzieła z kilku muzeów.")
                            .font(.footnote)
                            .foregroundStyle(Theme.inkSoft)
                            .fixedSize(horizontal: false, vertical: true)
                        if let job = drawJob {
                            Text(jobProgress(job))
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(Theme.accent)
                        }
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.right").foregroundStyle(Theme.inkSoft)
                }
            }
        }
        .buttonStyle(.plain)
        .disabled(drawJob != nil)
    }

    private func draw(_ request: DrawRequest) async {
        drawJob = .some(nil)
        defer { drawJob = nil }
        do {
            let id = try await model.backend.drawRandom(request)
            let job = try await watchJob(id, backend: model.backend) { drawJob = $0 }
            var text = "Wylosowano \(job.done) dzieł"
            if let skipped = job.skipped, skipped > 0 { text += ", pominięto \(skipped) słabszych na e-papierze" }
            model.toast = text
            await model.refreshFacets()
        } catch {
            model.show(error)
        }
    }

    private func addButton(_ pack: LibraryPack) -> some View {
        Button {
            Task { await add(pack) }
        } label: {
            HStack(spacing: 6) {
                if running[pack.key] != nil {
                    ProgressView().controlSize(.mini)
                } else {
                    Image(systemName: "plus")
                }
                Text("do \(pack.size)")
            }
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(Theme.accent.opacity(0.12), in: Capsule())
        }
        .disabled(running[pack.key] != nil)
    }

    private func add(_ pack: LibraryPack) async {
        guard running[pack.key] == nil else { return }
        running[pack.key] = .some(nil)
        defer { running[pack.key] = nil }
        do {
            let id = try await model.backend.importPack(key: pack.key)
            let job = try await watchJob(id, backend: model.backend) { running[pack.key] = $0 }
            model.toast = "\(pack.name): \(job.done) dzieł w bibliotece"
            await model.refreshFacets()
        } catch {
            model.show(error)
        }
    }
}

/// Period, style and kind for a random draw from the museums.
struct RandomDrawSheet: View {
    let start: (DrawRequest) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var request = DrawRequest()
    @State private var period = Period.any
    @State private var customFrom = ""
    @State private var customTo = ""
    @State private var onlySuitable = true

    enum Period: String, CaseIterable, Identifiable {
        case any = "Dowolny"
        case before1600 = "Do 1600"
        case baroque = "1600–1750"
        case romantic = "1750–1850"
        case late19th = "1850–1900"
        case early20th = "1900–1950"
        case custom = "Własny"
        var id: String { rawValue }

        var years: (Int?, Int?) {
            switch self {
            case .any, .custom: (nil, nil)
            case .before1600: (nil, 1599)
            case .baroque: (1600, 1750)
            case .romantic: (1750, 1850)
            case .late19th: (1850, 1900)
            case .early20th: (1900, 1950)
            }
        }
    }

    private let kinds = [
        ("any", "Wszystko"), ("painting", "Obrazy"), ("print", "Grafiki"), ("drawing", "Rysunki"),
        ("poster", "Plakaty"),
    ]
    private let styles = [
        "Impressionism", "Post-Impressionism", "Ukiyo-e", "Art Nouveau", "Romanticism", "Realism",
        "Baroque", "Symbolism", "Japonisme", "Pointillism",
    ]

    var body: some View {
        NavigationStack {
            Form {
                Section("Rodzaj") {
                    Picker("Rodzaj", selection: $request.kind) {
                        ForEach(kinds, id: \.0) { Text($0.1).tag($0.0) }
                    }
                }
                Section("Okres") {
                    Picker("Lata", selection: $period) {
                        ForEach(Period.allCases) { Text($0.rawValue).tag($0) }
                    }
                    if period == .custom {
                        TextField("Od roku", text: $customFrom).keyboardType(.numberPad)
                        TextField("Do roku", text: $customTo).keyboardType(.numberPad)
                    }
                }
                Section {
                    TextField("Dowolny, np. Impressionism", text: $request.style)
                        .textInputAutocapitalization(.words)
                        .autocorrectionDisabled()
                    FlowLayout(spacing: 8) {
                        ForEach(styles, id: \.self) { style in
                            Chip(title: style, selected: request.style == style) {
                                request.style = request.style == style ? "" : style
                            }
                        }
                    }
                    .buttonStyle(.borderless)  // in a Form row every button would fire together
                    .padding(.vertical, 4)
                } header: {
                    Text("Styl")
                } footer: {
                    Text("Po angielsku, tak jak opisują go muzea. Rijksmuseum nie ma stylów, więc przy wybranym stylu losują tylko pozostałe muzea.")
                }
                Section {
                    Picker("Ile dzieł", selection: $request.count) {
                        ForEach([50, 100, 200, 300, 500], id: \.self) { Text("\($0)").tag($0) }
                    }
                    Toggle("Tylko dobrze wyglądające na e-papierze", isOn: $onlySuitable)
                } footer: {
                    Text("Losowanie idzie w tle i potrwa kilka minut. Dzieła, które już masz, są pomijane.")
                }
            }
            .navigationTitle("Losuj do biblioteki")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Anuluj") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Losuj") {
                        start(finalRequest)
                        dismiss()
                    }
                    .fontWeight(.semibold)
                }
            }
        }
    }

    private var finalRequest: DrawRequest {
        var final = request
        if period == .custom {
            final.yearFrom = Int(customFrom)
            final.yearTo = Int(customTo)
        } else {
            (final.yearFrom, final.yearTo) = period.years
        }
        final.style = final.style.trimmingCharacters(in: .whitespaces)
        final.minSuitability = onlySuitable ? 0.6 : 0
        return final
    }
}
