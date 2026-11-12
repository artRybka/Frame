import Foundation

/// The demo's analyses of the composition for a few more of its bundled
/// works, drawn on study sheets made by the server's own renderer
/// (Resources/DemoImages/<stem>-sheet.jpg and -sheet-dark.jpg): what the
/// sheet looks like on a wide picture, a tall print in its margins and a
/// dark one. CI screenshots open one with `-demoStudy <name>`; the demo's
/// own study stays the wave.
enum DemoStudies {
    struct Study: Sendable {
        let id: String
        let title: String
        let take: DailyWork.Take
    }

    /// Server-style path of a demo work's sheet (the app adds "&dark=1").
    static func sheet(_ id: String) -> String { "/demo/sheet/\(id)?v=1" }

    /// The study asked for at launch (`-demoStudy bedroom`), if any.
    static var asked: Study? {
        UserDefaults.standard.string(forKey: "demoStudy").flatMap { named[$0] }
    }

    private typealias Spot = DailyWork.Spot
    private typealias Mark = DailyWork.Mark

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
}
