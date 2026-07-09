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
    var tankCapacityGallons: Double = 0

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
    var clientID: String = UUID().uuidString
    var serverID: Int?
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
    var clientID: String = UUID().uuidString
    var serverID: Int?
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
    var clientID: String = UUID().uuidString
    var serverID: Int?
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

    // MARK: API Refresh

    func refresh() async {
        let df = ISO8601DateFormatter()
        df.formatOptions = [.withFullDate]

        // Each fetch is independent — one failure doesn't block the others
        if let p = try? await QuailAPI.shared.fetchVehicleProfile(), p.make != nil || p.currentMileage != nil {
            if let v = p.make,          !v.isEmpty { profile.make = v }
            if let v = p.model,         !v.isEmpty { profile.model = v }
            if let v = p.year                      { profile.year = v }
            if let v = p.vin,           !v.isEmpty { profile.vin = v }
            if let v = p.licensePlate,  !v.isEmpty { profile.licensePlate = v }
            if let v = p.currentMileage              { profile.currentMileage = v }
            if let v = p.oilType,       !v.isEmpty  { profile.oilType = v }
            if let v = p.tankCapacityGallons, v > 0 { profile.tankCapacityGallons = v }
        }

        if let payloads = try? await QuailAPI.shared.fetchVehicleFuel(), !payloads.isEmpty {
            fuelRecords = payloads.compactMap { p -> FuelRecord? in
                guard let date = df.date(from: p.date), let gal = p.gallons, gal > 0 else { return nil }
                return FuelRecord(
                    id: stableID("fuel-\(p.id)"),
                    date: date,
                    mileage: p.mileage,
                    gallons: gal,
                    pricePerGallon: p.pricePerGallon,
                    stationName: p.station ?? "",
                    notes: p.notes ?? ""
                )
            }.sorted { $0.date > $1.date }
        }

        if let payloads = try? await QuailAPI.shared.fetchVehicleMaintenance(), !payloads.isEmpty {
            maintenanceRecords = payloads.compactMap { p -> MaintenanceRecord? in
                guard let date = df.date(from: p.date) else { return nil }
                let typeID = maintenanceTypes.first { $0.name.lowercased() == p.typeName.lowercased() }?.id ?? UUID()
                return MaintenanceRecord(
                    id: stableID("maint-\(p.id)"),
                    typeID: typeID,
                    typeName: p.typeName,
                    date: date,
                    mileage: p.mileage,
                    isShopPerformed: p.isShopPerformed ?? false,
                    shopName: p.shopName ?? "",
                    cost: p.cost,
                    notes: p.notes ?? ""
                )
            }.sorted { $0.date > $1.date }
        }

        if let payloads = try? await QuailAPI.shared.fetchVehicleInspections(), !payloads.isEmpty {
            inspectionItems = payloads.map { p in
                InspectionCheckItem(
                    id: stableID("inspect-\(p.id)"),
                    name: p.name,
                    periodicityDays: p.periodicityDays,
                    lastCheckedDate: p.lastCheckedDate.flatMap { df.date(from: $0) },
                    isBuiltIn: p.isBuiltIn ?? false
                )
            }
        }

        if let payloads = try? await QuailAPI.shared.fetchVehicleIssues(), !payloads.isEmpty {
            issues = payloads.map { p in
                VehicleIssue(
                    id: stableID("issue-\(p.id)"),
                    dateNoticed: p.dateNoticed.flatMap { df.date(from: $0) } ?? Date(),
                    mileageNoticed: p.mileageNoticed ?? 0,
                    title: p.title,
                    description: p.description ?? "",
                    isResolved: p.isResolved ?? false,
                    resolvedDate: p.resolvedDate.flatMap { df.date(from: $0) }
                )
            }
        }

        if let payloads = try? await fetchVehicleTireSets(), !payloads.isEmpty {
            tireSets = payloads.map { p in
                TireSet(
                    id: stableID("tire-\(p.clientId ?? String(p.id))"),
                    clientID: p.clientId ?? String(p.id),
                    serverID: p.id,
                    brand: p.brand ?? "",
                    model: p.model ?? "",
                    size: p.size ?? "",
                    installDate: p.installDate.flatMap { df.date(from: $0) } ?? Date(),
                    installMileage: p.installMileage ?? 0,
                    requiredPressureFront: p.requiredPressureFront ?? 35,
                    requiredPressureRear: p.requiredPressureRear ?? 35,
                    pressureChecks: (p.pressureChecks ?? []).compactMap { c in
                        guard let d = c.date, let date = ISO8601DateFormatter().date(from: d) ?? df.date(from: d) else { return nil }
                        return TirePressureCheck(
                            date: date,
                            mileage: c.mileage ?? 0,
                            frontLeft: c.frontLeft ?? 0,
                            frontRight: c.frontRight ?? 0,
                            rearLeft: c.rearLeft ?? 0,
                            rearRight: c.rearRight ?? 0,
                            notes: c.notes ?? ""
                        )
                    },
                    isActive: p.isActive ?? true
                )
            }
        }

        if let payloads = try? await fetchVehicleCorrectiveRecords(), !payloads.isEmpty {
            correctiveRecords = payloads.compactMap { p -> CorrectiveRecord? in
                guard let date = df.date(from: p.date) else { return nil }
                return CorrectiveRecord(
                    id: stableID("corrective-\(p.clientId ?? String(p.id))"),
                    clientID: p.clientId ?? String(p.id),
                    serverID: p.id,
                    date: date,
                    mileage: p.mileage ?? 0,
                    description: p.description ?? "",
                    reason: p.reason ?? "",
                    partsReplaced: p.partsReplaced ?? [],
                    cost: p.cost,
                    resolvedIssue: p.resolvedIssue ?? false,
                    linkedIssueID: nil,
                    notes: p.notes ?? ""
                )
            }
        }

        if let payloads = try? await fetchVehicleProcedures(), !payloads.isEmpty {
            procedures = payloads.map { p in
                MaintenanceProcedure(
                    id: stableID("procedure-\(p.clientId ?? String(p.id))"),
                    clientID: p.clientId ?? String(p.id),
                    serverID: p.id,
                    title: p.title,
                    relatedTypeName: p.relatedTypeName ?? "",
                    tools: p.tools ?? [],
                    parts: p.parts ?? [],
                    steps: (p.steps ?? []).compactMap { s in
                        guard let text = s.text else { return nil }
                        return ProcedureStep(text: text)
                    },
                    notes: p.notes ?? "",
                    lastUpdated: p.updatedAt.flatMap { ISO8601DateFormatter().date(from: $0) } ?? Date()
                )
            }
        }

        save()
    }

    // MARK: Tires / Corrective / Procedures network payloads
    //
    // These three vehicle sections were local-only (UserDefaults/Documents JSON
    // via save()/load()) until now — they never synced to the backend or showed
    // up in admin. The backend routes already exist (app/routers/vehicle.py:
    // /vehicle/tires, /vehicle/corrective, /vehicle/procedures), but QuailAPI.swift
    // has no typed wrappers for them yet, so we use the generic
    // QuailAPI.shared.fetchData/sendJSON helpers directly here, following the same
    // client_id upsert pattern already used by fuel/maintenance/issues/inspections.

    private struct TirePressureCheckPayload: Codable {
        var date: String?
        var mileage: Int?
        var frontLeft: Int?
        var frontRight: Int?
        var rearLeft: Int?
        var rearRight: Int?
        var notes: String?

        enum CodingKeys: String, CodingKey {
            case date, mileage, notes
            case frontLeft = "front_left"
            case frontRight = "front_right"
            case rearLeft = "rear_left"
            case rearRight = "rear_right"
        }
    }

    private struct TireSetPayload: Codable {
        var id: Int
        var clientId: String?
        var brand: String?
        var model: String?
        var size: String?
        var installDate: String?
        var installMileage: Int?
        var requiredPressureFront: Int?
        var requiredPressureRear: Int?
        var pressureChecks: [TirePressureCheckPayload]?
        var isActive: Bool?

        enum CodingKeys: String, CodingKey {
            case id, brand, model, size
            case clientId = "client_id"
            case installDate = "install_date"
            case installMileage = "install_mileage"
            case requiredPressureFront = "required_pressure_front"
            case requiredPressureRear = "required_pressure_rear"
            case pressureChecks = "pressure_checks"
            case isActive = "is_active"
        }
    }

    private struct CorrectiveRecordPayload: Codable {
        var id: Int
        var clientId: String?
        var date: String
        var mileage: Int?
        var description: String?
        var reason: String?
        var partsReplaced: [String]?
        var cost: Double?
        var resolvedIssue: Bool?
        var linkedIssueId: Int?
        var notes: String?

        enum CodingKeys: String, CodingKey {
            case id, date, mileage, description, reason, cost, notes
            case clientId = "client_id"
            case partsReplaced = "parts_replaced"
            case resolvedIssue = "resolved_issue"
            case linkedIssueId = "linked_issue_id"
        }
    }

    private struct ProcedureStepPayload: Codable {
        var text: String?
    }

    private struct VehicleProcedurePayload: Codable {
        var id: Int
        var clientId: String?
        var title: String
        var relatedTypeName: String?
        var tools: [String]?
        var parts: [String]?
        var steps: [ProcedureStepPayload]?
        var notes: String?
        var updatedAt: String?

        enum CodingKeys: String, CodingKey {
            case id, title, tools, parts, steps, notes
            case clientId = "client_id"
            case relatedTypeName = "related_type_name"
            case updatedAt = "updated_at"
        }
    }

    private func fetchVehicleTireSets() async throws -> [TireSetPayload] {
        let data = try await QuailAPI.shared.fetchData(path: "/vehicle/tires")
        return try JSONDecoder().decode([TireSetPayload].self, from: data)
    }

    private func fetchVehicleCorrectiveRecords() async throws -> [CorrectiveRecordPayload] {
        let data = try await QuailAPI.shared.fetchData(path: "/vehicle/corrective")
        return try JSONDecoder().decode([CorrectiveRecordPayload].self, from: data)
    }

    private func fetchVehicleProcedures() async throws -> [VehicleProcedurePayload] {
        let data = try await QuailAPI.shared.fetchData(path: "/vehicle/procedures")
        return try JSONDecoder().decode([VehicleProcedurePayload].self, from: data)
    }

    private func syncTireSet(_ ts: TireSet) {
        let df = ISO8601DateFormatter()
        df.formatOptions = [.withFullDate]
        let checks: [[String: Any]] = ts.pressureChecks.map { c in
            [
                "date": df.string(from: c.date),
                "mileage": c.mileage,
                "front_left": c.frontLeft,
                "front_right": c.frontRight,
                "rear_left": c.rearLeft,
                "rear_right": c.rearRight,
                "notes": c.notes,
            ]
        }
        let body: [String: Any] = [
            "client_id": ts.clientID,
            "brand": ts.brand,
            "model": ts.model,
            "size": ts.size,
            "install_date": df.string(from: ts.installDate),
            "install_mileage": ts.installMileage,
            "required_pressure_front": ts.requiredPressureFront,
            "required_pressure_rear": ts.requiredPressureRear,
            "pressure_checks": checks,
            "is_active": ts.isActive,
        ]
        Task { try? await QuailAPI.shared.sendJSON(path: "/vehicle/tires", method: "POST", jsonBody: body) }
    }

    private func syncCorrectiveRecord(_ r: CorrectiveRecord) {
        let df = ISO8601DateFormatter()
        df.formatOptions = [.withFullDate]
        let body: [String: Any] = [
            "client_id": r.clientID,
            "date": df.string(from: r.date),
            "mileage": r.mileage,
            "description": r.description,
            "reason": r.reason,
            "parts_replaced": r.partsReplaced,
            "cost": r.cost as Any,
            "resolved_issue": r.resolvedIssue,
            "notes": r.notes,
        ]
        Task { try? await QuailAPI.shared.sendJSON(path: "/vehicle/corrective", method: "POST", jsonBody: body) }
    }

    private func syncProcedure(_ p: MaintenanceProcedure) {
        let body: [String: Any] = [
            "client_id": p.clientID,
            "title": p.title,
            "related_type_name": p.relatedTypeName,
            "tools": p.tools,
            "parts": p.parts,
            "steps": p.steps.map { ["text": $0.text] },
            "notes": p.notes,
        ]
        Task { try? await QuailAPI.shared.sendJSON(path: "/vehicle/procedures", method: "POST", jsonBody: body) }
    }

    private func stableID(_ seed: String) -> UUID {
        var bytes = Array(repeating: UInt8(0), count: 16)
        for (i, byte) in Data(seed.utf8).prefix(16).enumerated() { bytes[i] = byte }
        for (i, byte) in Data(seed.utf8).dropFirst(16).prefix(16).enumerated() { bytes[i] ^= byte }
        bytes[6] = (bytes[6] & 0x0F) | 0x40
        bytes[8] = (bytes[8] & 0x3F) | 0x80
        return UUID(uuid: (bytes[0],bytes[1],bytes[2],bytes[3],bytes[4],bytes[5],bytes[6],bytes[7],
                           bytes[8],bytes[9],bytes[10],bytes[11],bytes[12],bytes[13],bytes[14],bytes[15]))
    }

    // MARK: Mutations

    func addMaintenanceRecord(_ r: MaintenanceRecord) {
        maintenanceRecords.append(r)
        if r.mileage > profile.currentMileage { profile.currentMileage = r.mileage }
        save()
    }

    func addFuelRecord(_ r: FuelRecord) {
        fuelRecords.append(r)
        if r.mileage > profile.currentMileage {
            profile.currentMileage = r.mileage
            let newMileage = r.mileage
            Task { try? await QuailAPI.shared.updateVehicleMileage(newMileage) }
        }
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
        syncTireSet(ts)
        if ts.isActive {
            // Every other set was just flipped to inactive locally — push those too
            // so the backend's is_active flags stay consistent with the local state.
            for other in tireSets where other.id != ts.id {
                syncTireSet(other)
            }
        }
    }

    func addPressureCheck(_ check: TirePressureCheck, tireID: UUID) {
        guard let i = tireSets.firstIndex(where: { $0.id == tireID }) else { return }
        tireSets[i].pressureChecks.append(check)
        if check.mileage > profile.currentMileage { profile.currentMileage = check.mileage }
        save()
        syncTireSet(tireSets[i])
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
        syncCorrectiveRecord(r)
    }

    func saveProcedure(_ p: MaintenanceProcedure) {
        if let i = procedures.firstIndex(where: { $0.id == p.id }) {
            procedures[i] = p
        } else {
            procedures.append(p)
        }
        save()
        syncProcedure(p)
    }

    func deleteIssue(_ id: UUID) { issues.removeAll { $0.id == id }; save() }

    func deleteTireSet(_ id: UUID) {
        guard let ts = tireSets.first(where: { $0.id == id }) else { return }
        tireSets.removeAll { $0.id == id }
        save()
        if let serverID = ts.serverID {
            Task { try? await QuailAPI.shared.sendJSON(path: "/vehicle/tires/\(serverID)", method: "DELETE") }
        }
    }

    func deleteCorrectiveRecord(_ id: UUID) {
        guard let rec = correctiveRecords.first(where: { $0.id == id }) else { return }
        correctiveRecords.removeAll { $0.id == id }
        save()
        if let serverID = rec.serverID {
            Task { try? await QuailAPI.shared.sendJSON(path: "/vehicle/corrective/\(serverID)", method: "DELETE") }
        }
    }

    func deleteProcedure(_ id: UUID) {
        guard let proc = procedures.first(where: { $0.id == id }) else { return }
        procedures.removeAll { $0.id == id }
        save()
        if let serverID = proc.serverID {
            Task { try? await QuailAPI.shared.sendJSON(path: "/vehicle/procedures/\(serverID)", method: "DELETE") }
        }
    }

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
