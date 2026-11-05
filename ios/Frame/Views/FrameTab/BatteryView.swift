import SwiftUI

/// Behind the Bateria tile: how long the battery lasts at the schedule set
/// from the level now, the last week's readings with the drop ahead, a day
/// of the frame's (each thing, how many times and what it costs) and how
/// well the costs fit the last day on battery. The server learns the costs
/// from the readings on battery: at first they are the ones measured in
/// tests and the range is wide.
struct BatteryView: View {
    @Environment(\.dismiss) private var dismiss
    let estimate: BatteryEstimate
    let onBattery: Bool
    var economy = false
    var charging = false

    var body: some View {
        NavigationStack {
            List {
                Section {
                    header.padding(.vertical, 4)
                }
                .listRowBackground(Theme.card)
                if let recent = estimate.recent, recent.count >= 2 {
                    Section {
                        BatteryChart(
                            readings: recent,
                            level: onBattery ? (estimate.level ?? estimate.readLevel ?? recent.last?.level) : nil,
                            days: onBattery ? estimate.days : nil,
                            low: estimate.daysLow,
                            high: estimate.daysHigh
                        )
                        .frame(height: 150)
                        .padding(.vertical, 6)
                    } header: {
                        Text("Ostatni tydzień i dalej")
                    }
                    .listRowBackground(Theme.card)
                }
                Section {
                    if lines.count > 1 {
                        BatteryStack(lines: lines)
                            .frame(height: 12)
                            .padding(.vertical, 6)
                    }
                    ForEach(lines) { line in
                        lineRow(line)
                    }
                } header: {
                    HStack {
                        Text("Dzień ramki")
                        Spacer()
                        Text("\(BatteryText.percent(estimate.perDay)) na dobę")
                            .textCase(nil)
                            .font(.subheadline)
                            .foregroundStyle(Theme.ink)
                    }
                } footer: {
                    Text(dayFooter)
                }
                .listRowBackground(Theme.card)
                Section {
                    fit
                } header: {
                    Text("Trafność")
                } footer: {
                    Text(basis)
                }
                .listRowBackground(Theme.card)
            }
            .scrollContentBackground(.hidden)
            .paperPage()
            .navigationTitle("Bateria")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Gotowe") { dismiss() } }
            }
        }
        .presentationDetents([.large])
    }

    // MARK: The answer

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 16) {
                ring
                VStack(alignment: .leading, spacing: 4) {
                    Text(headline)
                        .font(.serif(28, weight: .semibold))
                        .foregroundStyle(Theme.ink)
                    Text(subline)
                        .font(.subheadline)
                        .foregroundStyle(Theme.inkSoft)
                }
            }
            if let sinceReading {
                Divider()
                Text(sinceReading)
                    .font(.footnote)
                    .foregroundStyle(Theme.inkSoft)
            }
        }
    }

    private var latestLevel: Int? { estimate.recent?.last?.level }

    /// The ring of the tile, with the level inside instead of beside it.
    private var ring: some View {
        let shown = onBattery ? (estimate.level ?? estimate.readLevel ?? latestLevel) : latestLevel
        let fraction = Double(shown ?? 0) / 100
        let color: Color = charging ? Theme.warn : (shown ?? 100) <= 15 ? Theme.bad : (shown ?? 100) <= 35 ? Theme.warn : Theme.good
        return ZStack {
            Circle().stroke(Theme.mat, lineWidth: 9)
            if let read = estimate.readLevel, estimate.level != nil, onBattery {
                Circle()
                    .trim(from: 0, to: Double(read) / 100)
                    .stroke(color.opacity(0.32), style: StrokeStyle(lineWidth: 9))
                    .rotationEffect(.degrees(-90))
            }
            Circle()
                .trim(from: 0, to: fraction)
                .stroke(color, style: StrokeStyle(lineWidth: 9, lineCap: .butt))
                .rotationEffect(.degrees(-90))
            Text(shown.map { "\($0)%" } ?? "—")
                .font(.serif(15, weight: .semibold))
                .monospacedDigit()
                .foregroundStyle(Theme.ink)
        }
        .frame(width: 70, height: 70)
        .accessibilityHidden(true)
    }

    private var headline: String {
        if onBattery, let days = estimate.days {
            return "ok. " + BatteryText.span(days, low: nil, high: nil)
        }
        return "ok. " + BatteryText.span(estimate.fullDays, low: nil, high: nil)
    }

    /// "do ok. 17 listopada" and the likely range; on the charger what a
    /// full battery would give.
    private var subline: String {
        let perDay = "\(BatteryText.percent(estimate.perDay)) na dobę"
        let onIt = onBattery && estimate.days != nil
        let (days, low, high) = onIt
            ? (estimate.days ?? 0, estimate.daysLow, estimate.daysHigh)
            : (estimate.fullDays, estimate.fullDaysLow, estimate.fullDaysHigh)
        let span = BatteryText.span(days, low: low, high: high)
        let range = span.contains("–") ? "najpewniej \(span) · \(perDay)" : perDay
        guard onIt else { return "na pełnej baterii\n\(range)" }
        return "do ok. \(BatteryText.until(days))\n\(range)"
    }

    /// Asleep the frame reads nothing: the level now is the server's guess.
    private var sinceReading: String? {
        guard onBattery, let level = estimate.level, let read = estimate.readLevel else {
            return onBattery ? nil : "Na zasilaczu: prognoza ruszy po odpięciu, od poziomu w tej chwili."
        }
        let when = When.clock(estimate.readAt).map { " o \($0)" } ?? ""
        return "Ramka śpi, więc \(level)% to szacunek od ostatniego odczytu \(read)%\(when)."
    }

    // MARK: A day of the frame's

    /// The day as the server breaks it down; from an older server the four
    /// totals it sends.
    private var lines: [BatteryLine] {
        if let lines = estimate.day.lines, !lines.isEmpty { return lines }
        let day = estimate.day
        let old = [
            BatteryLine(kind: "standby", count: day.standbyHours, each: day.standbyHours > 0 ? day.standbyCost / day.standbyHours : 0, cost: day.standbyCost),
            BatteryLine(kind: "deep", count: day.deepHours, each: day.deepHours > 0 ? day.deepCost / day.deepHours : 0, cost: day.deepCost),
            BatteryLine(kind: "wakes", count: day.wakes, each: day.wakes > 0 ? day.wakesCost / day.wakes : 0, cost: day.wakesCost),
            BatteryLine(kind: "changes", count: day.changes, each: day.changes > 0 ? day.changesCost / day.changes : 0, cost: day.changesCost),
        ]
        return old.filter { $0.count > 0 }.sorted { $0.cost > $1.cost }
    }

    private func lineRow(_ line: BatteryLine) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            RoundedRectangle(cornerRadius: 3)
                .fill(BatteryStack.color(line.kind))
                .frame(width: 10, height: 10)
            VStack(alignment: .leading, spacing: 2) {
                Text(BatteryText.lineTitle(line.kind)).foregroundStyle(Theme.ink)
                Text(detail(line)).font(.caption).foregroundStyle(Theme.inkSoft)
            }
            Spacer(minLength: 8)
            VStack(alignment: .trailing, spacing: 2) {
                Text(BatteryText.percent(line.cost))
                    .monospacedDigit()
                    .foregroundStyle(Theme.ink)
                let measured = learnt(line.kind)
                Text(measured >= 0.6 ? "zmierzone" : measured >= 0.2 ? "częściowo zmierzone" : "założenie")
                    .font(.caption2)
                    .foregroundStyle(measured >= 0.6 ? Theme.good : Theme.inkSoft)
            }
        }
    }

    private func detail(_ line: BatteryLine) -> String {
        let each = BatteryText.percent(line.each)
        let costs = estimate.costs
        switch line.kind {
        case "standby":
            return "\(BatteryText.hours(line.count)) · \(each) na godzinę"
        case "deep":
            return BatteryText.hours(line.count)
        case "checks":
            let minutes = costs.checkMinutes.map { " i ok. \(BatteryText.minutes($0)) jest w sieci" } ?? ""
            return "\(BatteryText.times(line.count)) × \(each) · ramka wstaje\(minutes)"
        case "changes":
            let minutes = costs.appAwakeMinutes.map { ", ok. \(BatteryText.minutes($0))" } ?? ""
            if line.count < 0.95 {
                return "\(BatteryText.every(line.count)) × \(each) · pobudka\(minutes), rysowanie"
            }
            return "\(BatteryText.times(line.count)) × \(each) · pobudka\(minutes), rysowanie"
        case "wakes":
            return "\(BatteryText.times(line.count)) × \(each) · pobudka bez nowego obrazu"
        case "sends":
            let daily = "ok. \(BatteryText.times(line.count)) dziennie"
            return economy
                ? "\(daily) · czeka na kontrolę, więc głównie rysowanie"
                : "\(daily) · każdy budzi ramkę"
        default:
            return BatteryText.times(line.count)
        }
    }

    /// The costs' `learnt` (standby, deep sleep, wake, change) for a line.
    private func learnt(_ kind: String) -> Double {
        let index = switch kind {
        case "standby": 0
        case "deep": 1
        case "sends": 3
        default: 2
        }
        return index < estimate.costs.learnt.count ? estimate.costs.learnt[index] : 0
    }

    private var dayFooter: String {
        let sends = estimate.day.lines?.contains { $0.kind == "sends" } ?? false
        let base = "Według harmonogramu, od pobudek zmierzonych na baterii."
        return sends ? base + " Obrazy z aplikacji to średnia z ostatnich dwóch tygodni." : base + " Obrazy wysłane z aplikacji dojdą, gdy jakieś wyślesz."
    }

    // MARK: How well it fits

    @ViewBuilder private var fit: some View {
        if let check = estimate.check {
            let close = abs(check.used - check.expected) <= max(2, check.used * 0.25)
            HStack(spacing: 12) {
                Image(systemName: close ? "checkmark" : "exclamationmark")
                    .font(.footnote.weight(.bold))
                    .foregroundStyle(close ? Theme.good : Theme.warn)
                    .frame(width: 28, height: 28)
                    .background(Circle().fill((close ? Theme.good : Theme.warn).opacity(0.14)))
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(BatteryText.lastSpan(check.hours)): zużyła \(BatteryText.percent(check.used))")
                        .foregroundStyle(Theme.ink)
                    Text(close
                        ? "Wyliczone z tego, co ramka robiła: \(BatteryText.percent(check.expected))."
                        : "Wyliczone \(BatteryText.percent(check.expected)); z kolejnymi odczytami prognoza się poprawi.")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
            }
        } else {
            HStack(spacing: 12) {
                Image(systemName: "ellipsis")
                    .font(.footnote.weight(.bold))
                    .foregroundStyle(Theme.inkSoft)
                    .frame(width: 28, height: 28)
                    .background(Circle().fill(Theme.mat))
                VStack(alignment: .leading, spacing: 2) {
                    Text("Jeszcze za mało danych").foregroundStyle(Theme.ink)
                    Text("Po pierwszej dobie na baterii pokażę, ile zużyła naprawdę.")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                }
            }
        }
    }

    private var basis: String {
        let hours = estimate.hoursMeasured
        guard hours >= 1 else {
            return "Na razie to założenia z testów tej ramki. Serwer zapisuje poziom baterii przy każdej pobudce na baterii i z każdym dniem prognoza jest dokładniejsza."
        }
        let span = hours >= 48 ? "\(Int(hours / 24)) dni" : "\(Int(hours)) godz."
        return "Z \(span) na baterii (\(estimate.readings) odczytów poziomu). Każdy dzień na baterii zawęża zakres."
    }
}

/// The day's parts side by side, as wide as their share of it.
struct BatteryStack: View {
    let lines: [BatteryLine]

    static func color(_ kind: String) -> Color {
        switch kind {
        case "checks": Color(light: 0x2D4B73, dark: 0x8FA9CC)
        case "changes": Theme.good
        case "sends": Theme.warn
        case "standby": Theme.vermilion
        case "wakes": Color(light: 0x7A5C8E, dark: 0xB79CCB)
        default: Theme.markInfo
        }
    }

    var body: some View {
        GeometryReader { geometry in
            let total = max(lines.reduce(0) { $0 + $1.cost }, 0.0001)
            HStack(spacing: 0) {
                ForEach(lines) { line in
                    Self.color(line.kind)
                        .frame(width: geometry.size.width * line.cost / total)
                }
            }
            .clipShape(Capsule())
        }
        .accessibilityHidden(true)
    }
}

/// The week's readings on battery and the drop ahead at the schedule set:
/// a dashed line to empty, in a band from the likely range.
struct BatteryChart: View {
    let readings: [BatteryReading]
    /// Where the level is now, and the days it lasts (nil on the charger).
    let level: Int?
    let days: Double?
    let low: Double?
    let high: Double?
    var now: Date = .now

    private static let polish = Locale(identifier: "pl_PL")

    var body: some View {
        GeometryReader { geometry in
            let points = readings.compactMap { reading in reading.date.map { ($0, reading.level) } }
            let start = points.first?.0 ?? now.addingTimeInterval(-7 * 86400)
            let ahead = min(high ?? days ?? 0, max((days ?? 0) * 1.6, 1), 120)
            let end = days == nil ? now : now.addingTimeInterval(ahead * 86400)
            let left: CGFloat = 38, bottom: CGFloat = 18
            let width = geometry.size.width - left - 4, height = geometry.size.height - bottom - 6
            let span = max(end.timeIntervalSince(start), 3600)
            let x = { (date: Date) -> CGFloat in left + width * CGFloat(date.timeIntervalSince(start) / span) }
            let y = { (level: Double) -> CGFloat in 6 + height * CGFloat(1 - level / 100) }
            ZStack(alignment: .topLeading) {
                ForEach([100.0, 50.0, 0.0], id: \.self) { mark in
                    Path { path in
                        path.move(to: CGPoint(x: left, y: y(mark)))
                        path.addLine(to: CGPoint(x: geometry.size.width, y: y(mark)))
                    }
                    .stroke(Theme.hairline, lineWidth: 0.5)
                    Text(mark == 0 ? "0" : "\(Int(mark))%")
                        .font(.system(size: 10))
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(1)
                        .fixedSize()
                        .frame(width: left - 6, alignment: .trailing)
                        .position(x: (left - 6) / 2, y: y(mark))
                }
                if let level, let days {
                    let from = CGPoint(x: x(now), y: y(Double(level)))
                    if let low, let high {
                        Path { path in
                            path.move(to: from)
                            path.addLine(to: CGPoint(x: min(x(now.addingTimeInterval(low * 86400)), x(end)), y: y(0)))
                            let far = now.addingTimeInterval(high * 86400)
                            if far <= end {
                                path.addLine(to: CGPoint(x: x(far), y: y(0)))
                            } else {
                                let remaining = Double(level) * (1 - end.timeIntervalSince(now) / (high * 86400))
                                path.addLine(to: CGPoint(x: x(end), y: y(0)))
                                path.addLine(to: CGPoint(x: x(end), y: y(max(remaining, 0))))
                            }
                            path.closeSubpath()
                        }
                        .fill(Theme.good.opacity(0.12))
                    }
                    Path { path in
                        path.move(to: from)
                        path.addLine(to: CGPoint(x: x(now.addingTimeInterval(days * 86400)), y: y(0)))
                    }
                    .stroke(Theme.good, style: StrokeStyle(lineWidth: 2, dash: [5, 4]))
                    Path { path in
                        path.move(to: CGPoint(x: x(now), y: 2))
                        path.addLine(to: CGPoint(x: x(now), y: y(0)))
                    }
                    .stroke(Theme.ink.opacity(0.25), style: StrokeStyle(lineWidth: 1, dash: [2, 3]))
                    Text("dziś")
                        .font(.system(size: 10))
                        .foregroundStyle(Theme.ink)
                        .position(x: x(now) + 14, y: 10)
                }
                Path { path in
                    for (index, point) in points.enumerated() {
                        let spot = CGPoint(x: x(point.0), y: y(Double(point.1)))
                        if index == 0 { path.move(to: spot) } else { path.addLine(to: spot) }
                    }
                }
                .stroke(Theme.good, style: StrokeStyle(lineWidth: 2, lineJoin: .round))
                ForEach(Array(points.enumerated()), id: \.offset) { _, point in
                    Circle()
                        .fill(Theme.good)
                        .frame(width: 4.5, height: 4.5)
                        .position(x: x(point.0), y: y(Double(point.1)))
                }
                ForEach(Self.ticks(start: start, end: end, now: now), id: \.self) { tick in
                    Text(tick.formatted(.dateTime.day().month(.defaultDigits).locale(Self.polish)))
                        .font(.system(size: 10))
                        .foregroundStyle(Theme.inkSoft)
                        .position(x: min(max(x(tick), left + 12), geometry.size.width - 16), y: geometry.size.height - 6)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibility)
    }

    /// The first day, today and the day it runs out.
    private static func ticks(start: Date, end: Date, now: Date) -> [Date] {
        var ticks = [start]
        if now.timeIntervalSince(start) > 86400 { ticks.append(now) }
        if end.timeIntervalSince(now) > 86400 { ticks.append(end) }
        return ticks
    }

    private var accessibility: String {
        let first = readings.first.map { "od \($0.level)%" } ?? ""
        let last = level.map { " do \($0)% dziś" } ?? ""
        let ahead = days.map { ", wystarczy na ok. \(BatteryText.span($0, low: nil, high: nil))" } ?? ""
        return "Bateria w ostatnim tygodniu \(first)\(last)\(ahead)"
    }
}

/// Days, hours and percent as the battery tile and sheet say them.
enum BatteryText {
    private static let polish = Locale(identifier: "pl_PL")

    /// "7 dni", "5–9 dni" (a range only when it is wide), "ok. 3 mies.",
    /// "18 godz."; the caller adds "ok.".
    static func span(_ days: Double, low: Double?, high: Double?) -> String {
        let unit = days > 60 ? "mies." : days >= 2 ? "dni" : "godz."
        func value(_ days: Double) -> Int {
            switch unit {
            case "mies.": Int((days / 30).rounded())
            case "dni": Int(days.rounded())
            default: max(1, Int((days * 24).rounded()))
            }
        }
        let middle = value(days)
        if let low, let high, low > 0, high / low >= 1.35 {
            let from = min(value(low), middle), to = max(value(high), middle)
            if from < to { return "\(from)–\(to) \(unit)" }
        }
        if unit == "dni", middle == 1 { return "1 dzień" }
        return "\(middle) \(unit)"
    }

    /// The same with no line break inside (word joiners, no-break space).
    static func unbroken(_ text: String) -> String {
        text.replacingOccurrences(of: "–", with: "\u{2060}–\u{2060}")
            .replacingOccurrences(of: " ", with: "\u{00A0}")
    }

    static func percent(_ value: Double) -> String {
        if value > 0, value < 0.1 { return "<0,1%" }
        let digits = value < 10 ? 1 : 0
        return value.formatted(.number.precision(.fractionLength(0...digits)).locale(polish)) + "%"
    }

    static func hours(_ value: Double) -> String {
        value.formatted(.number.precision(.fractionLength(0...1)).locale(polish)) + " godz."
    }

    /// "17 listopada": the day ``days`` from now.
    static func until(_ days: Double, from now: Date = .now) -> String {
        let date = now.addingTimeInterval(days * 86400)
        let formatter = DateFormatter()
        formatter.locale = polish
        formatter.dateFormat = "d MMMM"
        return formatter.string(from: date)
    }

    /// "Puste kontrole", "Zmiany obrazu"… for a line of a day.
    static func lineTitle(_ kind: String) -> String {
        switch kind {
        case "standby": "Czuwanie w sieci"
        case "deep": "Sen bez Wi-Fi"
        case "checks": "Puste kontrole"
        case "changes": "Zmiany obrazu"
        case "wakes": "Pobudki na ciszę nocną"
        case "sends": "Obrazy z aplikacji"
        default: kind
        }
    }

    /// "7", "0,5": how many times a day.
    static func times(_ value: Double) -> String {
        value.formatted(.number.precision(.fractionLength(0...1)).locale(polish))
    }

    /// "co 2 dni" for a change every other day (0,5 a day).
    static func every(_ perDay: Double) -> String {
        guard perDay > 0 else { return "0" }
        let days = Int((1 / perDay).rounded())
        return days <= 1 ? "1" : "co \(days) dni"
    }

    /// "2,5 min".
    static func minutes(_ value: Double) -> String {
        "\(value.formatted(.number.precision(.fractionLength(0...1)).locale(polish))) min"
    }

    /// "Ostatnia doba", "Ostatnie 14 godz.".
    static func lastSpan(_ hours: Double) -> String {
        hours >= 20 ? "Ostatnia doba" : "Ostatnie \(Int(hours.rounded())) godz."
    }

    /// "1 pobudka", "2 pobudki", "5 pobudek", "1,5 pobudki".
    static func count(_ value: Double, one: String, few: String, many: String) -> String {
        let text = value.formatted(.number.precision(.fractionLength(0...1)).locale(polish))
        guard value == value.rounded() else { return "\(text) \(few)" }
        let n = Int(value)
        if n == 1 { return "1 \(one)" }
        let tens = n % 100, ones = n % 10
        let word = (2...4).contains(ones) && !(12...14).contains(tens) ? few : many
        return "\(n) \(word)"
    }
}
