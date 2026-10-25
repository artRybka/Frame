import SwiftUI
import UIKit

/// Gallery look: warm paper, ink-black type, Prussian blue (Hokusai's Berlin
/// blue) as the accent and vermilion (the artist's seal) for highlights.
enum Theme {
    static let paper = Color(light: 0xF5F1EA, dark: 0x121110)
    static let card = Color(light: 0xFFFDF9, dark: 0x1D1B19)
    static let mat = Color(light: 0xEEE8DE, dark: 0x2A2724)
    static let matWhite = Color(light: 0xFBF9F4, dark: 0xE9E4DA)
    static let ink = Color(light: 0x1D1B18, dark: 0xF1ECE4)
    static let inkSoft = Color(light: 0x6E675E, dark: 0xA79F94)
    static let hairline = Color(light: 0xDDD5C8, dark: 0x34302B)
    static let accent = Color(light: 0x23466B, dark: 0x9DBCE0)
    static let vermilion = Color(light: 0xB8432F, dark: 0xE58A6F)
    /// The frame around the panel: white, like the real one.
    static let moulding = Color(light: 0xFFFFFF, dark: 0xE6E2DA)
    static let mouldingEdge = Color(light: 0xD3CBBE, dark: 0x4A453F)
    static let good = Color(light: 0x3E7B56, dark: 0x7CC49A)
    static let warn = Color(light: 0xB7832A, dark: 0xE2B45E)
    static let bad = Color(light: 0xB8432F, dark: 0xE58A6F)

    static let corner: CGFloat = 14
    static let gutter: CGFloat = 20
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
    static let moods = ["warm", "cool", "vivid", "muted", "monochrome", "dark", "light"]

    static func name(_ tag: String) -> String {
        switch tag {
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
        case "warm": "Ciepłe"
        case "cool": "Chłodne"
        case "vivid": "Żywe"
        case "muted": "Stonowane"
        case "monochrome": "Monochromia"
        case "dark": "Ciemne"
        case "light": "Jasne"
        default: tag
        }
    }

    static func color(_ tag: String) -> Color {
        switch tag {
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
        case "warm": Color(hex: 0xC97B3F)
        case "cool": Color(hex: 0x4D7FA6)
        case "vivid": Color(hex: 0xC2412D)
        case "muted": Color(hex: 0xA59A8A)
        case "monochrome": Color(hex: 0x6A6762)
        case "dark": Color(hex: 0x2E2B28)
        case "light": Color(hex: 0xEDE6D8)
        default: Theme.mat
        }
    }
}

enum Names {
    /// "zmianę", "zmiany" or "zmian" after `count`.
    static func changes(_ count: Int) -> String {
        if count == 1 { return "zmianę" }
        let tens = count % 100 / 10, ones = count % 10
        return tens != 1 && (2 ... 4).contains(ones) ? "zmiany" : "zmian"
    }

    static func source(_ key: String) -> String {
        switch key {
        case "aic": "Art Institute of Chicago"
        case "cma": "Cleveland Museum of Art"
        case "met": "The Met"
        case "rijks": "Rijksmuseum"
        case "wmc": "Wikimedia Commons"
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

    /// Styles that can be picked by hand; "auto" chooses one of them per picture.
    static let manualPresets = ["photo", "painting", "graphic", "bw"]

    static func preset(_ key: String) -> String {
        switch key {
        case "auto": "Auto"
        case "photo": "Zdjęcie"
        case "painting": "Obraz"
        case "graphic": "Grafika"
        case "bw": "Czarno-białe"
        default: key
        }
    }

    /// What a style does to the picture on its way to the six inks; it
    /// never changes the framing (server: imaging.pipeline.PRESETS,
    /// library.style for "auto").
    static func presetExplanation(_ key: String, photo: Bool = false) -> String {
        switch key {
        case "auto" where photo: "Dobierany do każdego zdjęcia osobno: kolorowe jako Zdjęcie, czarno-białe i w sepii tylko czarną i białą farbą, bez kolorowego szumu w szarościach."
        case "auto": "Dobierany do każdego obrazu osobno: zdjęcia jako Zdjęcie, drzeworyty, litografie i plakaty jako Grafika, a rysunki, ryciny i fotografie bez koloru tylko czarną i białą farbą. Pozostałe jako Obraz."
        case "photo": "Do zdjęć: rozjaśnia cienie, które e-papier łatwo zaczernia, lekko podbija kontrast i kolory, mocniej wyostrza."
        case "graphic": "Do plakatów, ilustracji i drzeworytów: płaskie, nasycone barwy, wyraźny kontrast i ostre krawędzie, drobniejszy raster bez szumu."
        case "bw": "Do rysunków, grafik i fotografii czarno-białej: tylko czarna i biała farba, delikatny raster dla płynnych przejść."
        default: "Do obrazów olejnych i akwareli: zachowuje relacje tonów, delikatnie podbija kolory i wyostrza."
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
