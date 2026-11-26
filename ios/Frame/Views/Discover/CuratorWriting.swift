import SwiftUI

/// "O dziele" while the curator's note is being written: words the card
/// already knows of the work (what the model saw, its colours, the facts)
/// typed as on a typewriter, a part of some taken back, and once the note
/// comes all of it erased and the note typed in its place (Mateusz
/// 2026-11-26: „częściowo kasować jak pisane na maszynie… przeplatane ze
/// słów kluczowych, kolorów i informacji”; „docelowy tekst niech najpierw
/// kasuje to co już jest i dopiero się wpisuje”; the caret blinks a while
/// first, the first words come slower).
struct CuratorWriting: View {
    /// The words to type, in turn; read again before each one, as more
    /// arrive (the keywords come a few seconds after the card opens).
    let words: [String]
    /// The note, once written: what is typed is erased and the note typed.
    let note: String?
    /// The note is all typed: the card shows it as it shows any text.
    let typed: () -> Void

    @Environment(\.accessibilityReduceMotion) private var still
    @State private var shown = ""
    @State private var pool: [String] = []
    @State private var target: String?
    @State private var lastKey = Date.distantPast
    @State private var width: CGFloat = 320
    /// Characters of the note already typed: those are in full ink.
    @State private var final = 0

    static let size: CGFloat = 17
    private static let lineSpacing: CGFloat = 5
    /// The caret alone at first, before the first word.
    private static let firstWait = 1.8
    private static let letter = 1.0 / 14
    private static let erase = 1.0 / 30
    /// The note is typed in at most this long, however long it is.
    private static let noteTyping = 2.6

    var body: some View {
        TimelineView(.periodic(from: .now, by: 0.1)) { context in
            Text(bound: line(at: context.date))
                .font(.system(size: Self.size, design: .serif))
                .lineSpacing(Self.lineSpacing)
                .frame(maxWidth: .infinity, alignment: .topLeading)
        }
        // Three lines held, so the page does not jump as words come and go.
        .frame(minHeight: Self.size * 1.25 * 3 + Self.lineSpacing * 2, alignment: .topLeading)
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { width = $0 }
        .onAppear {
            pool = words
            target = note
        }
        .onChange(of: words) { _, now in pool = now }
        .onChange(of: note) { _, now in target = now }
        .task { await run() }
        .accessibilityElement()
        .accessibilityLabel(Text(bound: "Kurator pisze notkę o tym dziele"))
    }

    /// What is typed, the newest letters a touch brighter, and the caret:
    /// steady while keys are struck, blinking while it waits.
    private func line(at now: Date) -> AttributedString {
        var text = AttributedString(shown)
        text.foregroundColor = Theme.inkSoft
        if final > 0 {
            let end = text.index(text.startIndex, offsetByCharacters: min(final, shown.count))
            text[text.startIndex ..< end].foregroundColor = Theme.ink.opacity(0.9)
        } else if shown.count >= 2, now.timeIntervalSince(lastKey) < 0.6 {
            let start = text.index(text.endIndex, offsetByCharacters: -2)
            text[start ..< text.endIndex].foregroundColor = Theme.ink.opacity(0.9)
        }
        let striking = now.timeIntervalSince(lastKey) < 0.5
        let blink = Int(now.timeIntervalSinceReferenceDate * 2.2) % 2 == 0
        var caret = AttributedString("\u{2009}|")
        caret.foregroundColor = striking || blink ? Theme.ink.opacity(0.8) : .clear
        return text + caret
    }

    // MARK: Typing

    private func run() async {
        if still {
            // No motion: the words as they are, the note at once.
            shown = pool.joined(separator: " · ")
            while target == nil, !Task.isCancelled { try? await Task.sleep(for: .seconds(0.3)) }
            if !Task.isCancelled { typed() }
            return
        }
        await pause(Self.firstWait)
        var turn = 0
        var random = SystemRandomNumberGenerator()
        while !Task.isCancelled, target == nil {
            guard !pool.isEmpty else {
                await pause(0.3)
                continue
            }
            let word = pool[turn % pool.count]
            var piece = (shown.isEmpty ? "" : " · ") + word
            if shown.count + piece.count > room {  // full: wiped back fast
                await remove(shown.count, each: Self.erase * 0.6)
                piece = word
            }
            // The first words slower, as a hand finding the keys.
            let slow = [2.4, 1.8, 1.3].indices.contains(turn) ? [2.4, 1.8, 1.3][turn] : 1
            await type(piece, each: Self.letter * slow, uneven: true)
            turn += 1
            await pause(Double.random(in: 0.5 ... 1.0, using: &random))
            // A part of a word taken back: typed again, or the word let go.
            if turn > 2, word.count > 3, Double.random(in: 0 ... 1, using: &random) < 0.45 {
                let back = Int.random(in: 2 ... word.count - 1, using: &random)
                await remove(back, each: Self.erase)
                await pause(0.15)
                if Bool.random(using: &random) {
                    await type(String(word.suffix(back)), each: Self.letter, uneven: true)
                } else {
                    await remove(word.count - back + (piece.hasPrefix(" · ") ? 3 : 0), each: Self.erase)
                }
            }
        }
        guard !Task.isCancelled, let note = target else { return }
        // The note: what is there erased first, then the note typed in.
        await remove(shown.count, each: Self.erase * 0.7, stopping: false)
        let each = min(1.0 / 110, Self.noteTyping / Double(max(note.count, 1)))
        var index = note.startIndex
        var last = Date()
        while index < note.endIndex, !Task.isCancelled {
            // Several letters a frame when the note is long.
            let due = max(1, Int(Date().timeIntervalSince(last) / each))
            let next = note.index(index, offsetBy: due, limitedBy: note.endIndex) ?? note.endIndex
            shown += note[index ..< next]
            final = shown.count
            index = next
            last = Date()
            lastKey = last
            try? await Task.sleep(for: .seconds(max(each, 1.0 / 60)))
        }
        if !Task.isCancelled { typed() }
    }

    /// How many characters three lines hold, about, at this width.
    private var room: Int { max(30, Int(width / (Self.size * 0.47)) * 3 - 4) }

    /// Waits, cut short when the note comes.
    private func pause(_ seconds: Double) async {
        let until = Date().addingTimeInterval(seconds)
        while Date() < until, target == nil, !Task.isCancelled {
            try? await Task.sleep(for: .seconds(min(0.1, until.timeIntervalSinceNow)))
        }
    }

    private func type(_ piece: String, each: Double, uneven: Bool) async {
        for character in piece {
            guard target == nil, !Task.isCancelled else { return }
            shown.append(character)
            lastKey = Date()
            try? await Task.sleep(for: .seconds(each * (uneven ? Double.random(in: 0.6 ... 1.5) : 1)))
        }
    }

    private func remove(_ count: Int, each: Double, stopping: Bool = true) async {
        for _ in 0 ..< min(count, shown.count) {
            guard !stopping || target == nil, !Task.isCancelled else { return }
            shown.removeLast()
            lastKey = Date()
            try? await Task.sleep(for: .seconds(each))
        }
    }
}
