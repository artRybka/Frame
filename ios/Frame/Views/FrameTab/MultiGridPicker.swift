import SwiftUI

/// A board of several photos ("Multi"): which windows the mat has.
/// Mirrors server/src/frame_server/imaging/grids.py (GRIDS, grid_rects).
struct MultiGrid: Hashable, Sendable {
    let id: String  // "A", "B", ... within its count
    let name: String
    let cols: Double
    let rows: Double
    let cells: [[Double]]  // col, row, cols, rows on the landscape canvas

    static let counts = 2 ... 8

    static let all: [Int: [MultiGrid]] = [
        2: [
            MultiGrid(id: "A", name: "Para pionów", cols: 6, rows: 1, cells: [[1, 0, 2, 1], [3, 0, 2, 1]]),
            MultiGrid(id: "B", name: "Duży i mały", cols: 12, rows: 12, cells: [[0, 0, 8, 12], [8, 3, 4, 6]]),
        ],
        3: [
            MultiGrid(id: "A", name: "Tryptyk", cols: 3, rows: 1, cells: [[0, 0, 1, 1], [1, 0, 1, 1], [2, 0, 1, 1]]),
            MultiGrid(id: "B", name: "Jeden i dwa", cols: 3, rows: 2, cells: [[0, 0, 2, 2], [2, 0, 1, 1], [2, 1, 1, 1]]),
            MultiGrid(id: "C", name: "Pion i dwa poziomy", cols: 12, rows: 12, cells: [[0, 0, 4, 12], [4, 0, 8, 6], [4, 6, 8, 6]]),
        ],
        4: [
            MultiGrid(id: "A", name: "Siatka 2×2", cols: 8, rows: 2, cells: [[1, 0, 3, 1], [4, 0, 3, 1], [1, 1, 3, 1], [4, 1, 3, 1]]),
            MultiGrid(id: "B", name: "Rząd pionów", cols: 4, rows: 12, cells: [[0, 2, 1, 8], [1, 2, 1, 8], [2, 2, 1, 8], [3, 2, 1, 8]]),
            MultiGrid(id: "C", name: "Duży i trzy", cols: 12, rows: 12, cells: [[0, 0, 9, 12], [9, 0, 3, 4], [9, 4, 3, 4], [9, 8, 3, 4]]),
        ],
        5: [
            MultiGrid(id: "A", name: "Środek i cztery rogi", cols: 4, rows: 2,
                      cells: [[1, 0, 2, 2], [0, 0, 1, 1], [0, 1, 1, 1], [3, 0, 1, 1], [3, 1, 1, 1]]),
            MultiGrid(id: "B", name: "Pion i cztery", cols: 12, rows: 12,
                      cells: [[0, 0, 4, 12], [4, 0, 4, 6], [8, 0, 4, 6], [4, 6, 4, 6], [8, 6, 4, 6]]),
        ],
        6: [
            MultiGrid(id: "A", name: "Siatka 3×2", cols: 3, rows: 2,
                      cells: [[0, 0, 1, 1], [1, 0, 1, 1], [2, 0, 1, 1], [0, 1, 1, 1], [1, 1, 1, 1], [2, 1, 1, 1]]),
            MultiGrid(id: "B", name: "Duży i pięć", cols: 16, rows: 12,
                      cells: [[2, 0, 8, 8], [10, 0, 4, 4], [10, 4, 4, 4], [2, 8, 4, 4], [6, 8, 4, 4], [10, 8, 4, 4]]),
        ],
        7: [
            MultiGrid(id: "A", name: "Środek i boki", cols: 4, rows: 3,
                      cells: [[1, 0, 2, 3], [0, 0, 1, 1], [0, 1, 1, 1], [0, 2, 1, 1], [3, 0, 1, 1], [3, 1, 1, 1], [3, 2, 1, 1]]),
            MultiGrid(id: "B", name: "Cztery nad trzema", cols: 8, rows: 2,
                      cells: [[0, 0, 2, 1], [2, 0, 2, 1], [4, 0, 2, 1], [6, 0, 2, 1], [1, 1, 2, 1], [3, 1, 2, 1], [5, 1, 2, 1]]),
        ],
        8: [
            MultiGrid(id: "A", name: "Siatka 4×2", cols: 4, rows: 2,
                      cells: [[0, 0, 1, 1], [1, 0, 1, 1], [2, 0, 1, 1], [3, 0, 1, 1], [0, 1, 1, 1], [1, 1, 1, 1], [2, 1, 1, 1], [3, 1, 1, 1]]),
            MultiGrid(id: "B", name: "Duży i siedem", cols: 48, rows: 12,
                      cells: [[0, 0, 24, 7], [24, 0, 12, 3.5], [36, 0, 12, 3.5], [24, 3.5, 12, 3.5], [36, 3.5, 12, 3.5],
                              [0, 7, 16, 5], [16, 7, 16, 5], [32, 7, 16, 5]]),
        ],
    ]

    static func grids(_ count: Int) -> [MultiGrid] { all[count] ?? [] }

    /// The windows on a canvas of `size` (server: grid_rects); a portrait
    /// canvas uses the grid transposed.
    func rects(in size: CGSize, margin: Double) -> [CGRect] {
        let portrait = size.height > size.width
        let outer = min(size.width, size.height) * max(margin, 0.03)
        let gap = outer * 0.55
        let inner = CGSize(width: size.width - 2 * outer, height: size.height - 2 * outer)
        let (c, r) = portrait ? (rows, cols) : (cols, rows)
        return cells.map { cell in
            let (x, y, w, h) = portrait ? (cell[1], cell[0], cell[3], cell[2]) : (cell[0], cell[1], cell[2], cell[3])
            let x0 = outer + x / c * inner.width + gap / 2
            let y0 = outer + y / r * inner.height + gap / 2
            let x1 = outer + (x + w) / c * inner.width - gap / 2
            let y1 = outer + (y + h) / r * inner.height - gap / 2
            return CGRect(x: x0, y: y0, width: x1 - x0, height: y1 - y0)
        }
    }
}

/// How many photos go on a board and in which grid.
struct MultiSettings: View {
    @Binding var presentation: Presentation
    let portrait: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Toggle("Losowa liczba zdjęć", isOn: $presentation.multiRandom)
            if presentation.multiRandom {
                Text("Za każdym razem od 2 do 8 zdjęć, w siatce dobranej do ich kształtów.")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                Stepper(value: $presentation.multiCount, in: MultiGrid.counts) {
                    HStack {
                        Text("Zdjęć na planszy")
                        Spacer()
                        Text("\(presentation.multiCount)").monospacedDigit().foregroundStyle(Theme.inkSoft)
                    }
                }
                .onChange(of: presentation.multiCount) { _, count in
                    if !MultiGrid.grids(count).contains(where: { $0.id == presentation.multiGrid }) {
                        presentation.multiGrid = "auto"
                    }
                }
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 8) {
                    GridOption(title: "Auto", grid: nil, portrait: portrait, margin: presentation.margin,
                               mat: MatSwatch.color(presentation.mat),
                               selected: presentation.multiGrid == "auto") {
                        presentation.multiGrid = "auto"
                    }
                    ForEach(MultiGrid.grids(presentation.multiCount), id: \.id) { grid in
                        GridOption(title: grid.name, grid: grid, portrait: portrait, margin: presentation.margin,
                                   mat: MatSwatch.color(presentation.mat),
                                   selected: presentation.multiGrid == grid.id) {
                            presentation.multiGrid = grid.id
                        }
                    }
                }
                Text(presentation.multiGrid == "auto"
                     ? "Siatka dobierana do zdjęć: pionowe trafiają do pionowych okienek, poziome do poziomych."
                     : "Zawsze ta siatka; każde zdjęcie przycinane do swojego okienka.")
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

/// Miniature of a grid on the frame; "Auto" shows the grid's shapes faded.
private struct GridOption: View {
    let title: String
    let grid: MultiGrid?
    let portrait: Bool
    let margin: Double
    let mat: Color
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                ZStack {
                    Canvas { context, size in
                        context.fill(Path(CGRect(origin: .zero, size: size)), with: .color(mat))
                        guard let grid else { return }
                        for rect in grid.rects(in: size, margin: max(margin, 0.07)) {
                            context.fill(Path(rect), with: .color(Theme.accent.opacity(0.75)))
                        }
                    }
                    if grid == nil {
                        Image(systemName: "sparkles")
                            .font(.subheadline)
                            .foregroundStyle(Theme.accent.opacity(0.75))
                    }
                }
                .aspectRatio(portrait ? 9.0 / 16.0 : 16.0 / 9.0, contentMode: .fit)
                .frame(height: portrait ? 64 : 44)
                .padding(3)
                .background(Theme.frameWood)
                Text(title)
                    .font(.caption2.weight(.medium))
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                    .foregroundStyle(Theme.ink)
            }
            .frame(maxWidth: .infinity)
            .padding(6)
            .background(selected ? Theme.accent.opacity(0.1) : .clear, in: RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(selected ? Theme.accent : Theme.hairline, lineWidth: selected ? 2 : 1))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(title)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}
