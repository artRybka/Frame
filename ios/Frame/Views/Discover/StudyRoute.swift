import SwiftUI

/// "Otwórz studium" pushes the study as a value on the stack the card is on,
/// with the cards it leads to on top of it. A study shown with
/// `navigationDestination(isPresented:)` was dropped by the first value
/// pushed from it, so a tapped work in "Inne prace artysty" brought back the
/// studied work's card instead of its own.
private struct OpenStudyKey: EnvironmentKey {
    static let defaultValue: ((String) -> Void)? = nil
}

extension EnvironmentValues {
    /// Pushes the study of the work with this id; nil off a stack that set
    /// none (the study then opens in a sheet).
    var openStudy: ((String) -> Void)? {
        get { self[OpenStudyKey.self] }
        set { self[OpenStudyKey.self] = newValue }
    }
}

extension View {
    /// On a `NavigationStack` (with a `DailyRoute` destination) whose cards
    /// open their studies on `path`.
    func opensStudies(on path: Binding<NavigationPath>) -> some View {
        environment(\.openStudy) { itemID in
            path.wrappedValue.append(DailyRoute(day: nil, study: itemID))
        }
    }
}
