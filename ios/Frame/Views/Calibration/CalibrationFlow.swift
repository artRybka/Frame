import PhotosUI
import SwiftUI

/// Measuring the frame's real ink colours: the chart on the frame, a photo
/// of it, its corners marked, the result compared and applied.
struct CalibrationFlow: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    enum Step: Int, CaseIterable {
        case chart, photo, corners, result
    }

    @State private var step = Step.chart
    @State private var chartShown = false
    @State private var busy = false
    @State private var error: String?
    @State private var photo: UIImage?
    @State private var photoData: Data?
    @State private var corners = CornerEditor.defaultCorners
    @State private var result: CalibrationResult?
    @State private var pickerItem: PhotosPickerItem?
    @State private var showingCamera = false
    @State private var afterCalibration = true

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    StepIndicator(step: step)
                    switch step {
                    case .chart: chartStep
                    case .photo: photoStep
                    case .corners: cornersStep
                    case .result: resultStep
                    }
                    if let error {
                        Label(error, systemImage: "exclamationmark.triangle")
                            .font(.subheadline)
                            .foregroundStyle(Theme.bad)
                    }
                }
                .padding(.horizontal, Theme.gutter)
                .padding(.top, 8)
                .padding(.bottom, 32)
                .animation(.easeInOut(duration: 0.25), value: step)
            }
            .scrollDisabled(step == .corners)  // the handles need the drags
            .background(Theme.paper)
            .navigationTitle("Kalibracja kolorów")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Anuluj") { Task { await cancel() } }
                }
            }
        }
        .fullScreenCover(isPresented: $showingCamera) {
            CameraPicker { image in Task { await use(image) } }
                .ignoresSafeArea()
        }
        .onChange(of: pickerItem) { _, item in
            Task {
                guard let data = try? await item?.loadTransferable(type: Data.self),
                      let image = UIImage(data: data)
                else { return }
                await use(image)
            }
        }
        .interactiveDismissDisabled(busy)
        .task { await startFromLaunchRoute() }
    }

    // MARK: Steps

    private var chartStep: some View {
        VStack(alignment: .leading, spacing: 18) {
            StepTitle(
                number: 1, title: "Plansza na ramce",
                text: "Ramka pokaże sześć pól, po jednym dla każdej farby. Plansza zostanie na niej przez pół godziny, potem wróci zwykły pokaz."
            )
            ChartMiniature()
            Button {
                Task { await showChart() }
            } label: {
                HStack(spacing: 10) {
                    if busy { ProgressView().tint(.white) }
                    Text(busy ? "Ramka odświeża ekran…" : "Wyświetl planszę")
                }
            }
            .buttonStyle(PrimaryButtonStyle())
            .disabled(busy)
            Button("Plansza już jest na ramce") { step = .photo }
                .font(.subheadline.weight(.medium))
                .frame(maxWidth: .infinity)
                .disabled(busy)
        }
    }

    private var photoStep: some View {
        VStack(alignment: .leading, spacing: 18) {
            StepTitle(number: 2, title: "Zdjęcie ramki", text: "Zrób zdjęcie całej ramki z planszą.")
            Card {
                Tip(symbol: "sun.max", text: "W świetle dziennym, bez lampy błyskowej.")
                Tip(symbol: "camera.viewfinder", text: "Na wprost; cała ramka w kadrze, jak największa.")
                Tip(symbol: "rays", text: "Bez odblasków: jeśli w ekranie odbija się okno, zmień kąt.")
            }
            if UIImagePickerController.isSourceTypeAvailable(.camera) {
                Button {
                    showingCamera = true
                } label: {
                    Label("Zrób zdjęcie", systemImage: "camera")
                }
                .buttonStyle(PrimaryButtonStyle())
            }
            PhotosPicker(selection: $pickerItem, matching: .images) {
                Label("Wybierz z rolki", systemImage: "photo.on.rectangle")
            }
            .buttonStyle(SecondaryButtonStyle())
            if model.backend.isDemo, let sample = CalibrationPhoto.sample {
                Button("Użyj przykładowego zdjęcia") { Task { await use(sample) } }
                    .font(.subheadline.weight(.medium))
                    .frame(maxWidth: .infinity)
            }
        }
    }

    private var cornersStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            StepTitle(
                number: 3, title: "Narożniki",
                text: "Przeciągnij kółka na czarne kwadraty w rogach ekranu. Fioletowe ramki muszą leżeć wewnątrz kolorowych pól."
            )
            if let photo {
                CornerEditor(image: photo, corners: $corners)
            }
            HStack(spacing: 12) {
                Button("Inne zdjęcie") { step = .photo }
                    .buttonStyle(SecondaryButtonStyle())
                Button {
                    Task { await measure() }
                } label: {
                    HStack(spacing: 10) {
                        if busy { ProgressView().tint(.white) }
                        Text("Zmierz")
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(busy || photoData == nil)
            }
        }
    }

    @ViewBuilder private var resultStep: some View {
        VStack(alignment: .leading, spacing: 18) {
            StepTitle(
                number: 4, title: "Zmierzone kolory",
                text: "Farby Twojej ramki w Twoim świetle, obok kolorów, według których serwer liczy obraz teraz."
            )
            if let result {
                Card {
                    HStack {
                        Text("Farba")
                        Spacer()
                        Text("teraz").frame(width: 46)
                        Spacer().frame(width: 22)
                        Text("zmierzone").frame(width: 70)
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Theme.inkSoft)
                    ForEach(result.inks) { ink in
                        InkRow(ink: ink)
                    }
                }
                if !result.warnings.isEmpty {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(result.warnings, id: \.self) { warning in
                            Label(warning, systemImage: "exclamationmark.triangle.fill")
                                .font(.subheadline)
                        }
                    }
                    .foregroundStyle(Theme.warn)
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.warn.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
                }
                if let item = model.currentItem {
                    comparison(result, item: item)
                }
                if !model.backend.isDemo {
                    DisclosureGroup("Jak zmierzono") {
                        ArtImage(ref: .calibrationChart(candidate: result.candidateId), maxPixel: 1400, contentMode: .fit)
                            .aspectRatio(16.0 / 9.0, contentMode: .fit)
                            .clipShape(RoundedRectangle(cornerRadius: 8))
                            .padding(.top, 8)
                    }
                    .tint(Theme.accent)
                }
                Button {
                    Task { await apply() }
                } label: {
                    HStack(spacing: 10) {
                        if busy { ProgressView().tint(.white) }
                        Text("Zastosuj nowe kolory")
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(busy)
                Button("Zrób inne zdjęcie") { step = .photo }
                    .buttonStyle(SecondaryButtonStyle())
            }
        }
    }

    private func comparison(_ result: CalibrationResult, item: Item) -> some View {
        let portrait = model.isPortrait
        let ref: ImageRef =
            afterCalibration
            ? .calibrationPreview(candidate: result.candidateId, item: item.id)
            : .framePreview(item.id, settings: model.settings)
        return VStack(spacing: 12) {
            Picker("Podgląd", selection: $afterCalibration) {
                Text("Teraz").tag(false)
                Text("Po kalibracji").tag(true)
            }
            .pickerStyle(.segmented)
            FramedArtwork(ref: ref, aspectRatio: portrait ? 9.0 / 16.0 : 16.0 / 9.0, moulding: 5)
            .frame(maxWidth: portrait ? 200 : .infinity)
            Text(item.title)
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: Actions

    private func showChart() async {
        busy = true
        error = nil
        defer { busy = false }
        do {
            try await model.backend.showCalibrationChart()
            chartShown = true
            await model.followPlayer()
            step = .photo
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func use(_ image: UIImage) async {
        guard let prepared = CalibrationPhoto.prepare(image) else {
            error = "Nie udało się odczytać zdjęcia."
            return
        }
        error = nil
        photo = prepared.image
        photoData = prepared.data
        corners = await CalibrationPhoto.detectCorners(in: prepared.image) ?? CornerEditor.defaultCorners
        step = .corners
    }

    private func measure() async {
        guard let photoData else { return }
        busy = true
        error = nil
        defer { busy = false }
        do {
            result = try await model.backend.measureCalibration(photo: photoData, corners: corners)
            afterCalibration = true
            step = .result
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func apply() async {
        guard let result else { return }
        busy = true
        defer { busy = false }
        do {
            model.calibration = try await model.backend.applyCalibration(candidateID: result.candidateId)
            model.toast = "Nowe kolory zapisane — ramka odświeża obraz"
            dismiss()
            await model.followPlayer()
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func cancel() async {
        dismiss()
        if chartShown || model.player?.current?.title == "Plansza kalibracji" {
            try? await model.backend.cancelCalibration()
            await model.followPlayer()
        }
    }

    /// CI screenshots: `-screen calibration` (corners) or `calibration-result`.
    private func startFromLaunchRoute() async {
        guard model.backend.isDemo, LaunchRoute.screen.hasPrefix("calibration"),
              let sample = CalibrationPhoto.sample
        else { return }
        await use(sample)
        if LaunchRoute.screen == "calibration-result" { await measure() }
    }
}

private struct StepIndicator: View {
    let step: CalibrationFlow.Step

    var body: some View {
        HStack(spacing: 6) {
            ForEach(CalibrationFlow.Step.allCases, id: \.self) { item in
                Capsule()
                    .fill(item.rawValue <= step.rawValue ? Theme.accent : Theme.hairline)
                    .frame(height: 4)
            }
        }
        .accessibilityElement()
        .accessibilityLabel("Krok \(step.rawValue + 1) z \(CalibrationFlow.Step.allCases.count)")
    }
}

private struct StepTitle: View {
    let number: Int
    let title: String
    let text: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Eyebrow("Krok \(number) z 4", color: Theme.vermilion)
            Text(title).font(.serif(28, weight: .semibold)).foregroundStyle(Theme.ink)
            Text(text).font(.callout).foregroundStyle(Theme.inkSoft)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

private struct Tip: View {
    let symbol: String
    let text: String

    var body: some View {
        Label {
            Text(text).foregroundStyle(Theme.ink)
        } icon: {
            Image(systemName: symbol).foregroundStyle(Theme.accent)
        }
        .font(.subheadline)
    }
}

/// One ink: its colour in the palette used now and as measured.
private struct InkRow: View {
    let ink: MeasuredInk

    var body: some View {
        HStack {
            Text(Names.ink(ink.name)).foregroundStyle(Theme.ink)
            Spacer()
            swatch(ink.previous).frame(width: 46)
            Image(systemName: "arrow.right")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Theme.inkSoft)
                .frame(width: 22)
            swatch(ink.perceived).frame(width: 70)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(Names.ink(ink.name)) farba")
    }

    private func swatch(_ rgb: [Int]) -> some View {
        RoundedRectangle(cornerRadius: 6)
            .fill(Color(rgb: rgb))
            .frame(width: 34, height: 26)
            .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Theme.inkSoft.opacity(0.35), lineWidth: 0.75))
    }
}

/// The palette chart in miniature (testchart.palette_chart): corner markers
/// and one patch per ink.
struct ChartMiniature: View {
    private static let inks: [[Int]] = [
        [0, 0, 0], [255, 255, 255], [255, 255, 0], [255, 0, 0], [0, 0, 255], [0, 255, 0],
    ]

    var body: some View {
        Canvas { context, size in
            context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(.white))
            let marker = size.width * 80 / 2560
            let origins: [CGPoint] = [
                CGPoint(x: 0, y: 0), CGPoint(x: size.width - marker, y: 0),
                CGPoint(x: 0, y: size.height - marker), CGPoint(x: size.width - marker, y: size.height - marker),
            ]
            for origin in origins {
                context.fill(Path(CGRect(origin: origin, size: CGSize(width: marker, height: marker))), with: .color(.black))
                let core = marker / 3
                let inner = CGRect(x: origin.x + core, y: origin.y + core, width: core, height: core)
                context.fill(Path(inner), with: .color(.white))
            }
            for (rect, rgb) in zip(ChartGeometry.patches, Self.inks) {
                let frame = CGRect(
                    x: rect.minX * size.width, y: rect.minY * size.height,
                    width: rect.width * size.width, height: rect.height * size.height
                )
                context.fill(Path(frame), with: .color(Color(rgb: rgb)))
                context.stroke(Path(frame.insetBy(dx: -1, dy: -1)), with: .color(.black), lineWidth: 0.75)
            }
        }
        .aspectRatio(16.0 / 9.0, contentMode: .fit)
        .padding(6)
        .background(Theme.frameWood)
        .clipShape(RoundedRectangle(cornerRadius: 2))
        .shadow(color: .black.opacity(0.25), radius: 14, y: 10)
        .padding(.vertical, 6)
        .accessibilityLabel("Plansza z sześcioma polami farb")
    }
}
