import SwiftUI
import UIKit

/// Gallery look: warm paper, ink-black type and controls (buttons, switches,
/// selections, charts), and vermilion (the artist's seal) as the one colour
/// for highlights. There is no blue accent any more (D1, 2026-11-01).
enum Theme {
    static let paper = Color(light: 0xF5F1EA, dark: 0x121110)
    static let card = Color(light: 0xFFFDF9, dark: 0x1D1B19)
    /// Under an outlined button that stands out from the page (the study's
    /// buttons on a work's card, Mateusz 2026-11-04): pure white, pure black.
    static let raised = Color(light: 0xFFFFFF, dark: 0x000000)
    static let mat = Color(light: 0xEEE8DE, dark: 0x2A2724)
    static let matWhite = Color(light: 0xFBF9F4, dark: 0xE9E4DA)
    static let ink = Color(light: 0x1D1B18, dark: 0xF1ECE4)
    static let inkSoft = Color(light: 0x6E675E, dark: 0xA79F94)
    static let hairline = Color(light: 0xDDD5C8, dark: 0x34302B)
    static let vermilion = Color(light: 0xB8432F, dark: 0xE58A6F)
    /// The frame around the panel: white, like the real one.
    static let moulding = Color(light: 0xFFFFFF, dark: 0xE6E2DA)
    static let mouldingEdge = Color(light: 0xD3CBBE, dark: 0x4A453F)
    static let good = Color(light: 0x3E7B56, dark: 0x7CC49A)
    static let warn = Color(light: 0xB7832A, dark: 0xE2B45E)
    static let bad = Color(light: 0xB8432F, dark: 0xE58A6F)
    /// Second lines on the frosted glass of the cards at the bottom: inkSoft
    /// fades to 2.5:1 there over bright pictures.
    static let glassInk = Color(light: 0x3A352F, dark: 0xD3CCC1)
    /// The kind of a card at the bottom, in a small disc: soft colours, a
    /// glyph in paper on them (`NoticeCard`).
    static let markGood = Color(light: 0x6F977B, dark: 0x8DB79A)
    static let markBad = Color(light: 0xBE7A66, dark: 0xD39684)
    static let markWarn = Color(light: 0xBF9A58, dark: 0xD7B679)
    static let markInfo = Color(light: 0x8A8378, dark: 0xA79F94)
    /// The track of a switch that is on: ink in the light; in the dark a warm
    /// stone, because cream ink is as light as the white knob.
    static let switchOn = Color(light: 0x1D1B18, dark: 0x8F8578)

    /// The app icon's row of squares, and the sixth that closes the frame
    /// in Discover's empty search; black turns cream in the dark, like the
    /// dark icon, and the sixth the other way round.
    static let iconSquares = [
        Color(hex: 0xA84B37), Color(hex: 0xEEB453), Color(hex: 0x2559CC), Color(hex: 0x3F8F4E),
        Color(light: 0x000000, dark: 0xEDE9DE), Color(light: 0xFFFFFF, dark: 0x000000),
    ]

    static let corner: CGFloat = 14
    static let gutter: CGFloat = 20
}

extension Theme {
    /// Screen titles in the same serif as the section headers: the large
    /// title on each tab and the inline one on pushed screens and sheets.
    /// Only the font changes; colours and bar backgrounds stay the system's.
    static func serifNavigationTitles() {
        func serif(_ style: UIFont.TextStyle, weight: UIFont.Weight) -> UIFont {
            let size = UIFont.preferredFont(
                forTextStyle: style,
                compatibleWith: UITraitCollection(preferredContentSizeCategory: .large)
            ).pointSize
            let base = UIFont.systemFont(ofSize: size, weight: weight)
            let font = base.fontDescriptor.withDesign(.serif).map { UIFont(descriptor: $0, size: size) } ?? base
            return UIFontMetrics(forTextStyle: style).scaledFont(for: font)
        }
        let bar = UINavigationBar.appearance()
        bar.largeTitleTextAttributes = [.font: serif(.largeTitle, weight: .semibold)]
        bar.titleTextAttributes = [.font: serif(.headline, weight: .semibold)]
    }
}

/// Every switch in the app: the system one, its track `Theme.switchOn`.
/// Set once at the root, so a `.tint(Theme.ink)` around a switch does not
/// reach its track.
struct FrameSwitchStyle: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Toggle(configuration)
            .toggleStyle(.switch)
            .tint(Theme.switchOn)
    }
}

extension View {
    /// A thin white frame around a miniature of the panel.
    func whiteFrame(_ width: CGFloat, corner: CGFloat = 2) -> some View {
        padding(width)
            .background(Theme.moulding)
            .clipShape(RoundedRectangle(cornerRadius: corner))
            .overlay(RoundedRectangle(cornerRadius: corner).strokeBorder(Theme.mouldingEdge, lineWidth: 0.5))
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }

    init(light: UInt32, dark: UInt32) {
        self.init(
            uiColor: UIColor { traits in
                let hex = traits.userInterfaceStyle == .dark ? dark : light
                return UIColor(
                    red: CGFloat((hex >> 16) & 0xFF) / 255,
                    green: CGFloat((hex >> 8) & 0xFF) / 255,
                    blue: CGFloat(hex & 0xFF) / 255,
                    alpha: 1
                )
            }
        )
    }

    /// "#rrggbb" from the server's colour analysis.
    init?(hexString: String) {
        let digits = hexString.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        guard digits.count == 6, let value = UInt32(digits, radix: 16) else { return nil }
        self.init(hex: value)
    }
}

extension Font {
    static func serif(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .serif)
    }

    /// Caveat, a hand-written face for the composition's labels (bundled,
    /// SIL Open Font License: Resources/Fonts).
    static func hand(_ size: CGFloat) -> Font {
        .custom("Caveat-SemiBold", size: size)
    }
}

extension ItemSummary {
    var placeholderColor: Color {
        colors.first.flatMap { Color(hexString: $0.hex) } ?? Theme.mat
    }
}

extension Item {
    var placeholderColor: Color {
        colors.first.flatMap { Color(hexString: $0.hex) } ?? Theme.mat
    }
}

/// Polish names and display colours for the server's colour/mood tags.
enum ColorTag {
    static let families = [
        "red", "orange", "yellow", "green", "teal", "blue", "purple", "pink", "brown", "black",
        "gray", "white",
    ]
    static let moods = ["warm", "cool", "vivid", "muted", "colorful", "monochrome", "dark", "light"]
    /// The Tonacja card's middles, between a group's ends ("tone:neutral").
    static let middles = ["neutral", "moderate", "medium"]
    /// Tags of colours that are only an accent of a picture ("accent:red");
    /// a picture has either a colour's own tag or its accent tag.
    static let accentPrefix = "accent:"
    static let accentFamilies = [
        "red", "orange", "yellow", "green", "teal", "blue", "purple", "pink", "brown",
    ]

    static func accent(_ family: String) -> String { accentPrefix + family }

    /// Colours a picture is painted in ("only:blue"), as the server tags
    /// them: never shown on a work. Picked under "Dominuje", they find
    /// pictures painted in those colours alone (with white, grey, black).
    static let onlyPrefix = "only:"
    static let onlyFamilies = accentFamilies

    static func only(_ family: String) -> String { onlyPrefix + family }

    /// How much of a work a colour asked for in the Kolor sheet covers,
    /// "blue@much" (server `colors.LEVELS`): a small accent, clear, much,
    /// most of its colours. White, grey and black are never an accent.
    enum Level: Int, CaseIterable {
        case accent, clear, much, most

        var key: String {
            switch self {
            case .accent: "accent"
            case .clear: "clear"
            case .much: "much"
            case .most: "most"
            }
        }

        /// "Błękit · wyraźny".
        var name: String {
            switch self {
            case .accent: "akcent"
            case .clear: "obecny"
            case .much: "wyraźny"
            case .most: "główny"
            }
        }

        /// The word agreeing with the colour's name: "Szarości · obecne",
        /// "Czerwień · obecna", "Błękit · obecny" (Mateusz).
        func name(for family: String) -> String {
            guard self != .accent else { return name }
            let stem = String(name.dropLast())
            return switch ColorTag.gender(family) {
            case .feminine: stem + "a"
            case .plural: stem + "e"
            case .masculine: name
            }
        }

        /// How much of the ring around the swatch it fills.
        var fraction: Double { Double(rawValue + 1) / Double(Self.allCases.count) }

        /// The levels a family can take: no accent of white, grey or black.
        static func of(_ family: String) -> [Level] {
            neutrals.contains(family) ? [.clear, .much, .most] : allCases
        }
    }

    static let neutrals = ["black", "gray", "white"]
    static let levelMark = "@"

    enum Gender { case masculine, feminine, plural }

    /// The grammatical gender of a colour's Polish name, for the level word.
    static func gender(_ family: String) -> Gender {
        switch family {
        case "red", "yellow", "green", "black", "white": .feminine
        case "gray": .plural
        default: .masculine
        }
    }
    /// Colours picked at once in the Kolor sheet, at most.
    static let maxLevels = 3

    static func level(_ family: String, _ level: Level) -> String { family + levelMark + level.key }

    /// The level of a colour tag as the Kolor sheet shows it: "blue@much",
    /// and older rules' "accent:blue", "blue" and "only:blue" at the
    /// level nearest to what they ask.
    static func level(of tag: String) -> Level? {
        if let mark = tag.range(of: levelMark) {
            return Level.allCases.first { $0.key == tag[mark.upperBound...] }
        }
        if tag.hasPrefix(accentPrefix) { return .accent }
        if tag.hasPrefix(onlyPrefix) { return .most }
        return families.contains(tag) ? .clear : nil
    }

    /// Moods asked from the Tonacja card ("tone:warm"): every one must fit
    /// (older rules' plain "warm" is one of a group).
    static let tonePrefix = "tone:"

    static func tone(_ mood: String) -> String { tonePrefix + mood }

    /// The Tonacja card's groups, one of each at most; every work is on one
    /// side of each (the server's ``TONE_GROUPS``).
    static let toneGroups = [
        ["warm", "neutral", "cool"], ["vivid", "moderate", "muted"], ["colorful", "monochrome"],
        ["dark", "medium", "light"],
    ]

    /// What a Tonacja group is about, under its dots ("Temperatura").
    static func toneTitle(_ left: String) -> String {
        switch left {
        case "warm": "Temperatura"
        case "vivid": "Nasycenie"
        case "colorful": "Barwność"
        case "dark": "Jasność"
        default: name(left)
        }
    }

    /// The family a tag is of: "blue" for "blue", "accent:blue", "only:blue",
    /// "blue@much"; the mood for "tone:warm".
    static func family(_ tag: String) -> String {
        for prefix in [accentPrefix, onlyPrefix, tonePrefix] where tag.hasPrefix(prefix) {
            return String(tag.dropFirst(prefix.count))
        }
        if let mark = tag.range(of: levelMark) {
            return String(tag[..<mark.lowerBound])
        }
        return tag
    }

    /// A work's tags as the Kolor sheet groups them: colours, accents,
    /// moods, each in the sheet's order (moods in pairs).
    static func rows(_ tags: [String]) -> [[String]] {
        let accents = accentFamilies.map(accent)
        let known = Set(families + accents + moods)
        // Not the Tonacja sides ("tone:warm"): every work has four, the
        // plain moods say what stands out.
        return [
            families.filter(tags.contains),
            accents.filter(tags.contains),
            moods.filter(tags.contains)
                + tags.filter { !known.contains($0) && !$0.hasPrefix(onlyPrefix) && !$0.hasPrefix(tonePrefix) },
        ]
    }

    static func name(_ tag: String) -> String {
        if tag.hasPrefix(accentPrefix) {
            return "Akcent: " + name(family(tag)).lowercased()
        }
        if tag.hasPrefix(onlyPrefix) {
            return "Dominuje: " + name(family(tag)).lowercased()
        }
        if tag.contains(levelMark), let level = level(of: tag) {
            return name(family(tag)) + " · " + level.name(for: family(tag))
        }
        if tag.hasPrefix(tonePrefix) {
            return name(family(tag))
        }
        return switch tag {
        case "red": "Czerwień"
        case "orange": "Pomarańcz"
        case "yellow": "Żółć"
        case "green": "Zieleń"
        case "teal": "Turkus"
        case "blue": "Błękit"
        case "purple": "Fiolet"
        case "pink": "Róż"
        case "brown": "Brąz"
        case "black": "Czerń"
        case "gray": "Szarości"
        case "white": "Biel"
        case "colorful": "Kolorowe"
        case "warm": "Ciepłe"
        case "cool": "Chłodne"
        case "vivid": "Żywe"
        case "muted": "Stonowane"
        case "monochrome": "Mono"
        case "dark": "Ciemne"
        case "light": "Jasne"
        case "neutral": "Neutralne"
        case "moderate": "Umiarkowane"
        case "medium": "Średnie"
        default: tag
        }
    }

    static func color(_ tag: String) -> Color {
        if tag != family(tag) {
            return color(family(tag))
        }
        return switch tag {
        case "red": Color(hex: 0xB8432F)
        case "orange": Color(hex: 0xD9822B)
        case "yellow": Color(hex: 0xE3C04A)
        case "green": Color(hex: 0x4F7D4A)
        case "teal": Color(hex: 0x3B8A86)
        case "blue": Color(hex: 0x23466B)
        case "purple": Color(hex: 0x6B4C8A)
        case "pink": Color(hex: 0xD98BA0)
        case "brown": Color(hex: 0x7A5636)
        case "black": Color(hex: 0x1D1B18)
        case "gray": Color(hex: 0x8E8A84)
        case "white": Color(hex: 0xF4F0E8)
        case "colorful": Color(hex: 0x6E9F55)
        case "warm": Color(hex: 0xFF9A1F)
        case "cool": Color(hex: 0x9CC3E4)
        case "vivid": Color(hex: 0xFF4A2E)
        case "muted": Color(hex: 0xA9A497)
        case "monochrome": Color(hex: 0x6A6762)
        case "dark": Color(hex: 0x2E2B28)
        case "light": Color(hex: 0xEDE6D8)
        case "neutral": Color(hex: 0xCFC9BF)
        case "moderate": Color(hex: 0xCB8E6F)
        case "medium": Color(hex: 0x8A847B)
        default: Theme.mat
        }
    }
}

extension ColorTag {
    /// How a tag's dot is filled: a colour family flat, the moods with a
    /// look of their own so they read at a glance (PLAN 3.3zw, 3.3zzt):
    /// Ciepłe from golden yellow through orange to red, Chłodne from ice to
    /// blue, Żywe colours spread in a mesh and Stonowane the same greyed,
    /// Kolorowe a printer's raster of cyan, magenta and yellow, Mono one of
    /// black (``HalftoneDot``; small dots: quarters).
    static func fill(_ tag: String) -> AnyShapeStyle {
        switch family(tag) {
        case "warm":
            AnyShapeStyle(LinearGradient(
                stops: [
                    .init(color: Color(hex: 0xFFD24A), location: 0),
                    .init(color: Color(hex: 0xFF9A1F), location: 0.45),
                    .init(color: Color(hex: 0xF2462B), location: 1),
                ],
                startPoint: .topLeading, endPoint: .bottomTrailing
            ))
        case "cool":
            AnyShapeStyle(LinearGradient(
                stops: [
                    .init(color: Color(hex: 0xE6F2FB), location: 0),
                    .init(color: Color(hex: 0x9CC3E4), location: 0.45),
                    .init(color: Color(hex: 0x2F5E9A), location: 1),
                ],
                startPoint: .topLeading, endPoint: .bottomTrailing
            ))
        // Żywe pure and full, Stonowane all but grey, Umiarkowane between
        // (szkic 16: before, the three were too alike).
        case "vivid":
            spread([0xFF1503, 0xFF891B, 0xFFC52D, 0xDD2890, 0xFF9B5E, 0x64BD37, 0x7C3FB9, 0x116DD3, 0x1BAAA2])
        case "moderate":
            spread([0xB95A53, 0xCE9057, 0xD1B365, 0xAC638D, 0xD8AB8F, 0x769C62, 0x81679B, 0x4D75A1, 0x488784])
        case "muted":
            spread([0xA18E8D, 0xAB9E93, 0xB0AA9A, 0x9F9199, 0xBCB3AD, 0x91988D, 0x948F99, 0x848D97, 0x7C8A8A])
        case "neutral":
            // The grey of paper, flat: no colour either way, and not a ball
            // (szkic 16, M1a).
            AnyShapeStyle(Color(hex: 0xCFC9BF))
        case "medium":
            AnyShapeStyle(EllipticalGradient(
                stops: [
                    .init(color: Color(hex: 0xA9A49C), location: 0),
                    .init(color: Color(hex: 0x8A847B), location: 0.6),
                    .init(color: Color(hex: 0x6F6A62), location: 1),
                ],
                center: UnitPoint(x: 0.32, y: 0.28), startRadiusFraction: 0, endRadiusFraction: 0.9
            ))
        case "light":
            // Paper in light: white where it falls, warm cream away from it.
            AnyShapeStyle(EllipticalGradient(
                stops: [
                    .init(color: .white, location: 0),
                    .init(color: Color(hex: 0xFBF8F1), location: 0.35),
                    .init(color: Color(hex: 0xE9E1D2), location: 1),
                ],
                center: UnitPoint(x: 0.32, y: 0.28), startRadiusFraction: 0, endRadiusFraction: 0.85
            ))
        case "colorful":
            quarters([0x00AEEF, 0xEC008C, 0xFFE600, 0x00B85C])
        case "monochrome":
            quarters([0x1D1B18, 0x6A6762, 0xB3AEA6, 0xF4F0E8])
        default:
            AnyShapeStyle(color(tag))
        }
    }

    /// Colours spread over the dot in patches that melt into each other,
    /// with no point they run to (Mateusz: not a cone): a 3×3 mesh, row by
    /// row, the rim going round the hues and a soft blend in the middle.
    private static func spread(_ colours: [UInt32]) -> AnyShapeStyle {
        let points: [SIMD2<Float>] = [
            [0, 0], [0.5, 0], [1, 0],
            [0, 0.5], [0.5, 0.5], [1, 0.5],
            [0, 1], [0.5, 1], [1, 1],
        ]
        return AnyShapeStyle(MeshGradient(width: 3, height: 3, points: points, colors: colours.map { Color(hex: $0) }))
    }

    /// Four colours in quarters, from the top clockwise.
    private static func quarters(_ colours: [UInt32]) -> AnyShapeStyle {
        let stops = colours.enumerated().flatMap { index, hex in
            let colour = Color(hex: hex)
            return [
                Gradient.Stop(color: colour, location: Double(index) / 4),
                Gradient.Stop(color: colour, location: Double(index + 1) / 4),
            ]
        }
        return AnyShapeStyle(AngularGradient(stops: stops, center: .center, angle: .degrees(-90)))
    }

    /// The ring around a picked swatch in the Kolor sheet: the colour
    /// itself, a mood in its strongest tone.
    static func ring(_ tag: String) -> AnyShapeStyle {
        switch family(tag) {
        case "white": AnyShapeStyle(Color(hex: 0xBDB4A6))
        case "yellow": AnyShapeStyle(Color(hex: 0xD4AE2E))
        case "warm": AnyShapeStyle(Color(hex: 0xF2662B))
        case "cool": AnyShapeStyle(Color(hex: 0x3F6FA8))
        case "vivid": fill("vivid")
        case "muted": fill("muted")
        case "moderate": fill("moderate")
        case "neutral", "medium": AnyShapeStyle(Color(hex: 0x8A847B))
        case "colorful": AnyShapeStyle(Color(hex: 0xEC008C))
        // Ink: black in light mode, light on the dark sheet, where a black
        // ring around a black dot would not show.
        case "monochrome", "black", "dark": AnyShapeStyle(Theme.ink)
        case "light": AnyShapeStyle(Color(hex: 0xBDB4A6))
        default: AnyShapeStyle(color(tag))
        }
    }

    /// Light swatches carry a dark tick.
    static func light(_ tag: String) -> Bool {
        ["white", "yellow", "pink", "light", "cool", "neutral"].contains(family(tag))
    }
}

/// The round dot of a colour or mood tag, everywhere tags show.
struct ColorTagDot: View {
    let tag: String
    var size: CGFloat = 12
    /// The hairline around it; nil for none.
    var stroke: Color? = Theme.inkSoft.opacity(0.4)
    var lineWidth: CGFloat = 0.75

    var body: some View {
        MoodFill(tag: tag)
            .frame(width: size, height: size)
            .overlay {
                if let stroke { Circle().strokeBorder(stroke, lineWidth: lineWidth) }
            }
    }
}

/// A tag's round fill: Kolorowe and Mono, from 20 pt on, as a printer's
/// raster (``HalftoneDot``), the rest as ``ColorTag.fill``.
struct MoodFill: View {
    let tag: String

    var body: some View {
        let mood = ColorTag.family(tag)
        GeometryReader { proxy in
            if ["colorful", "monochrome"].contains(mood), proxy.size.width >= 20 {
                HalftoneDot(black: mood == "monochrome")
            } else {
                Circle().fill(ColorTag.fill(tag))
            }
        }
    }
}

/// A printer's raster in a circle: cyan, magenta and yellow dots, each
/// ink at its own screen angle, growing and shrinking across it so the
/// inks mix as in print (Kolorowe); ``black`` one ink, black (Mono).
struct HalftoneDot: View {
    var black = false

    /// Ink, screen angle in degrees, and the phase of its growing dots.
    private var inks: [(Color, CGFloat, CGFloat)] {
        if black { return [(Color(hex: 0x1D1B18), 45, 0.8)] }
        return [
            (Color(hex: 0x00AEEF), 15, 0.3),
            (Color(hex: 0xEC008C), 75, 1.9),
            (Color(hex: 0xFFE600), 0, 3.6),
        ]
    }

    var body: some View {
        Canvas { context, size in
            let side = min(size.width, size.height)
            let r = side / 2
            let step = side / 8
            context.clip(to: Path(ellipseIn: CGRect(x: 0, y: 0, width: side, height: side)))
            context.fill(Path(CGRect(x: 0, y: 0, width: side, height: side)), with: .color(Color(hex: 0xFBF8F2)))
            context.blendMode = .multiply
            for (index, ink) in inks.enumerated() {
                let (colour, degrees, phase) = ink
                let angle: CGFloat = degrees * .pi / 180
                let (cosA, sinA) = (cos(angle), sin(angle))
                let (cosP, sinP) = (cos(phase), sin(phase))
                let reach = Int(side / step) + 4
                var dots = Path()
                for i in -reach ... reach {
                    for j in -reach ... reach {
                        let (u, v) = (CGFloat(i), CGFloat(j))
                        let x: CGFloat = r + (u * cosA - v * sinA) * step
                        let y: CGFloat = r + (u * sinA + v * cosA) * step
                        guard x > -step, x < side + step, y > -step, y < side + step else { continue }
                        let along: CGFloat = (x * cosP + y * sinP) / side
                        let wave: CGFloat = 0.5 + 0.5 * sin(along * .pi * 1.6 + CGFloat(index))
                        let radius: CGFloat = step * 0.5 * (0.35 + 0.65 * wave)
                        dots.addEllipse(in: CGRect(x: x - radius, y: y - radius, width: 2 * radius, height: 2 * radius))
                    }
                }
                context.fill(dots, with: .color(colour))
            }
        }
        .accessibilityHidden(true)
    }
}

/// Disk sizes as the server counts them (1 MB = 1 MiB, 1 GB = 1000 MB), so
/// a limit of "1,5 GB" and a library at its limit read the same.
enum ByteSize {
    static func mb(_ mb: Int) -> String {
        guard mb >= 1000 else { return "\(mb) MB" }
        let gb = Double(mb) / 1000
        return gb.formatted(.number.precision(.fractionLength(0 ... 1)).locale(Locale(identifier: "pl_PL"))) + " GB"
    }

    static func bytes(_ bytes: Int64) -> String {
        let mb = Double(bytes) / 1_048_576
        if mb >= 1_000_000 {
            let tb = mb / 1_000_000
            return tb.formatted(.number.precision(.fractionLength(0 ... 1)).locale(Locale(identifier: "pl_PL"))) + " TB"
        }
        if mb < 1 && bytes > 0 { return "< 1 MB" }
        return Self.mb(Int(mb.rounded()))
    }
}

enum Names {
    /// "zmianę", "zmiany" or "zmian" after `count`.
    static func changes(_ count: Int) -> String {
        if count == 1 { return "zmianę" }
        let tens = count % 100 / 10, ones = count % 10
        return tens != 1 && (2 ... 4).contains(ones) ? "zmiany" : "zmian"
    }

    /// "godzina", "godziny" or "godzin" after `count`.
    static func hours(_ count: Int) -> String {
        if count == 1 { return "godzina" }
        let tens = count % 100 / 10, ones = count % 10
        return tens != 1 && (2 ... 4).contains(ones) ? "godziny" : "godzin"
    }

    /// "pobudka", "pobudki" or "pobudek" after `count`.
    static func wakes(_ count: Int) -> String {
        if count == 1 { return "pobudka" }
        let tens = count % 100 / 10, ones = count % 10
        return tens != 1 && (2 ... 4).contains(ones) ? "pobudki" : "pobudek"
    }

    static func source(_ key: String) -> String {
        switch key {
        case "aic": "Art Institute of Chicago"
        case "cma": "Cleveland Museum of Art"
        case "met": "The Met"
        case "rijks": "Rijksmuseum"
        case "wmc": "Wikimedia Commons"
        case "europeana": "Europeana"
        case "openverse": "Openverse"
        case "smk": "Statens Museum for Kunst"
        case "nga": "National Gallery of Art"
        case "mnw": "Muzeum Narodowe w Warszawie"
        case "mnk": "Muzeum Narodowe w Krakowie"
        case "yale": "Yale"
        case "si": "Smithsonian"
        case "paris": "Paris Musées"
        case "vam": "Victoria and Albert Museum"
        case "wellcome": "Wellcome Collection"
        case "courtauld": "Courtauld Gallery"
        case "wikiart": "WikiArt"
        case "upload": "Własne"
        case "icloud": "Album iCloud"
        default: key
        }
    }

    static func kind(_ kind: ItemKind) -> String {
        switch kind {
        case .artwork: "Dzieło"
        case .own: "Własna praca"
        case .photo: "Zdjęcie"
        }
    }

    /// "1 zdjęcie", "3 zdjęcia", "12 zdjęć".
    static func photos(_ count: Int) -> String {
        let mod10 = count % 10
        let mod100 = count % 100
        if count == 1 { return "1 zdjęcie" }
        if (2 ... 4).contains(mod10) && !(12 ... 14).contains(mod100) { return "\(count) zdjęcia" }
        return "\(count) zdjęć"
    }

    /// "1 obraz", "3 obrazy", "12 obrazów": works and photos together.
    static func pictures(_ count: Int) -> String {
        let mod10 = count % 10
        let mod100 = count % 100
        if count == 1 { return "1 obraz" }
        if (2 ... 4).contains(mod10) && !(12 ... 14).contains(mod100) { return "\(count) obrazy" }
        return "\(count) obrazów"
    }

    /// "1 dzieło", "3 dzieła", "12 dzieł".
    static func works(_ count: Int) -> String {
        let mod10 = count % 10
        let mod100 = count % 100
        if count == 1 { return "1 dzieło" }
        if (2 ... 4).contains(mod10) && !(12 ... 14).contains(mod100) { return "\(count) dzieła" }
        return "\(count) dzieł"
    }
}

enum When {
    private static let parser: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()

    static func date(_ iso: String?) -> Date? {
        guard let iso else { return nil }
        return parser.date(from: iso)
    }

    /// "dziś, 07:00", "jutro, 07:00", "w piątek, 07:00".
    static func schedule(_ iso: String?) -> String? {
        guard let date = date(iso) else { return nil }
        let time = date.formatted(.dateTime.hour().minute().locale(Locale(identifier: "pl_PL")))
        let calendar = Calendar.current
        if calendar.isDateInToday(date) { return "dziś, \(time)" }
        if calendar.isDateInTomorrow(date) { return "jutro, \(time)" }
        let day = date.formatted(.dateTime.weekday(.wide).locale(Locale(identifier: "pl_PL")))
        return "\(day), \(time)"
    }

    /// "dziś o 19:00", "jutro o 07:00", "w piątek o 07:00".
    static func at(_ iso: String?) -> String? {
        guard let date = date(iso), let time = clock(iso) else { return nil }
        let calendar = Calendar.current
        if calendar.isDateInToday(date) { return "dziś o \(time)" }
        if calendar.isDateInTomorrow(date) { return "jutro o \(time)" }
        var day = date.formatted(.dateTime.weekday(.wide).locale(Locale(identifier: "pl_PL")))
        if day.hasSuffix("a") { day = String(day.dropLast()) + "ę" }  // środę, sobotę, niedzielę
        return "\(day.hasPrefix("wt") ? "we" : "w") \(day) o \(time)"
    }

    /// "dziś, 07:00", "wczoraj, 19:30", "w środę, 07:00", "28 paź, 07:00":
    /// a moment gone by.
    static func past(_ iso: String?) -> String? {
        guard let date = date(iso), let time = clock(iso) else { return nil }
        let calendar = Calendar.current
        if calendar.isDateInToday(date) { return "dziś, \(time)" }
        if calendar.isDateInYesterday(date) { return "wczoraj, \(time)" }
        let pl = Locale(identifier: "pl_PL")
        if date.timeIntervalSinceNow > -6 * 86400 {
            return "\(date.formatted(.dateTime.weekday(.abbreviated).locale(pl))) \(time)"
        }
        return "\(date.formatted(.dateTime.day().month(.abbreviated).locale(pl))), \(time)"
    }

    /// "19:00".
    static func clock(_ iso: String?) -> String? {
        date(iso)?.formatted(.dateTime.hour().minute().locale(Locale(identifier: "pl_PL")))
    }

    /// "za 6 h 12 min", "za 12 min", "za chwilę", "za 2 dni".
    static func countdown(_ iso: String?, from now: Date = .now) -> String? {
        guard let date = date(iso) else { return nil }
        let minutes = Int((date.timeIntervalSince(now) / 60).rounded(.up))
        if minutes <= 1 { return "za chwilę" }
        let hours = minutes / 60, rest = minutes % 60
        if hours >= 48 { return "za \(hours / 24) dni" }
        if hours == 0 { return "za \(rest) min" }
        return rest == 0 ? "za \(hours) h" : "za \(hours) h \(rest) min"
    }

    /// "od 51 min", "od 2 h 5 min", "od 3 dni": how long something lasts.
    static func since(_ iso: String?, to now: Date = .now) -> String? {
        guard let date = date(iso) else { return nil }
        let minutes = max(1, Int(now.timeIntervalSince(date) / 60))
        let hours = minutes / 60, rest = minutes % 60
        if hours >= 48 { return "od \(hours / 24) dni" }
        if hours == 0 { return "od \(minutes) min" }
        return rest == 0 ? "od \(hours) h" : "od \(hours) h \(rest) min"
    }

    /// "5 min temu", "wczoraj".
    static func ago(_ iso: String?) -> String? {
        guard let date = date(iso) else { return nil }
        if abs(date.timeIntervalSinceNow) < 60 { return "przed chwilą" }
        let style = Date.RelativeFormatStyle(presentation: .named, unitsStyle: .wide)
            .locale(Locale(identifier: "pl_PL"))
        return date.formatted(style)
    }

    /// Photo timestamps, e.g. "14 sierpnia 2025, 18:32".
    static func long(_ iso: String?) -> String? {
        guard let date = date(iso) else { return nil }
        return date.formatted(
            .dateTime.day().month(.wide).year().hour().minute().locale(Locale(identifier: "pl_PL"))
        )
    }
}
