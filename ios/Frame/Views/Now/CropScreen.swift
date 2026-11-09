import SwiftUI

/// Cropping on a screen of its own, opened by tapping the frame's preview:
/// the frame as large as it fits with the crop windows over it, and under it
/// the window's shape, then "Kadr automatyczny" beside "Zapisz kadr". Nothing
/// here scrolls, so a drag always moves the picture, and nothing comes or
/// goes while cropping, so the picture keeps its size.
struct CropScreen: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let itemID: String
    /// The preview under the windows; it follows the draft, as a new window
    /// shape needs a new mat.
    let preview: ImageRef?
    let aspectRatio: CGFloat
    var placeholder: Color = Theme.mat
    /// The picture is on the frame now, so saving redraws it there.
    var onFrame = false
    @Binding var draft: FramingDraft
    /// Saves the crop; false (it failed) keeps the screen open.
    let save: () async -> Bool
    /// Where the preview it opened from is on the screen (global): the
    /// frame comes out of it and goes back onto it. Presented and dismissed
    /// without the system's animation (`CropScreen.present`).
    var home: CGRect?
    /// Closes it where it was opened (the binding there set to false), with
    /// the system's animation off: `dismiss()` kept it on, so the empty
    /// screen still slid away as a cream card with the frame in it, over
    /// the preview already shown again (two frames for a moment).
    var onClose: (() -> Void)?
    /// The frame is leaving its preview: the preview there hides now, not
    /// as the screen is asked for (hidden at the tap, it could leave an
    /// empty place for a frame before this screen was up). Until then the
    /// frame here lies on it casting no shadow, so the two don't darken.
    var onOpen: (() -> Void)?

    init(
        itemID: String, preview: ImageRef?, aspectRatio: CGFloat, placeholder: Color = Theme.mat,
        onFrame: Bool = false, draft: Binding<FramingDraft>, save: @escaping () async -> Bool, home: CGRect? = nil,
        previewLoaded: ImageRef? = nil, onOpen: (() -> Void)? = nil, onClose: (() -> Void)? = nil,
        homeGrow: CGFloat = 1
    ) {
        self.itemID = itemID
        self.preview = preview
        self.aspectRatio = aspectRatio
        self.placeholder = placeholder
        self.onFrame = onFrame
        _draft = draft
        self.save = save
        self.home = home
        self.onOpen = onOpen
        self.onClose = onClose
        // The preview the parent shows already: the windows are up from
        // the first frame, not dropped in halfway through the flight with
        // "Wczytuję podgląd…" over it for a moment.
        _loaded = State(initialValue: previewLoaded)
        _away = State(initialValue: onOpen == nil)
        _atHome = State(initialValue: home != nil)
        _grow = State(initialValue: homeGrow)
    }

    /// Opens or closes it with no animation of the system's: the screen
    /// itself flies the frame out of its preview and back.
    static func present(_ change: () -> Void) {
        var transaction = Transaction()
        transaction.disablesAnimations = true
        withTransaction(transaction, change)
    }

    /// The draft as it was when the screen opened, for "Anuluj".
    @State private var original: FramingDraft?
    @State private var loaded: ImageRef?
    /// The frame has left its preview (`onOpen`) and casts its own shadow.
    @State private var away: Bool
    /// `preview` as the parent has it now: closing waits for the saved
    /// crop's, which `self` in a task started before saving does not know.
    @State private var latest: ImageRef?
    @State private var saving = false
    @State private var confirmingDiscard = false
    /// A landscape frame lies on its side here, larger on the upright
    /// phone: it turns as the screen grows out of the preview, and turns
    /// back before the screen shrinks into it again.
    @State private var turned = false
    /// Closing: the frame turning back, nothing more to press.
    @State private var closing = false
    /// The frame sits on the preview it came from (as the screen opens and
    /// once it has gone back), with the page and controls faded out.
    @State private var atHome: Bool
    @State private var shown = false
    /// The last moment: the frame on the preview goes with the screen, as
    /// the preview under it shows again.
    @State private var gone = false
    /// The preview held open is grown a touch (`PressHold.pictureGrow`):
    /// the frame starts at that size, not with a small jump back.
    @State private var grow: CGFloat

    private var ready: Bool { draft.view?.windows.isEmpty == false }

    var body: some View {
        VStack(spacing: 14) {
            header
                .opacity(shown ? 1 : 0)
            GeometryReader { geo in
                let turn = turned && turns(in: geo.size)
                // Turned, it is laid out in the space with its sides swapped.
                let box = turn ? CGSize(width: geo.size.height, height: geo.size.width) : geo.size
                FramedArtwork(ref: preview, aspectRatio: aspectRatio, placeholder: placeholder, shadow: false) {
                    if ready, loaded != nil {
                        CropWindows(itemID: itemID, draft: $draft)
                            // On the preview it lands as the preview itself,
                            // not as the windows drawn here (a small jump).
                            .opacity(atHome ? 0 : 1)
                            .transition(.opacity)
                    }
                }
                .environment(\.artImageLoaded) { ref in
                    guard ref == preview else { return }
                    withAnimation(.easeOut(duration: 0.3)) { loaded = ref }
                }
                .environment(\.cropTurned, turn)
                .frame(width: box.width, height: box.height)
                .rotationEffect(.degrees(turn ? 90 : 0))
                // Cast after the turn, so it keeps falling down.
                .frameShadow(away)
                .modifier(AtHome(move: atHome ? homeMove(in: geo) : nil))
                .opacity(gone ? 0 : 1)
                .frame(width: geo.size.width, height: geo.size.height)
                .overlay {
                    if loaded != preview, !closing {
                        LoadingBadge(text: "Wczytuję podgląd…")
                    }
                }
            }
            .padding(.horizontal, Theme.gutter)
            .padding(.top, 8)

            Group {
                Text(hint)
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .multilineTextAlignment(.center)
                    .lineLimit(2, reservesSpace: true)
                    .padding(.horizontal, Theme.gutter)
                    .contentTransition(.opacity)
                if ready {
                    CropTools(draft: $draft)
                }
                HStack(spacing: 10) {
                    Button {
                        Task { await automaticCrop() }
                    } label: {
                        Text("Kadr automatyczny")
                            .lineLimit(1)
                            .minimumScaleFactor(0.8)
                    }
                    .buttonStyle(SecondaryButtonStyle())
                    .disabled(!ready || !draft.offAutomatic || saving)
                    .opacity(ready && draft.offAutomatic ? 1 : 0.45)
                    Button {
                        Task { await saveAndClose() }
                    } label: {
                        HStack(spacing: 10) {
                            if saving { ProgressView().tint(Theme.paper) }
                            Text("Zapisz kadr")
                        }
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(!draft.changed || saving)
                    .opacity(draft.changed || saving ? 1 : 0.45)
                }
                .frame(maxWidth: 420)
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, 8)
            }
            .opacity(shown ? 1 : 0)
        }
        .disabled(saving || closing)
        .animation(.easeInOut(duration: 0.2), value: draft.changed)
        .animation(.easeInOut(duration: 0.2), value: draft.offAutomatic)
        // The page behind it fades in and out with the controls, so the frame
        // is seen to come out of its preview and go back onto it.
        .background {
            Color.clear.paperPage()
                .opacity(shown ? 1 : 0)
        }
        .presentationBackground(.clear)
        .onAppear { if original == nil { original = draft } }
        .onChange(of: preview, initial: true) { latest = preview }
        .task {
            // One frame on the preview first, so it is seen to come out of it.
            try? await Task.sleep(for: .seconds(0.03))
            // The preview there hides as this frame takes its shadow over.
            Self.present {
                away = true
                onOpen?()
            }
            withAnimation(Self.out) {
                atHome = false
                shown = true
                grow = 1
            }
            withAnimation(Self.turnIn) { turned = true }
        }
        .onChange(of: draft.key) { _, _ in
            // Another picture or presentation came in under it: nothing to crop.
            dismiss()
        }
    }

    /// "Anuluj", where a navigation bar would have it: a bar of its own, so
    /// it fades with the rest while the frame flies. No title: the frame
    /// says what the screen is (Mateusz 2026-11-07).
    private var header: some View {
        HStack {
            Button("Anuluj") { cancel() }
                .buttonStyle(.glass)
                .disabled(saving || closing)
                .confirmationDialog("Odrzucić zmiany kadru?", isPresented: $confirmingDiscard, titleVisibility: .visible) {
                    Button("Odrzuć zmiany", role: .destructive) { discard() }
                    Button("Edytuj dalej", role: .cancel) {}
                }
            Spacer()
        }
        .padding(.horizontal, Theme.gutter)
        .padding(.top, 6)
    }

    /// How the frame here gets onto the preview it came from: the same middle,
    /// at its size (the frame unturned, as it is when it flies).
    private func homeMove(in geo: GeometryProxy) -> AtHome.Move? {
        guard let home, home.width > 0 else { return nil }
        let space = geo.frame(in: .global)
        let width = Moulding.fitted(aspectRatio, in: space.size).width
        guard width > 0 else { return nil }
        return AtHome.Move(
            // The moulding is in proportion, so the frame scaled down is the
            // preview's own, moulding and all.
            scale: home.width / width * grow,
            offset: CGSize(width: home.midX - space.midX, height: home.midY - space.midY)
        )
    }

    /// A landscape frame turns where the space is upright, so it comes out
    /// larger (a 16:9 frame across a phone's width is a narrow strip).
    private func turns(in size: CGSize) -> Bool {
        aspectRatio > 1 && size.height > size.width
    }

    private var hint: String {
        guard draft.changed else {
            return "Przesuń obraz palcem albo rozsuń dwa palce, żeby go wykadrować."
        }
        return onFrame
            ? "Po zapisaniu ramka od razu pokaże nowy kadr."
            : "Zapisany kadr ramka pokaże, gdy obraz trafi na nią w tym ustawieniu."
    }

    private func saveAndClose() async {
        saving = true
        defer { saving = false }
        if await save() { await close() }
    }

    /// Back on its place: a turned frame turns back, then it goes quickly
    /// onto the preview it came from while the page fades, and only then
    /// does the screen go (the preview under it is the same, so nothing
    /// blinks; the system's zoom shrank the whole screen and then swapped).
    private func close() async {
        guard !closing else { return }
        closing = true
        // A saved crop's preview first, so it lands as the card will show it.
        // At least a moment: the parent hands over the saved crop's preview
        // in the next update after saving.
        let waited = ContinuousClock.now
        repeat {
            try? await Task.sleep(for: .seconds(0.05))
        } while loaded != latest && ContinuousClock.now - waited < .seconds(2)
        if turned, aspectRatio > 1 {
            await animate(Self.turnBack, until: .logicallyComplete) { turned = false }
        }
        // To the very end: swapped while a spring still crept, it jumped.
        await animate(Self.back, until: .removed) {
            atHome = home != nil
            shown = false
        }
        Self.present {
            gone = true
            if let onClose { onClose() } else { dismiss() }
        }
    }

    /// Quick, so the frame is on its side by the time the screen has popped
    /// out (the frame's own turn, 0.6 s, was too slow here).
    private static let turnIn = Animation.spring(duration: 0.28, bounce: 0)
    /// Back again before the frame goes onto the preview.
    private static let turnBack = Animation.spring(duration: 0.35, bounce: 0)
    /// Out of the preview, as the screen opens.
    /// No bounce: overshooting, the frame seemed to jump.
    private static let out = Animation.spring(duration: 0.35, bounce: 0)
    /// Back onto it: quick, but no bounce, so it settles right on it.
    private static let back = Animation.spring(duration: 0.3, bounce: 0)

    /// Runs `change` with `animation` and returns once it is `until`.
    private func animate(_ animation: Animation, until: AnimationCompletionCriteria, _ change: () -> Void) async {
        await withCheckedContinuation { (done: CheckedContinuation<Void, Never>) in
            withAnimation(animation, completionCriteria: until, change) { done.resume() }
        }
    }

    /// Back to the crop the server would choose; "Zapisz kadr" keeps it.
    private func automaticCrop() async {
        guard draft.custom else {
            draft.crops = draft.saved  // the saved crop is the automatic one
            draft.automatic = nil
            return
        }
        guard let view = draft.view else { return }
        let key = draft.key
        do {
            let auto = try await model.backend.framing(itemID: itemID, orientation: view.orientation, automatic: true)
            guard key == draft.key, auto.windows.count == draft.crops.count else { return }
            draft.automatic = auto.windows.map(\.crop)
            draft.crops = auto.windows.map(\.crop)
        } catch {
            model.show(error)
        }
    }

    private func cancel() {
        if let original, draft != original {
            confirmingDiscard = true
        } else {
            Task { await close() }
        }
    }

    private func discard() {
        if let original { draft = original }
        Task { await close() }
    }
}

/// The crop screen's frame moved onto the preview it came from.
private struct AtHome: ViewModifier {
    struct Move: Equatable {
        var scale: CGFloat
        var offset: CGSize
    }

    let move: Move?

    func body(content: Content) -> some View {
        content
            .scaleEffect(move?.scale ?? 1)
            .offset(move?.offset ?? .zero)
    }
}
