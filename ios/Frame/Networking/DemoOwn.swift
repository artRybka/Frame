import CoreImage
import CoreImage.CIFilterBuiltins
import UIKit

/// "Dodaj własne dzieło" in the demo: a photograph of a painting hanging on
/// a wall, taken a little from the side, put together here from a bundled
/// picture (no photograph of anyone's home in the app), and the work cut out
/// of a photograph as the server does it.
enum DemoOwn {
    /// The painting on the wall: Monet's "Cliff Walk at Pourville".
    static let paintingID = "aic:14620"
    static let size = CGSize(width: 1200, height: 1600)
    /// The frame's outer edge and the painting's, as fractions of the
    /// photograph (top-left, top-right, bottom-right, bottom-left).
    static let outer: [[Double]] = [[0.13, 0.27], [0.88, 0.245], [0.895, 0.735], [0.12, 0.75]]
    static let work: [[Double]] = [[0.185, 0.315], [0.825, 0.295], [0.837, 0.69], [0.177, 0.705]]

    private static let context = CIContext()

    /// The photograph, as the camera would give it; `glare`: the glass's
    /// reflection on it (without: as two shots merged would give it).
    static func photo(glare withGlare: Bool = true) -> UIImage? {
        guard let url = Bundle.main.url(forResource: DemoFraming.stem(paintingID), withExtension: "jpg"),
              let painting = CIImage(contentsOf: url)
        else { return nil }
        let w = size.width, h = size.height
        // CI's origin is bottom left.
        func point(_ p: [Double]) -> CGPoint { CGPoint(x: p[0] * w, y: (1 - p[1]) * h) }
        let renderer = UIGraphicsImageRenderer(size: size, format: { let f = UIGraphicsImageRendererFormat(); f.scale = 1; return f }())
        let wall = renderer.image { ctx in
            let cg = ctx.cgContext
            // A warm wall lit from the upper left, a skirting of shadow below.
            let colours = [UIColor(red: 0.93, green: 0.90, blue: 0.84, alpha: 1).cgColor,
                           UIColor(red: 0.80, green: 0.76, blue: 0.69, alpha: 1).cgColor] as CFArray
            if let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colours, locations: [0, 1]) {
                cg.drawRadialGradient(gradient, startCenter: CGPoint(x: w * 0.25, y: h * 0.1), startRadius: 0,
                                      endCenter: CGPoint(x: w * 0.4, y: h * 0.4), endRadius: h * 1.05, options: .drawsAfterEndLocation)
            }
            // The frame's shadow on the wall, then the frame.
            func quad(_ q: [[Double]], dx: Double = 0, dy: Double = 0) -> UIBezierPath {
                let path = UIBezierPath()
                path.move(to: CGPoint(x: q[0][0] * w + dx, y: q[0][1] * h + dy))
                for p in q.dropFirst() { path.addLine(to: CGPoint(x: p[0] * w + dx, y: p[1] * h + dy)) }
                path.close()
                return path
            }
            cg.saveGState()
            cg.setShadow(offset: CGSize(width: 14, height: 22), blur: 30, color: UIColor.black.withAlphaComponent(0.35).cgColor)
            UIColor(red: 0.36, green: 0.25, blue: 0.15, alpha: 1).setFill()
            quad(outer).fill()
            cg.restoreGState()
            // A gilt lip inside the frame.
            UIColor(red: 0.72, green: 0.58, blue: 0.33, alpha: 1).setFill()
            let lip = zip(outer, work).map { o, i in [i[0] + (o[0] - i[0]) * 0.28, i[1] + (o[1] - i[1]) * 0.28] }
            quad(lip).fill()
        }
        guard let wallCI = CIImage(image: wall) else { return nil }
        let warp = CIFilter.perspectiveTransform()
        warp.inputImage = painting
        warp.topLeft = point(work[0])
        warp.topRight = point(work[1])
        warp.bottomRight = point(work[2])
        warp.bottomLeft = point(work[3])
        guard let placed = warp.outputImage else { return nil }
        // The glass's reflection: a soft pale streak across the upper right.
        let glare = CIFilter.radialGradient()
        glare.center = CGPoint(x: w * 0.7, y: h * 0.62)
        glare.radius0 = 0
        glare.radius1 = Float(w * 0.22)
        glare.color0 = CIColor(red: 1, green: 1, blue: 1, alpha: 0.28)
        glare.color1 = CIColor(red: 1, green: 1, blue: 1, alpha: 0)
        var out = placed.composited(over: wallCI)
        if withGlare, let light = glare.outputImage?.cropped(to: wallCI.extent) { out = light.composited(over: out) }
        guard let cg = context.createCGImage(out, from: wallCI.extent) else { return nil }
        return UIImage(cgImage: cg)
    }

    /// The work inside `corners` of `image`, upright (the server's `warp`).
    static func cut(_ image: UIImage, corners: [[Double]]?, own: OwnWork?) -> UIImage {
        OwnPicture.cut(image, corners: corners, own: own)
    }

    /// The demo's photograph: the work found where it was put.
    static func isDemoPhoto(_ image: UIImage) -> Bool {
        abs(image.size.width - size.width) < 1 && abs(image.size.height - size.height) < 1
    }

    static let hints = OwnHints(
        signature: "Claude Monet 82", artist: "Claude Monet", date: "1882", technique: "oil",
        support: "canvas", title: "Spacer po klifie", sure: true
    )
}
