import Foundation
import AppIntents
import ActivityKit
import UserNotifications
import UIKit

struct QueuedCsvImportItem: Codable, Identifiable, Hashable {
    enum Status: String, Codable {
        case assigned
        case processing
        case imported
        case needsReview
        case failed
    }

    let id: UUID
    let originalFileName: String
    let storedFileName: String
    let accountID: Int
    let accountLabel: String
    let headerSignature: String
    let queuedAt: Date
    var status: Status
    var detail: String
}

enum ImportQueueStore {
    private static let encoder = JSONEncoder()
    private static let decoder = JSONDecoder()

    private static var directoryURL: URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        let url = base.appendingPathComponent("ImportQueue", isDirectory: true)
        if !FileManager.default.fileExists(atPath: url.path) {
            try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        }
        return url
    }

    private static var manifestURL: URL {
        directoryURL.appendingPathComponent("queue.json")
    }

    static func load() -> [QueuedCsvImportItem] {
        guard let data = try? Data(contentsOf: manifestURL),
              let items = try? decoder.decode([QueuedCsvImportItem].self, from: data) else {
            return []
        }
        return items
    }

    static func save(_ items: [QueuedCsvImportItem]) {
        guard let data = try? encoder.encode(items) else { return }
        try? data.write(to: manifestURL, options: [.atomic])
    }

    static func enqueue(fileData: Data, originalFileName: String, accountID: Int, accountLabel: String, headerSignature: String, status: QueuedCsvImportItem.Status, detail: String) throws -> QueuedCsvImportItem {
        let storedFileName = "\(UUID().uuidString)-\(sanitizedFileName(originalFileName))"
        let targetURL = directoryURL.appendingPathComponent(storedFileName)
        try fileData.write(to: targetURL, options: [.atomic])
        return createManifestItem(
            originalFileName: originalFileName,
            storedFileName: storedFileName,
            accountID: accountID,
            accountLabel: accountLabel,
            headerSignature: headerSignature,
            status: status,
            detail: detail
        )
    }

    static func enqueue(sourceURL: URL, originalFileName: String, accountID: Int, accountLabel: String, headerSignature: String, status: QueuedCsvImportItem.Status, detail: String) throws -> QueuedCsvImportItem {
        let storedFileName = "\(UUID().uuidString)-\(sanitizedFileName(originalFileName))"
        let targetURL = directoryURL.appendingPathComponent(storedFileName)
        let accessed = sourceURL.startAccessingSecurityScopedResource()
        defer {
            if accessed { sourceURL.stopAccessingSecurityScopedResource() }
        }
        if FileManager.default.fileExists(atPath: targetURL.path) {
            try? FileManager.default.removeItem(at: targetURL)
        }
        try FileManager.default.copyItem(at: sourceURL, to: targetURL)
        return createManifestItem(
            originalFileName: originalFileName,
            storedFileName: storedFileName,
            accountID: accountID,
            accountLabel: accountLabel,
            headerSignature: headerSignature,
            status: status,
            detail: detail
        )
    }

    private static func createManifestItem(originalFileName: String, storedFileName: String, accountID: Int, accountLabel: String, headerSignature: String, status: QueuedCsvImportItem.Status, detail: String) -> QueuedCsvImportItem {
        var items = load()
        let item = QueuedCsvImportItem(
            id: UUID(),
            originalFileName: originalFileName,
            storedFileName: storedFileName,
            accountID: accountID,
            accountLabel: accountLabel,
            headerSignature: headerSignature,
            queuedAt: Date(),
            status: status,
            detail: detail
        )
        items.insert(item, at: 0)
        save(items)
        return item
    }

    static func updateStatus(id: UUID, status: QueuedCsvImportItem.Status, detail: String) {
        var items = load()
        guard let index = items.firstIndex(where: { $0.id == id }) else { return }
        items[index].status = status
        items[index].detail = detail
        save(items)
    }

    static func remove(id: UUID) {
        var items = load()
        guard let index = items.firstIndex(where: { $0.id == id }) else { return }
        let item = items.remove(at: index)
        try? FileManager.default.removeItem(at: storedFileURL(for: item))
        save(items)
    }

    static func storedFileURL(for item: QueuedCsvImportItem) -> URL {
        directoryURL.appendingPathComponent(item.storedFileName)
    }

    private static func sanitizedFileName(_ name: String) -> String {
        let cleaned = name.replacingOccurrences(of: "[^A-Za-z0-9._-]+", with: "-", options: .regularExpression)
        return cleaned.isEmpty ? "import.csv" : cleaned
    }
}

struct ShortcutImportRunSummary {
    let status: QueuedCsvImportItem.Status
    let detail: String
    let fileTransactionCount: Int
    let processedTransactions: Int
    let skippedTransactions: Int
}

struct ShortcutImportProgressSnapshot {
    let status: String
    let fileTransactionCount: Int
}

enum ShortcutImportProcessor {
    @MainActor
    static func assign(
        intentFile: IntentFile,
        originalName: String,
        accountID: Int,
        accountLabel: String
    ) async -> ShortcutImportRunSummary {
        do {
            if let sourceURL = intentFile.fileURL {
                _ = try ImportQueueStore.enqueue(
                    sourceURL: sourceURL,
                    originalFileName: originalName,
                    accountID: accountID,
                    accountLabel: accountLabel,
                    headerSignature: "",
                    status: .assigned,
                    detail: "Assigned to \(accountLabel). Ready for batch processing."
                )
            } else {
                let fileData = intentFile.data
                _ = try ImportQueueStore.enqueue(
                    fileData: fileData,
                    originalFileName: originalName,
                    accountID: accountID,
                    accountLabel: accountLabel,
                    headerSignature: "",
                    status: .assigned,
                    detail: "Assigned to \(accountLabel). Ready for batch processing."
                )
            }
        } catch {
            let detail = "Assign failed: \(error.localizedDescription)"
            return ShortcutImportRunSummary(status: .assigned, detail: detail, fileTransactionCount: 0, processedTransactions: 0, skippedTransactions: 0)
        }

        let detail = "Assigned to \(accountLabel). Ready for batch processing."
        return ShortcutImportRunSummary(status: .assigned, detail: detail, fileTransactionCount: 0, processedTransactions: 0, skippedTransactions: 0)
    }

    @MainActor
    static func process(
        fileData: Data,
        originalName: String,
        accountID: Int,
        accountLabel: String,
        existingQueueID: UUID? = nil,
        progress: ((ShortcutImportProgressSnapshot) -> Void)? = nil
    ) async -> ShortcutImportRunSummary {
        let stagedURL: URL
        do {
            stagedURL = try stageTemporaryImportFile(data: fileData, originalName: originalName)
        } catch {
            let detail = error.localizedDescription
            if let existingQueueID {
                ImportQueueStore.updateStatus(id: existingQueueID, status: .failed, detail: detail)
            } else {
                _ = try? ImportQueueStore.enqueue(fileData: fileData, originalFileName: originalName, accountID: accountID, accountLabel: accountLabel, headerSignature: "", status: .failed, detail: detail)
            }
            return ShortcutImportRunSummary(status: .failed, detail: detail, fileTransactionCount: 0, processedTransactions: 0, skippedTransactions: 0)
        }
        defer { try? FileManager.default.removeItem(at: stagedURL) }

        do {
            let preview = try await QuailCashAPI.shared.fetchCsvPreview(fileURL: stagedURL)
            progress?(ShortcutImportProgressSnapshot(
                status: "Importing \(preview.rowCount) rows from \(originalName)",
                fileTransactionCount: preview.rowCount
            ))
            let headerSignature = csvHeaderSignature(preview.columns)
            let preset = try await QuailCashAPI.shared.fetchCsvMappingPreset(accountID: accountID)

            guard let preset, presetHasRequiredMapping(preset), presetMatchesPreview(preset, preview: preview) else {
                let detail = "Saved mapping missing or header did not match. Review in app."
                if let existingQueueID {
                    ImportQueueStore.updateStatus(id: existingQueueID, status: .needsReview, detail: detail)
                } else {
                    _ = try? ImportQueueStore.enqueue(
                        fileData: fileData,
                        originalFileName: originalName,
                        accountID: accountID,
                        accountLabel: accountLabel,
                        headerSignature: headerSignature,
                        status: .needsReview,
                        detail: detail
                    )
                }
                return ShortcutImportRunSummary(status: .needsReview, detail: detail, fileTransactionCount: preview.rowCount, processedTransactions: 0, skippedTransactions: 0)
            }

            let jobID = try await QuailCashAPI.shared.importCsvMappedAsync(fileURL: stagedURL, fields: mappingFields(from: preset, accountID: accountID))
            var jobStatus: CsvJobStatusPayload
            while true {
                try await Task.sleep(nanoseconds: 800_000_000)
                jobStatus = try await QuailCashAPI.shared.pollCsvJob(jobID: jobID)
                progress?(ShortcutImportProgressSnapshot(
                    status: "Row \(jobStatus.processedRows ?? 0) of \(jobStatus.totalRows ?? preview.rowCount)",
                    fileTransactionCount: jobStatus.totalRows ?? preview.rowCount
                ))
                if jobStatus.status == "done" || jobStatus.status == "failed" { break }
            }
            if jobStatus.status == "failed" {
                throw NSError(domain: "CsvImport", code: 0, userInfo: [NSLocalizedDescriptionKey: jobStatus.error ?? "Import failed"])
            }
            let detail = "Inserted \(jobStatus.inserted ?? 0), updated \(jobStatus.updated ?? 0), skipped \(jobStatus.skipped ?? 0)."
            if let existingQueueID {
                ImportQueueStore.updateStatus(id: existingQueueID, status: .imported, detail: detail)
            } else {
                _ = try? ImportQueueStore.enqueue(
                    fileData: fileData,
                    originalFileName: originalName,
                    accountID: accountID,
                    accountLabel: accountLabel,
                    headerSignature: headerSignature,
                    status: .imported,
                    detail: detail
                )
            }
            return ShortcutImportRunSummary(
                status: .imported,
                detail: detail,
                fileTransactionCount: jobStatus.totalRows ?? preview.rowCount,
                processedTransactions: (jobStatus.inserted ?? 0) + (jobStatus.updated ?? 0),
                skippedTransactions: jobStatus.skipped ?? 0
            )
        } catch {
            let detail = error.localizedDescription
            if let existingQueueID {
                ImportQueueStore.updateStatus(id: existingQueueID, status: .failed, detail: detail)
            } else {
                _ = try? ImportQueueStore.enqueue(
                    fileData: fileData,
                    originalFileName: originalName,
                    accountID: accountID,
                    accountLabel: accountLabel,
                    headerSignature: "",
                    status: .failed,
                    detail: detail
                )
            }
            return ShortcutImportRunSummary(status: .failed, detail: detail, fileTransactionCount: 0, processedTransactions: 0, skippedTransactions: 0)
        }
    }

    private static func stageTemporaryImportFile(data: Data, originalName: String) throws -> URL {
        let fileName = originalName.isEmpty ? "transactions.csv" : originalName
        let ext = URL(fileURLWithPath: fileName).pathExtension.isEmpty ? "csv" : URL(fileURLWithPath: fileName).pathExtension
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("shortcut-import-\(UUID().uuidString).\(ext)")
        try data.write(to: url, options: [.atomic])
        return url
    }

    private static func presetHasRequiredMapping(_ preset: CsvMappingPresetPayload) -> Bool {
        guard preset.purchaseCol != nil, preset.merchantCol != nil else { return false }
        if preset.amountCol != nil { return true }
        return preset.debitCol != nil && preset.creditCol != nil
    }

    private static func presetMatchesPreview(_ preset: CsvMappingPresetPayload, preview: CsvPreviewPayload) -> Bool {
        let previewSignature = csvHeaderSignature(preview.columns)
        if let saved = preset.headerSignature, !saved.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return normalizedText(saved) == previewSignature
        }
        return requiredPresetIndicesExist(preset, in: preview.columns)
    }

    private static func requiredPresetIndicesExist(_ preset: CsvMappingPresetPayload, in columns: [CsvPreviewColumnPayload]) -> Bool {
        let valid = Set(columns.map(\.index))
        let required = [
            preset.purchaseCol,
            preset.merchantCol,
            preset.amountCol,
            preset.debitCol,
            preset.creditCol,
            preset.postedCol,
            preset.indicatorCol,
        ].compactMap { $0 }
        return required.allSatisfy { valid.contains($0) }
    }

    private static func mappingFields(from preset: CsvMappingPresetPayload, accountID: Int) -> [String: String] {
        var fields: [String: String] = [
            "delimiter": "auto",
            "account_id": String(accountID),
            "credit_indicator_value": preset.creditIndicatorValue ?? "credit",
            "invert_amount": preset.invertAmount ? "true" : "false",
        ]
        if let purchase = preset.purchaseCol { fields["purchase_col"] = String(purchase) }
        if let posted = preset.postedCol { fields["posted_col"] = String(posted) }
        if let merchant = preset.merchantCol { fields["merchant_col"] = String(merchant) }
        if let amount = preset.amountCol {
            fields["amount_col"] = String(amount)
        } else {
            if let debit = preset.debitCol { fields["debit_col"] = String(debit) }
            if let credit = preset.creditCol { fields["credit_col"] = String(credit) }
        }
        if let indicator = preset.indicatorCol { fields["indicator_col"] = String(indicator) }
        return fields
    }

    private static func csvHeaderSignature(_ columns: [CsvPreviewColumnPayload]) -> String {
        normalizedText(columns.map(\.label).joined(separator: "|"))
    }

    private static func normalizedText(_ text: String) -> String {
        text.lowercased()
            .replacingOccurrences(of: "[^a-z0-9]+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    @MainActor
    static func processAllAssigned() async -> (processed: Int, imported: Int, review: Int, failed: Int) {
        var items = ImportQueueStore.load()
        let candidates = items.filter { $0.status == .assigned || $0.status == .failed || $0.status == .needsReview }
        guard candidates.isEmpty == false else {
            return (0, 0, 0, 0)
        }

        let activity = ImportLiveActivityManager.start(
            batchName: "Processing \(candidates.count) imports",
            status: "Starting",
            processedFileCount: 0,
            totalFileCount: candidates.count,
            currentFileTransactions: 0,
            importedTransactions: 0,
            skippedTransactions: 0
        )

        var imported = 0
        var review = 0
        var failed = 0
        var importedTransactions = 0
        var skippedTransactions = 0

        for (index, item) in candidates.enumerated() {
            ImportQueueStore.updateStatus(id: item.id, status: .processing, detail: "Processing \(item.originalFileName)...")
            await ImportLiveActivityManager.update(
                activity,
                status: "\(item.accountLabel): \(item.originalFileName)",
                processedFileCount: index,
                totalFileCount: candidates.count,
                currentFileTransactions: 0,
                importedTransactions: importedTransactions,
                skippedTransactions: skippedTransactions
            )
            let fileURL = ImportQueueStore.storedFileURL(for: item)
            guard let data = try? Data(contentsOf: fileURL) else {
                failed += 1
                ImportQueueStore.updateStatus(id: item.id, status: .failed, detail: "Stored file could not be read.")
                await ImportLiveActivityManager.update(
                    activity,
                    status: "Missing stored file",
                    processedFileCount: index + 1,
                    totalFileCount: candidates.count,
                    currentFileTransactions: 0,
                    importedTransactions: importedTransactions,
                    skippedTransactions: skippedTransactions
                )
                continue
            }

            let summary = await process(
                fileData: data,
                originalName: item.originalFileName,
                accountID: item.accountID,
                accountLabel: item.accountLabel,
                existingQueueID: item.id,
                progress: { snapshot in
                    Task { @MainActor in
                        await ImportLiveActivityManager.update(
                            activity,
                            status: snapshot.status,
                            processedFileCount: index,
                            totalFileCount: candidates.count,
                            currentFileTransactions: snapshot.fileTransactionCount,
                            importedTransactions: importedTransactions,
                            skippedTransactions: skippedTransactions
                        )
                    }
                }
            )
            switch summary.status {
            case .imported:
                imported += 1
            case .needsReview:
                review += 1
            case .failed:
                failed += 1
            case .assigned, .processing:
                break
            }
            importedTransactions += summary.processedTransactions
            skippedTransactions += summary.skippedTransactions

            await ImportLiveActivityManager.update(
                activity,
                status: "Processed \(index + 1) of \(candidates.count)",
                processedFileCount: index + 1,
                totalFileCount: candidates.count,
                currentFileTransactions: summary.fileTransactionCount,
                importedTransactions: importedTransactions,
                skippedTransactions: skippedTransactions
            )
        }

        let finalStatus = review > 0 ? "Needs review" : failed > 0 ? "Completed with failures" : "Completed"
        await ImportLiveActivityManager.end(
            activity,
            status: finalStatus,
            processedFileCount: candidates.count,
            totalFileCount: candidates.count,
            currentFileTransactions: 0,
            importedTransactions: importedTransactions,
            skippedTransactions: skippedTransactions
        )
        items = ImportQueueStore.load()
        _ = items
        return (candidates.count, imported, review, failed)
    }
}

enum ImportLiveActivityManager {
    static func start(
        batchName: String,
        status: String,
        processedFileCount: Int,
        totalFileCount: Int,
        currentFileTransactions: Int,
        importedTransactions: Int,
        skippedTransactions: Int
    ) -> Activity<ImportBatchAttributes>? {
        guard ActivityAuthorizationInfo().areActivitiesEnabled else { return nil }
        let attributes = ImportBatchAttributes(batchName: batchName)
        let state = ImportBatchAttributes.ContentState(
            title: batchName,
            status: status,
            processedFileCount: processedFileCount,
            totalFileCount: totalFileCount,
            currentFileTransactions: currentFileTransactions,
            importedTransactions: importedTransactions,
            skippedTransactions: skippedTransactions
        )
        return try? Activity.request(attributes: attributes, content: .init(state: state, staleDate: nil))
    }

    static func update(
        _ activity: Activity<ImportBatchAttributes>?,
        status: String,
        processedFileCount: Int,
        totalFileCount: Int,
        currentFileTransactions: Int,
        importedTransactions: Int,
        skippedTransactions: Int
    ) async {
        guard let activity else { return }
        let state = ImportBatchAttributes.ContentState(
            title: activity.attributes.batchName,
            status: status,
            processedFileCount: processedFileCount,
            totalFileCount: totalFileCount,
            currentFileTransactions: currentFileTransactions,
            importedTransactions: importedTransactions,
            skippedTransactions: skippedTransactions
        )
        await activity.update(.init(state: state, staleDate: nil))
    }

    static func end(
        _ activity: Activity<ImportBatchAttributes>?,
        status: String,
        processedFileCount: Int,
        totalFileCount: Int,
        currentFileTransactions: Int,
        importedTransactions: Int,
        skippedTransactions: Int
    ) async {
        guard let activity else { return }
        let state = ImportBatchAttributes.ContentState(
            title: activity.attributes.batchName,
            status: status,
            processedFileCount: processedFileCount,
            totalFileCount: totalFileCount,
            currentFileTransactions: currentFileTransactions,
            importedTransactions: importedTransactions,
            skippedTransactions: skippedTransactions
        )
        let content = ActivityContent(state: state, staleDate: nil)
        await activity.update(
            content,
            alertConfiguration: AlertConfiguration(
                title: "\(activity.attributes.batchName)",
                body: "\(status)",
                sound: .default
            )
        )
        await activity.end(content, dismissalPolicy: .default)
    }
}

enum LocalNotificationHelper {
    static func ensureAuthorization() async -> Bool {
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        switch settings.authorizationStatus {
        case .authorized, .provisional, .ephemeral:
            return true
        case .notDetermined:
            return (try? await center.requestAuthorization(options: [.alert, .badge, .sound])) ?? false
        case .denied:
            return false
        @unknown default:
            return false
        }
    }

    static func notify(title: String, body: String) async {
        guard await ensureAuthorization() else { return }
        let center = UNUserNotificationCenter.current()
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
        try? await center.add(request)
    }
}

struct QuailAccountEntity: AppEntity, Identifiable, Hashable {
    static var typeDisplayRepresentation = TypeDisplayRepresentation(name: "Account")
    static var defaultQuery = QuailAccountEntityQuery()

    let id: Int
    let label: String
    let bank: String
    let isCredit: Bool

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\(label)", subtitle: "\(bank)")
    }
}

struct QuailAccountEntityQuery: EntityQuery {
    func entities(for identifiers: [QuailAccountEntity.ID]) async throws -> [QuailAccountEntity] {
        let all = try await suggestedEntities()
        let wanted = Set(identifiers)
        return all.filter { wanted.contains($0.id) }
    }

    func suggestedEntities() async throws -> [QuailAccountEntity] {
        let payload = try await QuailCashAPI.shared.fetchBankInfo()
        let accounts = payload.accounts.map {
            QuailAccountEntity(id: $0.id, label: "\($0.bank) - \($0.name)", bank: $0.bank, isCredit: false)
        }
        let cards = payload.creditCards.map {
            QuailAccountEntity(id: $0.id, label: "\($0.bank) - \($0.name) (credit)", bank: $0.bank, isCredit: true)
        }
        return accounts + cards
    }
}

struct AssignBankCsvToAccountIntent: AppIntent {
    static var title: LocalizedStringResource = "Assign Bank CSV To Account"
    static var description = IntentDescription("Assign a downloaded bank CSV to an account and stage it for later batch processing.")
    static var openAppWhenRun: Bool = false

    @Parameter(title: "CSV File")
    var file: IntentFile

    @Parameter(title: "Account")
    var account: QuailAccountEntity

    @MainActor
    func perform() async throws -> some IntentResult {
        let originalName = file.filename
        _ = await ShortcutImportProcessor.assign(
            intentFile: file,
            originalName: originalName,
            accountID: account.id,
            accountLabel: account.label
        )
        await LocalNotificationHelper.notify(title: "CSV assigned", body: "\(account.label): \(originalName)")
        return .result()
    }

}

struct ProcessAssignedCsvQueueIntent: AppIntent {
    static var title: LocalizedStringResource = "Process Assigned CSV Queue"
    static var description = IntentDescription("Process all staged CSV files using their assigned accounts, with live progress and a completion notification.")
    static var openAppWhenRun: Bool = false

    @MainActor
    func perform() async throws -> some IntentResult {
        let summary = await ShortcutImportProcessor.processAllAssigned()
        guard summary.processed > 0 else {
            return .result()
        }
        let body = "\(summary.imported) imported, \(summary.review) need review, \(summary.failed) failed."
        await LocalNotificationHelper.notify(title: "CSV queue complete", body: body)
        return .result()
    }
}

struct QuailCashAppShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: AssignBankCsvToAccountIntent(),
            phrases: [
                "Assign bank CSV with \(.applicationName)",
                "Stage bank import in \(.applicationName)"
            ],
            shortTitle: "Assign CSV",
            systemImageName: "tray.and.arrow.down"
        )
        AppShortcut(
            intent: ProcessAssignedCsvQueueIntent(),
            phrases: [
                "Process assigned CSV queue with \(.applicationName)",
                "Run staged bank imports in \(.applicationName)"
            ],
            shortTitle: "Process CSV Queue",
            systemImageName: "play.circle"
        )
        AppShortcut(
            intent: LogFuelFillupIntent(),
            phrases: [
                "Log gas fill-up in \(.applicationName)",
                "Record gas in \(.applicationName)",
                "Log fuel in \(.applicationName)",
                "Add fill-up to \(.applicationName)"
            ],
            shortTitle: "Log Gas Fill-Up",
            systemImageName: "fuelpump.fill"
        )
    }
}
