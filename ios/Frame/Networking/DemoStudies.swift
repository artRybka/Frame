import Foundation
import SwiftUI
import UIKit

/// The demo's analyses of the composition for a few more of its bundled
/// works, drawn on study sheets made by the server's own renderer
/// in its two layers (Resources/DemoImages/<stem>-wash.jpg and -pen.png,
/// "-dark" for the dark page): what the sheet looks like on a wide picture,
/// a tall print in its margins and a dark one. CI screenshots open one with `-demoStudy <name>`; the demo's
/// own study stays the wave.
enum DemoStudies {
    struct Study: Sendable {
        let id: String
        let title: String
        let take: DailyWork.Take
    }

    /// Server-style path of a demo work's sheet (the app adds "&dark=1"
    /// and "&layer=wash-bleed" or "&layer=pen-bleed").
    static func sheet(_ id: String) -> String { "/demo/sheet/\(id)?v=1" }

    /// How much wider than the field the bundled layers are on each side
    /// (the server's `sheet.BLEED`).
    static let bleed = 0.08

    /// The take with the strokes its sheet's pen was drawn along.
    static func sketched(_ take: DailyWork.Take, id: String) -> DailyWork.Take {
        var take = take
        take.sketch = sketches[id]
        return take
    }

    /// The study asked for at launch (`-demoStudy bedroom`), if any.
    static var asked: Study? {
        UserDefaults.standard.string(forKey: "demoStudy").flatMap { named[$0] }
    }

    private typealias Spot = DailyWork.Spot
    private typealias Mark = DailyWork.Mark
    private typealias Stroke = DailyWork.Stroke

    /// The pen strokes of the demo's sheets, as fractions of each work's
    /// field (the ones the bundled pen layers were drawn along).
    static let sketches: [String: [DailyWork.Stroke]] = [
        "aic:24645": [
            Stroke(points: [Spot(x: 0.01, y: 0.37), Spot(x: 0.1, y: 0.3), Spot(x: 0.2, y: 0.19), Spot(x: 0.28, y: 0.125), Spot(x: 0.38, y: 0.115), Spot(x: 0.45, y: 0.16), Spot(x: 0.5, y: 0.22), Spot(x: 0.56, y: 0.31), Spot(x: 0.575, y: 0.41)]),
            Stroke(points: [Spot(x: 0.42, y: 0.19), Spot(x: 0.37, y: 0.3), Spot(x: 0.36, y: 0.42), Spot(x: 0.4, y: 0.55), Spot(x: 0.465, y: 0.67)]),
            Stroke(points: [Spot(x: 0.03, y: 0.62), Spot(x: 0.15, y: 0.6), Spot(x: 0.27, y: 0.6), Spot(x: 0.34, y: 0.57), Spot(x: 0.4, y: 0.65), Spot(x: 0.5, y: 0.74), Spot(x: 0.62, y: 0.8), Spot(x: 0.75, y: 0.83)]),
            Stroke(points: [Spot(x: 0.99, y: 0.42), Spot(x: 0.92, y: 0.5), Spot(x: 0.85, y: 0.58), Spot(x: 0.78, y: 0.64), Spot(x: 0.7, y: 0.7), Spot(x: 0.6, y: 0.73)]),
            Stroke(points: [Spot(x: 0.585, y: 0.725), Spot(x: 0.615, y: 0.675), Spot(x: 0.632, y: 0.655), Spot(x: 0.652, y: 0.678), Spot(x: 0.69, y: 0.725)], sharp: true),
            Stroke(points: [Spot(x: 0.47, y: 0.7), Spot(x: 0.56, y: 0.725)]),
            Stroke(points: [Spot(x: 0.69, y: 0.722), Spot(x: 0.78, y: 0.69)]),
            Stroke(points: [Spot(x: 0.04, y: 0.5), Spot(x: 0.1, y: 0.6), Spot(x: 0.18, y: 0.7), Spot(x: 0.24, y: 0.71)]),
            Stroke(points: [Spot(x: 0.55, y: 0.725), Spot(x: 0.6, y: 0.757), Spot(x: 0.68, y: 0.76), Spot(x: 0.73, y: 0.735)]),
            Stroke(points: [Spot(x: 0.44, y: 0.84), Spot(x: 0.52, y: 0.9), Spot(x: 0.62, y: 0.93), Spot(x: 0.72, y: 0.935)]),
            Stroke(points: [Spot(x: 0.02, y: 0.88), Spot(x: 0.08, y: 0.83), Spot(x: 0.16, y: 0.8), Spot(x: 0.24, y: 0.83), Spot(x: 0.3, y: 0.9)]),
            Stroke(points: [Spot(x: 0.058, y: 0.09), Spot(x: 0.097, y: 0.09), Spot(x: 0.097, y: 0.3), Spot(x: 0.058, y: 0.3)], sharp: true, closed: true),
            Stroke(points: [Spot(x: 0.72, y: 0.95), Spot(x: 0.82, y: 0.86), Spot(x: 0.92, y: 0.78), Spot(x: 0.99, y: 0.72)]),
        ],
        "aic:28560": [
            Stroke(points: [Spot(x: 0.595, y: 0.335), Spot(x: 0.65, y: 0.31), Spot(x: 0.75, y: 0.295), Spot(x: 0.85, y: 0.3), Spot(x: 0.915, y: 0.315), Spot(x: 0.935, y: 0.77), Spot(x: 0.615, y: 0.845)], sharp: true, closed: true),
            Stroke(points: [Spot(x: 0.48, y: 0.5), Spot(x: 0.48, y: 0.27), Spot(x: 0.53, y: 0.255), Spot(x: 0.6, y: 0.255), Spot(x: 0.685, y: 0.265), Spot(x: 0.69, y: 0.31)], sharp: true),
            Stroke(points: [Spot(x: 0.49, y: 0.5), Spot(x: 0.535, y: 0.64), Spot(x: 0.6, y: 0.83)]),
            Stroke(points: [Spot(x: 0.52, y: 0.4), Spot(x: 0.585, y: 0.385), Spot(x: 0.6, y: 0.47), Spot(x: 0.595, y: 0.56), Spot(x: 0.54, y: 0.555), Spot(x: 0.51, y: 0.48)], closed: true),
            Stroke(points: [Spot(x: 0.5, y: 0.31), Spot(x: 0.56, y: 0.285), Spot(x: 0.66, y: 0.3), Spot(x: 0.6, y: 0.35), Spot(x: 0.52, y: 0.37)], closed: true),
            Stroke(points: [Spot(x: 0.0, y: 0.44), Spot(x: 0.07, y: 0.4), Spot(x: 0.085, y: 0.56)], sharp: true),
            Stroke(points: [Spot(x: 0.03, y: 0.61), Spot(x: 0.1, y: 0.555), Spot(x: 0.16, y: 0.6), Spot(x: 0.14, y: 0.675), Spot(x: 0.05, y: 0.675)], closed: true),
            Stroke(points: [Spot(x: 0.03, y: 0.66), Spot(x: 0.02, y: 0.81)]),
            Stroke(points: [Spot(x: 0.14, y: 0.68), Spot(x: 0.145, y: 0.85)]),
            Stroke(points: [Spot(x: 0.36, y: 0.33), Spot(x: 0.41, y: 0.305), Spot(x: 0.415, y: 0.41)], sharp: true),
            Stroke(points: [Spot(x: 0.37, y: 0.44), Spot(x: 0.42, y: 0.405), Spot(x: 0.475, y: 0.43), Spot(x: 0.46, y: 0.475), Spot(x: 0.385, y: 0.475)], closed: true),
            Stroke(points: [Spot(x: 0.43, y: 0.47), Spot(x: 0.435, y: 0.575)]),
            Stroke(points: [Spot(x: 0.15, y: 0.36), Spot(x: 0.3, y: 0.335), Spot(x: 0.36, y: 0.385), Spot(x: 0.21, y: 0.42)], sharp: true, closed: true),
            Stroke(points: [Spot(x: 0.21, y: 0.42), Spot(x: 0.21, y: 0.61)]),
            Stroke(points: [Spot(x: 0.325, y: 0.39), Spot(x: 0.33, y: 0.585)]),
            Stroke(points: [Spot(x: 0.235, y: 0.0), Spot(x: 0.385, y: 0.0), Spot(x: 0.385, y: 0.275), Spot(x: 0.245, y: 0.29)], sharp: true, closed: true),
            Stroke(points: [Spot(x: 0.13, y: 0.545), Spot(x: 0.2, y: 0.49), Spot(x: 0.36, y: 0.48), Spot(x: 0.475, y: 0.475)], sharp: true),
            Stroke(points: [Spot(x: 0.6, y: 0.99), Spot(x: 0.5, y: 0.72), Spot(x: 0.44, y: 0.5)]),
        ],
        "cma:103244": [
            Stroke(points: [Spot(x: 0.004, y: 0.701), Spot(x: 0.226, y: 0.642), Spot(x: 0.503, y: 0.588), Spot(x: 0.78, y: 0.55), Spot(x: 0.996, y: 0.534)]),
            Stroke(points: [Spot(x: 0.004, y: 0.819), Spot(x: 0.226, y: 0.76), Spot(x: 0.503, y: 0.701), Spot(x: 0.78, y: 0.658), Spot(x: 0.996, y: 0.631)]),
            Stroke(points: [Spot(x: 0.281, y: 0.819), Spot(x: 0.292, y: 0.958)]),
            Stroke(points: [Spot(x: 0.492, y: 0.733), Spot(x: 0.503, y: 0.969)]),
            Stroke(points: [Spot(x: 0.769, y: 0.679), Spot(x: 0.791, y: 0.958)]),
            Stroke(points: [Spot(x: 0.94, y: 0.658), Spot(x: 0.957, y: 0.947)]),
            Stroke(points: [Spot(x: 0.503, y: 0.819), Spot(x: 0.636, y: 0.744), Spot(x: 0.769, y: 0.819)], sharp: true),
            Stroke(points: [Spot(x: 0.06, y: 0.862), Spot(x: 0.171, y: 0.808), Spot(x: 0.281, y: 0.872)], sharp: true),
            Stroke(points: [Spot(x: 0.004, y: 0.261), Spot(x: 0.115, y: 0.245), Spot(x: 0.281, y: 0.266), Spot(x: 0.447, y: 0.282), Spot(x: 0.636, y: 0.314), Spot(x: 0.835, y: 0.33), Spot(x: 0.996, y: 0.347)]),
            Stroke(points: [Spot(x: 0.004, y: 0.341), Spot(x: 0.281, y: 0.363), Spot(x: 0.447, y: 0.379), Spot(x: 0.636, y: 0.389), Spot(x: 0.835, y: 0.422), Spot(x: 0.996, y: 0.438)]),
            Stroke(points: [Spot(x: 0.06, y: 0.516), Spot(x: 0.281, y: 0.529), Spot(x: 0.492, y: 0.543)]),
            Stroke(points: [Spot(x: 0.182, y: 0.663), Spot(x: 0.22, y: 0.647), Spot(x: 0.254, y: 0.668), Spot(x: 0.281, y: 0.733), Spot(x: 0.226, y: 0.744), Spot(x: 0.198, y: 0.711)], closed: true),
            Stroke(points: [Spot(x: 0.364, y: 0.62), Spot(x: 0.403, y: 0.609), Spot(x: 0.431, y: 0.636), Spot(x: 0.425, y: 0.695), Spot(x: 0.386, y: 0.695)], closed: true),
            Stroke(points: [Spot(x: 0.553, y: 0.572), Spot(x: 0.614, y: 0.561), Spot(x: 0.652, y: 0.577), Spot(x: 0.636, y: 0.652), Spot(x: 0.564, y: 0.652)], closed: true),
            Stroke(points: [Spot(x: 0.697, y: 0.561), Spot(x: 0.746, y: 0.545), Spot(x: 0.774, y: 0.567), Spot(x: 0.741, y: 0.626), Spot(x: 0.702, y: 0.62)], closed: true),
            Stroke(points: [Spot(x: 0.885, y: 0.025), Spot(x: 0.951, y: 0.025), Spot(x: 0.951, y: 0.205), Spot(x: 0.885, y: 0.205)], sharp: true, closed: true),
            Stroke(points: [Spot(x: 0.047, y: 0.803), Spot(x: 0.102, y: 0.803), Spot(x: 0.102, y: 0.945), Spot(x: 0.047, y: 0.945)], sharp: true, closed: true),
        ],
        "aic:61128": [
            Stroke(points: [Spot(x: 0.0, y: 0.47), Spot(x: 0.2, y: 0.62), Spot(x: 0.42, y: 0.8), Spot(x: 0.62, y: 0.985)]),
            Stroke(points: [Spot(x: 0.14, y: 0.555), Spot(x: 0.24, y: 0.5), Spot(x: 0.33, y: 0.535), Spot(x: 0.31, y: 0.65), Spot(x: 0.245, y: 0.67)], sharp: true, closed: true),
            Stroke(points: [Spot(x: 0.215, y: 0.19), Spot(x: 0.26, y: 0.175), Spot(x: 0.3, y: 0.21), Spot(x: 0.33, y: 0.33), Spot(x: 0.33, y: 0.47), Spot(x: 0.25, y: 0.52), Spot(x: 0.14, y: 0.555), Spot(x: 0.105, y: 0.42), Spot(x: 0.13, y: 0.3), Spot(x: 0.2, y: 0.27)], closed: true),
            Stroke(points: [Spot(x: 0.41, y: 0.345), Spot(x: 0.45, y: 0.285), Spot(x: 0.51, y: 0.3), Spot(x: 0.52, y: 0.36), Spot(x: 0.6, y: 0.43), Spot(x: 0.565, y: 0.52), Spot(x: 0.49, y: 0.63), Spot(x: 0.36, y: 0.6), Spot(x: 0.31, y: 0.52), Spot(x: 0.33, y: 0.44)], closed: true),
            Stroke(points: [Spot(x: 0.575, y: 0.24), Spot(x: 0.655, y: 0.24), Spot(x: 0.665, y: 0.3), Spot(x: 0.565, y: 0.305)], sharp: true, closed: true),
            Stroke(points: [Spot(x: 0.6, y: 0.31), Spot(x: 0.66, y: 0.35), Spot(x: 0.74, y: 0.4), Spot(x: 0.765, y: 0.52), Spot(x: 0.68, y: 0.6), Spot(x: 0.6, y: 0.57)]),
            Stroke(points: [Spot(x: 0.505, y: 0.205), Spot(x: 0.565, y: 0.205), Spot(x: 0.572, y: 0.265), Spot(x: 0.5, y: 0.27)], sharp: true, closed: true),
            Stroke(points: [Spot(x: 0.4, y: 0.06), Spot(x: 0.435, y: 0.05), Spot(x: 0.44, y: 0.1), Spot(x: 0.475, y: 0.17), Spot(x: 0.47, y: 0.27), Spot(x: 0.425, y: 0.27), Spot(x: 0.41, y: 0.16)], closed: true),
            Stroke(points: [Spot(x: 0.595, y: 0.09), Spot(x: 0.63, y: 0.06), Spot(x: 0.665, y: 0.09), Spot(x: 0.7, y: 0.17), Spot(x: 0.71, y: 0.32), Spot(x: 0.64, y: 0.31), Spot(x: 0.6, y: 0.2)], closed: true),
            Stroke(points: [Spot(x: 0.735, y: 0.09), Spot(x: 0.76, y: 0.075), Spot(x: 0.785, y: 0.1), Spot(x: 0.82, y: 0.16), Spot(x: 0.83, y: 0.33), Spot(x: 0.845, y: 0.42), Spot(x: 0.735, y: 0.43), Spot(x: 0.73, y: 0.25)], closed: true),
            Stroke(points: [Spot(x: 0.885, y: 0.3), Spot(x: 0.94, y: 0.275), Spot(x: 0.995, y: 0.31), Spot(x: 0.995, y: 0.5), Spot(x: 0.955, y: 0.555), Spot(x: 0.9, y: 0.52), Spot(x: 0.875, y: 0.4)], closed: true),
            Stroke(points: [Spot(x: 0.71, y: 0.75), Spot(x: 0.74, y: 0.62), Spot(x: 0.8, y: 0.55), Spot(x: 0.9, y: 0.55), Spot(x: 0.995, y: 0.57)]),
            Stroke(points: [Spot(x: 0.47, y: 0.85), Spot(x: 0.5, y: 0.62), Spot(x: 0.56, y: 0.565), Spot(x: 0.64, y: 0.6), Spot(x: 0.665, y: 0.72)]),
            Stroke(points: [Spot(x: 0.135, y: 0.0), Spot(x: 0.135, y: 0.27)]),
        ],
    ]

    static let named: [String: Study] = [
        "bedroom": Study(
            id: "aic:28560",
            title: "Sypialnia",
            take: .init(
                title: "Analiza kompozycji",
                grid: "none",
                text: "Kompozycja zamknięta: pokój mieści się w kadrze cały, a jego linie schodzą się nad łóżkiem, wysoko i nieco z lewej, więc podłoga zdaje się stawać dęba. Łóżko zajmuje prawą połowę i jest najcięższą formą obrazu; równoważą je dwa krzesła i stolik po lewej. Żółć wraca trzykrotnie, od krzesła przy drzwiach po ramę łóżka, i prowadzi oko w głąb. Pośród błękitów i zieleni czerwona kołdra jest jedyną ciepłą plamą.",
                marks: [
                    Mark(shape: "rays", points: [Spot(x: 0.42, y: 0.33), Spot(x: 0.605, y: 0.84), Spot(x: 0.3, y: 0.99)], title: "Zbieg podłogi i łóżka", text: "linie pokoju schodzą się nad wezgłowiem"),
                    Mark(shape: "loop", points: [Spot(x: 0.555, y: 0.47), Spot(x: 0.61, y: 0.565)], title: "Czerwień kołdry", text: "jedyna ciepła plama pośród błękitów"),
                    Mark(shape: "echo", points: [Spot(x: 0.085, y: 0.6), Spot(x: 0.42, y: 0.445), Spot(x: 0.75, y: 0.46)], title: "Żółć wraca trzy razy", text: "krzesło, krzesło i rama łóżka"),
                    Mark(shape: "rect", points: [Spot(x: 0.235, y: 0), Spot(x: 0.385, y: 0.285)], title: "Okno", text: "zielony prostokąt zamyka głąb pokoju"),
                ]
            )
        ),
        "shower": Study(
            id: "cma:103244",
            title: "Nagła ulewa nad mostem Ōhashi",
            take: .init(
                title: "Analiza kompozycji",
                grid: "thirds",
                text: "Kompozycja otwarta: most wchodzi w kadr z lewej i wychodzi z prawej, a jego filary tnie dolna krawędź. Dwa skosy krzyżują się jak nożyce: most wznosi się ku prawej, daleki brzeg opada. Oba leżą blisko linii trójpodziału pola. Przechodnie kulą się w równym rytmie, a samotny flisak na rzece jest ich przeciwwagą. Cynober kartusza u góry odpowiada podpisowi u dołu i spina arkusz po przekątnej.",
                marks: [
                    Mark(shape: "line", points: [Spot(x: 0.05, y: 0.705), Spot(x: 0.5, y: 0.6), Spot(x: 0.94, y: 0.535)], title: "Skos mostu", text: "wznosi się ku prawej"),
                    Mark(shape: "line", points: [Spot(x: 0.05, y: 0.315), Spot(x: 0.94, y: 0.4)], title: "Przeciwny skos brzegu", text: "opada ku prawej, na przekór mostowi"),
                    Mark(shape: "rhythm", points: [Spot(x: 0.25, y: 0.725), Spot(x: 0.24, y: 0.645), Spot(x: 0.415, y: 0.685), Spot(x: 0.405, y: 0.61), Spot(x: 0.585, y: 0.645), Spot(x: 0.585, y: 0.565), Spot(x: 0.705, y: 0.615), Spot(x: 0.71, y: 0.55)], title: "Rytm przechodniów", text: "cztery skulone sylwetki"),
                    Mark(shape: "loop", points: [Spot(x: 0.295, y: 0.525), Spot(x: 0.5, y: 0.565)], title: "Samotny flisak", text: "przeciwwaga dla tłumu na moście"),
                    Mark(shape: "echo", points: [Spot(x: 0.875, y: 0.145), Spot(x: 0.112, y: 0.85)], title: "Cynober wraca", text: "kartusz u góry i podpis u dołu"),
                ],
                field: .init(x: 0.046, y: 0.037, w: 0.903, h: 0.932)
            )
        ),
        "moulin": Study(
            id: "aic:61128",
            title: "W Moulin Rouge",
            take: .init(
                title: "Analiza kompozycji",
                grid: "none",
                text: "Kompozycja otwarta i ukośna: balustrada wchodzi z lewego dolnego rogu i odcina widza od sali, a zielona twarz po prawej jest ucięta krawędzią, jakby ktoś właśnie przeszedł obok. Środek zajmuje krąg pięciu osób przy stoliku, zwarty i ciemny. W głębi trzy stojące postaci dają spokojne piony. Ruda wraca trzy razy, od brody po grzywkę, i wiąże stolik z twarzą na pierwszym planie.",
                marks: [
                    Mark(shape: "line", points: [Spot(x: 0, y: 0.47), Spot(x: 0.62, y: 0.985)], title: "Skos balustrady", text: "odcina widza od sali"),
                    Mark(shape: "loop", points: [Spot(x: 0.42, y: 0.4), Spot(x: 0.72, y: 0.63)], title: "Krąg przy stoliku", text: "pięć głów wokół białego obrusa"),
                    Mark(shape: "rhythm", points: [Spot(x: 0.435, y: 0.27), Spot(x: 0.42, y: 0.06), Spot(x: 0.64, y: 0.31), Spot(x: 0.625, y: 0.07), Spot(x: 0.775, y: 0.42), Spot(x: 0.76, y: 0.08)], title: "Piony w głębi", text: "trzy stojące postaci"),
                    Mark(shape: "loop", points: [Spot(x: 0.935, y: 0.42), Spot(x: 0.995, y: 0.565)], title: "Zielona twarz", text: "ucięta kadrem, najbliżej widza"),
                    Mark(shape: "echo", points: [Spot(x: 0.285, y: 0.3), Spot(x: 0.455, y: 0.365), Spot(x: 0.9, y: 0.29)], title: "Ruda wraca", text: "broda, kok i grzywka"),
                ]
            )
        ),
    ]

    // MARK: The sheet an image model draws (a stand-in)

    /// `-demoDrawn YES`: the demo's page has its sheet as a server with
    /// Google's key sends it (`DailyWork.Drawn`).
    static var drawnAsked: Bool { UserDefaults.standard.bool(forKey: "demoDrawn") }

    /// Pencils as the server measures them off the model's answers.
    static let pencils = ["#394f98", "#be4031", "#287b3f", "#da7e28", "#8a529b", "#2792a2", "#c2337f"]

    private static let drawnLock = NSLock()
    private static var drawnTakes: [String: DailyWork.Take] = [:]

    /// The take's sheet as the image model's: no model draws here, so the
    /// study is the bundled sheet's stains with its pen over them, and
    /// each mark's line is drawn with the app's own stick into a layer, as
    /// the server sends the model's. The last mark comes without a layer
    /// (the model left it out): the app draws it itself.
    static func drawn(_ take: DailyWork.Take, id: String) -> DailyWork.Drawn? {
        guard let aspect = fieldAspect(id) else { return nil }
        drawnLock.withLock { drawnTakes[id] = take }
        let marks = take.marksInField
        let titled = marks.indices.filter { !marks[$0].title.isEmpty }.prefix(pencils.count)
        let path = "/demo/drawn/\(id)?v=1"
        return DailyWork.Drawn(
            sheet: path + "&part=page",
            bleed: bleed,
            aspect: aspect,
            marks: titled.enumerated().map { place, index in
                let left = place == titled.count - 1 && titled.count > 1
                return DailyWork.Drawn.Pencilled(
                    mark: index,
                    layer: left ? "" : path + "&part=m\(place + 1)",
                    colour: pencils[place],
                    numbers: left ? [] : onLine(marks[index], aspect: aspect)
                )
            }
        )
    }

    /// The field's shape, from the bundled layer (wider than the field by
    /// the margin on each side).
    private static func fieldAspect(_ id: String) -> Double? {
        guard let url = Bundle.main.url(forResource: DemoFraming.stem(id) + "-wash", withExtension: "jpg"),
              let image = UIImage(contentsOfFile: url.path), image.size.height > 0
        else { return nil }
        return Double(image.size.width) / (1 + 2 * bleed) / Double(image.size.height)
    }

    /// Places on a mark's own line for its number, as the server finds
    /// them on the model's: one, each ring of an echo, the first and the
    /// last beat of a rhythm.
    static func onLine(_ mark: DailyWork.Mark, aspect: Double) -> [DailyWork.Drawn.Number] {
        typealias Number = DailyWork.Drawn.Number
        let points = mark.points
        guard let first = points.first, let last = points.last else { return [] }
        func between(_ a: Spot, _ b: Spot, _ share: Double) -> Number {
            Number(x: a.x + (b.x - a.x) * share, y: a.y + (b.y - a.y) * share)
        }
        switch mark.shape {
        case "loop":
            let rx = max(abs(last.x - first.x), 0.01), ry = max(abs(last.y - first.y), 0.01)
            return [Number(x: first.x + rx * 0.707, y: first.y - ry * 0.707)]
        case "echo":
            // On top of each ring, whose radius is a share of the longer side.
            return points.map { Number(x: $0.x, y: $0.y - 0.03 * max(aspect, 1)) }
        case "rhythm":
            guard points.count >= 4 else { return [between(first, last, 0.5)] }
            return [between(points[0], points[1], 0.5), between(points[points.count - 2], last, 0.5)]
        case "rect":
            return [Number(x: (first.x + last.x) / 2, y: min(first.y, last.y))]
        default:
            return [between(first, points.count > 1 ? points[1] : last, 0.4)]
        }
    }

    /// "/demo/drawn/<id>?v=1&part=page|m<n>": the stand-in's study, or the
    /// line of its n-th titled mark, made once and kept in the temporary
    /// folder.
    static func drawnPart(_ path: String) -> URL? {
        guard let parts = URLComponents(string: path),
              let part = parts.queryItems?.first(where: { $0.name == "part" })?.value
        else { return nil }
        let id = String(parts.path.dropFirst("/demo/drawn/".count))
        let stem = DemoFraming.stem(id)
        let out = FileManager.default.temporaryDirectory
            .appendingPathComponent("demo-drawn-2-\(stem)-\(part).\(part == "page" ? "jpg" : "png")")
        if FileManager.default.fileExists(atPath: out.path) { return out }
        guard let washURL = Bundle.main.url(forResource: stem + "-wash", withExtension: "jpg"),
              let wash = UIImage(contentsOfFile: washURL.path)
        else { return nil }
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        if part == "page" {
            format.opaque = true
            let pen = Bundle.main.url(forResource: stem + "-pen", withExtension: "png").flatMap { UIImage(contentsOfFile: $0.path) }
            let page = UIGraphicsImageRenderer(size: wash.size, format: format).image { _ in
                wash.draw(at: .zero)
                pen?.draw(in: CGRect(origin: .zero, size: wash.size))
            }
            guard let data = page.jpegData(compressionQuality: 0.9) else { return nil }
            try? data.write(to: out)
            return out
        }
        guard part.hasPrefix("m"), let number = Int(part.dropFirst()), number >= 1,
              let take = drawnLock.withLock({ drawnTakes[id] })
        else { return nil }
        let marks = take.marksInField
        let titled = marks.indices.filter { !marks[$0].title.isEmpty }
        guard number <= titled.count else { return nil }
        let index = titled[number - 1]
        // The field alone, drawn as on a phone and made three times as large.
        let field = CGSize(width: wash.size.width / (1 + 2 * bleed), height: wash.size.height)
        let drawnAt = CGSize(width: 360, height: 360 * field.height / field.width)
        format.opaque = false
        let layer = UIGraphicsImageRenderer(size: field, format: format).image { context in
            let cg = context.cgContext
            cg.scaleBy(x: field.width / drawnAt.width, y: field.height / drawnAt.height)
            cg.setFillColor(UIColor.black.cgColor)
            for path in Pencil.paths(for: marks[index], in: drawnAt, seed: index * 7 + 1, weight: Chalk.weight * 1.6, chalk: true) {
                cg.addPath(path.cgPath)
                cg.fillPath()
            }
        }
        guard let data = layer.pngData() else { return nil }
        try? data.write(to: out)
        return out
    }
}
