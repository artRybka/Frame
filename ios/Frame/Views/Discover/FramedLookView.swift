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
            Image(systemName: "photo.artframe")
                .font(.system(size: 15, weight: .semibold))
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

/// The framed photograph shown so that `pull` 0 fills the box with the
/// work alone (`inner`, where it is in the photograph) and 1 shows the
/// photograph whole: the camera pulling back from the work to its frame.
struct PullBack: ViewModifier, Animatable {
    var pull: CGFloat
    let inner: CGRect

    var animatableData: CGFloat {
        get { pull }
        set { pull = newValue }
    }

    func body(content: Content) -> some View {
        GeometryReader { geo in
            let shown = 1 - pull
            let region = CGRect(
                x: inner.minX * shown, y: inner.minY * shown,
                width: inner.width + (1 - inner.width) * pull,
                height: inner.height + (1 - inner.height) * pull
            )
            let width = geo.size.width / max(region.width, 0.01)
            let height = geo.size.height / max(region.height, 0.01)
            content
                .frame(width: width, height: height)
                .offset(x: -region.minX * width, y: -region.minY * height)
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
                    Image(systemName: "photo.artframe")
                        .font(.system(size: 16, weight: .semibold))
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
