import SwiftUI

/// The study's "Jak powstawał" (Mateusz 2026-11-13, "G2"): how the work was
/// painted, stage by stage, as a published technical study of it tells
/// (the server found one; without it the section is not there). Each stage
/// is the same canvas drawn by Google's image model, the last the work
/// itself; under each the study's own words. Scrolled sideways, a stage at
/// a time.
struct PaintingStagesRow: View {
    let work: DailyWork
    let stages: [DailyWork.PaintingStage]
    let column: CGFloat

    /// The work's shape, kept between a tall one and a long one so a stage
    /// and its words fit the column.
    private var aspect: CGFloat {
        CGFloat(max(0.6, min(1.8, work.item.summary.aspectRatio)))
    }

    private var width: CGFloat { column * 0.86 }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(alignment: .top, spacing: 14) {
                    ForEach(Array(stages.enumerated()), id: \.offset) { n, stage in
                        card(n, stage)
                    }
                }
                .scrollTargetLayout()
            }
            .scrollTargetBehavior(.viewAligned)
            .edgeToEdgeRow()
            Text("Etapy według badania technicznego dzieła. Obrazy etapów narysował model Google; ostatni to samo dzieło.")
                .font(.caption)
                .foregroundStyle(Theme.inkSoft)
        }
    }

    private func card(_ n: Int, _ stage: DailyWork.PaintingStage) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            picture(stage)
                .frame(width: width, height: width / aspect)
                .clipShape(RoundedRectangle(cornerRadius: 3, style: .continuous))
                .accessibilityLabel("Etap \(n + 1): \(stage.title)")
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text("\(n + 1)")
                    .font(.serif(15, weight: .semibold))
                    .foregroundStyle(Theme.vermilion)
                Text(stage.title)
                    .font(.serif(16, weight: .medium))
                    .foregroundStyle(Theme.ink)
            }
            Text(stage.text)
                .font(.subheadline)
                .foregroundStyle(Theme.ink)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(width: width, alignment: .leading)
    }

    @ViewBuilder
    private func picture(_ stage: DailyWork.PaintingStage) -> some View {
        let id = work.item.item.id
        if stage.image.isEmpty {
            ArtImage(ref: .image(id), fallback: .thumb(id), placeholder: work.item.item.placeholderColor,
                     maxPixel: 1200, contentMode: .fit)
        } else {
            ArtImage(ref: .path(stage.image), placeholder: work.item.item.placeholderColor,
                     maxPixel: 1200, contentMode: .fit)
        }
    }
}
