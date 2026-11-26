// What Vision finds in works much wider than the screen (Mateusz
// 2026-11-26), on a Mac's processor: the simulator on CI answers the same
// for every picture. A diagnosis, taken out again before a release.
import CoreML
import Foundation
import ImageIO
import Vision

func box(_ rect: CGRect) -> String {
    String(format: "x %.3f-%.3f y %.3f-%.3f", rect.minX, rect.maxX, 1 - rect.maxY, 1 - rect.minY)
}

func onProcessor(_ request: VNRequest) {
    guard let stages = try? request.supportedComputeStageDevices else { return }
    for (stage, devices) in stages {
        for device in devices {
            if case .cpu = device { request.setComputeDevice(device, for: stage) }
        }
    }
}

for path in CommandLine.arguments.dropFirst() {
    let name = URL(fileURLWithPath: path).deletingPathExtension().lastPathComponent
    guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
          let picture = CGImageSourceCreateImageAtIndex(source, 0, nil)
    else {
        print("DIAG \(name): no picture")
        continue
    }
    print("DIAG \(name): \(picture.width)x\(picture.height)")
    for processor in [true, false] {
        let how = processor ? "cpu" : "any"
        let handler = VNImageRequestHandler(cgImage: picture, orientation: .up)
        let faces = VNDetectFaceRectanglesRequest()
        let people = VNDetectHumanRectanglesRequest()
        people.upperBodyOnly = false
        let animals = VNRecognizeAnimalsRequest()
        let attention = VNGenerateAttentionBasedSaliencyImageRequest()
        let objects = VNGenerateObjectnessBasedSaliencyImageRequest()
        let all: [VNRequest] = [faces, people, animals, attention, objects]
        if processor { all.forEach(onProcessor) }
        for request in all {
            do { try handler.perform([request]) } catch { print("DIAG \(name) \(how) \(type(of: request)) failed: \(error)") }
        }
        for face in faces.results ?? [] { print("DIAG \(name) \(how) face \(box(face.boundingBox)) sure \(face.confidence)") }
        for one in people.results ?? [] { print("DIAG \(name) \(how) figure \(box(one.boundingBox)) sure \(one.confidence)") }
        for one in animals.results ?? [] {
            print("DIAG \(name) \(how) animal \(one.labels.map(\.identifier)) \(box(one.boundingBox)) sure \(one.confidence)")
        }
        print("DIAG \(name) \(how) faces \(faces.results?.count ?? -1), figures \(people.results?.count ?? -1), animals \(animals.results?.count ?? -1)")
        for (kind, request) in [("attention", attention as VNImageBasedRequest), ("objects", objects as VNImageBasedRequest)] {
            guard let found = request.results?.first as? VNSaliencyImageObservation else {
                print("DIAG \(name) \(how) \(kind): nothing")
                continue
            }
            for one in found.salientObjects ?? [] {
                print("DIAG \(name) \(how) \(kind) place \(box(one.boundingBox)) sure \(one.confidence)")
            }
            let buffer = found.pixelBuffer
            CVPixelBufferLockBaseAddress(buffer, .readOnly)
            let wide = CVPixelBufferGetWidth(buffer), tall = CVPixelBufferGetHeight(buffer)
            let stride = CVPixelBufferGetBytesPerRow(buffer)
            if let base = CVPixelBufferGetBaseAddress(buffer) {
                print("DIAG \(name) \(how) \(kind) heat \(wide)x\(tall)")
                for y in 0 ..< tall {
                    let row = base.advanced(by: y * stride).assumingMemoryBound(to: Float32.self)
                    let line = (0 ..< wide).map { String(format: "%.3f", row[$0]) }.joined(separator: " ")
                    print("HEAT \(name) \(how) \(kind) \(y): \(line)")
                }
            }
            CVPixelBufferUnlockBaseAddress(buffer, .readOnly)
        }
    }
}
