import UIKit

/// A long description shortened to whole sentences: as many as fit in a
/// few lines, ending on its full stop, instead of a word cut in half with
/// "…" (the "Dzieło" card on "Teraz").
enum SentenceClip {
    /// The text to show and the lines it may take: 0 when it ends on a
    /// sentence and needs no limit, else the limit (cut with "…" as before).
    struct Clip: Equatable {
        var text: NSAttributedString
        var lines: Int
    }

    /// The sentences of `text` that fit in `lines` lines of `width`. The
    /// first sentence alone may take up to `grace` lines more, so a long
    /// opening sentence is still read whole; when even that is too long
    /// (or the text has no full stop) it is cut at `lines` with "…".
    static func clip(_ text: NSAttributedString, width: CGFloat, lines: Int, grace: Int = 3) -> Clip {
        guard width > 0, lineCount(text, width: width) > lines else { return Clip(text: text, lines: 0) }
        let ends = sentenceEnds(text.string)
        func prefix(_ end: Int) -> NSAttributedString {
            text.attributedSubstring(from: NSRange(location: 0, length: end))
        }
        // The longest run of sentences that fits: lines only grow with the text.
        var low = 0, high = ends.count - 1, best: Int?
        while low <= high {
            let mid = (low + high) / 2
            if lineCount(prefix(ends[mid]), width: width) <= lines {
                best = ends[mid]
                low = mid + 1
            } else {
                high = mid - 1
            }
        }
        if let best { return Clip(text: prefix(best), lines: 0) }
        if let first = ends.first, lineCount(prefix(first), width: width) <= lines + grace {
            return Clip(text: prefix(first), lines: 0)
        }
        return Clip(text: text, lines: lines)
    }

    /// Where each sentence ends (UTF-16 offsets, trailing spaces left out),
    /// for sentences that end on ".", "!", "?" or "…", maybe followed by a
    /// closing quote or bracket.
    static func sentenceEnds(_ string: String) -> [Int] {
        let ns = string as NSString
        var ends: [Int] = []
        ns.enumerateSubstrings(
            in: NSRange(location: 0, length: ns.length), options: [.bySentences, .substringNotRequired]
        ) { _, range, _, _ in
            var end = range.location + range.length
            while end > range.location, isSpace(ns.character(at: end - 1)) { end -= 1 }
            var probe = end
            while probe > range.location, closers.contains(ns.character(at: probe - 1)) { probe -= 1 }
            if probe > range.location, terminals.contains(ns.character(at: probe - 1)) { ends.append(end) }
        }
        return ends
    }

    /// Lines `text` takes at `width`, laid out as the description's
    /// `UITextView` (TextKit 1, no padding) lays it out.
    static func lineCount(_ text: NSAttributedString, width: CGFloat) -> Int {
        let storage = NSTextStorage(attributedString: text)
        let manager = NSLayoutManager()
        let container = NSTextContainer(size: CGSize(width: width, height: .greatestFiniteMagnitude))
        container.lineFragmentPadding = 0
        manager.addTextContainer(container)
        storage.addLayoutManager(manager)
        manager.ensureLayout(for: container)
        var count = 0
        manager.enumerateLineFragments(forGlyphRange: manager.glyphRange(for: container)) { _, _, _, _, _ in
            count += 1
        }
        return count
    }

    private static let terminals = Set(".!?…".utf16)
    private static let closers = Set("\"'”’»)]".utf16)

    private static func isSpace(_ unit: unichar) -> Bool {
        guard let scalar = Unicode.Scalar(unit) else { return false }
        return CharacterSet.whitespacesAndNewlines.contains(scalar)
    }
}
