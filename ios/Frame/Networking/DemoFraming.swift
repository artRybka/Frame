import UIKit

/// The demo's stand-in for the server's render: an artwork's e-paper look
/// (Resources/DemoImages/<stem>-ink.jpg, made by the server pipeline) placed
/// on the panel canvas the way the presentation settings say. Mirrors
/// server/src/frame_server/imaging/layout.py and caption.py.
enum DemoFraming {
    struct Art: Sendable {
        let caption: String
        let isPhoto: Bool
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

    /// Where the picture lands: fill (cover, cropped by the canvas) or fit
    /// (whole picture, `margin` of passe-partout); "auto" fills when the crop
    /// would be small.
    static func placement(
        _ image: CGSize, in canvas: CGSize, fit: String, margin: Double
    ) -> (fill: Bool, rect: CGRect) {
        let target = canvas.width / canvas.height
        let ratio = image.width / image.height
        let fill = fit == "fill" || (fit == "auto" && abs(ratio - target) / max(ratio, target) <= 0.12)
        if fill {
            let scale = max(canvas.width / image.width, canvas.height / image.height)
            let size = CGSize(width: image.width * scale, height: image.height * scale)
            return (
                true,
                CGRect(
                    x: (canvas.width - size.width) / 2, y: (canvas.height - size.height) / 2,
                    width: size.width, height: size.height
                )
            )
        }
        let pad = (min(canvas.width, canvas.height) * margin).rounded()
        let scale = min((canvas.width - 2 * pad) / image.width, (canvas.height - 2 * pad) / image.height)
        let size = CGSize(width: (image.width * scale).rounded(), height: (image.height * scale).rounded())
        return (
            false,
            CGRect(
                x: ((canvas.width - size.width) / 2).rounded(.down),
                y: ((canvas.height - size.height) / 2).rounded(.down),
                width: size.width, height: size.height
            )
        )
    }

    /// File URL of the framed preview; rendered once per framing and cached.
    static func framed(_ id: String, art: Art, settings: FrameSettings) -> URL? {
        let pres = art.isPhoto ? settings.photo : settings.art
        let stem = stem(id)
        let directory = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("DemoFrames", isDirectory: true)
        let output = directory.appendingPathComponent(
            "\(stem)-\(settings.orientation)-\(pres.fit)-\(pres.margin)-\(pres.label).jpg"
        )
        if FileManager.default.fileExists(atPath: output.path) { return output }
        guard
            let source = Bundle.main.url(forResource: stem + "-ink", withExtension: "jpg")
                ?? Bundle.main.url(forResource: stem, withExtension: "jpg"),
            let image = UIImage(contentsOfFile: source.path)
        else { return nil }

        let size = canvas(settings.orientation)
        let (fill, rect) = placement(image.size, in: size, fit: pres.fit, margin: pres.margin)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = true
        let data = UIGraphicsImageRenderer(size: size, format: format).jpegData(withCompressionQuality: 0.85) { _ in
            UIColor.white.setFill()  // paper white, as the server's adapted preview shows it
            UIRectFill(CGRect(origin: .zero, size: size))
            image.draw(in: rect)
            if pres.label, !art.caption.isEmpty {
                drawCaption(art.caption, canvas: size, picture: rect, onMat: !fill)
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

    /// Below the picture on a white passe-partout, right-aligned like a museum
    /// label; otherwise on a small white card in the bottom-right corner.
    private static func drawCaption(_ text: String, canvas: CGSize, picture: CGRect, onMat: Bool) {
        let size = max(9, (min(canvas.width, canvas.height) * 0.02).rounded())
        let pad = (size * 0.6).rounded()
        let style = NSMutableParagraphStyle()
        style.lineBreakMode = .byTruncatingTail
        let attributes: [NSAttributedString.Key: Any] = [
            .font: UIFont.systemFont(ofSize: size),
            .foregroundColor: UIColor.black,
            .paragraphStyle: style,
        ]
        let line = text as NSString
        let natural = line.size(withAttributes: attributes)
        if onMat, canvas.height - picture.maxY >= size * 2 {
            let width = min(natural.width, picture.width)
            line.draw(
                in: CGRect(x: picture.maxX - width, y: picture.maxY + pad, width: width, height: natural.height),
                withAttributes: attributes
            )
        } else {
            let width = min(natural.width, canvas.width * 0.6)
            let card = CGRect(
                x: canvas.width - 2 * pad - width - 2 * pad,
                y: canvas.height - 2 * pad - natural.height - 2 * pad,
                width: width + 2 * pad, height: natural.height + 2 * pad
            )
            UIColor.white.setFill()
            UIRectFill(card)
            line.draw(in: card.insetBy(dx: pad, dy: pad), withAttributes: attributes)
        }
    }
}
