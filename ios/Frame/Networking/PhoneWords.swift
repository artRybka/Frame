import Foundation
import NaturalLanguage
import SwiftUI
import Translation

/// Polish words typed in Szukaj, translated on the phone (Apple's
/// Translation) and sent to the server before the search asks for them
/// (`POST /api/search/words`): the museums abroad are asked "guitar" for
/// "gitara" at once, without waiting for Haiku (Mateusz 2026-11-20:
/// "wdrażamy, bo warto. Przyspieszy.").
///
/// The server keeps what the phone sent only when it knew nothing of the
/// words and they came back changed; a name, English or a word half typed
/// is left to Haiku as before. Without the languages on the phone nothing is
/// translated here and the search goes as it did.
actor PhoneWords {
    static let shared = PhoneWords()

    static let polish = Locale.Language(identifier: "pl")
    /// English for most museums, French for Paris Musées: each as any of
    /// its kinds on the phone. The phone has "Angielski (USA)" and asking
    /// for English alone found it not there: nothing was ever translated
    /// (Mateusz 2026-11-20, "hulajnoga" by Haiku).
    static let targets: [[Locale.Language]] = [
        ["en-US", "en-GB", "en"].map { Locale.Language(identifier: $0) },
        ["fr-FR", "fr"].map { Locale.Language(identifier: $0) },
    ]

    /// The kind of `kinds` the phone translates Polish into without the
    /// network, or nil.
    static func installed(_ kinds: [Locale.Language]) async -> Locale.Language? {
        let availability = LanguageAvailability()
        for kind in kinds where await availability.status(from: polish, to: kind) == .installed {
            return kind
        }
        return nil
    }

    /// How long a search waits for the phone's words at most; what comes
    /// later still goes to the server for the next search.
    static let patience: Duration = .seconds(1.5)

    /// Folded words already sent (or sent nothing for) since the app began.
    private var done: Set<String> = []

    struct Word: Encodable, Sendable {
        let text: String
        let en: String
        let fr: String
    }

    /// The translations of `phrases` not sent before, of those that may be Polish.
    func translated(_ phrases: [String]) async -> [Word] {
        let wanted = phrases.filter { phrase in
            !done.contains(Self.fold(phrase)) && Self.mayBePolish(phrase)
        }
        guard !wanted.isEmpty else { return [] }
        var english: [String: String] = [:]
        var french: [String: String] = [:]
        if let target = await Self.installed(Self.targets[0]) {
            english = await Self.translate(wanted, to: target)
        }
        if !english.isEmpty, let target = await Self.installed(Self.targets[1]) {
            french = await Self.translate(wanted, to: target)
        }
        guard !english.isEmpty else { return [] }
        var words: [Word] = []
        for phrase in wanted {
            done.insert(Self.fold(phrase))
            guard let en = english[phrase] else { continue }
            words.append(Word(text: phrase, en: en, fr: french[phrase] ?? ""))
        }
        return words
    }

    /// Each of `phrases` in `target`, by its text; nothing when it failed.
    private static func translate(_ phrases: [String], to target: Locale.Language) async -> [String: String] {
        let session = TranslationSession(installedSource: polish, target: target)
        let requests = phrases.map { TranslationSession.Request(sourceText: $0, clientIdentifier: $0) }
        guard let responses = try? await session.translations(from: requests) else { return [:] }
        var found: [String: String] = [:]
        for response in responses {
            let text = response.targetText.trimmingCharacters(in: .whitespacesAndNewlines)
            if let phrase = response.clientIdentifier, !text.isEmpty { found[phrase] = text }
        }
        return found
    }

    /// Words that may be Polish: with a Polish letter, or not English
    /// beyond doubt ("Rembrandt", "landscape" stay with Haiku either way:
    /// the server keeps only what came back changed).
    static func mayBePolish(_ phrase: String) -> Bool {
        guard phrase.contains(where: \.isLetter), phrase.count <= 80 else { return false }
        if phrase.rangeOfCharacter(from: CharacterSet(charactersIn: "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")) != nil { return true }
        let recognizer = NLLanguageRecognizer()
        recognizer.languageConstraints = [.polish, .english, .french, .german, .italian, .spanish, .dutch]
        recognizer.processString(phrase)
        let english = recognizer.languageHypotheses(withMaximum: 3)[.english] ?? 0
        return english < 0.8
    }

    static func fold(_ text: String) -> String {
        text.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
            .split(whereSeparator: \.isWhitespace).joined(separator: " ")
    }
}

/// Asks once, in Szukaj, for Polish and English (and French) on the phone,
/// so that the words can be translated here (`PhoneWords`): the system's
/// own sheet, which says what is downloaded.
struct PhoneWordsLanguages: ViewModifier {
    @AppStorage("phoneWords.asked") private var asked = ""
    @State private var configuration: TranslationSession.Configuration?

    func body(content: Content) -> some View {
        content
            .task {
                configuration = await next()
            }
            .translationTask(configuration) { session in
                try? await session.prepareTranslation()
                if let target = configuration?.target?.minimalIdentifier {
                    asked = (asked.split(separator: ",").map(String.init) + [target]).joined(separator: ",")
                }
                configuration = await next()
            }
    }

    /// The first language not on the phone (in none of its kinds) and not
    /// asked for yet.
    private func next() async -> TranslationSession.Configuration? {
        let availability = LanguageAvailability()
        let done = Set(asked.split(separator: ",").map(String.init))
        for kinds in PhoneWords.targets {
            guard let target = kinds.first, !done.contains(target.minimalIdentifier) else { continue }
            if await PhoneWords.installed(kinds) != nil { continue }
            if await availability.status(from: PhoneWords.polish, to: target) == .supported {
                return TranslationSession.Configuration(source: PhoneWords.polish, target: target)
            }
        }
        return nil
    }
}

extension View {
    func asksForPhoneWords() -> some View { modifier(PhoneWordsLanguages()) }
}
