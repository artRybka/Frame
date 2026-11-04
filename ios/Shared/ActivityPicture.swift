import UIKit

/// A work's picture small enough to ride inside a Live Activity (the send
/// bar, a study being written): ActivityKit keeps a card's data, picture
/// included, under 4 KB, and a widget cannot fetch anything itself.
enum ActivityPicture {
    /// The JPEG's bytes at most, leaving room for the title and the state
    /// even as base64.
    static let maxBytes = 2_200
    /// Longest side in pixels, tried in turn until the JPEG fits.
    static let sides: [CGFloat] = [132, 112, 96, 80, 64]
    static let qualities: [CGFloat] = [0.6, 0.45, 0.3]

    static func data(from image: UIImage) -> Data? {
        for side in sides {
            let small = resized(image, longest: side)
            for quality in qualities {
                if let data = small.jpegData(compressionQuality: quality), data.count <= maxBytes {
                    return data
                }
            }
        }
        return nil
    }

    static func resized(_ image: UIImage, longest: CGFloat) -> UIImage {
        let pixels = CGSize(width: image.size.width * image.scale, height: image.size.height * image.scale)
        guard pixels.width > 0, pixels.height > 0 else { return image }
        let scale = min(1, longest / max(pixels.width, pixels.height))
        let size = CGSize(width: max(1, (pixels.width * scale).rounded()), height: max(1, (pixels.height * scale).rounded()))
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = true
        return UIGraphicsImageRenderer(size: size, format: format).image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
    }
}
