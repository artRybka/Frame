import Foundation

/// The works of an Odkrywaj set put in order as the museums answer. Each
/// answer is one search: one painter's works, or one museum's on a subject
/// (up to 24 in a row), so they are held back and woven in. Never two
/// works of one painter, or from one museum, side by side while another can
/// stand between them; the same painter or museum not again within a few
/// works when there are enough of them, nor two of one kind (paintings,
/// prints, drawings) in a row if it can be; and gently, the earlier works
/// first (each painter's in the order of their years, and of those that may
/// come next the oldest). Works shown stay where they are: what is left of
/// one answer waits for the next answers, with others to stand between.
struct WorkWeave {
    /// In the order shown.
    private(set) var shown: [RemoteItem] = []
    /// Come, not shown yet: in the order they came.
    private(set) var held: [RemoteItem] = []
    /// How many works back a painter or a museum is avoided (when others
    /// are there).
    static let spacing = 3
    /// A round that wove fewer works than this lets what it held go too:
    /// nothing else is coming, and holding them back would only show the
    /// squares.
    static let fewestPerRound = 6
    /// Held over more than this after a round, works of one museum may
    /// stand side by side (painters still apart): one museum has far more
    /// than the others, and its works should not wait for ever.
    static let mostHeld = 36

    /// Shown this round (since the last `endRound`).
    private var thisRound = 0

    /// How strictly the next work is chosen.
    private enum Rule {
        /// A painter and a museum other than the last work's.
        case apart
        /// A painter other than the last work's.
        case painterApart
        /// Anything, the best of what is held.
        case any
    }

    /// Takes the works of one answer in (leaving out copies of works here
    /// already, a better copy in place of the worse one) and shows those
    /// that can stand where they come.
    mutating func add(_ more: [RemoteItem]) {
        for candidate in more {
            if let old = candidate.replaces, let index = shown.firstIndex(where: { $0.id == old }) {
                if !contains(id: candidate.id) { shown[index] = candidate }
            } else if let old = candidate.replaces, let index = held.firstIndex(where: { $0.id == old }) {
                if !contains(id: candidate.id) { held[index] = candidate }
            } else if !shown.contains(where: { $0.isSameWork(as: candidate) })
                && !held.contains(where: { $0.isSameWork(as: candidate) })
            {
                held.append(candidate)
            }
        }
        show(.apart)
    }

    /// A round of answers is over: `more` when another round may follow.
    /// After the last round, or one that showed too little, everything
    /// held is shown; when much is held, one museum's works may come
    /// together.
    mutating func endRound(more: Bool) {
        if !more || thisRound < Self.fewestPerRound {
            show(.painterApart)
            show(.any)
        } else if held.count > Self.mostHeld {
            show(.painterApart)
        }
        thisRound = 0
    }

    private func contains(id: String) -> Bool {
        shown.contains { $0.id == id } || held.contains { $0.id == id }
    }

    private mutating func show(_ rule: Rule) {
        while let next = pick(rule) {
            shown.append(held.remove(at: next))
            thisRound += 1
        }
    }

    /// The held work to show next under `rule`, nil when none may come.
    private func pick(_ rule: Rule) -> Int? {
        let last = shown.last
        let painters = shown.suffix(Self.spacing).map(Self.painter)
        let museums = shown.suffix(Self.spacing).map(Self.museum)
        let kinds = shown.suffix(1).map(Self.kind)
        // How far back it was shown (not at all is best).
        func back(_ key: String, in recent: [String]) -> Int {
            recent.lastIndex(of: key).map { recent.count - $0 } ?? Int.max
        }
        var best: (index: Int, rank: [Int])?
        for (index, work) in held.enumerated() {
            if let last {
                switch rule {
                case .apart:
                    if Self.painter(work) == Self.painter(last) || Self.museum(work) == Self.museum(last) {
                        continue
                    }
                case .painterApart:
                    if Self.painter(work) == Self.painter(last) { continue }
                case .any:
                    break
                }
            }
            // Further back is better, so negated; then the earliest year,
            // then the first come.
            let rank = [
                -back(Self.painter(work), in: painters),
                -back(Self.museum(work), in: museums),
                -back(Self.kind(work), in: kinds),
                work.item.year ?? Int.max,
                index,
            ]
            if best == nil || rank.lexicographicallyPrecedes(best!.rank) { best = (index, rank) }
        }
        return best?.index
    }

    private static func folded(_ text: String) -> String {
        text.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Who painted it, as one name however it is written; a work of no
    /// known painter is its own.
    static func painter(_ work: RemoteItem) -> String {
        let name = folded(work.item.artist)
        return name.isEmpty ? "#" + work.id : name
    }

    /// The museum it is in, else the one its picture is from.
    static func museum(_ work: RemoteItem) -> String {
        let name = folded(work.item.museumShown)
        return name.isEmpty ? "@" + work.item.source : name
    }

    /// Painting, print, drawing… as the museum has it; unknown is its own.
    static func kind(_ work: RemoteItem) -> String {
        let name = folded(work.item.classification)
        return name.isEmpty ? "#" + work.id : name
    }
}
