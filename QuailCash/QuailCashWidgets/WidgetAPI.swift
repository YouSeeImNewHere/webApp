import Foundation

enum WidgetAPI {
    static let baseURL = URL(string: "https://webapp-pe3q.onrender.com")!
    static let endpointPath = "/widget/summary"
    static let widgetScriptVersion = 3
    static let liveDataMaxAgeMinutes = 20.0

    static func fetchSummary(widgetToken: String) async throws -> WidgetSummaryPayload {
        var components = URLComponents(url: baseURL.appendingPathComponent(endpointPath), resolvingAgainstBaseURL: false)!
        components.queryItems = [
            URLQueryItem(name: "widget_script_version", value: String(widgetScriptVersion))
        ]
        var request = URLRequest(url: components.url!)
        request.timeoutInterval = 12
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue(widgetToken, forHTTPHeaderField: "x-widget-token")
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        let payload = try JSONDecoder.widget.decode(WidgetSummaryPayload.self, from: data)
        guard payload.ok == true else {
            throw URLError(.cannotParseResponse)
        }
        return payload
    }
}

struct WidgetSummaryPayload: Decodable {
    let ok: Bool?
    let changed: Bool?
    let updateRequired: Bool?
    let generatedAt: String?
    let safeToSpend: Double
    let notificationsUnread: Int
    let credit: WidgetCreditPayload
    let totals: WidgetTotalsPayload
    let today: WidgetTodayPayload
    let month: WidgetMonthPayload

    enum CodingKeys: String, CodingKey {
        case ok
        case changed
        case updateRequired = "update_required"
        case generatedAt = "generated_at"
        case safeToSpend = "safe_to_spend"
        case notificationsUnread = "notifications_unread"
        case credit
        case totals
        case today
        case month
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        ok = try c.decodeIfPresent(Bool.self, forKey: .ok)
        changed = try c.decodeIfPresent(Bool.self, forKey: .changed)
        updateRequired = try c.decodeIfPresent(Bool.self, forKey: .updateRequired)
        generatedAt = try c.decodeIfPresent(String.self, forKey: .generatedAt)
        safeToSpend = c.decodeFlexibleDouble(forKey: .safeToSpend) ?? 0
        notificationsUnread = c.decodeFlexibleInt(forKey: .notificationsUnread) ?? 0
        credit = (try? c.decode(WidgetCreditPayload.self, forKey: .credit)) ?? .empty
        totals = (try? c.decode(WidgetTotalsPayload.self, forKey: .totals)) ?? .empty
        today = (try? c.decode(WidgetTodayPayload.self, forKey: .today)) ?? .empty
        month = (try? c.decode(WidgetMonthPayload.self, forKey: .month)) ?? .empty
    }

    static let preview = WidgetSummaryPayload(
        ok: true,
        changed: true,
        updateRequired: false,
        generatedAt: ISO8601DateFormatter().string(from: .now),
        safeToSpend: 842.17,
        notificationsUnread: 3,
        credit: WidgetCreditPayload(used: 412.30, available: 1087.70, cap: 1500),
        totals: WidgetTotalsPayload(checking: 2240.15, savings: 6312.44),
        today: WidgetTodayPayload(remainingToday: 27.43, baseline: 41.00),
        month: WidgetMonthPayload(freeSpendGoal: 1180.00)
    )

    init(
        ok: Bool?,
        changed: Bool?,
        updateRequired: Bool?,
        generatedAt: String?,
        safeToSpend: Double,
        notificationsUnread: Int,
        credit: WidgetCreditPayload,
        totals: WidgetTotalsPayload,
        today: WidgetTodayPayload,
        month: WidgetMonthPayload
    ) {
        self.ok = ok
        self.changed = changed
        self.updateRequired = updateRequired
        self.generatedAt = generatedAt
        self.safeToSpend = safeToSpend
        self.notificationsUnread = notificationsUnread
        self.credit = credit
        self.totals = totals
        self.today = today
        self.month = month
    }

    var entryState: WidgetEntryState {
        let age = dataAgeMinutes
        if age.isFinite && age <= WidgetAPI.liveDataMaxAgeMinutes {
            return .live
        }
        return .stale
    }

    var dataAgeMinutes: Double {
        guard let generatedAt else { return .infinity }
        return max(0, (Date().timeIntervalSince(parseDate(generatedAt) ?? .distantPast)) / 60.0)
    }

    func footerText(for state: WidgetEntryState) -> String {
        switch state {
        case .live:
            return "Live"
        case .tokenMissing:
            return "Paste widget token"
        case .failed:
            return "Refresh failed"
        case .stale:
            let minutes = Int(dataAgeMinutes.rounded())
            if minutes < 60 { return "Cache \(minutes)m old" }
            let hours = Int((Double(minutes) / 60.0).rounded())
            if hours < 48 { return "Cache \(hours)h old" }
            return "Cache \((Double(hours) / 24.0).rounded())d old"
        }
    }

    private func parseDate(_ iso: String) -> Date? {
        ISO8601DateFormatter().date(from: iso)
    }
}

struct WidgetCreditPayload: Decodable {
    let used: Double
    let available: Double
    let cap: Double

    static let empty = WidgetCreditPayload(used: 0, available: 0, cap: 0)

    var pct: Double {
        cap > 0 ? used / cap : 0
    }
}

struct WidgetTotalsPayload: Decodable {
    let checking: Double
    let savings: Double

    static let empty = WidgetTotalsPayload(checking: 0, savings: 0)
}

struct WidgetTodayPayload: Decodable {
    let remainingToday: Double
    let baseline: Double

    enum CodingKeys: String, CodingKey {
        case remainingToday = "remaining_today"
        case baseline
    }

    static let empty = WidgetTodayPayload(remainingToday: 0, baseline: 0)
}

struct WidgetMonthPayload: Decodable {
    let freeSpendGoal: Double

    enum CodingKeys: String, CodingKey {
        case freeSpendGoal = "free_spend_goal"
    }

    static let empty = WidgetMonthPayload(freeSpendGoal: 0)
}

private extension JSONDecoder {
    static let widget: JSONDecoder = {
        let decoder = JSONDecoder()
        return decoder
    }()
}

private extension KeyedDecodingContainer {
    func decodeFlexibleDouble(forKey key: Key) -> Double? {
        if let value = try? decodeIfPresent(Double.self, forKey: key) { return value }
        if let value = try? decodeIfPresent(Int.self, forKey: key) { return Double(value) }
        if let value = try? decodeIfPresent(String.self, forKey: key) { return Double(value) }
        return nil
    }

    func decodeFlexibleInt(forKey key: Key) -> Int? {
        if let value = try? decodeIfPresent(Int.self, forKey: key) { return value }
        if let value = try? decodeIfPresent(Double.self, forKey: key) { return Int(value) }
        if let value = try? decodeIfPresent(String.self, forKey: key) { return Int(value) }
        return nil
    }
}

extension Double {
    var money0: String {
        money(minFraction: 0, maxFraction: 0)
    }

    var money2: String {
        money(minFraction: 2, maxFraction: 2)
    }

    var clamped01: Double {
        max(0, min(1, self))
    }

    private func money(minFraction: Int, maxFraction: Int) -> String {
        let sign = self < 0 ? "-" : ""
        let absValue = abs(self)
        let formatter = NumberFormatter()
        formatter.numberStyle = .currency
        formatter.currencyCode = "USD"
        formatter.minimumFractionDigits = minFraction
        formatter.maximumFractionDigits = maxFraction
        return sign + (formatter.string(from: NSNumber(value: absValue)) ?? "$0")
    }
}
