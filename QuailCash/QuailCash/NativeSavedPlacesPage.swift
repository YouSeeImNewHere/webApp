import SwiftUI
import MapKit

struct SavedPlacesPageView: View {
    @EnvironmentObject private var navigator: AppNavigator
    @StateObject private var store = SavedPlacesStore.shared
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @State private var showNewListSheet = false
    @State private var editingList: SavedPlaceList? = nil

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        AppChromeFrame(
            title: "Saved Places",
            badgeValue: nil,
            selectedTab: nil,
            showsBottomBar: false,
            showsStandaloneBar: false,
            onLeadingTap: { navigator.goBack() },
            onTrailingTap: { showNewListSheet = true },
            trailingIcon: "plus"
        ) {
            Group {
                if store.isLoading && store.lists.isEmpty {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if store.lists.isEmpty {
                    emptyState
                } else {
                    listContent
                }
            }
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            MapReturnBar(
                palette: palette,
                onMapTap: { navigator.show(.map) },
                onHomeTap: { navigator.setRoot(.dashboard) }
            )
        }
        .task { await store.refresh() }
        .sheet(isPresented: $showNewListSheet) { newListSheet }
        .sheet(item: $editingList) { list in editListSheet(list) }
    }

    private var listContent: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                ForEach(store.lists) { list in
                    NavigationLink(value: list) {
                        listRow(list)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(16)
        }
        .navigationDestination(for: SavedPlaceList.self) { list in
            PlaceListDetailView(list: list)
        }
    }

    private func listRow(_ list: SavedPlaceList) -> some View {
        HStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill((Color(hex: list.color) ?? .purple).opacity(0.15))
                    .frame(width: 48, height: 48)
                Text(list.emoji).font(.system(size: 24))
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(list.name)
                    .font(.system(size: 15, weight: .semibold, design: .rounded))
                    .foregroundStyle(.primary)
                Text("\(list.placeCount) \(list.placeCount == 1 ? "place" : "places")")
                    .font(.system(size: 12, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .contextMenu {
            Button { editingList = list } label: { Label("Edit", systemImage: "pencil") }
            Button(role: .destructive) {
                Task { await store.deleteList(list) }
            } label: { Label("Delete List", systemImage: "trash") }
        }
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "bookmark.slash")
                .font(.system(size: 48))
                .foregroundStyle(.secondary)
            Text("No saved lists yet")
                .font(.system(size: 18, weight: .semibold, design: .rounded))
            Text("Create a list and save places from the map.")
                .font(.system(size: 14, design: .rounded))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button { showNewListSheet = true } label: {
                Label("Create a List", systemImage: "plus.circle.fill")
                    .font(.system(size: 15, weight: .semibold, design: .rounded))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 24).padding(.vertical, 12)
                    .background(Color.purple, in: Capsule())
            }.buttonStyle(.plain)
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var newListSheet: some View {
        ListEditorSheet(title: "New List") { name, emoji, color in
            Task { await store.createList(name: name, emoji: emoji, color: color) }
        }
    }

    private func editListSheet(_ list: SavedPlaceList) -> some View {
        ListEditorSheet(title: "Edit List", initialName: list.name, initialEmoji: list.emoji, initialColor: list.color) { name, emoji, color in
            Task {
                var updated = list
                updated.name = name; updated.emoji = emoji; updated.color = color
                await store.updateList(updated)
            }
        }
    }
}

// MARK: - List editor sheet

private struct ListEditorSheet: View {
    let title: String
    var initialName: String = ""
    var initialEmoji: String = "📍"
    var initialColor: String = "#5856D6"
    let onSave: (String, String, String) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var name: String = ""
    @State private var emoji: String = ""
    @State private var selectedColor: String = "#5856D6"

    private let colorOptions: [(String, Color)] = [
        ("#5856D6", .purple), ("#007AFF", .blue), ("#34C759", .green),
        ("#FF9500", .orange), ("#FF3B30", .red), ("#FF2D55", .pink),
        ("#AF52DE", Color(red: 0.69, green: 0.32, blue: 0.87))
    ]

    var body: some View {
        NavigationView {
            Form {
                Section("Name") {
                    HStack {
                        TextField("Emoji", text: $emoji)
                            .frame(width: 40)
                            .multilineTextAlignment(.center)
                        TextField("List name", text: $name)
                    }
                }
                Section("Color") {
                    HStack(spacing: 12) {
                        ForEach(colorOptions, id: \.0) { hex, color in
                            Circle()
                                .fill(color)
                                .frame(width: 28, height: 28)
                                .overlay(Circle().stroke(selectedColor == hex ? Color.primary : Color.clear, lineWidth: 2.5))
                                .onTapGesture { selectedColor = hex }
                        }
                    }
                    .padding(.vertical, 4)
                }
            }
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        onSave(name, emoji.isEmpty ? "📍" : emoji, selectedColor)
                        dismiss()
                    }
                    .disabled(name.isEmpty)
                }
            }
            .onAppear {
                name = initialName
                emoji = initialEmoji == "📍" && initialName.isEmpty ? "" : initialEmoji
                selectedColor = initialColor
            }
        }
    }
}

// MARK: - Place list detail

struct PlaceListDetailView: View {
    let list: SavedPlaceList
    @StateObject private var store = SavedPlacesStore.shared

    private var places: [SavedPlace] { store.placesByList[list.id] ?? [] }

    var body: some View {
        Group {
            if places.isEmpty && !store.isLoading {
                VStack(spacing: 12) {
                    Text(list.emoji).font(.system(size: 48))
                    Text("No places yet")
                        .font(.system(size: 16, weight: .semibold, design: .rounded))
                    Text("Tap the bookmark icon on any place in the map to save it here.")
                        .font(.system(size: 13, design: .rounded))
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 32)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    ForEach(places) { place in
                        PlaceRow(place: place)
                            .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                Button(role: .destructive) {
                                    Task { await store.deletePlace(place) }
                                } label: { Label("Delete", systemImage: "trash") }
                            }
                    }
                }
                .listStyle(.insetGrouped)
            }
        }
        .navigationTitle(list.name)
        .navigationBarTitleDisplayMode(.large)
        .task { await store.loadPlaces(for: list.id) }
    }
}

private struct PlaceRow: View {
    let place: SavedPlace

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(place.name)
                .font(.system(size: 15, weight: .semibold, design: .rounded))
            if !place.address.isEmpty {
                Text(place.address)
                    .font(.system(size: 12, design: .rounded))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            if !place.notes.isEmpty {
                Text(place.notes)
                    .font(.system(size: 12, design: .rounded))
                    .foregroundStyle(.secondary)
                    .italic()
            }
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
        .onTapGesture {
            guard let coord = place.coordinate else { return }
            let mapItem = MKMapItem(placemark: MKPlacemark(coordinate: coord))
            mapItem.name = place.name
            mapItem.openInMaps()
        }
    }
}
