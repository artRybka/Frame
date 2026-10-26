import UIKit

/// The demo's stand-in for the server's render: an artwork's e-paper look
/// (Resources/DemoImages/<stem>-ink.jpg, made by the server pipeline) laid
/// out on the panel canvas as the presentation settings say. Mirrors
/// server/src/frame_server/imaging/layout.py (plan_layout), mat.py,
/// caption.py and text.py, without the dithering.
enum DemoFraming {
    struct Art: Sendable {
        let caption: String
        let text: TextBlock
        let isPhoto: Bool
        var tint: UIColor?  // the "picture" mat, as the server picks it
        var darkTint: UIColor?  // and the "picture_dark" one
    }

    /// The wall text "Opis" prints on the mat (server: text.TextBlock).
    struct TextBlock: Hashable, Sendable {
        var title = ""
        var meta: [String] = []
        var body = ""
    }

    /// Crops for one orientation: chosen by the server's interest analysis
    /// for the demo works (DemoLibrary.json "framing"), or corrected by the user.
    typealias Crops = FramingCrops

    struct Window {
        let rect: CGRect  // on the canvas
        let box: CGRect  // part of the picture shown, in its pixels
        let role: String  // "picture", "fill" or "detail"
        let crop: Crop?
    }

    struct Plan {
        let fit: String  // resolved: "fit", "fill" or "description"
        let canvas: CGSize
        let windows: [Window]
        let captionAt: CGRect?  // right-aligned within; origin = top-left of the line
        var textRect: CGRect?  // "description": where the text is printed on the mat
    }

    /// The panel canvas at half resolution (the frame is 2560×1440).
    static func canvas(_ orientation: String) -> CGSize {
        orientation == "portrait" ? CGSize(width: 720, height: 1280) : CGSize(width: 1280, height: 720)
    }

    static func stem(_ id: String) -> String {
        id.replacingOccurrences(of: ":", with: "_").replacingOccurrences(of: "/", with: "_")
    }

    /// Museum-label text, as the server's `caption_for`.
    static func caption(for item: Item) -> String {
        if item.kind == .photo {
            return [item.dateText, item.photo?.caption ?? ""].filter { !$0.isEmpty }
                .joined(separator: " · ")
        }
        let text = [item.artist, item.title].filter { !$0.isEmpty }.joined(separator: " — ")
        return item.dateText.isEmpty ? text : "\(text), \(item.dateText)"
    }

    /// What "Opis" prints, as the server's `text_block_for`.
    static func textBlock(for item: Item) -> TextBlock {
        if item.kind == .photo {
            let title = (item.photo?.caption).flatMap { $0.isEmpty ? nil : $0 } ?? item.title
            let when = item.dateText.isEmpty ? String((item.photo?.takenAt ?? "").prefix(10)) : item.dateText
            return TextBlock(title: title, meta: [when, item.photo?.contributor ?? ""].filter { !$0.isEmpty })
        }
        let detail = [item.dateText, item.medium].filter { !$0.isEmpty }.joined(separator: " · ")
        let body = item.description.isEmpty
            ? [item.museum, item.credit].filter { !$0.isEmpty }.joined(separator: ", ")
            : item.description
        return TextBlock(title: item.title, meta: [item.artist, detail].filter { !$0.isEmpty }, body: body)
    }

    /// Pixel size of the image the demo frames (the e-paper look, else the original).
    static func pixelSize(_ id: String) -> CGSize? {
        guard let url = source(id), let image = UIImage(contentsOfFile: url.path)?.cgImage else { return nil }
        return CGSize(width: image.width, height: image.height)
    }

    /// The image the demo frames: the bundled e-paper look, else the bundled
    /// original, else a photo uploaded in this demo session.
    static func source(_ id: String) -> URL? {
        let stem = stem(id)
        if let url = Bundle.main.url(forResource: stem + "-ink", withExtension: "jpg")
            ?? Bundle.main.url(forResource: stem, withExtension: "jpg") {
            return url
        }
        let upload = uploadURL(id)
        return FileManager.default.fileExists(atPath: upload.path) ? upload : nil
    }

    /// Where the demo keeps a photo "uploaded" from the camera roll.
    static func uploadURL(_ id: String) -> URL {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("DemoUploads", isDirectory: true)
            .appendingPathComponent(stem(id) + ".jpg")
    }

    /// The dark mat from the light one, where the server's is not known: the
    /// same hue, deep and muted.
    static func deep(_ tint: UIColor) -> UIColor {
        var hue: CGFloat = 0, saturation: CGFloat = 0, brightness: CGFloat = 0, alpha: CGFloat = 0
        tint.getHue(&hue, saturation: &saturation, brightness: &brightness, alpha: &alpha)
        return UIColor(hue: hue, saturation: min(0.1 + saturation * 1.5, 0.35), brightness: 0.25, alpha: 1)
    }

    /// A rough stand-in for the server's picture tint (mat.picture_tint), for
    /// photos uploaded in the demo: the average hue, pale.
    static func tint(of image: CGImage) -> UIColor {
        var pixel = [UInt8](repeating: 0, count: 4)
        let space = CGColorSpaceCreateDeviceRGB()
        pixel.withUnsafeMutableBytes { buffer in
            guard let context = CGContext(
                data: buffer.baseAddress, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 4,
                space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
            ) else { return }
            context.interpolationQuality = .medium
            context.draw(image, in: CGRect(x: 0, y: 0, width: 1, height: 1))
        }
        let average = UIColor(red: CGFloat(pixel[0]) / 255, green: CGFloat(pixel[1]) / 255, blue: CGFloat(pixel[2]) / 255, alpha: 1)
        var hue: CGFloat = 0, saturation: CGFloat = 0, brightness: CGFloat = 0, alpha: CGFloat = 0
        average.getHue(&hue, saturation: &saturation, brightness: &brightness, alpha: &alpha)
        return UIColor(hue: hue, saturation: min(saturation * 0.3, 0.16), brightness: 0.93, alpha: 1)
    }

    // MARK: Planning (layout.py)

    static func captionSize(_ canvas: CGSize) -> CGFloat {
        max(9, (min(canvas.width, canvas.height) * 0.02).rounded())
    }

    static func captionBand(_ canvas: CGSize) -> CGFloat {
        (captionSize(canvas) * 2.6).rounded()
    }

    /// The picture in a mat window: its outermost edge stays behind the mat
    /// (layout.whole, PICTURE_TRIM).
    static func whole(_ size: CGSize) -> CGRect {
        CGRect(origin: .zero, size: size).insetBy(dx: size.width * 0.02, dy: size.height * 0.02)
    }

    static func cropBox(_ size: CGSize, aspect: CGFloat, crop: Crop) -> CGRect {
        var w = size.width, h = size.height
        if size.width / size.height > aspect { w = size.height * aspect } else { h = size.width / aspect }
        w /= crop.zoom
        h /= crop.zoom
        let cx = min(max(crop.x * size.width, w / 2), size.width - w / 2)
        let cy = min(max(crop.y * size.height, h / 2), size.height - h / 2)
        return CGRect(x: cx - w / 2, y: cy - h / 2, width: w, height: h)
    }

    /// Canvas share left beside the picture at full height (or width).
    private static func room(_ size: CGSize, _ canvas: CGSize) -> CGFloat {
        let ratio = size.width / size.height
        if ratio < canvas.width / canvas.height { return 1 - canvas.height * ratio / canvas.width }
        return 1 - canvas.width / ratio / canvas.height
    }

    static func resolveFit(_ size: CGSize, canvas: CGSize, fit: String) -> String {
        let ratio = size.width / size.height, target = canvas.width / canvas.height
        if fit == "auto" {
            if abs(ratio - target) / max(ratio, target) <= 0.12 { return "fill" }
            return room(size, canvas) >= 0.35 ? "description" : "fit"
        }
        return fit
    }

    static func plan(
        _ size: CGSize, canvas: CGSize, presentation: Presentation, caption: Bool, crops: Crops?
    ) -> Plan {
        switch resolveFit(size, canvas: canvas, fit: presentation.fit) {
        case "fill":
            return planFill(size, canvas, caption, crops?.fill)
        case "description":
            if let plan = planDescription(size, canvas, presentation.margin, crops) { return plan }
            return planFit(size, canvas, presentation.margin, caption, crops?.fit)
        default:
            return planFit(size, canvas, presentation.margin, caption, crops?.fit)
        }
    }

    /// "Passe-partout" uncropped: `whole` as a crop (layout.WHOLE).
    static let wholeCrop = Crop(zoom: 1 / (1 - 2 * 0.02))

    private static func fitted(_ aspect: CGFloat, _ availW: CGFloat, _ availH: CGFloat) -> CGSize {
        if availW / availH > aspect { return CGSize(width: max(1, (availH * aspect).rounded()), height: availH) }
        return CGSize(width: availW, height: max(1, (availW / aspect).rounded()))
    }

    /// "Passe-partout": where the mat window may go (layout.fit_area).
    static func fitArea(_ canvas: CGSize, margin: Double, caption: Bool) -> CGRect {
        let pad = (min(canvas.width, canvas.height) * margin).rounded()
        let bottom = caption ? max(pad, captionBand(canvas)) : pad
        return CGRect(x: pad, y: pad, width: canvas.width - 2 * pad, height: canvas.height - pad - bottom)
    }

    /// The picture in one mat window: whole, or cropped to any shape.
    private static func planFit(_ size: CGSize, _ canvas: CGSize, _ margin: Double, _ caption: Bool, _ crop: Crop?) -> Plan {
        let chosen = crop ?? wholeCrop
        let aspect = chosen.aspect.map { CGFloat($0) } ?? size.width / size.height
        let area = fitArea(canvas, margin: margin, caption: caption)
        let pad = area.minY, availW = area.width, availH = area.height
        let sized = fitted(aspect, availW, availH)
        let rect = CGRect(
            x: ((canvas.width - sized.width) / 2).rounded(.down), y: pad + ((availH - sized.height) / 2).rounded(.down),
            width: sized.width, height: sized.height
        )
        let at = caption ? CGRect(x: rect.minX, y: rect.maxY + (captionSize(canvas) * 0.6).rounded(), width: rect.width, height: captionSize(canvas) * 1.4) : nil
        let window = Window(rect: rect, box: cropBox(size, aspect: aspect, crop: chosen), role: "picture", crop: chosen)
        return Plan(fit: "fit", canvas: canvas, windows: [window], captionAt: at)
    }

    private static func planFill(_ size: CGSize, _ canvas: CGSize, _ caption: Bool, _ crop: Crop?) -> Plan {
        let band = caption ? captionBand(canvas) : 0
        let rect = CGRect(x: 0, y: 0, width: canvas.width, height: canvas.height - band)
        let aspect = rect.width / rect.height
        let chosen = crop ?? Crop()
        var at: CGRect?
        if caption {
            let pad = (min(canvas.width, canvas.height) * 0.03).rounded()
            let top = rect.maxY + ((band - (captionSize(canvas) * 1.2).rounded()) / 2).rounded(.down)
            at = CGRect(x: pad, y: top, width: canvas.width - 2 * pad, height: captionSize(canvas) * 1.4)
        }
        let window = Window(rect: rect, box: cropBox(size, aspect: aspect, crop: chosen), role: "fill", crop: chosen)
        return Plan(fit: "fill", canvas: canvas, windows: [window], captionAt: at)
    }

    /// The close-up as close as the source's pixels allow, and at least 1.8×
    /// the picture beside it, shown at `picture` canvas points per source
    /// pixel (layout.detail_zoom).
    static func detailZoom(_ size: CGSize, aspect: CGFloat, windowWidth: CGFloat, picture: CGFloat) -> CGFloat {
        let cover = min(size.width, size.height * aspect)
        // The demo's canvas is half the panel's: its window half as wide.
        let closest = cover * 1.6 / (windowWidth * 2)
        let least = 1.8 * picture * cover / windowWidth
        return min(max(1.5, min(3, closest), least), 8)
    }

    /// "description": the picture, a close-up beside it and the text printed
    /// on the mat. Picture at the left or on top, whichever shows it larger;
    /// smaller, in a mat window, when the frame has its own shape. Its crop
    /// moves and zooms it in a window of its own shape (layout._plan_description).
    private static func planDescription(_ size: CGSize, _ canvas: CGSize, _ margin: Double, _ crops: Crops?) -> Plan? {
        let options = [true, false].compactMap { beside(size, canvas, margin, side: $0) }
        guard let best = options.max(by: { $0.0.width * $0.0.height < $1.0.width * $1.0.height }) else { return nil }
        let (main, rects) = best
        let shown = crops?.picture ?? wholeCrop
        let box = crops?.picture.map { cropBox(size, aspect: main.width / main.height, crop: $0) } ?? whole(size)
        let aspect = rects[0].width / rects[0].height
        // Without the server's hint: the upper middle, close enough.
        let zoom = detailZoom(size, aspect: aspect, windowWidth: rects[0].width, picture: main.width / box.width)
        let detail = crops?.detail ?? Crop(x: 0.5, y: 0.35, zoom: zoom)
        let windows = [
            Window(rect: main, box: box, role: "picture", crop: shown),
            Window(rect: rects[0], box: cropBox(size, aspect: aspect, crop: detail), role: "detail", crop: detail),
        ]
        return Plan(fit: "description", canvas: canvas, windows: windows, captionAt: nil, textRect: rects[1])
    }

    /// One arrangement: the picture, then the close-up and the text beside it.
    private static func beside(_ size: CGSize, _ canvas: CGSize, _ margin: Double, side: Bool) -> (CGRect, [CGRect])? {
        let (cw, ch) = (canvas.width, canvas.height)
        let short = min(cw, ch)
        let m = (short * max(margin, 0.04)).rounded()
        let share: CGFloat = 0.33
        let ratio = size.width / size.height
        let main: CGRect, rects: [CGRect]
        if side {  // picture at the left; the rest stacked in a column at the right
            let fullW = (ch * ratio).rounded()
            let col: CGRect
            if cw - fullW >= cw * share {
                main = CGRect(x: 0, y: 0, width: fullW, height: ch)
                col = CGRect(x: fullW + m, y: m, width: cw - fullW - 2 * m, height: ch - 2 * m)
            } else {  // in a mat window, as large as leaves the column 0.4 of the short side
                let availH = ch - 2 * m
                let sized = fitted(ratio, cw - 3 * m - (short * 0.4).rounded(), availH)
                let colW = cw - 3 * m - sized.width
                let y = m + ((availH - sized.height) / 2).rounded(.down)
                main = CGRect(x: m, y: y, width: sized.width, height: sized.height)
                col = CGRect(x: m + sized.width + m, y: y, width: colW, height: sized.height)
            }
            let winH = ((col.height - m) / 2).rounded(.down)
            rects = [
                CGRect(x: col.minX, y: col.minY, width: col.width, height: winH),
                CGRect(x: col.minX, y: col.minY + winH + m, width: col.width, height: col.height - winH - m),
            ]
        } else {  // picture on top; the rest side by side in a row below
            let fullH = (cw / ratio).rounded()
            let row: CGRect
            if ch - fullH >= ch * share {
                main = CGRect(x: 0, y: 0, width: cw, height: fullH)
                row = CGRect(x: m, y: fullH + m, width: cw - 2 * m, height: ch - fullH - 2 * m)
            } else {  // in a mat window, as large as leaves the row 0.2 of the short side
                let sized = fitted(ratio, cw - 2 * m, ch - 3 * m - (short * 0.2).rounded())
                let rowH = ch - 3 * m - sized.height
                let x = ((cw - sized.width) / 2).rounded(.down)
                main = CGRect(x: x, y: m, width: sized.width, height: sized.height)
                row = CGRect(x: x, y: m + sized.height + m, width: sized.width, height: rowH)
            }
            let winW = ((row.width - m) / 2).rounded(.down)
            rects = [
                CGRect(x: row.minX, y: row.minY, width: winW, height: row.height),
                CGRect(x: row.minX + winW + m, y: row.minY, width: row.width - winW - m, height: row.height),
            ]
        }
        guard min(rects[0].width, rects[0].height) >= 0.12 * short else { return nil }
        return (main, rects)
    }

    // MARK: Drawing (mat.py, caption.py)

    /// The mats as the server's preview shows them: nominal colours, the
    /// correction for the inks is left to the panel's image.
    static func matColor(_ name: String) -> UIColor {
        switch name {
        case "cream": UIColor(red: 1, green: 0.973, blue: 0.855, alpha: 1)
        case "grey": UIColor(white: 0.68, alpha: 1)
        case "black": .black
        default: .white
        }
    }

    /// File URL of the framed preview; rendered once per framing and cached.
    static func framed(_ id: String, art: Art, settings: FrameSettings, crops: Crops?) -> URL? {
        let pres = art.isPhoto ? settings.photo : settings.art
        let stem = stem(id)
        let board = switch pres.mat {
        case "picture": art.tint ?? matColor("cream")
        case "picture_dark": art.darkTint ?? deep(art.tint ?? matColor("cream"))
        default: matColor(pres.mat)
        }
        let key = [settings.orientation, pres.key, art.caption, "\(art.text)", "\(board)", "\(String(describing: crops))"].joined(separator: "|")
        let directory = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("DemoFrames", isDirectory: true)
        let output = directory.appendingPathComponent("\(stem)-\(settings.orientation)-\(pres.fit)-\(fnv(key)).jpg")
        if FileManager.default.fileExists(atPath: output.path) { return output }
        guard let source = source(id), let image = UIImage(contentsOfFile: source.path), let cgImage = image.cgImage
        else { return nil }
        let white = isDark(board)

        let size = canvas(settings.orientation)
        let pixels = CGSize(width: cgImage.width, height: cgImage.height)
        let layout = plan(pixels, canvas: size, presentation: pres, caption: pres.label && !art.caption.isEmpty, crops: crops)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = true
        let data = UIGraphicsImageRenderer(size: size, format: format).jpegData(withCompressionQuality: 0.85) { context in
            board.setFill()
            UIRectFill(CGRect(origin: .zero, size: size))
            for window in layout.windows {
                if let part = cgImage.cropping(to: window.box.integral) {
                    UIImage(cgImage: part).draw(in: window.rect)
                }
            }
            drawBevels(layout, board: board, whiteCore: pres.mat == "picture_dark", in: context.cgContext)
            if let at = layout.captionAt {
                drawCaption(art.caption, in: at, canvas: size, white: white)
            }
            if let rect = layout.textRect {
                drawText(art.text, in: rect, canvas: size, white: white)
            }
        }
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try data.write(to: output, options: .atomic)
        } catch {
            return nil
        }
        return output
    }

    /// 45° bevels cut in the board's colour (or a white core), a little
    /// lighter at the bottom and right, darker at the top and left, and the
    /// mat's shadow on the picture under its top and left edges.
    private static func drawBevels(_ plan: Plan, board: UIColor, whiteCore: Bool, in context: CGContext) {
        let short = min(plan.canvas.width, plan.canvas.height)
        let b = max(2, (short * 0.006).rounded()), shadow = max(2, (short * 0.006).rounded())
        let core = whiteCore ? UIColor.white : board
        let lit = whiteCore ? core : toward(core, 1, 0.2), shaded = toward(core, 0, whiteCore ? 0.18 : 0.15)
        for window in plan.windows {
            let r = window.rect
            let open = (
                left: r.minX > 0, top: r.minY > 0,
                right: r.maxX < plan.canvas.width, bottom: r.maxY < plan.canvas.height
            )
            func fill(_ points: [CGPoint], _ color: UIColor) {
                context.beginPath()
                context.addLines(between: points)
                context.closePath()
                context.setFillColor(color.cgColor)
                context.fillPath()
            }
            if open.top {
                fill([CGPoint(x: r.minX - b, y: r.minY - b), CGPoint(x: r.maxX + b, y: r.minY - b), CGPoint(x: r.maxX, y: r.minY), CGPoint(x: r.minX, y: r.minY)], shaded)
            }
            if open.left {
                fill([CGPoint(x: r.minX - b, y: r.minY - b), CGPoint(x: r.minX, y: r.minY), CGPoint(x: r.minX, y: r.maxY), CGPoint(x: r.minX - b, y: r.maxY + b)], shaded)
            }
            if open.bottom {
                fill([CGPoint(x: r.minX, y: r.maxY), CGPoint(x: r.maxX, y: r.maxY), CGPoint(x: r.maxX + b, y: r.maxY + b), CGPoint(x: r.minX - b, y: r.maxY + b)], lit)
            }
            if open.right {
                fill([CGPoint(x: r.maxX, y: r.minY), CGPoint(x: r.maxX + b, y: r.minY - b), CGPoint(x: r.maxX + b, y: r.maxY + b), CGPoint(x: r.maxX, y: r.maxY)], lit)
            }
            let colors = [UIColor.black.withAlphaComponent(0.22).cgColor, UIColor.black.withAlphaComponent(0).cgColor] as CFArray
            guard let gradient = CGGradient(colorsSpace: nil, colors: colors, locations: [0, 1]) else { continue }
            context.saveGState()
            context.clip(to: r)
            if open.top {
                context.drawLinearGradient(gradient, start: CGPoint(x: r.minX, y: r.minY), end: CGPoint(x: r.minX, y: r.minY + shadow), options: [])
            }
            if open.left {
                context.drawLinearGradient(gradient, start: CGPoint(x: r.minX, y: r.minY), end: CGPoint(x: r.minX + shadow, y: r.minY), options: [])
            }
            context.restoreGState()
        }
    }

    /// "#rrggbb" as a colour.
    static func color(hex: String) -> UIColor? {
        guard hex.hasPrefix("#"), hex.count == 7, let value = UInt32(hex.dropFirst(), radix: 16) else { return nil }
        return UIColor(
            red: CGFloat((value >> 16) & 0xFF) / 255, green: CGFloat((value >> 8) & 0xFF) / 255,
            blue: CGFloat(value & 0xFF) / 255, alpha: 1
        )
    }

    /// Whether letters on this board should be white (mat.is_dark).
    static func isDark(_ color: UIColor) -> Bool {
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        color.getRed(&r, green: &g, blue: &b, alpha: &a)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.4
    }

    /// Each sRGB component part of the way to `target` (sRGB is roughly even
    /// to the eye, like the server's cube-root mix).
    private static func toward(_ color: UIColor, _ target: CGFloat, _ amount: CGFloat) -> UIColor {
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        color.getRed(&r, green: &g, blue: &b, alpha: &a)
        return UIColor(
            red: r + (target - r) * amount, green: g + (target - g) * amount,
            blue: b + (target - b) * amount, alpha: 1
        )
    }

    /// Right-aligned on the mat, like a museum label.
    private static func drawCaption(_ text: String, in rect: CGRect, canvas: CGSize, white: Bool) {
        let style = NSMutableParagraphStyle()
        style.alignment = .right
        style.lineBreakMode = .byTruncatingTail
        let attributes: [NSAttributedString.Key: Any] = [
            .font: UIFont.systemFont(ofSize: captionSize(canvas)),
            .foregroundColor: white ? UIColor.white : UIColor(white: 0.1, alpha: 1),
            .paragraphStyle: style,
        ]
        (text as NSString).draw(in: rect, withAttributes: attributes)
    }

    /// Split after . ! ? when the next word starts with a capital (text.sentences).
    static func sentences(_ text: String) -> [String] {
        let words = text.split(whereSeparator: \.isWhitespace).map(String.init)
        var out: [String] = []
        var current: [String] = []
        for word in words {
            let opening = word.drop(while: { "\"“(‘'".contains($0) })
            if let last = current.last, let end = last.last, ".!?".contains(end),
               opening.first?.isUppercase == true {
                out.append(current.joined(separator: " "))
                current = []
            }
            current.append(word)
        }
        if !current.isEmpty { out.append(current.joined(separator: " ")) }
        return out
    }

    /// A museum wall text on the mat (text.py): serif title (up to three
    /// lines), the artist and date, a short rule, then as many whole sentences as fit.
    private static func drawText(_ block: TextBlock, in full: CGRect, canvas: CGSize, white: Bool) {
        let short = min(canvas.width, canvas.height)
        // Lines of about 70 characters at most, like the server (MEASURE).
        let rect = CGRect(x: full.minX, y: full.minY, width: min(full.width, (short * 0.5).rounded()), height: full.height)
        let ink = white ? UIColor.white : UIColor(white: 0.1, alpha: 1)
        let serif = UIFontDescriptor.preferredFontDescriptor(withTextStyle: .body).withDesign(.serif)
        func serifFont(_ size: CGFloat, bold: Bool = false) -> UIFont {
            let descriptor = bold ? serif?.withSymbolicTraits(.traitBold) : serif
            return descriptor.map { UIFont(descriptor: $0, size: size) } ?? UIFont.systemFont(ofSize: size)
        }
        let title = serifFont((short * 0.03).rounded(), bold: true)
        let meta = UIFont.systemFont(ofSize: (short * 0.021).rounded())
        let body = serifFont((short * 0.015).rounded())

        var cursor = rect.minY
        func draw(_ text: String, _ font: UIFont, lines: Int, leading: CGFloat) {
            let style = NSMutableParagraphStyle()
            style.lineBreakMode = .byWordWrapping
            style.lineHeightMultiple = leading
            let attributes: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: ink, .paragraphStyle: style]
            let room = CGRect(x: rect.minX, y: cursor, width: rect.width, height: max(0, rect.maxY - cursor))
            // Half a line of slack: laid-out lines run a little taller than
            // lineHeight × multiple, and a box exactly n lines high holds n - 1.
            let limit = (CGFloat(lines) + 0.5) * font.lineHeight * leading
            let options: NSStringDrawingOptions = [.usesLineFragmentOrigin, .truncatesLastVisibleLine]
            let box = CGRect(origin: room.origin, size: CGSize(width: room.width, height: min(room.height, limit)))
            (text as NSString).draw(with: box, options: options, attributes: attributes, context: nil)
            let used = (text as NSString).boundingRect(with: box.size, options: options, attributes: attributes, context: nil)
            cursor += min(box.height, ceil(used.height))
        }
        if !block.title.isEmpty {
            draw(block.title, title, lines: 3, leading: 1.1)
            cursor += (short * 0.007).rounded()
        }
        for line in block.meta where !line.isEmpty {
            draw(line, meta, lines: 1, leading: 1.25)
        }
        let rule = max(1, (short * 0.001).rounded())
        guard !block.body.isEmpty, cursor + rule + short * 0.03 < rect.maxY else { return }
        cursor += (short * 0.008).rounded()
        ink.setFill()
        UIRectFill(CGRect(x: rect.minX, y: cursor, width: (rect.width * 0.12).rounded(), height: rule))
        cursor += rule + (short * 0.01).rounded()

        // As many whole sentences as fit; an ellipsis only if not even one does.
        let style = NSMutableParagraphStyle()
        style.lineHeightMultiple = 1.3
        let attributes: [NSAttributedString.Key: Any] = [.font: body, .foregroundColor: ink, .paragraphStyle: style]
        let space = CGSize(width: rect.width, height: max(0, rect.maxY - cursor))
        var chosen: [String] = []
        for sentence in sentences(block.body) {
            let candidate = (chosen + [sentence]).joined(separator: " ") as NSString
            let height = candidate.boundingRect(
                with: CGSize(width: space.width, height: .greatestFiniteMagnitude),
                options: .usesLineFragmentOrigin, attributes: attributes, context: nil
            ).height
            if height > space.height || candidate.length > 900 { break }
            chosen.append(sentence)
        }
        let text = chosen.isEmpty ? block.body : chosen.joined(separator: " ")
        (text as NSString).draw(
            with: CGRect(origin: CGPoint(x: rect.minX, y: cursor), size: space),
            options: [.usesLineFragmentOrigin, .truncatesLastVisibleLine], attributes: attributes, context: nil
        )
    }

    /// Stable short hash for cache file names.
    private static func fnv(_ text: String) -> String {
        var hash: UInt64 = 0xcbf2_9ce4_8422_2325
        for byte in text.utf8 {
            hash ^= UInt64(byte)
            hash = hash &* 0x100_0000_01b3
        }
        return String(hash, radix: 16)
    }
}
