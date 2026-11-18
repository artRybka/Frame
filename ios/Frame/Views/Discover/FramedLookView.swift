import SwiftUI

/// "W ramie" on a work's card (Mateusz 2026-11-17, variant C): a round
/// button beside "Oryginał / Na ramce" shows the work in its frame, its
/// passe-partout or (a print shown without it) its sheet, as the museum
/// photographed it, and back. Only on "Oryginał", only when there is
/// something around the work (`Item.framed`). The frame and the colours
/// keep the work alone.
struct FrameToggle: View {
    let look: FramedLook
    let on: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            FrameGlyph()
                .foregroundStyle(on ? Theme.paper : Theme.ink)
                .frame(width: 34, height: 34)
                .background(on ? Theme.ink : Theme.mat, in: Circle())
                .overlay(Circle().strokeBorder(Theme.hairline.opacity(on ? 0 : 1), lineWidth: 0.5))
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .sensoryFeedback(.selection, trigger: on)
        .accessibilityLabel(look.name)
        .accessibilityValue(on ? "włączone" : "wyłączone")
        .accessibilityAddTraits(.isToggle)
        .accessibilityHint(Text(on ? "Pokazuje samo dzieło" : "Pokazuje dzieło tak, jak je sfotografowano"))
    }
}

/// "W ramie" on the card: the box shows the work alone at `pull` 0 and
/// the work in its frame at 1, the camera pulling back from the work. The
/// work is always its own picture, drawn at its own proportions; the framed
/// photograph lies under it, its opening on the work (Mateusz 2026-11-18:
/// the frame set straight by its own corners gave the work other
/// proportions, and the work "jumped" as the frame went).
struct WorkInFrame<Work: View, Around: View>: View, Animatable {
    var pull: CGFloat
    /// Where the work lies in the framed photograph; nil: the work alone.
    let inner: CGRect?
    @ViewBuilder var work: Work
    @ViewBuilder var around: Around

    var animatableData: CGFloat {
        get { pull }
        set { pull = newValue }
    }

    var body: some View {
        GeometryReader { geo in
            let inner = inner ?? CGRect(x: 0, y: 0, width: 1, height: 1)
            let pull = self.inner == nil ? 0 : pull
            // What of the framed photograph is in the box: the work's own
            // place at 0, the whole photograph at 1.
            let region = CGRect(
                x: inner.minX * (1 - pull), y: inner.minY * (1 - pull),
                width: inner.width + (1 - inner.width) * pull,
                height: inner.height + (1 - inner.height) * pull
            )
            let width = geo.size.width / max(region.width, 0.01)
            let height = geo.size.height / max(region.height, 0.01)
            ZStack(alignment: .topLeading) {
                if self.inner != nil {
                    around
                        .frame(width: width, height: height)
                        .offset(x: -region.minX * width, y: -region.minY * height)
                }
                work
                    .frame(width: inner.width * width, height: inner.height * height)
                    .offset(x: (inner.minX - region.minX) * width, y: (inner.minY - region.minY) * height)
            }
            .frame(width: geo.size.width, height: geo.size.height, alignment: .topLeading)
        }
        .clipped()
    }
}

/// The full-screen viewer's button for the same (under the cross, as the
/// buttons of what was done to the picture).
struct FrameViewerButton: View {
    let look: FramedLook
    let on: Bool
    let loading: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            ZStack {
                if loading {
                    ProgressView().tint(.white).controlSize(.small)
                } else {
                    FrameGlyph(scale: 1.08)
                        .foregroundStyle(on ? .white : .white.opacity(0.4))
                }
            }
            .frame(width: 40, height: 40)
            .background(.black.opacity(0.5), in: Circle())
            .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(look.name)
        .accessibilityValue(on ? "włączone" : "wyłączone")
        .accessibilityAddTraits(.isToggle)
    }
}

/// The buttons' icon (Mateusz 2026-11-17, „4” of nine on the sheet): a
/// passe-partout, its edge drawn and a small picture in the middle. SF
/// Symbols has none that reads as a frame without a landscape in it.
struct FrameGlyph: View {
    var scale: CGFloat = 1

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 1.5 * scale)
                .strokeBorder(lineWidth: 1.6 * scale)
            Rectangle()
                .frame(width: 7 * scale, height: 5.5 * scale)
        }
        .frame(width: 18 * scale, height: 15 * scale)
        .accessibilityHidden(true)
    }
}
