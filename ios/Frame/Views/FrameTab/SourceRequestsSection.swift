import SwiftUI

/// Konfiguracja → Diagnostyka (Mateusz 2026-11-07: "dane dot. ostatnich
/// ilości zapytań i ew. odmów"): how many requests the server sent to each
/// art source today and over the last days, how many the source turned away
/// (a bot wall, "too many requests", errors) and how many the server held
/// back itself because the source was resting or its quota was spent.
struct SourceRequestsSection: View {
    @Environment(AppModel.self) private var model
    @State private var loading = true
    @State private var showQuiet = false

    private var report: SourceRequests? { model.sourceRequests }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Zapytania do źródeł", subtitle: subtitle)
            Card {
                if let report {
                    summary(report)
                    let active = report.sources.filter { !$0.quiet }
                    ForEach(active) { row in
                        Divider()
                        SourceRequestRow(row: row, days: report.days)
                    }
                    let quiet = report.sources.filter(\.quiet)
                    if !quiet.isEmpty {
                        Divider()
                        quietList(quiet, days: report.days)
                    }
                    Divider()
                    legend
                } else if loading {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                } else {
                    Text("Serwer nie podał liczby zapytań. Starsza wersja serwera ich nie liczy.")
                        .font(.subheadline)
                        .foregroundStyle(Theme.inkSoft)
                }
            }
            Button {
                Task { await reload() }
            } label: {
                Label("Odśwież", systemImage: "arrow.clockwise")
                    .font(.subheadline.weight(.medium))
            }
            .buttonStyle(.bordered)
            .disabled(loading)
        }
        .task { await reload() }
    }

    private var subtitle: String {
        "Dziś i w ostatnich \(report?.days ?? 7) dniach"
    }

    private func reload() async {
        loading = true
        await model.loadSourceRequests()
        loading = false
    }

    private func summary(_ report: SourceRequests) -> some View {
        let today = report.sources.reduce(0) { $0 + $1.today.sent }
        let week = report.sources.reduce(0) { $0 + $1.week.sent }
        let turnedAway = report.sources.reduce(0) { $0 + $1.week.turnedAway }
        let held = report.sources.reduce(0) { $0 + $1.week.refused }
        return VStack(alignment: .leading, spacing: 4) {
            Text(SourceRequestText.requests(today) + " dziś")
                .font(.title3.weight(.semibold))
                .foregroundStyle(Theme.ink)
            Text(SourceRequestText.requests(week) + " w \(report.days) dni")
                .font(.subheadline)
                .foregroundStyle(Theme.inkSoft)
            if turnedAway > 0 || held > 0 {
                Text(SourceRequestText.refusals(turnedAway: turnedAway, held: held))
                    .font(.subheadline)
                    .foregroundStyle(turnedAway > 0 ? Theme.warn : Theme.inkSoft)
            } else {
                Text("Bez odmów")
                    .font(.subheadline)
                    .foregroundStyle(Theme.good)
            }
        }
    }

    private func quietList(_ quiet: [SourceRequests.Row], days: Int) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Button {
                withAnimation(.snappy) { showQuiet.toggle() }
            } label: {
                HStack {
                    Text("Bez zapytań w \(days) dni: \(quiet.count)")
                        .font(.subheadline)
                        .foregroundStyle(Theme.ink)
                    Spacer()
                    Image(systemName: "chevron.down")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(Theme.inkSoft)
                        .rotationEffect(.degrees(showQuiet ? 180 : 0))
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            if showQuiet {
                Text(quiet.map { SourceRequestText.name($0.name) }.joined(separator: ", "))
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
            }
        }
    }

    private var legend: some View {
        Text("Odmowy to odpowiedzi źródła: blokada przed robotami, „za dużo zapytań” (429) i błędy (401, 403, 5xx). Wstrzymane to zapytania, których serwer sam nie wysłał, bo źródło odpoczywa po odmowie albo wyczerpał się jego limit. Część limitu zostaje zawsze na to, na co czekasz w aplikacji.")
            .font(.caption)
            .foregroundStyle(Theme.inkSoft)
    }
}

/// One source: today's and the week's requests, its refusals, quota and rest.
private struct SourceRequestRow: View {
    let row: SourceRequests.Row
    let days: Int

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(SourceRequestText.name(row.name))
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(2)
                Spacer(minLength: 8)
                Text("\(row.today.sent.formatted(.number.locale(SourceRequestText.polish))) dziś")
                    .font(.subheadline.monospacedDigit())
                    .foregroundStyle(Theme.ink)
            }
            Text(weekLine)
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
            if row.week.turnedAway > 0 {
                Text(turnedAwayLine)
                    .font(.caption)
                    .foregroundStyle(Theme.warn)
            }
            if row.week.refused > 0 {
                Text("Wstrzymane przez serwer: \(row.week.refused)" + todayPart(row.today.refused))
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
            }
            if row.resting > 0 {
                Label("Odpoczywa jeszcze \(SourceRequestText.duration(row.resting))", systemImage: "pause.circle")
                    .font(.caption)
                    .foregroundStyle(Theme.warn)
            }
            if let quota = row.quota {
                quotaView(quota)
            }
        }
        .padding(.vertical, 2)
    }

    private var weekLine: String {
        var line = SourceRequestText.requests(row.week.sent) + " w \(days) dni"
        if row.week.bytes > 0 { line += " · " + ByteSize.bytes(row.week.bytes) }
        return line
    }

    private var turnedAwayLine: String {
        var kinds: [String] = []
        if row.week.walled > 0 { kinds.append("blokada \(row.week.walled)") }
        if row.week.throttled > 0 { kinds.append("429 × \(row.week.throttled)") }
        if row.week.failed > 0 { kinds.append("błędy \(row.week.failed)") }
        return "Odmowy: \(row.week.turnedAway)" + todayPart(row.today.turnedAway) + " (" + kinds.joined(separator: ", ") + ")"
    }

    private func todayPart(_ today: Int) -> String {
        today > 0 ? ", dziś \(today)" : ""
    }

    private func quotaView(_ quota: SourceRequests.Quota) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            ProgressView(value: Double(min(quota.spent, quota.of)), total: Double(max(quota.of, 1)))
                .tint(quota.spent >= quota.background ? Theme.warn : Theme.good)
            Text("Limit: \(quota.spent) z \(quota.of) \(SourceRequestText.window(quota.hours)), w tle do \(quota.background)")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
        }
        .padding(.top, 2)
    }
}

enum SourceRequestText {
    static let polish = Locale(identifier: "pl_PL")

    /// "1 zapytanie", "3 zapytania", "1 204 zapytań".
    static func requests(_ n: Int) -> String {
        let tens = n % 100, ones = n % 10
        let few = (2...4).contains(ones) && !(12...14).contains(tens)
        let word = n == 1 ? "zapytanie" : (few ? "zapytania" : "zapytań")
        return "\(n.formatted(.number.locale(polish))) \(word)"
    }

    static func refusals(turnedAway: Int, held: Int) -> String {
        var parts: [String] = []
        if turnedAway > 0 { parts.append("odmowy źródeł: \(turnedAway)") }
        if held > 0 { parts.append("wstrzymane: \(held)") }
        let text = parts.joined(separator: " · ")
        return text.prefix(1).uppercased() + text.dropFirst()
    }

    /// Hosts of no source: pictures Openverse and Europeana point to.
    static func name(_ name: String?) -> String {
        name ?? "Inne serwery (obrazy z Openverse i Europeany)"
    }

    /// "na godzinę", "na dobę", "na 6 godz.".
    static func window(_ hours: Double) -> String {
        if hours == 1 { return "na godzinę" }
        if hours == 24 { return "na dobę" }
        return "na \(Int(hours.rounded())) godz."
    }

    /// "40 s", "12 min", "1 godz. 5 min".
    static func duration(_ seconds: Double) -> String {
        let s = Int(seconds.rounded())
        if s < 60 { return "\(s) s" }
        let minutes = (s + 59) / 60
        if minutes < 60 { return "\(minutes) min" }
        let hours = minutes / 60, rest = minutes % 60
        return rest == 0 ? "\(hours) godz." : "\(hours) godz. \(rest) min"
    }
}
