import SwiftUI
import UIKit

/// The app icon's colour squares at play, while Discover's search is still
/// empty: one of a few games, picked at random, and a tap moves on to the
/// next. The row stands in the middle of the screen; the view reaches down
/// to the tab bar so there is room to fall to. Every round they rest a
/// while in the row. With Reduce Motion they just stand in it. At the end of
/// a list they play in a small box instead, the row near its bottom.
struct SquaresAnimation: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var game = SquareGame.allCases.randomElement() ?? .wave
    @State private var start = Date.now
    /// The middle of the screen, from the view's top.
    @State private var middle: Double?
    /// Whether the row stands in the middle of the screen (or of the box).
    private let inScreenMiddle: Bool
    /// Whether a tap moves on to the next game.
    private let tapForNext: Bool

    /// Room under the row of a box, for falling ones to fade out in.
    static let fadeRoom = 30.0

    init(inScreenMiddle: Bool = true, tapForNext: Bool = true) {
        self.inScreenMiddle = inScreenMiddle
        self.tapForNext = tapForNext
    }

    var body: some View {
        TimelineView(.animation(paused: reduceMotion)) { context in
            let time = context.date.timeIntervalSince(start)
            Canvas { canvas, size in
                let squares = reduceMotion ? SquareGame.row : game.squares(at: time)
                draw(squares, in: &canvas, size: size)
            }
        }
        .onGeometryChange(for: Double.self) { proxy in
            Double(proxy.frame(in: .global).minY)
        } action: { top in
            middle = Self.screenHeight.map { $0 / 2 - top }
        }
        .contentShape(Rectangle())
        .onTapGesture {
            let games = SquareGame.allCases
            game = games[((games.firstIndex(of: game) ?? 0) + 1) % games.count]
            start = .now
        }
        .allowsHitTesting(tapForNext)
        .accessibilityHidden(true)
    }

    /// The height of the window the app shows in.
    private static var screenHeight: Double? {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        let scene = scenes.first { $0.activationState == .foregroundActive } ?? scenes.first
        return (scene?.keyWindow ?? scene?.windows.first).map { Double($0.bounds.height) }
    }

    private func draw(_ squares: [PlayingSquare], in canvas: inout GraphicsContext, size: CGSize) {
        let side = SquareGame.side
        // The row's left edge, and the line the squares stand on: the row
        // in the middle of the screen (of the view until that is known), or
        // in a box just above the room to fade out in.
        let left = (Double(size.width) - SquareGame.row.width) / 2
        let height = Double(size.height)
        let row = inScreenMiddle ? (middle ?? height / 2) : height - Self.fadeRoom - side / 2
        let base = min(height - side, max(5 * side, row + side / 2))
        for square in squares where square.alpha > 0 {
            var context = canvas
            // Falling ones fade out at the bottom.
            context.opacity = square.alpha * min(1, max(0, (Double(size.height) - base - square.y) / Self.fadeRoom))
            // Scaled from the bottom edge, turned about the centre.
            context.translateBy(x: left + square.x + side / 2, y: base + square.y - side / 2 * square.sy)
            context.rotate(by: .degrees(square.rotation))
            context.scaleBy(x: square.sx, y: square.sy)
            let rect = CGRect(x: -side / 2, y: -side / 2, width: side, height: side)
            context.fill(Path(rect), with: .color(Theme.iconSquares[square.index]))
            if square.index == 5 {
                // White on paper (black on the dark one) needs an edge.
                context.stroke(
                    Path(rect.insetBy(dx: 0.5, dy: 0.5)), with: .color(Theme.hairline),
                    lineWidth: 1 / max(0.2, square.sx)
                )
            }
        }
    }
}

/// One square of a game: `x` of its left edge from the row's, `y` how far it
/// is lifted (up is negative), rotation in degrees, scale from its bottom.
struct PlayingSquare {
    let index: Int
    var x: Double
    var y: Double = 0
    var rotation: Double = 0
    var sx: Double = 1
    var sy: Double = 1
    var alpha: Double = 1
}

/// The games, each a function of time in seconds that loops, with a rest in
/// the row once a round.
enum SquareGame: CaseIterable {
    /// They hop one after another; each time round one does a flip.
    case wave
    /// The first leaps over the others to the end of the row, again and again.
    case leapfrog
    /// They fall in from above and bounce, cheer together and drop to the
    /// bottom of the screen.
    case drop
    /// They stack into two columns and a sixth square closes the frame.
    case frame

    static let side = 11.0
    static let gap = 5.0
    static let step = side + gap
    static let indices = Array(0 ..< 5)

    static var row: [PlayingSquare] { indices.map { PlayingSquare(index: $0, x: Double($0) * step) } }

    /// How long the squares stand still in their row, once a round.
    static let rest = 2.0

    /// A round of play, and when in it they all stand in their row, which is
    /// where the rest goes.
    private var rhythm: (play: Double, still: Double) {
        switch self {
        case .wave: (2 * 2.6, 2 * 2.6)
        case .leapfrog: (5, 5)  // after five leaps they are back in order
        case .drop: (5.6, 2.0)  // all landed, before they cheer
        case .frame: (6, 6)
        }
    }

    func squares(at time: Double) -> [PlayingSquare] {
        let (play, still) = rhythm
        let k = floor(time / (play + Self.rest)), u = time - k * (play + Self.rest)
        let t = k * play + (u < still ? u : max(still, u - Self.rest))
        switch self {
        case .wave: return Self.wave(t)
        case .leapfrog: return Self.leapfrog(t)
        case .drop: return Self.drop(t)
        case .frame: return Self.frame(t)
        }
    }

    private static func wave(_ t: Double) -> [PlayingSquare] {
        let period = 2.6, hop = 0.5, land = 0.18, delay = 0.11, height = 1.5 * side
        return indices.map { i -> PlayingSquare in
            let local = t - Double(i) * delay
            let u = mod(local, period)
            let flipper = Int(mod(floor(local / period), 5)) == i
            var s = PlayingSquare(index: i, x: Double(i) * step)
            if u < hop {
                let p = u / hop, k = sin(.pi * p)
                s.y = -(flipper ? 1.45 : 1) * height * 4 * p * (1 - p)
                s.sx = 1 - 0.08 * k
                s.sy = 1 + 0.12 * k
                if flipper { s.rotation = 360 * easeInOut(p) }
            } else if u < hop + land {
                let k = sin(.pi * (u - hop) / land)
                s.sx = 1 + 0.22 * k
                s.sy = 1 - 0.28 * k
            }
            return s
        }
    }

    private static func leapfrog(_ t: Double) -> [PlayingSquare] {
        let jump = 1.0, k = floor(t / jump), u = t / jump - k
        let p = easeInOut(clamp((u - 0.12) / 0.7))
        return indices.map { i -> PlayingSquare in
            let slot = Int(mod(Double(i) - k, 5))
            guard slot == 0 else { return PlayingSquare(index: i, x: (Double(slot) - p) * step) }
            var s = PlayingSquare(index: i, x: 4 * step * p)
            s.y = -1.9 * side * 4 * p * (1 - p)
            s.rotation = 180 * p
            if u < 0.12 {  // crouch before the jump
                let c = sin(.pi * u / 0.12)
                s.sx = 1 + 0.18 * c
                s.sy = 1 - 0.25 * c
            } else if u > 0.82 {  // landing
                let c = sin(.pi * (u - 0.82) / 0.18)
                s.sx = 1 + 0.2 * c
                s.sy = 1 - 0.26 * c
            }
            return s
        }
    }

    private static func drop(_ t: Double) -> [PlayingSquare] {
        let period = 5.6, u = mod(t, period), height = 4.4 * side, fall = 0.75
        let order = [1, 3, 0, 4, 2]  // when each one comes, by index
        return indices.map { i -> PlayingSquare in
            var s = PlayingSquare(index: i, x: Double(i) * step)
            let turn = i % 2 == 1 ? 1.0 : -1.0
            let f = u - (0.15 + Double(order[i]) * 0.2)
            if f < 0 {
                s.alpha = 0
                return s
            }
            if f < fall {
                let p = f / fall
                s.y = -height * (1 - bounceOut(p))
                s.rotation = turn * 140 * (1 - easeOut(min(1, p * 1.6)))
                s.alpha = clamp(p * 5)
                return s
            }
            let cheer = u - (2.55 + Double(i) * 0.05)
            if cheer > 0 && cheer < 0.42 {
                let c = cheer / 0.42
                s.y = -0.75 * side * 4 * c * (1 - c)
                s.sy = 1 + 0.1 * sin(.pi * c)
            }
            // After a while they drop off the bottom, one after another.
            let away = u - (3.5 + Double(order[i]) * 0.13)
            if away > 0 {
                let gravity = 40 * side, kick = 6 * side
                s.y = -kick * away + 0.5 * gravity * away * away
                s.rotation = turn * 220 * away
            }
            return s
        }
    }

    /// Column and row (from the bottom) of each square in the frame: black,
    /// blue and red on the left, green and yellow on the right, and the
    /// sixth at the top right.
    private static let cells = [(0, 0), (1, 0), (0, 1), (1, 1), (0, 2), (1, 2)]

    private static func frame(_ t: Double) -> [PlayingSquare] {
        let period = 6.0, u = mod(t, period)
        let left = (row.width - (2 * side + gap)) / 2
        func target(_ i: Int) -> (x: Double, y: Double) {
            (left + Double(cells[i].0) * step, -Double(cells[i].1) * step)
        }
        var squares = indices.map { i -> PlayingSquare in
            let (x, y) = target(i)
            let there = clamp((u - (0.6 + Double(i) * 0.28)) / 0.55)
            let back = clamp((u - (4.3 + Double(4 - i) * 0.2)) / 0.45)
            let p = easeInOut(there) * (1 - easeInOut(back))
            let hop = sin(.pi * (there < 1 ? there : back)) * 0.9 * side
            let home = Double(i) * step
            return PlayingSquare(
                index: i, x: home + (x - home) * p, y: y * p - hop,
                rotation: 90 * (there < 1 ? easeInOut(there) : 1 - easeInOut(back))
            )
        }
        // The sixth pops in once the others are in place, and out before they leave.
        let pop = clamp((u - 2.55) / 0.35), gone = clamp((u - 4.0) / 0.25)
        if pop > 0 && gone < 1 {
            let (x, y) = target(5)
            let k = pop < 1 ? backOut(pop) : 1 - easeIn(gone)
            squares.append(PlayingSquare(index: 5, x: x, y: y, sx: k, sy: k))
        }
        return squares
    }

    // MARK: Easing

    private static func clamp(_ v: Double) -> Double { min(1, max(0, v)) }
    private static func mod(_ a: Double, _ n: Double) -> Double { a - n * floor(a / n) }
    private static func easeInOut(_ p: Double) -> Double {
        p < 0.5 ? 4 * p * p * p : 1 - pow(-2 * p + 2, 3) / 2
    }
    private static func easeOut(_ p: Double) -> Double { 1 - pow(1 - p, 3) }
    private static func easeIn(_ p: Double) -> Double { p * p * p }
    private static func backOut(_ p: Double) -> Double {
        let c = 1.9
        return 1 + (c + 1) * pow(p - 1, 3) + c * pow(p - 1, 2)
    }
    private static func bounceOut(_ p: Double) -> Double {
        let n = 7.5625, d = 2.75
        if p < 1 / d { return n * p * p }
        if p < 2 / d { let q = p - 1.5 / d; return n * q * q + 0.75 }
        if p < 2.5 / d { let q = p - 2.25 / d; return n * q * q + 0.9375 }
        let q = p - 2.625 / d
        return n * q * q + 0.984375
    }
}

private extension Array where Element == PlayingSquare {
    /// From the first square's left edge to the last one's right edge.
    var width: Double { Double(count) * SquareGame.side + Double(count - 1) * SquareGame.gap }
}

/// Waiting on a search: the icon's squares in a small box, nothing to read.
/// Shown for as long as more may come; gone only once nothing more will.
struct SearchWaiting: View {
    var height: CGFloat = 96

    var body: some View {
        SquaresAnimation(inScreenMiddle: false, tapForNext: false)
            .frame(height: height)
            .frame(maxWidth: .infinity)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Szukam")
    }
}
