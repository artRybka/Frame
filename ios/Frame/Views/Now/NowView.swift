import CoreLocation
import SwiftUI

/// Home: the picture on the frame, presented like an exhibit.
struct NowView: View {
    @Environment(AppModel.self) private var model
    @State private var showingSend = LaunchRoute.screen == "send"
    @State private var path = NavigationPath()

    private var current: NowShowing? { model.player?.current }
    private var item: Item? { current?.item }

    var body: some View {
        NavigationStack(path: $path) {
            ZStack {
                AmbientBackground(swatches: item?.colors ?? [])
                ScrollView {
                    VStack(alignment: .leading, spacing: 26) {
                        header
                        hero
                        controls
                        if let item {
                            ArtworkInfo(item: item)
                        } else if let current {
                            Card {
                                Text(current.title.isEmpty ? "Bez tytułu" : current.title)
                                    .font(.serif(26, weight: .semibold))
                                if !current.description.isEmpty {
                                    Text(current.description).foregroundStyle(Theme.inkSoft)
                                }
                            }
                        }
                        if let upcoming = model.player?.upcoming, !upcoming.isEmpty {
                            Strip(title: "Następne", items: upcoming)
                        }
                        if let history = model.player?.history, !history.isEmpty {
                            Strip(title: "Ostatnio na ramce", items: history)
                        }
                    }
                    .padding(.horizontal, Theme.gutter)
                    .padding(.bottom, 40)
                }
                .refreshable { await model.refreshAll() }
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showingSend = true
                    } label: {
                        Image(systemName: "plus")
                            .font(.headline)
                            .frame(width: 34, height: 34)
                            .background(.ultraThinMaterial, in: Circle())
                    }
                    .accessibilityLabel("Wyślij zdjęcie na ramkę")
                }
            }
            .navigationDestination(for: String.self) { id in
                ItemDetailView(itemID: id)
            }
            .sheet(isPresented: $showingSend) {
                SendSheet()
            }
        }
    }

    // MARK: Header

    private var header: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 4) {
                Eyebrow(model.status?.device.name.map { "Na ramce · \($0)" } ?? "Na ramce")
                Text(sourceTitle)
                    .font(.serif(17, weight: .medium))
                    .foregroundStyle(Theme.ink)
                    .lineLimit(1)
            }
            Spacer(minLength: 12)
            StatusCluster(status: model.status?.device)
        }
        .padding(.top, 6)
    }

    private var sourceTitle: String {
        if model.player?.mode == "album" { return "Album rodzinny" }
        return model.player?.playlist?.name ?? "Cała biblioteka"
    }

    // MARK: Hero

    private var heroRef: ImageRef? {
        if let current { return .path(current.previewUrl) }
        return nil
    }

    @ViewBuilder
    private var hero: some View {
        let aspect: CGFloat = model.isPortrait ? 9.0 / 16.0 : 16.0 / 9.0
        Group {
            if let heroRef {
                FramedArtwork(
                    ref: heroRef, aspectRatio: aspect, placeholder: item?.placeholderColor ?? Theme.mat
                )
                .onTapGesture {
                    if let id = item?.id { path.append(id) }
                }
            } else {
                FramedArtwork(ref: nil, aspectRatio: aspect)
                    .overlay {
                        if model.connection != .connected {
                            ProgressView()
                        }
                    }
            }
        }
        .frame(maxWidth: model.isPortrait ? 260 : .infinity)
        .frame(maxWidth: .infinity)
        .overlay {
            if model.working || model.player?.busy == true {
                VStack(spacing: 10) {
                    ProgressView().tint(.white)
                    Text("Przygotowuję obraz…")
                        .font(.footnote.weight(.medium))
                        .foregroundStyle(.white)
                }
                .padding(18)
                .background(.black.opacity(0.45), in: RoundedRectangle(cornerRadius: 14))
            }
        }
        .animation(.easeInOut, value: model.working)
    }

    // MARK: Controls

    private var controls: some View {
        VStack(spacing: 14) {
            HStack(spacing: 22) {
                GlassButton(systemImage: "backward.fill", label: "Poprzedni") {
                    Task { await model.previous() }
                }
                pinMenu
                GlassButton(systemImage: "forward.fill", label: "Następny") {
                    Task { await model.next() }
                }
            }
            .disabled(model.working)
            Text(scheduleLine)
                .font(.footnote)
                .foregroundStyle(Theme.inkSoft)
        }
        .frame(maxWidth: .infinity)
    }

    private var isHeld: Bool { model.player?.hold != nil }

    private var pinMenu: some View {
        Menu {
            if isHeld {
                Button("Odepnij", systemImage: "pin.slash") { Task { await model.releaseHold() } }
            }
            Section("Zatrzymaj ten obraz") {
                ForEach([HoldSpec.oneHour, .threeHours, .oneDay, .forever]) { spec in
                    Button(spec.label) { Task { await model.hold(spec) } }
                }
            }
        } label: {
            Image(systemName: isHeld ? "pin.fill" : "pin")
                .font(.system(size: 26, weight: .semibold))
                .foregroundStyle(isHeld ? Theme.paper : Theme.ink)
                .frame(width: 72, height: 72)
                .background(isHeld ? AnyShapeStyle(Theme.vermilion) : AnyShapeStyle(.ultraThinMaterial), in: Circle())
                .overlay(Circle().strokeBorder(Color.white.opacity(0.35)))
                .shadow(color: .black.opacity(0.14), radius: 12, y: 7)
        }
        .accessibilityLabel(isHeld ? "Przypięte" : "Przypnij")
    }

    private var scheduleLine: String {
        guard let player = model.player else { return " " }
        if let hold = player.hold {
            if hold.forever { return "Przypięty na stałe" }
            if let until = When.schedule(hold.until) { return "Przypięty do: \(until)" }
        }
        if let next = When.schedule(player.nextChangeAt) { return "Następna zmiana: \(next)" }
        return " "
    }
}

/// Battery and connection at a glance.
struct StatusCluster: View {
    let status: DeviceStatus?

    var body: some View {
        HStack(spacing: 8) {
            if let level = status?.batteryLevel {
                HStack(spacing: 4) {
                    Image(systemName: Self.batteryIcon(level: level, charging: status?.charging == true))
                        .symbolRenderingMode(.hierarchical)
                    Text("\(level)%").monospacedDigit()
                }
                .foregroundStyle(level <= 15 ? Theme.bad : Theme.ink)
            }
            Circle()
                .fill(connectionColor)
                .frame(width: 8, height: 8)
                .overlay(Circle().stroke(connectionColor.opacity(0.35), lineWidth: 4))
        }
        .font(.footnote.weight(.semibold))
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.ultraThinMaterial, in: Capsule())
        .accessibilityElement(children: .combine)
    }

    private var connectionColor: Color {
        switch status?.reachable {
        case .some(true): Theme.good
        case .some(false): Theme.bad
        case .none: Theme.warn
        }
    }

    static func batteryIcon(level: Int, charging: Bool) -> String {
        if charging { return "battery.100percent.bolt" }
        switch level {
        case ..<13: return "battery.0percent"
        case ..<38: return "battery.25percent"
        case ..<63: return "battery.50percent"
        case ..<88: return "battery.75percent"
        default: return "battery.100percent"
        }
    }
}

/// Museum-label style description of the current picture.
struct ArtworkInfo: View {
    @Environment(AppModel.self) private var model
    let item: Item
    @State private var expanded = false
    @State private var favorite: Bool?

    var body: some View {
        Card(padding: 22) {
            HStack(alignment: .top) {
                Eyebrow(Names.kind(item.kind), color: Theme.vermilion)
                Spacer()
                Button {
                    Task {
                        let new = !(favorite ?? item.favorite)
                        favorite = new
                        _ = await model.setFavorite(item.id, new)
                    }
                } label: {
                    Image(systemName: (favorite ?? item.favorite) ? "heart.fill" : "heart")
                        .font(.title3)
                        .foregroundStyle((favorite ?? item.favorite) ? Theme.vermilion : Theme.inkSoft)
                        .contentTransition(.symbolEffect(.replace))
                }
                .accessibilityLabel("Ulubione")
            }
            Text(item.title.isEmpty ? "Bez tytułu" : item.title)
                .font(.serif(28, weight: .semibold))
                .foregroundStyle(Theme.ink)
                .fixedSize(horizontal: false, vertical: true)
            if item.kind == .photo {
                PhotoFacts(item: item)
            } else {
                VStack(alignment: .leading, spacing: 3) {
                    if !item.artist.isEmpty {
                        Text(item.artist).font(.serif(18)).foregroundStyle(Theme.ink)
                    }
                    if !item.artistBio.isEmpty {
                        Text(item.artistBio).font(.subheadline).foregroundStyle(Theme.inkSoft)
                    }
                }
                Text([item.dateText, item.medium].filter { !$0.isEmpty }.joined(separator: " · "))
                    .font(.subheadline)
                    .foregroundStyle(Theme.inkSoft)
            }
            if !item.colors.isEmpty {
                PaletteStrip(swatches: item.colors)
                    .padding(.vertical, 4)
            }
            if !item.description.isEmpty {
                Text(item.description)
                    .font(.serif(16))
                    .lineSpacing(4)
                    .foregroundStyle(Theme.ink.opacity(0.88))
                    .lineLimit(expanded ? nil : 5)
                Button(expanded ? "Zwiń" : "Czytaj więcej") {
                    withAnimation(.easeInOut) { expanded.toggle() }
                }
                .font(.subheadline.weight(.semibold))
            }
            HStack {
                if !item.museum.isEmpty {
                    Label(item.museum, systemImage: "building.columns")
                        .font(.caption)
                        .foregroundStyle(Theme.inkSoft)
                        .lineLimit(1)
                }
                Spacer()
                NavigationLink(value: item.id) {
                    Text("Szczegóły")
                        .font(.subheadline.weight(.semibold))
                }
            }
        }
    }
}

/// Date, place and who added a family photo.
struct PhotoFacts: View {
    let item: Item
    @State private var place: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let taken = When.long(item.photo?.takenAt) ?? (item.dateText.isEmpty ? nil : item.dateText) {
                Label(taken, systemImage: "calendar")
            }
            if let place {
                Label(place, systemImage: "mappin.and.ellipse")
            }
            if let who = item.photo?.contributor ?? (item.artist.isEmpty ? nil : item.artist) {
                Label("Dodał(a): \(who)", systemImage: "person.crop.circle")
            }
            if let caption = item.photo?.caption, !caption.isEmpty {
                Text("„\(caption)”").font(.serif(17)).italic()
            }
        }
        .font(.subheadline)
        .foregroundStyle(Theme.ink)
        .task(id: item.id) { await geocode() }
    }

    private func geocode() async {
        guard let lat = item.photo?.latitude, let lon = item.photo?.longitude else { return }
        let marks = try? await CLGeocoder().reverseGeocodeLocation(
            CLLocation(latitude: lat, longitude: lon), preferredLocale: Locale(identifier: "pl_PL")
        )
        if let mark = marks?.first {
            place = [mark.locality ?? mark.name, mark.country].compactMap { $0 }.joined(separator: ", ")
        }
    }
}

/// Horizontal row of small pictures.
struct Strip: View {
    let title: String
    let items: [ItemSummary]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Eyebrow(title)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 14) {
                    ForEach(items) { item in
                        NavigationLink(value: item.id) {
                            VStack(alignment: .leading, spacing: 6) {
                                ArtImage(ref: .thumb(item.id), placeholder: item.placeholderColor, maxPixel: 400)
                                    .frame(width: 120, height: 92)
                                    .clipShape(RoundedRectangle(cornerRadius: 5, style: .continuous))
                                    .shadow(color: .black.opacity(0.12), radius: 6, y: 4)
                                Text(item.title)
                                    .font(.serif(13, weight: .medium))
                                    .foregroundStyle(Theme.ink)
                                    .lineLimit(2)
                                    .frame(width: 120, alignment: .leading)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.vertical, 4)
            }
            .scrollClipDisabled()
        }
    }
}
