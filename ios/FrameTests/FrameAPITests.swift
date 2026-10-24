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
          "history": [],
          "hold": {"until": null, "forever": true},
          "last_change_at": "2026-10-24T05:00:00+00:00",
          "next_change_at": "2026-10-25T05:00:00+00:00",
          "busy": false,
          "last_error": null
        }
        """
        let view = try LiveBackend.decoder().decode(PlayerView.self, from: Data(json.utf8))
        XCTAssertEqual(view.playlist?.itemCount, 21)
        XCTAssertEqual(view.playlist?.rules.query, "woodblock")
        XCTAssertEqual(view.current?.previewUrl, "/api/previews/ABC.png")
        XCTAssertEqual(view.upcoming.first?.aspectRatio ?? 0, 1.5, accuracy: 0.001)
        XCTAssertEqual(view.hold?.forever, true)
        XCTAssertNotNil(When.schedule(view.nextChangeAt))
    }

    func testEncodesSettingsInSnakeCase() throws {
        var settings = FrameSettings.defaults
        settings.playlistId = 4
        let data = try LiveBackend.encoder().encode(settings)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["playlist_id"] as? Int, 4)
        XCTAssertEqual(object["interval_minutes_battery"] as? Int, 1440)
        XCTAssertNotNil(object["quiet_start"])
    }

    func testRequestsCarryTokenAndEscapeIDs() throws {
        let api = LiveBackend(baseURL: URL(string: "http://frame.local:8099")!, token: "secret")
        let request = try XCTUnwrap(api.request(for: .thumb("aic:24645")))
        XCTAssertEqual(request.url?.absoluteString, "http://frame.local:8099/api/library/items/aic:24645/thumb")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer secret")
        let preview = try XCTUnwrap(api.request(for: .path("/api/previews/X.png")))
        XCTAssertEqual(preview.url?.path, "/api/previews/X.png")
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

    func testDemoBackendUsesBundledImages() throws {
        let demo = DemoBackend()
        let thumb = try XCTUnwrap(demo.request(for: .thumb("aic:24645"))?.url)
        XCTAssertTrue(thumb.isFileURL)
        XCTAssertEqual(thumb.lastPathComponent, "aic_24645.jpg")
        let preview = try XCTUnwrap(demo.request(for: .path("/demo/aic:24645?key"))?.url)
        XCTAssertTrue(preview.isFileURL)
        XCTAssertTrue(preview.lastPathComponent.hasPrefix("aic_24645-landscape-fit-"))
    }

    func testDemoPreviewFollowsPresentationSettings() async throws {
        let demo = DemoBackend()
        let before = try await demo.player().current?.previewUrl
        var settings = try await demo.settings()
        settings.art.fit = "fill"
        _ = try await demo.saveSettings(settings)
        let after = try await demo.player().current?.previewUrl
        XCTAssertNotEqual(before, after)
        let current = try await demo.player().current
        let id = try XCTUnwrap(current?.item?.id)
        let framed = try XCTUnwrap(demo.request(for: .framePreview(id))?.url)
        XCTAssertTrue(framed.lastPathComponent.contains("-fill-"))
    }

    func testDemoFramingMatchesServerLayout() {
        let canvas = DemoFraming.canvas("landscape")
        // Portrait 2:3 picture, 5% passe-partout: as layout.placement on the server.
        let fit = DemoFraming.placement(CGSize(width: 800, height: 1200), in: canvas, fit: "fit", margin: 0.05)
        XCTAssertFalse(fit.fill)
        XCTAssertEqual(fit.rect, CGRect(x: 424, y: 36, width: 432, height: 648))
        // Nearly 16:9: "auto" fills.
        let auto = DemoFraming.placement(CGSize(width: 1500, height: 900), in: canvas, fit: "auto", margin: 0.05)
        XCTAssertTrue(auto.fill)
        XCTAssertEqual(auto.rect.width, 1280, accuracy: 0.5)
    }
}
