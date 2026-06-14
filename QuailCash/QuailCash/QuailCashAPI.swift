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
            return "Could not read the home payload."
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
        configuration.timeoutIntervalForRequest = 30
        configuration.timeoutIntervalForResource = 60
        session = URLSession(configuration: configuration)
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
        let request = makeRequest(url: AppConfig.url(path: "/month-budget"))
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

    func fetchDayLimit(recalc: Bool = false) async throws -> DayLimitPayload {
        let suffix = recalc ? "?recalc=1" : ""
        let request = makeRequest(url: AppConfig.url(path: "/day-limit\(suffix)"))
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

    private func perform(_ request: URLRequest) async throws -> (Data, URLResponse) {
        do {
            return try await session.data(for: request)
        } catch {
            print("[QuailCash] QuailCashAPI.transportError=\(error.localizedDescription)")
            throw QuailCashAPIError.transport(error)
        }
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

extension JSONDecoder {
    static var quailCash: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .useDefaultKeys
        return decoder
    }
}
