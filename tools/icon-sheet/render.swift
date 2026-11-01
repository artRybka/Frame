// Renders each SF Symbol named in symbols.txt to a black-on-clear PNG, for
// the icon sheet in the project files. Run on macOS: swift render.swift.
import AppKit

let here = URL(fileURLWithPath: CommandLine.arguments[1])
let out = URL(fileURLWithPath: CommandLine.arguments[2])
try FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
let names = try String(contentsOf: here.appendingPathComponent("symbols.txt"), encoding: .utf8)
    .split(whereSeparator: \.isNewline).map(String.init).filter { !$0.isEmpty }
var missing: [String] = []
let side = 160
for name in names {
    guard let base = NSImage(systemSymbolName: name, accessibilityDescription: nil),
          let image = base.withSymbolConfiguration(.init(pointSize: 96, weight: .regular))
    else { missing.append(name); continue }
    let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: side, pixelsHigh: side, bitsPerSample: 8, samplesPerPixel: 4,
        hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    rep.size = NSSize(width: side, height: side)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    let size = image.size
    let rect = NSRect(x: (CGFloat(side) - size.width) / 2, y: (CGFloat(side) - size.height) / 2,
                      width: size.width, height: size.height)
    image.draw(in: rect)
    NSColor.black.set()
    rect.fill(using: .sourceAtop)
    NSGraphicsContext.restoreGraphicsState()
    try rep.representation(using: .png, properties: [:])!.write(to: out.appendingPathComponent(name + ".png"))
}
try (missing.joined(separator: "\n") + "\n").write(
    to: out.appendingPathComponent("missing.txt"), atomically: true, encoding: .utf8)
print("rendered \(names.count - missing.count), missing: \(missing)")
