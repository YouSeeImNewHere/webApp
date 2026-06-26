import Foundation
import SwiftUI
import Combine

// MARK: - Enums

enum MaintenanceColor: String, Codable, CaseIterable, Identifiable {
    case orange, blue, red, yellow, green, teal, purple, gray
    var id: String { rawValue }
    var color: Color {
        switch self {
        case .orange: return Color(red: 0.95, green: 0.55, blue: 0.10)
        case .blue:   return Color(red: 0.40, green: 0.60, blue: 0.95)
        case .red:    return Color(red: 0.85, green: 0.25, blue: 0.20)
        case .yellow: return Color(red: 0.90, green: 0.75, blue: 0.10)
        case .green:  return Color(red: 0.25, green: 0.70, blue: 0.40)
        case .teal:   return Color(red: 0.15, green: 0.70, blue: 0.65)
        case .purple: return Color(red: 0.58, green: 0.33, blue: 0.85)
        case .gray:   return Color(red: 0.50, green: 0.52, blue: 0.55)
        }
    }
    var label: String { rawValue.capitalized }
}

enum VehicleMaintenanceStatus { case ok, dueSoon, overdue, never }

// MARK: - Models

struct VehicleProfile: Codable {
    var make: String = ""
    var model: String = ""
    var year: Int = Calendar.current.component(.year, from: Date())
    var vin: String = ""
    var licensePlate: String = ""
    var oilType: String = ""
    var oilCapacityWithFilter: Double = 0.0
    var oilCapacityWithoutFilter: Double = 0.0
    var transmissionFluidType: String = ""
    var transmissionFluidCapacity: Double = 0.0
    var coolantType: String = ""
    var currentMileage: Int = 0

    var displayName: String {
        let parts = [String(year), make, model].filter { !$0.isEmpty }
        return parts.isEmpty ? "My Vehicle" : parts.joined(separator: " ")
    }
    var isEmpty: Bool { make.isEmpty && model.isEmpty }
}

struct MaintenanceTypeDefinition: Codable, Identifiable, Hashable {
    var id: UUID = UUID()
    var name: String
    var monthInterval: Int?
    var mileageInterval: Int?
    var icon: String = "wrench.and.screwdriver.fill"
    var colorName: MaintenanceColor = .blue
    var isBuiltIn: Bool = false
    var isEnabled: Bool = true
}

struct MaintenanceRecord: Codable, Identifiable {
    var id: UUID = UUID()
    var typeID: UUID
    var typeName: String
    var date: Date
    var mileage: Int
    var isShopPerformed: Bool = false
    var shopName: String = ""
    var linkedTransactionID: String = ""
    var cost: Double?
    var notes: String = ""
}

struct InspectionCheckItem: Codable, Identifiable {
    var id: UUID = UUID()
    var name: String
    var periodicityDays: Int
    var lastCheckedDate: Date? = nil
    var isBuiltIn: Bool = false

    var isDue: Bool {
        guard let last = lastCheckedDate else { return true }
        return Date().timeIntervalSince(last) >= Double(periodicityDays) * 86400
    }
    var periodicityLabel: String { periodicityDays <= 7 ? "Weekly" : "Monthly" }
}

struct FuelRecord: Codable, Identifiable {
    var id: UUID = UUID()
    var date: Date
    var mileage: Int
    var gallons: Double
    var pricePerGallon: Double?
    var stationName: String = ""
    var linkedTransactionID: String = ""
    var notes: String = ""

    var totalCost: Double? {
        guard let ppg = pricePerGallon else { return nil }
        return ppg * gallons
    }
}

struct TirePressureCheck: Codable, Identifiable {
    var id: UUID = UUID()
    var date: Date
    var mileage: Int
    var frontLeft: Int
    var frontRight: Int
    var rearLeft: Int
    var rearRight: Int
    var notes: String = ""
}

struct TireSet: Codable, Identifiable {
    var id: UUID = UUID()
    var brand: String = ""
    var model: String = ""
    var size: String = ""
    var installDate: Date = Date()
    var installMileage: Int = 0
    var requiredPressureFront: Int = 35
    var requiredPressureRear: Int = 35
    var pressureChecks: [TirePressureCheck] = []
    var isActive: Bool = true

    var displayName: String {
        let parts = [brand, model, size].filter { !$0.isEmpty }
        return parts.isEmpty ? "Unnamed Tires" : parts.joined(separator: " ")
    }
    var lastPressureCheck: TirePressureCheck? {
        pressureChecks.max(by: { $0.date < $1.date })
    }
}

struct CorrectiveRecord: Codable, Identifiable {
    var id: UUID = UUID()
    var date: Date = Date()
    var mileage: Int = 0
    var description: String = ""
    var reason: String = ""
    var partsReplaced: [String] = []
    var cost: Double?
    var resolvedIssue: Bool = false
    var linkedIssueID: UUID?
    var notes: String = ""
}

struct VehicleIssue: Codable, Identifiable {
    var id: UUID = UUID()
    var dateNoticed: Date = Date()
    var mileageNoticed: Int = 0
    var title: String = ""
    var description: String = ""
    var howOccurred: String = ""
    var isResolved: Bool = false
    var resolvedDate: Date?
}

struct ProcedureStep: Codable, Identifiable {
    var id: UUID = UUID()
    var text: String = ""
}

struct MaintenanceProcedure: Codable, Identifiable {
    var id: UUID = UUID()
    var title: String = ""
    var relatedTypeName: String = ""
    var tools: [String] = []
    var parts: [String] = []
    var steps: [ProcedureStep] = []
    var notes: String = ""
    var lastUpdated: Date = Date()
}

struct PendingGasDetection {
    var transactionID: String
    var merchant: String
    var amount: Double
    var date: Date
}

// MARK: - Store

@MainActor
final class VehicleStore: ObservableObject {
    static let shared = VehicleStore()

    @Published var profile = VehicleProfile()
    @Published var maintenanceTypes: [MaintenanceTypeDefinition] = []
    @Published var maintenanceRecords: [MaintenanceRecord] = []
    @Published var inspectionItems: [InspectionCheckItem] = []
    @Published var fuelRecords: [FuelRecord] = []
    @Published var tireSets: [TireSet] = []
    @Published var correctiveRecords: [CorrectiveRecord] = []
    @Published var issues: [VehicleIssue] = []
    @Published var procedures: [MaintenanceProcedure] = []
    @Published var pendingGasDetection: PendingGasDetection? = nil

    private let enc: JSONEncoder = { let e = JSONEncoder(); e.dateEncodingStrategy = .iso8601; return e }()
    private let dec: JSONDecoder = { let d = JSONDecoder(); d.dateDecodingStrategy = .iso8601; return d }()

    private init() { load() }

    // MARK: Persistence

    private func url(_ name: String) -> URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("vehicle_\(name).json")
    }

    private func load() {
        profile             = read("profile")    ?? VehicleProfile()
        maintenanceTypes    = read("mtypes")     ?? Self.defaultMaintenanceTypes
        maintenanceRecords  = read("mrecords")   ?? []
        inspectionItems     = read("inspect")    ?? Self.defaultInspectionItems
        fuelRecords         = read("fuel")       ?? []
        tireSets            = read("tires")      ?? []
        correctiveRecords   = read("corrective") ?? []
        issues              = read("issues")     ?? []
        procedures          = read("procedures") ?? []
    }

    func save() {
        write(profile,            "profile")
        write(maintenanceTypes,   "mtypes")
        write(maintenanceRecords, "mrecords")
        write(inspectionItems,    "inspect")
        write(fuelRecords,        "fuel")
        write(tireSets,           "tires")
        write(correctiveRecords,  "corrective")
        write(issues,             "issues")
        write(procedures,         "procedures")
    }

    private func read<T: Decodable>(_ name: String) -> T? {
        guard let data = try? Data(contentsOf: url(name)) else { return nil }
        return try? dec.decode(T.self, from: data)
    }

    private func write<T: Encodable>(_ value: T, _ name: String) {
        guard let data = try? enc.encode(value) else { return }
        try? data.write(to: url(name), options: .atomicWrite)
    }

    // MARK: Computed

    func lastRecord(for typeID: UUID) -> MaintenanceRecord? {
        maintenanceRecords.filter { $0.typeID == typeID }.max(by: { $0.date < $1.date })
    }

    func status(for type: MaintenanceTypeDefinition) -> VehicleMaintenanceStatus {
        let last = lastRecord(for: type.id)
        guard type.monthInterval != nil || type.mileageInterval != nil else { return .ok }
        if last == nil { return .never }

        var overdue = false
        var dueSoon = false

        if let mi = type.mileageInterval {
            let remaining = (last!.mileage + mi) - profile.currentMileage
            if remaining <= 0 { overdue = true }
            else if remaining <= max(300, mi / 10) { dueSoon = true }
        }

        if let months = type.monthInterval {
            let next = Calendar.current.date(byAdding: .month, value: months, to: last!.date)!
            let days = Calendar.current.dateComponents([.day], from: Date(), to: next).day ?? 0
            if days < 0 { overdue = true }
            else if days <= 30 { dueSoon = true }
        }

        if overdue { return .overdue }
        if dueSoon { return .dueSoon }
        return .ok
    }

    func nextDueDescription(for type: MaintenanceTypeDefinition) -> String {
        let last = lastRecord(for: type.id)
        var parts: [String] = []

        if let mi = type.mileageInterval {
            let base = last?.mileage ?? profile.currentMileage
            parts.append("\((base + mi).formatted()) mi")
        }

        if let months = type.monthInterval, let base = last?.date {
            if let next = Calendar.current.date(byAdding: .month, value: months, to: base) {
                parts.append(next.formatted(date: .abbreviated, time: .omitted))
            }
        }

        if parts.isEmpty { return last == nil ? "Never done" : "OK" }
        return parts.joined(separator: " · ")
    }

    func averageMPG(last n: Int = 20) -> Double? {
        let sorted = fuelRecords.sorted { $0.date > $1.date }
        guard sorted.count >= 2 else { return nil }
        let slice = Array(sorted.prefix(n + 1))
        var totalMiles = 0
        var totalGallons = 0.0
        for i in 0..<slice.count - 1 {
            let mi = slice[i].mileage - slice[i + 1].mileage
            guard mi > 0 else { continue }
            totalMiles += mi
            totalGallons += slice[i].gallons
        }
        guard totalGallons > 0, totalMiles > 0 else { return nil }
        return Double(totalMiles) / totalGallons
    }

    var activeTireSet: TireSet? { tireSets.first(where: { $0.isActive }) }
    var openIssues: [VehicleIssue] { issues.filter { !$0.isResolved } }

    // MARK: Mutations

    func addMaintenanceRecord(_ r: MaintenanceRecord) {
        maintenanceRecords.append(r)
        if r.mileage > profile.currentMileage { profile.currentMileage = r.mileage }
        save()
    }

    func addFuelRecord(_ r: FuelRecord) {
        fuelRecords.append(r)
        if r.mileage > profile.currentMileage { profile.currentMileage = r.mileage }
        save()
    }

    func checkInspectionItem(_ id: UUID) {
        guard let i = inspectionItems.firstIndex(where: { $0.id == id }) else { return }
        inspectionItems[i].lastCheckedDate = Date()
        save()
    }

    func addTireSet(_ ts: TireSet) {
        if ts.isActive { tireSets = tireSets.map { var t = $0; t.isActive = false; return t } }
        tireSets.append(ts)
        save()
    }

    func addPressureCheck(_ check: TirePressureCheck, tireID: UUID) {
        guard let i = tireSets.firstIndex(where: { $0.id == tireID }) else { return }
        tireSets[i].pressureChecks.append(check)
        if check.mileage > profile.currentMileage { profile.currentMileage = check.mileage }
        save()
    }

    func addIssue(_ issue: VehicleIssue) { issues.append(issue); save() }

    func addCorrectiveRecord(_ r: CorrectiveRecord) {
        correctiveRecords.append(r)
        if r.mileage > profile.currentMileage { profile.currentMileage = r.mileage }
        if r.resolvedIssue, let lid = r.linkedIssueID,
           let i = issues.firstIndex(where: { $0.id == lid }) {
            issues[i].isResolved = true
            issues[i].resolvedDate = r.date
        }
        save()
    }

    func saveProcedure(_ p: MaintenanceProcedure) {
        if let i = procedures.firstIndex(where: { $0.id == p.id }) {
            procedures[i] = p
        } else {
            procedures.append(p)
        }
        save()
    }

    func deleteIssue(_ id: UUID) { issues.removeAll { $0.id == id }; save() }
    func deleteCorrectiveRecord(_ id: UUID) { correctiveRecords.removeAll { $0.id == id }; save() }
    func deleteProcedure(_ id: UUID) { procedures.removeAll { $0.id == id }; save() }
    func deleteMaintenanceRecord(_ id: UUID) { maintenanceRecords.removeAll { $0.id == id }; save() }
    func deleteFuelRecord(_ id: UUID) { fuelRecords.removeAll { $0.id == id }; save() }

    func deleteMaintenanceType(_ id: UUID) {
        maintenanceTypes.removeAll { $0.id == id && !$0.isBuiltIn }
        save()
    }

    func saveMaintenanceType(_ t: MaintenanceTypeDefinition) {
        if let i = maintenanceTypes.firstIndex(where: { $0.id == t.id }) {
            maintenanceTypes[i] = t
        } else {
            maintenanceTypes.append(t)
        }
        save()
    }

    func saveInspectionItem(_ item: InspectionCheckItem) {
        if let i = inspectionItems.firstIndex(where: { $0.id == item.id }) {
            inspectionItems[i] = item
        } else {
            inspectionItems.append(item)
        }
        save()
    }

    func deleteInspectionItem(_ id: UUID) {
        inspectionItems.removeAll { $0.id == id && !$0.isBuiltIn }
        save()
    }

    // MARK: Defaults

    static let defaultMaintenanceTypes: [MaintenanceTypeDefinition] = [
        .init(name: "Oil Change",          monthInterval: 6,  mileageInterval: 5000,  icon: "drop.fill",                    colorName: .orange, isBuiltIn: true),
        .init(name: "Tire Rotation",       monthInterval: 6,  mileageInterval: 7500,  icon: "circle.grid.cross.fill",       colorName: .blue,   isBuiltIn: true),
        .init(name: "Brake Pads",          monthInterval: nil, mileageInterval: 50000, icon: "slowmo",                      colorName: .red,    isBuiltIn: true),
        .init(name: "Brake Fluid",         monthInterval: 24, mileageInterval: nil,    icon: "drop.halffull",               colorName: .red,    isBuiltIn: true),
        .init(name: "Spark Plugs",         monthInterval: nil, mileageInterval: 30000, icon: "bolt.fill",                   colorName: .yellow, isBuiltIn: true),
        .init(name: "Air Filter",          monthInterval: 12, mileageInterval: 15000,  icon: "aqi.medium",                  colorName: .green,  isBuiltIn: true),
        .init(name: "Cabin Filter",        monthInterval: 12, mileageInterval: 15000,  icon: "wind",                        colorName: .teal,   isBuiltIn: true),
        .init(name: "Coolant Flush",       monthInterval: 24, mileageInterval: 30000,  icon: "thermometer.medium",          colorName: .blue,   isBuiltIn: true),
        .init(name: "Transmission Fluid",  monthInterval: nil, mileageInterval: 30000, icon: "gearshape.fill",              colorName: .purple, isBuiltIn: true),
        .init(name: "Battery",             monthInterval: 48, mileageInterval: nil,    icon: "battery.100",                 colorName: .green,  isBuiltIn: true),
        .init(name: "Timing Belt",         monthInterval: nil, mileageInterval: 60000, icon: "gearshape.2.fill",            colorName: .gray,   isBuiltIn: true),
    ]

    static let defaultInspectionItems: [InspectionCheckItem] = [
        .init(name: "Tire Pressure",      periodicityDays: 7,  isBuiltIn: true),
        .init(name: "Fluid Levels",       periodicityDays: 7,  isBuiltIn: true),
        .init(name: "Lights",             periodicityDays: 7,  isBuiltIn: true),
        .init(name: "Wipers",             periodicityDays: 7,  isBuiltIn: true),
        .init(name: "Battery Terminals",  periodicityDays: 30, isBuiltIn: true),
        .init(name: "Belts & Hoses",      periodicityDays: 30, isBuiltIn: true),
        .init(name: "Brake Pad Visual",   periodicityDays: 30, isBuiltIn: true),
        .init(name: "Tire Tread Depth",   periodicityDays: 30, isBuiltIn: true),
    ]
}
