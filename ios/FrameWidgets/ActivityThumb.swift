import SwiftUI
import UIKit

/// The work's small picture on a Live Activity (`ActivityPicture`), in its
/// own proportions within `height`, with a status mark on its corner; just
/// the mark when there is no picture.
struct ActivityThumb<Mark: View>: View {
    let data: Data?
    let height: CGFloat
    var corner: CGFloat = 6
    /// The card's background, around the mark.
    var ground: Color = Palette.paper
    @ViewBuilder let mark: () -> Mark

    var body: some View {
        if let image = data.flatMap(UIImage.init(data:)), image.size.height > 0 {
            let ratio = min(max(image.size.width / image.size.height, 0.6), 1.6)
            Image(uiImage: image)
                .resizable()
                .aspectRatio(contentMode: .fill)
                .frame(width: height * ratio, height: height)
                .clipShape(RoundedRectangle(cornerRadius: corner, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: corner, style: .continuous)
                        .strokeBorder(.primary.opacity(0.12), lineWidth: 0.5)
                )
                .overlay(alignment: .bottomTrailing) {
                    mark()
                        .font(.system(size: max(11, height * 0.34)))
                        .background(Circle().fill(ground).padding(-1.5))
                        .offset(x: 5, y: 5)
                }
                .padding(.trailing, 4)
                .padding(.bottom, 4)
        } else {
            mark()
        }
    }
}

/// Just the picture, for the island's small corner.
struct ActivityPictureOnly: View {
    let data: Data?
    let height: CGFloat
    let fallback: String
    let tint: Color

    var body: some View {
        if let image = data.flatMap(UIImage.init(data:)), image.size.height > 0 {
            let ratio = min(max(image.size.width / image.size.height, 0.6), 1.4)
            Image(uiImage: image)
                .resizable()
                .aspectRatio(contentMode: .fill)
                .frame(width: height * ratio, height: height)
                .clipShape(RoundedRectangle(cornerRadius: height * 0.22, style: .continuous))
        } else {
            Image(systemName: fallback).foregroundStyle(tint)
        }
    }
}
