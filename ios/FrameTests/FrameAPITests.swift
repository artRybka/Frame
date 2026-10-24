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
        XCTAssertTrue(preview.lastPathComponent.hasPrefix("aic_24645-landscape-"))
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

    func testDemoCropCorrections() async throws {
        let demo = DemoBackend()
        let current = try await demo.player().current
        let id = try XCTUnwrap(current?.item?.id)  // a tall woodblock print: close-ups
        let view = try await demo.framing(itemID: id, orientation: "landscape")
        XCTAssertEqual(view.fit, "details")
        XCTAssertEqual(view.windows.count, 2)
        XCTAssertFalse(view.windows.contains(where: \.custom))

        var crops = view.windows.map(\.crop)
        crops[0].zoom = 3
        let saved = try await demo.saveFraming(itemID: id, orientation: "landscape", crops: crops)
        XCTAssertTrue(saved.windows.allSatisfy(\.custom))
        XCTAssertEqual(saved.windows[0].crop.zoom, 3)
        let after = try await demo.player().current?.previewUrl
        XCTAssertNotEqual(current?.previewUrl, after)

        let reset = try await demo.resetFraming(itemID: id, orientation: "landscape")
        XCTAssertFalse(reset.windows.contains(where: \.custom))

        // "Opis": one close-up to correct.
        var settings = try await demo.settings()
        settings.art.fit = "description"
        _ = try await demo.saveSettings(settings)
        let text = try await demo.framing(itemID: id, orientation: "landscape")
        XCTAssertEqual(text.fit, "description")
        XCTAssertEqual(text.windows.count, 1)
        let one = try await demo.saveFraming(itemID: id, orientation: "landscape", crops: [Crop(x: 0.4, y: 0.6, zoom: 2)])
        XCTAssertEqual(one.windows.map(\.custom), [true])
    }

    func testDemoFramingMatchesServerLayout() {
        let canvas = DemoFraming.canvas("landscape")
        let fit = Presentation(preset: "painting", fit: "fit", margin: 0.05, label: false)
        // Portrait 2:3 picture, 5% passe-partout: as layout.plan_layout on the server.
        let framed = DemoFraming.plan(CGSize(width: 800, height: 1200), canvas: canvas, presentation: fit, caption: false, crops: nil)
        XCTAssertEqual(framed.fit, "fit")
        XCTAssertEqual(framed.windows[0].rect, CGRect(x: 424, y: 36, width: 432, height: 648))
        // Nearly 16:9: "auto" fills; a portrait picture gets close-ups.
        var auto = fit
        auto.fit = "auto"
        let wide = DemoFraming.plan(CGSize(width: 1500, height: 900), canvas: canvas, presentation: auto, caption: false, crops: nil)
        XCTAssertEqual(wide.fit, "fill")
        XCTAssertEqual(wide.windows[0].rect.width, 1280, accuracy: 0.5)
        let tall = DemoFraming.plan(CGSize(width: 800, height: 1200), canvas: canvas, presentation: auto, caption: true, crops: nil)
        XCTAssertEqual(tall.fit, "details")
        XCTAssertEqual(tall.windows.map(\.role), ["picture", "detail", "detail"])
        XCTAssertEqual(tall.windows[0].rect, CGRect(x: 0, y: 0, width: 480, height: 720))
        XCTAssertNotNil(tall.captionAt)
        // The picture's outer edge stays behind the mat.
        XCTAssertEqual(tall.windows[0].box.minX, 16, accuracy: 0.5)
        XCTAssertEqual(framed.windows[0].box.maxY, 1176, accuracy: 0.5)
        // "Opis": one close-up and the text where the second one was.
        var description = fit
        description.fit = "description"
        let text = DemoFraming.plan(CGSize(width: 800, height: 1200), canvas: canvas, presentation: description, caption: true, crops: nil)
        XCTAssertEqual(text.fit, "description")
        XCTAssertEqual(text.windows.map(\.role), ["picture", "detail"])
        XCTAssertNil(text.captionAt)
        XCTAssertGreaterThan(text.textRect?.minY ?? 0, text.windows[1].rect.maxY)
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

    func testQuadMappingHitsTheCorners() throws {
        let corners = [
            CGPoint(x: 0.13, y: 0.25), CGPoint(x: 0.88, y: 0.27),
            CGPoint(x: 0.87, y: 0.84), CGPoint(x: 0.12, y: 0.87),
        ]
        let map = try XCTUnwrap(QuadMapping(corners: corners))
        let unit = [CGPoint(x: 0, y: 0), CGPoint(x: 1, y: 0), CGPoint(x: 1, y: 1), CGPoint(x: 0, y: 1)]
        for (u, corner) in zip(unit, corners) {
            XCTAssertEqual(map(u).x, corner.x, accuracy: 1e-9)
            XCTAssertEqual(map(u).y, corner.y, accuracy: 1e-9)
        }
        XCTAssertNil(QuadMapping(corners: Array(repeating: CGPoint(x: 0.5, y: 0.5), count: 4)))
    }

    func testChartGeometryMatchesTheServerChart() {
        // testchart.palette_patches: margin 200, gap 60, 680 × 490 px patches.
        let first = ChartGeometry.patches[0]
        XCTAssertEqual(first.minX * 2560, 200, accuracy: 0.01)
        XCTAssertEqual(first.width * 2560, 680, accuracy: 0.01)
        XCTAssertEqual(ChartGeometry.patches[5].maxY * 1440, 200 + 490 + 60 + 490, accuracy: 0.01)
    }

    func testDemoCalibration() async throws {
        let demo = DemoBackend()
        let before = try await demo.calibration()
        XCTAssertFalse(before.calibrated)
        let result = try await demo.measureCalibration(photo: Data(), corners: [])
        XCTAssertEqual(result.inks.map(\.name), before.palette.colors.map(\.name))
        let applied = try await demo.applyCalibration(candidateID: result.candidateId)
        XCTAssertTrue(applied.calibrated)
        XCTAssertEqual(applied.palette.colors.first { $0.name == "black" }?.perceived, [18, 18, 21])
        let reset = try await demo.resetCalibration()
        XCTAssertFalse(reset.calibrated)
    }
}
