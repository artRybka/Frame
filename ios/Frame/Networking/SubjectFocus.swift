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

    private var cache: [String: UnitPoint] = [:]

    /// Unit point in the picture, origin top-left. Waits `patience` seconds
    /// at most, then gives the middle (the answer still comes in for next
    /// time); a picture scrolled away before its turn is skipped.
    func point(in image: UIImage, key: String, patience: Double = 2.5) async -> UnitPoint {
        if let cached = cache[key] { return cached }
        let job = Job()
        let operation = BlockOperation {
            let point = Self.find(in: image)
            job.finish(point)
            Task { await SubjectFocus.shared.remember(point, for: key) }
        }
        return await withTaskCancellationHandler {
            await withCheckedContinuation { (continuation: CheckedContinuation<UnitPoint, Never>) in
                job.start(continuation)
                Self.queue.addOperation(operation)
                DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + patience) {
                    job.finish(.center)
                }
            }
        } onCancel: {
            operation.cancel()
            job.finish(.center)
        }
    }

    private func remember(_ point: UnitPoint, for key: String) {
        cache[key] = point
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
