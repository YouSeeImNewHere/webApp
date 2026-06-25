import Foundation
import ActivityKit

struct ImportBatchAttributes: ActivityAttributes {
    struct ContentState: Codable, Hashable {
        var title: String
        var status: String
        var processedFileCount: Int
        var totalFileCount: Int
        var currentFileTransactions: Int
        var importedTransactions: Int
        var skippedTransactions: Int
    }

    var batchName: String
}
