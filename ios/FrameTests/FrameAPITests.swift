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

    func testChosenModesAlwaysApply() {
        let canvas = DemoFraming.canvas("landscape")
        // A 16:9 picture on the 16:9 frame: no room beside it, so it gets smaller.
        for fit in ["details", "description"] {
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
