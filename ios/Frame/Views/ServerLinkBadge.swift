import SwiftUI

/// Whether the app reaches the server, at the top of every tab: a spinner
/// while it connects (also while it tries again), "Bez połączenia" once it
/// surely did not, and a tap tries again; nothing while connected.
struct ServerLinkBadge: View {
    @Environment(AppModel.self) private var model
    /// "Teraz" still shows the last launch's picture although the server
    /// answers (its "Teraz" did not load): a tap loads it again.
    var stale = false

    private enum Look {
        case spinner, offline, reload
    }

    private var look: Look? {
        switch model.serverLink {
        case .connecting: .spinner
        case .offline: .offline
        case .online: stale ? .reload : nil
        }
    }

    var body: some View {
        if let look {
            Button {
                Task { await model.refreshAll() }
            } label: {
                Group {
                    switch look {
                    case .spinner:
                        ProgressView().controlSize(.small)
                            .frame(width: 34)
                    case .offline:
                        HStack(spacing: 7) {
                            Image(systemName: "wifi.slash")
                            Text("Bez połączenia")
                                .fixedSize()
                        }
                        .padding(.horizontal, 12)
                    case .reload:
                        Image(systemName: "arrow.clockwise")
                            .frame(width: 34)
                    }
                }
                .font(.footnote.weight(.medium))
                .foregroundStyle(Theme.inkSoft)
                .frame(height: 34)
                .background(.ultraThinMaterial, in: Capsule())
                .contentShape(Capsule())
            }
            .buttonStyle(.plain)
            .disabled(look == .spinner)
            .animation(.easeInOut(duration: 0.2), value: look)
            .accessibilityLabel(label(look))
            .accessibilityHint(Text(look == .spinner ? "" : "Próbuje ponownie połączyć się z serwerem"))
        }
    }

    private func label(_ look: Look) -> String {
        switch look {
        case .spinner: "Łączę z serwerem"
        case .offline: "Bez połączenia z serwerem"
        case .reload: "Odśwież"
        }
    }
}

extension View {
    /// `ServerLinkBadge` at the leading end of the navigation bar, while it
    /// has something to say; `hidden` where the page says it itself.
    func serverLinkBadge(hidden: Bool = false, stale: Bool = false) -> some View {
        modifier(ServerLinkBadgeItem(hidden: hidden, stale: stale))
    }
}

private struct ServerLinkBadgeItem: ViewModifier {
    @Environment(AppModel.self) private var model
    let hidden: Bool
    let stale: Bool

    private var shown: Bool {
        !hidden && (model.serverLink != .online || stale)
    }

    func body(content: Content) -> some View {
        content.toolbar {
            if shown {
                ToolbarItem(placement: .topBarLeading) {
                    ServerLinkBadge(stale: stale)
                }
            }
        }
    }
}
