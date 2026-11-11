import SwiftUI

/// Konfiguracja → Zadania nocne (Mateusz 2026-11-10: "uruchomienie zadań
/// nocnych niezależnie od pory dnia"): the server's night, one task at a time
/// or all of them, started now; what runs and how each last went. Since
/// 2026-11-11 in packages ("Powtórki i jakość", "Utrzymanie katalogu"…),
/// each started at once, its tasks folded away ("lista jest długa i
/// niekoniecznie jasna").
struct NightTasksSection: View {
    @Environment(AppModel.self) private var model
    @State private var loading = true
    @State private var confirmAll = false

    private var night: NightTasks? { model.nightTasks }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Zadania nocne", subtitle: subtitle)
            if let night {
                if let running = night.running {
                    RunningCard(night: night, running: running)
                } else {
                    allButton(night)
                }
                if let groups = night.groups, !groups.isEmpty {
                    ForEach(groups) { group in
                        NightGroupCard(night: night, group: group)
                    }
                } else {
                    Card(padding: 0) {
                        NightTaskRows(tasks: night.tasks, running: night.running)
                    }
                }
                Text("Na żądanie zadania nie czekają, aż odłożysz aplikację: serwer może wtedy odpowiadać wolniej.")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
            } else if loading {
                ProgressView()
                    .frame(maxWidth: .infinity)
            } else {
                Card {
                    Text("Serwer nie podał zadań nocnych. Starsza wersja serwera nie uruchamia ich na żądanie.")
                        .font(.subheadline)
                        .foregroundStyle(Theme.inkSoft)
                }
            }
        }
        .task {
            await model.loadNightTasks()
            loading = false
        }
        // While tasks run: asked again every few seconds.
        .task(id: night?.running != nil) {
            while night?.running != nil, !Task.isCancelled {
                try? await Task.sleep(for: .seconds(3))
                guard !Task.isCancelled else { return }
                await model.loadNightTasks()
            }
        }
    }

    private var subtitle: String {
        guard let night else { return "Co noc na serwerze" }
        return "Co noc od \(night.nightStart) do \(night.nightEnd). Tu możesz uruchomić je teraz."
    }

    private func allButton(_ night: NightTasks) -> some View {
        Button {
            confirmAll = true
        } label: {
            Label("Uruchom wszystkie teraz", systemImage: "moon.stars.fill")
                .font(.subheadline.weight(.semibold))
                .frame(maxWidth: .infinity)
        }
        .buttonStyle(.borderedProminent)
        .tint(Theme.ink)
        .controlSize(.large)
        .confirmationDialog("Uruchomić cały pakiet?", isPresented: $confirmAll, titleVisibility: .visible) {
            Button("Uruchom wszystkie (\(night.tasks.count))") {
                Task { await model.startNightTasks() }
            }
            Button("Anuluj", role: .cancel) {}
        } message: {
            Text("Zadania pójdą po kolei, tak jak w nocy, najwyżej przez 2 godziny. Część z nich pyta Claude'a: koszt z Twojego klucza.")
        }
    }
}

/// A package of tasks: what it does, when it last ran, a button to start
/// all of it, and its tasks folded away.
private struct NightGroupCard: View {
    @Environment(AppModel.self) private var model
    @State private var open = false
    @State private var confirm = false
    let night: NightTasks
    let group: NightTasks.Group

    private var entries: [NightTasks.Entry] { night.entries(of: group) }
    private var isRunning: Bool {
        guard let running = night.running else { return false }
        return group.tasks.contains { running.tasks.contains($0) && !running.done.contains($0) }
    }

    var body: some View {
        Card(padding: 0) {
            VStack(alignment: .leading, spacing: 0) {
                HStack(alignment: .top, spacing: 12) {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 6) {
                            Text(group.label)
                                .font(.headline)
                                .foregroundStyle(Theme.ink)
                            if entries.contains(where: \.paid) {
                                Image(systemName: "sparkle")
                                    .font(.caption)
                                    .foregroundStyle(Theme.inkSoft)
                                    .accessibilityLabel("część pyta Claude'a")
                            }
                        }
                        Text(group.about)
                            .font(.caption)
                            .foregroundStyle(Theme.inkSoft)
                            .fixedSize(horizontal: false, vertical: true)
                        if let last = lastText {
                            Text(last.text)
                                .font(.caption)
                                .foregroundStyle(last.warn ? Theme.warn : Theme.inkSoft)
                        }
                    }
                    Spacer(minLength: 8)
                    startButton
                }
                .padding(16)
                Divider().padding(.leading, 16)
                Button {
                    withAnimation(.snappy) { open.toggle() }
                } label: {
                    HStack {
                        Text(open ? "Schowaj zadania" : "Zadania (\(entries.count))")
                            .font(.subheadline)
                        Spacer()
                        Image(systemName: "chevron.down")
                            .font(.footnote.weight(.semibold))
                            .rotationEffect(.degrees(open ? 180 : 0))
                    }
                    .foregroundStyle(Theme.inkSoft)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                if open {
                    Divider().padding(.leading, 16)
                    NightTaskRows(tasks: entries, running: night.running)
                }
            }
        }
    }

    @ViewBuilder private var startButton: some View {
        if isRunning {
            ProgressView()
                .frame(width: 36, height: 36)
        } else {
            Button {
                confirm = true
            } label: {
                Image(systemName: "play.fill")
                    .font(.subheadline.weight(.semibold))
                    .frame(width: 36, height: 36)
            }
            .buttonStyle(.bordered)
            .buttonBorderShape(.circle)
            .tint(Theme.ink)
            .disabled(night.running != nil)
            .accessibilityLabel("Uruchom pakiet: \(group.label)")
            .confirmationDialog(group.label, isPresented: $confirm, titleVisibility: .visible) {
                Button("Uruchom pakiet (\(entries.count))") {
                    Task { await model.startNightTasks(group.tasks, title: group.label) }
                }
                Button("Anuluj", role: .cancel) {}
            } message: {
                if entries.contains(where: \.paid) {
                    Text("Zadania pójdą po kolei, najwyżej przez 2 godziny. Część z nich pyta Claude'a: koszt z Twojego klucza.")
                } else {
                    Text("Zadania pójdą po kolei, najwyżej przez 2 godziny.")
                }
            }
        }
    }

    /// "Ostatnio dziś, 03:25 · 12 min", "Jeszcze nie było", "Był błąd".
    private var lastText: (text: String, warn: Bool)? {
        let runs = entries.compactMap(\.last)
        if runs.contains(where: \.failed) { return ("Ostatnio był błąd", true) }
        guard let latest = runs.max(by: { $0.at < $1.at }) else { return ("Jeszcze nie było", false) }
        let took = runs.filter { $0.at.prefix(10) == latest.at.prefix(10) }.reduce(0) { $0 + $1.took }
        let never = entries.count - runs.count
        var parts = ["Ostatnio " + (When.past(latest.at) ?? "")]
        parts.append(NightDuration.text(took))
        if never > 0 { parts.append("\(never) jeszcze nie było") }
        return (parts.joined(separator: " · "), false)
    }
}

/// Tasks one under another, each with its button.
private struct NightTaskRows: View {
    let tasks: [NightTasks.Entry]
    let running: NightTasks.Running?

    var body: some View {
        VStack(spacing: 0) {
            ForEach(Array(tasks.enumerated()), id: \.element.id) { index, task in
                if index > 0 {
                    Divider().padding(.leading, 16)
                }
                NightTaskRow(task: task, running: running)
            }
        }
    }
}

/// What runs now: the task, how far along, and a way to stop it.
private struct RunningCard: View {
    @Environment(AppModel.self) private var model
    let night: NightTasks
    let running: NightTasks.Running

    var body: some View {
        Card {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(running.asked ? "Trwa na żądanie" : "Trwa nocna praca")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(Theme.inkSoft)
                    Text(night.label(running.current) ?? (running.stopping ? "Zatrzymuję…" : "Zaczynam…"))
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(Theme.ink)
                }
                Spacer()
                Text("\(min(running.done.count + 1, running.tasks.count)) z \(running.tasks.count)")
                    .font(.subheadline.monospacedDigit())
                    .foregroundStyle(Theme.inkSoft)
            }
            ProgressView(value: Double(running.done.count), total: Double(max(running.tasks.count, 1)))
                .tint(Theme.ink)
            if let since = When.since(running.startedAt) {
                Text("Uruchomione \(since)")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
            }
            if running.asked {
                Button(role: .destructive) {
                    Task { await model.stopNightTasks() }
                } label: {
                    Label(running.stopping ? "Zatrzymuję" : "Zatrzymaj", systemImage: "stop.fill")
                        .font(.subheadline.weight(.medium))
                }
                .buttonStyle(.bordered)
                .disabled(running.stopping)
            }
        }
    }
}

/// One task: its name, how it last went, and a button to start it now.
private struct NightTaskRow: View {
    @Environment(AppModel.self) private var model
    @State private var confirm = false
    let task: NightTasks.Entry
    let running: NightTasks.Running?

    private var isCurrent: Bool { running?.current == task.name }
    private var isWaiting: Bool {
        guard let running else { return false }
        return running.tasks.contains(task.name) && !running.done.contains(task.name) && !isCurrent
    }

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(task.label)
                        .font(.subheadline)
                        .foregroundStyle(Theme.ink)
                    if task.paid {
                        Image(systemName: "sparkle")
                            .font(.caption2)
                            .foregroundStyle(Theme.inkSoft)
                            .accessibilityLabel("pyta Claude'a")
                    }
                }
                if let last = lastText {
                    Text(last.text)
                        .font(.caption)
                        .foregroundStyle(last.warn ? Theme.warn : Theme.inkSoft)
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 8)
            if isCurrent {
                ProgressView()
            } else if isWaiting {
                Image(systemName: "clock")
                    .foregroundStyle(Theme.inkSoft)
                    .accessibilityLabel("czeka w kolejce")
            } else {
                Button {
                    confirm = true
                } label: {
                    Image(systemName: "play.fill")
                        .font(.footnote.weight(.semibold))
                        .frame(width: 30, height: 30)
                }
                .buttonStyle(.bordered)
                .buttonBorderShape(.circle)
                .tint(Theme.ink)
                .disabled(running != nil)
                .accessibilityLabel("Uruchom: \(task.label)")
                .confirmationDialog(task.label, isPresented: $confirm, titleVisibility: .visible) {
                    Button("Uruchom teraz") {
                        Task { await model.startNightTasks([task.name]) }
                    }
                    Button("Anuluj", role: .cancel) {}
                } message: {
                    if task.paid {
                        Text("Pyta Claude'a: koszt z Twojego klucza.")
                    }
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    /// "dziś, 03:12 · 14 s · 3", "Nic do zrobienia", "Błąd".
    private var lastText: (text: String, warn: Bool)? {
        guard let last = task.last else { return ("Jeszcze nie było", false) }
        var parts = [When.past(last.at) ?? ""]
        parts.append(NightDuration.text(last.took))
        if last.failed {
            parts.append("błąd")
        } else if last.nothing {
            parts.append("nic do zrobienia")
        } else if let count = last.count {
            parts.append("\(count)")
        }
        if last.asked { parts.append("na żądanie") }
        return (parts.filter { !$0.isEmpty }.joined(separator: " · "), last.failed)
    }
}

enum NightDuration {
    /// "0,4 s", "14 s", "6 min", "1 h 20 min".
    static func text(_ seconds: Double) -> String {
        if seconds < 10 {
            return seconds.formatted(.number.precision(.fractionLength(1)).locale(Locale(identifier: "pl_PL"))) + " s"
        }
        if seconds < 90 { return "\(Int(seconds.rounded())) s" }
        let minutes = Int((seconds / 60).rounded())
        if minutes < 60 { return "\(minutes) min" }
        let rest = minutes % 60
        return rest == 0 ? "\(minutes / 60) h" : "\(minutes / 60) h \(rest) min"
    }
}

/// Konfiguracja → Miejsce na serwerze: how many works the server has
/// gathered and how many in large pictures (Mateusz 2026-11-10).
struct CatalogueCountSection: View {
    let counts: CatalogueCounts

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Zebrane dzieła", subtitle: "Ile dzieł ma serwer i ile w dużej rozdzielczości")
            Card {
                VStack(alignment: .leading, spacing: 8) {
                    Text(Names.worksGrouped(counts.works))
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(Theme.ink)
                    row("Wszystkie obrazy z muzeów, z kopiami i detalami", counts.pictures)
                }
                Divider()
                VStack(alignment: .leading, spacing: 8) {
                    row("W dużej rozdzielczości na serwerze", counts.originals)
                    row("W tym co najmniej 2560 px (pełny ekran ramki)", counts.frameSize)
                    Text("Reszta to miniatury: duży obraz serwer pobiera, gdy jest potrzebny.")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
                if counts.own > 0 {
                    Divider()
                    row("Twoje prace i zdjęcia", counts.own)
                }
            }
        }
    }

    private func row(_ title: String, _ count: Int) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title)
                .font(.subheadline)
                .foregroundStyle(Theme.ink)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 12)
            Text(count.grouped)
                .font(.subheadline.monospacedDigit())
                .foregroundStyle(Theme.inkSoft)
        }
    }
}

extension Int {
    /// "70 239": thousands apart, as in Polish.
    var grouped: String {
        formatted(.number.grouping(.automatic).locale(Locale(identifier: "pl_PL")))
    }
}

extension Names {
    /// "70 239 dzieł": as `works`, the number with its thousands apart.
    static func worksGrouped(_ count: Int) -> String {
        let text = works(count)
        guard let space = text.firstIndex(of: " ") else { return text }
        return count.grouped + String(text[space...])
    }
}
