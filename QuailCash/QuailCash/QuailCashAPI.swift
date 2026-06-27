import Foundation
import WebKit

enum QuailCashAPIError: LocalizedError {
    case unauthorized
    case badResponse
    case decodingFailed
    case transport(Error)

    var errorDescription: String? {
        switch self {
        case .unauthorized:
            return "You need to sign in first."
        case .badResponse:
            return "The server returned an unexpected response."
        case .decodingFailed:
            return "Could not read the server response."
        case .transport(let error):
            return error.localizedDescription
        }
    }
}

final class QuailCashAPI {
    static let shared = QuailCashAPI()

    private let session: URLSession

    private init() {
        let configuration = URLSessionConfiguration.default
        configuration.httpCookieStorage = .shared
        configuration.httpShouldSetCookies = true
        configuration.httpCookieAcceptPolicy = .always
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.timeoutIntervalForRequest = 60
        configuration.timeoutIntervalForResource = 120
        configuration.waitsForConnectivity = true
        session = URLSession(configuration: configuration)
    }

    private enum RequestTimeout {
        static let standard: TimeInterval = 30
        static let standardResource: TimeInterval = 60
        static let csvPreview: TimeInterval = 90
        static let csvDryRun: TimeInterval = 180
        static let csvImport: TimeInterval = 1800
    }

    func fetchHome(txLimit: Int = 15) async throws -> HomePayload {
        let request = makeRequest(url: AppConfig.homeURL(txLimit: txLimit))
        print("[QuailCash] QuailCashAPI.fetchHome url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchHome status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }

        do {
            return try JSONDecoder.quailCash.decode(HomePayload.self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.decodeFailure bodyPrefix=\(String(text.prefix(800)))")
            } else {
                print("[QuailCash] QuailCashAPI.decodeFailure body is not utf8")
            }
            if let decodingError = error as? DecodingError {
                print("[QuailCash] QuailCashAPI.decodingError=\(Self.describe(decodingError))")
            } else {
                print("[QuailCash] QuailCashAPI.decodeFailure error=\(error.localizedDescription)")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchTransactions(limit: Int = 100) async throws -> [TransactionItem] {
        let request = makeRequest(url: AppConfig.url(path: "/transactions", queryItems: [
            URLQueryItem(name: "limit", value: String(limit))
        ]))
        print("[QuailCash] QuailCashAPI.fetchTransactions url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchTransactions status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode([TransactionItem].self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.transactionsDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchTransactionsAll(limit: Int = 10000, offset: Int = 0) async throws -> [TransactionItem] {
        let request = makeRequest(url: AppConfig.url(path: "/transactions-all", queryItems: [
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset))
        ]))
        print("[QuailCash] QuailCashAPI.fetchTransactionsAll url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchTransactionsAll status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode([TransactionItem].self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.transactionsAllDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchExtraSaved() async throws -> Double {
        let request = makeRequest(url: AppConfig.url(path: "/extra-saved"))
        print("[QuailCash] QuailCashAPI.fetchExtraSaved url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchExtraSaved status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }

        do {
            let payload = try JSONDecoder.quailCash.decode(ExtraSavedPayload.self, from: data)
            return payload.extraSaved ?? 0
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.extraSavedDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchExtraSavedDetail() async throws -> ExtraSavedDetailPayload {
        let request = makeRequest(url: AppConfig.url(path: "/extra-saved-detail"))
        print("[QuailCash] QuailCashAPI.fetchExtraSavedDetail url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchExtraSavedDetail status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode(ExtraSavedDetailPayload.self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.extraSavedDetailDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchBankInfo() async throws -> BankInfoPayload {
        let request = makeRequest(url: AppConfig.url(path: "/bank-info"))
        print("[QuailCash] QuailCashAPI.fetchBankInfo url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchBankInfo status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode(BankInfoPayload.self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.bankInfoDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchAccountInfo(accountID: Int) async throws -> AccountInfoPayload {
        let request = makeRequest(url: AppConfig.url(path: "/account/\(accountID)"))
        print("[QuailCash] QuailCashAPI.fetchAccountInfo url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchAccountInfo status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode(AccountInfoPayload.self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.accountInfoDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchAccountSeries(accountID: Int, start: String, end: String) async throws -> [ChartSeriesPoint] {
        let request = makeRequest(url: AppConfig.url(path: "/account-series", queryItems: [
            URLQueryItem(name: "account_id", value: String(accountID)),
            URLQueryItem(name: "start", value: start),
            URLQueryItem(name: "end", value: end),
        ]))
        print("[QuailCash] QuailCashAPI.fetchAccountSeries url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchAccountSeries status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode([ChartSeriesPoint].self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.accountSeriesDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchAccountTransactionsRange(accountID: Int, start: String, end: String, limit: Int = 500) async throws -> AccountTransactionsRangePayload {
        let request = makeRequest(url: AppConfig.url(path: "/account-transactions-range", queryItems: [
            URLQueryItem(name: "account_id", value: String(accountID)),
            URLQueryItem(name: "start", value: start),
            URLQueryItem(name: "end", value: end),
            URLQueryItem(name: "limit", value: String(limit)),
        ]))
        print("[QuailCash] QuailCashAPI.fetchAccountTransactionsRange url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchAccountTransactionsRange status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode(AccountTransactionsRangePayload.self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.accountTransactionsRangeDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchNotifications(limit: Int = 100) async throws -> [NotificationItemPayload] {
        let request = makeRequest(url: AppConfig.url(path: "/notifications", queryItems: [
            URLQueryItem(name: "limit", value: String(limit))
        ]))
        print("[QuailCash] QuailCashAPI.fetchNotifications url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchNotifications status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        do {
            struct Wrapper: Decodable { let items: [NotificationItemPayload] }
            let payload = try JSONDecoder.quailCash.decode(Wrapper.self, from: data)
            return payload.items
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.notificationsDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchNotificationDetail(id: Int) async throws -> NotificationDetailPayload {
        let request = makeRequest(url: AppConfig.url(path: "/notifications/\(id)"))
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode(NotificationDetailPayload.self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.notificationDetailDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func markNotificationRead(id: Int) async throws {
        let request = makeRequest(url: AppConfig.url(path: "/notifications/\(id)/read"), method: "POST")
        let (_, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
    }

    func dismissNotification(id: Int) async throws {
        let request = makeRequest(url: AppConfig.url(path: "/notifications/\(id)/dismiss"), method: "POST")
        let (_, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
    }

    func markAllNotificationsRead() async throws {
        let request = makeRequest(url: AppConfig.url(path: "/notifications/mark-all-read"), method: "POST")
        let (_, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
    }

    func clearReadNotifications() async throws {
        let request = makeRequest(url: AppConfig.url(path: "/notifications/clear-read"), method: "POST")
        let (_, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
    }

    func fetchAdminErrorNotifications(limit: Int = 200) async throws -> [AdminErrorNotificationPayload] {
        let request = makeRequest(url: AppConfig.url(path: "/admin/error-notifications", queryItems: [
            URLQueryItem(name: "limit", value: String(limit))
        ]))
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        do {
            struct Wrapper: Decodable { let items: [AdminErrorNotificationPayload] }
            return try JSONDecoder.quailCash.decode(Wrapper.self, from: data).items
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.errorNotificationsDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func clearAdminErrorNotifications() async throws {
        let request = makeRequest(url: AppConfig.url(path: "/admin/error-notifications/clear"), method: "POST", jsonBody: [:])
        let (_, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
    }

    func fetchInfraMetrics() async throws -> InfraMetricsPayload {
        let request = makeRequest(url: AppConfig.url(path: "/admin/infra-metrics"))
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        return try JSONDecoder.quailCash.decode(InfraMetricsPayload.self, from: data)
    }

    func fetchPendingUsers() async throws -> [PendingUserPayload] {
        let request = makeRequest(url: AppConfig.url(path: "/admin/pending-users"))
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        do {
            struct Wrapper: Decodable { let items: [PendingUserPayload] }
            return try JSONDecoder.quailCash.decode(Wrapper.self, from: data).items
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.pendingUsersDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func approvePendingUser(id: Int) async throws {
        let request = makeRequest(url: AppConfig.url(path: "/admin/pending-users/\(id)/approve"), method: "POST", jsonBody: [:])
        let (_, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
    }

    func fetchUpcomingWindow(daysAhead: Int = 30, accountID: Int? = nil) async throws -> [UpcomingEventPayload] {
        let payload: [String: Any] = [
            "days_ahead": max(1, min(daysAhead, 120)),
            "min_occ": 3,
            "include_stale": false,
            "account_id": accountID as Any,
            "profile": NSNull(),
        ]
        let request = makeRequest(url: AppConfig.url(path: "/page/home/upcoming"), method: "POST", jsonBody: payload)
        print("[QuailCash] QuailCashAPI.fetchUpcomingWindow url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchUpcomingWindow status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        do {
            struct Wrapper: Decodable { let events: [UpcomingEventPayload] }
            let payload = try JSONDecoder.quailCash.decode(Wrapper.self, from: data)
            return payload.events.filter { !$0.date.isEmpty }
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.upcomingDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchCategories() async throws -> [String] {
        let request = makeRequest(url: AppConfig.url(path: "/categories"))
        let data = try await checkedData(for: request)
        do {
            return try JSONDecoder.quailCash.decode([String].self, from: data)
        } catch {
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchNotificationsUnreadCount() async throws -> Int {
        let request = makeRequest(url: AppConfig.url(path: "/notifications/unread-count"))
        let data = try await checkedData(for: request)
        do {
            struct Payload: Decodable { let unread: Int }
            return max(0, try JSONDecoder.quailCash.decode(Payload.self, from: data).unread)
        } catch {
            throw QuailCashAPIError.decodingFailed
        }
    }

    func registerIOSPushDevice(token: String, environment: String, deviceName: String? = nil, bundleID: String? = nil, appVersion: String? = nil) async throws {
        var body: [String: Any] = [
            "token": token,
            "environment": environment,
        ]
        if let deviceName, !deviceName.isEmpty {
            body["device_name"] = deviceName
        }
        if let bundleID, !bundleID.isEmpty {
            body["bundle_id"] = bundleID
        }
        if let appVersion, !appVersion.isEmpty {
            body["app_version"] = appVersion
        }
        let request = makeRequest(
            url: AppConfig.url(path: "/notifications/ios/devices"),
            method: "POST",
            jsonBody: body
        )
        _ = try await checkedData(for: request)
    }

    func unregisterIOSPushDevice(token: String) async throws {
        let request = makeRequest(
            url: AppConfig.url(path: "/notifications/ios/devices"),
            method: "DELETE",
            jsonBody: ["token": token]
        )
        _ = try await checkedData(for: request)
    }

    func sendIOSTestPush(title: String? = nil, body: String? = nil) async throws {
        var payload: [String: Any] = [:]
        if let title, !title.isEmpty {
            payload["title"] = title
        }
        if let body, !body.isEmpty {
            payload["body"] = body
        }
        let request = makeRequest(
            url: AppConfig.url(path: "/notifications/ios/test"),
            method: "POST",
            jsonBody: payload
        )
        _ = try await checkedData(for: request)
    }

    func fetchCategoryTrend(category: String, period: String = "all") async throws -> CategoryTrendPayload {
        let request = makeRequest(url: AppConfig.url(path: "/category-trend", queryItems: [
            URLQueryItem(name: "category", value: category),
            URLQueryItem(name: "period", value: period)
        ]))
        let data = try await checkedData(for: request)
        do {
            return try JSONDecoder.quailCash.decode(CategoryTrendPayload.self, from: data)
        } catch {
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchCategoryLifetimeTotals() async throws -> [CategoryLifetimeTotalPayload] {
        let request = makeRequest(url: AppConfig.url(path: "/category-totals-lifetime"))
        let data = try await checkedData(for: request)
        do {
            return try JSONDecoder.quailCash.decode([CategoryLifetimeTotalPayload].self, from: data)
        } catch {
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchUnassigned(limit: Int = 25, mode: UnassignedMode = .freq) async throws -> [UnassignedTransactionPayload] {
        let request = makeRequest(url: AppConfig.url(path: "/unassigned", queryItems: [
            URLQueryItem(name: "limit", value: String(max(1, min(limit, 500)))),
            URLQueryItem(name: "mode", value: mode.rawValue),
        ]))
        let data = try await checkedData(for: request)
        do {
            return try JSONDecoder.quailCash.decode([UnassignedTransactionPayload].self, from: data)
        } catch {
            throw QuailCashAPIError.decodingFailed
        }
    }

    func createCategoryRule(category: String, keywords: [String], applyNow: Bool = true) async throws -> CategoryRuleApplyJobPayload? {
        let request = makeRequest(
            url: AppConfig.url(path: "/category-rules"),
            method: "POST",
            jsonBody: [
                "category": category,
                "keywords": keywords,
                "apply_now": applyNow,
            ]
        )
        let data = try await checkedData(for: request)
        do {
            struct Response: Decodable {
                let ok: Bool
                let applyJob: CategoryRuleApplyJobPayload?

                enum CodingKeys: String, CodingKey {
                    case ok
                    case applyJob = "apply_job"
                }
            }
            let response = try JSONDecoder.quailCash.decode(Response.self, from: data)
            return response.applyJob
        } catch {
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchCategoryRuleList(
        ruleID: String = "",
        keyword: String = "",
        category: String = "",
        limit: Int = 50,
        offset: Int = 0
    ) async throws -> CategoryRuleListPayload {
        var queryItems: [URLQueryItem] = [
            URLQueryItem(name: "include_inactive", value: "1"),
            URLQueryItem(name: "with_counts", value: "1"),
            URLQueryItem(name: "limit", value: String(max(1, min(limit, 200)))),
            URLQueryItem(name: "offset", value: String(max(0, offset))),
        ]
        if !ruleID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            queryItems.append(URLQueryItem(name: "rule_id", value: ruleID))
        }
        if !keyword.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            queryItems.append(URLQueryItem(name: "keyword", value: keyword))
        }
        if !category.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            queryItems.append(URLQueryItem(name: "category", value: category))
        }
        let request = makeRequest(url: AppConfig.url(path: "/category-rules/list", queryItems: queryItems))
        let data = try await checkedData(for: request)
        do {
            return try JSONDecoder.quailCash.decode(CategoryRuleListPayload.self, from: data)
        } catch {
            throw QuailCashAPIError.decodingFailed
        }
    }

    func runCategoryRulesCheckAll(uncategorizedOnly: Bool) async throws -> CategoryRulesCheckAllPayload {
        let request = makeRequest(url: AppConfig.url(path: "/category-rules/check-all", queryItems: [
            URLQueryItem(name: "include_inactive", value: "1"),
            URLQueryItem(name: "uncategorized_only", value: uncategorizedOnly ? "1" : "0"),
            URLQueryItem(name: "sample_limit", value: "2"),
            URLQueryItem(name: "apply_now", value: "1"),
        ]))
        let data = try await checkedData(for: request)
        do {
            return try JSONDecoder.quailCash.decode(CategoryRulesCheckAllPayload.self, from: data)
        } catch {
            throw QuailCashAPIError.decodingFailed
        }
    }

    func updateCategoryRule(ruleID: Int, category: String) async throws -> CategoryRuleUpdateResponse {
        let request = makeRequest(
            url: AppConfig.url(path: "/category-rules/\(ruleID)"),
            method: "POST",
            jsonBody: [
                "category": category,
                "reapply_existing": true,
            ]
        )
        let data = try await checkedData(for: request)
        do {
            return try JSONDecoder.quailCash.decode(CategoryRuleUpdateResponse.self, from: data)
        } catch {
            throw QuailCashAPIError.decodingFailed
        }
    }

    func setCategoryRuleActive(ruleID: Int, isActive: Bool) async throws {
        let request = makeRequest(
            url: AppConfig.url(path: "/category-rules/\(ruleID)/active"),
            method: "POST",
            jsonBody: ["is_active": isActive]
        )
        _ = try await checkedData(for: request)
    }

    func deleteCategoryRule(ruleID: Int) async throws {
        let request = makeRequest(url: AppConfig.url(path: "/category-rules/\(ruleID)"), method: "DELETE")
        _ = try await checkedData(for: request)
    }

    func testCategoryRule(pattern: String, flags: String = "i", limit: Int = 50) async throws -> CategoryRuleTestPayload {
        let request = makeRequest(
            url: AppConfig.url(path: "/category-rules/test"),
            method: "POST",
            jsonBody: [
                "pattern": pattern,
                "flags": flags,
                "limit": max(1, min(limit, 250)),
            ]
        )
        let data = try await checkedData(for: request)
        do {
            return try JSONDecoder.quailCash.decode(CategoryRuleTestPayload.self, from: data)
        } catch {
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchCategoryRuleJob(jobID: Int) async throws -> CategoryRuleApplyJobPayload {
        let request = makeRequest(url: AppConfig.url(path: "/category-rules/jobs/\(jobID)"))
        let data = try await checkedData(for: request)
        do {
            struct Response: Decodable {
                let ok: Bool
                let job: CategoryRuleApplyJobPayload
            }
            return try JSONDecoder.quailCash.decode(Response.self, from: data).job
        } catch {
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchCsvPreview(
        fileURL: URL,
        headerRow: Int = 1,
        dataStartRow: Int = 2,
        maxRows: Int = 12
    ) async throws -> CsvPreviewPayload {
        let request = try makeMultipartRequest(
            url: AppConfig.url(path: "/csv/preview"),
            fields: [
                "delimiter": "auto",
                "header_row": String(headerRow),
                "data_start_row": String(dataStartRow),
                "max_rows": String(maxRows),
            ],
            fileFieldName: "file",
            fileURL: fileURL,
            timeoutInterval: RequestTimeout.csvPreview
        )
        let data = try await checkedData(for: request)
        do {
            return try JSONDecoder.quailCash.decode(CsvPreviewPayload.self, from: data)
        } catch {
            throw QuailCashAPIError.decodingFailed
        }
    }

    func saveCsvMappingPreset(accountID: Int, preset: [String: Any]) async throws {
        let request = makeRequest(
            url: AppConfig.url(path: "/csv/mapping-presets"),
            method: "POST",
            jsonBody: [
                "account_id": accountID,
                "institution_key": "__account__",
                "preset": preset,
            ]
        )
        _ = try await checkedData(for: request)
    }

    func fetchCsvMappingPreset(accountID: Int) async throws -> CsvMappingPresetPayload? {
        let request = makeRequest(url: AppConfig.url(path: "/csv/mapping-presets", queryItems: [
            URLQueryItem(name: "account_id", value: String(accountID)),
            URLQueryItem(name: "institution_key", value: "__account__"),
        ]))
        let data = try await checkedData(for: request)
        do {
            let payload = try JSONDecoder.quailCash.decode(CsvMappingPresetResponsePayload.self, from: data)
            return (payload.ok && payload.found) ? payload.preset : nil
        } catch {
            throw QuailCashAPIError.decodingFailed
        }
    }

    func runCsvDryRun(fileURL: URL, fields: [String: String]) async throws -> CsvDryRunPayload {
        let request = try makeMultipartRequest(
            url: AppConfig.url(path: "/csv/ingest-mapped/dry-run"),
            fields: fields,
            fileFieldName: "file",
            fileURL: fileURL,
            timeoutInterval: RequestTimeout.csvDryRun
        )
        let data = try await checkedData(for: request)
        do {
            return try JSONDecoder.quailCash.decode(CsvDryRunPayload.self, from: data)
        } catch {
            throw QuailCashAPIError.decodingFailed
        }
    }

    func importCsvMapped(fileURL: URL, fields: [String: String]) async throws -> CsvImportResultPayload {
        let request = try makeMultipartRequest(
            url: AppConfig.url(path: "/csv/ingest-mapped"),
            fields: fields,
            fileFieldName: "file",
            fileURL: fileURL,
            timeoutInterval: RequestTimeout.csvImport
        )
        let data = try await checkedData(for: request)
        do {
            return try JSONDecoder.quailCash.decode(CsvImportResultPayload.self, from: data)
        } catch {
            throw QuailCashAPIError.decodingFailed
        }
    }

    func importCsvMappedAsync(fileURL: URL, fields: [String: String]) async throws -> String {
        let request = try makeMultipartRequest(
            url: AppConfig.url(path: "/csv/ingest-mapped/async"),
            fields: fields,
            fileFieldName: "file",
            fileURL: fileURL,
            timeoutInterval: RequestTimeout.csvImport
        )
        let data = try await checkedData(for: request)
        struct Response: Decodable { let ok: Bool; let jobId: String; enum CodingKeys: String, CodingKey { case ok; case jobId = "job_id" } }
        do {
            return try JSONDecoder.quailCash.decode(Response.self, from: data).jobId
        } catch {
            throw QuailCashAPIError.decodingFailed
        }
    }

    func pollCsvJob(jobID: String) async throws -> CsvJobStatusPayload {
        let request = makeRequest(url: AppConfig.url(path: "/csv/jobs/\(jobID)"))
        let data = try await checkedData(for: request)
        do {
            return try JSONDecoder.quailCash.decode(CsvJobStatusPayload.self, from: data)
        } catch {
            throw QuailCashAPIError.decodingFailed
        }
    }

    func createTransaction(accountID: Int, amount: Double, merchant: String, status: String, date: String) async throws -> Bool {
        let body: [String: Any] = [
            "account_id": accountID,
            "amount": amount,
            "merchant": merchant,
            "status": status,
            "date": date,
            "source": "Manual",
        ]
        let request = makeRequest(url: AppConfig.url(path: "/transaction"), method: "POST", jsonBody: body)
        print("[QuailCash] QuailCashAPI.createTransaction url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.createTransaction status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        return true
    }

    func fetchCategoryTransactions(category: String, start: String, end: String, limit: Int = 100) async throws -> [TransactionItem] {
        let request = makeRequest(url: AppConfig.url(path: "/category-transactions", queryItems: [
            URLQueryItem(name: "category", value: category),
            URLQueryItem(name: "start", value: start),
            URLQueryItem(name: "end", value: end),
            URLQueryItem(name: "limit", value: String(limit))
        ]))
        print("[QuailCash] QuailCashAPI.fetchCategoryTransactions url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchCategoryTransactions status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode([TransactionItem].self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.categoryTransactionsDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchTransactionDetail(txId: String) async throws -> TransactionDetailPayload {
        let request = makeRequest(url: AppConfig.url(path: "/transaction/\(txId)"))
        print("[QuailCash] QuailCashAPI.fetchTransactionDetail url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchTransactionDetail status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        do {
            let payload = try JSONDecoder.quailCash.decode(TransactionDetailResponse.self, from: data)
            return payload.transaction
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.transactionDetailDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func setInterestRate(accountID: Int, ratePercent: Double, effectiveDate: String, note: String) async throws -> Bool {
        let body = [
            "account_id": accountID,
            "rate_percent": ratePercent,
            "effective_date": effectiveDate,
            "note": note,
        ] as [String: Any]
        let request = makeRequest(url: AppConfig.url(path: "/interest-rate"), method: "POST", jsonBody: body)
        print("[QuailCash] QuailCashAPI.setInterestRate url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.setInterestRate status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        return true
    }

    func verifyAccountBalance(accountID: Int, verifiedDate: String) async throws -> Bool {
        let request = makeRequest(
            url: AppConfig.url(path: "/account/\(accountID)/balance-verified"),
            method: "POST",
            jsonBody: ["verified_date": verifiedDate] as [String: Any]
        )
        print("[QuailCash] QuailCashAPI.verifyAccountBalance url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.verifyAccountBalance status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        return true
    }

    func updateTransactionCategory(txId: String, category: String) async throws -> Bool {
        let request = makeRequest(
            url: AppConfig.url(path: "/transaction/\(txId)/category"),
            method: "POST",
            jsonBody: ["category": category] as [String: Any]
        )
        print("[QuailCash] QuailCashAPI.updateTransactionCategory url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.updateTransactionCategory status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        return true
    }

    func updateTransactionMeta(txId: String, status: String, postedDate: String) async throws -> Bool {
        let request = makeRequest(
            url: AppConfig.url(path: "/transaction/\(txId)/meta"),
            method: "PATCH",
            jsonBody: ["status": status, "postedDate": postedDate] as [String: Any]
        )
        print("[QuailCash] QuailCashAPI.updateTransactionMeta url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.updateTransactionMeta status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        return true
    }

    func invertTransactionAmount(txId: String) async throws -> Double {
        let request = makeRequest(url: AppConfig.url(path: "/transaction/\(txId)/invert-amount"), method: "POST")
        print("[QuailCash] QuailCashAPI.invertTransactionAmount url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.invertTransactionAmount status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        return 0
    }

    func ignoreTransaction(txId: String, ignored: Bool) async throws -> Bool {
        let request = makeRequest(
            url: AppConfig.url(path: "/transaction/\(txId)/ignore"),
            method: "POST",
            jsonBody: ["ignored": ignored] as [String: Any]
        )
        print("[QuailCash] QuailCashAPI.ignoreTransaction url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.ignoreTransaction status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        return true
    }

    func deleteTransaction(txId: String) async throws -> Bool {
        let request = makeRequest(url: AppConfig.url(path: "/transaction/\(txId)"), method: "DELETE")
        print("[QuailCash] QuailCashAPI.deleteTransaction url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.deleteTransaction status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        return true
    }

    func fetchMonthBudget() async throws -> MonthBudgetPayload {
        return try await fetchMonthBudget(year: nil, month: nil)
    }

    func fetchMonthBudget(year: Int?, month: Int?) async throws -> MonthBudgetPayload {
        var items: [URLQueryItem] = []
        if let year { items.append(URLQueryItem(name: "year", value: String(year))) }
        if let month { items.append(URLQueryItem(name: "month", value: String(month))) }
        let request = makeRequest(url: AppConfig.url(path: "/month-budget", queryItems: items))
        print("[QuailCash] QuailCashAPI.fetchMonthBudget url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchMonthBudget status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode(MonthBudgetPayload.self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.monthBudgetDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchLESProfile() async throws -> LESProfilePayload {
        let data = try await fetchData(path: "/les-profile", queryItems: [URLQueryItem(name: "key", value: "default")])
        do {
            return try JSONDecoder.quailCash.decode(LESProfilePayload.self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.lesProfileDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func saveLESProfile(_ profile: LESProfile) async throws -> LESProfilePayload {
        let data = try await fetchData(path: "/les-profile", method: "POST", jsonBody: [
            "key": "default",
            "profile": profile.asDictionary
        ])
        do {
            return try JSONDecoder.quailCash.decode(LESProfilePayload.self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.saveLESProfileDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchLESPaychecks(year: Int, month: Int, profile: LESProfile) async throws -> LESPaychecksPayload {
        let data = try await fetchData(path: "/les/paychecks", method: "POST", jsonBody: [
            "year": year,
            "month": month,
            "profile": profile.asDictionary
        ])
        do {
            return try JSONDecoder.quailCash.decode(LESPaychecksPayload.self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.lesPaychecksDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchPageBudget(year: Int, month: Int, recalc: Bool = false) async throws -> PageBudgetPayload {
        var items = [
            URLQueryItem(name: "year", value: String(year)),
            URLQueryItem(name: "month", value: String(month)),
        ]
        if recalc {
            items.append(URLQueryItem(name: "recalc", value: "1"))
        }
        let request = makeRequest(url: AppConfig.url(path: "/page/budget", queryItems: items))
        print("[QuailCash] QuailCashAPI.fetchPageBudget url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchPageBudget status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode(PageBudgetPayload.self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.pageBudgetDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchRoundUpSettings() async throws -> RoundUpSettingsPayload {
        let request = makeRequest(url: AppConfig.url(path: "/settings/round-ups"))
        print("[QuailCash] QuailCashAPI.fetchRoundUpSettings url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        print("[QuailCash] QuailCashAPI.fetchRoundUpSettings status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode(RoundUpSettingsPayload.self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.roundupsDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func saveRoundUpSettings(enabled: Bool) async throws -> Bool {
        let request = makeRequest(url: AppConfig.url(path: "/settings/round-ups"), method: "POST", jsonBody: [
            "enabled": enabled
        ])
        print("[QuailCash] QuailCashAPI.saveRoundUpSettings url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        print("[QuailCash] QuailCashAPI.saveRoundUpSettings status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        return true
    }

    func saveSavingsGoal(mode: String, value: Double) async throws -> Bool {
        let request = makeRequest(url: AppConfig.url(path: "/settings/savings-goal"), method: "POST", jsonBody: [
            "mode": mode,
            "value": value
        ])
        print("[QuailCash] QuailCashAPI.saveSavingsGoal url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        print("[QuailCash] QuailCashAPI.saveSavingsGoal status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        return true
    }

    func upsertBudgetGroup(year: Int, month: Int, name: String, allocated: Double, cap: Double?, categories: [String]) async throws -> Bool {
        var body: [String: Any] = [
            "year": year,
            "month": month,
            "name": name,
            "allocated": allocated,
            "categories": categories
        ]
        body["cap"] = cap as Any
        let request = makeRequest(url: AppConfig.url(path: "/budget/groups"), method: "POST", jsonBody: body)
        print("[QuailCash] QuailCashAPI.upsertBudgetGroup url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        print("[QuailCash] QuailCashAPI.upsertBudgetGroup status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        return true
    }

    func deleteBudgetGroup(year: Int, month: Int, name: String) async throws -> Bool {
        let request = makeRequest(url: AppConfig.url(path: "/budget/groups", queryItems: [
            URLQueryItem(name: "year", value: String(year)),
            URLQueryItem(name: "month", value: String(month)),
            URLQueryItem(name: "name", value: name),
        ]), method: "DELETE")
        print("[QuailCash] QuailCashAPI.deleteBudgetGroup url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        print("[QuailCash] QuailCashAPI.deleteBudgetGroup status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        return true
    }

    func createFund(name: String, targetAmount: Double, targetDate: String?, cadence: String, contribAmount: Double) async throws -> Bool {
        let request = makeRequest(url: AppConfig.url(path: "/funds"), method: "POST", jsonBody: [
            "name": name,
            "target_amount": targetAmount,
            "target_date": targetDate as Any,
            "cadence": cadence,
            "contrib_amount": contribAmount
        ])
        print("[QuailCash] QuailCashAPI.createFund url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        print("[QuailCash] QuailCashAPI.createFund status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        return true
    }

    func updateFund(id: Int, name: String, targetAmount: Double, targetDate: String?, cadence: String, contribAmount: Double, isActive: Bool = true) async throws -> Bool {
        let request = makeRequest(url: AppConfig.url(path: "/funds/\(id)"), method: "PATCH", jsonBody: [
            "name": name,
            "target_amount": targetAmount,
            "target_date": targetDate as Any,
            "cadence": cadence,
            "contrib_amount": contribAmount,
            "is_active": isActive
        ])
        print("[QuailCash] QuailCashAPI.updateFund url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        print("[QuailCash] QuailCashAPI.updateFund status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        return true
    }

    func adjustFund(id: Int, amount: Double, note: String) async throws -> Bool {
        let request = makeRequest(url: AppConfig.url(path: "/funds/\(id)/adjust"), method: "POST", jsonBody: [
            "amount": amount,
            "note": note
        ])
        print("[QuailCash] QuailCashAPI.adjustFund url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        print("[QuailCash] QuailCashAPI.adjustFund status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        return true
    }

    func deleteFund(id: Int) async throws -> Bool {
        let request = makeRequest(url: AppConfig.url(path: "/funds/\(id)"), method: "DELETE")
        print("[QuailCash] QuailCashAPI.deleteFund url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        print("[QuailCash] QuailCashAPI.deleteFund status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        return true
    }

    func fetchDayLimit(recalc: Bool = false) async throws -> DayLimitPayload {
        let request = makeRequest(url: AppConfig.url(path: "/day-limit", queryItems: recalc ? [
            URLQueryItem(name: "recalc", value: "1"),
        ] : []))
        print("[QuailCash] QuailCashAPI.fetchDayLimit url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchDayLimit status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode(DayLimitPayload.self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.dayLimitDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchSpentSoFarBreakdown(start: String, end: String) async throws -> SpentSoFarBreakdownPayload {
        let request = makeRequest(url: AppConfig.url(path: "/spent-so-far-breakdown", queryItems: [
            URLQueryItem(name: "start", value: start),
            URLQueryItem(name: "end", value: end),
        ]))
        print("[QuailCash] QuailCashAPI.fetchSpentSoFarBreakdown url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchSpentSoFarBreakdown status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode(SpentSoFarBreakdownPayload.self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.spentBreakdownDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchSpentSoFarTransactions(category: String, start: String, end: String, limit: Int = 500) async throws -> [TransactionItem] {
        let request = makeRequest(url: AppConfig.url(path: "/spent-so-far-transactions", queryItems: [
            URLQueryItem(name: "category", value: category),
            URLQueryItem(name: "start", value: start),
            URLQueryItem(name: "end", value: end),
            URLQueryItem(name: "limit", value: String(limit)),
        ]))
        print("[QuailCash] QuailCashAPI.fetchSpentSoFarTransactions url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchSpentSoFarTransactions status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        do {
            let response = try JSONDecoder.quailCash.decode(SpentSoFarTransactionsResponse.self, from: data)
            return response.transactions
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.spentTxDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchChartSeries(mode: ChartMode, start: String, end: String) async throws -> [ChartSeriesPoint] {
        let request = makeRequest(url: AppConfig.url(path: mode.endpoint, queryItems: [
            URLQueryItem(name: "start", value: start),
            URLQueryItem(name: "end", value: end),
        ]))
        print("[QuailCash] QuailCashAPI.fetchChartSeries url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchChartSeries status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }

        do {
            return try JSONDecoder.quailCash.decode([ChartSeriesPoint].self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.chartDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            if let decodingError = error as? DecodingError {
                print("[QuailCash] QuailCashAPI.chartDecodingError=\(Self.describe(decodingError))")
            } else {
                print("[QuailCash] QuailCashAPI.chartDecodeFailure error=\(error.localizedDescription)")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchSpendingSeries(start: String, end: String) async throws -> [ChartSeriesPoint] {
        let request = makeRequest(url: AppConfig.url(path: "/spending", queryItems: [
            URLQueryItem(name: "start", value: start),
            URLQueryItem(name: "end", value: end),
        ]))
        print("[QuailCash] QuailCashAPI.fetchSpendingSeries url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        print("[QuailCash] QuailCashAPI.fetchSpendingSeries status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode([ChartSeriesPoint].self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.spendingSeriesDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchSpendingCategoryTotals(start: String, end: String) async throws -> [SpendingCategoryTotalPayload] {
        let request = makeRequest(url: AppConfig.url(path: "/category-totals-range", queryItems: [
            URLQueryItem(name: "start", value: start),
            URLQueryItem(name: "end", value: end),
        ]))
        print("[QuailCash] QuailCashAPI.fetchSpendingCategoryTotals url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        print("[QuailCash] QuailCashAPI.fetchSpendingCategoryTotals status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode([SpendingCategoryTotalPayload].self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.spendingCategoryTotalsDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchUnknownMerchantRange(start: String, end: String) async throws -> UnknownMerchantRangePayload {
        let request = makeRequest(url: AppConfig.url(path: "/unknown-merchant-total-range", queryItems: [
            URLQueryItem(name: "start", value: start),
            URLQueryItem(name: "end", value: end),
        ]))
        print("[QuailCash] QuailCashAPI.fetchUnknownMerchantRange url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        print("[QuailCash] QuailCashAPI.fetchUnknownMerchantRange status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode(UnknownMerchantRangePayload.self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.unknownMerchantRangeDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchSpendingUnbudgetedSafeRange(start: String, end: String) async throws -> SpendingUnbudgetedSafeRangePayload {
        let request = makeRequest(url: AppConfig.url(path: "/spending-unbudgeted-safe-range", queryItems: [
            URLQueryItem(name: "start", value: start),
            URLQueryItem(name: "end", value: end),
        ]))
        print("[QuailCash] QuailCashAPI.fetchSpendingUnbudgetedSafeRange url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        print("[QuailCash] QuailCashAPI.fetchSpendingUnbudgetedSafeRange status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode(SpendingUnbudgetedSafeRangePayload.self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.spendingUnbudgetedSafeRangeDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchSpendingUnbudgetedDay(day: String) async throws -> SpendingUnbudgetedDayPayload {
        let request = makeRequest(url: AppConfig.url(path: "/spending-unbudgeted-day", queryItems: [
            URLQueryItem(name: "day", value: day),
        ]))
        print("[QuailCash] QuailCashAPI.fetchSpendingUnbudgetedDay url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else { throw QuailCashAPIError.badResponse }
        print("[QuailCash] QuailCashAPI.fetchSpendingUnbudgetedDay status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 { throw QuailCashAPIError.unauthorized }
            throw QuailCashAPIError.badResponse
        }
        do {
            return try JSONDecoder.quailCash.decode(SpendingUnbudgetedDayPayload.self, from: data)
        } catch {
            if let text = String(data: data, encoding: .utf8) {
                print("[QuailCash] QuailCashAPI.spendingUnbudgetedDayDecodeFailure bodyPrefix=\(String(text.prefix(800)))")
            }
            throw QuailCashAPIError.decodingFailed
        }
    }

    func fetchData(path: String, queryItems: [URLQueryItem] = [], method: String = "GET", jsonBody: [String: Any]? = nil) async throws -> Data {
        let request = makeRequest(url: AppConfig.url(path: path, queryItems: queryItems), method: method, jsonBody: jsonBody)
        print("[QuailCash] QuailCashAPI.fetchData url=\(request.url?.absoluteString ?? "nil")")
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        print("[QuailCash] QuailCashAPI.fetchData status=\(http.statusCode) bytes=\(data.count)")
        guard http.statusCode == 200 else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            throw QuailCashAPIError.badResponse
        }
        return data
    }

    func sendJSON(path: String, method: String = "POST", queryItems: [URLQueryItem] = [], jsonBody: [String: Any]? = nil) async throws {
        _ = try await fetchData(path: path, queryItems: queryItems, method: method, jsonBody: jsonBody)
    }

    func syncCookies(from webView: WKWebView) async {
        await withCheckedContinuation { continuation in
            webView.configuration.websiteDataStore.httpCookieStore.getAllCookies { cookies in
                for cookie in cookies {
                    HTTPCookieStorage.shared.setCookie(cookie)
                }
                continuation.resume()
            }
        }
    }

    func installCookies(_ cookies: [HTTPCookie]) {
        for cookie in cookies {
            HTTPCookieStorage.shared.setCookie(cookie)
        }
    }

    // MARK: - Vehicle

    struct VehicleProfilePayload: Codable {
        var make: String?
        var model: String?
        var year: Int?
        var vin: String?
        var licensePlate: String?
        var currentMileage: Int?
        var oilType: String?
        var notes: String?
    }

    struct VehicleFuelPayload: Codable {
        var id: Int
        var date: String
        var mileage: Int
        var gallons: Double?
        var pricePerGallon: Double?
        var totalCost: Double?
        var milesSinceLast: Double?
        var mpg: Double?
        var station: String?
        var notes: String?
        var linkedTransactionId: String?
        var linkedMerchant: String?
    }

    struct VehicleMaintenancePayload: Codable {
        var id: Int
        var typeName: String
        var date: String
        var mileage: Int
        var cost: Double?
        var isShopPerformed: Bool?
        var shopName: String?
        var notes: String?
        var linkedTransactionId: String?
        var linkedMerchant: String?
    }

    struct VehicleTxCandidate: Codable, Identifiable {
        var id: String
        var date: String?
        var amount: Double?
        var merchant: String?
        var category: String?
    }

    struct VehicleInspectionPayload: Codable {
        var id: Int
        var name: String
        var periodicityDays: Int
        var lastCheckedDate: String?
        var isBuiltIn: Bool?
    }

    struct VehicleIssueAPIPayload: Codable {
        var id: Int
        var title: String
        var description: String?
        var mileageNoticed: Int?
        var dateNoticed: String?
        var isResolved: Bool?
        var resolvedDate: String?
        var notes: String?
    }

    private struct VehicleListWrapper<T: Codable>: Codable {
        var records: [T]
    }

    private func vehicleDecoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    func fetchVehicleProfile() async throws -> VehicleProfilePayload? {
        let data = try await checkedData(for: makeRequest(url: AppConfig.url(path: "/vehicle/profile")))
        if data.count <= 2 { return nil }
        return try? vehicleDecoder().decode(VehicleProfilePayload.self, from: data)
    }

    func fetchVehicleFuel(limit: Int = 500) async throws -> [VehicleFuelPayload] {
        let data = try await checkedData(for: makeRequest(url: AppConfig.url(path: "/vehicle/fuel", queryItems: [URLQueryItem(name: "limit", value: "\(limit)")])))
        return (try? vehicleDecoder().decode(VehicleListWrapper<VehicleFuelPayload>.self, from: data).records) ?? []
    }

    func fetchVehicleMaintenance(limit: Int = 500) async throws -> [VehicleMaintenancePayload] {
        let data = try await checkedData(for: makeRequest(url: AppConfig.url(path: "/vehicle/maintenance", queryItems: [URLQueryItem(name: "limit", value: "\(limit)")])))
        return (try? vehicleDecoder().decode(VehicleListWrapper<VehicleMaintenancePayload>.self, from: data).records) ?? []
    }

    func fetchVehicleInspections() async throws -> [VehicleInspectionPayload] {
        let data = try await checkedData(for: makeRequest(url: AppConfig.url(path: "/vehicle/inspections")))
        return (try? vehicleDecoder().decode([VehicleInspectionPayload].self, from: data)) ?? []
    }

    func fetchVehicleTxCandidates(kind: String, recordId: Int) async throws -> [VehicleTxCandidate] {
        let url = AppConfig.url(path: "/vehicle/match-transactions", queryItems: [
            URLQueryItem(name: "kind", value: kind),
            URLQueryItem(name: "record_id", value: "\(recordId)"),
        ])
        let data = try await checkedData(for: makeRequest(url: url))
        struct Wrapper: Codable { var candidates: [VehicleTxCandidate] }
        do {
            return try vehicleDecoder().decode(Wrapper.self, from: data).candidates
        } catch {
            let raw = String(data: data, encoding: .utf8) ?? "<non-utf8>"
            print("[QuailCash] fetchVehicleTxCandidates decode error: \(error)\nraw: \(raw)")
            throw error
        }
    }

    func linkVehicleTransaction(kind: String, recordId: Int, transactionId: String, merchant: String?) async throws {
        let body: [String: Any] = ["kind": kind, "record_id": recordId, "transaction_id": transactionId, "merchant": merchant ?? ""]
        var req = makeRequest(url: AppConfig.url(path: "/vehicle/link-transaction"), method: "POST", jsonBody: body)
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        _ = try await checkedData(for: req)
    }

    func unlinkVehicleTransaction(kind: String, recordId: Int) async throws {
        let req = makeRequest(
            url: AppConfig.url(path: "/vehicle/link-transaction"),
            queryItems: [URLQueryItem(name: "kind", value: kind), URLQueryItem(name: "record_id", value: "\(recordId)")],
            method: "DELETE"
        )
        _ = try await checkedData(for: req)
    }

    func bulkImportVehicleFuel(_ records: [[String: Any]]) async throws -> Int {
        var req = makeRequest(url: AppConfig.url(path: "/vehicle/fuel/bulk"), method: "POST", jsonBody: ["records": records])
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let data = try await checkedData(for: req)
        let obj = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
        return (obj["inserted"] as? Int) ?? 0
    }

    func bulkImportVehicleMaintenance(_ records: [[String: Any]]) async throws -> Int {
        var req = makeRequest(url: AppConfig.url(path: "/vehicle/maintenance/bulk"), method: "POST", jsonBody: ["records": records])
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let data = try await checkedData(for: req)
        let obj = (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
        return (obj["inserted"] as? Int) ?? 0
    }

    func fetchVehicleIssues() async throws -> [VehicleIssueAPIPayload] {
        let data = try await checkedData(for: makeRequest(url: AppConfig.url(path: "/vehicle/issues")))
        return (try? vehicleDecoder().decode([VehicleIssueAPIPayload].self, from: data)) ?? []
    }

    private func makeRequest(url: URL, method: String = "GET", jsonBody: [String: Any]? = nil) -> URLRequest {
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("QuailCash/1.0", forHTTPHeaderField: "User-Agent")
        if let token = AuthStore.token, !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let jsonBody {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try? JSONSerialization.data(withJSONObject: jsonBody, options: [])
        }
        return request
    }

    private func makeRequest(url: URL, queryItems: [URLQueryItem], method: String = "GET", jsonBody: [String: Any]? = nil) -> URLRequest {
        var components = URLComponents(url: url, resolvingAgainstBaseURL: false) ?? URLComponents()
        components.queryItems = queryItems.isEmpty ? nil : queryItems
        return makeRequest(url: components.url ?? url, method: method, jsonBody: jsonBody)
    }

    private func makeMultipartRequest(
        url: URL,
        method: String = "POST",
        fields: [String: String],
        fileFieldName: String,
        fileURL: URL,
        mimeType: String = "application/octet-stream",
        timeoutInterval: TimeInterval? = nil
    ) throws -> URLRequest {
        let boundary = "Boundary-\(UUID().uuidString)"
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = timeoutInterval ?? RequestTimeout.standardResource
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("QuailCash/1.0", forHTTPHeaderField: "User-Agent")
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        if let token = AuthStore.token, !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        var body = Data()
        for key in fields.keys.sorted() {
            body.appendMultipart("--\(boundary)\r\n")
            body.appendMultipart("Content-Disposition: form-data; name=\"\(key)\"\r\n\r\n")
            body.appendMultipart("\(fields[key] ?? "")\r\n")
        }

        let fileData = try Data(contentsOf: fileURL)
        body.appendMultipart("--\(boundary)\r\n")
        body.appendMultipart("Content-Disposition: form-data; name=\"\(fileFieldName)\"; filename=\"\(fileURL.lastPathComponent)\"\r\n")
        body.appendMultipart("Content-Type: \(mimeType)\r\n\r\n")
        body.append(fileData)
        body.appendMultipart("\r\n")
        body.appendMultipart("--\(boundary)--\r\n")

        request.httpBody = body
        return request
    }

    private func perform(_ request: URLRequest) async throws -> (Data, URLResponse) {
        do {
            return try await session.data(for: request)
        } catch is CancellationError {
            throw CancellationError()
        } catch let urlError as URLError where urlError.code == .cancelled {
            // URLSession can cancel on first attempt during app launch on real device; retry once
            try await Task.sleep(nanoseconds: 500_000_000)
            try Task.checkCancellation()
            do {
                return try await session.data(for: request)
            } catch {
                print("[QuailCash] QuailCashAPI.transportError=\(error.localizedDescription)")
                throw QuailCashAPIError.transport(error)
            }
        } catch {
            print("[QuailCash] QuailCashAPI.transportError=\(error.localizedDescription)")
            throw QuailCashAPIError.transport(error)
        }
    }

    private func checkedData(for request: URLRequest) async throws -> Data {
        let (data, response) = try await perform(request)
        guard let http = response as? HTTPURLResponse else {
            throw QuailCashAPIError.badResponse
        }
        guard (200...299).contains(http.statusCode) else {
            if http.statusCode == 401 || http.statusCode == 403 {
                throw QuailCashAPIError.unauthorized
            }
            let message = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
            let userMessage = (message?.isEmpty == false) ? message! : "The server returned status \(http.statusCode)."
            throw QuailCashAPIError.transport(NSError(domain: "QuailCashAPI", code: http.statusCode, userInfo: [
                NSLocalizedDescriptionKey: userMessage
            ]))
        }
        return data
    }

    private static func describe(_ error: DecodingError) -> String {
        func path(_ codingPath: [CodingKey]) -> String {
            codingPath.map { $0.stringValue }.joined(separator: ".")
        }
        switch error {
        case .typeMismatch(let type, let context):
            return "typeMismatch type=\(type) path=\(path(context.codingPath)) desc=\(context.debugDescription)"
        case .valueNotFound(let type, let context):
            return "valueNotFound type=\(type) path=\(path(context.codingPath)) desc=\(context.debugDescription)"
        case .keyNotFound(let key, let context):
            return "keyNotFound key=\(key.stringValue) path=\(path(context.codingPath)) desc=\(context.debugDescription)"
        case .dataCorrupted(let context):
            return "dataCorrupted path=\(path(context.codingPath)) desc=\(context.debugDescription)"
        @unknown default:
            return "unknown decoding error"
        }
    }
}

private extension LESProfile {
    var asDictionary: [String: Any] {
        [
            "paygrade": paygrade,
            "service_start": serviceStart,
            "has_dependents": hasDependents,
            "bas": bas,
            "bah_override": bahOverride as Any,
            "submarine_pay": submarinePay,
            "career_sea_pay": careerSeaPay,
            "spec_duty_pay": specDutyPay,
            "filing_status": filingStatus,
            "step2_multiple_jobs": step2MultipleJobs,
            "dep_under17": depUnder17,
            "other_dep": otherDep,
            "other_income_annual": otherIncomeAnnual,
            "other_deductions_annual": otherDeductionsAnnual,
            "extra_withholding": extraWithholding,
            "tsp_rate": tspRate,
            "fica_include_special_pays": ficaIncludeSpecialPays,
            "meal_rate": mealRate,
            "meal_end_day": mealEndDay,
            "meal_deduction_enabled": mealDeductionEnabled,
            "meal_deduction_start": mealDeductionStart as Any,
            "mid_month_fraction": midMonthFraction,
            "allotments_total": allotmentsTotal,
            "mid_month_collections_total": midMonthCollectionsTotal,
        ]
    }
}

private extension Data {
    mutating func appendMultipart(_ string: String) {
        if let data = string.data(using: .utf8) {
            append(data)
        }
    }
}

extension JSONDecoder {
    static var quailCash: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .useDefaultKeys
        return decoder
    }
}
