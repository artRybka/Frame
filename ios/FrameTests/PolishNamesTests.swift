import XCTest
@testable import Frame

/// "Polskie imiona artystów": first names change, surnames never do.
final class PolishNamesTests: XCTestCase {
    func testFirstNamesChangeAndSurnamesStay() {
        let cases: [(String, String)] = [
            ("Paul Cézanne", "Paweł Cézanne"),
            ("Vincent van Gogh", "Wincenty van Gogh"),
            ("Claude Monet", "Klaudiusz Monet"),
            ("Pierre-Auguste Renoir", "Piotr August Renoir"),
            ("Jean-Baptiste-Siméon Chardin", "Jan Chrzciciel Szymon Chardin"),
            ("Henri de Toulouse-Lautrec", "Henryk de Toulouse-Lautrec"),
            ("Pieter Bruegel the Elder", "Piotr Bruegel the Elder"),
            ("Workshop of Peter Paul Rubens", "Workshop of Piotr Paweł Rubens"),
            ("Joseph Mallord William Turner", "Józef Mallord Wilhelm Turner"),
            ("Élisabeth Louise Vigée Le Brun", "Elżbieta Ludwika Vigée Le Brun"),
            ("Albrecht Dürer", "Olbracht Dürer"),
            ("Hieronymus Bosch", "Hieronim Bosch"),
            ("Michelangelo Buonarroti", "Michał Anioł Buonarroti"),
            ("Camille Claudel", "Kamila Claudel"),
        ]
        for (name, polish) in cases {
            XCTAssertEqual(PolishNames.artist(name), polish, name)
        }
    }

    func testSurnameFirstAndOneWordNames() {
        XCTAssertEqual(PolishNames.artist("Gogh, Vincent van"), "Gogh, Wincenty van")
        XCTAssertEqual(PolishNames.artist("Monet, Claude"), "Monet, Klaudiusz")
        XCTAssertEqual(PolishNames.artist("Paul Cézanne, French"), "Paweł Cézanne, French")
        XCTAssertEqual(PolishNames.artist("Michelangelo"), "Michał Anioł")
        XCTAssertEqual(PolishNames.artist("Titian"), "Tycjan")
    }

    func testNamesWithoutKnownFirstNamesStayAsTheyAre() {
        for name in ["Katsushika Hokusai", "Rembrandt van Rijn", "El Greco", "Thomas", "Caravaggio", "", "Unknown"] {
            XCTAssertEqual(PolishNames.artist(name), name, name)
        }
    }

    @MainActor
    func testTheSwitchIsOffUntilTurnedOn() {
        let style = NameStyle.shared
        let was = style.polishFirstNames
        defer { style.polishFirstNames = was }
        style.polishFirstNames = false
        XCTAssertEqual(Names.artist("Paul Cézanne"), "Paul Cézanne")
        style.polishFirstNames = true
        XCTAssertEqual(Names.artist("Paul Cézanne"), "Paweł Cézanne")
        let week = ArtTheme(key: "week-artist-paul-cezanne", name: "Paul Cézanne", description: "")
        XCTAssertEqual(Names.theme(week), "Paweł Cézanne")
        let other = ArtTheme(key: "impressionism", name: "Paul i przyjaciele", description: "")
        XCTAssertEqual(Names.theme(other), "Paul i przyjaciele")
    }
}
