import SwiftUI

/// Cropping on a screen of its own, opened by tapping the frame's preview:
/// the frame as large as it fits with the crop windows over it, and under it
/// the window's shape, the automatic crop and "Zapisz kadr". Nothing here
/// scrolls, so a drag always moves the picture.
struct CropScreen: View {
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

    /// The draft as it was when the screen opened, for "Anuluj".
    @State private var original: FramingDraft?
    @State private var loaded: ImageRef?
    @State private var saving = false
    @State private var confirmingDiscard = false

    private var ready: Bool { draft.view?.windows.isEmpty == false }

    var body: some View {
        NavigationStack {
            VStack(spacing: 14) {
                FramedArtwork(ref: preview, aspectRatio: aspectRatio, placeholder: placeholder) {
                    if ready, loaded != nil {
                        CropWindows(itemID: itemID, draft: $draft)
                            .transition(.opacity)
                    }
                }
                .environment(\.artImageLoaded) { ref in
                    guard ref == preview else { return }
                    withAnimation(.easeOut(duration: 0.3)) { loaded = ref }
                }
                .overlay {
                    if loaded != preview {
                        LoadingBadge(text: "Wczytuję podgląd…")
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding(.horizontal, Theme.gutter)
                .padding(.top, 8)

                Text(hint)
                    .font(.caption)
                    .foregroundStyle(Theme.inkSoft)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, Theme.gutter)
                    .contentTransition(.opacity)
                if ready {
                    CropTools(itemID: itemID, draft: $draft)
                }
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
                .frame(maxWidth: 420)
                .padding(.horizontal, Theme.gutter)
                .padding(.bottom, 8)
            }
            .disabled(saving)
            .animation(.easeInOut(duration: 0.2), value: draft.changed)
            .background(Theme.paper)
            .navigationTitle("Kadr")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Anuluj") { cancel() }
                        .disabled(saving)
                }
            }
            .confirmationDialog("Odrzucić zmiany kadru?", isPresented: $confirmingDiscard, titleVisibility: .visible) {
                Button("Odrzuć zmiany", role: .destructive) { discard() }
                Button("Edytuj dalej", role: .cancel) {}
            }
        }
        .onAppear { if original == nil { original = draft } }
        .onChange(of: draft.key) { _, _ in
            // Another picture or presentation came in under it: nothing to crop.
            dismiss()
        }
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
        if await save() { dismiss() }
    }

    private func cancel() {
        if let original, draft != original {
            confirmingDiscard = true
        } else {
            dismiss()
        }
    }

    private func discard() {
        if let original { draft = original }
        dismiss()
    }
}

/// A small round mark in the corner of a picture that opens it larger.
struct CornerBadge: View {
    let systemImage: String

    var body: some View {
        Image(systemName: systemImage)
            .font(.footnote.weight(.semibold))
            .foregroundStyle(Theme.ink)
            .frame(width: 30, height: 30)
            .background(.ultraThinMaterial, in: Circle())
            .overlay(Circle().strokeBorder(Theme.hairline))
            .padding(10)
            .allowsHitTesting(false)
    }
}
