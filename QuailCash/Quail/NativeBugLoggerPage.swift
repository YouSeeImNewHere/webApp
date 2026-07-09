import SwiftUI
import UIKit
import PhotosUI
import Combine

// MARK: - Network logger

struct NetworkLogEntry: Identifiable, Codable {
    let id: UUID
    let method: String
    let path: String
    let status: Int
    let duration: TimeInterval
    let error: String?
    let timestamp: Date
    init(method: String, path: String, status: Int, duration: TimeInterval, error: String? = nil, timestamp: Date) {
        id = UUID()
        self.method = method; self.path = path; self.status = status
        self.duration = duration; self.error = error; self.timestamp = timestamp
    }
}

@MainActor
final class NetworkLogger: ObservableObject {
    static let shared = NetworkLogger()
    @Published private(set) var entries: [NetworkLogEntry] = []
    private let maxEntries = 20

    nonisolated func log(method: String, path: String, status: Int, duration: TimeInterval, error: String? = nil) {
        let entry = NetworkLogEntry(method: method, path: path, status: status, duration: duration, error: error, timestamp: Date())
        Task { @MainActor in
            self.entries.insert(entry, at: 0)
            if self.entries.count > self.maxEntries { self.entries = Array(self.entries.prefix(self.maxEntries)) }
        }
    }
}

// MARK: - Models

enum BugStatus: String, Codable, CaseIterable {
    case open, inProgress, resolved

    var label: String {
        switch self {
        case .open: return "Open"
        case .inProgress: return "In Progress"
        case .resolved: return "Resolved"
        }
    }

    var color: Color {
        switch self {
        case .open: return .red
        case .inProgress: return .orange
        case .resolved: return .green
        }
    }
}

struct DrawnStroke: Codable {
    var points: [CodablePoint]
    var colorHex: String
    var lineWidth: Double
}

struct CodablePoint: Codable {
    var x: Double
    var y: Double
    var cgPoint: CGPoint { CGPoint(x: x, y: y) }
    init(_ p: CGPoint) { x = p.x; y = p.y }
}

struct BugReport: Codable, Identifiable {
    let id: UUID
    var title: String
    var description: String
    var screenshotFilename: String?
    var strokes: [DrawnStroke]
    var status: BugStatus
    var route: String
    var networkLog: [NetworkLogEntry]
    var createdAt: Date
    var updatedAt: Date
    // Backend sync bookkeeping — not present in older locally-cached JSON, so all optional/defaulted.
    var serverId: Int? = nil
    var hasRemoteScreenshot: Bool = false
    var screenshotUploaded: Bool = false

    init(id: UUID, title: String, description: String, screenshotFilename: String?, strokes: [DrawnStroke], status: BugStatus, route: String, networkLog: [NetworkLogEntry], createdAt: Date, updatedAt: Date, serverId: Int? = nil, hasRemoteScreenshot: Bool = false, screenshotUploaded: Bool = false) {
        self.id = id; self.title = title; self.description = description
        self.screenshotFilename = screenshotFilename; self.strokes = strokes; self.status = status
        self.route = route; self.networkLog = networkLog; self.createdAt = createdAt; self.updatedAt = updatedAt
        self.serverId = serverId; self.hasRemoteScreenshot = hasRemoteScreenshot; self.screenshotUploaded = screenshotUploaded
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(UUID.self, forKey: .id)
        title = try c.decode(String.self, forKey: .title)
        description = try c.decode(String.self, forKey: .description)
        screenshotFilename = try c.decodeIfPresent(String.self, forKey: .screenshotFilename)
        strokes = (try? c.decode([DrawnStroke].self, forKey: .strokes)) ?? []
        status = (try? c.decode(BugStatus.self, forKey: .status)) ?? .open
        route = (try? c.decode(String.self, forKey: .route)) ?? ""
        networkLog = (try? c.decode([NetworkLogEntry].self, forKey: .networkLog)) ?? []
        createdAt = try c.decode(Date.self, forKey: .createdAt)
        updatedAt = try c.decode(Date.self, forKey: .updatedAt)
        serverId = (try? c.decodeIfPresent(Int.self, forKey: .serverId)) ?? nil
        hasRemoteScreenshot = (try? c.decodeIfPresent(Bool.self, forKey: .hasRemoteScreenshot) ?? false) ?? false
        screenshotUploaded = (try? c.decodeIfPresent(Bool.self, forKey: .screenshotUploaded) ?? false) ?? false
    }
}

// MARK: - Text Bug Note (checklist-style)

struct TextBugNote: Codable, Identifiable {
    var id: UUID = UUID()
    var text: String
    var isResolved: Bool = false
    var createdAt: Date = Date()
    var serverId: Int? = nil
}

@MainActor
final class TextBugStore: ObservableObject {
    static let shared = TextBugStore()
    @Published var notes: [TextBugNote] = []
    private let key = "quail.bugs.textNotes"

    init() {
        loadCache()
        Task { await refresh() }
    }

    // MARK: - Local cache (offline fallback)

    func loadCache() {
        guard let data = UserDefaults.standard.data(forKey: key),
              let decoded = try? JSONDecoder().decode([TextBugNote].self, from: data) else { return }
        notes = decoded
    }

    func saveCache() {
        if let data = try? JSONEncoder().encode(notes) { UserDefaults.standard.set(data, forKey: key) }
    }

    // MARK: - Backend sync

    func refresh() async {
        do {
            let data = try await QuailAPI.shared.fetchData(path: "/bugs/notes")
            let payloads = try JSONDecoder.quailCash.decode([BugNotePayload].self, from: data)
            notes = payloads.map { $0.asTextBugNote() }.sorted { $0.createdAt > $1.createdAt }
            saveCache()
        } catch {
            print("[Quail] TextBugStore.refresh failed, using cache: \(error.localizedDescription)")
        }
    }

    func add(text: String) {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return }
        let note = TextBugNote(text: t)
        notes.insert(note, at: 0)
        saveCache()
        Task { await push(note) }
    }

    func toggle(_ note: TextBugNote) {
        if let i = notes.firstIndex(where: { $0.id == note.id }) {
            notes[i].isResolved.toggle()
            saveCache()
            Task { await push(notes[i]) }
        }
    }

    func delete(_ note: TextBugNote) {
        notes.removeAll { $0.id == note.id }
        saveCache()
        guard let serverId = note.serverId else { return }
        Task {
            do {
                try await QuailAPI.shared.sendJSON(path: "/bugs/notes/\(serverId)", method: "DELETE")
            } catch {
                print("[Quail] TextBugStore.delete failed: \(error.localizedDescription)")
            }
        }
    }

    private func push(_ note: TextBugNote) async {
        do {
            let body: [String: Any] = [
                "client_id": note.id.uuidString,
                "text": note.text,
                "is_resolved": note.isResolved,
            ]
            let data = try await QuailAPI.shared.fetchData(path: "/bugs/notes", method: "POST", jsonBody: body)
            let payload = try JSONDecoder.quailCash.decode(BugNotePayload.self, from: data)
            if let i = notes.firstIndex(where: { $0.id == note.id }) {
                notes[i].serverId = payload.id
                saveCache()
            }
        } catch {
            print("[Quail] TextBugStore.push failed: \(error.localizedDescription)")
        }
    }

    var openCount: Int { notes.filter { !$0.isResolved }.count }
}

// MARK: - Backend payload models

private struct BugReportPayload: Codable {
    var id: Int
    var clientId: String
    var title: String
    var description: String?
    var status: String
    var route: String?
    var networkLog: String?
    var hasScreenshot: Bool?
    var createdAt: String?
    var updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case clientId = "client_id"
        case title
        case description
        case status
        case route
        case networkLog = "network_log"
        case hasScreenshot = "has_screenshot"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    func asBugReport(existingLocal: BugReport?) -> BugReport {
        let uuid = UUID(uuidString: clientId) ?? existingLocal?.id ?? UUID()
        let decodedLog: [NetworkLogEntry]
        if let logJSON = networkLog, let data = logJSON.data(using: .utf8),
           let entries = try? JSONDecoder().decode([NetworkLogEntry].self, from: data) {
            decodedLog = entries
        } else {
            decodedLog = existingLocal?.networkLog ?? []
        }
        return BugReport(
            id: uuid,
            title: title,
            description: description ?? "",
            screenshotFilename: existingLocal?.screenshotFilename,
            strokes: existingLocal?.strokes ?? [],
            status: BugStatus(rawValue: status) ?? .open,
            route: route ?? "",
            networkLog: decodedLog,
            createdAt: BugReportStore.parseServerDate(createdAt) ?? existingLocal?.createdAt ?? Date(),
            updatedAt: BugReportStore.parseServerDate(updatedAt) ?? existingLocal?.updatedAt ?? Date(),
            serverId: id,
            hasRemoteScreenshot: hasScreenshot ?? false,
            screenshotUploaded: (hasScreenshot ?? false) || (existingLocal?.screenshotUploaded ?? false)
        )
    }
}

private struct BugNotePayload: Codable {
    var id: Int
    var clientId: String
    var text: String
    var isResolved: Bool?
    var createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case clientId = "client_id"
        case text
        case isResolved = "is_resolved"
        case createdAt = "created_at"
    }

    func asTextBugNote() -> TextBugNote {
        TextBugNote(
            id: UUID(uuidString: clientId) ?? UUID(),
            text: text,
            isResolved: isResolved ?? false,
            createdAt: BugReportStore.parseServerDate(createdAt) ?? Date(),
            serverId: id
        )
    }
}

// MARK: - Store

@MainActor
final class BugReportStore: ObservableObject {
    static let shared = BugReportStore()
    @Published var reports: [BugReport] = []

    private let key = "quail.bugs.reports"
    private nonisolated let docsDir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]

    init() {
        loadCache()
        Task { await refresh() }
    }

    static func parseServerDate(_ iso: String?) -> Date? {
        guard let iso else { return nil }
        let withFraction = ISO8601DateFormatter()
        withFraction.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = withFraction.date(from: iso) { return d }
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        if let d = plain.date(from: iso) { return d }
        // Postgres isoformat() without timezone suffix normalization; try appending "Z" style offset.
        if let d = withFraction.date(from: iso + "Z") { return d }
        return nil
    }

    // MARK: - Local cache (offline fallback)

    func loadCache() {
        guard let data = UserDefaults.standard.data(forKey: key),
              let decoded = try? JSONDecoder().decode([BugReport].self, from: data) else { return }
        reports = decoded.sorted { $0.createdAt > $1.createdAt }
    }

    func saveCache() {
        if let data = try? JSONEncoder().encode(reports) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }

    // MARK: - Backend sync

    func refresh() async {
        do {
            let data = try await QuailAPI.shared.fetchData(path: "/bugs/reports")
            let payloads = try JSONDecoder.quailCash.decode([BugReportPayload].self, from: data)
            let existingByID = Dictionary(uniqueKeysWithValues: reports.map { ($0.id, $0) })
            reports = payloads
                .map { $0.asBugReport(existingLocal: existingByID[UUID(uuidString: $0.clientId) ?? UUID()]) }
                .sorted { $0.createdAt > $1.createdAt }
            saveCache()
        } catch {
            print("[Quail] BugReportStore.refresh failed, using cache: \(error.localizedDescription)")
        }
    }

    func add(_ report: BugReport) {
        reports.insert(report, at: 0)
        saveCache()
        Task { await push(report) }
    }

    func update(_ report: BugReport) {
        if let i = reports.firstIndex(where: { $0.id == report.id }) {
            reports[i] = report
            saveCache()
            Task { await push(reports[i]) }
        }
    }

    func delete(_ report: BugReport) {
        if let filename = report.screenshotFilename {
            let url = docsDir.appendingPathComponent(filename)
            try? FileManager.default.removeItem(at: url)
        }
        reports.removeAll { $0.id == report.id }
        saveCache()
        guard let serverId = report.serverId else { return }
        Task {
            do {
                try await QuailAPI.shared.sendJSON(path: "/bugs/reports/\(serverId)", method: "DELETE")
            } catch {
                print("[Quail] BugReportStore.delete failed: \(error.localizedDescription)")
            }
        }
    }

    /// Upserts the report to the backend, then uploads the screenshot (if any and not already uploaded).
    private func push(_ report: BugReport) async {
        do {
            let logJSON: String
            if let data = try? JSONEncoder().encode(report.networkLog), let s = String(data: data, encoding: .utf8) {
                logJSON = s
            } else {
                logJSON = "[]"
            }
            let body: [String: Any] = [
                "client_id": report.id.uuidString,
                "title": report.title,
                "description": report.description,
                "status": statusRawValue(report.status),
                "route": report.route,
                "network_log": logJSON,
            ]
            let data = try await QuailAPI.shared.fetchData(path: "/bugs/reports", method: "POST", jsonBody: body)
            let payload = try JSONDecoder.quailCash.decode(BugReportPayload.self, from: data)
            if let i = reports.firstIndex(where: { $0.id == report.id }) {
                reports[i].serverId = payload.id
                saveCache()
            }

            if let filename = report.screenshotFilename, !report.screenshotUploaded {
                let fileURL = docsDir.appendingPathComponent(filename)
                if FileManager.default.fileExists(atPath: fileURL.path) {
                    try await QuailAPI.shared.uploadBugScreenshot(clientId: report.id.uuidString, fileURL: fileURL)
                    if let i = reports.firstIndex(where: { $0.id == report.id }) {
                        reports[i].screenshotUploaded = true
                        reports[i].hasRemoteScreenshot = true
                        saveCache()
                    }
                }
            }
        } catch {
            print("[Quail] BugReportStore.push failed: \(error.localizedDescription)")
        }
    }

    private func statusRawValue(_ status: BugStatus) -> String {
        switch status {
        case .open: return "open"
        case .inProgress: return "in_progress"
        case .resolved: return "resolved"
        }
    }

    nonisolated func saveImage(_ image: UIImage, id: UUID) -> String {
        let filename = "bug_\(id.uuidString).jpg"
        let url = docsDir.appendingPathComponent(filename)
        if let data = image.jpegData(compressionQuality: 0.75) {
            try? data.write(to: url)
        }
        return filename
    }

    nonisolated func loadImage(filename: String) -> UIImage? {
        let url = docsDir.appendingPathComponent(filename)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return UIImage(data: data)
    }

    /// Downloads and locally caches the screenshot for a report that has one on the server
    /// but no local file yet (e.g. synced from another device/Android).
    func ensureScreenshotDownloaded(for report: BugReport) async -> String? {
        if let filename = report.screenshotFilename,
           FileManager.default.fileExists(atPath: docsDir.appendingPathComponent(filename).path) {
            return filename
        }
        guard report.hasRemoteScreenshot, let serverId = report.serverId else { return nil }
        do {
            let data = try await QuailAPI.shared.fetchData(path: "/bugs/reports/\(serverId)/screenshot")
            let filename = "bug_\(report.id.uuidString).jpg"
            let url = docsDir.appendingPathComponent(filename)
            try data.write(to: url)
            if let i = reports.firstIndex(where: { $0.id == report.id }) {
                reports[i].screenshotFilename = filename
                saveCache()
            }
            return filename
        } catch {
            print("[Quail] BugReportStore.ensureScreenshotDownloaded failed: \(error.localizedDescription)")
            return nil
        }
    }
}

// MARK: - Screenshot utility

func captureAppScreenshot() -> UIImage? {
    let scene = UIApplication.shared.connectedScenes
        .compactMap { $0 as? UIWindowScene }
        .first(where: { $0.activationState == .foregroundActive })
        ?? UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
    guard let window = scene?.windows.max(by: { $0.windowLevel < $1.windowLevel }) else { return nil }
    let renderer = UIGraphicsImageRenderer(bounds: window.bounds)
    return renderer.image { _ in
        window.drawHierarchy(in: window.bounds, afterScreenUpdates: false)
    }
}

// MARK: - Main page

struct BugLoggerPageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @EnvironmentObject private var navigator: AppNavigator
    @StateObject private var store = BugReportStore.shared
    @StateObject private var textStore = TextBugStore.shared
    @State private var showingNewBug = false
    @State private var capturedScreenshot: UIImage?
    @State private var selectedReport: BugReport?
    @State private var filterStatus: BugStatus? = nil

    var filtered: [BugReport] {
        guard let f = filterStatus else { return store.reports }
        return store.reports.filter { $0.status == f }
    }

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        let totalOpen = store.reports.filter { $0.status == .open }.count + textStore.openCount
        AppChromeFrame(
            title: "Quail Bugs",
            badgeValue: totalOpen,
            selectedTab: nil,
            showsBottomBar: false,
            showsStandaloneBar: false,
            showsDashboardBar: true,
            onLeadingTap: { navigator.goBack() },
            onTrailingTap: {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                    capturedScreenshot = captureAppScreenshot()
                    DispatchQueue.main.async { showingNewBug = true }
                }
            }
        ) {
            AppPageScroll {
                VStack(spacing: 14) {
                    // Quick text bug entry
                    TextBugChecklistCard(palette: palette)

                    // Status filter chips for screenshot bugs
                    if !store.reports.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                FilterChip(label: "All", active: filterStatus == nil, palette: palette) { filterStatus = nil }
                                ForEach(BugStatus.allCases, id: \.rawValue) { s in
                                    FilterChip(
                                        label: s.label,
                                        count: store.reports.filter { $0.status == s }.count,
                                        active: filterStatus == s,
                                        color: s.color,
                                        palette: palette
                                    ) { filterStatus = filterStatus == s ? nil : s }
                                }
                            }
                        }
                    }

                    if !filtered.isEmpty {
                        VStack(spacing: 10) {
                            ForEach(filtered) { report in
                                BugRowView(report: report, palette: palette) { selectedReport = report }
                            }
                        }
                    } else if store.reports.isEmpty && textStore.notes.isEmpty {
                        VStack(spacing: 10) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 36)).foregroundStyle(.green)
                            Text("No bugs logged yet.")
                                .font(.system(size: 14, design: .rounded)).foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity).padding(.top, 20)
                    }
                }
            }
        }
        .sheet(isPresented: $showingNewBug) {
            NewBugSheet(initialScreenshot: capturedScreenshot, palette: QuailTheme.palette(for: themeSelection)) { report in
                store.add(report)
            }
            .presentationDetents([.large])
        }
        .sheet(item: $selectedReport) { report in
            BugDetailSheet(report: report, palette: QuailTheme.palette(for: themeSelection)) { updated in
                store.update(updated)
            } onDelete: {
                store.delete(report)
                selectedReport = nil
            }
            .presentationDetents([.large])
        }
    }
}

private struct TextBugChecklistCard: View {
    let palette: QuailThemePalette
    @StateObject private var store = TextBugStore.shared
    @State private var newText = ""
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Input row
            HStack(spacing: 8) {
                Image(systemName: "plus.circle").font(.system(size: 16)).foregroundStyle(.secondary)
                TextField("Note a bug without a screenshot…", text: $newText)
                    .font(.system(size: 13, design: .rounded))
                    .focused($focused)
                    .onSubmit { addNote() }
                if !newText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Button(action: addNote) {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.system(size: 20)).foregroundStyle(.red)
                    }.buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 12).padding(.vertical, 10)

            if !store.notes.isEmpty {
                Divider().padding(.horizontal, 12)
                ForEach(Array(store.notes.enumerated()), id: \.element.id) { idx, note in
                    TextBugNoteRow(note: note, palette: palette)
                    if idx < store.notes.count - 1 { Divider().padding(.leading, 36) }
                }
            }
        }
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func addNote() {
        store.add(text: newText)
        newText = ""
        focused = false
    }
}

private struct TextBugNoteRow: View {
    let note: TextBugNote
    let palette: QuailThemePalette

    var body: some View {
        HStack(spacing: 10) {
            Button { TextBugStore.shared.toggle(note) } label: {
                Image(systemName: note.isResolved ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 18))
                    .foregroundStyle(note.isResolved ? .green : .secondary)
            }.buttonStyle(.plain)

            Text(note.text)
                .font(.system(size: 13, design: .rounded))
                .foregroundStyle(note.isResolved ? .secondary : .primary)
                .strikethrough(note.isResolved, color: .secondary)
                .frame(maxWidth: .infinity, alignment: .leading)

            Button { TextBugStore.shared.delete(note) } label: {
                Image(systemName: "xmark").font(.system(size: 11)).foregroundStyle(.secondary)
            }.buttonStyle(.plain)
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
    }
}

private struct FilterChip: View {
    let label: String
    var count: Int? = nil
    let active: Bool
    var color: Color = .accentColor
    let palette: QuailThemePalette
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 4) {
                Text(label)
                if let c = count, c > 0 {
                    Text("\(c)")
                        .font(.system(size: 10, weight: .bold, design: .rounded))
                        .foregroundStyle(active ? .white : color)
                        .padding(.horizontal, 5).padding(.vertical, 2)
                        .background(active ? Color.white.opacity(0.3) : color.opacity(0.15), in: Capsule())
                }
            }
            .font(.system(size: 12, weight: .semibold, design: .rounded))
            .foregroundStyle(active ? .white : palette.chromeIconForeground)
            .padding(.horizontal, 12).padding(.vertical, 7)
            .background(active ? color : palette.surface, in: Capsule())
            .overlay(Capsule().stroke(active ? color : palette.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

// Shared thumbnail cache — keyed by filename, stores downsampled UIImage
private final class ThumbnailCache {
    static let shared = ThumbnailCache()
    private var cache: [String: UIImage] = [:]
    private let queue = DispatchQueue(label: "quail.bugs.thumbcache")

    func thumbnail(for filename: String, completion: @escaping (UIImage?) -> Void) {
        queue.async {
            if let cached = self.cache[filename] {
                DispatchQueue.main.async { completion(cached) }
                return
            }
            let thumb = BugReportStore.shared.loadImage(filename: filename)
                .map { $0.downsample(to: CGSize(width: 112, height: 88)) }
            if let thumb { self.cache[filename] = thumb }
            DispatchQueue.main.async { completion(thumb) }
        }
    }
}

private extension UIImage {
    func downsample(to size: CGSize) -> UIImage {
        let renderer = UIGraphicsImageRenderer(size: size)
        return renderer.image { _ in self.draw(in: CGRect(origin: .zero, size: size)) }
    }
}

private struct BugRowView: View {
    let report: BugReport
    let palette: QuailThemePalette
    let onTap: () -> Void
    @State private var thumbnail: UIImage?

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 12) {
                // Thumbnail — loaded async, never blocks main thread
                RoundedRectangle(cornerRadius: 6)
                    .fill(palette.elevatedSurface)
                    .frame(width: 56, height: 44)
                    .overlay {
                        if let img = thumbnail {
                            Image(uiImage: img)
                                .resizable().scaledToFill()
                                .clipped()
                        } else if report.screenshotFilename != nil {
                            ProgressView().scaleEffect(0.6)
                        } else {
                            Image(systemName: "text.bubble").foregroundStyle(.secondary).font(.system(size: 14))
                        }
                    }
                    .clipShape(RoundedRectangle(cornerRadius: 6))

                VStack(alignment: .leading, spacing: 3) {
                    Text(report.title.isEmpty ? "Untitled Bug" : report.title)
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                        .lineLimit(1)
                    if !report.description.isEmpty {
                        Text(report.description)
                            .font(.system(size: 11, design: .rounded))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    Text(report.createdAt.formatted(.relative(presentation: .named)))
                        .font(.system(size: 10, design: .rounded))
                        .foregroundStyle(.tertiary)
                }

                Spacer()

                Text(report.status.label)
                    .font(.system(size: 10, weight: .bold, design: .rounded))
                    .foregroundStyle(report.status.color)
                    .padding(.horizontal, 8).padding(.vertical, 4)
                    .background(report.status.color.opacity(0.12), in: Capsule())
            }
            .padding(12)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .task(id: report.screenshotFilename) {
            guard let filename = report.screenshotFilename else { return }
            ThumbnailCache.shared.thumbnail(for: filename) { thumbnail = $0 }
        }
    }
}

// MARK: - New bug sheet

struct NewBugSheet: View {
    let initialScreenshot: UIImage?
    var currentRoute: String = ""
    var networkLog: [NetworkLogEntry] = []
    let palette: QuailThemePalette
    let onSave: (BugReport) -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var title = ""
    @State private var description = ""
    @State private var screenshot: UIImage?
    @State private var strokes: [DrawnStroke] = []
    @State private var showingImagePicker = false
    @State private var pickerItem: PhotosPickerItem?
    @State private var drawColor: Color = .red
    @State private var lineWidth: Double = 3.0
    @State private var isErasing = false
    @State private var phase: Phase = .annotate

    enum Phase { case annotate, describe }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Button("Cancel") { dismiss() }
                    .font(.system(size: 14, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                Spacer()
                Text(phase == .annotate ? "Annotate" : "Describe Bug")
                    .font(.system(size: 15, weight: .bold, design: .rounded))
                Spacer()
                if phase == .annotate {
                    Button("Next") { phase = .describe }
                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                } else {
                    Button("Save") { saveBug() }
                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 14)

            Divider()

            if phase == .annotate {
                annotatePhase
            } else {
                describePhase
            }
        }
        .onAppear { screenshot = initialScreenshot }
    }

    @ViewBuilder private var annotatePhase: some View {
        VStack(spacing: 0) {
            // Canvas
            ZStack {
                if let img = screenshot {
                    GeometryReader { geo in
                        Image(uiImage: img)
                            .resizable().scaledToFit()
                            .frame(width: geo.size.width, height: geo.size.height)
                            .overlay(
                                DrawingCanvas(
                                    strokes: $strokes,
                                    drawColor: isErasing ? .clear : drawColor,
                                    lineWidth: isErasing ? 20 : lineWidth,
                                    isErasing: isErasing
                                )
                            )
                    }
                } else {
                    VStack(spacing: 12) {
                        Image(systemName: "photo.badge.plus")
                            .font(.system(size: 40)).foregroundStyle(.secondary)
                        Text("No screenshot").font(.system(size: 13, design: .rounded)).foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(palette.elevatedSurface)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.black)

            // Toolbar
            HStack(spacing: 16) {
                // Photo picker
                PhotosPicker(selection: $pickerItem, matching: .images) {
                    Image(systemName: "photo.badge.plus")
                        .font(.system(size: 20, weight: .medium))
                        .foregroundStyle(palette.chromeIconForeground)
                }
                .onChange(of: pickerItem) { _, item in
                    Task {
                        if let data = try? await item?.loadTransferable(type: Data.self),
                           let img = UIImage(data: data) {
                            screenshot = img
                            strokes = []
                        }
                    }
                }

                Divider().frame(height: 24)

                // Color swatches
                ForEach([Color.red, Color.orange, Color.yellow, Color.green, Color.blue, Color.white], id: \.self) { c in
                    Circle()
                        .fill(c)
                        .frame(width: drawColor == c && !isErasing ? 26 : 20)
                        .overlay(Circle().stroke(palette.border, lineWidth: drawColor == c && !isErasing ? 2 : 0))
                        .onTapGesture { drawColor = c; isErasing = false }
                }

                Divider().frame(height: 24)

                Button {
                    isErasing.toggle()
                } label: {
                    Image(systemName: isErasing ? "eraser.fill" : "eraser")
                        .font(.system(size: 18, weight: .medium))
                        .foregroundStyle(isErasing ? .orange : palette.chromeIconForeground)
                }

                Button {
                    if !strokes.isEmpty { strokes.removeLast() }
                } label: {
                    Image(systemName: "arrow.uturn.backward")
                        .font(.system(size: 18, weight: .medium))
                        .foregroundStyle(strokes.isEmpty ? palette.border : palette.chromeIconForeground)
                }
                .disabled(strokes.isEmpty)
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .background(palette.barBackground)
        }
    }

    @ViewBuilder private var describePhase: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Preview thumbnail
                if let img = renderedImage() {
                    Image(uiImage: img)
                        .resizable().scaledToFit()
                        .frame(maxWidth: .infinity, maxHeight: 180)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(palette.border, lineWidth: 1))
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Title").font(.system(size: 11, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                    TextField("Short description of the bug", text: $title)
                        .font(.system(size: 14, design: .rounded))
                        .padding(10)
                        .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 8))
                }

                VStack(alignment: .leading, spacing: 8) {
                    Text("Details").font(.system(size: 11, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                    TextField("Steps to reproduce, expected vs actual behavior…", text: $description, axis: .vertical)
                        .font(.system(size: 14, design: .rounded))
                        .lineLimit(4...8)
                        .padding(10)
                        .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 8))
                }

                // Debug info
                VStack(alignment: .leading, spacing: 8) {
                    Text("Debug Info").font(.system(size: 11, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 6) {
                            Image(systemName: "mappin.circle.fill").foregroundStyle(.purple).font(.system(size: 11))
                            Text("Route: \(currentRoute.isEmpty ? "unknown" : currentRoute)")
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundStyle(.primary)
                        }

                        Divider()

                        if networkLog.isEmpty {
                            Text("No network calls recorded")
                                .font(.system(size: 11, design: .monospaced))
                                .foregroundStyle(.secondary)
                        } else {
                            ForEach(networkLog) { entry in
                                HStack(spacing: 6) {
                                    // Status color dot
                                    Circle()
                                        .fill(entry.status == -1 ? Color.red : entry.status < 300 ? Color.green : Color.orange)
                                        .frame(width: 6, height: 6)
                                    Text(entry.method)
                                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                                        .foregroundStyle(.secondary)
                                    Text(entry.path)
                                        .font(.system(size: 11, design: .monospaced))
                                        .lineLimit(1)
                                        .truncationMode(.middle)
                                    Spacer(minLength: 4)
                                    if entry.status == -1 {
                                        Text("ERR")
                                            .font(.system(size: 10, weight: .bold, design: .monospaced))
                                            .foregroundStyle(.red)
                                    } else {
                                        Text("\(entry.status)")
                                            .font(.system(size: 10, weight: .bold, design: .monospaced))
                                            .foregroundStyle(entry.status < 300 ? .green : .orange)
                                    }
                                    Text(String(format: "%.0fms", entry.duration * 1000))
                                        .font(.system(size: 10, design: .monospaced))
                                        .foregroundStyle(.secondary)
                                }
                                if let err = entry.error {
                                    Text(err)
                                        .font(.system(size: 10, design: .monospaced))
                                        .foregroundStyle(.red)
                                        .lineLimit(1)
                                        .padding(.leading, 12)
                                }
                            }
                        }
                    }
                    .padding(10)
                    .background(Color.black.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(palette.border, lineWidth: 1))
                }
            }
            .padding(16)
        }
    }

    private func renderedImage() -> UIImage? {
        guard let base = screenshot else { return nil }
        let renderer = UIGraphicsImageRenderer(size: base.size)
        return renderer.image { ctx in
            base.draw(at: .zero)
            let scale = base.size.width / UIScreen.main.bounds.width
            ctx.cgContext.setLineCap(.round)
            ctx.cgContext.setLineJoin(.round)
            for stroke in strokes {
                guard stroke.points.count > 1 else { continue }
                let uiColor = UIColor(Color(hex: stroke.colorHex) ?? .red)
                ctx.cgContext.setStrokeColor(uiColor.cgColor)
                ctx.cgContext.setLineWidth(stroke.lineWidth * scale)
                ctx.cgContext.move(to: CGPoint(x: stroke.points[0].x * scale, y: stroke.points[0].y * scale))
                for p in stroke.points.dropFirst() {
                    ctx.cgContext.addLine(to: CGPoint(x: p.x * scale, y: p.y * scale))
                }
                ctx.cgContext.strokePath()
            }
        }
    }

    private func saveBug() {
        let id = UUID()
        var filename: String?
        if let img = renderedImage() {
            filename = BugReportStore.shared.saveImage(img, id: id)
        }
        let report = BugReport(
            id: id,
            title: title.isEmpty ? "Untitled Bug" : title,
            description: description,
            screenshotFilename: filename,
            strokes: strokes,
            status: .open,
            route: currentRoute,
            networkLog: networkLog,
            createdAt: Date(),
            updatedAt: Date()
        )
        onSave(report)
        dismiss()
    }
}

// MARK: - Drawing canvas

struct DrawingCanvas: View {
    @Binding var strokes: [DrawnStroke]
    let drawColor: Color
    let lineWidth: Double
    let isErasing: Bool

    @State private var currentPoints: [CGPoint] = []
    @State private var canvasSize: CGSize = .zero

    var body: some View {
        Canvas { ctx, size in
            canvasSize = size
            for stroke in strokes {
                guard stroke.points.count > 1 else { continue }
                var path = Path()
                path.move(to: stroke.points[0].cgPoint)
                for p in stroke.points.dropFirst() { path.addLine(to: p.cgPoint) }
                let color = Color(hex: stroke.colorHex) ?? .red
                ctx.stroke(path, with: .color(color), style: StrokeStyle(lineWidth: stroke.lineWidth, lineCap: .round, lineJoin: .round))
            }
            if currentPoints.count > 1 {
                var path = Path()
                path.move(to: currentPoints[0])
                for p in currentPoints.dropFirst() { path.addLine(to: p) }
                ctx.stroke(path, with: .color(drawColor), style: StrokeStyle(lineWidth: lineWidth, lineCap: .round, lineJoin: .round))
            }
        }
        .gesture(
            DragGesture(minimumDistance: 0, coordinateSpace: .local)
                .onChanged { v in currentPoints.append(v.location) }
                .onEnded { _ in
                    guard currentPoints.count > 1 else { currentPoints = []; return }
                    if isErasing {
                        eraseNear(currentPoints)
                    } else {
                        strokes.append(DrawnStroke(
                            points: currentPoints.map { CodablePoint($0) },
                            colorHex: drawColor.hexString,
                            lineWidth: lineWidth
                        ))
                    }
                    currentPoints = []
                }
        )
        .background(Color.clear)
    }

    private func eraseNear(_ points: [CGPoint]) {
        let eraserRadius: Double = 20
        strokes = strokes.filter { stroke in
            !stroke.points.contains { sp in
                points.contains { ep in
                    let dx = sp.x - ep.x
                    let dy = sp.y - ep.y
                    return sqrt(dx*dx + dy*dy) < eraserRadius
                }
            }
        }
    }
}

// MARK: - Bug detail sheet

struct BugDetailSheet: View {
    @State var report: BugReport
    let palette: QuailThemePalette
    let onUpdate: (BugReport) -> Void
    let onDelete: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var editingTitle = false
    @State private var tempTitle = ""
    @State private var showingDeleteConfirm = false
    @State private var resolvedScreenshotFilename: String?
    @State private var isLoadingScreenshot = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Button("Done") { onUpdate(report); dismiss() }
                    .font(.system(size: 14, weight: .medium, design: .rounded))
                Spacer()
                Text(report.title).font(.system(size: 15, weight: .bold, design: .rounded)).lineLimit(1)
                Spacer()
                Button(role: .destructive) { showingDeleteConfirm = true } label: {
                    Image(systemName: "trash").font(.system(size: 14, weight: .medium)).foregroundStyle(.red)
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 14)
            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    // Screenshot — loaded locally, or downloaded on demand if only present on the server.
                    if let filename = resolvedScreenshotFilename ?? report.screenshotFilename,
                       let img = BugReportStore.shared.loadImage(filename: filename) {
                        Image(uiImage: img)
                            .resizable().scaledToFit()
                            .frame(maxWidth: .infinity)
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                    } else if report.hasRemoteScreenshot {
                        VStack(spacing: 8) {
                            ProgressView()
                            Text("Loading screenshot…")
                                .font(.system(size: 11, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, minHeight: 100)
                        .task {
                            guard !isLoadingScreenshot else { return }
                            isLoadingScreenshot = true
                            if let filename = await BugReportStore.shared.ensureScreenshotDownloaded(for: report) {
                                report.screenshotFilename = filename
                                resolvedScreenshotFilename = filename
                            }
                            isLoadingScreenshot = false
                        }
                    }

                    // Status picker
                    VStack(alignment: .leading, spacing: 8) {
                        Text("STATUS").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                        HStack(spacing: 8) {
                            ForEach(BugStatus.allCases, id: \.rawValue) { s in
                                Button {
                                    report.status = s
                                    report.updatedAt = Date()
                                } label: {
                                    Text(s.label)
                                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                                        .foregroundStyle(report.status == s ? .white : s.color)
                                        .padding(.horizontal, 12).padding(.vertical, 7)
                                        .background(report.status == s ? s.color : s.color.opacity(0.1), in: Capsule())
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }

                    // Title
                    VStack(alignment: .leading, spacing: 6) {
                        Text("TITLE").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                        TextField("Bug title", text: $report.title)
                            .font(.system(size: 14, design: .rounded))
                            .padding(10)
                            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 8))
                    }

                    // Description
                    VStack(alignment: .leading, spacing: 6) {
                        Text("DETAILS").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                        TextField("Description", text: $report.description, axis: .vertical)
                            .font(.system(size: 14, design: .rounded))
                            .lineLimit(3...)
                            .padding(10)
                            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 8))
                    }

                    Text("Logged \(report.createdAt.formatted(date: .abbreviated, time: .shortened))")
                        .font(.system(size: 11, design: .rounded)).foregroundStyle(.tertiary)

                    // Debug info
                    VStack(alignment: .leading, spacing: 8) {
                        Text("DEBUG").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                        VStack(alignment: .leading, spacing: 5) {
                            HStack(spacing: 6) {
                                Image(systemName: "mappin.circle.fill").foregroundStyle(.purple).font(.system(size: 11))
                                Text(report.route.isEmpty ? "unknown" : report.route)
                                    .font(.system(size: 12, design: .monospaced))
                            }
                            if !report.networkLog.isEmpty {
                                Divider()
                                ForEach(report.networkLog) { entry in
                                    HStack(spacing: 6) {
                                        Circle()
                                            .fill(entry.status == -1 ? Color.red : entry.status < 300 ? Color.green : Color.orange)
                                            .frame(width: 6, height: 6)
                                        Text(entry.method)
                                            .font(.system(size: 10, weight: .bold, design: .monospaced))
                                            .foregroundStyle(.secondary)
                                        Text(entry.path)
                                            .font(.system(size: 11, design: .monospaced))
                                            .lineLimit(1).truncationMode(.middle)
                                        Spacer(minLength: 4)
                                        Text(entry.status == -1 ? "ERR" : "\(entry.status)")
                                            .font(.system(size: 10, weight: .bold, design: .monospaced))
                                            .foregroundStyle(entry.status == -1 ? .red : entry.status < 300 ? .green : .orange)
                                        Text(String(format: "%.0fms", entry.duration * 1000))
                                            .font(.system(size: 10, design: .monospaced))
                                            .foregroundStyle(.secondary)
                                    }
                                    if let err = entry.error {
                                        Text(err).font(.system(size: 10, design: .monospaced)).foregroundStyle(.red).lineLimit(1).padding(.leading, 12)
                                    }
                                }
                            }
                        }
                        .padding(10)
                        .background(Color.black.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))
                        .overlay(RoundedRectangle(cornerRadius: 8).stroke(palette.border, lineWidth: 1))
                    }
                }
                .padding(16)
            }
        }
        .confirmationDialog("Delete Bug?", isPresented: $showingDeleteConfirm, titleVisibility: .visible) {
            Button("Delete", role: .destructive) { onDelete(); dismiss() }
        }
    }
}

// MARK: - Color helpers

extension Color {
    init?(hex: String) {
        var s = hex.trimmingCharacters(in: .whitespacesAndNewlines)
        if s.hasPrefix("#") { s = String(s.dropFirst()) }
        guard s.count == 6, let v = UInt64(s, radix: 16) else { return nil }
        self.init(red: Double((v >> 16) & 0xFF)/255, green: Double((v >> 8) & 0xFF)/255, blue: Double(v & 0xFF)/255)
    }

    var hexString: String {
        let c = UIColor(self).cgColor.components ?? [0,0,0,1]
        return String(format: "#%02X%02X%02X", Int(c[0]*255), Int(c[1]*255), Int(c[2]*255))
    }
}

// MARK: - Global bug report FAB (injected into AppChromeFrame via environment)

struct BugReportFAB: View {
    let palette: QuailThemePalette
    @EnvironmentObject private var navigator: AppNavigator
    @ObservedObject private var netLog = NetworkLogger.shared
    @State private var showingSheet = false
    @State private var captured: UIImage?
    @State private var capturedRoute: String = ""
    @State private var capturedNetLog: [NetworkLogEntry] = []

    var body: some View {
        Button {
            // Snapshot debug context immediately
            capturedRoute = "\(navigator.rootRoute)"
            capturedNetLog = Array(netLog.entries.prefix(10))
            // Slight delay so button tap highlight clears before capture
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                captured = captureAppScreenshot()
                // Open sheet on next tick so SwiftUI has committed the captured image
                DispatchQueue.main.async {
                    showingSheet = true
                }
            }
        } label: {
            Image(systemName: "ladybug.fill")
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 32, height: 32)
                .background(Color.red, in: Circle())
                .shadow(color: .black.opacity(0.2), radius: 4, y: 2)
        }
        .buttonStyle(.plain)
        .sheet(isPresented: $showingSheet) {
            NewBugSheet(
                initialScreenshot: captured,
                currentRoute: capturedRoute,
                networkLog: capturedNetLog,
                palette: palette
            ) { report in
                BugReportStore.shared.add(report)
            }
            .presentationDetents([.large])
        }
    }
}
