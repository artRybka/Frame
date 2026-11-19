import SwiftUI

/// Konfiguracja → Diagnostyka: the trial of merging a scan on the phone
/// (Mateusz 2026-11-18 23:34 UTC: "przyspieszyć składanie obrazów - teraz
/// trwa to zdecydowanie za długo … Może iPhone mógłby wykonywać część pracy
/// znacznie szybciej niż serwer?"; 2026-11-19 00:12 UTC: "Najpierw próba na
/// iPhonie"). One button: the phone merges his last kept scans itself and
/// shows how long each took (`ScanTrial`). Nothing of his collection changes.
struct ScanTrialSection: View {
    @Environment(AppModel.self) private var model
    @State private var trial = ScanTrial()

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            SectionHeader(title: "Składanie skanu na iPhonie", subtitle: "Próba")
            Card {
                Text(bound: "iPhone sam składa Twoje \(ScanTrial.most) ostatnie skany z tych samych zdjęć, z których złożył je serwer, i mierzy czas. Wynik zostaje na serwerze do porównania. W Twojej kolekcji nic się nie zmienia.")
                    .font(.subheadline)
                    .foregroundStyle(Theme.inkSoft)
                ForEach(trial.rows) { row in
                    Divider()
                    line(row)
                }
                if let mean = trial.mean, !trial.running {
                    Divider()
                    Text(bound: "Średnio \(ScanTrialText.seconds(mean)) na skan")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(Theme.ink)
                }
                if let told = trial.told {
                    Divider()
                    Text(bound: told)
                        .font(.subheadline)
                        .foregroundStyle(Theme.warn)
                }
            }
            Button {
                Task { await trial.run(with: model.backend) }
            } label: {
                Label(trial.running ? "Trwa próba…" : "Zacznij próbę", systemImage: "timer")
                    .font(.subheadline.weight(.medium))
            }
            .buttonStyle(.bordered)
            .disabled(trial.running)
            Text(bound: "Potrwa kilka minut, bo zdjęcia w pełnej wielkości idą z serwera i z powrotem. Zostaw aplikację otwartą, najlepiej w domowym Wi-Fi.")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
        }
    }

    private func line(_ row: ScanTrial.Row) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(bound: ScanTrialText.name(row.date))
                    .font(.subheadline)
                    .foregroundStyle(Theme.ink)
                if case let .failed(why) = row.stage {
                    Text(bound: why)
                        .font(.caption)
                        .foregroundStyle(Theme.warn)
                }
            }
            Spacer(minLength: 8)
            switch row.stage {
            case .done:
                Text(bound: row.seconds.map(ScanTrialText.seconds) ?? "Gotowe")
                    .font(.subheadline.weight(.semibold).monospacedDigit())
                    .foregroundStyle(Theme.good)
            case .failed:
                Text(bound: "Nie udało się")
                    .font(.subheadline)
                    .foregroundStyle(Theme.warn)
            case .waiting:
                Text(bound: ScanTrialText.stage(row.stage))
                    .font(.subheadline)
                    .foregroundStyle(Theme.inkSoft)
            case .fetching, .merging, .sending:
                HStack(spacing: 8) {
                    ProgressView()
                    Text(bound: ScanTrialText.stage(row.stage))
                        .font(.subheadline)
                        .foregroundStyle(Theme.inkSoft)
                }
            }
        }
    }
}

/// The trial's words.
enum ScanTrialText {
    private static let polish = Locale(identifier: "pl_PL")

    /// "5,2 s"
    static func seconds(_ seconds: Double) -> String {
        String(format: "%.1f s", locale: polish, seconds)
    }

    /// "Skan z 18 lis, 19:13"; "Skan" when the server did not say when.
    static func name(_ date: Date?) -> String {
        guard let date else { return "Skan" }
        let when = date.formatted(
            Date.FormatStyle(locale: polish).day().month(.abbreviated).hour().minute()
        )
        return "Skan z \(when)"
    }

    static func stage(_ stage: ScanTrial.Row.Stage) -> String {
        switch stage {
        case .waiting: "Czeka"
        case .fetching: "Pobieram zdjęcia"
        case .merging: "Składam"
        case .sending: "Wysyłam wynik"
        case .done: "Gotowe"
        case .failed: "Nie udało się"
        }
    }
}
