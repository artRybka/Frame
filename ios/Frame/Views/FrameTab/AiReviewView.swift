import SwiftUI

/// Konfiguracja → Model językowy → „Do sprawdzenia": what the catalogue's
/// gatekeeper set aside at night (a stamp, a page of text, a photograph of
/// a gallery's wall…), each with „Przywróć", and what the night audit found
/// that does not add up in a work's title, date, Polish text or picture.
/// Both were confirmed by a second model before they came here.
struct AiReviewView: View {
    @Environment(AppModel.self) private var model
    @State private var review: AiReview?
    @State private var failed = false
    /// Works whose answer the server is still taking.
    @State private var busy: Set<String> = []
    /// The picture open on the whole screen (tap on a thumbnail; Mateusz
    /// 2026-11-15 „Z miniatury nic nie widzę").
    @State private var opened: Item?
    /// The thumbnail whose work is being fetched for the viewer.
    @State private var opening: String?
    /// The work's card, opened from its title.
    @State private var card: String?
    @Namespace private var zoomSpace
    /// "Zmień…"/"Popraw…": the value written by hand.
    @State private var editing: FixEditing?
    /// "Popraw opis": the Polish texts being mended.
    @State private var polishing: FixEditing?
    /// "Inna kopia": the work whose copies are open.
    @State private var copiesFor: Item?
    /// Works whose corrected values are being asked for, and those asked.
    @State private var suggesting: Set<String> = []
    @State private var asked: Set<String> = []
    @MainActor private static var openedOnce = false

    var body: some View {
        ScrollViewReader { proxy in
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                header
                if let review {
                    if review.isEmpty {
                        EmptyStateView(
                            title: "Nic do sprawdzenia",
                            message: "Strażnik katalogu i nocny przegląd nie znalazły nic nowego.",
                            systemImage: "checkmark.seal"
                        )
                    }
                    if !review.setAside.isEmpty {
                        section(
                            "Odłożone przez strażnika",
                            note: "Nie pokazują się w katalogu ani w Szukaj. „Przywróć” wraca dzieło na stałe.",
                            entries: review.setAside
                        )
                    }
                    if !review.findings.isEmpty {
                        section(
                            "Znalezione w nocnym przeglądzie",
                            note: "Nic nie zostało zmienione. Popraw jednym dotknięciem, odhacz jako sprawdzone albo ukryj dzieło.",
                            entries: review.findings
                        )
                        .id("findings")
                    }
                } else if failed {
                    EmptyStateView(
                        title: "Nie udało się wczytać",
                        message: "Serwer nie odpowiedział. Spróbuj za chwilę.",
                        systemImage: "wifi.exclamationmark"
                    )
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 40)
                }
            }
            .pageWidth()
            .padding(.horizontal, Theme.gutter)
            .padding(.bottom, 40)
        }
        .paperPage()
        // Screenshots: `-scroll findings` opens at the night audit's findings.
        .onChange(of: review?.findings.count) { _, count in
            guard LaunchRoute.scroll == "findings", (count ?? 0) > 0 else { return }
            Task {
                try? await Task.sleep(for: .milliseconds(400))
                proxy.scrollTo("findings", anchor: .top)
            }
        }
        }
        .navigationTitle("Do sprawdzenia")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task {
            await load()
            await suggestMissing()
        }
        .fullScreenCover(item: $opened) { item in
            OriginalViewer(item: item, whole: true)
                .navigationTransition(.zoom(sourceID: item.id, in: zoomSpace))
        }
        .navigationDestination(item: $card) { id in
            ItemDetailView(itemID: id)
        }
        .sheet(item: $editing) { editing in
            ReviewFixSheet(editing: editing) { updated in
                withAnimation(.snappy) { review = updated }
            }
        }
        .sheet(item: $polishing) { editing in
            PolishFixSheet(editing: editing) { updated in
                withAnimation(.snappy) { review = updated }
            }
        }
        .sheet(item: $copiesFor) { item in
            CopiesSheet(item: item) { _ in
                // A better copy picked: the picture's problem is done.
                act("audit:" + item.id + "|picture") {
                    try await model.backend.dropReviewProblem(itemID: item.id, field: "picture")
                }
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            Eyebrow("Claude w nocy", color: Theme.vermilion)
            Text("Do sprawdzenia")
                .font(.serif(32, weight: .semibold))
                .foregroundStyle(Theme.ink)
            Text("Haiku przegląda w nocy obrazy z Commons, Europeany, Openverse i WikiArt oraz 30 losowych dzieł katalogu. Każdą decyzję potwierdza drugi model.")
                .font(.serif(17))
                .foregroundStyle(Theme.inkSoft)
        }
    }

    private func section(_ title: String, note: String, entries: [AiReview.Entry]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: title, subtitle: note)
            Card {
                ForEach(Array(entries.enumerated()), id: \.element.id) { index, entry in
                    if index > 0 { Divider() }
                    row(entry)
                }
            }
        }
    }

    private func row(_ entry: AiReview.Entry) -> some View {
        HStack(alignment: .top, spacing: 12) {
            thumbnail(entry)
            VStack(alignment: .leading, spacing: 4) {
                Button { card = entry.item.id } label: {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("\(Text(entry.item.title.isEmpty ? "Bez tytułu" : entry.item.title)) \(Text(Image(systemName: "chevron.right")).font(.caption.weight(.semibold)).foregroundStyle(Theme.inkSoft))")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(Theme.ink)
                            .lineLimit(2)
                            .multilineTextAlignment(.leading)
                        if !entry.item.artist.isEmpty {
                            Text(Names.artist(entry.item.artist))
                                .font(.caption)
                                .foregroundStyle(Theme.inkSoft)
                                .lineLimit(1)
                        }
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityHint(Text("Otwiera kartę dzieła"))
                if !entry.seenAsName.isEmpty {
                    Text(entry.seenAsName)
                        .font(.caption.weight(.medium))
                        .foregroundStyle(Theme.vermilion)
                }
                if !entry.why.isEmpty {
                    Text(entry.why)
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
                ForEach(entry.problems, id: \.self) { problem in
                    VStack(alignment: .leading, spacing: 6) {
                        Text("\(Text(problem.name + ":").fontWeight(.semibold)) \(problem.problem)")
                            .font(.caption)
                            .foregroundStyle(Theme.ink)
                        remedies(entry, problem)
                    }
                    .padding(.top, 2)
                }
                HStack(spacing: 16) {
                    if entry.by == "gatekeeper" {
                        Button("Przywróć") { act(entry.id) { try await model.backend.bringBack(itemID: entry.item.id) } }
                        Button("Zgadza się") { act(entry.id) { try await model.backend.dismissReview(itemID: entry.item.id) } }
                    } else {
                        Button("Sprawdzone") { act(entry.id) { try await model.backend.dismissReview(itemID: entry.item.id) } }
                        Button("Ukryj") { act(entry.id) { try await model.backend.hideReviewed(itemID: entry.item.id) } }
                    }
                    if busy.contains(entry.id) { ProgressView().controlSize(.small) }
                }
                .font(.subheadline.weight(.semibold))
                .buttonStyle(.borderless)
                .tint(Theme.ink)
                .disabled(busy.contains(entry.id))
                .padding(.top, 2)
            }
            Spacer(minLength: 0)
        }
        .padding(.vertical, 4)
    }

    /// What mends one problem in a tap (Mateusz 2026-11-15, „Pełne poprawki
    /// jednym dotknięciem"): a title, a maker or a date put right with the
    /// value the audit proposes ("Zmień…" to write it otherwise); a picture
    /// cut by Opus told what the audit saw, or another copy picked.
    @ViewBuilder
    private func remedies(_ entry: AiReview.Entry, _ problem: AiReview.Problem) -> some View {
        let key = entry.id + "|" + problem.field
        let itemID = entry.item.id
        Group {
            if busy.contains(key) {
                Label {
                    Text(problem.field == "picture" ? "Szukam krawędzi dzieła…" : "Poprawiam…")
                } icon: {
                    ProgressView().controlSize(.small)
                }
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
            } else if problem.valued {
                if let fix = problem.proposal {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 8) { fixButtons(entry, problem, fix: fix, key: key) }
                        VStack(alignment: .leading, spacing: 6) { fixButtons(entry, problem, fix: fix, key: key) }
                    }
                } else if suggesting.contains(itemID) {
                    Label {
                        Text("Szukam poprawki…")
                    } icon: {
                        ProgressView().controlSize(.small)
                    }
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                } else {
                    Button("Popraw…") { editing = FixEditing(entry: entry, problem: problem) }
                }
            } else if problem.field == "polish" {
                Button("Popraw opis") { polishing = FixEditing(entry: entry, problem: problem) }
            } else if problem.field == "picture" {
                HStack(spacing: 8) {
                    Button("Przytnij") {
                        act(key) { try await model.backend.cutReviewed(itemID: itemID) }
                    }
                    Button("Inna kopia") { openCopies(itemID) }
                }
            }
        }
        .font(.caption.weight(.semibold))
        .buttonStyle(.bordered)
        .controlSize(.small)
        .tint(Theme.ink)
        .disabled(busy.contains(key) || busy.contains(entry.id))
    }

    @ViewBuilder
    private func fixButtons(_ entry: AiReview.Entry, _ problem: AiReview.Problem, fix: String, key: String) -> some View {
        Button {
            act(key) {
                try await model.backend.applyReviewFix(
                    itemID: entry.item.id, field: problem.field, value: fix, valuePl: problem.fixPl
                )
            }
        } label: {
            // A long title wraps (a small bordered button keeps one line).
            Text("Popraw na „\(fix)\u{201D}")
                .multilineTextAlignment(.leading)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
        }
        Button("Zmień…") { editing = FixEditing(entry: entry, problem: problem) }
    }

    /// Works found with values still to propose, asked once each while the
    /// list is open (a fraction of a cent each; findings the audit wrote
    /// before it gave them).
    private func suggestMissing() async {
        guard let review else { return }
        let waiting = review.findings.filter { entry in
            !asked.contains(entry.item.id)
                && entry.problems.contains { $0.valued && $0.fix == "" }
        }
        for entry in waiting {
            asked.insert(entry.item.id)
            suggesting.insert(entry.item.id)
            defer { suggesting.remove(entry.item.id) }
            guard let updated = try? await model.backend.suggestReviewFixes(itemID: entry.item.id) else { continue }
            withAnimation(.snappy) { self.review = updated }
        }
    }

    private func openCopies(_ id: String) {
        guard opening == nil else { return }
        opening = id
        Task {
            defer { opening = nil }
            do {
                copiesFor = try await model.backend.item(id: id)
            } catch {
                model.notices.warn("Nie udało się otworzyć kopii", error.localizedDescription)
            }
        }
    }

    /// The picture, bigger than before and with a magnifier: a tap opens it
    /// on the whole screen, to zoom into (a ruler, a colour chart, a cut
    /// edge are seen there, not on a thumbnail).
    private func thumbnail(_ entry: AiReview.Entry) -> some View {
        Button { open(entry.item.id) } label: {
            ArtImage(ref: .thumb(entry.item.id), placeholder: entry.item.placeholderColor, maxPixel: 360)
                .frame(width: 88, height: 88)
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                .overlay(alignment: .bottomTrailing) {
                    Group {
                        if opening == entry.item.id {
                            ProgressView().controlSize(.mini).tint(.white)
                        } else {
                            Image(systemName: "arrow.up.left.and.arrow.down.right")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundStyle(.white)
                        }
                    }
                    .frame(width: 22, height: 22)
                    .background(.black.opacity(0.45), in: Circle())
                    .padding(4)
                }
                .matchedTransitionSource(id: entry.item.id, in: zoomSpace) {
                    $0.clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(Text(entry.item.title.isEmpty ? "Obraz" : entry.item.title))
        .accessibilityHint(Text("Otwiera obraz na całym ekranie"))
    }

    private func open(_ id: String) {
        guard opening == nil else { return }
        opening = id
        Task {
            defer { opening = nil }
            do {
                opened = try await model.backend.item(id: id)
            } catch {
                model.notices.warn("Nie udało się otworzyć obrazu", error.localizedDescription)
            }
        }
    }

    private func load() async {
        do {
            review = try await model.backend.aiReview()
            failed = false
            // Screenshots: `-reviewOpen YES` opens the first picture by itself.
            if UserDefaults.standard.bool(forKey: "reviewOpen"), !Self.openedOnce,
               let first = (review?.setAside.first ?? review?.findings.first) {
                Self.openedOnce = true
                open(first.item.id)
            }
            // Screenshots: `-reviewPolish YES` opens "Popraw opis" of the first such remark.
            if UserDefaults.standard.bool(forKey: "reviewPolish"), !Self.openedOnce,
               let entry = review?.findings.first(where: { $0.problems.contains { $0.field == "polish" } }),
               let problem = entry.problems.first(where: { $0.field == "polish" }) {
                Self.openedOnce = true
                polishing = FixEditing(entry: entry, problem: problem)
            }
        } catch {
            if review == nil { failed = true }
        }
    }

    private func act(_ key: String, _ call: @escaping () async throws -> AiReview) {
        busy.insert(key)
        Task {
            defer { busy.remove(key) }
            do {
                let updated = try await call()
                withAnimation(.snappy) { review = updated }
                await model.loadAiSettings()
            } catch {
                model.notices.warn("Nie udało się", error.localizedDescription)
            }
        }
    }
}

/// A problem's value being written by hand.
struct FixEditing: Identifiable {
    let entry: AiReview.Entry
    let problem: AiReview.Problem
    var id: String { entry.id + "|" + problem.field }
}

/// "Zmień…" / "Popraw…" on a finding: the work's title (with its Polish
/// title), maker or date written by hand, the audit's proposal filled in.
struct ReviewFixSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let editing: FixEditing
    let saved: (AiReview) -> Void
    @State private var value = ""
    @State private var valuePl = ""
    @State private var saving = false

    private var problem: AiReview.Problem { editing.problem }
    private var isTitle: Bool { problem.field == "title" }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(problem.problem)
                        .font(.subheadline)
                        .foregroundStyle(Theme.inkSoft)
                }
                Section(isTitle ? "Tytuł w katalogu" : problem.name) {
                    TextField(problem.name, text: $value, axis: .vertical)
                }
                if isTitle {
                    Section {
                        TextField("Polski tytuł", text: $valuePl, axis: .vertical)
                    } header: {
                        Text("Polski tytuł")
                    } footer: {
                        Text("Ten tytuł widać w aplikacji i na ramce. Polski opis dzieła zostanie napisany od nowa z poprawionym tytułem.")
                    }
                }
            }
            .navigationTitle("Popraw")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Anuluj") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    if saving {
                        ProgressView()
                    } else {
                        Button("Zapisz", action: save)
                            .disabled(value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                }
            }
        }
        .presentationDetents([.medium, .large])
        .onAppear(perform: fill)
    }

    private func fill() {
        let item = editing.entry.item
        switch problem.field {
        case "title":
            value = problem.proposal ?? item.title
            valuePl = problem.fixPl.flatMap { $0.isEmpty ? nil : $0 } ?? item.titlePl ?? ""
        case "artist":
            value = problem.proposal ?? item.artist
        default:
            value = problem.proposal ?? item.dateText
        }
    }

    private func save() {
        saving = true
        let pl = valuePl.trimmingCharacters(in: .whitespacesAndNewlines)
        Task {
            defer { saving = false }
            do {
                let updated = try await model.backend.applyReviewFix(
                    itemID: editing.entry.item.id,
                    field: problem.field,
                    value: value.trimmingCharacters(in: .whitespacesAndNewlines),
                    valuePl: isTitle && !pl.isEmpty ? pl : nil
                )
                saved(updated)
                dismiss()
            } catch {
                model.notices.warn("Nie udało się zapisać", error.localizedDescription)
            }
        }
    }
}

/// "Popraw opis" (Mateusz 2026-11-16, de Chirico's self-portrait: „Nie mam
/// możliwości korygowania takich pomyłek"): Claude mends the Polish texts
/// where the audit's remark says, and they are shown to be read, changed
/// by hand if need be, and kept with "Zapisz".
struct PolishFixSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let editing: FixEditing
    let saved: (AiReview) -> Void
    @State private var frame = ""
    @State private var full = ""
    @State private var loading = true
    @State private var failure: String?
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(editing.problem.problem)
                        .font(.subheadline)
                        .foregroundStyle(Theme.inkSoft)
                }
                if loading {
                    Section {
                        Label {
                            Text("Claude poprawia opis…")
                        } icon: {
                            ProgressView()
                        }
                        .foregroundStyle(Theme.inkSoft)
                    }
                } else if let failure {
                    Section {
                        Text(failure).foregroundStyle(Theme.vermilion)
                        Button("Spróbuj jeszcze raz") { Task { await propose() } }
                    }
                } else {
                    Section {
                        TextField("Opis", text: $full, axis: .vertical)
                            .lineLimit(6...)
                    } header: {
                        Text("Opis na karcie")
                    } footer: {
                        Text("Poprawione jest tylko to, czego dotyczy uwaga. Możesz jeszcze coś zmienić.")
                    }
                    Section("Tekst na ramce") {
                        TextField("Tekst na ramce", text: $frame, axis: .vertical)
                            .lineLimit(3...)
                    }
                }
            }
            .navigationTitle("Popraw opis")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Anuluj") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    if saving {
                        ProgressView()
                    } else {
                        Button("Zapisz", action: save)
                            .disabled(loading || failure != nil
                                || full.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                }
            }
        }
        .presentationDetents([.large])
        .task { await propose() }
    }

    private func propose() async {
        loading = true
        failure = nil
        defer { loading = false }
        do {
            let draft = try await model.backend.proposePolish(itemID: editing.entry.item.id)
            frame = draft.frame
            full = draft.full
        } catch {
            failure = error.localizedDescription
        }
    }

    private func save() {
        saving = true
        Task {
            defer { saving = false }
            do {
                let updated = try await model.backend.savePolish(
                    itemID: editing.entry.item.id,
                    draft: PolishDraft(frame: frame, full: full)
                )
                saved(updated)
                dismiss()
            } catch {
                model.notices.warn("Nie udało się zapisać", error.localizedDescription)
            }
        }
    }
}
