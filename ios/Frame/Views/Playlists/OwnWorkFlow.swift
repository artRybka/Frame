import CoreImage
import CoreImage.CIFilterBuiltins
import ImageIO
import SwiftUI

/// "Dodaj własne dzieło" (Mateusz 2026-11-15, variant A with hints): from
/// the "+" in Playlisty, three steps on the whole screen. A photograph from
/// the camera, open at once with one line of advice (or from Photos beside
/// its shutter; Mateusz 2026-11-15 23:52, sketch A), the steps after it in
/// the app's own navigation bar; the work found in it by the server and cut out
/// of its frame and mount, its corners his to move; then what he knows of
/// it, with what was read off the picture (signature, date, technique) as
/// chips to take. One work at a time. "Zrób zdjęcie ponownie" on its card
/// takes the first two steps again and keeps what he wrote.
struct OwnWorkFlow: View {
    enum Mode {
        case add
        /// A new photograph of a work of his ("Zrób zdjęcie ponownie").
        case retake(Item)
    }

    enum Step: Int, CaseIterable {
        case photo, cut, describe

        var name: String {
            switch self {
            case .photo: "Zdjęcie"
            case .cut: "Kadr"
            case .describe: "Opis"
            }
        }
    }

    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let mode: Mode
    /// The work as added: its card opens. (A new photograph of a work he
    /// has is kept behind its card, `AppModel.retakeOwnWork`.)
    let done: (Item) -> Void

    @State private var step = Step.photo
    @State private var photo: UIImage?
    @State private var incoming: OwnIncoming?
    /// The server is sending or looking at the photograph.
    @State private var finding = false
    /// The corners the server found; nil when none.
    @State private var found: [[Double]]?
    /// They are the rectangle the camera followed, not the server's answer.
    @State private var foundByCamera = false
    /// The corners he went on with; nil, the photograph whole.
    @State private var corners: [[Double]]?
    @State private var cutBy = "auto"
    /// The work cut out on the phone, for the description's header.
    @State private var picture: UIImage?
    @State private var hints: OwnHints?
    @State private var readingHints = false
    @State private var text = OwnDescription()
    @State private var adding = false
    /// The LiDAR's depth of the first photograph, and the size it gave
    /// between the corners he went on with.
    @State private var depth: OwnDepth?
    @State private var measured: OwnDepth.Size?
    /// The glare taken out by the side photographs.
    @State private var merged: OwnMerged?
    /// The first photograph without it, as the server keeps it now.
    @State private var clean: UIImage?
    /// The first photograph as it was taken and the scan made of the
    /// three, both cut to the work: the page that shows what the scan gave.
    @State private var compared: (before: UIImage, after: UIImage)?
    /// The white balance he set on that page (no colour chart beside the
    /// work): 0, as taken.
    @State private var balance = 0.0
    /// A scan's photographs on their way to the server from the moment
    /// each is taken.
    @State private var sending = OwnSending()
    /// The three photographs being made one, while he sets the corners on
    /// the first: by the phone itself (`PhoneScan`; Mateusz 2026-11-19
    /// 07:42 UTC: "Tak, składaj na iPhonie"), by the server where the
    /// phone cannot.
    @State private var merging: Task<Void, Never>?
    /// It is done with them (whether or not anything was taken out).
    @State private var mergeEnded = false
    /// The phone's own scan of this scan's photographs.
    @State private var scanning = OwnPhoneScan()
    /// The corners the phone's scan was made within; nil, the server made it.
    @State private var cleaned: [[Double]]?
    /// The phone's scan on its way to the server, which keeps it in the
    /// first photograph's place; `owed` until it is kept there.
    @State private var owed: OwnPhoneScan.Owed?
    @State private var delivering: Task<OwnPhoneScan.Delivery, Never>?
    /// "Dalej" was pressed in "Kadr" and the scan is not made yet.
    @State private var awaited = false
    /// "Dalej" was pressed on the scan's page.
    @State private var going = false
    @State private var findingText = "Szukam dzieła na zdjęciu…"

    private var retaking: Item? {
        if case let .retake(item) = mode { return item }
        return nil
    }

    private var steps: [Step] { retaking == nil ? Step.allCases : [.photo, .cut] }

    var body: some View {
        NavigationStack {
            Group {
                switch step {
                case .photo:
                    if ["own-scan", "own-scan2"].contains(LaunchRoute.screen) {
                        OwnScanSketch(close: back)  // the scan's camera as a scene, for screenshots
                    } else {
                        OwnCamera(
                            close: back, took: take, early: early,
                            finding: finding ? photo : nil, findingText: findingText
                        )
                    }
                case .cut:
                    if let compared {
                        OwnScanResult(
                            before: compared.before, after: compared.after,
                            scanned: merged != nil,
                            doubt: merged?.doubt ?? false,
                            nothing: (merged?.replaced ?? 0) == 0,
                            balance: incoming?.chart == nil ? $balance : nil,
                            again: again,
                            next: { single in
                                Task {
                                    going = true
                                    // A new photograph of a work he has: the
                                    // choice goes with it, behind the card.
                                    var kept = true
                                    if single, retaking == nil { kept = await keepFirst() }
                                    if kept { _ = await cutDone(single: single) }
                                    going = false
                                }
                            },
                            busy: going
                        )
                    } else {
                        cutStep
                    }
                case .describe: describeStep
                }
            }
            .paperPage()
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(action: back) {
                        Image(systemName: "chevron.backward")
                    }
                    .accessibilityLabel(step == steps.first ? "Zamknij" : "Wstecz")
                    .disabled(adding)
                }
                ToolbarItem(placement: .principal) {
                    VStack(spacing: 1) {
                        Text(bound: retaking == nil ? "Własne dzieło" : "Nowe zdjęcie")
                            .font(.headline)
                            .foregroundStyle(Theme.ink)
                        Text(bound: "\(step.name) · \((steps.firstIndex(of: step) ?? 0) + 1) z \(steps.count)")
                            .font(.caption)
                            .foregroundStyle(Theme.inkSoft)
                    }
                    .accessibilityElement(children: .combine)
                }
            }
            .toolbar(step == .photo || compared != nil ? .hidden : .visible, for: .navigationBar)
        }
        .task {
            OwnPhoneScan.sweep()
            await openForScreenshot()
        }
    }

    /// The arrow at the top left: a step back, out from the first.
    private func back() {
        switch step {
        case .photo: dismiss()
        case .cut: again()
        case .describe: withAnimation(.easeInOut(duration: 0.3)) { step = .cut }
        }
    }

    // MARK: 1. The photograph

    /// A scan's photographs so far (nil: begun anew), the next still to be
    /// taken: they go to the server meanwhile, and the work is looked for
    /// in the first (Mateusz 2026-11-16 16:44 UTC: "etap „łączę trzy
    /// zdjęcia, usuwam odblaski” trwa bardzo długo […] może niektóre
    /// procesy robić w tle a w międzyczasie wykonać np. Kadrowanie?"; the
    /// three were sent one after another, some 3 s each, only after the
    /// third was taken, then Opus looked for the work, 4 s).
    private func early(_ shots: OwnShots?) {
        if shots?.sides.isEmpty ?? true { sending = OwnSending() }
        if let shots { sending.send(shots, with: model.backend) }
    }

    /// Back to the camera, for the photographs anew.
    private func again() {
        sending = OwnSending()
        merging?.cancel()
        merging = nil
        forget()
        withAnimation(.easeInOut(duration: 0.3)) {
            compared = nil
            step = .photo
        }
    }

    /// The photograph upright (the camera's turn drawn in), sent with the
    /// ones from the sides (what of them is not with the server yet), and
    /// the work looked for in it. Then "Kadr" at once, on the first
    /// photograph: the server makes the three one meanwhile.
    private func take(_ shots: OwnShots) {
        let image = Self.upright(shots.first)
        photo = image
        depth = shots.depth
        merged = nil
        clean = nil
        compared = nil
        balance = 0
        merging?.cancel()
        merging = nil
        mergeEnded = false
        forget()
        finding = true
        findingText = shots.sides.isEmpty ? "Szukam dzieła na zdjęciu…" : "Wysyłam zdjęcia…"
        Task {
            defer { finding = false }
            sending.send(shots, with: model.backend)
            do {
                var sent = try await sending.photo()
                // Any of the side ones failing leaves the first photograph as it was.
                let scanned = await sending.sidesSent()
                if !shots.sides.isEmpty { findingText = "Szukam dzieła na zdjęciu…" }
                // No key, or Opus could not: he sets the corners himself.
                if let looked = await sending.looked() { sent = looked }
                incoming = sent
                // A colour chart beside the work: the server set the
                // photograph's colours by it, and that photograph is the
                // one shown from here on ("Kadr", "Na wprost", the header).
                if sent.chart != nil,
                   let data = try? await model.backend.ownPhoto(token: sent.token, side: Int(OwnPicture.shownSide)),
                   let trued = UIImage(data: data) {
                    photo = trued
                }
                // Where the model has no answer for a rectangle, the one the
                // camera followed (Mateusz 2026-11-16: "czy to potrzebne
                // skoro mamy już dane z iPhone?"): a start nearer than the
                // photograph whole.
                let seen = sent.corners == nil && (sent.shape.isEmpty || sent.shape == "rectangle") ? shots.outline : nil
                found = sent.corners ?? seen
                foundByCamera = seen != nil
                if scanned {
                    let token = sent.token
                    // Within the corners the server's merge would go by:
                    // the model's, else what the camera followed. With
                    // none, or without the memory to spare, the server
                    // makes the scan as before; so it does of a
                    // photograph with a colour chart when it gives no
                    // tables of it for the phone's own photographs.
                    let charted = sent.chart != nil
                    let may = charted ? sent.tables == true : sent.phone == true
                    let within = may ? PhoneScan.valid(sent.corners) ?? PhoneScan.valid(shots.outline) : nil
                    let here = within != nil && OwnPhoneScan.can(shots, size: (sent.width, sent.height))
                    merging = Task {
                        if here, let within, await scanHere(shots, token: token, corners: within, charted: charted) { return }
                        // He went back to the camera: nothing is asked of the server.
                        guard !Task.isCancelled else { return }
                        await merge(token: token, outline: shots.outline, trace: shots.trace)
                    }
                }
                withAnimation(.easeInOut(duration: 0.3)) { step = .cut }
            } catch {
                sending = OwnSending()
                model.show(error)
            }
        }
    }

    /// The side photographs laid over the first on the server; where they
    /// took a glare out, the photograph as the server keeps it now. Any
    /// of it failing leaves the first photograph as it was, with nothing
    /// to choose between.
    private func merge(token: String, outline: [[Double]]?, trace: [String: Double]) async {
        defer { if incoming?.token == token { mergeEnded = true } }
        guard let done = try? await model.backend.mergeOwnPhotos(token: token, outline: outline, trace: trace), done.used > 0
        else { return }
        var made: UIImage?
        if done.replaced > 0 {
            // For the screen: whole, it is 48 MP.
            guard let data = try? await model.backend.ownPhoto(token: token, side: Int(OwnPicture.shownSide)),
                  let image = UIImage(data: data)
            else { return }
            made = image
        }
        // He may have gone back to the camera meanwhile.
        guard incoming?.token == token, !Task.isCancelled else { return }
        clean = made
        merged = done
    }

    /// The scan made by the phone of its camera's own photographs, shown
    /// as soon as it is made (some 5 s; the server was 34 s at it) and
    /// sent to the server meanwhile. False when the phone could not make
    /// it: the server then does.
    private func scanHere(_ shots: OwnShots, token: String, corners: [[Double]], charted: Bool) async -> Bool {
        let scanning = self.scanning, heat = ProcessInfo.processInfo.thermalState
        // A colour chart beside the work: the phone's own photographs are
        // put in its colours first, by what the server read of it.
        var chart: Data?
        if charted {
            guard let given = try? await model.backend.ownChartTables(token: token) else { return false }
            chart = given
        }
        guard let made = await scanning.make(shots, corners: corners, chart: chart) else { return false }
        // He may have gone back to the camera meanwhile.
        guard incoming?.token == token, !Task.isCancelled else { return true }
        await scanMade(made, by: scanning, token: token, heat: (heat, ProcessInfo.processInfo.thermalState))
        if incoming?.token == token { mergeEnded = true }
        return true
    }

    /// What the phone made of the scan: the first photograph without its
    /// reflections shown (small, for the screen), and the whole of it on
    /// its way to the server.
    private func scanMade(
        _ made: PhoneScan.Made, by scanning: OwnPhoneScan, token: String,
        heat: (before: ProcessInfo.ThermalState, after: ProcessInfo.ThermalState)
    ) async {
        var shown: UIImage?
        if made.note.used > 0, let picture = made.picture {
            // For the screen: whole, it is 48 MP.
            shown = await Task.detached(priority: .userInitiated) { OwnPicture.shown(picture) }.value
        }
        guard let incoming, incoming.token == token, !Task.isCancelled else { return }
        cleaned = made.corners
        clean = shown
        merged = made.note.used > 0
            ? OwnMerged(
                token: token, width: incoming.width, height: incoming.height, used: made.note.used,
                replaced: made.picture == nil ? 0 : made.note.removed, doubt: made.note.doubt
            )
            : nil
        owed = OwnPhoneScan.Owed(
            token: token, note: PhoneScan.told(made, trace: scanning.trace, heat: heat), picture: made.picture,
            outline: scanning.outline, trace: scanning.trace
        )
        deliver()
    }

    /// The phone's scan sent to the server, after any sent before it: the
    /// later one is the one kept.
    private func deliver() {
        guard let owed else { return }
        let backend = model.backend, before = delivering
        delivering = Task {
            _ = await before?.value
            return await OwnPhoneScan.deliver(owed, with: backend)
        }
    }

    /// Whether the server keeps the scan he saw, before anything goes on
    /// from it. What is left of sending it is waited for; lost on the
    /// way, it is sent once more; not taken by the server, the server
    /// makes the scan of the photographs it has, as before.
    private func delivered() async -> Bool {
        guard let owed, let sent = delivering else { return true }
        var how = await sent.value
        if case .lost = how {
            deliver()
            how = await delivering?.value ?? how
        }
        // He may have gone back to the camera meanwhile.
        guard self.owed?.token == owed.token else { return false }
        switch how {
        case .kept:
            self.owed = nil
            delivering = nil
            return true
        case .refused:
            self.owed = nil
            delivering = nil
            cleaned = nil
            clean = nil
            merged = nil
            await merge(token: owed.token, outline: owed.outline, trace: owed.trace)
            return true
        case let .lost(told):
            model.show(OwnPhoneScan.Lost(told: told))
            return false
        }
    }

    /// The phone's scan let go of: its photographs, and what was owed
    /// the server of it.
    private func forget() {
        scanning.clear()
        scanning = OwnPhoneScan()
        cleaned = nil
        owed = nil
        delivering = nil
    }

    // MARK: 2. The cut

    private var cutNote: String {
        if let shape = incoming?.shape, !shape.isEmpty, shape != "rectangle" {
            return "To dzieło nie jest prostokątem, więc zostaje całe zdjęcie. Możesz je przyciąć sam."
        }
        if awaited { return "Jeszcze chwila: kończę łączyć trzy zdjęcia i usuwać odblaski…" }
        let chart = incoming?.chart != nil ? "Barwy ustawione według wzornika. " : ""
        let cleaned = merged.map { $0.replaced > 0 && $0.doubt != true } ?? false
        let glare = chart + (cleaned ? "Odblaski usunięte z trzech zdjęć. "
            : merged == nil && merging != nil && !mergeEnded ? "W tle łączę trzy zdjęcia i usuwam odblaski. " : "")
        if foundByCamera { return glare + "Zaznaczyłem to, co widział aparat. Popraw narożniki, jeśli trzeba." }
        if found != nil { return glare + "Rama wycięta. Popraw narożniki, jeśli trzeba." }
        return glare + "Nie znalazłem dzieła na zdjęciu. Ustaw narożniki sam."
    }

    @ViewBuilder
    private var cutStep: some View {
        if let photo, let incoming {
            CutEditor(
                photo: .local(photo), aspect: incoming.aspect, corners: found,
                saveTitle: retaking == nil ? "Dalej" : "Zapisz", savesUnchanged: true,
                note: cutNote,
                cancel: again
            ) { chosen in
                await cutChosen(chosen)
            }
        }
    }

    private func cutChosen(_ chosen: [[Double]]) async -> Bool {
        let whole = chosen == [[0, 0], [1, 0], [1, 1], [0, 1]]
        corners = whole ? nil : chosen
        cutBy = chosen == found ? "auto" : "owner"
        guard incoming != nil else { return false }
        // The scan is made while he sets the corners; what is left of
        // that is waited for here, under a word of it.
        if let merging {
            awaited = !mergeEnded
            await merging.value
            awaited = false
        }
        // His corners reach beyond what the phone's scan cleaned: it is
        // made once more within them, for him to see (the server does so
        // only as the work is added: its `_again`, which still does when
        // the phone cannot).
        if merged != nil, let had = cleaned, let token = incoming?.token, let his = PhoneScan.valid(corners),
           PhoneScan.beyond(his, cleaned: had) {
            awaited = true
            let scanning = self.scanning, heat = ProcessInfo.processInfo.thermalState
            if let made = await scanning.again(corners: his), made.note.used > 0 {
                await scanMade(made, by: scanning, token: token, heat: (heat, ProcessInfo.processInfo.thermalState))
            }
            awaited = false
        }
        if merged != nil, let photo {
            // What the scan gave: the work alone, as he cut it (the same
            // twice where the side photographs took nothing off).
            let both = (OwnPicture.cut(photo, corners: corners), OwnPicture.cut(clean ?? photo, corners: corners))
            withAnimation(.easeInOut(duration: 0.3)) { compared = both }
            return true
        }
        if incoming?.chart == nil, let photo {
            // No colour chart beside it: the work alone, for him to set
            // its white balance by.
            let one = OwnPicture.cut(photo, corners: corners)
            withAnimation(.easeInOut(duration: 0.3)) { compared = (one, one) }
            return true
        }
        return await cutDone()
    }

    /// "Na wprost" on "Skan gotowy": the server keeps the first
    /// photograph as it was taken, and so does the rest of the way.
    private func keepFirst() async -> Bool {
        guard let token = incoming?.token else { return false }
        // The server keeps the scan's photographs with the scan: that first.
        guard await delivered() else { return false }
        do {
            try await model.backend.keepOwnFirstPhoto(token: token)
        } catch {
            model.show(error)
            return false
        }
        clean = nil
        merged = nil
        return true
    }

    /// The corners are his and the scan (if any) seen: on to what he
    /// knows of the work, or the new photograph kept in the old one's
    /// place.
    private func cutDone(single: Bool = false) async -> Bool {
        guard let incoming else { return false }
        // The phone's scan is with the server before the work is made of it.
        guard await delivered() else { return false }
        if let item = retaking {
            // The server is some seconds at it: the card says so meanwhile.
            model.retakeOwnWork(
                itemID: item.id,
                OwnPhotoCut(
                    token: incoming.token, corners: corners, by: cutBy, shape: incoming.shape,
                    balance: incoming.chart == nil ? balance : 0
                ),
                single: single
            )
            dismiss()
            return true
        }
        if let shown = clean ?? photo {
            picture = OwnBalance.tinted(OwnPicture.cut(shown, corners: corners), balance: balance)
        }
        // The LiDAR's size between his corners (none for the photograph whole).
        measured = corners.flatMap { depth?.size($0) }
        withAnimation(.easeInOut(duration: 0.3)) {
            compared = nil
            step = .describe
        }
        readHints()
        return true
    }

    /// What can be read off the work (Sonnet, about a grosz): the chips
    /// come in while he writes. None without a key, and no word of it.
    private func readHints() {
        guard let incoming, hints == nil, !readingHints else { return }
        readingHints = true
        Task {
            defer { readingHints = false }
            if let read = try? await model.backend.ownHints(token: incoming.token, corners: corners), !read.isEmpty {
                withAnimation(.easeOut(duration: 0.3)) { hints = read }
            }
        }
    }

    // MARK: 3. The description

    private var describeStep: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    OwnDescriptionForm(
                        text: $text, picture: picture, aspect: picture.map { Double($0.size.width / max($0.size.height, 1)) },
                        hints: hints, readingHints: readingHints, places: places, measured: measured
                    )
                    .pageWidth()
                    .padding(.horizontal, Theme.gutter)
                    .padding(.bottom, 40)
                }
                .scrollDismissesKeyboard(.interactively)
                .onChange(of: text.hangs) { _, hangs in
                    // CI screenshots: the lower fields, filled.
                    guard LaunchRoute.scroll == "filled", !hangs.isEmpty else { return }
                    Task {
                        try? await Task.sleep(for: .milliseconds(400))
                        withAnimation(nil) { proxy.scrollTo("size", anchor: .center) }
                    }
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button {
                    Task { await add() }
                } label: {
                    if adding { ProgressView() } else { Text("Dodaj") }
                }
                .disabled(adding)
            }
        }
    }

    /// Where his other works hang: chips under "Gdzie wisi".
    private var places: [String] {
        var seen = Set<String>()
        return model.ownWorks.compactMap { $0.own?.hangs }.filter { !$0.isEmpty && seen.insert($0).inserted }
    }

    private func add() async {
        guard let incoming else { return }
        adding = true
        defer { adding = false }
        do {
            let item = try await model.backend.addOwnWork(
                NewOwnWork(
                    token: incoming.token, corners: corners, by: cutBy, shape: incoming.shape,
                    balance: incoming.chart == nil ? balance : 0, text: text.trimmed
                )
            )
            model.ownWorkChanged(item)
            model.notices.info("Dodane do kolekcji", item.title.isEmpty ? "Bez tytułu" : item.title)
            done(item)
            dismiss()
        } catch {
            model.show(error)
        }
    }

    // MARK: Screenshots

    /// `-screen own-cut|own-describe` (demo): the demo's photograph taken,
    /// the flow at that step.
    private func openForScreenshot() async {
        let screens = ["own-cut", "own-balance", "own-describe", "own-card"]
        guard model.demoMode, screens.contains(LaunchRoute.screen), photo == nil,
              let demo = DemoOwn.photo()
        else { return }
        take(OwnShots(first: demo))
        guard LaunchRoute.screen != "own-cut" else { return }
        for _ in 0 ..< 50 where step != .cut { try? await Task.sleep(for: .milliseconds(200)) }
        guard step == .cut else { return }
        _ = await cutChosen(DemoOwn.work)
        // The page with the white balance (the demo has no colour chart),
        // as set by `-scanBalance`; the later screens go on from it.
        balance = OwnBalance.launched
        guard LaunchRoute.screen != "own-balance" else { return }
        if compared != nil { _ = await cutDone() }
        if LaunchRoute.scroll == "measured" { measured = OwnDepth.Size(heightCm: 65, widthCm: 81) }
        if LaunchRoute.scroll == "filled" || LaunchRoute.screen == "own-card" {
            try? await Task.sleep(for: .seconds(2))
            text.title = "Spacer po klifie"
            text.artist = "Claude Monet"
            text.dateText = "1882"
            text.medium = "olej na płótnie"
            text.heightCm = 65
            text.widthCm = 81
            text.hangs = "Salon"
            text.origin = "Prezent od dziadka"
        }
        if LaunchRoute.screen == "own-card" {
            try? await Task.sleep(for: .seconds(1))
            await add()  // the card opens
        }
    }

    /// The camera's photograph as it was held: pixels upright, so the
    /// corners mean the same on the phone and on the server.
    static func upright(_ image: UIImage) -> UIImage {
        let side = OwnPicture.shownSide  // for the screen; the server is sent the camera's file
        let scale = min(1, side / max(image.size.width, image.size.height))
        guard image.imageOrientation != .up || scale < 1 else { return image }
        let size = CGSize(width: (image.size.width * scale).rounded(), height: (image.size.height * scale).rounded())
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        return UIGraphicsImageRenderer(size: size, format: format).image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
    }
}

/// A scan's photographs on their way to the server from the moment each is
/// taken, and the work looked for in the first: by the time the third is
/// taken, only that one is left to send.
@MainActor
final class OwnSending {
    private var first: Task<OwnIncoming, Error>?
    private var look: Task<OwnIncoming?, Never>?
    /// One after another: the server numbers them as they come.
    private var sides: [Task<Void, Error>] = []

    /// The photographs taken so far: those not yet on their way are sent.
    func send(_ shots: OwnShots, with backend: any FrameBackend) {
        let first = self.first ?? begin(shots, with: backend)
        for index in shots.sides.indices.dropFirst(sides.count) {
            let file = shots.file(index + 1), picture = shots.sides[index], before = sides.last
            let angle = shots.angle(index)
            sides.append(Task<Void, Error> {
                let token = try await first.value.token
                if let before { try await before.value }
                // The camera's own file, every pixel of it; a demo's is drawn.
                guard let data = file ?? OwnWorkFlow.upright(picture).jpegData(compressionQuality: 0.9)
                else { throw CancellationError() }
                try await backend.sendOwnSide(token: token, data, angle: angle)
            })
        }
    }

    private func begin(_ shots: OwnShots, with backend: any FrameBackend) -> Task<OwnIncoming, Error> {
        let file = shots.file(0), picture = shots.first
        // What the camera said of its lens for this photograph: of its
        // own file only (a picture drawn anew names no camera).
        let lens = file != nil ? shots.depth?.lens : nil
        let sent = Task<OwnIncoming, Error> {
            guard let data = file ?? OwnWorkFlow.upright(picture).jpegData(compressionQuality: 0.9)
            else { throw CancellationError() }
            return try await backend.sendOwnPhoto(data, lens: lens)
        }
        first = sent
        look = Task<OwnIncoming?, Never> {
            guard let token = try? await sent.value.token else { return nil }
            return try? await backend.findOwnWork(token: token)
        }
        return sent
    }

    /// The first photograph as the server keeps it.
    func photo() async throws -> OwnIncoming {
        guard let first else { throw CancellationError() }
        return try await first.value
    }

    /// Whether there are side photographs and each is with the server.
    func sidesSent() async -> Bool {
        do {
            for side in sides { try await side.value }
        } catch {
            return false
        }
        return !sides.isEmpty
    }

    /// The first photograph with the work found in it; nil when the
    /// server could not look (no key, Opus down).
    func looked() async -> OwnIncoming? {
        guard let look else { return nil }
        return await look.value
    }
}

/// The work cut out of a photograph on the phone, as the server cuts it.
enum OwnPicture {
    private static let context = CIContext()

    /// The long side of the photograph the steps show (the corners are set
    /// on it): the file itself is 48 MP, 200 MB once drawn.
    static let shownSide: CGFloat = 4000

    /// A photograph's file as a picture for the screen: upright, no longer
    /// than `shownSide`, read at that size (never whole into memory).
    static func shown(_ file: Data) -> UIImage? {
        guard let source = CGImageSourceCreateWithData(file as CFData, nil) else { return nil }
        let options: [CFString: Any] = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceThumbnailMaxPixelSize: shownSide,
            kCGImageSourceShouldCacheImmediately: true,
        ]
        guard let cg = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) else { return nil }
        return UIImage(cgImage: cg, scale: 1, orientation: .up)
    }

    /// Whether the server reads such a file as it is (JPEG, HEIC): others
    /// (RAW, PNG with its own colours) are drawn anew for it.
    static func sendable(_ file: Data) -> Bool {
        guard let source = CGImageSourceCreateWithData(file as CFData, nil),
              let type = CGImageSourceGetType(source) as String?
        else { return false }
        return ["public.jpeg", "public.heic", "public.heif"].contains(type)
    }

    /// The work inside `corners` of `image`, upright; in the shape of his
    /// size (`own`) when he gave one near enough, as the server keeps it.
    static func cut(_ image: UIImage, corners: [[Double]]?, own: OwnWork?) -> UIImage {
        let upright = cut(image, corners: corners)
        guard corners != nil, let own, let source = CIImage(image: upright) else { return upright }
        let w = source.extent.width, h = source.extent.height
        guard h > 0, let ratio = own.ratio(Double(w / h)) else { return upright }
        let area = Double(w * h)
        let width = CGFloat((area * ratio).squareRoot()), height = CGFloat((area / ratio).squareRoot())
        let scaled = source.transformed(by: CGAffineTransform(scaleX: width / w, y: height / h))
        guard let cg = context.createCGImage(scaled, from: scaled.extent) else { return upright }
        return UIImage(cgImage: cg)
    }

    static func cut(_ image: UIImage, corners: [[Double]]?) -> UIImage {
        guard let corners, corners.count == 4, let source = CIImage(image: image) else { return image }
        let w = source.extent.width, h = source.extent.height
        func point(_ p: [Double]) -> CGPoint { CGPoint(x: p[0] * w, y: (1 - p[1]) * h) }
        let straighten = CIFilter.perspectiveCorrection()
        straighten.inputImage = source
        straighten.topLeft = point(corners[0])
        straighten.topRight = point(corners[1])
        straighten.bottomRight = point(corners[2])
        straighten.bottomLeft = point(corners[3])
        guard let out = straighten.outputImage, let cg = context.createCGImage(out, from: out.extent) else { return image }
        return UIImage(cgImage: cg)
    }
}

extension OwnDescription {
    /// Without spaces at the ends.
    var trimmed: OwnDescription {
        var out = self
        let paths: [WritableKeyPath<OwnDescription, String>] = [\.title, \.artist, \.dateText, \.medium, \.description, \.hangs, \.origin]
        for path in paths {
            out[keyPath: path] = out[keyPath: path].trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return out
    }
}
