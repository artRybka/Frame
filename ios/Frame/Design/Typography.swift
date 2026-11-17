import Foundation
import os
import SwiftUI

/// Polish line breaking: what must not stay at the end of a line.
///
/// A one-letter word (a, i, o, u, w, z) goes to the next line with the word
/// after it ("sztuki i / kolekcjoner", Mateusz 2026-11-17), initials stay
/// with the name, a number with its "r." or "cm", a Roman century with
/// "w." or "wieku", and a dash never starts a line. Each such space becomes
/// a no-break space (U+00A0), one character for one, so ranges into the
/// text (`SentenceClip`) stay valid.
///
/// Where it applies:
/// - every string literal the app shows (`Text("…")`, buttons, labels,
///   titles, alerts): SwiftUI looks those up in the main bundle, and
///   `bindAppStrings()` binds what the lookup returns;
/// - `ReadingText` and `NameText`;
/// - a string made at run time (the server's descriptions, notes, names):
///   `Text(bound: value)` or `value.bound`.
/// Never on what is typed, edited, searched for or sent back: only on
/// what is shown. The server does the same on the frame's "Opis" page
/// (server/src/frame_server/imaging/breaks.py); keep the two in step.
enum Typography {
    private static let patterns: [(String, String)] = [
        // a, i, o, u, w, z (and capitals) as words of their own, also in a
        // run ("a w domu"); after a space, a bracket, a quote or a dash.
        (#"(?<![^\s(\[„"'“‘«—–])([aiouwzAIOUWZ]) (?=\S)"#, "$1\u{00A0}"),
        // Initials: "J. M. W. Turner".
        (#"(?<![^\s(\[„"'“‘«])(\p{Lu}\.) (?=\p{Lu})"#, "$1\u{00A0}"),
        // "1868 r.", "XIX w.", "XIX wieku", "50 cm".
        (#"(\d|\b[IVXLC]+) (?=(?:r\.|w\.|wiek\w*|cm\b|mm\b|m\b|px\b|kg\b|zł\b|%))"#, "$1\u{00A0}"),
        // A dash goes with the word before it: "Duret – krytyk".
        (#"(?<=\S) (?=[–—] )"#, "\u{00A0}"),
    ]

    private static let rules: [(NSRegularExpression, String)] = patterns.map { rule in
        // swiftlint:disable:next force_try
        (try! NSRegularExpression(pattern: rule.0), rule.1)
    }

    /// `text` with no-break spaces where Polish typesetting wants them.
    static func bound(_ text: String) -> String {
        guard text.contains(" ") else { return text }
        let result = NSMutableString(string: text)
        for (rule, template) in rules {
            rule.replaceMatches(
                in: result, range: NSRange(location: 0, length: result.length), withTemplate: template
            )
        }
        return result as String
    }

    /// `text` as it should be copied or searched: plain spaces again.
    static func unbound(_ text: String) -> String {
        text.replacingOccurrences(of: "\u{00A0}", with: " ")
    }

    /// Binds every string the app looks up in its bundle, which is every
    /// literal SwiftUI shows (`Text("…")`, `Button("…")`, `.navigationTitle`).
    /// Called once, at launch.
    static func bindAppStrings() {
        guard !(Bundle.main is BoundBundle) else { return }
        object_setClass(Bundle.main, BoundBundle.self)
    }
}

/// The main bundle, answering its look-ups bound (`Typography.bindAppStrings`).
/// The answers are kept: the same few hundred strings are asked for again
/// and again as views are drawn.
private final class BoundBundle: Bundle {
    private static let made = OSAllocatedUnfairLock(initialState: [String: String]())

    override func localizedString(forKey key: String, value: String?, table tableName: String?) -> String {
        let found = super.localizedString(forKey: key, value: value, table: tableName)
        if let kept = Self.made.withLock({ $0[found] }) { return kept }
        let bound = Typography.bound(found)
        Self.made.withLock { $0[found] = bound }
        return bound
    }
}

extension StringProtocol {
    /// Shown with Polish line breaking (`Typography.bound`).
    var bound: String { Typography.bound(String(self)) }
}

extension AttributedString {
    /// Shown with Polish line breaking (`Typography.bound`), its attributes
    /// kept: each bound space is swapped for a no-break one in place.
    var bound: AttributedString {
        let plain = String(characters)
        let fixed = Typography.bound(plain)
        guard fixed != plain else { return self }
        let changed = zip(plain, fixed).enumerated().filter { $0.element.0 != $0.element.1 }
        var result = self
        for (offset, pair) in changed.reversed() {
            let start = result.characters.index(result.characters.startIndex, offsetBy: offset)
            result.characters.replaceSubrange(start...start, with: [pair.1])
        }
        return result
    }
}

extension Text {
    /// A string made at run time, shown with Polish line breaking: no "i"
    /// or "w" left at a line's end (`Typography`).
    init(bound content: some StringProtocol) {
        self.init(verbatim: Typography.bound(String(content)))
    }

    /// Styled text made at run time, with Polish line breaking.
    init(bound content: AttributedString) {
        self.init(content.bound)
    }
}
