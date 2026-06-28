import Foundation
import Combine
import CoreLocation

struct SavedPlaceList: Identifiable, Codable, Equatable, Hashable {
    var id: Int
    var name: String
    var emoji: String
    var color: String
    var placeCount: Int
    var createdAt: String

    static func from(_ d: [String: Any]) -> SavedPlaceList? {
        guard let id = d["id"] as? Int, let name = d["name"] as? String else { return nil }
        return SavedPlaceList(
            id: id, name: name,
            emoji: d["emoji"] as? String ?? "📍",
            color: d["color"] as? String ?? "#5856D6",
            placeCount: d["place_count"] as? Int ?? 0,
            createdAt: d["created_at"] as? String ?? ""
        )
    }
}

struct SavedPlace: Identifiable, Codable, Equatable {
    var id: Int
    var listId: Int
    var name: String
    var address: String
    var latitude: Double?
    var longitude: Double?
    var notes: String
    var savedAt: String

    var coordinate: CLLocationCoordinate2D? {
        guard let lat = latitude, let lon = longitude else { return nil }
        return CLLocationCoordinate2D(latitude: lat, longitude: lon)
    }

    static func from(_ d: [String: Any]) -> SavedPlace? {
        guard let id = d["id"] as? Int, let name = d["name"] as? String else { return nil }
        return SavedPlace(
            id: id,
            listId: d["list_id"] as? Int ?? 0,
            name: name,
            address: d["address"] as? String ?? "",
            latitude: d["latitude"] as? Double,
            longitude: d["longitude"] as? Double,
            notes: d["notes"] as? String ?? "",
            savedAt: d["saved_at"] as? String ?? ""
        )
    }
}

@MainActor
final class SavedPlacesStore: ObservableObject {
    static let shared = SavedPlacesStore()

    @Published var lists: [SavedPlaceList] = []
    @Published var placesByList: [Int: [SavedPlace]] = [:]
    @Published var isLoading = false

    func refresh() async {
        isLoading = true
        defer { isLoading = false }
        guard let raw = try? await QuailCashAPI.shared.fetchSavedPlaceLists() else { return }
        lists = raw.compactMap(SavedPlaceList.from)
    }

    func loadPlaces(for listId: Int) async {
        guard let raw = try? await QuailCashAPI.shared.fetchSavedPlaces(listId: listId) else { return }
        placesByList[listId] = raw.compactMap(SavedPlace.from)
    }

    func createList(name: String, emoji: String, color: String) async {
        guard let raw = try? await QuailCashAPI.shared.createSavedPlaceList(name: name, emoji: emoji, color: color),
              let list = SavedPlaceList.from(raw) else { return }
        lists.append(list)
    }

    func updateList(_ list: SavedPlaceList) async {
        try? await QuailCashAPI.shared.updateSavedPlaceList(list.id, name: list.name, emoji: list.emoji, color: list.color)
        if let idx = lists.firstIndex(where: { $0.id == list.id }) {
            lists[idx] = list
        }
    }

    func deleteList(_ list: SavedPlaceList) async {
        try? await QuailCashAPI.shared.deleteSavedPlaceList(list.id)
        lists.removeAll { $0.id == list.id }
        placesByList.removeValue(forKey: list.id)
    }

    func savePlace(listId: Int, name: String, address: String, latitude: Double?, longitude: Double?, notes: String = "") async -> SavedPlace? {
        guard let raw = try? await QuailCashAPI.shared.savePlace(listId: listId, name: name, address: address, latitude: latitude, longitude: longitude, notes: notes),
              let place = SavedPlace.from(raw) else { return nil }
        placesByList[listId, default: []].insert(place, at: 0)
        if let idx = lists.firstIndex(where: { $0.id == listId }) {
            lists[idx].placeCount += 1
        }
        return place
    }

    func deletePlace(_ place: SavedPlace) async {
        try? await QuailCashAPI.shared.deleteSavedPlace(place.id)
        placesByList[place.listId]?.removeAll { $0.id == place.id }
        if let idx = lists.firstIndex(where: { $0.id == place.listId }) {
            lists[idx].placeCount = max(0, lists[idx].placeCount - 1)
        }
    }
}
