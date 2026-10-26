import ImageIO
import UIKit

/// A photo from the camera roll, ready to add to the library: an upright
/// JPEG plus the date and place read from its EXIF before re-encoding drops them.
struct PhotoUpload: Sendable {
    var data: Data
    var title: String
    var takenAt: String?  // ISO 8601, the camera's local time
    var latitude: Double?
    var longitude: Double?
    /// Sent once ("Zdjęcie na ramkę"): shown with this look, outside the library's lists.
    var look: Look?

    init(data: Data, title: String = "", takenAt: String? = nil, latitude: Double? = nil, longitude: Double? = nil) {
        self.data = data
        self.title = title
        self.takenAt = takenAt
        self.latitude = latitude
        self.longitude = longitude
    }

    /// From the original file (HEIC or JPEG, as the photo picker gives it).
    init(original: Data, title: String = "") {
        var takenAt: String?
        var latitude: Double?
        var longitude: Double?
        if let source = CGImageSourceCreateWithData(original as CFData, nil),
           let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any] {
            let exif = properties[kCGImagePropertyExifDictionary] as? [CFString: Any]
            if let stamp = exif?[kCGImagePropertyExifDateTimeOriginal] as? String {
                takenAt = Self.iso(exif: stamp)
            }
            if let gps = properties[kCGImagePropertyGPSDictionary] as? [CFString: Any],
               let lat = gps[kCGImagePropertyGPSLatitude] as? Double,
               let lon = gps[kCGImagePropertyGPSLongitude] as? Double {
                latitude = (gps[kCGImagePropertyGPSLatitudeRef] as? String) == "S" ? -lat : lat
                longitude = (gps[kCGImagePropertyGPSLongitudeRef] as? String) == "W" ? -lon : lon
            }
        }
        self.init(data: Self.jpeg(original), title: title, takenAt: takenAt, latitude: latitude, longitude: longitude)
    }

    /// "2026:07:01 10:00:00" → "2026-07-01T10:00:00".
    static func iso(exif stamp: String) -> String? {
        let parts = stamp.split(separator: " ")
        guard parts.count == 2 else { return nil }
        let date = parts[0].replacingOccurrences(of: ":", with: "-")
        return date.count == 10 ? "\(date)T\(parts[1])" : nil
    }

    /// HEIC and huge originals → an upright JPEG of a sensible size (the
    /// frame shows 2560 px at most).
    static func jpeg(_ data: Data, maxSide: CGFloat = 3000) -> Data {
        guard let image = UIImage(data: data) else { return data }
        let scale = min(1, maxSide / max(image.size.width, image.size.height))
        let size = CGSize(width: (image.size.width * scale).rounded(), height: (image.size.height * scale).rounded())
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1  // pixels, not points × the screen's scale
        let rendered = UIGraphicsImageRenderer(size: size, format: format).image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
        return rendered.jpegData(compressionQuality: 0.9) ?? data
    }
}
