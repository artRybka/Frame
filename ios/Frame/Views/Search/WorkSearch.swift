import SwiftUI

/// One search of the works, for Szukaj and for the playlist editor alike
/// (Mateusz, 2026-11-07: "to samo szukanie"): what the catalogue has for the
/// choices (at once) and what the museums have (each as it answers, more
/// pages while the results' end is near). The catalogue's works come all, a
/// page at a time as the end nears, its best fits first (Mateusz, 2026-11-09:
/// "z katalogu pokazujmy oczywiście wszystko, a nie tylko 60"); the museums
/// after them. The server's search is one too: a
/// smart playlist of the same choices fetches what this shows, and the works
/// it found count for those choices in the catalogue from then on.
@MainActor
@Observable
final class WorkSearch {
    /// What a search depends on, to start it again when it changes.
    struct Key: Hashable {
        let rules: PlaylistRules
        /// The museums chosen (none: all of them); the catalogue keeps to them too.
        let sources: [String]
        /// Whether the museums are asked at all (no museum has the owner's
        /// own works, nor anything but art).
        var museums = true
        /// The museums of `sources` (a playlist's may name the owner's own
        /// photos too); nil: all of `sources`.
        var museumSources: [String]?

        var isEmpty: Bool { rules.isEmpty && sources.isEmpty }
    }

    private(set) var catalogue: ItemPage?
    /// The museums' works as they came, the catalogue's copies too.
    var results: [RemoteItem] = []
    /// The page to ask each museum for more; museums with no more are left out.
    private(set) var next: [String: Int] = [:]
    /// The catalogue had plenty (`plenty`): the museums' first pages wait
    /// until its end is pulled (Mateusz, 2026-11-07: "Gdy na serwerze mamy
    /// sporo odpowiedzi, to nie zadawajmy pytania do muzeów").
    private(set) var museumsWaiting = false
    /// The catalogue is being asked.
    private(set) var searching = false
    /// The museums are still answering their first pages.
    private(set) var asking = false
    /// What the results are for, so that coming back to the view doesn't
    /// search again; the search goes on while a work is open.
    private(set) var searched: Key?
    /// The search whose answer is all in, the museums' first pages too.
    private(set) var settled: Key?
    /// Works hidden here with "Ukryj dzieło": gone from the results at once,
    /// back if the server refuses. The next search's answer leaves them out
    /// itself, so it clears them.
    var hidden: Set<String> = []
    /// The results' end is less than a screen away: time to ask for more
    /// (`scrolled(nearEnd:)`).
    @ObservationIgnored private var nearEnd = false

    @ObservationIgnored private var loadingMore = false
    /// Rounds of museum pages in a row that brought no work.
    @ObservationIgnored private var emptyRounds = 0
    @ObservationIgnored private var loader: Task<Void, Never>?
    /// The catalogue's question, for its next pages.
    @ObservationIgnored private var catalogueQuery: LibraryQuery?
    /// "Podobne do": the steps of nearness past its own floor asked so far
    /// (`LibraryQuery.likeFurther`). Its list at an end, the squares come
    /// and the next step brings the less near (Mateusz 2026-11-19: "po
    /// obecnym limicie dodać kwadraciki i doczytanie po kolejnym
    /// machnięciu").
    private var likeFurther = 0
    /// The server's most steps (`looks.ALIKE_FURTHER`).
    static let likeSteps = 3
    /// "Podobne do" was pulled for more (`askFurther`), being asked: more
    /// never comes at the end on its own, neither the next page nor the
    /// next step, so that it is plainly more, on demand (Mateusz
    /// 2026-11-19: "Chciałbym żeby było warzenie faktycznego doczytania na
    /// żadanie"; "po kolejnych skokach znowu dociąga szybko, bez
    /// zatrzymania").
    private(set) var pulledFurther = false
    @ObservationIgnored private weak var model: AppModel?

    /// How long a round that brought nothing waits before the next.
    private static let retryPause: Duration = .seconds(10)
    /// Rounds bringing no work after which the museums are asked no more.
    private static let emptyRoundsLimit = 3
    /// The catalogue's works for a search, from which the museums are asked
    /// only once its end is pulled (Mateusz 2026-11-19, of the 60 till then:
    /// "To dajmy nie zawsze, tylko 6", then "Albo wiesz co - 12"). With
    /// fewer they are asked at once.
    static let plenty = 12
    /// The catalogue's works asked at a time (the server keeps the whole
    /// answer, so the next pages come at once).
    static let catalogueStep = 120

    // MARK: What is shown

    /// The catalogue's works found, less those hidden here.
    var shownCatalogue: [ItemSummary] {
        (catalogue?.items ?? []).filter { !hidden.contains($0.id) }
    }

    /// Museum works the catalogue doesn't hold already, in any copy.
    var fromMuseums: [RemoteItem] {
        let known = Set(catalogue?.items.map(\.id) ?? [])
        return results.filter {
            !known.contains($0.id) && !known.contains($0.twin ?? "") && !hidden.contains($0.id)
        }
    }

    /// The museums' works on screen: only once the catalogue has answered,
    /// so that its works don't come in above them (the museums' grid jumped
    /// down) and the copies it holds are left out from the start.
    var shownFromMuseums: [RemoteItem] { searching ? [] : fromMuseums }

    /// How many of the catalogue's works fit, less those hidden here.
    var inCatalogue: Int {
        let hiddenHere = (catalogue?.items ?? []).filter { hidden.contains($0.id) }.count
        return max(0, (catalogue?.total ?? 0) - hiddenHere)
    }

    /// All the works found so far: the catalogue's and the museums'.
    var found: Int { inCatalogue + fromMuseums.count }

    /// The catalogue has works not yet asked for.
    var catalogueMore: Bool {
        guard let catalogue else { return false }
        return catalogue.items.count < catalogue.total || likeFurtherLeft
    }

    /// "Podobne do" has less near works still to ask for.
    private var likeFurtherLeft: Bool {
        guard let like = searched?.rules.like, !like.isEmpty else { return false }
        return likeFurther < Self.likeSteps
    }

    /// The catalogue or a museum may still have more.
    var more: Bool { catalogueMore || museumsWaiting || !next.isEmpty }

    /// The end of what is shown, with more that comes only when the end is
    /// pulled (`askFurther`): in "Podobne do" the rest of this step or the
    /// next, less near; in a search the museums, once the server's own works
    /// are all shown (Mateusz 2026-11-19: "Czy ten sam mechanizm możemy
    /// dodać do szukania gdy kończą się wyniki które mamy na serwerze i
    /// trzeba przeszukać muzea?"), from `plenty` of them. With fewer found,
    /// they come on their own.
    var waitsForPull: Bool {
        guard let catalogue, !searching, !pulledFurther, !catalogue.items.isEmpty else { return false }
        if searched?.rules.like.isEmpty == false { return catalogueMore }
        return museumsWaiting && !catalogueMore
    }

    /// What the pull at the end brings: the museums' works, or more of
    /// "Podobne do".
    var pullsMuseums: Bool { museumsWaiting }

    /// The end pulled: the museums' first pages, or the next works of
    /// "Podobne do", the next page of this step or the next step, less near.
    func askFurther() {
        guard waitsForPull else { return }
        pulledFurther = true
        nearEnd = true
        moreIfNeeded()
    }

    /// Still asking: the catalogue, or the museums' first pages.
    var busy: Bool { searching || asking }

    /// "412 dzieł+", or "Szukam…" while nothing has come yet.
    var summary: String {
        if busy && found == 0 { return "Szukam…" }
        return Names.works(found) + (more ? "+" : "")
    }

    /// The search is over and found nothing.
    var nothingFound: Bool {
        guard let searched, !searched.isEmpty else { return false }
        return settled == searched && !busy && !more && shownCatalogue.isEmpty && fromMuseums.isEmpty
    }

    // MARK: Searching

    /// Searches for `key`, unless that is what the results are for already.
    func start(_ key: Key, model: AppModel) {
        self.model = model
        guard key != searched else { return }
        searched = key
        loader?.cancel()
        // Not tied to a view's task: it goes on while a work is open.
        loader = Task { await search(key) }
    }

    private func search(_ key: Key) async {
        results = []
        next = [:]
        museumsWaiting = false
        emptyRounds = 0
        catalogueQuery = nil
        likeFurther = 0
        pulledFurther = false
        guard !key.isEmpty, let model else {
            catalogue = nil
            searching = false
            asking = false
            settled = key
            return
        }
        searching = true
        asking = true
        var query = LibraryQuery(rules: key.rules, limit: Self.catalogueStep)
        query.sources = key.sources
        do {
            let found = try await model.backend.items(query)
            if !Task.isCancelled {
                catalogue = found
                catalogueQuery = query
                hidden = []
            }
        } catch {
            if !Task.isCancelled, !error.isCancellation { model.show(error) }
        }
        if !Task.isCancelled { searching = false }
        // The catalogue answers at once (it is the server's own); with
        // plenty in it the museums are asked only when its end is pulled.
        if Task.isCancelled || key != searched { return }
        if asksMuseums(key), (catalogue?.total ?? 0) >= Self.plenty {
            museumsWaiting = true
        } else {
            await listen(key, sources: key.museumSources ?? key.sources, page: 1)
        }
        // Nothing in the library nor on the museums' first pages: their
        // further pages won't do better. With colours asked the server looks
        // through random works page after page, and "Szukam…" spun for good
        // on a mix nothing fits (Mono with turquoise, 2026-11-05).
        if !Task.isCancelled, key == searched, (catalogue?.total ?? 0) == 0, results.isEmpty {
            next = [:]
        }
        if !Task.isCancelled {
            asking = false
            settled = key
            // A first page shorter than the screen asks for the next at once.
            moreIfNeeded()
        }
    }

    /// Whether the museums have anything for `key`: favourites and
    /// playlists are the owner's, no museum has them. A look is asked of
    /// them by searches Haiku makes of it, what they bring judged by how it
    /// looks (Mateusz 2026-11-13); the works like one ("Podobne do") are the
    /// catalogue's own numbers alone.
    private func asksMuseums(_ key: Key) -> Bool {
        key.museums && !key.rules.asksMine && key.rules.like.isEmpty
    }

    /// Takes in the museums' answers as each comes.
    private func listen(_ key: Key, sources: [String], page: Int) async {
        guard asksMuseums(key), let model else { return }
        do {
            let answers = try await model.backend.museumAnswers(key.rules, sources: sources, page: page)
            for try await answer in answers {
                guard !Task.isCancelled, key == searched else { return }
                withAnimation(.snappy) { results = results.adding(answer.items) }
                next[answer.source] = answer.next
            }
        } catch {
            // A museum that doesn't answer (the Met's bot wall turns the
            // server away for a while) is left out quietly: the others'
            // works are enough (Mateusz, 2026-10-31).
        }
    }

    /// The results were scrolled: their end is `near` or not.
    func scrolled(nearEnd near: Bool) {
        nearEnd = near
        moreIfNeeded()
    }

    /// Asks the museums for their next pages while the results' end is near,
    /// again and again until it isn't (a page can bring few new works). When
    /// a round brought nothing (a museum that didn't answer), the next waits
    /// a while, so that the squares at the end keep their word without
    /// asking a museum that is down over and over.
    func moreIfNeeded(after pause: Duration = .zero) {
        guard nearEnd, !asking, !loadingMore, more, !waitsForPull, let key = searched, !key.isEmpty else { return }
        loadingMore = true
        Task { @MainActor in
            if pause > .zero { try? await Task.sleep(for: pause) }
            guard key == searched, nearEnd, more else {
                loadingMore = false
                moreIfNeeded()
                return
            }
            if catalogueMore {
                await moreOfCatalogue(key)
                loadingMore = false
                moreIfNeeded()
                return
            }
            let found = results.count
            let pages = next
            await loadMore(key)
            loadingMore = false
            guard key == searched else {
                moreIfNeeded()
                return
            }
            emptyRounds = results.count == found ? emptyRounds + 1 : 0
            // Rounds that bring nothing in a row: the museums have no more
            // that fits, however many pages they still have.
            if emptyRounds >= Self.emptyRoundsLimit { next = [:] }
            let moved = results.count != found || next != pages
            moreIfNeeded(after: moved ? .zero : Self.retryPause)
        }
    }

    /// The catalogue's next works. A page that brings none new (the
    /// catalogue changed meanwhile) ends it where it is.
    private func moreOfCatalogue(_ key: Key) async {
        guard let model, var query = catalogueQuery, let had = catalogue else { return }
        // "Podobne do" at the end of its works: the next step, less near,
        // after those already here (the server's order is the same).
        let further = had.items.count >= had.total && !query.like.isEmpty
        if further { query.likeFurther += 1 }
        query.offset = had.items.count
        do {
            let page = try await model.backend.items(query)
            guard !Task.isCancelled, key == searched, var now = catalogue else { return }
            let known = Set(now.items.map(\.id))
            let new = page.items.filter { !known.contains($0.id) }
            now.items += new
            if further {
                catalogueQuery = query
                likeFurther = query.likeFurther
                now = ItemPage(total: max(page.total, now.items.count), items: now.items)
            } else if new.isEmpty {
                now = ItemPage(total: now.items.count, items: now.items)
            }
            // A pull brings something: a page or step with nothing new goes
            // on to the next.
            if !new.isEmpty { pulledFurther = false }
            catalogue = now
        } catch {
            // Asked again a while later, while the end is still near.
            if !error.isCancellation { try? await Task.sleep(for: Self.retryPause) }
        }
    }

    /// The next page of each museum that has more; the first pages when
    /// they waited for the catalogue's end.
    private func loadMore(_ key: Key) async {
        if museumsWaiting {
            museumsWaiting = false
            await listen(key, sources: key.museumSources ?? key.sources, page: 1)
            return
        }
        // Museums looked through for colours stop at different pages.
        let byPage = Dictionary(grouping: next.keys.sorted()) { next[$0] ?? 1 }
        await withTaskGroup(of: Void.self) { group in
            for (page, keys) in byPage {
                group.addTask { @MainActor in await self.listen(key, sources: keys, page: page) }
            }
        }
    }

    // MARK: Changes from the tiles

    /// A work's heart turned: on its tile at once.
    func mark(_ id: String, favorite: Bool) {
        if let index = results.firstIndex(where: { $0.id == id }) {
            results[index].item.favorite = favorite
        }
        if let index = catalogue?.items.firstIndex(where: { $0.id == id }) {
            catalogue?.items[index].favorite = favorite
        }
    }

    /// "Ukryj dzieło": out of the results at once, and with it the copies
    /// the catalogue's work stands for; back if the server refuses.
    func hide(_ id: String) async {
        withAnimation { _ = hidden.insert(id) }
        guard let model, await model.setExcluded(id, true) != nil else {
            withAnimation { _ = hidden.remove(id) }
            return
        }
        // A museum's copies of the work hidden: the server leaves them out
        // of the next answers, these ones go now.
        let work = results.first { $0.id == id }?.work ?? ""
        let copies = results.filter { $0.twin == id || (!work.isEmpty && $0.work == work) }.map(\.id)
        hidden.formUnion(copies)
    }
}
