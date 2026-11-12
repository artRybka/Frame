import SwiftUI
import UIKit

/// One take on the composition, drawn as a study sheet: the picture's field
/// in stains of its colours with a pen sketch over them (made by the server,
/// on the page's own colour), ruled with a thin frame and the grid in
/// graphite, the marks over it in a blue coloured pencil, much
/// heavier than the sketch under them, which is laid thin with its stains
/// so the marks are what is read first, a little
/// over the sheet: shifting with the phone's turn over the shadow they
/// cast, and on the dark page brighter than its white where the screen can
/// (`Chalk`, `ChalkMarks`), with a number beside each;
/// their labels under the sheet in two columns, hand-written: a title and a
/// line under it. A tap on a label picks its mark out on the sheet: the
/// others step back until it is tapped again. A tap on the sheet shows the
/// picture itself under the marks, another brings the sheet back (no sign
/// for it on the sheet).
///
/// From a server that sends the sheet's two layers (`layers`) it is laid
/// down before the reader, pen then stains then chalk (`SheetLayers`), and
/// each chalk mark lies on a plane of its own over the sheet (`ChalkMarks`).
/// Where the server has the layers with the page's margin beside the field
/// (`bleed`), they are laid wider than the frame: a stain or two run out to
/// the screen's edge and a stroke of the pen goes on past the frame.
///
/// A server from before the sheet (no `sheet`), or a sheet that would not
/// load: the picture as it is, the marks in pencil with a paper-coloured
/// edge, and a tap hides them.
struct CompositionSketch: View {
    @Environment(AppModel.self) private var model
    @Environment(\.colorScheme) private var scheme
    let item: RemoteItem
    /// The whole picture's shape (the sheet shows its field).
    let aspect: CGFloat
    let take: DailyWork.Take
    /// Server path of the take's study sheet ("" when it has none).
    var sheet: String = ""
    /// The server has the sheet as its two layers too (the stains, the pen).
    var layers = false
    /// How much wider than the field the layers can be had on each side (of
    /// the field's width): the page's margin, into which a stain runs out
    /// and a stroke goes on (Mateusz 2026-11-12 11:04: "plamy akwareli mogą
    /// w jednym czy max 2 miejscach wylewać się i sięgać krawędzi bocznej
    /// ekranu. podobnie kreska rysunku - pojedyncza może wystawać poza
    /// kadr"). 0 from a server before that: the layers end at the frame.
    var bleed: CGFloat = 0
    /// The text block's width: the picture takes all of it, the same in
    /// every take (nil: as wide as the column lets it).
    var width: CGFloat? = nil
    @State private var bare = LaunchRoute.compositionBare
    /// The sheet's pictures that are here: the marks come with them.
    @State private var loaded: Set<ImageRef> = []
    /// The sheet that would not load: the marks go on the picture.
    @State private var failed: ImageRef?
    /// The sheet is drawn far enough for the chalk (`SheetLayers`).
    @State private var chalkDue = false
    /// The label that was tapped (by its number): its mark is lit on the
    /// sheet and the others step back (Mateusz 2026-11-12 11:31:
    /// "Dotknięcie podpisu z numerkiem pod spodem niech jakoś zapala -
    /// wyróżnia wskazane zakreślenie na szkicu powyżej").
    @State private var chosen: Int? = LaunchRoute.chalkChosen

    /// A mark with a label, by its number on the picture.
    struct Labelled: Identifiable {
        let number: Int
        let mark: DailyWork.Mark
        var id: Int { number }
    }

    /// The sheet's pictures for the page's colour now: the whole sheet, or
    /// its stains and its pen (`Self.sheetRefs`).
    private var sheetRefs: [ImageRef] {
        Self.sheetRefs(sheet, layers: layers, bleed: bleed, dark: scheme == .dark)
    }

    static func sheetRefs(_ sheet: String, layers: Bool, bleed: CGFloat = 0, dark: Bool) -> [ImageRef] {
        guard !sheet.isEmpty else { return [] }
        let page = sheet + (dark ? "&dark=1" : "")
        guard layers else { return [.path(page)] }
        let wide = bleed > 0 ? "-bleed" : ""
        return [.path(page + "&layer=wash" + wide), .path(page + "&layer=pen" + wide)]
    }

    var body: some View {
        let refs = sheetRefs.first == failed ? [] : sheetRefs
        let marks = refs.isEmpty ? take.marks : take.marksInField
        let labelled = Self.labelled(marks)
        let here = !refs.isEmpty && refs.allSatisfy(loaded.contains)
        VStack(spacing: 14) {
            if !refs.isEmpty {
                sheetPicture(refs, marks: marks, labelled: labelled, here: here)
            } else {
                picture(labelled)
            }
            if !labelled.isEmpty {
                LazyVGrid(
                    columns: [GridItem(.flexible(), spacing: 14, alignment: .topLeading), GridItem(.flexible(), alignment: .topLeading)],
                    alignment: .leading,
                    spacing: 12
                ) {
                    ForEach(labelled) { entry in
                        if refs.isEmpty {
                            label(entry, chalk: false)
                        } else {
                            pointing(entry)
                        }
                    }
                }
            }
        }
        .animation(.easeOut(duration: 0.3), value: here)
        .sensoryFeedback(.selection, trigger: chosen)
    }

    /// A label of the sheet: a tap leaves its mark alone over the sheet,
    /// another lets it go; the labels of the others step back with their
    /// marks.
    private func pointing(_ entry: Labelled) -> some View {
        let lit = chosen == entry.number
        return label(entry, chalk: true)
            .opacity(chosen == nil || lit ? 1 : Chalk.aside)
            .contentShape(Rectangle())
            .onTapGesture {
                withAnimation(.easeInOut(duration: 0.25)) { chosen = lit ? nil : entry.number }
            }
            .accessibilityAddTraits(lit ? [.isButton, .isSelected] : .isButton)
            .accessibilityHint(lit ? "Przestaje wyróżniać ten znak" : "Wyróżnia ten znak na arkuszu")
    }

    /// The place among `marks` of the mark whose label was tapped.
    static func chosenMark(_ number: Int?, among marks: [DailyWork.Mark]) -> Int? {
        guard let number else { return nil }
        let owners = ChalkDrawing.owners(marks)
        return owners.indices.contains(number - 1) ? owners[number - 1] : nil
    }

    private let pencil = Pencil.lead
    private let paper = Pencil.paper

    /// A box of the given shape: the whole given width, as tall as the
    /// shape makes it.
    @ViewBuilder
    private func box(_ aspect: CGFloat) -> some View {
        if let width, width > 0 {
            Color.clear.frame(width: width, height: width / aspect)
        } else {
            Color.clear.frame(maxWidth: .infinity).aspectRatio(aspect, contentMode: .fit)
        }
    }

    private var pictureRef: ImageRef { item.inLibrary ? item.item.originalRef : item.thumb }

    // MARK: The study sheet

    /// The field's shape: the picture's, cut to its field.
    private var fieldAspect: CGFloat {
        let field = take.shownField
        return aspect * CGFloat(field.w / field.h)
    }

    /// The sheet with the marks over it. The frame and the grid run a
    /// little past the field's corners, as ruled by hand, and the
    /// picture's great lines further (`Pencil.overflow`): room is made
    /// above and below for them, at the sides they run into the gutter.
    /// No marks before the sheet is here: they are drawn on it, not on
    /// the bare page. A sheet in two layers is drawn before the reader
    /// and its marks come one after another once it is.
    private func sheetPicture(_ refs: [ImageRef], marks: [DailyWork.Mark], labelled: [Labelled], here: Bool) -> some View {
        let room = sheetRoom(marks)
        let dark = scheme == .dark
        let drawn = refs.count == 2
        return box(fieldAspect)
            .overlay {
                Group {
                    if drawn {
                        // Wider than the frame by the page's margin on each
                        // side, where the server's layers are.
                        GeometryReader { geometry in
                            SheetLayers(
                                wash: refs[0], pen: refs[1], strokes: take.sketch ?? [], ready: here,
                                maxPixel: Self.sheetPixels, bleed: bleed
                            ) { chalkDue = true }
                            .padding(.horizontal, -bleed * geometry.size.width)
                        }
                    } else {
                        ArtImage(ref: refs[0], placeholder: .clear, maxPixel: Self.sheetPixels)
                    }
                }
                .environment(\.artImageLoaded) { loaded in sheetLoaded(loaded) }
                .opacity(bare ? 0 : 1)
            }
            .overlay {
                // The picture itself, cut to the field: only once asked for.
                if bare { fieldOfPicture.transition(.opacity) }
            }
            .overlay {
                Canvas { context, size in
                    let field = Self.pictureRect(in: size, room: room)
                    context.translateBy(x: field.minX, y: field.minY)
                    drawRuling(in: &context, size: field.size, dark: dark)
                }
                .padding(EdgeInsets(top: -room.top, leading: -room.leading, bottom: -room.bottom, trailing: -room.trailing))
                .allowsHitTesting(false)
            }
            .overlay {
                ChalkMarks(
                    marks: marks, labelled: labelled, room: room, shown: here && (chalkDue || !drawn), planes: drawn,
                    chosen: Self.chosenMark(chosen, among: marks)
                )
                    .padding(EdgeInsets(top: -room.top, leading: -room.leading, bottom: -room.bottom, trailing: -room.trailing))
                    .allowsHitTesting(false)
            }
            .contentShape(Rectangle())
            .onTapGesture {
                withAnimation(.easeInOut(duration: 0.3)) { bare.toggle() }
            }
            .sensoryFeedback(.selection, trigger: bare)
            .accessibilityAddTraits(.isButton)
            .accessibilityHint(bare ? "Pokazuje arkusz analizy" : "Pokazuje obraz pod śladami analizy")
            .padding(.top, room.top)
            .padding(.bottom, room.bottom)
            .frame(maxWidth: .infinity)
            .task(id: refs) {
                // A sheet already in memory has its marks at once.
                for ref in refs where sheetInMemory(ref) { loaded.insert(ref) }
            }
    }

    /// The picture cut to the field the sheet shows.
    private var fieldOfPicture: some View {
        GeometryReader { geometry in
            let field = take.shownField
            let whole = CGSize(width: geometry.size.width / field.w, height: geometry.size.height / field.h)
            ArtImage(ref: pictureRef, fallback: .thumb(item.id), placeholder: item.item.placeholderColor, maxPixel: 1600)
                .frame(width: whole.width, height: whole.height)
                .offset(x: -field.x * whole.width, y: -field.y * whole.height)
        }
        .clipped()
    }

    /// The sheet is here, or was given up on: with it come the marks;
    /// without it they go on the picture, as before the sheet.
    private func sheetLoaded(_ ref: ImageRef) {
        let refs = sheetRefs
        guard refs.contains(ref) else { return }
        if sheetInMemory(ref) {
            loaded.insert(ref)
        } else {
            failed = refs.first
        }
    }

    private func sheetInMemory(_ ref: ImageRef) -> Bool {
        model.backend.request(for: ref).flatMap { ImageLoader.inMemory(for: $0, maxPixel: Self.sheetPixels) } != nil
    }

    private static let sheetPixels: CGFloat = 1600

    /// Room around the field for what runs past it: the frame's and the
    /// grid's ends always, the marks' as far as they reach.
    private func sheetRoom(_ marks: [DailyWork.Mark]) -> EdgeInsets {
        let least = Pencil.reach + 2
        guard let width, width > 0, fieldAspect > 0 else {
            return EdgeInsets(top: least, leading: least, bottom: least, trailing: least)
        }
        let size = CGSize(width: width, height: width / fieldAspect)
        let marks = Pencil.overflow(of: marks, in: size, weight: Chalk.weight)
        return EdgeInsets(
            top: max(marks.top, least), leading: max(marks.leading, least),
            bottom: max(marks.bottom, least), trailing: max(marks.trailing, least)
        )
    }

    /// The frame and the grid ruled in graphite (the marks lie over them,
    /// `ChalkMarks`).
    private func drawRuling(in context: inout GraphicsContext, size: CGSize, dark: Bool) {
        let graphite = Theme.ink.opacity(dark ? 0.5 : 0.55)
        let corners = [CGPoint.zero, CGPoint(x: size.width, y: 0), CGPoint(x: size.width, y: size.height), CGPoint(x: 0, y: size.height)]
        for index in 0..<4 {
            let path = Pencil.ruled(corners[index], corners[(index + 1) % 4], over: Pencil.reach, width: 0.9, seed: 70 + index)
            context.fill(path, with: .color(graphite))
        }
        for (index, line) in Pencil.grid(take.grid, in: size).enumerated() {
            let path = Pencil.ruled(line[0], line[1], over: Pencil.reach, width: 0.9, seed: 90 + index)
            context.fill(path, with: .color(graphite))
        }
    }

    // MARK: The picture itself (before the sheet)

    /// The picture with the marks over it. The picture's great lines may
    /// run on past its edges (Mateusz 2026-11-02): there they go on in the
    /// page's ink over its background, room made above and below for them;
    /// at the sides they run to the screen's edge.
    private func picture(_ labelled: [Labelled]) -> some View {
        let room = overflow
        return box(aspect)
            .overlay {
                ArtImage(
                    ref: pictureRef,
                    fallback: .thumb(item.id),
                    placeholder: item.item.placeholderColor,
                    maxPixel: 1600
                )
            }
            .clipShape(RoundedRectangle(cornerRadius: Self.corner, style: .continuous))
            .overlay {
                ZStack {
                    Canvas { context, size in drawOutside(in: &context, size: size, room: room) }
                    Canvas { context, size in
                        let picture = Self.pictureRect(in: size, room: room)
                        context.clip(to: Path(roundedRect: picture, cornerRadius: Self.corner, style: .continuous))
                        context.translateBy(x: picture.minX, y: picture.minY)
                        draw(in: &context, size: picture.size, labelled: labelled)
                    }
                    .shadow(color: .black.opacity(0.3), radius: 1.5, y: 0.5)
                }
                .padding(EdgeInsets(top: -room.top, leading: -room.leading, bottom: -room.bottom, trailing: -room.trailing))
                .opacity(bare ? 0 : 1)
                .allowsHitTesting(false)
            }
            .contentShape(Rectangle())
            .onTapGesture {
                withAnimation(.easeInOut(duration: 0.25)) { bare.toggle() }
            }
            .sensoryFeedback(.selection, trigger: bare)
            .accessibilityAddTraits(.isButton)
            .accessibilityHint(bare ? "Pokazuje ślady analizy" : "Pokazuje sam obraz")
            .padding(.top, room.top)
            .padding(.bottom, room.bottom)
            .frame(maxWidth: .infinity)
    }

    private static let corner: CGFloat = 3

    /// The field's place in the picture of `size`: where the grid goes.
    private func fieldRect(in size: CGSize) -> CGRect {
        let field = take.shownField
        return CGRect(x: field.x * size.width, y: field.y * size.height, width: field.w * size.width, height: field.h * size.height)
    }

    /// Each stroke twice: a wider paper-coloured one under it, then the
    /// pencil; the grid fainter, the numbers on paper discs (`Pencil.badge`).
    private func draw(in context: inout GraphicsContext, size: CGSize, labelled: [Labelled]) {
        let field = fieldRect(in: size)
        for (index, line) in Pencil.grid(take.grid, in: field.size).enumerated() {
            let moved = line.map { CGPoint(x: $0.x + field.minX, y: $0.y + field.minY) }
            let path = Pencil.stroke(moved, width: 1, seed: 90 + index, start: 0.05, end: 0.05)
            context.stroke(path, with: .color(paper.opacity(0.7)), lineWidth: 1.6)
            context.fill(path, with: .color(pencil.opacity(0.75)))
        }
        for (index, mark) in take.marks.enumerated() {
            let paths = Pencil.paths(for: mark, in: size, seed: index * 7 + 1)
            for path in paths {
                context.stroke(path, with: .color(paper), style: StrokeStyle(lineWidth: 3.2, lineCap: .round, lineJoin: .round))
            }
            for path in paths {
                context.fill(path, with: .color(pencil))
            }
        }
        for entry in labelled {
            Pencil.badge(entry.number, at: Pencil.numberSpot(for: entry.mark, in: size), in: &context)
        }
    }

    /// How far the marks run past the picture's edges, in points: nothing
    /// before the picture's size is known.
    private var overflow: EdgeInsets {
        guard let width, width > 0, aspect > 0 else { return EdgeInsets() }
        return Pencil.overflow(of: take.marks, in: CGSize(width: width, height: width / aspect))
    }

    /// The picture's place in a canvas grown by `room` on each side.
    static func pictureRect(in size: CGSize, room: EdgeInsets) -> CGRect {
        CGRect(
            x: room.leading, y: room.top,
            width: max(size.width - room.leading - room.trailing, 1),
            height: max(size.height - room.top - room.bottom, 1)
        )
    }

    /// The marks' parts beyond the picture: plain strokes in the page's ink
    /// (dark on the light page, light on the dark one), no paper edge.
    private func drawOutside(in context: inout GraphicsContext, size: CGSize, room: EdgeInsets) {
        guard room.top + room.bottom + room.leading + room.trailing > 0 else { return }
        let picture = Self.pictureRect(in: size, room: room)
        var outside = Path(CGRect(origin: .zero, size: size))
        outside.addRoundedRect(in: picture, cornerSize: CGSize(width: Self.corner, height: Self.corner), style: .continuous)
        context.clip(to: outside, style: FillStyle(eoFill: true))
        context.translateBy(x: picture.minX, y: picture.minY)
        for (index, mark) in take.marks.enumerated() {
            for path in Pencil.paths(for: mark, in: picture.size, seed: index * 7 + 1) {
                context.fill(path, with: .color(Theme.ink.opacity(0.85)))
            }
        }
    }

    // MARK: The notes

    /// The number on the same badge as on the picture, and beside it the
    /// title with its line under it: the line starts where the title does,
    /// not under the number. `chalk`: the mark is drawn in chalk on the
    /// sheet (else in the lead pencil on its paper disc).
    private func label(_ entry: Labelled, chalk: Bool) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 5) {
            Canvas { context, size in
                let spot = CGPoint(x: size.width / 2, y: size.height / 2)
                if chalk {
                    Chalk.badge(entry.number, of: entry.mark, at: spot, in: &context, dark: scheme == .dark)
                } else {
                    Pencil.badge(entry.number, at: spot, in: &context)
                }
            }
            .frame(width: 22, height: 22)
            // (the sheet's number lies on the page's own colour: no edge)
            .shadow(color: .black.opacity(chalk ? 0 : 0.22), radius: 1.2, y: 0.5)
            .alignmentGuide(.firstTextBaseline) { $0[VerticalAlignment.center] + 5 }
            .accessibilityHidden(true)
            // The hand-written face has tall lines: the note sits close
            // under its title, and its own lines close together, as
            // written by hand.
            // A title that takes two lines is written word by word too:
            // as one text its lines stood a whole tall line apart, far
            // more than the note's under it (Mateusz 2026-11-12 12:44:
            // "coś się posypały odstępy w nagłówkach tekstu?").
            VStack(alignment: .leading, spacing: -7) {
                HandLines(text: entry.mark.title, size: 21, even: true)
                if !entry.mark.text.isEmpty {
                    HandLines(text: entry.mark.text, size: 18)
                        .foregroundStyle(Theme.inkSoft)
                }
            }
        }
        .foregroundStyle(Theme.ink)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The marks with a title, numbered in the order the model gave them
    /// (the eye's path): untitled marks are drawn, not labelled.
    static func labelled(_ marks: [DailyWork.Mark]) -> [Labelled] {
        marks.filter { !$0.title.isEmpty }.enumerated().map { Labelled(number: $0.offset + 1, mark: $0.element) }
    }
}

/// The stick the study sheet's marks are drawn in: a blue coloured pencil
/// (deep on the light page, pale on the dark one), heavier than the pen's
/// sketch under it, every mark alike: what only answers across the picture
/// (a colour that returns) is told by its form, small rings and a broken
/// line between them. Its numbers are written in the same pencil, each in
/// a ring of it on a dab of the page's colour.
///
/// Blue since Mateusz saw the trial sheets of the pen's fourth round, drawn
/// so (2026-11-12 19:40: "Fajnie też współgra teraz z niebieską linią. I
/// tak to wdrażajmy (teraz w apce jest czarna, inaczej to wygląda i trzeba
/// to pozmieniać."; 19:44: "To co wdrażamy teraz - niech wygląda tak jak na
/// Twoim szkicu."). Before that it was the pen's own colour, with red for
/// a returning colour, and white first; seen on the phone, the white lines read
/// worse than the sketch under them (Mateusz 2026-11-12 11:31: "Chyba linie
/// kredą są mniej czytelne niż szkic pod spodem. Może zróbmy tak: szkic pod
/// spodem słabszy, a linie kredą - ciut mocniejsze i grubsze niż rysunek
/// teraz. W kolorze rysunku, a powtórki kolorów zostawiamy czerwone").
/// Seen so, they were still too weak (12:44: "Rysunki kredy są za słabe.
/// muszą się wyraźniej odcinać. Może trzeba jeszcze rozjaśnić akwarelę w
/// trybie jasnym, a przyciemnić w ciemnym?"): the stick is broader and
/// pressed harder, less of it is lost in the paper's tooth, and the sheet
/// under it is laid thinner (`SheetPlan.washShare`, `penShare`).
/// The brighter copy is for light chalk, so it is made on the dark page
/// only, and dark chalk on the light page keeps no shadow with the phone
/// held still.
///
/// How it came to stand over the sheet: Mateusz 2026-11-12, of the coloured
/// pencil with the wash wiped to the page's colour under it: "Nie podoba mi
/// się ten styl kolorowych kresek na białym podkładzie … A może kreski
/// mogłyby mieć podbicie HDR? I wtedy być rysowane bielą a te od akcentów
/// kolorystycznych np. czerwienią?", and "kredka z delikatnym efektem
/// paralaksy … Takie 1,5pt przesunięcia".
///
/// So nothing lies under a stroke. What sets the marks off the sheet:
/// they are brighter than the page's own white where the screen has the
/// headroom (an extended-range copy, as `ArtGlow` makes of a picture), and
/// they shift over it as the phone turns, over a shadow that shows only
/// then.
///
/// Of that, 07:01: "Cień pod liniami jeżeli już, to minimalny i widoczny
/// tylko po przechyleniu telefonu"; "kreska kredy powinna być bardziej jak
/// kreda a nie piórko - teraz wygląda bardzo wektorowo i elektronicznie";
/// "nie podoba mi się czerwony numerek powtórzenia koloru, za bardzo zwraca
/// na siebie uwagę". So a stroke is a stick's: blunt at its ends, pressed
/// unevenly, a little dust beside it, and it stays only where the paper's
/// tooth took it (`tooth`, as the pastel of the colour bars). The shadow is
/// not there with the phone held still. Only where the screen has no
/// headroom (Low Power Mode, full sun), and white chalk would be lost on
/// the bare page, a faint one stays.
enum Chalk {
    /// The coloured pencil on each page, given outright: a picture
    /// rendered off screen knows no colour scheme.
    static func blue(dark: Bool) -> Color {
        Color(hex: dark ? 0x78A8FF : 0x1238A8)
    }

    /// The page's own colour (`Theme.paper`), under a number.
    static func page(dark: Bool) -> Color {
        Color(hex: dark ? 0x121110 : 0xF5F1EA)
    }

    static func color(for mark: DailyWork.Mark, dark: Bool) -> Color {
        blue(dark: dark)
    }

    /// How heavy the chalk is against the lead pencil's widths: two to
    /// three times the sheet's pen (about a point on a phone). It was 0.95
    /// and read as weak.
    static let weight: CGFloat = 1.25
    /// How much of a mark and of its label is left when another's label
    /// was tapped. Nothing is added to the one that was: it stands out by
    /// the others stepping back (Mateusz 2026-11-12 12:44, of a yellow
    /// light behind it: "na pewno nie żółte podświetlenie. raczej
    /// przygaszenie pozostałych").
    static let aside = 0.2

    /// How many times brighter than the page's white the chalk is drawn
    /// where the screen can (about a stop; picked by reasoning, not yet
    /// seen on a phone).
    static let gain: CGFloat = 2
    /// How far the marks move at a full turn of the phone, in points, and
    /// their shadow the other way.
    static let shift: CGFloat = 1.5
    static let castShift: CGFloat = 1
    /// With each mark on a plane of its own: how far the highest (the
    /// first mark, the main one) and the lowest move at a full turn, the
    /// others evenly between (picked by reasoning, around the 1.5 pt he
    /// asked for; not yet seen on a phone).
    static let highShift: CGFloat = 2.6
    static let lowShift: CGFloat = 0.8
    /// How long a mark takes to come onto the drawn sheet, and how long
    /// after the one before it starts.
    static let comeIn = 0.35
    static let comeGap = 0.2

    /// Which marks (by their place) each plane holds, the highest first:
    /// one each when `apart`, else all on one.
    static func planes(_ count: Int, apart: Bool) -> [[Int]] {
        guard count > 0 else { return [] }
        return apart ? (0..<count).map { [$0] } : [Array(0..<count)]
    }

    /// How far a plane moves at a full turn: `shift` when it is the only one.
    static func planeShift(_ plane: Int, of count: Int) -> CGFloat {
        guard count > 1 else { return shift }
        return highShift - (highShift - lowShift) * CGFloat(plane) / CGFloat(count - 1)
    }

    /// How far the shadow of a plane that moves `shift` goes the other
    /// way: further under a higher plane.
    static func castReach(under plane: CGFloat) -> CGFloat {
        castShift * plane / shift
    }
    /// How soft the shadow is and how dark on each page at a full turn.
    static let castBlur: CGFloat = 1
    static func castDepth(dark: Bool) -> Double { dark ? 0.5 : 0.34 }
    /// Without headroom: how much of that shadow stays with the phone held
    /// still, and where it lies then (the light from the upper left).
    static let castUnlit = 0.55
    static let castRest = CGSize(width: 0.4, height: 0.7)

    /// How much of the shadow shows at this turn of the phone (`x`, `y`:
    /// `Tilt`'s): none held still where the chalk is lit above the page's
    /// white, all at a full turn.
    static func castShown(x: Double, y: Double, lit: Bool, still: Bool) -> Double {
        let turned = still ? 0 : min(1, hypot(x, y))
        return lit ? turned : max(castUnlit, turned)
    }

    /// How hard the stick is pressed in a stroke, each its own (0.9…1).
    static func press(_ seed: Int) -> Double {
        0.9 + 0.1 * Pencil.Jitter.random(seed &* 31 &+ 5)
    }

    /// The dust a stick leaves beside its stroke: how far out, how thin.
    static let dustWidth: CGFloat = 1.5
    static let dust = 0.3

    /// The paper's tooth as a tile (`toothSide` points square): how much
    /// of the chalk stays at each place, in its alpha.
    static let toothSide = 96
    static let toothScale = 3
    static let tooth: CGImage? = {
        let side = toothSide * toothScale
        var bytes = [UInt8](repeating: 0, count: side * side * 4)
        for k in 0..<(side * side) {
            let x = (Double(k % side) + 0.5) / Double(toothScale), y = (Double(k / side) + 0.5) / Double(toothScale)
            let grain = 0.5 * Paint.noise(x / 0.55, y / 0.55, 241) + 0.3 * Paint.noise(x / 1.3, y / 1.3, 242)
                + 0.2 * Paint.noise(x / 4, y / 4, 243)
            bytes[4 * k + 3] = Paint.byte(255 * kept(grain))
        }
        guard let provider = CGDataProvider(data: Data(bytes) as CFData),
              let space = CGColorSpace(name: CGColorSpace.sRGB)
        else { return nil }
        return CGImage(
            width: side, height: side, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: side * 4,
            space: space, bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
            provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent
        )
    }()

    /// How much chalk stays where the paper's grain is `grain` (0…1): all
    /// on its hills, most of it in its hollows (a little over half made
    /// the strokes thin out against the stains).
    static func kept(_ grain: Double) -> Double {
        0.78 + 0.22 * Paint.step(0.36, 0.6, grain)
    }

    /// The gain for a screen with this headroom: nil where it would not
    /// show, and on the light page, where the chalk is dark.
    static func lift(headroom: CGFloat, dark: Bool = true) -> CGFloat? {
        guard dark else { return nil }
        let lift = min(gain, headroom * 0.9)
        return lift > 1.05 ? lift : nil
    }

    /// How far a layer that moves `shift` points at a full turn is moved
    /// now (`x`, `y`: `Tilt`'s, -1 to 1); nowhere with Reduce Motion.
    static func offset(x: Double, y: Double, shift: CGFloat, still: Bool) -> CGSize {
        still ? .zero : CGSize(width: CGFloat(x) * shift, height: CGFloat(y) * shift)
    }

    /// A mark's number, written by hand in the coloured pencil, in a ring
    /// of it on a dab of the page's colour. The same on the sheet and in
    /// the notes under it.
    static func badge(
        _ number: Int, of mark: DailyWork.Mark, at spot: CGPoint, in context: inout GraphicsContext, dark: Bool
    ) {
        Pencil.badge(number, at: spot, in: &context, ink: color(for: mark, dark: dark), paper: page(dark: dark), hand: true)
    }
}

/// A take's marks in chalk with their numbers, or (`cast`) the shadow they
/// throw; in a canvas grown by `room` around the picture's field. `only`:
/// just these marks (by their place among `marks`) and their numbers, as
/// one plane over the sheet holds them (`ChalkMarks`); each is drawn the
/// same alone as among the others.
struct ChalkDrawing: View {
    let marks: [DailyWork.Mark]
    let labelled: [CompositionSketch.Labelled]
    let room: EdgeInsets
    var cast = false
    var only: [Int]? = nil
    /// The page is the dark one: the chalk is light.
    var dark = false

    /// The place among `marks` of each labelled one, in the labels' order.
    static func owners(_ marks: [DailyWork.Mark]) -> [Int] {
        marks.indices.filter { !marks[$0].title.isEmpty }
    }

    private func has(_ index: Int) -> Bool { only?.contains(index) != false }

    /// The strokes of each mark drawn here, with its place among `marks`.
    private func strokes(in size: CGSize) -> [(index: Int, mark: DailyWork.Mark, paths: [Path])] {
        marks.enumerated().compactMap { (index, mark) -> (index: Int, mark: DailyWork.Mark, paths: [Path])? in
            guard has(index) else { return nil }
            return (index: index, mark: mark, paths: Pencil.paths(for: mark, in: size, seed: index * 7 + 1, weight: Chalk.weight, chalk: true))
        }
    }

    /// The numbers drawn here and where.
    private func numbers(in size: CGSize) -> [(entry: CompositionSketch.Labelled, spot: CGPoint)] {
        let owners = Self.owners(marks)
        let spots = Pencil.numberSpots(for: labelled.map(\.mark), in: size, among: marks)
        return zip(labelled, spots).enumerated().compactMap { (place, pair) -> (entry: CompositionSketch.Labelled, spot: CGPoint)? in
            guard place < owners.count, has(owners[place]) else { return nil }
            return (entry: pair.0, spot: pair.1)
        }
    }

    /// Where what is drawn here lies in a canvas of `size`, with room for
    /// its dust: what a plane's brighter copy is cut to.
    func bounds(in size: CGSize) -> CGRect {
        let field = CompositionSketch.pictureRect(in: size, room: room)
        var box = CGRect.null
        for entry in strokes(in: field.size) {
            for path in entry.paths where !path.isEmpty {
                box = box.union(path.boundingRect)
            }
        }
        for number in numbers(in: field.size) {
            box = box.union(CGRect(x: number.spot.x - 11, y: number.spot.y - 11, width: 22, height: 22))
        }
        guard !box.isNull else { return .zero }
        return box.offsetBy(dx: field.minX, dy: field.minY).insetBy(dx: -4, dy: -4)
    }

    var body: some View {
        Canvas { context, size in
            let field = CompositionSketch.pictureRect(in: size, room: room)
            context.translateBy(x: field.minX, y: field.minY)
            let drawn = strokes(in: field.size)
            let numbered = numbers(in: field.size)
            if cast {
                var soft = context
                soft.addFilter(.blur(radius: Chalk.castBlur))
                soft.drawLayer { layer in
                    for entry in drawn {
                        for path in entry.paths {
                            layer.fill(path, with: .color(.black))
                        }
                    }
                    for number in numbered {
                        let spot = number.spot
                        let reach: CGFloat = 9.5
                        layer.fill(
                            Path(ellipseIn: CGRect(x: spot.x - reach, y: spot.y - reach, width: 2 * reach, height: 2 * reach)),
                            with: .color(.black)
                        )
                    }
                }
            } else {
                // The strokes, then all of them rubbed into the paper's tooth.
                let whole = CGRect(x: -field.minX, y: -field.minY, width: size.width, height: size.height)
                context.drawLayer { layer in
                    for entry in drawn {
                        let colour = Chalk.color(for: entry.mark, dark: dark)
                        for (part, path) in entry.paths.enumerated() {
                            layer.stroke(
                                path, with: .color(colour.opacity(Chalk.dust)),
                                style: StrokeStyle(lineWidth: Chalk.dustWidth, lineCap: .round, lineJoin: .round)
                            )
                            layer.fill(path, with: .color(colour.opacity(Chalk.press(entry.index * 17 + part))))
                        }
                    }
                    if let tooth = Chalk.tooth {
                        layer.blendMode = .destinationIn
                        layer.fill(
                            Path(whole),
                            with: .tiledImage(Image(decorative: tooth, scale: CGFloat(Chalk.toothScale)))
                        )
                    }
                }
                for number in numbered {
                    Chalk.badge(number.entry.number, of: number.entry.mark, at: number.spot, in: &context, dark: dark)
                }
            }
        }
    }
}

/// The marks standing a little over the sheet: the chalk (on the dark page
/// brighter than its white where the screen can show it), and under it its
/// shadow, which shows as the two shift against each other with the phone's
/// turn (`Tilt`; still with Reduce Motion, no gyroscope in Low Power Mode).
///
/// `planes`: each mark stands at a height of its own, the first (the main
/// one) highest, so they shift against one another too and are told apart
/// (Mateusz 2026-11-12 09:47: "Poszczególne oznaczenia / linie kredą mogą
/// być umieszczone na różnych płaszczyznach paralaksy - łatwiej będzie się
/// je czytać"), and they come one after another when `shown` turns true.
///
/// `chosen`: the mark (by its place among `marks`) whose label was tapped.
/// It stays as it is and the others step back; told apart they must each
/// be on a plane of their own, so they are then even where `planes` is
/// not asked for.
struct ChalkMarks: View {
    let marks: [DailyWork.Mark]
    let labelled: [CompositionSketch.Labelled]
    let room: EdgeInsets
    var shown = true
    var planes = false
    var chosen: Int? = nil

    /// How much of a plane holding `group` shows.
    static func share(of group: [Int], chosen: Int?, shown: Bool) -> Double {
        guard shown else { return 0 }
        guard let chosen else { return 1 }
        return group.contains(chosen) ? 1 : Chalk.aside
    }

    var body: some View {
        GeometryReader { geometry in
            let groups = Chalk.planes(marks.count, apart: planes || chosen != nil)
            ZStack {
                // The lowest first: a higher one lies over it.
                ForEach(Array(groups.enumerated().reversed()), id: \.offset) { plane, group in
                    ChalkPlane(
                        marks: marks, labelled: labelled, room: room, only: group, size: geometry.size,
                        shift: planes ? Chalk.planeShift(plane, of: groups.count) : Chalk.shift
                    )
                    .opacity(Self.share(of: group, chosen: chosen, shown: shown))
                    .animation(
                        planes ? .easeOut(duration: Chalk.comeIn).delay(Chalk.comeGap * Double(plane)) : .easeOut(duration: 0.3),
                        value: shown
                    )
                }
            }
            .opacity(LaunchRoute.chalkDemo == "none" ? 0 : 1)
        }
        .followsTilt()
    }

    /// The marks as the canvas draws them, as a picture (clear around them).
    static func plain(
        marks: [DailyWork.Mark], labelled: [CompositionSketch.Labelled], room: EdgeInsets, size: CGSize, scale: CGFloat,
        only: [Int]? = nil, dark: Bool = false
    ) -> CGImage? {
        let renderer = ImageRenderer(
            content: ChalkDrawing(marks: marks, labelled: labelled, room: room, only: only, dark: dark)
                .frame(width: size.width, height: size.height)
        )
        renderer.scale = scale
        return renderer.cgImage
    }

    /// The pixels of a picture `scale` times its points that hold `box`
    /// (in points), and the place in points of exactly those pixels.
    static func cut(_ box: CGRect, of image: CGImage, scale: CGFloat) -> (pixels: CGRect, frame: CGRect)? {
        let whole = CGRect(x: 0, y: 0, width: image.width, height: image.height)
        let pixels = CGRect(x: box.minX * scale, y: box.minY * scale, width: box.width * scale, height: box.height * scale)
            .integral.intersection(whole)
        guard !pixels.isNull, pixels.width >= 1, pixels.height >= 1 else { return nil }
        let frame = CGRect(x: pixels.minX / scale, y: pixels.minY / scale, width: pixels.width / scale, height: pixels.height / scale)
        return (pixels: pixels, frame: frame)
    }
}

/// One plane of marks over the sheet: its chalk, its brighter copy where
/// the screen has headroom (cut to where the marks lie: an extended-range
/// picture of the whole sheet for every plane would be heavy), its shadow.
private struct ChalkPlane: View {
    let marks: [DailyWork.Mark]
    let labelled: [CompositionSketch.Labelled]
    let room: EdgeInsets
    let only: [Int]
    let size: CGSize
    /// How far this plane moves at a full turn of the phone.
    let shift: CGFloat
    @Environment(\.displayScale) private var displayScale
    @Environment(\.colorScheme) private var scheme
    @State private var lit: Lit?

    /// What the brighter copy was made of.
    struct Made: Equatable {
        let marks: [DailyWork.Mark]
        let only: [Int]
        let size: CGSize
        let scale: CGFloat
        let dark: Bool
    }

    private struct Lit {
        let source: Made
        let image: UIImage
        /// Where the copy lies in the plane.
        let frame: CGRect
    }

    var body: some View {
        let dark = scheme == .dark
        let made = Made(marks: marks, only: only, size: size, scale: displayScale, dark: dark)
        let bright = lit.flatMap { $0.source == made ? $0 : nil }
        // Dark chalk needs no shadow to be told from the page: it keeps
        // none with the phone held still, as the lit chalk keeps none.
        let quiet = bright != nil || !dark
        ZStack {
            ChalkDrawing(marks: marks, labelled: labelled, room: room, cast: true, only: only)
                .modifier(Floating(
                    rest: quiet ? .zero : Chalk.castRest, shift: -Chalk.castReach(under: shift),
                    cast: Chalk.castDepth(dark: dark), lit: quiet
                ))
            ZStack(alignment: .topLeading) {
                ChalkDrawing(marks: marks, labelled: labelled, room: room, only: only, dark: dark)
                    .opacity(bright == nil ? 1 : 0)
                if let bright {
                    Image(uiImage: bright.image)
                        .resizable()
                        .allowedDynamicRange(.high)
                        .frame(width: bright.frame.width, height: bright.frame.height)
                        .offset(x: bright.frame.minX, y: bright.frame.minY)
                }
            }
            .modifier(Floating(rest: .zero, shift: shift))
        }
        .task(id: made) { await light(made) }
    }

    /// Makes the brighter copy of this plane's marks as drawn at this size,
    /// where the screen has headroom for it.
    private func light(_ made: Made) async {
        guard made.size.width > 1, made.size.height > 1,
              let gain = Chalk.lift(headroom: LaunchRoute.chalkDemo == "lit" ? 8 : ScreenBoost.shared.headroom, dark: made.dark)
        else {
            lit = nil
            return
        }
        let drawing = ChalkDrawing(marks: marks, labelled: labelled, room: room, only: only, dark: made.dark)
        guard let plain = ChalkMarks.plain(
            marks: marks, labelled: labelled, room: room, size: made.size, scale: made.scale, only: only, dark: made.dark
        ),
              let cut = ChalkMarks.cut(drawing.bounds(in: made.size), of: plain, scale: made.scale),
              let part = plain.cropping(to: cut.pixels)
        else { return }
        let lifted = await Task.detached(priority: .userInitiated, operation: { ArtGlow.render(part, gain: gain) }).value
        guard !Task.isCancelled, let lifted else { return }
        lit = Lit(source: made, image: UIImage(cgImage: lifted, scale: made.scale, orientation: .up), frame: cut.frame)
    }
}

/// Moves a layer with the phone's turn, from where it rests. `cast`: the
/// layer is the marks' shadow, this dark at a full turn and shown as far
/// as the phone is turned (`Chalk.castShown`).
private struct Floating: ViewModifier {
    let rest: CGSize
    let shift: CGFloat
    var cast: Double? = nil
    var lit = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        let tilt = Tilt.shared
        let moved = Chalk.offset(x: tilt.x, y: tilt.y, shift: shift, still: reduceMotion)
        content
            .opacity(cast.map { $0 * Chalk.castShown(x: tilt.x, y: tilt.y, lit: lit, still: reduceMotion) } ?? 1)
            .offset(x: rest.width + moved.width, y: rest.height + moved.height)
    }
}

extension DailyWork.Mark {
    /// Where a remark about the mark points, as the server has it: a
    /// loop's centre, the middle of a rect or triangle, a spiral's eye, a
    /// vanishing point, a rhythm's middle beat, a path's middle point.
    var anchor: DailyWork.Spot {
        guard let first = points.first else { return DailyWork.Spot(x: 0.5, y: 0.5) }
        switch shape {
        case "loop", "rays": return first
        case "rhythm" where points.count >= 2:
            let start = 2 * (points.count / 4)
            let (a, b) = (points[start], points[start + 1])
            return DailyWork.Spot(x: (a.x + b.x) / 2, y: (a.y + b.y) / 2)
        case "rect" where points.count == 2:
            return DailyWork.Spot(x: (points[0].x + points[1].x) / 2, y: (points[0].y + points[1].y) / 2)
        case "triangle" where points.count == 3:
            return DailyWork.Spot(x: points.map(\.x).reduce(0, +) / 3, y: points.map(\.y).reduce(0, +) / 3)
        case "spiral": return points[points.count - 1]
        default: return points[points.count / 2]
        }
    }
}

/// Hand-written text wrapped word by word, its lines closer together than
/// the face's own: Caveat's lines are tall (1.26 em) for its small letters,
/// and SwiftUI's `Text` cannot tighten them (negative line spacing does
/// nothing), so a wrapped note looked double-spaced.
struct HandLines: View {
    let text: String
    let size: CGFloat
    /// Lines of about one length (a title), not a full one and a word
    /// left over under it.
    var even = false

    var body: some View {
        let words = text.split(whereSeparator: \.isWhitespace).map(String.init)
        // Caveat's space is 0.242 em; a line every 0.95 em, as close as the
        // note sits under its title. A word longer than the line is
        // written smaller, not out of the column.
        WordFlow(space: size * 0.242, pitch: size * 0.95, even: even) {
            ForEach(words.indices, id: \.self) { index in
                Text(words[index]).font(.hand(size)).lineLimit(1).minimumScaleFactor(0.7)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(text)
    }
}

/// Words laid out like a paragraph: as many as fit on a line, then the
/// next line `pitch` below (less than a word's own height, so the lines'
/// frames overlap; they have no background).
struct WordFlow: Layout {
    let space: CGFloat
    let pitch: CGFloat
    /// In as few lines as the width takes, but those as even as they can
    /// be: "Żółć wraca / trzy razy", not "Żółć wraca trzy / razy".
    var even = false

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let placed = place(subviews, width: proposal.width ?? .infinity)
        guard let last = placed.last else { return .zero }
        let width = placed.map { $0.origin.x + $0.size.width }.max() ?? 0
        return CGSize(width: width, height: last.origin.y + last.size.height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        for (subview, frame) in zip(subviews, place(subviews, width: bounds.width)) {
            subview.place(
                at: CGPoint(x: bounds.minX + frame.origin.x, y: bounds.minY + frame.origin.y),
                anchor: .topLeading,
                proposal: ProposedViewSize(frame.size)
            )
        }
    }

    /// Each word's frame. A word is offered the whole line: one that fits
    /// answers with its own size, a longer one with the line's width.
    private func place(_ subviews: Subviews, width: CGFloat) -> [CGRect] {
        let line = ProposedViewSize(width: width.isFinite ? width : nil, height: nil)
        let sizes = subviews.map { $0.sizeThatFits(line) }
        return Self.frames(of: sizes, width: width, space: space, pitch: pitch, even: even)
    }

    /// The frames of words of these sizes in a line this wide. `even`:
    /// in no more lines than that takes, laid in the narrowest width that
    /// still takes no more (so the lines come out about one length).
    static func frames(of sizes: [CGSize], width: CGFloat, space: CGFloat, pitch: CGFloat, even: Bool = false) -> [CGRect] {
        let whole = filled(sizes, width: width, space: space, pitch: pitch)
        guard even, width.isFinite, let last = whole.last, last.minY > 0 else { return whole }
        var narrow = sizes.map(\.width).max() ?? 0
        var wide = width
        var best = whole
        for _ in 0..<12 where wide - narrow > 0.5 {
            let middle = (narrow + wide) / 2
            let tried = filled(sizes, width: middle, space: space, pitch: pitch)
            if (tried.last?.minY ?? 0) <= last.minY + 0.01 {
                best = tried
                wide = middle
            } else {
                narrow = middle
            }
        }
        return best
    }

    /// Each word on the line while it fits, else at the start of the next
    /// (a word wider than the line gets a line of its own).
    private static func filled(_ sizes: [CGSize], width: CGFloat, space: CGFloat, pitch: CGFloat) -> [CGRect] {
        var frames: [CGRect] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        for size in sizes {
            // Half a point of give: laid again in exactly the width it asked
            // for, a line must not lose its last word to rounding.
            if x > 0, x + space + size.width > width + 0.5 {
                x = 0
                y += pitch
            }
            if x > 0 { x += space }
            frames.append(CGRect(origin: CGPoint(x: x, y: y), size: size))
            x += size.width
        }
        return frames
    }
}

/// Pencil marks as filled outlines: strokes thin at both ends and a little
/// uneven, loops that overshoot where they close, arrowheads of two
/// strokes. The same seed draws the same mark every time.
enum Pencil {
    /// Pencil and the paper edge around it, the same over any picture.
    static let lead = Color(hex: 0x2E2A25)
    static let paper = Color(hex: 0xFBF8F2)
    /// How much heavier the chalk of the study sheet is than the
    /// lead pencil on the picture (Mateusz 2026-11-11: "trochę mocniej dla
    /// większej czytelności").
    static let crayonWeight: CGFloat = 1.3
    /// How far the sheet's frame and grid run past the field's corners.
    static let reach: CGFloat = 6

    /// A mark's number: on a paper disc in a pencil ring drawn by hand, the
    /// same on the picture and in the legend under it (the ring's seed is
    /// the number, so number 2 has the same ring in both). On the study
    /// sheet it is a dab of the mark's chalk (`Chalk.badge`).
    static func badge(
        _ number: Int, at spot: CGPoint, in context: inout GraphicsContext,
        ink: Color = lead, paper: Color = paper, ring: Color? = nil, hand: Bool = false
    ) {
        context.fill(Path(ellipseIn: CGRect(x: spot.x - 9.5, y: spot.y - 9.5, width: 19, height: 19)), with: .color(paper))
        context.fill(loop(center: spot, rx: 8.5, ry: 8, width: 1.4, seed: 40 + number), with: .color(ring ?? ink))
        // (`hand`: written, as the notes are; the face's figures sit low in its tall line)
        context.draw(
            Text("\(number)").font(hand ? Theme.hand(15) : .system(size: 10.5, weight: .bold)).foregroundStyle(ink),
            at: hand ? CGPoint(x: spot.x, y: spot.y - 0.5) : spot
        )
    }

    /// The radius of the small ring at each of an echo's places, as the
    /// server measures it (`ai/sketch.py` ECHO_RING).
    static func echoRing(in size: CGSize) -> CGFloat {
        max(size.width, size.height) * 0.03
    }

    /// The broken, slightly bowed line from each of an echo's rings to the
    /// next: its dashes, as the server draws them (`ai/sketch.py`).
    static func echoDashes(_ points: [CGPoint], in size: CGSize) -> [[CGPoint]] {
        let longer = max(size.width, size.height)
        let gap = echoRing(in: size) + longer * 0.005
        var found: [[CGPoint]] = []
        for (a, b) in zip(points, points.dropFirst()) {
            let length = hypot(b.x - a.x, b.y - a.y)
            let span = length - 2 * gap
            guard span > 0 else { continue }
            let (ux, uy) = ((b.x - a.x) / length, (b.y - a.y) / length)
            let bow = 0.07 * length
            let count = max(Int(span / (longer * 0.023)), 2)
            for k in 0..<count {
                found.append([CGFloat(k), CGFloat(k) + 0.275, CGFloat(k) + 0.55].map { step in
                    let d = gap + step / CGFloat(count) * span
                    let lift = bow * sin(.pi * d / length)
                    return CGPoint(x: a.x + ux * d + uy * lift, y: a.y + uy * d - ux * lift)
                })
            }
        }
        return found
    }

    /// A mark's strokes in a picture of `size`. `weight`: how much heavier
    /// than the lead pencil (the sheet's chalk). `chalk`: a stick, not a
    /// point: its strokes end blunt.
    static func paths(for mark: DailyWork.Mark, in size: CGSize, seed: Int, weight: CGFloat = 1, chalk: Bool = false) -> [Path] {
        paths(for: mark, in: size, seed: seed, pen: Pen(weight: weight, least: chalk ? bluntEnd : pointedEnd))
    }

    /// How much of a stroke's width is left where it lands and lifts: a
    /// pencil's point, a stick of chalk.
    static let pointedEnd: CGFloat = 0.25
    static let bluntEnd: CGFloat = 0.72

    /// How heavy the pencil is (every stroke's width times it) and how
    /// blunt (`least`: the share of the width left at a stroke's ends).
    struct Pen {
        let weight: CGFloat
        var least: CGFloat = Pencil.pointedEnd
        func callAsFunction(_ width: CGFloat) -> CGFloat { width * weight }
    }

    private static func paths(for mark: DailyWork.Mark, in size: CGSize, seed: Int, pen: Pen) -> [Path] {
        let points = mark.points.map { CGPoint(x: $0.x * size.width, y: $0.y * size.height) }
        guard let first = points.first else { return [] }
        switch mark.shape {
        case "echo" where points.count >= 2:
            // Places that answer each other: a small ring at each and a
            // broken line between them, which nobody reads as an edge.
            let radius = echoRing(in: size)
            return points.enumerated().map { index, point in
                loop(center: point, rx: radius, ry: radius, width: pen(1.7), seed: seed + index, least: pen.least)
            } + echoDashes(points, in: size).enumerated().map { index, dash in
                stroke(dash, width: pen(1.6), seed: seed + 10 + index, start: 0.2, end: 0.2, least: pen.least)
            }
        case "loop":
            let corner = points.count > 1 ? points[1] : first
            let rx = max(abs(corner.x - first.x), 8)
            let ry = max(abs(corner.y - first.y), 8)
            return [loop(center: first, rx: rx, ry: ry, width: pen(2.4), seed: seed, least: pen.least)]
        case "triangle" where points.count == 3:
            return (0..<3).map { side(points[$0], points[($0 + 1) % 3], width: pen(2), seed: seed + $0, least: pen.least) }
        case "rect" where points.count == 2:
            let (a, b) = (points[0], points[1])
            let corners = [a, CGPoint(x: b.x, y: a.y), b, CGPoint(x: a.x, y: b.y)]
            return (0..<4).map { side(corners[$0], corners[($0 + 1) % 4], width: pen(1.6), seed: seed + $0, least: pen.least) }
        case "underline" where points.count >= 2:
            return [stroke(wave(from: first, to: points[points.count - 1]), width: pen(2.2), seed: seed, least: pen.least)]
        case "spiral" where points.count == 3:
            let line = spiral(start: points[0], through: points[1], eye: points[2])
            return line.count >= 2 ? [stroke(line, width: pen(2.2), seed: seed, start: 0.04, end: 0.3, least: pen.least)] : []
        case "rhythm" where points.count >= 4:
            // A stroke along each repeated form, all parallel, no line between them.
            return beats(points).enumerated().map { index, beat in
                stroke(beat, width: pen(2.3), seed: seed + index, start: 0.14, end: 0.14, least: pen.least)
            }
        case "rays" where points.count >= 3:
            // Each ray from its far end into the vanishing point, thinning as it goes.
            let eye = points[0]
            return points.dropFirst().enumerated().map { index, end in
                stroke([end, eye], width: pen(1.9), seed: seed + index, start: 0.05, end: 0.45, least: pen.least)
            }
        case "motion" where points.count >= 2:
            // A sweeping arrow, two speed lines trailing beside its start.
            let line = smooth(points)
            let tip = line[line.count - 1]
            let from = line[max(0, line.count - 6)]
            return [stroke(points, width: pen(3), seed: seed, start: 0.02, end: 0.08, least: pen.least)]
                + speedLines(line, gap: 6.5).enumerated().map { index, trail in
                    stroke(trail, width: pen(1.5), seed: seed + 3 + index, start: 0.3, end: 0.3, least: pen.least)
                }
                + head(tip: tip, from: from, width: pen(2.6), size: 13, least: pen.least)
        case "arrow" where points.count >= 2:
            let pieces = corners(points)
            let line = smooth(pieces[pieces.count - 1])
            let tip = line[line.count - 1]
            let from = line[max(0, line.count - 6)]
            return pieces.enumerated().map { stroke($1, width: pen(2.6), seed: seed + $0, least: pen.least) }
                + head(tip: tip, from: from, width: pen(2.3), size: 10, least: pen.least)
        default:
            // A wedge's or a zigzag's corners stay sharp: a curve through
            // them swung wide into a hairpin (Nighthawks, Mateusz 2026-11-02).
            return points.count >= 2
                ? corners(points).enumerated().map { stroke($1, width: pen(2.2), seed: seed + $0, least: pen.least) } : []
        }
    }

    /// How far the marks drawn in a picture of `size` run past its edges,
    /// in points: the picture's great lines (a triangle's apex up in the
    /// sky, a vanishing point above it) reach at most half a side out, as
    /// the server lets them (`ai/daily.py` REACH).
    static func overflow(of marks: [DailyWork.Mark], in size: CGSize, weight: CGFloat = 1) -> EdgeInsets {
        var bounds = CGRect(origin: .zero, size: size)
        for (index, mark) in marks.enumerated() {
            for path in paths(for: mark, in: size, seed: index * 7 + 1, weight: weight) where !path.isEmpty {
                bounds = bounds.union(path.boundingRect)
            }
        }
        func out(_ beyond: CGFloat, _ side: CGFloat) -> CGFloat {
            beyond > 0.5 ? min(beyond + 2, side * 0.5 + 4).rounded(.up) : 0
        }
        return EdgeInsets(
            top: out(-bounds.minY, size.height),
            leading: out(-bounds.minX, size.width),
            bottom: out(bounds.maxY - size.height, size.height),
            trailing: out(bounds.maxX - size.width, size.width)
        )
    }

    /// Where a mark's number goes: beside a loop's upper right, inside a
    /// rect's corner, over a triangle's top, before an underline, above a
    /// line's end, beside the middle of an arrow's way, beside a spiral's
    /// eye; always inside the picture.
    static func numberSpot(for mark: DailyWork.Mark, in size: CGSize) -> CGPoint {
        let points = mark.points.map { CGPoint(x: $0.x * size.width, y: $0.y * size.height) }
        guard let first = points.first else { return CGPoint(x: size.width / 2, y: size.height / 2) }
        var spot: CGPoint
        switch mark.shape {
        case "loop":
            let corner = points.count > 1 ? points[1] : first
            let rx = max(abs(corner.x - first.x), 8)
            let ry = max(abs(corner.y - first.y), 8)
            spot = CGPoint(x: first.x + rx * 0.72 + 9, y: first.y - ry * 0.72 - 9)
        case "rect":
            spot = CGPoint(x: points.map(\.x).min()! + 12, y: points.map(\.y).min()! + 12)
        case "triangle":
            let top = points.min { $0.y < $1.y }!
            spot = CGPoint(x: top.x + 13, y: top.y - 6)
        case "spiral":
            let eye = points[points.count - 1]
            spot = CGPoint(x: eye.x + 14, y: eye.y - 14)
        case "underline":
            let start = points.min { $0.x < $1.x }!
            spot = CGPoint(x: start.x - 14, y: start.y)
        case "line":
            let end = points[points.count - 1]
            spot = CGPoint(x: end.x - 4, y: end.y - 14)
        case "rhythm" where points.count >= 4:
            let first = beats(points)[0]
            let top = first.min { $0.y < $1.y }!
            spot = CGPoint(x: top.x, y: top.y - 13)
        case "rays" where points.count >= 2:
            let end = points[1]
            spot = CGPoint(x: end.x + 12, y: end.y + 12)
        case "motion":
            spot = CGPoint(x: first.x + 4, y: first.y - 15)
        case "echo":
            let radius = echoRing(in: size)
            spot = CGPoint(x: first.x + radius + 8, y: first.y - radius - 4)
        case "arrow" where points.count >= 2:
            // Beside the middle of its way: its last point is its head
            // (two points, and the "middle" one was the tip: the number
            // lay on the arrowhead, Mateusz 2026-11-12 11:31).
            spot = beside(points, at: 0.45, by: 15)
        default:
            let middle = points[points.count / 2]
            spot = CGPoint(x: middle.x, y: middle.y - 15)
        }
        let margin: CGFloat = 11
        spot.x = min(max(spot.x, margin), max(size.width - margin, margin))
        spot.y = min(max(spot.y, margin), max(size.height - margin, margin))
        return spot
    }

    /// The point `share` of the way along a line through `points`, moved
    /// `by` points off it to the side that lies higher (to the right of a
    /// line that stands upright).
    static func beside(_ points: [CGPoint], at share: CGFloat, by: CGFloat) -> CGPoint {
        guard points.count >= 2 else { return points.first ?? .zero }
        let lengths = zip(points, points.dropFirst()).map { hypot($1.x - $0.x, $1.y - $0.y) }
        var left = lengths.reduce(0, +) * share
        var piece = 0
        while piece < lengths.count - 1, left > lengths[piece] {
            left -= lengths[piece]
            piece += 1
        }
        let (a, b) = (points[piece], points[piece + 1])
        let length = max(lengths[piece], 0.0001)
        let (ux, uy) = ((b.x - a.x) / length, (b.y - a.y) / length)
        // The normal that points up; of an upright line, the one to the right.
        var (nx, ny) = (uy, -ux)
        if ny > 0.2 || (abs(ny) <= 0.2 && nx < 0) { (nx, ny) = (-nx, -ny) }
        return CGPoint(x: a.x + ux * left + nx * by, y: a.y + uy * left + ny * by)
    }

    /// The tips of the marks' arrowheads (an arrow's, a movement's), where
    /// no number may lie.
    static func heads(of marks: [DailyWork.Mark], in size: CGSize) -> [CGPoint] {
        marks.compactMap { mark -> CGPoint? in
            guard mark.shape == "arrow" || mark.shape == "motion", mark.points.count >= 2 else { return nil }
            let tip = mark.points[mark.points.count - 1]
            return CGPoint(x: tip.x * size.width, y: tip.y * size.height)
        }
    }

    /// How far a number's middle keeps from an arrowhead's tip: its disc
    /// and the head's two strokes.
    static let headClear: CGFloat = 22
    /// How far a number's middle keeps from another mark's line: its disc
    /// and half the chalk's width.
    static let lineClear: CGFloat = 12

    /// The lines a mark's strokes run along in a picture of `size` (what
    /// `paths` draws, without its width): where no other mark's number
    /// may lie.
    static func courses(of mark: DailyWork.Mark, in size: CGSize) -> [[CGPoint]] {
        let points = mark.points.map { CGPoint(x: $0.x * size.width, y: $0.y * size.height) }
        guard let first = points.first else { return [] }
        func ring(_ centre: CGPoint, _ rx: CGFloat, _ ry: CGFloat) -> [CGPoint] {
            (0...24).map { step in
                let angle = 2 * CGFloat.pi * CGFloat(step) / 24
                return CGPoint(x: centre.x + rx * cos(angle), y: centre.y + ry * sin(angle))
            }
        }
        switch mark.shape {
        case "echo" where points.count >= 2:
            let radius = echoRing(in: size)
            return points.map { ring($0, radius, radius) } + echoDashes(points, in: size)
        case "loop":
            let corner = points.count > 1 ? points[1] : first
            // (the hand goes round a little wider than the form)
            return [ring(first, max(abs(corner.x - first.x), 8) * 1.04, max(abs(corner.y - first.y), 8) * 1.04)]
        case "triangle" where points.count == 3:
            return [points + [first]]
        case "rect" where points.count == 2:
            let (a, b) = (points[0], points[1])
            return [[a, CGPoint(x: b.x, y: a.y), b, CGPoint(x: a.x, y: b.y), a]]
        case "underline" where points.count >= 2:
            return [smooth(wave(from: first, to: points[points.count - 1]))]
        case "spiral" where points.count == 3:
            return [smooth(spiral(start: points[0], through: points[1], eye: points[2]))]
        case "rhythm" where points.count >= 4:
            return beats(points)
        case "rays" where points.count >= 3:
            return points.dropFirst().map { [$0, first] }
        case "motion" where points.count >= 2:
            let line = smooth(points)
            return [line] + speedLines(line, gap: 6.5)
        default:
            return points.count >= 2 ? corners(points).map { smooth($0) } : []
        }
    }

    /// How far `point` is from the nearest of the `lines`.
    static func distance(from point: CGPoint, to lines: [[CGPoint]]) -> CGFloat {
        var nearest = CGFloat.infinity
        for line in lines {
            if line.count == 1 { nearest = min(nearest, hypot(point.x - line[0].x, point.y - line[0].y)) }
            for (a, b) in zip(line, line.dropFirst()) {
                let (dx, dy) = (b.x - a.x, b.y - a.y)
                let along = max(0, min(1, ((point.x - a.x) * dx + (point.y - a.y) * dy) / max(dx * dx + dy * dy, 0.0001)))
                nearest = min(nearest, hypot(point.x - a.x - dx * along, point.y - a.y - dy * along))
            }
        }
        return nearest
    }

    /// The marks' numbers on the study sheet: each at its own spot
    /// (`numberSpot`), moved a step aside where another number already
    /// sits, an arrowhead lies (`heads`: of all the marks drawn, `among`,
    /// labelled or not) or another mark's line runs (`courses`), so two
    /// never lie on each other, none covers where an arrow points and
    /// none is crossed by a line that is not its own: each mark stands at
    /// its own height over the sheet, and a higher one's line lay over a
    /// lower one's number (Mateusz 2026-11-12 13:46: "cyferka (3) schowała
    /// się za linią trójkąta (1) - musimy uniknąć takich 'nałożeń'").
    static func numberSpots(for marks: [DailyWork.Mark], in size: CGSize, among all: [DailyWork.Mark]? = nil) -> [CGPoint] {
        let margin: CGFloat = 11
        let step: CGFloat = 23
        let tips = heads(of: all ?? marks, in: size)
        let drawn = (all ?? marks).map { (mark: $0, lines: courses(of: $0, in: size)) }
        let steps = [(0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (1, -1), (-1, -1), (1, 1), (-1, 1), (2, 0), (-2, 0), (0, -2), (0, 2)]
        var taken: [CGPoint] = []
        for mark in marks {
            let spot = numberSpot(for: mark, in: size)
            let tried = steps.map { dx, dy in
                CGPoint(
                    x: min(max(spot.x + CGFloat(dx) * step, margin), max(size.width - margin, margin)),
                    y: min(max(spot.y + CGFloat(dy) * step, margin), max(size.height - margin, margin))
                )
            }
            func alone(_ candidate: CGPoint) -> Bool {
                taken.allSatisfy { hypot($0.x - candidate.x, $0.y - candidate.y) > 21 }
            }
            func clear(_ candidate: CGPoint) -> Bool {
                tips.allSatisfy { hypot($0.x - candidate.x, $0.y - candidate.y) >= headClear }
            }
            let others = drawn.filter { $0.mark != mark }.flatMap(\.lines)
            func off(_ candidate: CGPoint) -> Bool {
                distance(from: candidate, to: others) >= lineClear
            }
            let free = tried.first { alone($0) && clear($0) && off($0) }
                ?? tried.first { alone($0) && clear($0) }
                ?? tried.first(where: alone)
            taken.append(free ?? tried[0])
        }
        return taken
    }

    /// A line ruled in graphite from `a` to `b` and `over` past both ends,
    /// barely bent: the sheet's frame and its grid.
    static func ruled(_ a: CGPoint, _ b: CGPoint, over: CGFloat, width: CGFloat, seed: Int) -> Path {
        let length = max(hypot(b.x - a.x, b.y - a.y), 0.0001)
        let (ux, uy) = ((b.x - a.x) / length, (b.y - a.y) / length)
        let bend = CGFloat(Jitter.random(seed) - 0.5) * 0.8
        return stroke(
            [
                CGPoint(x: a.x - ux * over, y: a.y - uy * over),
                CGPoint(x: (a.x + b.x) / 2 - uy * bend, y: (a.y + b.y) / 2 + ux * bend),
                CGPoint(x: b.x + ux * over, y: b.y + uy * over),
            ],
            width: width, seed: seed, start: 0.03, end: 0.03
        )
    }

    /// The grid under a take: lines at the golden section, thirds (3×3),
    /// halves (2×2), thirds across and halves down (3×2) or the other way
    /// round (2×3), each a faint ruled stroke across the picture.
    static func grid(_ grid: String, in size: CGSize) -> [[CGPoint]] {
        let across: [CGFloat], down: [CGFloat]
        switch grid {
        case "golden": (across, down) = ([0.382, 0.618], [0.382, 0.618])
        case "thirds": (across, down) = ([1 / 3, 2 / 3], [1 / 3, 2 / 3])
        case "halves": (across, down) = ([0.5], [0.5])
        case "3x2": (across, down) = ([1 / 3, 2 / 3], [0.5])
        case "2x3": (across, down) = ([0.5], [1 / 3, 2 / 3])
        default: return []
        }
        return across.map { cut in
            [CGPoint(x: cut * size.width, y: size.height * 0.01), CGPoint(x: cut * size.width, y: size.height * 0.99)]
        } + down.map { cut in
            [CGPoint(x: size.width * 0.01, y: cut * size.height), CGPoint(x: size.width * 0.99, y: cut * size.height)]
        }
    }

    /// A golden spiral from `start` into its `eye`, turning the way `through`
    /// lies from the line between them: every quarter turn its radius shrinks
    /// by φ, as the server draws it (`ai/sketch.py`).
    static func spiral(start: CGPoint, through: CGPoint, eye: CGPoint) -> [CGPoint] {
        let dx = start.x - eye.x, dy = start.y - eye.y
        let radius = hypot(dx, dy)
        guard radius > 2 else { return [] }
        let cross = dx * (through.y - eye.y) - dy * (through.x - eye.x)
        let turn: CGFloat = cross < 0 ? -1 : 1
        let angle = atan2(dy, dx)
        let growth = log((1 + sqrt(5)) / 2) / (.pi / 2)
        let end = log(radius / 1.5) / growth
        let steps = max(Int(end / (.pi / 12)), 2)
        return (0...steps).map { step in
            let theta = end * CGFloat(step) / CGFloat(steps)
            let r = radius * exp(-growth * theta)
            return CGPoint(x: eye.x + r * cos(angle + turn * theta), y: eye.y + r * sin(angle + turn * theta))
        }
    }

    /// A pen stroke through the points: a filled outline, thin at both ends
    /// (`start` and `end` are the fractions it takes to reach full width).
    static func stroke(
        _ points: [CGPoint], width: CGFloat, seed: Int, start: CGFloat = 0.25, end: CGFloat = 0.25, least: CGFloat = pointedEnd
    ) -> Path {
        let line = smooth(points)
        guard line.count > 1 else { return Path() }
        var lengths: [CGFloat] = [0]
        for index in 1..<line.count {
            lengths.append(lengths[index - 1] + hypot(line[index].x - line[index - 1].x, line[index].y - line[index - 1].y))
        }
        let total = max(lengths[lengths.count - 1], 1)
        let phase = CGFloat(Jitter.random(seed) * 6)
        var left: [CGPoint] = []
        var right: [CGPoint] = []
        for index in line.indices {
            let t = lengths[index] / total
            let a = start > 0 ? min(1, t / start) : 1
            let b = end > 0 ? min(1, (1 - t) / end) : 1
            let wobble = 1 + 0.12 * sin(CGFloat(index) * 0.35 + phase)
            let half = width * (least + (1 - least) * pow(max(min(a, b), 0), 0.7)) * wobble / 2
            let before = line[max(index - 1, 0)]
            let after = line[min(index + 1, line.count - 1)]
            let dx = after.x - before.x
            let dy = after.y - before.y
            let length = max(hypot(dx, dy), 0.0001)
            let normal = CGPoint(x: -dy / length * half, y: dx / length * half)
            left.append(CGPoint(x: line[index].x + normal.x, y: line[index].y + normal.y))
            right.append(CGPoint(x: line[index].x - normal.x, y: line[index].y - normal.y))
        }
        var path = Path()
        path.addLines(left + right.reversed())
        path.closeSubpath()
        return path
    }

    /// A loop drawn in one go: it starts lower left, goes round a little more
    /// than once and widens as it goes, so the ends do not meet.
    static func loop(center: CGPoint, rx: CGFloat, ry: CGFloat, width: CGFloat, seed: Int, least: CGFloat = pointedEnd) -> Path {
        var jitter = Jitter(seed: seed)
        let start = 190 + jitter.next() * 40
        let points = (0..<24).map { index -> CGPoint in
            let angle = (start + 380 * Double(index) / 23) * .pi / 180
            let k = 1 + 0.04 * sin(Double(index) * 0.8) + 0.07 * Double(index) / 23
            return CGPoint(x: center.x + rx * k * cos(angle), y: center.y + ry * k * sin(angle))
        }
        return stroke(points, width: width, seed: seed, start: 0.12, end: 0.3, least: least)
    }

    /// A rhythm's beats: the points in pairs (a repeated form's foot and
    /// top), each made a stroke through the pair's middle, all parallel to
    /// their common direction and a fifth longer than the form, as the
    /// server draws them (`ai/sketch.py`).
    static func beats(_ points: [CGPoint]) -> [[CGPoint]] {
        let pairs = stride(from: 0, to: points.count - 1, by: 2).map { (points[$0], points[$0 + 1]) }
        var ux: CGFloat = 0
        var uy: CGFloat = 0
        for (a, b) in pairs {
            var dx = b.x - a.x
            var dy = b.y - a.y
            if dy < 0 || (dy == 0 && dx < 0) { (dx, dy) = (-dx, -dy) }
            let length = max(hypot(dx, dy), 0.0001)
            ux += dx / length
            uy += dy / length
        }
        let norm = max(hypot(ux, uy), 0.0001)
        (ux, uy) = (ux / norm, uy / norm)
        return pairs.map { pair in
            let (a, b) = pair
            let middle = CGPoint(x: (a.x + b.x) / 2, y: (a.y + b.y) / 2)
            let half = hypot(b.x - a.x, b.y - a.y) / 2 * 1.2
            return [
                CGPoint(x: middle.x - ux * half, y: middle.y - uy * half),
                CGPoint(x: middle.x + ux * half, y: middle.y + uy * half),
            ]
        }
    }

    /// Two short strokes beside the start of a movement's path, one on each
    /// side, trailing it like the lines behind something moving fast.
    static func speedLines(_ path: [CGPoint], gap: CGFloat) -> [[CGPoint]] {
        let sides: [(side: CGFloat, from: Double, to: Double)] = [(1, 0, 0.42), (-1, 0.08, 0.34)]
        return sides.compactMap { entry -> [CGPoint]? in
            let side = entry.side
            let first = Int(Double(path.count) * entry.from)
            let last = min(max(Int(Double(path.count) * entry.to), first + 2), path.count)
            guard last - first >= 2 else { return nil }
            return (first..<last).map { index in
                let before = path[max(index - 1, 0)]
                let after = path[min(index + 1, path.count - 1)]
                let length = max(hypot(after.x - before.x, after.y - before.y), 0.0001)
                let normal = CGPoint(x: -(after.y - before.y) / length, y: (after.x - before.x) / length)
                return CGPoint(x: path[index].x + side * gap * normal.x, y: path[index].y + side * gap * normal.y)
            }
        }
    }

    /// An arrowhead: two short strokes back from the tip.
    static func head(tip: CGPoint, from: CGPoint, width: CGFloat, size: CGFloat, least: CGFloat = pointedEnd) -> [Path] {
        let angle = atan2(tip.y - from.y, tip.x - from.x)
        return [CGFloat(2.55), -2.45].map { turn -> Path in
            let a = angle + turn
            let points = [
                tip,
                CGPoint(x: tip.x + size * 0.55 * cos(a) + 0.6, y: tip.y + size * 0.55 * sin(a)),
                CGPoint(x: tip.x + size * cos(a), y: tip.y + size * sin(a)),
            ]
            return stroke(points, width: width, seed: 1, start: 0.05, end: 0.6, least: least)
        }
    }

    /// A ruled side of a triangle or rect, a little past both corners.
    static func side(_ a: CGPoint, _ b: CGPoint, width: CGFloat, seed: Int, least: CGFloat = pointedEnd) -> Path {
        let length = max(hypot(b.x - a.x, b.y - a.y), 0.0001)
        let over = CGPoint(x: (b.x - a.x) / length * 3, y: (b.y - a.y) / length * 3)
        let bend = CGFloat(Jitter.random(seed) - 0.5) * 1.2
        let middle = CGPoint(x: (a.x + b.x) / 2 - over.y / 3 * bend, y: (a.y + b.y) / 2 + over.x / 3 * bend)
        return stroke(
            [CGPoint(x: a.x - over.x, y: a.y - over.y), middle, CGPoint(x: b.x + over.x, y: b.y + over.y)],
            width: width, seed: seed, start: 0.1, end: 0.1, least: least
        )
    }

    /// An underline as a small wave from start to end.
    static func wave(from start: CGPoint, to end: CGPoint) -> [CGPoint] {
        let length = hypot(end.x - start.x, end.y - start.y)
        let steps = max(Int(length / 12.5), 3)
        let normal = CGPoint(x: -(end.y - start.y) / max(length, 0.0001), y: (end.x - start.x) / max(length, 0.0001))
        return (0...steps).map { step -> CGPoint in
            let t = CGFloat(step) / CGFloat(steps)
            let lift: CGFloat = step % 2 == 0 ? 0 : 3.5
            return CGPoint(
                x: start.x + (end.x - start.x) * t + normal.x * lift,
                y: start.y + (end.y - start.y) * t + normal.y * lift
            )
        }
    }

    /// The points cut where the line turns sharply (more than `limit`
    /// degrees), each piece to be drawn on its own: a curve keeps its gentle
    /// bends, a wedge or a zigzag its corners. Neighbouring pieces share the
    /// corner point.
    static func corners(_ points: [CGPoint], limit: CGFloat = 35) -> [[CGPoint]] {
        guard points.count > 2 else { return [points] }
        var pieces: [[CGPoint]] = [[points[0]]]
        for index in 1..<points.count {
            pieces[pieces.count - 1].append(points[index])
            guard index < points.count - 1 else { break }
            let (a, b, c) = (points[index - 1], points[index], points[index + 1])
            let turn = abs(atan2(c.y - b.y, c.x - b.x) - atan2(b.y - a.y, b.x - a.x))
            let degrees = min(turn, 2 * .pi - turn) * 180 / .pi
            if degrees > limit { pieces.append([b]) }
        }
        return pieces
    }

    /// A Catmull-Rom curve through the points, ten samples a segment.
    static func smooth(_ points: [CGPoint], samples: Int = 10) -> [CGPoint] {
        guard points.count > 1 else { return points }
        var out: [CGPoint] = []
        for index in 0..<(points.count - 1) {
            let p0 = points[max(index - 1, 0)]
            let p1 = points[index]
            let p2 = points[index + 1]
            let p3 = points[min(index + 2, points.count - 1)]
            for step in 0..<samples {
                let t = CGFloat(step) / CGFloat(samples)
                let t2 = t * t
                let t3 = t2 * t
                func axis(_ v0: CGFloat, _ v1: CGFloat, _ v2: CGFloat, _ v3: CGFloat) -> CGFloat {
                    0.5 * (2 * v1 + (v2 - v0) * t + (2 * v0 - 5 * v1 + 4 * v2 - v3) * t2 + (3 * v1 - v0 - 3 * v2 + v3) * t3)
                }
                out.append(CGPoint(x: axis(p0.x, p1.x, p2.x, p3.x), y: axis(p0.y, p1.y, p2.y, p3.y)))
            }
        }
        out.append(points[points.count - 1])
        return out
    }

    /// SplitMix64: the same marks for the same seed.
    struct Jitter {
        var state: UInt64

        init(seed: Int) { state = UInt64(truncatingIfNeeded: seed) &+ 0x9E37_79B9_7F4A_7C15 }

        static func random(_ seed: Int) -> Double {
            var jitter = Jitter(seed: seed)
            return jitter.next()
        }

        mutating func next() -> Double {
            state = state &+ 0x9E37_79B9_7F4A_7C15
            var z = state
            z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
            z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
            z ^= z >> 31
            return Double(z >> 11) / Double(1 << 53)
        }
    }
}
