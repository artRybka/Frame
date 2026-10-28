import UIKit
import XCTest
@testable import Frame

final class FrameAPITests: XCTestCase {
    func testDecodesPlayerViewFromServer() throws {
        let json = """
        {
          "mode": "art",
          "playlist": {"id": 3, "name": "Japońskie drzeworyty", "description": "", "kind": "smart",
                       "rules": {"query": "woodblock", "artists": [], "styles": [], "subjects": [],
                                 "colors": [], "kinds": [], "sources": [], "year_from": null,
                                 "year_to": null, "favorites_only": false, "min_suitability": null},
                       "item_count": 21, "cover_item_ids": ["aic:24645"]},
          "current": {"title": "Under the Wave off Kanagawa", "description": "Katsushika Hokusai",
                      "source": "aic", "created": "2026-10-24T05:00:00+00:00",
                      "preview_url": "/api/previews/ABC.png", "item": null},
          "upcoming": [{"id": "aic:4371", "kind": "artwork", "source": "aic", "title": "Hamamatsu",
                        "artist": "Utagawa Hiroshige", "date_text": "1832", "year": 1832,
                        "colors": [{"hex": "#c1b59d", "weight": 0.4}], "width": 900, "height": 600,
                        "favorite": false, "suitability": 0.88}],
          "queued": ["aic:4371"],
          "history": [],
          "hold": {"until": null, "forever": true},
          "last_change_at": "2026-10-24T05:00:00+00:00",
          "next_change_at": "2026-10-25T05:00:00+00:00",
          "busy": false,
          "last_error": null,
          "progress": {"stage": "downloading", "phase": "loading", "active": true,
                       "title": "Under the Wave off Kanagawa", "fraction": 0.31, "seconds_left": 47,
                       "started_at": "2026-10-24T05:00:00+00:00", "finished_at": null, "message": null}
        }
        """
        let view = try LiveBackend.decoder().decode(PlayerView.self, from: Data(json.utf8))
        XCTAssertEqual(view.progress?.stage, "downloading")
        XCTAssertEqual(view.progress?.phaseIndex, 1)
        XCTAssertEqual(view.progress?.secondsLeft, 47)
        XCTAssertEqual(view.playlist?.itemCount, 21)
        XCTAssertEqual(view.playlist?.rules.query, "woodblock")
        XCTAssertEqual(view.current?.previewUrl, "/api/previews/ABC.png")
        XCTAssertEqual(view.upcoming.first?.aspectRatio ?? 0, 1.5, accuracy: 0.001)
        XCTAssertEqual(view.queued, ["aic:4371"])
        XCTAssertEqual(view.hold?.forever, true)
        XCTAssertNotNil(When.schedule(view.nextChangeAt))
    }

    func testDecodesUndeliveredPicture() throws {
        let json = """
        {"state": "failed", "failure": "timeout", "failed_at": "2026-10-26T06:00:00+00:00",
         "message": "panel did not download the image in time", "asleep_until": null,
         "shown_at": "2026-10-25T18:00:02.120+00:00",
         "on_frame": {"title": "Most w Argenteuil", "description": "", "source": "aic",
                      "created": "2026-10-25T18:00:00+00:00", "preview_url": "/api/previews/OLD.png",
                      "item": null}}
        """
        var delivery = try LiveBackend.decoder().decode(Delivery.self, from: Data(json.utf8))
        XCTAssertTrue(delivery.isFailed)
        XCTAssertFalse(delivery.isShown)
        XCTAssertEqual(delivery.headline, "Nie dotarł na ramkę")
        XCTAssertTrue(delivery.explanation.contains("ramka nie pobrała obrazu"))
        XCTAssertEqual(delivery.onFrame?.previewUrl, "/api/previews/OLD.png")
        delivery = Delivery(state: "waiting", asleepUntil: "07:00")
        XCTAssertEqual(delivery.explanation, "Ramka śpi do 07:00, obraz trafi na nią po przebudzeniu.")
        XCTAssertTrue(Delivery(state: "unknown").isShown)

        // Economy: when the frame's alarm brings it, and a wake it missed.
        let wake = ISO8601DateFormatter().string(from: Date.now.addingTimeInterval(3 * 3600 + 600))
        delivery = Delivery(state: "waiting", asleepUntil: "19:00", asleepUntilAt: wake)
        XCTAssertTrue(delivery.headline.hasPrefix("Pojawi się "))
        XCTAssertTrue(delivery.explanation.contains("przycisk"))
        delivery.missedWakeAt = wake
        XCTAssertTrue(delivery.headline.hasPrefix("Ramka nie obudziła się o "))
        XCTAssertTrue(delivery.explanation.hasPrefix("Spróbuje znowu "))
    }

    func testEconomySettingsAndCountdown() throws {
        var settings = FrameSettings.defaults
        settings.changeTimes = ["07:00", "19:00"]
        XCTAssertEqual(settings.checkMinutes, [])
        settings.powerMode = "economy"
        settings.checkEveryHours = 4
        XCTAssertEqual(settings.checkMinutes, [11 * 60, 15 * 60])
        settings.changeTimes = ["08:00"]
        settings.checkEveryHours = 6
        XCTAssertEqual(settings.checkMinutes, [14 * 60])
        let json = try LiveBackend.encoder().encode(settings)
        XCTAssertTrue(String(decoding: json, as: UTF8.self).contains("\"power_mode\":\"economy\""))
        let decoded = try LiveBackend.decoder().decode(FrameSettings.self, from: json)
        XCTAssertTrue(decoded.isEconomy)

        let now = Date.now
        let iso = { (seconds: TimeInterval) in ISO8601DateFormatter().string(from: now.addingTimeInterval(seconds)) }
        XCTAssertEqual(When.countdown(iso(6 * 3600 + 12 * 60), from: now), "za 6 h 12 min")
        XCTAssertEqual(When.countdown(iso(12 * 60), from: now), "za 12 min")
        XCTAssertEqual(When.countdown(iso(30), from: now), "za chwilę")
        XCTAssertEqual(Names.wakes(2), "pobudki")
        XCTAssertEqual(Names.wakes(5), "pobudek")
    }

    func testPanelAppDecodes() throws {
        let json = """
        {"active": true,
         "package": {"version": "1.0.0", "size": 24576, "uploaded_at": "2026-10-28T09:00:00+00:00"},
         "state": {"active": true, "seen_at": "2026-10-28T09:05:00+00:00", "build": "1.0.0",
                   "code": "abc", "screen": "2560x1440@1", "asleep": true,
                   "wake_at": "2026-10-28T19:00:00+01:00", "standby": false,
                   "missed_wake": null, "previous_source": 0}}
        """
        let app = try LiveBackend.decoder().decode(PanelAppView.self, from: Data(json.utf8))
        XCTAssertTrue(app.active)
        XCTAssertEqual(app.package?.size, 24576)
        XCTAssertEqual(app.state.standby, false)
        let status = try LiveBackend.decoder().decode(
            DeviceStatus.self, from: Data(#"{"configured": true, "panel_app": true}"#.utf8)
        )
        XCTAssertEqual(status.panelApp, true)
    }

    func testPanelWifiDecodesAndExplainsAWrongNetwork() throws {
        let json = """
        {"configured": true, "panel_app": true, "wifi": {"read_at": "2026-10-28T20:00:00+00:00",
         "signal": 0.6, "level": 3, "ssid": "Rocky IoT", "ip": "192.168.3.151", "frequency": 2437,
         "expected_ip": "192.100.3.151", "home_ssid": "IoT_Synology", "wrong_network": true}}
        """
        let status = try LiveBackend.decoder().decode(DeviceStatus.self, from: Data(json.utf8))
        let wifi = try XCTUnwrap(status.wifi)
        XCTAssertEqual(wifi.band, "2,4 GHz")
        XCTAssertEqual(wifi.strength, "sygnał średni (3/5)")
        XCTAssertTrue(wifi.warning?.contains("Rocky IoT zamiast IoT_Synology") == true)
        let home = PanelWifi(readAt: "2026-10-28T20:00:00+00:00", signal: 0.2, ssid: "IoT_Synology")
        XCTAssertNil(home.warning)
        XCTAssertEqual(home.strength, "sygnał słaby (20 %)")
        XCTAssertNil(home.band)
    }

    func testProgressPhasesAndLabels() {
        var progress = DisplayProgress(stage: "refreshing", phase: "displaying", active: true,
                                       title: "", fraction: 0.8, secondsLeft: 150)
        XCTAssertEqual(progress.phaseIndex, 2)
        progress = DisplayProgress(stage: "done", active: false, title: "", fraction: 1)
        XCTAssertEqual(progress.phaseIndex, DisplayProgress.phases.count)
        XCTAssertEqual(progress.stageLabel, "Obraz jest na ramce")
    }

    func testPanelAddressChecks() {
        XCTAssertEqual(PanelAddress.host(" http://192.168.1.152/ "), "192.168.1.152")
        XCTAssertNil(PanelAddress.host("192.168.1.152; rm"))
        XCTAssertEqual(PanelAddress.mac("a4-30-7a-01-02-ff"), "A4:30:7A:01:02:FF")
        XCTAssertEqual(PanelAddress.mac(""), "")
        XCTAssertNil(PanelAddress.mac("A4:30:7A:01:02"))
    }

    func testPanelConfigUpdateKeepsPinUnlessTyped() throws {
        let update = PanelConfigUpdate(host: "192.168.1.152", pin: nil, mac: nil, port: 1515)
        let json = try XCTUnwrap(
            JSONSerialization.jsonObject(with: LiveBackend.encoder().encode(update)) as? [String: Any]
        )
        XCTAssertNil(json["pin"])  // left out: the server keeps its PIN
        XCTAssertTrue(json["mac"] is NSNull)  // sent as null: no Wake-on-LAN
        let config = try LiveBackend.decoder().decode(
            PanelConfig.self,
            from: Data(#"{"host": "192.168.1.152", "mac": null, "port": 1515, "pin_set": true, "from_app": true}"#.utf8)
        )
        XCTAssertTrue(config.pinSet)
        XCTAssertTrue(config.fromApp)
    }

    func testAiSettingsFromServerAndPartialUpdates() throws {
        let json = #"""
        {"key_set": true, "key_tail": "abcd", "key_from_app": true, "pl_text": true,
         "keywords_artworks": true, "keywords_photos": false, "monthly_limit_usd": 5.0,
         "spent_usd": 0.42, "spent_by_kind": {"keywords": 0.42},
         "keywords_progress": {"done": 120, "waiting": 34, "refused": 1, "batch_items": 0,
                               "batch_done": 0, "preparing": false},
         "pl_text_progress": null, "error": null}
        """#
        let settings = try LiveBackend.decoder().decode(AiSettings.self, from: Data(json.utf8))
        XCTAssertEqual(settings.keyTail, "abcd")
        XCTAssertFalse(settings.keywordsPhotos)
        XCTAssertEqual(settings.keywordsProgress.done, 120)
        XCTAssertNil(settings.plTextProgress)

        let data = try LiveBackend.encoder().encode(AiSettingsUpdate(keywordsPhotos: false))
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object as? [String: Bool], ["keywords_photos": false])  // the rest stays
    }

    func testEncodesSettingsInSnakeCase() throws {
        var settings = FrameSettings.defaults
        settings.playlistId = 4
        let data = try LiveBackend.encoder().encode(settings)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["playlist_id"] as? Int, 4)
        XCTAssertEqual(object["change_times"] as? [String], ["07:00"])
        XCTAssertEqual(object["change_every_days"] as? Int, 1)
        XCTAssertNotNil(object["quiet_start"])
        XCTAssertNil(object["interval_minutes"])
    }

    func testQuietHoursOffIsSentAsNull() throws {
        var settings = FrameSettings.defaults
        settings.quietStart = nil
        let text = String(decoding: try LiveBackend.encoder().encode(settings), as: UTF8.self)
        XCTAssertTrue(text.contains("\"quiet_start\":null"))
    }

    func testQuietHoursEndAtTheNextChange() {
        var settings = FrameSettings.defaults
        settings.changeTimes = ["19:00", "07:30"]
        XCTAssertEqual(settings.quietEnd, "07:30")
        settings.quietStart = "05:00"
        XCTAssertEqual(settings.quietEnd, "07:30")
        settings.quietStart = "07:30"
        XCTAssertEqual(settings.quietEnd, "19:00")
        settings.changeTimes = ["07:30"]
        XCTAssertNil(settings.quietEnd)
        XCTAssertEqual(ScheduleSection.nextFreeTime(after: ["07:00"]), "10:00")
        XCTAssertEqual(ScheduleSection.nextFreeTime(after: ["07:00", "22:00"]), "01:00")
    }

    func testDecodesSettingsFromAnOlderServer() throws {
        let json = """
        {"mode": "art", "playlist_id": null, "interval_minutes": 1440,
         "interval_minutes_battery": 1440, "quiet_start": "22:00", "quiet_end": "06:30",
         "shuffle": true, "avoid_repeat_days": 14, "orientation": "portrait", "rotation": 90,
         "art": {"preset": "painting", "fit": "auto", "margin": 0.05, "label": false},
         "photo": {"preset": "photo", "fit": "fill", "margin": 0, "label": false},
         "album_url": "", "timezone": "Europe/Warsaw", "status_poll_minutes": 15}
        """
        let settings = try LiveBackend.decoder().decode(FrameSettings.self, from: Data(json.utf8))
        XCTAssertEqual(settings.changeTimes, ["06:30"])
        XCTAssertEqual(settings.changeEveryDays, 1)
        XCTAssertEqual(settings.quietStart, "22:00")
    }

    func testPhotoMultiSettingsRoundTrip() throws {
        var settings = FrameSettings.defaults
        settings.photo.fit = "multi"
        settings.photo.multiCount = 6
        settings.photo.multiGrid = "B"
        let data = try LiveBackend.encoder().encode(settings)
        let text = String(decoding: data, as: UTF8.self)
        XCTAssertTrue(text.contains("\"multi_count\":6"))
        XCTAssertTrue(text.contains("\"multi_grid\":\"B\""))
        let back = try LiveBackend.decoder().decode(FrameSettings.self, from: data)
        XCTAssertEqual(back.photo, settings.photo)
        // Older servers send no multi fields.
        let old = #"{"preset": "photo", "fit": "fill", "margin": 0, "label": false}"#
        let pres = try LiveBackend.decoder().decode(Presentation.self, from: Data(old.utf8))
        XCTAssertEqual(pres.multiCount, 4)
        XCTAssertEqual(pres.multiGrid, "auto")
    }

    func testMultiGridsMatchTheServer() {
        XCTAssertEqual(Array(MultiGrid.all.keys).sorted(), Array(MultiGrid.counts))
        let canvas = CGRect(x: 0, y: 0, width: 2560, height: 1440)
        for (count, grids) in MultiGrid.all {
            for grid in grids {
                let rects = grid.rects(in: canvas.size, margin: 0.07)
                XCTAssertEqual(rects.count, count)
                XCTAssertTrue(rects.allSatisfy { canvas.contains($0) })
            }
        }
        // Two portrait windows; on a portrait frame, two landscape ones.
        let pair = MultiGrid.grids(2)[0]
        let wide = pair.rects(in: canvas.size, margin: 0.07)[0]
        XCTAssertGreaterThan(wide.height, wide.width)
        let tall = pair.rects(in: CGSize(width: 1440, height: 2560), margin: 0.07)[0]
        XCTAssertGreaterThan(tall.width, tall.height)
    }

    func testRequestsCarryTokenAndEscapeIDs() throws {
        let api = LiveBackend(baseURL: URL(string: "http://frame.local:8099")!, token: "secret")
        let request = try XCTUnwrap(api.request(for: .thumb("aic:24645")))
        XCTAssertEqual(request.url?.absoluteString, "http://frame.local:8099/api/library/items/aic:24645/thumb")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer secret")
        let preview = try XCTUnwrap(api.request(for: .path("/api/previews/X.png")))
        XCTAssertEqual(preview.url?.path, "/api/previews/X.png")
    }

    func testRequestsFollowTheServerAddressInUse() throws {
        let home = try XCTUnwrap(URL(string: "http://192.100.3.185:8099"))
        let remote = try XCTUnwrap(URL(string: "http://nas.tail0.ts.net:8099/"))
        XCTAssertFalse(ServerRoute(home: home, remote: home).hasRemote)
        XCTAssertEqual(ServerRoute(home: home, active: .remote).active, .home)

        let atHome = ServerRoute(home: home, remote: remote)
        let built = LiveBackend(route: atHome, token: "secret").request("/api/items", query: [URLQueryItem(name: "q", value: "a b")])
        XCTAssertEqual(built.url?.absoluteString, "http://192.100.3.185:8099/api/items?q=a%20b")
        XCTAssertNil(atHome.rebased(built))

        let away = ServerRoute(home: home, remote: remote, active: .remote)
        let api = LiveBackend(route: away, token: "secret")
        let thumb = try XCTUnwrap(api.request(for: .thumb("aic:1")))
        XCTAssertEqual(thumb.url?.absoluteString, "http://nas.tail0.ts.net:8099/api/library/items/aic:1/thumb")
        let moved = try XCTUnwrap(away.rebased(built))
        XCTAssertEqual(moved.url?.absoluteString, "http://nas.tail0.ts.net:8099/api/items?q=a%20b")
        XCTAssertEqual(moved.value(forHTTPHeaderField: "Authorization"), "Bearer secret")
        XCTAssertTrue(ServerRoute.neverArrived(URLError(.cannotConnectToHost)))
        XCTAssertFalse(ServerRoute.neverArrived(URLError(.timedOut)))
        XCTAssertTrue(ServerRoute.unreachable(URLError(.timedOut)))
        XCTAssertFalse(ServerRoute.unreachable(URLError(.cancelled)))
    }

    func testMultipartBodyContainsFieldsAndFile() throws {
        var form = MultipartForm()
        form.addField("hold", "forever")
        form.addFile("file", filename: "a.jpg", mimeType: "image/jpeg", data: Data([0xFF, 0xD8]))
        let body = String(decoding: form.body(), as: UTF8.self)
        XCTAssertTrue(body.contains("name=\"hold\"\r\n\r\nforever\r\n"))
        XCTAssertTrue(body.contains("filename=\"a.jpg\""))
        XCTAssertTrue(body.hasSuffix("--\(form.boundary)--\r\n"))
    }

    func testPolishPlurals() {
        XCTAssertEqual(Names.works(1), "1 dzieło")
        XCTAssertEqual(Names.works(3), "3 dzieła")
        XCTAssertEqual(Names.works(5), "5 dzieł")
        XCTAssertEqual(Names.works(12), "12 dzieł")
        XCTAssertEqual(Names.works(22), "22 dzieła")
    }

    func testDemoSuggestionsAndThemes() async throws {
        let demo = DemoBackend()
        let rows = try await demo.suggestions()
        XCTAssertEqual(rows.map(\.key), ["for-you", "like:impressionism", "theme"])
        XCTAssertTrue(rows.allSatisfy { !$0.items.isEmpty })
        let themes = try await demo.themes()
        let theme = try XCTUnwrap(themes.first { $0.key == rows[2].theme })
        XCTAssertNotNil(theme.group)
        XCTAssertFalse(theme.cover?.isEmpty ?? true)
        let page = try await demo.themePage(key: theme.key, page: 1)
        XCTAssertFalse(page.items.isEmpty)
        XCTAssertFalse(page.more)
        XCTAssertEqual(page.items.first?.thumb, .thumb(page.items[0].id))  // demo works are on the server
        XCTAssertNil(page.items[0].thumbFallback)
    }

    func testMuseumThumbnailFallsBackToTheServer() async throws {
        let demo = DemoBackend()
        let themes = try await demo.themes()
        let theme = try XCTUnwrap(themes.first)
        let page = try await demo.themePage(key: theme.key, page: 1)
        var item = try XCTUnwrap(page.items.first).item
        item.thumbUrl = "https://www.artic.edu/iiif/2/abc/full/600,/0/default.jpg"
        let remote = RemoteItem(item: item, inLibrary: false)
        XCTAssertEqual(remote.thumb, .url(try XCTUnwrap(URL(string: item.thumbUrl))))
        XCTAssertEqual(remote.thumbFallback, .thumb(item.id))
        item.thumbUrl = ""
        XCTAssertNil(RemoteItem(item: item, inLibrary: false).thumbFallback)
    }

    func testSavingToPhotosPrefersTheMuseumsImage() async throws {
        let demo = DemoBackend()
        let themes = try await demo.themes()
        let page = try await demo.themePage(key: try XCTUnwrap(themes.first).key, page: 1)
        var item = try XCTUnwrap(page.items.first).item
        item.kind = .artwork
        item.imageUrl = "https://images.metmuseum.org/CRDImages/ep/original/DT1567.jpg"
        let sources = PhotoSaver.sources(for: item, backend: demo).map(\.url)
        XCTAssertEqual(sources.first, URL(string: item.imageUrl))
        XCTAssertEqual(sources.last, demo.request(for: .image(item.id))?.url)
        item.kind = .photo  // an iCloud photo's address expires: the server's copy only
        XCTAssertEqual(PhotoSaver.sources(for: item, backend: demo).count, 1)
        item.artist = "Vincent van Gogh"
        item.title = "Irysy / Irises"
        XCTAssertEqual(PhotoSaver.fileName(for: item), "Vincent van Gogh – Irysy Irises")
    }

    func testThemesBecomePlaylists() async throws {
        let demo = DemoBackend()
        let made = try await demo.themePlaylist(key: "sea", play: false)
        XCTAssertEqual(made.playlist.theme, "sea")
        XCTAssertGreaterThan(made.playlist.itemCount, 0)
        let again = try await demo.themePlaylist(key: "sea", play: false)
        XCTAssertEqual(again.playlist.id, made.playlist.id)
        let card = try await demo.themes().first { $0.key == "sea" }
        XCTAssertEqual(card?.playlistId, made.playlist.id)
    }

    func testSearchTokensRoundTrip() async throws {
        var rules = PlaylistRules(query: "mgła", artists: ["Claude Monet"], styles: ["Impressionism"])
        rules.terms = ["subject:sea", "years:1880-1914"]
        let tokens = rules.tokens(names: ["subject:sea": "Morze"])
        XCTAssertEqual(tokens.map(\.name), ["Claude Monet", "Morze", "1880–1914", "Impressionism", "mgła"])
        XCTAssertEqual(tokens[2].kind, "period")
        var back = PlaylistRules()
        back.setTokens(tokens)
        XCTAssertEqual(back, rules)
        XCTAssertEqual(rules.suggestedName(names: ["subject:sea": "Morze"]), "Claude Monet · Morze · 1880–1914")

        let demo = DemoBackend()
        let hits = try await demo.terms("mor")
        XCTAssertEqual(hits.first { $0.kind == "subject" }?.key, "subject:sea")
        XCTAssertEqual(hits.last?.kind, "word")
        let sea = try await demo.items(LibraryQuery(rules: PlaylistRules(terms: ["subject:sea"])))
        XCTAssertGreaterThan(sea.total, 0)
        let json = #"{"kind": "artist", "key": "Hokusai", "name": "Hokusai", "detail": "", "count": 3}"#
        XCTAssertEqual(try LiveBackend.decoder().decode(TermHit.self, from: Data(json.utf8)).count, 3)
    }

    func testLaterPagesLeaveOutCopiesOfWorks() async throws {
        let demo = DemoBackend()
        let themes = try await demo.themes()
        let theme = try XCTUnwrap(themes.first)
        let page = try await demo.themePage(key: theme.key, page: 1)
        var item = try XCTUnwrap(page.items.first).item
        item.year = 1889
        item.source = "met"
        let met = RemoteItem(item: item, inLibrary: false, work: "gogh|irises")
        // The same work from Commons: another id and source.
        let encoded = try LiveBackend.encoder().encode(item)
        var fields = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        fields["id"] = "wmc:1"
        fields["source"] = "wmc"
        fields["year"] = NSNull()
        let data = try JSONSerialization.data(withJSONObject: fields)
        var copy = try LiveBackend.decoder().decode(Item.self, from: data)
        let commons = RemoteItem(item: copy, inLibrary: false, work: "gogh|irises")
        copy.year = 1880
        let older = RemoteItem(item: copy, inLibrary: false, work: "gogh|irises")
        let other = RemoteItem(item: copy, inLibrary: false, work: "")
        XCTAssertEqual([met].adding([commons, met]).map(\.id), [met.id])
        XCTAssertEqual([met].adding([older]).map(\.id), [met.id, "wmc:1"])
        XCTAssertEqual([met].adding([other]).map(\.id), [met.id, "wmc:1"])
        // A better copy, come later, takes the place of the one shown.
        var better = met
        better.replaces = "wmc:1"
        XCTAssertEqual([commons].adding([better]).map(\.id), [met.id])
        let decoded = try LiveBackend.decoder().decode(
            RemoteItem.self, from: try LiveBackend.encoder().encode(met)
        )
        XCTAssertEqual(decoded.work, "gogh|irises")
    }

    func testDecodesThemePage() throws {
        let json = #"{"items": [], "more": true}"#
        let page = try LiveBackend.decoder().decode(ArtThemePage.self, from: Data(json.utf8))
        XCTAssertTrue(page.more)
        XCTAssertNil(page.nextPage)
        let skipped = #"{"items": [], "more": true, "next_page": 4}"#
        XCTAssertEqual(try LiveBackend.decoder().decode(ArtThemePage.self, from: Data(skipped.utf8)).nextPage, 4)
        let row = #"{"key": "theme", "title": "Motyw dnia", "subtitle": "", "theme": "ukiyo-e", "items": []}"#
        let decoded = try LiveBackend.decoder().decode(SuggestionRow.self, from: Data(row.utf8))
        XCTAssertEqual(decoded.theme, "ukiyo-e")
    }

    func testDemoBackendFiltersAndPlaylists() async throws {
        let demo = DemoBackend()
        let all = try await demo.items(LibraryQuery())
        XCTAssertGreaterThan(all.total, 10)
        var query = LibraryQuery()
        query.artists = ["Utagawa Hiroshige"]
        let hiroshige = try await demo.items(query)
        XCTAssertGreaterThan(hiroshige.total, 0)
        XCTAssertTrue(hiroshige.items.allSatisfy { $0.artist == "Utagawa Hiroshige" })

        let playlists = try await demo.playlists()
        XCTAssertFalse(playlists.isEmpty)
        let woodblock = try await demo.previewRules(PlaylistRules(query: "woodblock"))
        XCTAssertGreaterThan(woodblock.count, 0)

        let before = try await demo.player()
        try await demo.next()
        let after = try await demo.player()
        XCTAssertNotEqual(before.current?.item?.id, after.current?.item?.id)
        try await demo.previous()
        let back = try await demo.player()
        XCTAssertEqual(back.current?.item?.id, before.current?.item?.id)
    }

    func testRemovingSingleWorksFromPlaylists() async throws {
        let demo = DemoBackend()
        let playlists = try await demo.playlists()
        let smart = try XCTUnwrap(playlists.first { $0.kind == .smart && $0.itemCount > 1 })
        let detail = try await demo.playlist(id: smart.id)
        let victim = try XCTUnwrap(detail.items.first)
        let trimmed = try await demo.removeFromPlaylist(id: smart.id, itemID: victim.id)
        XCTAssertEqual(trimmed.playlist.itemCount, smart.itemCount - 1)
        XCTAssertFalse(trimmed.items.contains { $0.id == victim.id })
        XCTAssertEqual(trimmed.playlist.rules.excludeIds, [victim.id])

        let manual = try await demo.savePlaylist(
            Playlist(name: "Wybór", kind: .manual, itemIds: trimmed.items.prefix(2).map(\.id))
        )
        let left = try await demo.removeFromPlaylist(id: manual.playlist.id, itemID: manual.itemIds[0])
        XCTAssertEqual(left.itemIds, [manual.itemIds[1]])
    }

    func testRulesFromOlderServersHaveNoExceptions() throws {
        let json = """
            {"query": "", "artists": ["Ala"], "styles": [], "subjects": [], "colors": [], "kinds": [],
             "sources": [], "year_from": null, "year_to": null, "favorites_only": false, "min_suitability": null}
            """
        let rules = try LiveBackend.decoder().decode(PlaylistRules.self, from: Data(json.utf8))
        XCTAssertEqual(rules.artists, ["Ala"])
        XCTAssertEqual(rules.excludeIds, [])
        XCTAssertTrue(PlaylistRules(excludeIds: ["x"]).isEmpty)
    }

    func testDemoBackendUsesBundledImages() throws {
        let demo = DemoBackend()
        let thumb = try XCTUnwrap(demo.request(for: .thumb("aic:24645"))?.url)
        XCTAssertTrue(thumb.isFileURL)
        XCTAssertEqual(thumb.lastPathComponent, "aic_24645.jpg")
        let preview = try XCTUnwrap(demo.request(for: .path("/demo/aic:24645?key"))?.url)
        XCTAssertTrue(preview.isFileURL)
        XCTAssertTrue(preview.lastPathComponent.hasPrefix("aic_24645-landscape-"))
    }

    func testDemoPresentationWaitsForTheNextPicture() async throws {
        let demo = DemoBackend()
        let before = try await demo.player().current?.previewUrl
        var settings = try await demo.settings()
        settings.art.fit = "fill"
        _ = try await demo.saveSettings(settings)
        // The picture on the frame stays as it was drawn.
        let kept = try await demo.player().current?.previewUrl
        XCTAssertEqual(before, kept)
        let current = try await demo.player().current
        let id = try XCTUnwrap(current?.item?.id)
        let framed = try XCTUnwrap(demo.request(for: .framePreview(id))?.url)
        XCTAssertTrue(framed.lastPathComponent.contains("-fill-"))
        // Turning the screen redraws it, with the new presentation too.
        settings.orientation = settings.orientation == "portrait" ? "landscape" : "portrait"
        _ = try await demo.saveSettings(settings)
        let after = try await demo.player().current?.previewUrl
        XCTAssertNotEqual(before, after)
    }

    func testFrameNameRoundTrip() throws {
        var settings = FrameSettings.defaults
        var text = String(decoding: try LiveBackend.encoder().encode(settings), as: UTF8.self)
        XCTAssertFalse(text.contains("\"name\""))
        settings.name = "Salon"
        let data = try LiveBackend.encoder().encode(settings)
        text = String(decoding: data, as: UTF8.self)
        XCTAssertTrue(text.contains("\"name\":\"Salon\""))
        XCTAssertEqual(try LiveBackend.decoder().decode(FrameSettings.self, from: data).name, "Salon")
        // A turned screen redraws the picture; a new presentation does not.
        var restyled = settings
        restyled.art.mat = "black"
        XCTAssertEqual(restyled.screenKey, settings.screenKey)
        XCTAssertNotEqual(restyled.presentationKey, settings.presentationKey)
    }

    func testDemoCropCorrections() async throws {
        let demo = DemoBackend()
        let current = try await demo.player().current
        let id = try XCTUnwrap(current?.item?.id)  // a tall woodblock print: a description
        let view = try await demo.framing(itemID: id, orientation: "landscape")
        XCTAssertEqual(view.fit, "description")
        XCTAssertEqual(view.windows.map(\.role), ["picture", "detail"])
        XCTAssertFalse(view.windows.contains(where: \.custom))

        var crops = view.windows.map(\.crop)
        crops[0].zoom = 3
        let saved = try await demo.saveFraming(itemID: id, orientation: "landscape", crops: crops)
        XCTAssertTrue(saved.windows.allSatisfy(\.custom))
        XCTAssertEqual(saved.windows[0].crop.zoom, 3)
        let after = try await demo.player().current?.previewUrl
        XCTAssertNotEqual(current?.previewUrl, after)

        // "Kadr automatyczny" is offered without forgetting the saved crop.
        let auto = try await demo.framing(itemID: id, orientation: "landscape", automatic: true)
        XCTAssertFalse(auto.windows.contains(where: \.custom))
        XCTAssertEqual(auto.windows.map(\.crop), view.windows.map(\.crop))
        let still = try await demo.framing(itemID: id, orientation: "landscape")
        XCTAssertEqual(still.windows[0].crop.zoom, 3)

        // The windows' places, to crop right on the preview: two apart, on the canvas.
        let rects = try saved.windows.map { try XCTUnwrap($0.frame) }
        let canvas = CGRect(x: 0, y: 0, width: 1, height: 1).insetBy(dx: -0.0001, dy: -0.0001)
        XCTAssertTrue(rects.allSatisfy { canvas.contains($0) && $0.width > 0.05 && $0.height > 0.05 })
        XCTAssertFalse(rects[0].intersects(rects[1].insetBy(dx: 0.001, dy: 0.001)))
        for (window, rect) in zip(saved.windows, rects) {
            XCTAssertEqual(rect.width * 1280 / (rect.height * 720), window.aspect, accuracy: 0.01)
        }

        let reset = try await demo.resetFraming(itemID: id, orientation: "landscape")
        XCTAssertFalse(reset.windows.contains(where: \.custom))

        // Only the close-up, as older versions sent it: the picture stays whole.
        let one = try await demo.saveFraming(itemID: id, orientation: "landscape", crops: [Crop(x: 0.4, y: 0.6, zoom: 2)])
        XCTAssertEqual(one.windows[1].crop, Crop(x: 0.4, y: 0.6, zoom: 2))
        XCTAssertEqual(one.windows[0].crop, DemoFraming.wholeCrop)
    }

    func testFramingDraft() {
        let window = FramingWindow(role: "picture", aspect: 0.667, crop: Crop(zoom: 1.04), custom: true,
                                   rect: [0.3, 0.05, 0.4, 0.8], area: [0.05, 0.05, 0.9, 0.8])
        let view = FramingView(orientation: "landscape", fit: "fit", width: 800, height: 1200, windows: [window])
        var draft = FramingDraft(key: "a", view: view, saved: [window.crop], crops: [window.crop])
        XCTAssertNil(draft.change)
        XCTAssertNil(draft.trial)

        draft.crops[0].x = 0.4  // moved: saved on sending, same window
        XCTAssertEqual(draft.change, .save(orientation: "landscape", crops: draft.crops))
        XCTAssertFalse(draft.reshaped)

        draft.crops[0].aspect = 1  // a square window: the preview tries it first
        XCTAssertTrue(draft.reshaped)
        XCTAssertEqual(draft.trial, FramingCrops(fit: Crop(aspect: 1)))
        XCTAssertEqual(draft.aspect(0), 1)

        // Back to automatic: sending forgets the saved crop.
        draft.automatic = [Crop()]
        draft.crops = [Crop()]
        XCTAssertEqual(draft.change, .reset(orientation: "landscape"))
    }

    func testCropSavedFromWorkDetails() async throws {
        let demo = DemoBackend()
        let current = try await demo.player().current
        let id = try XCTUnwrap(current?.item?.id)
        let view = try await demo.framing(itemID: id, orientation: "landscape")
        var draft = FramingDraft(saved: view, key: "k")
        XCTAssertNil(draft.change)

        draft.crops[0].zoom = 3
        guard case let .save(orientation, crops)? = draft.change else { return XCTFail("no change to save") }
        let saved = try await demo.saveFraming(itemID: id, orientation: orientation, crops: crops)
        let after = FramingDraft(saved: saved, key: "k")
        XCTAssertNil(after.change)
        XCTAssertEqual(after.crops[0].zoom, 3)

        // The preview names the crops just saved: the one cached under the
        // plain address still shows the old crop.
        let named = try XCTUnwrap(after.savedCrops)
        XCTAssertEqual(named.picture?.zoom, 3)
        let api = LiveBackend(baseURL: URL(string: "http://frame.local:8099")!, token: "secret")
        let plain = try XCTUnwrap(api.request(for: .framePreview(id))?.url)
        let fresh = try XCTUnwrap(api.request(for: .framePreview(id, framing: named))?.url)
        XCTAssertNotEqual(plain, fresh)
    }

    func testChangesPlural() {
        XCTAssertEqual([1, 2, 4, 5, 12, 22, 25].map(Names.changes),
                       ["zmianę", "zmiany", "zmiany", "zmian", "zmian", "zmiany", "zmian"])
    }

    func testDemoFramingMatchesServerLayout() {
        let canvas = DemoFraming.canvas("landscape")
        let fit = Presentation(preset: "painting", fit: "fit", margin: 0.05, label: false)
        // Portrait 2:3 picture, 5% passe-partout: as layout.plan_layout on the server.
        let framed = DemoFraming.plan(CGSize(width: 800, height: 1200), canvas: canvas, presentation: fit, caption: false, crops: nil)
        XCTAssertEqual(framed.fit, "fit")
        XCTAssertEqual(framed.windows[0].rect, CGRect(x: 424, y: 36, width: 432, height: 648))
        // Nearly 16:9: "auto" fills; a portrait picture gets a description.
        var auto = fit
        auto.fit = "auto"
        let wide = DemoFraming.plan(CGSize(width: 1500, height: 900), canvas: canvas, presentation: auto, caption: false, crops: nil)
        XCTAssertEqual(wide.fit, "fill")
        XCTAssertEqual(wide.windows[0].rect.width, 1280, accuracy: 0.5)
        let tall = DemoFraming.plan(CGSize(width: 800, height: 1200), canvas: canvas, presentation: auto, caption: true, crops: nil)
        XCTAssertEqual(tall.fit, "description")
        XCTAssertEqual(tall.windows.map(\.role), ["picture", "detail"])
        XCTAssertEqual(tall.windows[0].rect, CGRect(x: 0, y: 0, width: 480, height: 720))
        XCTAssertNil(tall.captionAt)
        // The picture's outer edge stays behind the mat.
        XCTAssertEqual(tall.windows[0].box.minX, 16, accuracy: 0.5)
        XCTAssertEqual(framed.windows[0].box.maxY, 1176, accuracy: 0.5)
        // "Opis": the text below the close-up, which is at least 1.8× the picture.
        XCTAssertGreaterThan(tall.textRect?.minY ?? 0, tall.windows[1].rect.maxY)
        let scale = tall.windows.map { $0.rect.width / $0.box.width }
        XCTAssertGreaterThanOrEqual(scale[1] / scale[0], 1.8 - 1e-6)
        // The picture moved and zoomed in its window, which keeps its shape.
        var description = fit
        description.fit = "description"
        let crops = DemoFraming.Crops(picture: Crop(x: 0.3, y: 0.4, zoom: 2))
        let zoomed = DemoFraming.plan(CGSize(width: 800, height: 1200), canvas: canvas, presentation: description, caption: false, crops: crops)
        XCTAssertEqual(zoomed.windows[0].rect, tall.windows[0].rect)
        XCTAssertEqual(zoomed.windows[0].box.width, 400, accuracy: 0.5)
        XCTAssertEqual(zoomed.windows[0].box.midX, 240, accuracy: 0.5)
    }

    func testDescriptionCropsFromTheDraft() {
        let both = FramingCrops(mode: "description", crops: [Crop(zoom: 2), Crop(x: 0.2, zoom: 3)])
        XCTAssertEqual(both, FramingCrops(detail: Crop(x: 0.2, zoom: 3), picture: Crop(zoom: 2)))
        XCTAssertEqual(FramingCrops(mode: "description", crops: [Crop(zoom: 3)]), FramingCrops(detail: Crop(zoom: 3)))
    }

    func testChosenModesAlwaysApply() {
        let canvas = DemoFraming.canvas("landscape")
        // A 16:9 picture on the 16:9 frame: no room beside it, so it gets smaller.
        for fit in ["description"] {
            let pres = Presentation(preset: "painting", fit: fit, margin: 0.05, label: true)
            let plan = DemoFraming.plan(CGSize(width: 1600, height: 900), canvas: canvas, presentation: pres, caption: true, crops: nil)
            XCTAssertEqual(plan.fit, fit)
            let main = plan.windows[0].rect
            XCTAssertGreaterThan(main.minX, 0)
            XCTAssertLessThan(main.width, canvas.width)
            XCTAssertEqual(main.width / main.height, 16.0 / 9.0, accuracy: 0.01)
            XCTAssertEqual(plan.windows[1].rect.minY, main.minY)  // aligned with the picture
        }
    }

    func testPassePartoutCropTakesAnyShape() {
        let canvas = DemoFraming.canvas("landscape")
        let pres = Presentation(preset: "painting", fit: "fit", margin: 0.05, label: false)
        let plain = DemoFraming.plan(CGSize(width: 800, height: 1200), canvas: canvas, presentation: pres, caption: false, crops: nil)
        XCTAssertEqual(plain.windows[0].crop, DemoFraming.wholeCrop)
        let crops = DemoFraming.Crops(fit: Crop(x: 0.5, y: 0.3, zoom: 1.5, aspect: 1))
        let square = DemoFraming.plan(CGSize(width: 800, height: 1200), canvas: canvas, presentation: pres, caption: false, crops: crops)
        let rect = square.windows[0].rect
        XCTAssertEqual(rect.width, rect.height)
        XCTAssertEqual(rect.height, 648)
        XCTAssertEqual(square.windows[0].box.width, 800 / 1.5, accuracy: 0.5)
    }

    func testPhotoUploadReadsExifDates() {
        XCTAssertEqual(PhotoUpload.iso(exif: "2026:07:01 10:00:00"), "2026-07-01T10:00:00")
        XCTAssertNil(PhotoUpload.iso(exif: "garbage"))
        XCTAssertEqual(PickedPhoto.title("2026-07-01T10:00:00"), "Zdjęcie z 1 lipca 2026")
        XCTAssertEqual(PickedPhoto.title(nil), "Zdjęcie z rolki")
        XCTAssertEqual(Names.photos(1), "1 zdjęcie")
        XCTAssertEqual(Names.photos(3), "3 zdjęcia")
        XCTAssertEqual(Names.photos(12), "12 zdjęć")
        XCTAssertEqual(Names.photos(22), "22 zdjęcia")
    }

    func testDemoUploadedPhotosJoinAPlaylist() async throws {
        let demo = DemoBackend()
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let jpeg = UIGraphicsImageRenderer(size: CGSize(width: 300, height: 200), format: format)
            .jpegData(withCompressionQuality: 0.8) { context in
                UIColor.systemTeal.setFill()
                context.fill(CGRect(x: 0, y: 0, width: 300, height: 200))
            }
        let item = try await demo.uploadPhoto(PhotoUpload(data: jpeg, title: "Morze", takenAt: "2026-07-01T10:00:00"))
        XCTAssertEqual(item.kind, .photo)
        XCTAssertEqual(item.dateText, "2026-07-01")
        XCTAssertNotNil(demo.request(for: .thumb(item.id)))
        let saved = try await demo.savePlaylist(Playlist(name: "Wakacje", kind: .manual, itemIds: [item.id]))
        XCTAssertEqual(saved.itemIds, [item.id])
    }

    func testDemoPhotoSentOnceHasItsOwnLook() async throws {
        let demo = DemoBackend()
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let jpeg = UIGraphicsImageRenderer(size: CGSize(width: 300, height: 200), format: format)
            .jpegData(withCompressionQuality: 0.8) { context in
                UIColor.systemOrange.setFill()
                context.fill(CGRect(x: 0, y: 0, width: 300, height: 200))
            }
        var photo = PhotoUpload(data: jpeg, title: "Zdjęcie z rolki")
        var look = Look(FrameSettings.defaults.photo)
        XCTAssertEqual(look.fit, "fill")
        look.fit = "fit"
        look.mat = "cream"
        photo.look = look
        let item = try await demo.uploadPhoto(photo)
        XCTAssertEqual(item.look, look)
        var query = LibraryQuery()
        query.kinds = [.photo]
        let photos = try await demo.items(query)
        XCTAssertFalse(photos.items.contains { $0.id == item.id })  // never listed
        let framed = try await demo.framing(itemID: item.id, orientation: "portrait")
        XCTAssertEqual(framed.fit, "fit")

        look.fit = "fill"
        let changed = try await demo.setLook(itemID: item.id, look)
        XCTAssertEqual(changed.look?.fit, "fill")
        let filled = try await demo.framing(itemID: item.id, orientation: "portrait")
        XCTAssertEqual(filled.fit, "fill")
        try await demo.deleteItem(id: item.id)
        let gone = try? await demo.item(id: item.id)
        XCTAssertNil(gone)

        var settings = FrameSettings.defaults
        settings.photo = settings.photo.with(look)
        XCTAssertEqual(settings.photo.preset, "auto")
        XCTAssertFalse(settings.photo.label)
    }

    func testDecodesAlbumPlaylists() throws {
        let json = """
        {"id": 7, "name": "Rodzina", "description": "", "kind": "album",
         "rules": {"query": "", "artists": [], "styles": [], "subjects": [], "colors": [], "kinds": [],
                   "sources": [], "year_from": null, "year_to": null, "favorites_only": false,
                   "min_suitability": null, "exclude_ids": []},
         "item_count": 12, "cover_item_ids": ["icloud:G1"],
         "album": {"url": "https://www.icloud.com/sharedalbum/#B0aGWZuqDGKPOC", "order": "newest"},
         "album_sync": {"at": "2026-10-25T09:00:00+00:00", "name": "Rodzina", "count": 12, "added": 2,
                        "error": ""}}
        """
        let summary = try LiveBackend.decoder().decode(PlaylistSummary.self, from: Data(json.utf8))
        XCTAssertEqual(summary.kind, .album)
        XCTAssertEqual(summary.album?.order, .newest)
        XCTAssertEqual(summary.albumSync?.added, 2)
        XCTAssertEqual(summary.countText, "12 zdjęć")

        let playlist = Playlist(name: "Góry", kind: .album, album: AlbumSource(url: "https://x", order: .added))
        let text = String(decoding: try LiveBackend.encoder().encode(playlist), as: UTF8.self)
        XCTAssertTrue(text.contains("\"order\":\"added\""))
        XCTAssertTrue(text.contains("\"kind\":\"album\""))
    }

    func testDemoAlbumPlaylists() async throws {
        let demo = DemoBackend()
        let check = try await demo.checkAlbum(url: "https://www.icloud.com/sharedalbum/#B0aGWZuqDGKPOC")
        XCTAssertEqual(check.name, "Rodzina")
        do {
            _ = try await demo.checkAlbum(url: "https://example.com")
            XCTFail("a link that is not an album")
        } catch {}
        let saved = try await demo.savePlaylist(
            Playlist(name: "Rodzina", kind: .album, album: AlbumSource(url: "https://www.icloud.com/sharedalbum/#B0"))
        )
        XCTAssertEqual(saved.playlist.album?.order, .random)
        XCTAssertNotNil(saved.playlist.albumSync)
        let job = try await demo.syncAlbum(playlistID: saved.playlist.id)
        let status = try await demo.job(id: job)
        XCTAssertTrue(status.finished)
    }

    func testDecodesMuseumAnswerLines() throws {
        let line = #"{"source":"aic","total":120,"items":[],"failed":[],"next":4}"#
        let answer = try LiveBackend.decoder().decode(MuseumAnswer.self, from: Data(line.utf8))
        XCTAssertEqual(answer.source, "aic")
        XCTAssertEqual(answer.next, 4)
        let last = try LiveBackend.decoder().decode(
            MuseumAnswer.self, from: Data(#"{"source":"cma","total":3,"items":[],"next":null}"#.utf8)
        )
        XCTAssertNil(last.next)
    }

    func testDemoMuseumsAnswerOneByOne() async throws {
        let demo = DemoBackend()
        var sources: [String] = []
        for try await answer in try await demo.museumAnswers(PlaylistRules(), sources: ["aic", "met"], page: 1) {
            sources.append(answer.source)
        }
        XCTAssertEqual(sources, ["aic", "met"])
    }

    func testDescriptionKeepsWholeSentences() {
        XCTAssertEqual(
            DemoFraming.sentences("Painted c. 1890 in Paris. It shows the artist's room! “Quoted” one."),
            ["Painted c. 1890 in Paris.", "It shows the artist's room!", "“Quoted” one."]
        )
    }

    func testCropBoxClampsInsideThePicture() {
        let box = DemoFraming.cropBox(CGSize(width: 1000, height: 1000), aspect: 16.0 / 9.0, crop: Crop(x: 0, y: 1, zoom: 2))
        XCTAssertEqual(box.minX, 0, accuracy: 0.001)
        XCTAssertEqual(box.maxY, 1000, accuracy: 0.001)
        XCTAssertEqual(box.width, 500, accuracy: 0.001)
    }
}
