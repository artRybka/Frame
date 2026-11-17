import SwiftUI

/// "Uruchom teraz" under a use of the month's rest (Mateusz 2026-11-17:
/// "Dodaj mi opcję wykonania wskazanych zadań „na żądanie, w trybie
/// zwykłym” za określoną kwotę… podaję 50 $ na polskie słowa kluczowe i
/// opisy i mogę je puścić od razu"): the run going, with its works and its
/// money, or the button that starts one and what the last one did.
struct OnDemandRow: View {
    @Environment(AppModel.self) private var model
    let use: LeftoverUse
    /// What a run may be given now (nil: an older server).
    let free: Double?
    @State private var asking = false
    @State private var stopping = false

    var body: some View {
        if let run = use.run, run.running {
            going(run)
        } else {
            VStack(alignment: .leading, spacing: 4) {
                Button {
                    asking = true
                } label: {
                    Label("Uruchom teraz…", systemImage: "bolt")
                        .font(.caption.weight(.semibold))
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .tint(Theme.ink)
                .sheet(isPresented: $asking) { OnDemandSheet(use: use, free: free) }
                if let run = use.run {
                    Text(Self.lastNote(run))
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(.top, 4)
        }
    }

    private func going(_ run: OnDemandRun) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ProgressView(value: min(run.spentUsd, run.usd), total: max(run.usd, 0.01))
                .tint(Theme.ink)
            Text(Self.runningNote(run))
                .font(.caption.monospacedDigit())
                .foregroundStyle(Theme.ink)
                .fixedSize(horizontal: false, vertical: true)
            if run.stopping || stopping {
                Label("Zatrzymuję po bieżących dziełach…", systemImage: "hourglass")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
            } else {
                Button(role: .destructive) {
                    stopping = true
                    Task {
                        await model.stopOnDemand(key: use.key)
                        stopping = false
                    }
                } label: {
                    Label("Zatrzymaj", systemImage: "stop.fill")
                        .font(.caption.weight(.semibold))
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
        .padding(.top, 4)
    }

    /// "Teraz: 936 dzieł · 12,37 z 50,00 USD · w kolejce 124 387".
    static func runningNote(_ run: OnDemandRun) -> String {
        var parts = ["Teraz: \(works(run.done))", "\(Money.usd(run.spentUsd)) z \(Money.usd(run.usd))"]
        if run.waiting == nil {
            parts.append("liczę, co czeka…")
        } else if let left = run.left {
            parts.append("w kolejce \(AiSection.count(left))")
        }
        if run.failed > 0 { parts.append("nieudane \(run.failed)") }
        return parts.joined(separator: " · ")
    }

    /// "Ostatnio teraz: 3786 dzieł za 49,98 z 50,00 USD, 17.11 · kwota
    /// wykorzystana".
    static func lastNote(_ run: OnDemandRun) -> String {
        var line = "Ostatnio teraz: \(works(run.done)) za \(Money.usd(run.spentUsd)) z \(Money.usd(run.usd))"
        if let ended = run.ended, ended.count >= 10 {
            line += ", \(AiSection.dayMonth(String(ended.prefix(10))))"
        }
        if run.failed > 0 { line += ", nieudane \(run.failed)" }
        if let why = run.why { line += " · \(why)" }
        return line
    }

    /// "1 dzieło", "3 dzieła", "12 dzieł".
    static func works(_ n: Int) -> String {
        let count = AiSection.count(n)
        if n == 1 { return "1 dzieło" }
        if [2, 3, 4].contains(n % 10), ![12, 13, 14].contains(n % 100) { return "\(count) dzieła" }
        return "\(count) dzieł"
    }
}

/// The amount for a run now, what it buys and what may be given.
struct OnDemandSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let use: LeftoverUse
    let free: Double?
    @State private var text = "10"
    @State private var starting = false

    static let presets: [Double] = [5, 10, 20, 50, 100]

    private var amount: Double? {
        Double(text.replacingOccurrences(of: ",", with: ".").trimmingCharacters(in: .whitespaces))
    }

    private var tooMuch: Bool {
        guard let amount, let free else { return false }
        return amount > free + 0.005
    }

    private var valid: Bool {
        guard let amount else { return false }
        return amount >= 1 && amount <= 500 && !tooMuch
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(Self.about(use))
                        .font(.subheadline)
                        .foregroundStyle(Theme.inkSoft)
                }
                Section {
                    Picker("Kwota", selection: Binding(
                        get: { amount.flatMap { a in Self.presets.first { $0 == a } } ?? -1 },
                        set: { text = Self.plain($0) }
                    )) {
                        ForEach(Self.presets, id: \.self) { Text("\(Int($0)) $").tag($0) }
                    }
                    .pickerStyle(.segmented)
                    HStack {
                        Text("Inna kwota")
                        Spacer()
                        TextField("10", text: $text)
                            .keyboardType(.decimalPad)
                            .multilineTextAlignment(.trailing)
                            .frame(maxWidth: 100)
                        Text("USD").foregroundStyle(Theme.inkSoft)
                    }
                } header: {
                    Text("Kwota")
                } footer: {
                    Text(footer).foregroundStyle(tooMuch ? Theme.bad : Theme.inkSoft)
                }
            }
            .navigationTitle(use.label)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Anuluj") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    if starting {
                        ProgressView()
                    } else {
                        Button("Uruchom", action: start).disabled(!valid)
                    }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    /// What the amount buys and what may be given.
    private var footer: String {
        var parts: [String] = []
        if let amount, amount > 0, let each = use.nowEachUsd, each > 0 {
            var line = "Za \(Money.usd(amount)) ok. \(OnDemandRow.works(Int(amount / each))) (ok. \(Money.usd(each)) za dzieło)"
            if let waiting = use.waiting { line += ", czeka \(AiSection.count(waiting))" }
            parts.append(line + ".")
        }
        if let free {
            parts.append(
                tooMuch
                    ? "Za dużo: do limitu miesiąca zostało ok. \(Money.usd(free)) po odjęciu zapasu i tego, co już zamówione."
                    : "Dostępne teraz ok. \(Money.usd(free)) (limit miesiąca bez zapasu i tego, co już zamówione)."
            )
        }
        if let amount, amount > 500 { parts.append("Najwyżej 500 USD naraz.") }
        return parts.joined(separator: " ")
    }

    private func start() {
        guard let amount else { return }
        starting = true
        Task {
            let started = await model.startOnDemand(key: use.key, usd: amount)
            starting = false
            if started { dismiss() }
        }
    }

    /// "10" of 10, "12.5" of 12.5.
    static func plain(_ value: Double) -> String {
        value == value.rounded() ? String(Int(value)) : String(value).replacingOccurrences(of: ".", with: ",")
    }

    /// What a run now does, in the use's terms.
    static func about(_ use: LeftoverUse) -> String {
        let common = "Serwer pyta Claude od razu, dzieło po dziele, w trybie zwykłym: po pełnej cenie, ok. dwa razy drożej niż nocą przez Batch. Działa, aż wyda kwotę albo nic więcej nie będzie czekać; możesz go zatrzymać. Nie przekroczy miesięcznego limitu ani zapasu, a noc w tym czasie zostawia to zadanie."
        switch use.key {
        case "descriptions":
            return "Słowa kluczowe i polskie opisy dzieł katalogu, które ich jeszcze nie mają, najpierw Ulubione i playlisty. " + common
        case "crops":
            return "Najpierw dzieła, przy których Haiku już coś zobaczył i które czekają na Opusa, potem kolejne (ocena Haiku, a gdy trzeba, Opus). " + common
        default:
            return common
        }
    }
}
