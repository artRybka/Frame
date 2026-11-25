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
    /// together (a middle between two of them is often empty).
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
        return subject(faces: faceBoxes, figures: figures, salient: salient)
    }

    /// A figure this small (a share of the picture's height) is staffage,
    /// not the subject.
    static let figureLeast: CGFloat = 0.25

    /// See `point(in:key:near:subject:)`. Boxes are fractions with the
    /// origin top-left.
    static func subject(faces: [CGRect], figures: [CGRect], salient: [(box: CGRect, weight: CGFloat)]) -> UnitPoint {
        let largest = faces.map(\.area).max() ?? 0
        if let box = union(faces.filter { $0.area >= largest * 0.4 }) {
            return UnitPoint(x: box.midX, y: box.midY)
        }
        if let figure = figures.filter({ $0.height >= figureLeast }).max(by: { $0.area < $1.area }) {
            return UnitPoint(x: figure.midX, y: figure.minY + figure.height * headInFigure)
        }
        // The heaviest single place, by how sure Vision is and how much of
        // the picture it takes (the square root: a big field is no subject
        // for its size alone).
        if let best = salient.max(by: { $0.weight * $0.box.area.squareRoot() < $1.weight * $1.box.area.squareRoot() }) {
            return UnitPoint(x: best.box.midX, y: best.box.midY)
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
