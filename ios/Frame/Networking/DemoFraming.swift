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
    }

    /// The wall text "Opis" prints on the mat (server: text.TextBlock).
    struct TextBlock: Hashable, Sendable {
        var title = ""
        var meta: [String] = []
        var body = ""
    }

    /// Crops for one orientation: chosen by the server's interest analysis
    /// for the demo works (DemoLibrary.json "framing"), or corrected by the user.
    struct Crops: Codable, Hashable, Sendable {
        var fill: Crop?
        var details: [Crop]?
        var detail: Crop?  // "description": its one close-up
    }

    struct Window {
        let rect: CGRect  // on the canvas
        let box: CGRect  // part of the picture shown, in its pixels
        let role: String  // "picture", "fill" or "detail"
        let crop: Crop?
    }

    struct Plan {
        let fit: String  // resolved: "fit", "fill", "details" or "description"
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
        let stem = stem(id)
        guard
            let url = Bundle.main.url(forResource: stem + "-ink", withExtension: "jpg")
                ?? Bundle.main.url(forResource: stem, withExtension: "jpg"),
            let image = UIImage(contentsOfFile: url.path)?.cgImage
        else { return nil }
        return CGSize(width: image.width, height: image.height)
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
            return room(size, canvas) >= 0.35 ? "details" : "fit"
        }
        if fit == "details" || fit == "description", room(size, canvas) < 0.2 { return "fit" }
        return fit
    }

    static func plan(
        _ size: CGSize, canvas: CGSize, presentation: Presentation, caption: Bool, crops: Crops?
    ) -> Plan {
        switch resolveFit(size, canvas: canvas, fit: presentation.fit) {
        case "fill":
            return planFill(size, canvas, caption, crops?.fill)
        case let fit where fit == "details" || fit == "description":
            if let plan = planBeside(size, canvas, fit, presentation.margin, caption, crops) { return plan }
            return planFit(size, canvas, presentation.margin, caption)
        default:
            return planFit(size, canvas, presentation.margin, caption)
        }
    }

    private static func planFit(_ size: CGSize, _ canvas: CGSize, _ margin: Double, _ caption: Bool) -> Plan {
        let pad = (min(canvas.width, canvas.height) * margin).rounded()
        let bottom = caption ? max(pad, captionBand(canvas)) : pad
        let availW = canvas.width - 2 * pad, availH = canvas.height - pad - bottom
        let scale = min(availW / size.width, availH / size.height)
        let w = max(1, (size.width * scale).rounded()), h = max(1, (size.height * scale).rounded())
        let rect = CGRect(x: ((canvas.width - w) / 2).rounded(.down), y: pad + ((availH - h) / 2).rounded(.down), width: w, height: h)
        let at = caption ? CGRect(x: rect.minX, y: rect.maxY + (captionSize(canvas) * 0.6).rounded(), width: w, height: captionSize(canvas) * 1.4) : nil
        return Plan(fit: "fit", canvas: canvas, windows: [Window(rect: rect, box: whole(size), role: "picture", crop: nil)], captionAt: at)
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

    /// "details": the whole picture edge to edge and two close-ups beside it;
    /// "description": one close-up and the text printed on the mat instead
    /// of the second.
    private static func planBeside(
        _ size: CGSize, _ canvas: CGSize, _ fit: String, _ margin: Double, _ caption: Bool, _ crops: Crops?
    ) -> Plan? {
        let (cw, ch) = (canvas.width, canvas.height)
        let short = min(cw, ch)
        let m = (short * max(margin, 0.04)).rounded()
        let text = fit == "description"
        let band = caption && !text ? captionBand(canvas) : 0
        let gap = (captionSize(canvas) * 0.6).rounded()
        let main: CGRect, rects: [CGRect], at: CGRect
        if size.width / size.height < cw / ch {  // picture at the left; the rest stacked
            let mainW = (ch * size.width / size.height).rounded()
            main = CGRect(x: 0, y: 0, width: mainW, height: ch)
            let winW = cw - mainW - 2 * m, winH = ((ch - 3 * m - band) / 2).rounded(.down)
            rects = [
                CGRect(x: mainW + m, y: m, width: winW, height: winH),
                CGRect(x: mainW + m, y: 2 * m + winH, width: winW, height: winH),
            ]
            at = CGRect(x: mainW + m, y: 2 * m + 2 * winH + gap, width: winW, height: captionSize(canvas) * 1.4)
        } else {  // picture on top; the rest side by side
            let mainH = (cw * size.height / size.width).rounded()
            main = CGRect(x: 0, y: 0, width: cw, height: mainH)
            let winW = ((cw - 3 * m) / 2).rounded(.down), winH = ch - mainH - 2 * m - band
            rects = [
                CGRect(x: m, y: mainH + m, width: winW, height: winH),
                CGRect(x: 2 * m + winW, y: mainH + m, width: winW, height: winH),
            ]
            at = CGRect(x: m, y: mainH + m + winH + gap, width: 2 * winW + m, height: captionSize(canvas) * 1.4)
        }
        guard let first = rects.first, min(first.width, first.height) >= 0.12 * short else { return nil }
        let aspect = first.width / first.height
        // Without the server's hints: a wider and a closer close-up, apart.
        let chosen: [Crop] = text
            ? [crops?.detail ?? Crop(x: 0.5, y: 0.35, zoom: 2.5)]
            : (crops?.details?.count == 2 ? crops?.details : nil)
                ?? [Crop(x: 0.5, y: 0.3, zoom: 1.5), Crop(x: 0.5, y: 0.75, zoom: 2.5)]
        var windows = [Window(rect: main, box: whole(size), role: "picture", crop: nil)]
        for (rect, crop) in zip(rects, chosen) {
            windows.append(Window(rect: rect, box: cropBox(size, aspect: aspect, crop: crop), role: "detail", crop: crop))
        }
        if text {
            return Plan(fit: "description", canvas: canvas, windows: windows, captionAt: nil, textRect: rects[1])
        }
        return Plan(fit: "details", canvas: canvas, windows: windows, captionAt: caption ? at : nil)
    }

    // MARK: Drawing (mat.py, caption.py)

    /// The mats as the server's preview shows them (paper white = screen white).
    static func matColor(_ name: String) -> UIColor {
        switch name {
        case "cream": UIColor(red: 0.98, green: 0.96, blue: 0.89, alpha: 1)
        case "grey": UIColor(white: 0.68, alpha: 1)
        case "black": UIColor(white: 0.1, alpha: 1)
        default: .white
        }
    }

    /// File URL of the framed preview; rendered once per framing and cached.
    static func framed(_ id: String, art: Art, settings: FrameSettings, crops: Crops?) -> URL? {
        let pres = art.isPhoto ? settings.photo : settings.art
        let stem = stem(id)
        let key = [settings.orientation, pres.key, art.caption, "\(art.text)", "\(String(describing: crops))"].joined(separator: "|")
        let directory = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("DemoFrames", isDirectory: true)
        let output = directory.appendingPathComponent("\(stem)-\(settings.orientation)-\(pres.fit)-\(fnv(key)).jpg")
        if FileManager.default.fileExists(atPath: output.path) { return output }
        guard
            let source = Bundle.main.url(forResource: stem + "-ink", withExtension: "jpg")
                ?? Bundle.main.url(forResource: stem, withExtension: "jpg"),
            let image = UIImage(contentsOfFile: source.path), let cgImage = image.cgImage
        else { return nil }

        let size = canvas(settings.orientation)
        let pixels = CGSize(width: cgImage.width, height: cgImage.height)
        let layout = plan(pixels, canvas: size, presentation: pres, caption: pres.label && !art.caption.isEmpty, crops: crops)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = true
        let data = UIGraphicsImageRenderer(size: size, format: format).jpegData(withCompressionQuality: 0.85) { context in
            matColor(pres.mat).setFill()
            UIRectFill(CGRect(origin: .zero, size: size))
            for window in layout.windows {
                if let part = cgImage.cropping(to: window.box.integral) {
                    UIImage(cgImage: part).draw(in: window.rect)
                }
            }
            drawBevels(layout, board: matColor(pres.mat), in: context.cgContext)
            if let at = layout.captionAt {
                drawCaption(art.caption, in: at, canvas: size, white: pres.mat == "black")
            }
            if let rect = layout.textRect {
                drawText(art.text, in: rect, canvas: size, white: pres.mat == "black")
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

    /// 45° bevels cut in the board's colour, a little lighter at the bottom
    /// and right, darker at the top and left, and the mat's shadow on the
    /// picture under its top and left edges.
    private static func drawBevels(_ plan: Plan, board: UIColor, in context: CGContext) {
        let short = min(plan.canvas.width, plan.canvas.height)
        let b = max(2, (short * 0.006).rounded()), shadow = max(2, (short * 0.006).rounded())
        let lit = toward(board, 1, 0.2), shaded = toward(board, 0, 0.15)
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

    /// A museum wall text on the mat (text.py): serif title, the artist and
    /// date, a short rule, then as many whole sentences as fit.
    private static func drawText(_ block: TextBlock, in rect: CGRect, canvas: CGSize, white: Bool) {
        let short = min(canvas.width, canvas.height)
        let ink = white ? UIColor.white : UIColor(white: 0.1, alpha: 1)
        let serif = UIFontDescriptor.preferredFontDescriptor(withTextStyle: .body).withDesign(.serif)
        func serifFont(_ size: CGFloat, bold: Bool = false) -> UIFont {
            let descriptor = bold ? serif?.withSymbolicTraits(.traitBold) : serif
            return descriptor.map { UIFont(descriptor: $0, size: size) } ?? UIFont.systemFont(ofSize: size)
        }
        let title = serifFont((short * 0.04).rounded(), bold: true)
        let meta = UIFont.systemFont(ofSize: (short * 0.024).rounded())
        let body = serifFont((short * 0.024).rounded())

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
            draw(block.title, title, lines: 2, leading: 1.1)
            cursor += (short * 0.008).rounded()
        }
        for line in block.meta where !line.isEmpty {
            draw(line, meta, lines: 1, leading: 1.25)
        }
        let rule = max(1, (short * 0.0015).rounded())
        guard !block.body.isEmpty, cursor + rule + short * 0.05 < rect.maxY else { return }
        cursor += (short * 0.012).rounded()
        ink.setFill()
        UIRectFill(CGRect(x: rect.minX, y: cursor, width: (rect.width * 0.12).rounded(), height: rule))
        cursor += rule + (short * 0.016).rounded()

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
