import SwiftUI
import UIKit

/// The original on a dark screen of its own, opened filling the screen:
/// pinch out or double-tap to see it whole, pinch or double-tap to look
/// closer, drag to look around, tap to hide the caption.
struct OriginalViewer: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let item: Item
    @State private var image: UIImage?
    @State private var failed = false
    @State private var chrome = true

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            if let image {
                ZoomableImage(image: image) {
                    withAnimation(.easeInOut(duration: 0.2)) { chrome.toggle() }
                }
                .ignoresSafeArea()
            } else if failed {
                Label("Nie udało się wczytać obrazu", systemImage: "photo")
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.7))
            } else {
                ProgressView().tint(.white)
            }
        }
        .overlay(alignment: .topTrailing) {
            if chrome {
                Button {
                    dismiss()
                } label: {
                    Image(systemName: "xmark")
                        .font(.headline)
                        .foregroundStyle(.white)
                        .frame(width: 40, height: 40)
                        .background(.black.opacity(0.5), in: Circle())
                }
                .padding(.trailing, 16)
                .padding(.top, 8)
                .accessibilityLabel("Zamknij")
                .transition(.opacity)
            }
        }
        .overlay(alignment: .bottom) {
            if chrome { caption.transition(.opacity) }
        }
        .statusBarHidden(!chrome)
        .task(id: item.id) { await load() }
    }

    private var caption: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(item.title.isEmpty ? "Bez tytułu" : item.title)
                .font(.serif(19, weight: .semibold))
                .lineLimit(2)
            let line = [Names.artist(item.artist), item.dateText].filter { !$0.isEmpty }.joined(separator: " · ")
            if !line.isEmpty {
                Text(line).font(.footnote).opacity(0.75)
            }
        }
        .foregroundStyle(.white)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, Theme.gutter)
        .padding(.top, 36)
        .padding(.bottom, 12)
        .background(
            LinearGradient(colors: [.clear, .black.opacity(0.65)], startPoint: .top, endPoint: .bottom)
                .ignoresSafeArea()
        )
        .allowsHitTesting(false)
    }

    /// The tile's thumbnail at once (in memory already, so the screen is
    /// never a lone spinner while the original comes), then the copy the
    /// detail screen shows, then a sharper one to zoom into.
    private func load() async {
        if let request = model.backend.request(for: ItemPeeks.tiles[item.id]?.thumb ?? .thumb(item.id)),
           let thumb = try? await ImageLoader.shared.image(for: request, maxPixel: 700, priority: .high) {
            image = thumb
        }
        for maxPixel: CGFloat in [1800, 4096] {
            guard let request = model.backend.request(for: item.originalRef) else { break }
            if let loaded = try? await ImageLoader.shared.image(for: request, maxPixel: maxPixel, priority: .high) {
                image = loaded
            }
            if Task.isCancelled { return }
        }
        failed = image == nil
    }
}

/// A picture in a scroll view, shown filling the view (centred, the sides
/// that do not fit off screen): pinch to zoom, drag around, double-tap to
/// see it whole and to zoom back in on a spot, single tap for `onTap`.
struct ZoomableImage: UIViewRepresentable {
    let image: UIImage
    var onTap: () -> Void = {}

    func makeUIView(context: Context) -> ZoomScrollView { ZoomScrollView() }

    func updateUIView(_ view: ZoomScrollView, context: Context) {
        view.onTap = onTap
        view.show(image)
    }
}

final class ZoomScrollView: UIScrollView, UIScrollViewDelegate {
    private let imageView = UIImageView()
    var onTap: () -> Void = {}
    /// The bounds the picture was last fitted to.
    private var fitted: CGSize = .zero
    /// The zoom at which the picture covers the whole view; it opens there.
    private var fillScale: CGFloat = 1

    init() {
        super.init(frame: .zero)
        delegate = self
        showsVerticalScrollIndicator = false
        showsHorizontalScrollIndicator = false
        contentInsetAdjustmentBehavior = .never
        decelerationRate = .fast
        backgroundColor = .clear
        minimumZoomScale = 1
        maximumZoomScale = 8
        imageView.contentMode = .scaleAspectFit
        addSubview(imageView)

        let double = UITapGestureRecognizer(target: self, action: #selector(doubleTapped(_:)))
        double.numberOfTapsRequired = 2
        addGestureRecognizer(double)
        let single = UITapGestureRecognizer(target: self, action: #selector(tapped))
        single.require(toFail: double)
        addGestureRecognizer(single)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }

    /// A sharper copy of the same picture keeps the zoom and place; another
    /// shape is fitted afresh.
    func show(_ image: UIImage) {
        guard imageView.image !== image else { return }
        let sameShape = imageView.image.map {
            abs($0.size.width / max($0.size.height, 1) - image.size.width / max(image.size.height, 1)) < 0.01
        } ?? false
        imageView.image = image
        if !sameShape {
            fitted = .zero
            setNeedsLayout()
        }
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        guard bounds.size != fitted, bounds.width > 0, bounds.height > 0,
              let size = imageView.image?.size, size.width > 0, size.height > 0
        else { return }
        fitted = bounds.size
        zoomScale = 1
        let scale = min(bounds.width / size.width, bounds.height / size.height)
        imageView.frame = CGRect(x: 0, y: 0, width: size.width * scale, height: size.height * scale)
        contentSize = imageView.frame.size
        let fill = max(bounds.width / imageView.frame.width, bounds.height / imageView.frame.height)
        fillScale = min(maximumZoomScale, max(minimumZoomScale, fill))
        zoomScale = fillScale
        centre()
        // The middle of the picture in the middle of the view.
        contentOffset = CGPoint(x: (contentSize.width - bounds.width) / 2,
                                y: (contentSize.height - bounds.height) / 2)
    }

    /// Keeps a picture smaller than the screen in its middle.
    private func centre() {
        let size = imageView.frame.size
        let x = max(0, (bounds.width - size.width) / 2)
        let y = max(0, (bounds.height - size.height) / 2)
        contentInset = UIEdgeInsets(top: y, left: x, bottom: y, right: x)
    }

    func viewForZooming(in scrollView: UIScrollView) -> UIView? { imageView }

    func scrollViewDidZoom(_ scrollView: UIScrollView) { centre() }

    @objc private func tapped() { onTap() }

    @objc private func doubleTapped(_ gesture: UITapGestureRecognizer) {
        if zoomScale > minimumZoomScale * 1.01 {
            setZoomScale(minimumZoomScale, animated: true)
            return
        }
        let point = gesture.location(in: imageView)
        // Back to filling the screen, or closer when the picture already
        // fills it whole.
        let scale = fillScale > minimumZoomScale * 1.15 ? fillScale : min(maximumZoomScale, 3)
        let size = CGSize(width: bounds.width / scale, height: bounds.height / scale)
        zoom(to: CGRect(x: point.x - size.width / 2, y: point.y - size.height / 2,
                        width: size.width, height: size.height), animated: true)
    }
}
