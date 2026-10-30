import SwiftUI

/// Behind the Bateria tile: how long the battery lasts at the schedule set,
/// a day of the frame's and what each thing in it costs. The server learns
/// the costs from the readings on battery, so at first they are the ones
/// measured on other EM32DX frames and the range is wide.
struct BatteryView: View {
    @Environment(\.dismiss) private var dismiss
    let estimate: BatteryEstimate
    let onBattery: Bool

    var body: some View {
        NavigationStack {
            List {
                Section {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(headline)
                            .font(.serif(24, weight: .semibold))
                            .foregroundStyle(Theme.ink)
                        Text(rangeLine)
                            .font(.subheadline)
                            .foregroundStyle(Theme.inkSoft)
                    }
                    .padding(.vertical, 4)
                }
                Section {
                    row("Czuwanie w sieci", detail: "\(BatteryText.hours(estimate.day.standbyHours)) dziennie", cost: estimate.day.standbyCost)
                    row("Sen bez Wi-Fi", detail: "\(BatteryText.hours(estimate.day.deepHours)) dziennie", cost: estimate.day.deepCost)
                    row("Pobudki", detail: BatteryText.count(estimate.day.wakes, one: "pobudka", few: "pobudki", many: "pobudek") + " dziennie", cost: estimate.day.wakesCost)
                    row("Zmiany obrazu", detail: BatteryText.count(estimate.day.changes, one: "zmiana", few: "zmiany", many: "zmian") + " dziennie", cost: estimate.day.changesCost)
                } header: {
                    Text("Dzień ramki")
                } footer: {
                    Text("Według harmonogramu; obrazy wysłane z aplikacji to dodatkowe pobudki i zmiany.")
                }
                Section {
                    cost("Czuwanie w sieci", value: "\(BatteryText.percent(estimate.costs.standbyPerDay)) na dobę", learnt: learnt(0))
                    cost("Sen bez Wi-Fi", value: "\(BatteryText.percent(estimate.costs.deepPerDay)) na dobę", learnt: learnt(1))
                    cost("Pobudka", value: "\(BatteryText.percent(estimate.costs.perWake)) za każdą", learnt: learnt(2))
                    cost("Zmiana obrazu", value: "\(BatteryText.percent(estimate.costs.perChange)) za każdą", learnt: learnt(3))
                } header: {
                    Text("Ile to kosztuje")
                } footer: {
                    Text(basis)
                }
            }
            .scrollContentBackground(.hidden)
            .background(Theme.paper)
            .navigationTitle("Bateria")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Gotowe") { dismiss() } }
            }
        }
        .presentationDetents([.large])
    }

    private var headline: String {
        if onBattery, let days = estimate.days {
            return "Wystarczy na ok. " + BatteryText.span(days, low: nil, high: nil)
        }
        return "Pełna bateria: ok. " + BatteryText.span(estimate.fullDays, low: nil, high: nil)
    }

    private var rangeLine: String {
        let perDay = "\(BatteryText.percent(estimate.perDay)) dziennie przy obecnym harmonogramie"
        let (days, low, high) = onBattery && estimate.days != nil
            ? (estimate.days ?? 0, estimate.daysLow, estimate.daysHigh)
            : (estimate.fullDays, estimate.fullDaysLow, estimate.fullDaysHigh)
        let span = BatteryText.span(days, low: low, high: high)
        guard span.contains("–") else { return perDay }
        return "Najpewniej \(span) · \(perDay)"
    }

    private var basis: String {
        let hours = estimate.hoursMeasured
        guard hours >= 1 else {
            return "Na razie to założenia z pomiarów innych ramek EM32DX. Serwer zapisuje poziom baterii przy każdej pobudce na baterii i z każdym dniem szacunek jest dokładniejszy."
        }
        let span = hours >= 48 ? "\(Int(hours / 24)) dni" : "\(Int(hours)) godz."
        return "Z \(span) na baterii (\(estimate.readings) odczytów poziomu). Im dłużej ramka pracuje na baterii, tym dokładniej; na zasilaczu pomiar czeka."
    }

    private func learnt(_ index: Int) -> Double {
        index < estimate.costs.learnt.count ? estimate.costs.learnt[index] : 0
    }

    private func row(_ title: String, detail: String, cost: Double) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).foregroundStyle(Theme.ink)
                Text(detail).font(.caption).foregroundStyle(Theme.inkSoft)
            }
            Spacer()
            Text(BatteryText.percent(cost))
                .monospacedDigit()
                .foregroundStyle(Theme.ink)
        }
        .listRowBackground(Theme.card)
    }

    private func cost(_ title: String, value: String, learnt: Double) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).foregroundStyle(Theme.ink)
                Text(learnt >= 0.6 ? "zmierzone" : learnt >= 0.2 ? "częściowo zmierzone" : "założenie")
                    .font(.caption)
                    .foregroundStyle(learnt >= 0.6 ? Theme.good : Theme.inkSoft)
            }
            Spacer()
            Text(value)
                .monospacedDigit()
                .foregroundStyle(Theme.ink)
        }
        .listRowBackground(Theme.card)
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
