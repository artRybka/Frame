import SwiftUI
import UIKit

/// A card of the grid in Playlisty.
enum GridCard: Hashable, Sendable {
    /// "Propozycje dnia", always first.
    case suggestions
    /// A playlist, or "Kolekcja prywatna" (`AppModel.ownWorksCard`): moved
    /// with a finger.
    case card(Int)
    /// "Ukryte", always last.
    case hidden

    var movable: Int? {
        if case let .card(id) = self { return id }
        return nil
    }
}

/// The cards of Playlisty, two to a row, in a collection view of UIKit's
/// own (Mateusz 2026-11-23: moving the cards jumped, showed the card twice,
/// a big one and a small one, vanished oddly when let go, and a card just
/// moved could not be held again). SwiftUI's drag and drop could do none of
/// that better: the system's own grid lifts a card from its menu into the
/// finger in one move, leaves its place open while the others make room,
/// puts it down where the gap is and takes it again at once, as albums do
/// in Photos. Each card is SwiftUI (`UIHostingConfiguration`); the page
/// around it scrolls, so the grid is as tall as its cards and does not.
struct CardsGrid: UIViewRepresentable {
    let items: [GridCard]
    /// What each card shows, made anew with the page (its counts, covers,
    /// "Na ramce").
    let cells: [GridCard: AnyView]
    /// Changes when what the cards show does: only then they are drawn
    /// anew (the page is made again on every step of its scroll).
    let revision: Int
    /// Each card held: its own card above its menu.
    let previews: [GridCard: AnyView]
    let menus: [GridCard: UIMenu]
    let open: (GridCard) -> Void
    /// The movable cards in their new order, once one was let go.
    let arranged: ([Int]) -> Void
    /// A playlist whose deletion waits for a yes: asked on its card.
    @Binding var deleting: PlaylistSummary?
    let delete: (PlaylistSummary) -> Void

    static let columnSpacing: CGFloat = 16
    static let rowSpacing: CGFloat = 22
    static let radius: CGFloat = 12

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> UICollectionView {
        let view = Grid(frame: .zero, collectionViewLayout: Self.layout())
        view.backgroundColor = .clear
        view.isScrollEnabled = false
        view.clipsToBounds = false  // the cards' shadows
        view.dragInteractionEnabled = true
        view.reorderingCadence = .fast
        view.delegate = context.coordinator
        view.dragDelegate = context.coordinator
        view.dropDelegate = context.coordinator
        context.coordinator.attach(view)
        return view
    }

    func updateUIView(_ view: UICollectionView, context: Context) {
        context.coordinator.grid = self
        context.coordinator.show(items, revision: revision)
        if let deleting { context.coordinator.confirm(deleting) }
    }

    func sizeThatFits(_ proposal: ProposedViewSize, uiView: UICollectionView, context: Context) -> CGSize? {
        guard let width = proposal.width, width > 0 else { return nil }
        let rows = (items.count + 1) / 2
        let height = CGFloat(rows) * Self.cellHeight(width: width)
            + CGFloat(max(rows - 1, 0)) * Self.rowSpacing
        return CGSize(width: width, height: height)
    }

    /// A card: its square cover, 10 pt, and the caption, as tall in every
    /// card (`CardCaption`).
    static func cellHeight(width: CGFloat) -> CGFloat {
        let side = (width - columnSpacing) / 2
        return (side + 10 + Caption.height).rounded(.up)
    }

    private static func layout() -> UICollectionViewCompositionalLayout {
        UICollectionViewCompositionalLayout { _, environment in
            let width = environment.container.effectiveContentSize.width
            let height = cellHeight(width: width)
            let item = NSCollectionLayoutItem(layoutSize: .init(
                widthDimension: .absolute((width - columnSpacing) / 2), heightDimension: .absolute(height)
            ))
            let group = NSCollectionLayoutGroup.horizontal(
                layoutSize: .init(widthDimension: .fractionalWidth(1), heightDimension: .absolute(height)),
                subitems: [item, item]
            )
            group.interItemSpacing = .fixed(columnSpacing)
            let section = NSCollectionLayoutSection(group: group)
            section.interGroupSpacing = rowSpacing
            return section
        }
    }

    /// The caption's height at the reader's text size, measured once for each.
    enum Caption {
        private static var measured: [UIContentSizeCategory: CGFloat] = [:]

        static var height: CGFloat {
            MainActor.assumeIsolated {
                let size = UIApplication.shared.preferredContentSizeCategory
                if let known = measured[size] { return known }
                let host = UIHostingController(rootView: CardCaption { EmptyView() })
                let found = host.sizeThatFits(in: CGSize(width: 200, height: CGFloat.greatestFiniteMagnitude)).height
                measured[size] = found
                return found
            }
        }
    }

    /// Lets the page know when its height may have changed.
    final class Grid: UICollectionView {
        override func traitCollectionDidChange(_ previous: UITraitCollection?) {
            super.traitCollectionDidChange(previous)
            if previous?.preferredContentSizeCategory != traitCollection.preferredContentSizeCategory {
                collectionViewLayout.invalidateLayout()
                invalidateIntrinsicContentSize()
            }
        }
    }

    @MainActor
    final class Coordinator: NSObject, UICollectionViewDelegate, UICollectionViewDragDelegate,
        UICollectionViewDropDelegate
    {
        var grid: CardsGrid?
        private weak var view: UICollectionView?
        private var source: UICollectionViewDiffableDataSource<Int, GridCard>?
        /// The playlist asked about now, so it is asked once.
        private var asking: Int?
        private var drawn: Int?

        func attach(_ view: UICollectionView) {
            self.view = view
            let registration = UICollectionView.CellRegistration<UICollectionViewCell, GridCard> { [weak self] cell, _, card in
                cell.backgroundConfiguration = .clear()
                guard let content = self?.grid?.cells[card] else { return }
                cell.contentConfiguration = UIHostingConfiguration { content }.margins(.all, 0)
            }
            source = UICollectionViewDiffableDataSource(collectionView: view) { view, index, card in
                view.dequeueConfiguredReusableCell(using: registration, for: index, item: card)
            }
        }

        /// The cards as the page has them: moved ones go to their places
        /// (softly, when the order changed elsewhere: "Przesuń na
        /// początek"), every one drawn anew. Not while one is in the finger.
        func show(_ items: [GridCard], revision: Int) {
            guard let source, let view, !view.hasActiveDrag, !view.hasActiveDrop else { return }
            let shown = source.snapshot().itemIdentifiers
            guard shown != items || drawn != revision else { return }
            var snapshot = NSDiffableDataSourceSnapshot<Int, GridCard>()
            snapshot.appendSections([0])
            snapshot.appendItems(items)
            let animate = !shown.isEmpty && shown != items && view.window != nil
            if drawn != revision { snapshot.reconfigureItems(items.filter(shown.contains)) }
            drawn = revision
            source.apply(snapshot, animatingDifferences: animate)
        }

        // MARK: Tap and hold

        func collectionView(_ view: UICollectionView, didSelectItemAt index: IndexPath) {
            view.deselectItem(at: index, animated: true)
            guard let card = source?.itemIdentifier(for: index) else { return }
            grid?.open(card)
        }

        func collectionView(
            _ view: UICollectionView, contextMenuConfigurationForItemsAt indexPaths: [IndexPath], point: CGPoint
        ) -> UIContextMenuConfiguration? {
            guard let index = indexPaths.first, let card = source?.itemIdentifier(for: index),
                  let menu = grid?.menus[card]
            else { return nil }
            var provider: UIContextMenuContentPreviewProvider?
            if let preview = grid?.previews[card] {
                provider = {
                    let host = UIHostingController(rootView: preview)
                    host.view.backgroundColor = .clear
                    host.preferredContentSize = host.sizeThatFits(
                        in: CGSize(width: 320, height: CGFloat.greatestFiniteMagnitude)
                    )
                    return host
                }
            }
            return UIContextMenuConfiguration(
                identifier: index.item as NSNumber, previewProvider: provider, actionProvider: { _ in menu }
            )
        }

        func collectionView(
            _ view: UICollectionView, contextMenuConfiguration configuration: UIContextMenuConfiguration,
            highlightPreviewForItemAt index: IndexPath
        ) -> UITargetedPreview? {
            targeted(view, index)
        }

        func collectionView(
            _ view: UICollectionView, contextMenuConfiguration configuration: UIContextMenuConfiguration,
            dismissalPreviewForItemAt index: IndexPath
        ) -> UITargetedPreview? {
            targeted(view, index)
        }

        /// The card held, with its own rounded corners.
        private func targeted(_ view: UICollectionView, _ index: IndexPath) -> UITargetedPreview? {
            guard let cell = view.cellForItem(at: index) else { return nil }
            let parameters = UIPreviewParameters()
            parameters.backgroundColor = .clear
            parameters.visiblePath = UIBezierPath(roundedRect: cell.bounds, cornerRadius: CardsGrid.radius)
            return UITargetedPreview(view: cell, parameters: parameters)
        }

        // MARK: Moving a card

        func collectionView(
            _ view: UICollectionView, itemsForBeginning session: UIDragSession, at index: IndexPath
        ) -> [UIDragItem] {
            guard let card = source?.itemIdentifier(for: index), let id = card.movable else { return [] }
            let item = UIDragItem(itemProvider: NSItemProvider(object: String(id) as NSString))
            item.localObject = card
            return [item]
        }

        func collectionView(
            _ view: UICollectionView, dragPreviewParametersForItemAt index: IndexPath
        ) -> UIDragPreviewParameters? {
            guard let cell = view.cellForItem(at: index) else { return nil }
            let parameters = UIDragPreviewParameters()
            parameters.backgroundColor = .clear
            parameters.visiblePath = UIBezierPath(roundedRect: cell.bounds, cornerRadius: CardsGrid.radius)
            return parameters
        }

        func collectionView(_ view: UICollectionView, dragSessionIsRestrictedToDraggingApplication session: UIDragSession) -> Bool {
            true
        }

        func collectionView(_ view: UICollectionView, canHandle session: UIDropSession) -> Bool {
            session.localDragSession != nil
        }

        func collectionView(
            _ view: UICollectionView, dropSessionDidUpdate session: UIDropSession,
            withDestinationIndexPath destination: IndexPath?
        ) -> UICollectionViewDropProposal {
            guard session.localDragSession != nil else { return UICollectionViewDropProposal(operation: .forbidden) }
            return UICollectionViewDropProposal(operation: .move, intent: .insertAtDestinationIndexPath)
        }

        /// Never before "Propozycje dnia" nor after "Ukryte".
        func collectionView(
            _ view: UICollectionView, targetIndexPathForMoveOfItemFromOriginalIndexPath original: IndexPath,
            atCurrentIndexPath current: IndexPath, toProposedIndexPath proposed: IndexPath
        ) -> IndexPath {
            clamped(proposed, in: view)
        }

        private func clamped(_ index: IndexPath, in view: UICollectionView) -> IndexPath {
            let items = source?.snapshot().itemIdentifiers ?? []
            let first = items.firstIndex { $0.movable != nil } ?? 0
            let last = items.lastIndex { $0.movable != nil } ?? max(items.count - 1, 0)
            return IndexPath(item: min(max(index.item, first), last), section: 0)
        }

        func collectionView(_ view: UICollectionView, performDropWith coordinator: UICollectionViewDropCoordinator) {
            guard let source, let dropped = coordinator.items.first, let from = dropped.sourceIndexPath,
                  let moving = source.itemIdentifier(for: from)
            else { return }
            let to = clamped(coordinator.destinationIndexPath ?? from, in: view)
            var snapshot = source.snapshot()
            if to != from, let target = source.itemIdentifier(for: to), target != moving {
                if to.item > from.item {
                    snapshot.moveItem(moving, afterItem: target)
                } else {
                    snapshot.moveItem(moving, beforeItem: target)
                }
                source.apply(snapshot, animatingDifferences: false)
            }
            coordinator.drop(dropped.dragItem, toItemAt: to)
            let cards = snapshot.itemIdentifiers.compactMap(\.movable)
            DispatchQueue.main.async { [weak self] in self?.grid?.arranged(cards) }
        }

        // MARK: Deleting

        /// "Usunąć playlistę …?" pointing at its card.
        func confirm(_ playlist: PlaylistSummary) {
            guard asking != playlist.id, let view, let source,
                  let index = source.indexPath(for: .card(playlist.id)),
                  let host = view.window?.rootViewController?.topPresented
            else { return }
            asking = playlist.id
            let sheet = UIAlertController(
                title: "Usunąć playlistę „\(playlist.name)”?", message: nil, preferredStyle: .actionSheet
            )
            sheet.addAction(UIAlertAction(title: "Usuń", style: .destructive) { [weak self] _ in
                self?.asking = nil
                self?.grid?.deleting = nil
                self?.grid?.delete(playlist)
            })
            sheet.addAction(UIAlertAction(title: "Anuluj", style: .cancel) { [weak self] _ in
                self?.asking = nil
                self?.grid?.deleting = nil
            })
            if let popover = sheet.popoverPresentationController {
                let cell = view.cellForItem(at: index)
                popover.sourceView = cell ?? view
                popover.sourceRect = cell?.bounds ?? view.bounds
            }
            host.present(sheet, animated: true)
        }
    }
}

private extension UIViewController {
    var topPresented: UIViewController {
        presentedViewController?.topPresented ?? self
    }
}

/// How far the page is scrolled, for the cards' pictures that drift with it
/// (`parallax()`): read by each card itself, so the grid is not drawn anew
/// on every step of the scroll.
@Observable
final class ScrollLift {
    var value: CGFloat = 0
}

/// A card of the grid with the page's scroll.
struct LiftedCard<Content: View>: View {
    let lift: ScrollLift
    let content: Content

    var body: some View {
        content.environment(\.parallaxLift, lift.value)
    }
}
