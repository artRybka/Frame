import SwiftUI
import UIKit

/// A take on the composition on the study sheet an image model drew for it
/// (`DailyWork.Drawn`): the work as a study in watercolour and pen, and over
/// it the analysis's marks, each drawn by the model with a coloured pencil
/// of its own. The app lays each mark's line in its colour, writes its
/// number on the line where the server found room for it, rules the frame
/// and the grid in graphite and writes the title and the grid's name above
/// the field by hand; the notes under the sheet carry the marks' numbers in
/// their colours.
///
/// What Mateusz decided of it (2026-11-12): the lines stay coloured, one
/// colour a mark (21:59: "świetnie wyglądają kolorowe linie i bardzo
/// poprawiają czytelność! Absolutnie muszą zostać"); no copy of the
/// picture on a tap any more (20:54); the lines do not shift with the phone's
/// turn (21:26); the sheet is the light one on both pages, a card on the
/// dark page (20:54); one wash and one line run out of the field to the
/// screen's edge (21:59).
///
/// How the marks come (2026-11-13 07:11: "Najpierw widzimy tylko
/// szkic/akwarele. Dotknięcie szkicu pokazuje wszystkie adnotacje.
/// Dotknięcie wybranej tylko te jedną. Jeżeli strona jest chwilę
/// ‚zawieszona' … to pojawiają się wszystkie adnotacje jak po dotknięciu
/// szkicu."): the sheet opens as the sketch alone (`Shown.sketch`); a tap
/// on it brings every line, number and the grid (`.all`), another puts
/// them away; a tap on a note leaves that one line alone on the sketch
/// (`.one`); with the field in view and the page still for `still`, the
/// lines come by themselves as after a tap, once a visit: a sheet that
/// leaves the screen is the sketch alone again when it comes back.
///
/// A mark the model left out (no layer) is drawn here, in its colour. A
/// sheet that would not load is told to the page (`failed`), which shows
/// the server's own sheet instead.
struct DrawnSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.colorScheme) private var scheme
    let take: DailyWork.Take
    let drawn: DailyWork.Drawn
    /// Written above the field: whose work and which.
    var title = ""
    /// The text block's width: the field takes all of it.
    var width: CGFloat? = nil
    /// The sheet's picture cannot be had.
    var failed: () -> Void = {}

    /// Which of the marks are on the sketch.
    enum Shown: Equatable {
        /// None: the sketch and the wash alone.
        case sketch
        /// Every line, number, the frame and the grid.
        case all
        /// The one line (by its note's number) and the frame.
        case one(Int)

        /// A tap on the sheet: every mark, or none when every one is there.
        func tappedSheet() -> Shown { self == .all ? .sketch : .all }

        /// A tap on a note: its line alone, or every one back when it was.
        func tappedNote(_ number: Int) -> Shown { self == .one(number) ? .all : .one(number) }

        /// The tapped note's number.
        var chosen: Int? { if case let .one(number) = self { number } else { nil } }
    }

    /// How long the page stands still, the field in view, before the
    /// marks come by themselves.
    static let still: Duration = .seconds(2)

    /// What is on the sketch: at first the sketch alone (CI screenshots
    /// may open it with a note tapped).
    @State private var shown: Shown = LaunchRoute.chalkChosen.map { .one($0) } ?? .sketch
    /// The reader tapped the sheet or a note on this visit: the page's
    /// standing still no longer brings the marks.
    @State private var touched = LaunchRoute.compositionBare || LaunchRoute.chalkChosen != nil
    /// Taps, for the tap's feel (the marks coming by themselves give none).
    @State private var taps = 0
    /// The study is here: the lines come with it.
    @State private var here = false

    private var bare: Bool { shown == .sketch }

    /// The paper the sheet is drawn on, on either page.
    static let paper = Chalk.page(dark: false)
    /// On the dark page the sheet is a card: how far it reaches past the
    /// text's column on each side, and how round it is.
    static let cardReach: CGFloat = 12
    static let cardCorner: CGFloat = 18
    private static let pixels: CGFloat = 1600

    /// A mark of the take as it is shown: its number when it has a note,
    /// its colour, its line from the server (nil: drawn here) and where its
    /// number stands.
    struct Line: Identifiable {
        let index: Int
        let mark: DailyWork.Mark
        let number: Int?
        let colour: Color
        let layer: ImageRef?
        let spots: [DailyWork.Drawn.Number]
        var id: Int { index }
    }

    /// The take's marks in the field, each with what the model drew of it.
    /// A mark the server sent nothing for (none has a title today) is
    /// drawn in graphite.
    static func lines(_ take: DailyWork.Take, _ drawn: DailyWork.Drawn) -> [Line] {
        let marks = take.marksInField
        var number = 0
        return marks.enumerated().map { index, mark in
            if !mark.title.isEmpty { number += 1 }
            let made = drawn.marks.first { $0.mark == index }
            return Line(
                index: index, mark: mark, number: mark.title.isEmpty ? nil : number,
                colour: made.flatMap { Color(hexString: $0.colour) } ?? Pencil.lead,
                layer: made.flatMap { $0.layer.isEmpty ? nil : .path($0.layer) },
                spots: made?.numbers ?? []
            )
        }
    }

    /// How much of a line shows on the sketch: all of every one, of the
    /// tapped note's alone, or of none.
    static func share(of line: Line, shown: Shown) -> Double {
        switch shown {
        case .sketch: 0
        case .all: 1
        case let .one(number): line.number == number ? 1 : 0
        }
    }

    /// The grid's name as it is written on the sheet.
    static func gridName(_ grid: String) -> String? {
        switch grid {
        case "golden": "złoty podział"
        case "thirds": "trójpodział"
        case "halves": "osie"
        case "3x2": "trzy na dwa"
        case "2x3": "dwa na trzy"
        default: nil
        }
    }

    private var sheetRef: ImageRef { .path(drawn.sheet) }

    var body: some View {
        let lines = Self.lines(take, drawn)
        let noted = lines.filter { $0.number != nil }
        let dark = scheme == .dark
        VStack(spacing: 14) {
            VStack(spacing: 2) {
                heading
                field(lines)
            }
            if !noted.isEmpty {
                LazyVGrid(
                    columns: [GridItem(.flexible(), spacing: 14, alignment: .topLeading), GridItem(.flexible(), alignment: .topLeading)],
                    alignment: .leading,
                    spacing: 12
                ) {
                    ForEach(noted) { line in note(line) }
                }
            }
        }
        // The sheet is the light one: what is written on it is dark ink.
        .environment(\.colorScheme, .light)
        .modifier(SheetCard(on: dark))
        .animation(.easeOut(duration: 0.3), value: here)
        .sensoryFeedback(.selection, trigger: taps)
        // Off the screen: the next visit starts from the sketch again.
        .onScrollVisibilityChange(threshold: 0.02) { visible in
            guard !visible, !LaunchRoute.compositionBare, LaunchRoute.chalkChosen == nil else { return }
            shown = .sketch
            touched = false
        }
    }


    /// Whose work and which, and the grid's name, written by hand above
    /// the field (the grid's goes with the grid).
    @ViewBuilder
    private var heading: some View {
        let grid = Self.gridName(take.grid)
        if !title.isEmpty || grid != nil {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                HandLines(text: title, size: 17)
                    .foregroundStyle(Theme.ink.opacity(0.78))
                    .frame(maxWidth: .infinity, alignment: .leading)
                if let grid {
                    Text(grid)
                        .font(.hand(15))
                        .foregroundStyle(Theme.inkSoft)
                        .opacity(shown == .all ? 1 : 0)
                        .accessibilityHidden(true)
                }
            }
            .padding(.horizontal, 2)
        }
    }

    @ViewBuilder
    private func box() -> some View {
        let aspect = max(CGFloat(drawn.aspect), 0.05)
        if let width, width > 0 {
            Color.clear.frame(width: width, height: width / aspect)
        } else {
            Color.clear.frame(maxWidth: .infinity).aspectRatio(aspect, contentMode: .fit)
        }
    }

    /// The study with the lines over it. The frame and the grid run a
    /// little past the field's corners, as ruled by hand: room is made
    /// above and below for them.
    private func field(_ lines: [Line]) -> some View {
        let room = Pencil.reach + 2
        let bleed = CGFloat(drawn.bleed)
        return box()
            .overlay {
                // Wider than the field by the page's margin on each side.
                GeometryReader { geometry in
                    ArtImage(ref: sheetRef, placeholder: .clear, maxPixel: Self.pixels)
                        .padding(.horizontal, -bleed * geometry.size.width)
                }
                .environment(\.artImageLoaded) { ref in loaded(ref) }
            }
            .overlay {
                Canvas { context, size in
                    context.translateBy(x: room, y: room)
                    rule(in: &context, size: CGSize(width: size.width - 2 * room, height: size.height - 2 * room), grid: shown == .all)
                }
                .padding(-room)
                .opacity(bare || !here ? 0 : 1)
                .allowsHitTesting(false)
            }
            .overlay {
                ZStack {
                    ForEach(lines) { line in
                        pencil(line).opacity(Self.share(of: line, shown: shown))
                    }
                }
                .opacity(here ? 1 : 0)
                .allowsHitTesting(false)
            }
            .overlay {
                Canvas { context, size in
                    for line in lines {
                        guard let number = line.number else { continue }
                        let share = Self.share(of: line, shown: shown)
                        guard share > 0 else { continue }
                        context.opacity = share
                        for spot in Self.spots(of: line, in: size) {
                            Pencil.badge(number, at: spot, in: &context, ink: line.colour, paper: Self.paper, hand: true)
                        }
                    }
                }
                .opacity(here ? 1 : 0)
                .allowsHitTesting(false)
            }
            .contentShape(Rectangle())
            .onTapGesture {
                touched = true
                taps += 1
                withAnimation(.easeInOut(duration: 0.3)) { shown = shown.tappedSheet() }
            }
            .accessibilityAddTraits(.isButton)
            .accessibilityLabel("Arkusz analizy kompozycji")
            .accessibilityHint(shown == .all ? "Chowa linie kompozycji i zostawia sam szkic" : "Pokazuje wszystkie linie kompozycji")
            // The marks come by themselves: the study is here, most of the
            // field is on the screen, nobody tapped, and the page stood still.
            .modifier(StillInView(waiting: here && !touched && shown == .sketch, after: Self.still) {
                withAnimation(.easeInOut(duration: 0.6)) { shown = .all }
            })
            .padding(.vertical, room)
            .frame(maxWidth: .infinity)
            .task(id: drawn.sheet) {
                if inMemory(sheetRef) { here = true }
            }
    }

    /// Where a line's number stands in a field of `size`: where the server
    /// found room on the line, else (a mark drawn here) where the app
    /// puts it.
    static func spots(of line: Line, in size: CGSize) -> [CGPoint] {
        guard !line.spots.isEmpty else { return [Pencil.numberSpot(for: line.mark, in: size)] }
        return line.spots.map { CGPoint(x: $0.x * size.width, y: $0.y * size.height) }
    }

    /// A mark's line in its colour: the model's own, else drawn here with
    /// the same stick as the server's sheet's marks.
    @ViewBuilder
    private func pencil(_ line: Line) -> some View {
        if let layer = line.layer {
            line.colour.mask {
                ArtImage(ref: layer, placeholder: .clear, maxPixel: Self.pixels)
            }
        } else {
            Canvas { context, size in
                for path in Pencil.paths(for: line.mark, in: size, seed: line.index * 7 + 1, weight: Chalk.weight, chalk: true) {
                    context.fill(path, with: .color(line.colour))
                }
            }
        }
    }

    /// The frame and (with every mark shown) the grid, ruled in graphite.
    private func rule(in context: inout GraphicsContext, size: CGSize, grid: Bool) {
        let graphite = Pencil.lead.opacity(0.55)
        let corners = [CGPoint.zero, CGPoint(x: size.width, y: 0), CGPoint(x: size.width, y: size.height), CGPoint(x: 0, y: size.height)]
        for index in 0..<4 {
            let path = Pencil.ruled(corners[index], corners[(index + 1) % 4], over: Pencil.reach, width: 0.9, seed: 70 + index)
            context.fill(path, with: .color(graphite))
        }
        for (index, line) in (grid ? Pencil.grid(take.grid, in: size) : []).enumerated() {
            let path = Pencil.ruled(line[0], line[1], over: Pencil.reach, width: 0.9, seed: 90 + index)
            context.fill(path, with: .color(graphite))
        }
    }

    /// The study is here, or was given up on.
    private func loaded(_ ref: ImageRef) {
        guard ref == sheetRef else { return }
        if inMemory(ref) {
            here = true
        } else {
            failed()
        }
    }

    private func inMemory(_ ref: ImageRef) -> Bool {
        model.backend.request(for: ref).flatMap { ImageLoader.inMemory(for: $0, maxPixel: Self.pixels) } != nil
    }

    /// A mark's note: its number in its colour, as on its line, the title
    /// and a line under it by hand. A tap leaves its line alone on the
    /// sketch, another brings every one back.
    private func note(_ line: Line) -> some View {
        let chosen = shown.chosen
        let lit = chosen == line.number
        return HStack(alignment: .firstTextBaseline, spacing: 5) {
            Canvas { context, size in
                let spot = CGPoint(x: size.width / 2, y: size.height / 2)
                Pencil.badge(line.number ?? 0, at: spot, in: &context, ink: line.colour, paper: Self.paper, hand: true)
            }
            .frame(width: 22, height: 22)
            .alignmentGuide(.firstTextBaseline) { $0[VerticalAlignment.center] + 5 }
            .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: -7) {
                HandLines(text: line.mark.title, size: 21, even: true)
                if !line.mark.text.isEmpty {
                    HandLines(text: line.mark.text, size: 18)
                        .foregroundStyle(Theme.inkSoft)
                }
            }
        }
        .foregroundStyle(Theme.ink)
        .frame(maxWidth: .infinity, alignment: .leading)
        .opacity(chosen == nil || lit ? 1 : Chalk.aside)
        .contentShape(Rectangle())
        .onTapGesture {
            guard let number = line.number else { return }
            touched = true
            taps += 1
            withAnimation(.easeInOut(duration: 0.25)) { shown = shown.tappedNote(number) }
        }
        .accessibilityAddTraits(lit ? [.isButton, .isSelected] : .isButton)
        .accessibilityHint(lit ? "Pokazuje wszystkie linie kompozycji" : "Pokazuje na szkicu tylko tę linię")
    }
}

/// Calls `action` once the view has stood still for `after` with at least
/// half of it on the scroll view's screen, while `waiting`. Its state is
/// its own, so the view it watches is not drawn anew as the page scrolls.
private struct StillInView: ViewModifier {
    let waiting: Bool
    let after: Duration
    let action: () -> Void

    @State private var inView = false
    /// Counts the view's moves on the screen: the page standing still is
    /// the count standing still.
    @State private var moves = 0

    private struct Stillness: Equatable {
        let waiting: Bool
        let inView: Bool
        let moves: Int
    }

    func body(content: Content) -> some View {
        content
            .onScrollVisibilityChange(threshold: 0.5) { inView = $0 }
            .onGeometryChange(for: Int.self) { Int(($0.frame(in: .global).minY / 4).rounded()) } action: { _ in
                if waiting { moves &+= 1 }
            }
            .task(id: Stillness(waiting: waiting, inView: inView, moves: moves)) {
                guard waiting, inView else { return }
                do { try await Task.sleep(for: after) } catch { return }
                action()
            }
    }
}

/// The light sheet on the dark page: a card of the sheet's paper a little
/// wider than the text's column, the study's margins cut at its edge. On
/// the light page the sheet lies on the page itself and what runs out of
/// the field goes on to the screen's edge.
private struct SheetCard: ViewModifier {
    let on: Bool

    func body(content: Content) -> some View {
        if on {
            let shape = RoundedRectangle(cornerRadius: DrawnSheet.cardCorner, style: .continuous)
            content
                .padding(.vertical, 14)
                .padding(.horizontal, DrawnSheet.cardReach)
                .background(DrawnSheet.paper)
                .clipShape(shape)
                .padding(.horizontal, -DrawnSheet.cardReach)
        } else {
            content
        }
    }
}
