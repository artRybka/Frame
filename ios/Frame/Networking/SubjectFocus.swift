import SwiftUI
import UIKit
import Vision

/// Where a picture's subject is, so a box of another shape crops around it
/// instead of through its middle: the faces in it, else what draws the eye
/// (Vision's attention saliency), else the middle. Worked out once per
/// picture and remembered.
///
/// Vision blocks its thread while it works, so it runs a couple of pictures
/// at a time on a queue of its own: on Swift's few shared threads a screen
/// of collages blocked them all, and with them every download in the app.
actor SubjectFocus {
    static let shared = SubjectFocus()

    private static let queue: OperationQueue = {
        let queue = OperationQueue()
        queue.name = "com.artrybka.frame.subject-focus"
        queue.maxConcurrentOperationCount = 2
        queue.qualityOfService = .userInitiated
        return queue
    }()

    /// The points worked out so far, by picture.
    private static let found = Found()

    /// The point already worked out for the picture under `key`, right
    /// now: a cover or tile drawn again (scrolled back into a lazy row)
    /// shows its picture from the first frame, already framed, instead of
    /// fading in from its placeholder each time (Mateusz 2026-11-07: the
    /// covers in Odkrywaj blinked while browsing).
    nonisolated static func known(_ key: String) -> UnitPoint? {
        found.point(key)
    }

    /// Unit point in the picture, origin top-left. Waits `patience` seconds
    /// at most, then gives the middle (the answer still comes in for next
    /// time); a picture scrolled away before its turn is skipped.
    ///
    /// With `near` (where Claude said the picture is about, the study of
    /// the day): the face by that point, Vision's boxes being exact where
    /// Claude's point is only roughly right (Homer's "Autumn" cut under
    /// the lady's chin, Mateusz 2026-11-23); no face there, the point.
    ///
    /// `subject`: the one thing the picture is of, for a cut much tighter
    /// than the picture (Galeria, Mateusz 2026-11-23: "Staraj się kadrować
    /// na temat"): the main faces; else the largest figure's head; else the
    /// most telling of the places that draw the eye, not all of them
    /// together (a middle between two of them is often empty). Of a
    /// subject much wider than the screen its middle says little (the ribs
    /// of Stubbs's tiger, the shaft of a cart; Mateusz 2026-11-26: "kadr
    /// obejmuje jego środek który nic nie mówi"): the cut goes to the part
    /// of it that draws the eye most (`telling`), and of faces too far
    /// apart for one screen to the largest and those beside it (`together`).
    ///
    /// `ahead` false: a picture fetched before it is shown (Galeria's
    /// stock for its grid). It waits for all that are on the screen: a
    /// hundred of them in the line held the tiles shown back till their
    /// patience ran out, and those were then cut about the middle, not as
    /// their pages are (the film of 2026-11-24).
    func point(
        in image: UIImage, key: String, near: UnitPoint? = nil, subject: Bool = false, patience: Double = 2.5,
        ahead: Bool = true
    ) async -> UnitPoint {
        let key = near.map { Self.key(key, near: $0) } ?? (subject ? key + "|subject" : key)
        if let cached = Self.found.point(key) { return cached }
        let fallback = near ?? .center
        let job = Job()
        let operation = BlockOperation {
            // Asked for twice (a tile, and the stock fetched ahead): found once.
            if let known = Self.found.point(key) { return job.finish(known) }
            let point = near.map { Self.find(in: image, near: $0) }
                ?? (subject ? Self.findSubject(in: image) : Self.find(in: image))
            Self.found.remember(point, for: key)
            job.finish(point)
        }
        if !ahead { operation.queuePriority = .low }
        return await withTaskCancellationHandler {
            await withCheckedContinuation { (continuation: CheckedContinuation<UnitPoint, Never>) in
                job.start(continuation)
                Self.queue.addOperation(operation)
                DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + patience) {
                    job.finish(fallback)
                }
            }
        } onCancel: {
            operation.cancel()
            job.finish(fallback)
        }
    }

    /// Where a point found near Claude's is remembered: apart from the
    /// picture's own (the same picture cropped elsewhere without it).
    nonisolated static func key(_ key: String, near: UnitPoint) -> String {
        String(format: "%@|near:%.3f,%.3f", key, near.x, near.y)
    }

    /// Readable from any thread (a view's body), apart from the actor.
    private final class Found: @unchecked Sendable {
        private let lock = NSLock()
        private var points: [String: UnitPoint] = [:]

        func point(_ key: String) -> UnitPoint? {
            lock.withLock { points[key] }
        }

        func remember(_ point: UnitPoint, for key: String) {
            lock.withLock { points[key] = point }
        }
    }

    /// One answer, from whichever comes first: Vision, the time limit or
    /// the view going away.
    private final class Job: @unchecked Sendable {
        private let lock = NSLock()
        private var continuation: CheckedContinuation<UnitPoint, Never>?
        private var answer: UnitPoint?

        func start(_ continuation: CheckedContinuation<UnitPoint, Never>) {
            lock.lock()
            if let answer {
                lock.unlock()
                continuation.resume(returning: answer)  // cancelled before it started
            } else {
                self.continuation = continuation
                lock.unlock()
            }
        }

        func finish(_ point: UnitPoint) {
            lock.lock()
            guard answer == nil else { return lock.unlock() }
            answer = point
            let waiting = continuation
            continuation = nil
            lock.unlock()
            waiting?.resume(returning: point)
        }
    }

    private static func find(in image: UIImage) -> UnitPoint {
        guard let cgImage = image.cgImage else { return .center }
        let faces = VNDetectFaceRectanglesRequest()
        let attention = VNGenerateAttentionBasedSaliencyImageRequest()
        let handler = VNImageRequestHandler(cgImage: cgImage, orientation: .up)
        try? handler.perform([faces, attention])

        // The main faces: a crowd's small ones would pull to an empty middle.
        let faceBoxes = (faces.results ?? []).filter { $0.confidence > 0.5 }.map(\.boundingBox)
        let largest = faceBoxes.map(\.area).max() ?? 0
        if let box = union(faceBoxes.filter { $0.area >= largest * 0.4 }) {
            return center(of: box)
        }
        let salient = (attention.results?.first?.salientObjects ?? []).filter { $0.confidence > 0.3 }
        if let box = union(salient.map(\.boundingBox)) {
            return center(of: box)
        }
        return .center
    }

    private static func findSubject(in image: UIImage) -> UnitPoint {
        guard let cgImage = image.cgImage else { return .center }
        let faces = VNDetectFaceRectanglesRequest()
        let people = VNDetectHumanRectanglesRequest()
        people.upperBodyOnly = false
        let attention = VNGenerateAttentionBasedSaliencyImageRequest()
        let handler = VNImageRequestHandler(cgImage: cgImage, orientation: .up)
        try? handler.perform([faces, people, attention])
        let faceBoxes = (faces.results ?? []).filter { $0.confidence > 0.5 }.map { topLeft($0.boundingBox) }
        let figures = (people.results ?? []).filter { $0.confidence > 0.5 }.map { topLeft($0.boundingBox) }
        let salient = (attention.results?.first?.salientObjects ?? [])
            .filter { $0.confidence > 0.3 }
            .map { (box: topLeft($0.boundingBox), weight: CGFloat($0.confidence)) }
        return subject(
            faces: faceBoxes, figures: figures, salient: salient,
            heat: (attention.results?.first).flatMap { Heat($0.pixelBuffer) },
            shape: CGFloat(cgImage.width) / CGFloat(max(cgImage.height, 1))
        )
    }

    /// Vision's map of what draws the eye in a picture: the whole picture
    /// on a small grid, rows from the top.
    struct Heat {
        let wide: Int
        let tall: Int
        let values: [Float]

        init(wide: Int, tall: Int, values: [Float]) {
            self.wide = wide
            self.tall = tall
            self.values = values
        }

        init?(_ buffer: CVPixelBuffer) {
            guard CVPixelBufferGetPixelFormatType(buffer) == kCVPixelFormatType_OneComponent32Float else { return nil }
            CVPixelBufferLockBaseAddress(buffer, .readOnly)
            defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
            let wide = CVPixelBufferGetWidth(buffer), tall = CVPixelBufferGetHeight(buffer)
            guard wide > 0, tall > 0, let base = CVPixelBufferGetBaseAddress(buffer) else { return nil }
            let stride = CVPixelBufferGetBytesPerRow(buffer)
            var values: [Float] = []
            values.reserveCapacity(wide * tall)
            for y in 0 ..< tall {
                let row = base.advanced(by: y * stride).assumingMemoryBound(to: Float32.self)
                values.append(contentsOf: UnsafeBufferPointer(start: row, count: wide))
            }
            self.init(wide: wide, tall: tall, values: values)
        }

        /// What each column (or each row) holds of the rows (columns)
        /// from `from` up to `to`, fractions of the picture.
        func sums(columns: Bool, from: CGFloat = 0, to: CGFloat = 1) -> [CGFloat] {
            let count = columns ? wide : tall, across = columns ? tall : wide
            let first = min(max(Int((from * CGFloat(across)).rounded(.down)), 0), across - 1)
            let last = min(max(Int((to * CGFloat(across)).rounded(.up)), first + 1), across)
            var sums = [CGFloat](repeating: 0, count: count)
            for along in 0 ..< count {
                for other in first ..< last {
                    let value = columns ? values[other * wide + along] : values[along * wide + other]
                    sums[along] += CGFloat(max(value, 0))
                }
            }
            return sums
        }
    }

    /// The shape of the screen a work fills in Galeria (and of its tile in
    /// the grid), width to height.
    static let screen: CGFloat = 0.46
    /// The part of a subject the cut moves to holds this much more of what
    /// draws the eye than the part about its middle; less, and the work is
    /// cut as it was.
    static let tells: CGFloat = 1.1
    /// Windows that hold this share of the best one's are as good as it.
    static let asGood: CGFloat = 0.98

    /// How much of a picture of `shape` (width to height) a screen filled
    /// by it shows, and whether it is the picture's width that is cut.
    static func seen(of shape: CGFloat) -> (share: CGFloat, sideways: Bool) {
        shape > screen ? (screen / max(shape, 0.01), true) : (max(shape, 0.01) / screen, false)
    }

    /// Where a screen filled by the picture is best cut: about `point`
    /// (the middle of what draws the eye), unless another part of the
    /// picture holds clearly more of it than a screen about `point` does.
    /// Then the middle of that part, and across it where its heat is.
    static func telling(_ heat: Heat, shape: CGFloat, from point: UnitPoint) -> UnitPoint {
        let (share, sideways) = seen(of: shape)
        guard share < 0.95 else { return point }
        let sums = heat.sums(columns: sideways)
        let count = CGFloat(sums.count)
        var upTo: [CGFloat] = [0]
        for sum in sums { upTo.append(upTo[upTo.count - 1] + sum) }
        guard let all = upTo.last, all > 0 else { return point }
        // What a window about `middle` holds: whole cells and parts of the
        // two at its ends.
        func held(_ middle: CGFloat) -> CGFloat {
            func before(_ place: CGFloat) -> CGFloat {
                let at = min(max(place * count, 0), count)
                let cell = min(Int(at), sums.count - 1)
                return upTo[cell] + (at - CGFloat(cell)) * sums[cell]
            }
            return before(middle + share / 2) - before(middle - share / 2)
        }
        let least = share / 2, most = 1 - share / 2
        let steps = 200
        let middles = (0 ... steps).map { least + (most - least) * CGFloat($0) / CGFloat(steps) }
        let holds = middles.map(held)
        guard let best = holds.indices.max(by: { holds[$0] < holds[$1] }) else { return point }
        let now = min(max(sideways ? point.x : point.y, least), most)
        guard holds[best] > held(now) * tells else { return point }
        // The middle of the windows as good as the best one, about it.
        var first = best, last = best
        while first > 0, holds[first - 1] >= holds[best] * asGood { first -= 1 }
        while last < steps, holds[last + 1] >= holds[best] * asGood { last += 1 }
        let along = (middles[first] + middles[last]) / 2
        // Across the window: where its heat is.
        let across = heat.sums(columns: !sideways, from: along - share / 2, to: along + share / 2)
        var weight: CGFloat = 0, moment: CGFloat = 0
        for (cell, sum) in across.enumerated() {
            weight += sum
            moment += (CGFloat(cell) + 0.5) * sum
        }
        let other = weight > 0 ? moment / weight / CGFloat(across.count) : (sideways ? point.y : point.x)
        return sideways ? UnitPoint(x: along, y: other) : UnitPoint(x: other, y: along)
    }

    /// Faces on one screen take no more of it than this, edge to edge.
    static let facesFill: CGFloat = 0.8

    /// The largest of `faces` and those that are on one screen with it
    /// (larger ones first), as one box: of faces too far apart for one
    /// screen their middle is the empty wall between them.
    static func together(_ faces: [CGRect], shape: CGFloat) -> CGRect? {
        let (share, sideways) = seen(of: shape)
        guard share < 0.95 else { return union(faces) }
        let room = share * facesFill
        var box: CGRect?
        for face in faces.sorted(by: { $0.area > $1.area }) {
            guard let so = box else {
                box = face
                continue
            }
            let with = so.union(face)
            if (sideways ? with.width : with.height) <= room { box = with }
        }
        return box
    }

    /// A figure this small (a share of the picture's height) is staffage,
    /// not the subject.
    static let figureLeast: CGFloat = 0.25

    /// See `point(in:key:near:subject:)`. Boxes are fractions with the
    /// origin top-left; `shape` is the picture's, width to height.
    static func subject(
        faces: [CGRect], figures: [CGRect], salient: [(box: CGRect, weight: CGFloat)],
        heat: Heat? = nil, shape: CGFloat = SubjectFocus.screen
    ) -> UnitPoint {
        let largest = faces.map(\.area).max() ?? 0
        if let box = together(faces.filter { $0.area >= largest * 0.4 }, shape: shape) {
            return UnitPoint(x: box.midX, y: box.midY)
        }
        if let figure = figures.filter({ $0.height >= figureLeast }).max(by: { $0.area < $1.area }) {
            let head = UnitPoint(x: figure.midX, y: figure.minY + figure.height * headInFigure)
            // Lying down, wider than the screen: its head is not over its
            // middle, and the eye's map says where it is.
            let (share, sideways) = seen(of: shape)
            if let heat, sideways, figure.width > share { return telling(heat, shape: shape, from: head) }
            return head
        }
        // The heaviest single place, by how sure Vision is and how much of
        // the picture it takes (the square root: a big field is no subject
        // for its size alone).
        if let best = salient.max(by: { $0.weight * $0.box.area.squareRoot() < $1.weight * $1.box.area.squareRoot() }) {
            let middle = UnitPoint(x: best.box.midX, y: best.box.midY)
            return heat.map { telling($0, shape: shape, from: middle) } ?? middle
        }
        return .center
    }

    private static func find(in image: UIImage, near point: UnitPoint) -> UnitPoint {
        guard let cgImage = image.cgImage else { return point }
        let faces = VNDetectFaceRectanglesRequest()
        let people = VNDetectHumanRectanglesRequest()
        people.upperBodyOnly = false
        let handler = VNImageRequestHandler(cgImage: cgImage, orientation: .up)
        try? handler.perform([faces, people])
        return near(
            point,
            faces: (faces.results ?? []).filter { $0.confidence > 0.5 }.map { topLeft($0.boundingBox) },
            people: (people.results ?? []).filter { $0.confidence > 0.5 }.map { topLeft($0.boundingBox) }
        )
    }

    /// How far (a share of the picture) a face may be from Claude's point
    /// and still be the one it meant.
    static let faceReach: CGFloat = 0.3
    /// Where a head is in a whole figure's box, from its top.
    static let headInFigure: CGFloat = 0.1

    /// The face nearest `point` within `faceReach`; else, `point` inside a
    /// figure, its head (a face turned away, too small for Vision); else
    /// `point` itself. Boxes are fractions with the origin top-left.
    static func near(_ point: UnitPoint, faces: [CGRect], people: [CGRect]) -> UnitPoint {
        func distance(_ box: CGRect) -> CGFloat {
            hypot(box.midX - point.x, box.midY - point.y)
        }
        if let face = faces.filter({ distance($0) <= faceReach }).min(by: { distance($0) < distance($1) }) {
            return UnitPoint(x: face.midX, y: face.midY)
        }
        let inside = people.filter { $0.contains(CGPoint(x: point.x, y: point.y)) }
        if let figure = inside.min(by: { $0.width * $0.height < $1.width * $1.height }) {
            return UnitPoint(x: figure.midX, y: figure.minY + figure.height * headInFigure)
        }
        return point
    }

    /// Vision's box (origin bottom-left) with the origin top-left.
    private static func topLeft(_ box: CGRect) -> CGRect {
        CGRect(x: box.minX, y: 1 - box.maxY, width: box.width, height: box.height)
    }

    private static func union(_ boxes: [CGRect]) -> CGRect? {
        guard let first = boxes.first else { return nil }
        return boxes.dropFirst().reduce(first) { $0.union($1) }
    }

    /// Vision's boxes are normalised with the origin bottom-left.
    private static func center(of box: CGRect) -> UnitPoint {
        UnitPoint(x: box.midX, y: 1 - box.midY)
    }
}

private extension CGRect {
    var area: CGFloat { width * height }
}

/// A picture filling its box, shifted so `focus` sits as near the middle as
/// the picture's edges allow.
struct FocusedFill: View {
    let image: UIImage
    let focus: UnitPoint

    var body: some View {
        GeometryReader { geo in
            let box = geo.size
            let scale = max(box.width / image.size.width, box.height / image.size.height)
            let width = image.size.width * scale
            let height = image.size.height * scale
            Image(uiImage: image)
                .resizable()
                .frame(width: width, height: height)
                .offset(
                    x: Self.shift(focus.x, length: width, box: box.width),
                    y: Self.shift(focus.y, length: height, box: box.height)
                )
        }
    }

    /// From the leading edge: centred on the focus, never past an edge.
    static func shift(_ focus: CGFloat, length: CGFloat, box: CGFloat) -> CGFloat {
        min(0, max(box - length, box / 2 - focus * length))
    }
}
