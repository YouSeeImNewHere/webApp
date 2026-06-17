import Foundation

struct HomePayload: Decodable {
    let transactions: [TransactionItem]
    let categoryTotalsMonth: CategoryTotalsMonthPayload?
    let unknownMerchantTotalMonth: UnknownMerchantTotalMonth?
    let notificationsUnread: Int
    let bankTotals: BankTotalsPayload
    let monthBudget: MonthBudgetPayload?
    let dayLimit: DayLimitPayload?

    enum CodingKeys: String, CodingKey {
        case transactions
        case categoryTotalsMonth = "category_totals_month"
        case unknownMerchantTotalMonth = "unknown_merchant_total_month"
        case notificationsUnread = "notifications_unread"
        case bankTotals = "bank_totals"
        case monthBudget = "month_budget"
        case dayLimit = "day_limit"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        transactions = try container.decode([TransactionItem].self, forKey: .transactions)
        categoryTotalsMonth = try container.decodeIfPresent(CategoryTotalsMonthPayload.self, forKey: .categoryTotalsMonth)
        unknownMerchantTotalMonth = try container.decodeIfPresent(UnknownMerchantTotalMonth.self, forKey: .unknownMerchantTotalMonth)
        notificationsUnread = HomePayload.decodeUnreadCount(from: container, forKey: .notificationsUnread)
        bankTotals = try container.decode(BankTotalsPayload.self, forKey: .bankTotals)
        monthBudget = try container.decodeIfPresent(MonthBudgetPayload.self, forKey: .monthBudget)
        dayLimit = try container.decodeIfPresent(DayLimitPayload.self, forKey: .dayLimit)
    }

    private static func decodeUnreadCount(from container: KeyedDecodingContainer<CodingKeys>, forKey key: CodingKeys) -> Int {
        if let value = try? container.decode(Int.self, forKey: key) {
            return value
        }
        if let wrapper = try? container.decode(UnreadCountWrapper.self, forKey: key) {
            return wrapper.unread
        }
        return 0
    }
}

private struct UnreadCountWrapper: Decodable {
    let unread: Int
}

struct CategoryTotalsMonthPayload: Decodable {
    let categories: [CategoryTotalItem]
    let unassignedAllTime: Int?

    enum CodingKeys: String, CodingKey {
        case categories
        case unassignedAllTime = "unassigned_all_time"
    }
}

struct CategoryTotalItem: Decodable, Hashable {
    let category: String?
    let total: Double?
    let count: Int?
    let amount: Double?
    let name: String?
}

struct UnknownMerchantTotalMonth: Decodable {
    let total: Double
    let txCount: Int

    enum CodingKeys: String, CodingKey {
        case total
        case txCount = "tx_count"
    }
}

struct ExtraSavedDetailPayload: Decodable {
    let ok: Bool?
    let monthStart: String
    let today: String
    let totalExtraSaved: Double
    let days: [ExtraSavedDayPayload]

    enum CodingKeys: String, CodingKey {
        case ok
        case monthStart = "month_start"
        case today
        case totalExtraSaved = "total_extra_saved"
        case days
    }
}

struct ExtraSavedDayPayload: Decodable, Hashable {
    let day: String
    let baseline: Double
    let spentTodayFree: Double
    let leftover: Double
    let appliedToExtraSaved: Double?
    let extraSavedAfterDay: Double?
    let isToday: Bool?

    enum CodingKeys: String, CodingKey {
        case day
        case baseline
        case spentTodayFree = "spent_today_free"
        case leftover
        case appliedToExtraSaved = "applied_to_extra_saved"
        case extraSavedAfterDay = "extra_saved_after_day"
        case isToday = "is_today"
    }
}

struct SpentSoFarBreakdownPayload: Decodable {
    let ok: Bool?
    let start: String
    let end: String
    let total: Double
    let totalAll: Double
    let roundupsTotal: Double
    let excluded: [SpentBreakdownCategory]
    let included: [SpentBreakdownCategory]

    enum CodingKeys: String, CodingKey {
        case ok
        case start
        case end
        case total
        case totalAll = "total_all"
        case roundupsTotal = "roundups_total"
        case excluded
        case included
    }
}

struct SpentBreakdownCategory: Decodable, Hashable {
    let category: String
    let total: Double
}

struct SpentSoFarTransactionsResponse: Decodable {
    let ok: Bool?
    let transactions: [TransactionItem]
}

struct BankTotalsPayload: Decodable {
    let checking: BankGroupPayload?
    let savings: BankGroupPayload?
    let investment: BankGroupPayload?
    let credit: BankGroupPayload?
    let other: BankGroupPayload?
}

struct BankGroupPayload: Decodable {
    let total: Double
    let accounts: [BankAccountPayload]
}

struct BankAccountPayload: Decodable, Identifiable, Hashable {
    let id: Int
    let name: String
    let total: Double
    let lastCsvUploadAt: String?
    let lastManualVerifiedAt: String?
    let creditLimit: Double?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case total
        case lastCsvUploadAt = "last_csv_upload_at"
        case lastManualVerifiedAt = "last_manual_verified_at"
        case creditLimit = "credit_limit"
    }
}

struct BankInfoPayload: Decodable {
    let lastUpdated: String?
    let accounts: [BankInfoAccountPayload]
    let creditCards: [BankInfoCreditCardPayload]

    enum CodingKeys: String, CodingKey {
        case lastUpdated = "last_updated"
        case accounts
        case creditCards = "credit_cards"
    }
}

struct BankInfoAccountPayload: Decodable, Identifiable, Hashable {
    let id: Int
    let bank: String
    let name: String
    let type: String
    let apy: Double?
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case id = "account_id"
        case bank
        case name
        case type
        case apy
        case notes
    }
}

struct BankInfoCreditCardPayload: Decodable, Identifiable, Hashable {
    let id: Int
    let bank: String
    let name: String
    let apr: Double?
    let creditLimit: Double?
    let benefits: [BankInfoBenefitPayload]

    enum CodingKeys: String, CodingKey {
        case id = "card_id"
        case bank
        case name
        case apr
        case creditLimit = "credit_limit"
        case benefits
    }
}

struct AccountInfoPayload: Decodable, Identifiable, Hashable {
    let id: Int
    let institution: String?
    let name: String
    let accountType: String?
    let lastCsvUploadAt: String?
    let lastManualVerifiedAt: String?
    let auditUpdatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case institution
        case name
        case accountType = "accounttype"
        case lastCsvUploadAt = "last_csv_upload_at"
        case lastManualVerifiedAt = "last_manual_verified_at"
        case auditUpdatedAt = "audit_updated_at"
    }
}

struct BankInfoBenefitPayload: Decodable, Hashable {
    let categories: [String]?
    let cashbackPercent: Double?

    enum CodingKeys: String, CodingKey {
        case categories
        case cashbackPercent = "cashback_percent"
    }
}

struct TransactionItem: Decodable, Identifiable, Hashable {
    let id: String
    let accountID: Int?
    let effectiveDate: String?
    let postedDate: String?
    let date: String?
    let merchant: String
    let amount: Double
    let status: String?
    let isIgnored: Bool?
    let bank: String?
    let card: String?
    let accountType: String?
    let category: String?
    let dateISO: String?
    let roundupCents: Int?
    let balanceAfter: Double?
    let transferPeer: String?
    let transferPeerID: String?
    let transferDir: String?

    enum CodingKeys: String, CodingKey {
        case id
        case accountID = "account_id"
        case effectiveDate = "effectiveDate"
        case postedDate
        case date
        case merchant
        case amount
        case status
        case isIgnored = "is_ignored"
        case bank
        case card
        case accountType = "accountType"
        case category
        case dateISO
        case roundupCents = "roundup_cents"
        case balanceAfter = "balance_after"
        case transferPeer = "transfer_peer"
        case transferPeerID = "transfer_peer_id"
        case transferDir = "transfer_dir"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try Self.decodeStringFlexible(container, forKey: .id)
        accountID = try? Self.decodeOptionalIntFlexible(container, forKey: .accountID)
        effectiveDate = try container.decodeIfPresent(String.self, forKey: .effectiveDate)
        postedDate = try container.decodeIfPresent(String.self, forKey: .postedDate)
        date = try container.decodeIfPresent(String.self, forKey: .date)
        merchant = try container.decodeIfPresent(String.self, forKey: .merchant) ?? ""
        amount = try container.decodeIfPresent(Double.self, forKey: .amount) ?? 0
        status = try container.decodeIfPresent(String.self, forKey: .status)
        isIgnored = try container.decodeIfPresent(Bool.self, forKey: .isIgnored)
        bank = try container.decodeIfPresent(String.self, forKey: .bank)
        card = try container.decodeIfPresent(String.self, forKey: .card)
        accountType = try container.decodeIfPresent(String.self, forKey: .accountType)
        category = try container.decodeIfPresent(String.self, forKey: .category)
        dateISO = try container.decodeIfPresent(String.self, forKey: .dateISO)
        roundupCents = try container.decodeIfPresent(Int.self, forKey: .roundupCents)
        balanceAfter = try container.decodeIfPresent(Double.self, forKey: .balanceAfter)
        transferPeer = try container.decodeIfPresent(String.self, forKey: .transferPeer)
        transferPeerID = try Self.decodeOptionalStringFlexible(container, forKey: .transferPeerID)
        transferDir = try container.decodeIfPresent(String.self, forKey: .transferDir)
    }

    static func decodeStringFlexible<K: CodingKey>(_ container: KeyedDecodingContainer<K>, forKey key: K) throws -> String {
        if let value = try? container.decode(String.self, forKey: key) {
            return value
        }
        if let value = try? container.decode(Int.self, forKey: key) {
            return String(value)
        }
        if let value = try? container.decode(Double.self, forKey: key) {
            return value.rounded() == value ? String(Int(value)) : String(value)
        }
        throw DecodingError.typeMismatch(
            String.self,
            .init(codingPath: container.codingPath + [key], debugDescription: "Expected String-like id")
        )
    }

    static func decodeIntFlexible<K: CodingKey>(_ container: KeyedDecodingContainer<K>, forKey key: K) throws -> Int {
        if let value = try? container.decode(Int.self, forKey: key) {
            return value
        }
        if let value = try? container.decode(String.self, forKey: key), let parsed = Int(value) {
            return parsed
        }
        throw DecodingError.typeMismatch(
            Int.self,
            .init(codingPath: container.codingPath + [key], debugDescription: "Expected Int or numeric String")
        )
    }

    static func decodeOptionalIntFlexible<K: CodingKey>(_ container: KeyedDecodingContainer<K>, forKey key: K) throws -> Int? {
        if let value = try? container.decodeIfPresent(Int.self, forKey: key) {
            return value
        }
        if let value = try? container.decodeIfPresent(String.self, forKey: key), let parsed = Int(value) {
            return parsed
        }
        return nil
    }

    static func decodeOptionalStringFlexible<K: CodingKey>(_ container: KeyedDecodingContainer<K>, forKey key: K) throws -> String? {
        if let value = try? container.decodeIfPresent(String.self, forKey: key) {
            return value
        }
        if let value = try? container.decodeIfPresent(Int.self, forKey: key) {
            return String(value)
        }
        if let value = try? container.decodeIfPresent(Double.self, forKey: key) {
            return value.rounded() == value ? String(Int(value)) : String(value)
        }
        return nil
    }
}

struct TransactionDetailResponse: Decodable {
    let ok: Bool?
    let transaction: TransactionDetailPayload
}

struct TransactionDetailPayload: Decodable, Identifiable, Hashable {
    let id: String
    let accountID: Int?
    let postedDate: String?
    let purchaseDate: String?
    let merchant: String
    let amount: Double
    let status: String?
    let bank: String?
    let card: String?
    let accountType: String?
    let category: String?
    let isIgnored: Bool?
    let categoryRuleId: Int?
    let categoryRulePattern: String?

    enum CodingKeys: String, CodingKey {
        case id
        case accountID = "account_id"
        case postedDate
        case purchaseDate
        case merchant
        case amount
        case status
        case bank
        case card
        case accountType = "accountType"
        case category
        case isIgnored = "is_ignored"
        case categoryRuleId = "category_rule_id"
        case categoryRulePattern = "category_rule_pattern"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try TransactionItem.decodeStringFlexible(container, forKey: .id)
        accountID = try? TransactionItem.decodeOptionalIntFlexible(container, forKey: .accountID)
        postedDate = try container.decodeIfPresent(String.self, forKey: .postedDate)
        purchaseDate = try container.decodeIfPresent(String.self, forKey: .purchaseDate)
        merchant = try container.decodeIfPresent(String.self, forKey: .merchant) ?? ""
        amount = try container.decodeIfPresent(Double.self, forKey: .amount) ?? 0
        status = try container.decodeIfPresent(String.self, forKey: .status)
        bank = try container.decodeIfPresent(String.self, forKey: .bank)
        card = try container.decodeIfPresent(String.self, forKey: .card)
        accountType = try container.decodeIfPresent(String.self, forKey: .accountType)
        category = try container.decodeIfPresent(String.self, forKey: .category)
        isIgnored = try container.decodeIfPresent(Bool.self, forKey: .isIgnored)
        categoryRuleId = try? TransactionItem.decodeOptionalIntFlexible(container, forKey: .categoryRuleId)
        categoryRulePattern = try container.decodeIfPresent(String.self, forKey: .categoryRulePattern)
    }
}

struct AccountTransactionsRangePayload: Decodable {
    let accountID: Int
    let start: String
    let end: String
    let pendingBalanceMultiplier: Int?
    let startingBalance: Double?
    let endingBalance: Double?
    let transactions: [TransactionItem]

    enum CodingKeys: String, CodingKey {
        case accountID = "account_id"
        case start
        case end
        case pendingBalanceMultiplier = "pending_balance_multiplier"
        case startingBalance = "starting_balance"
        case endingBalance = "ending_balance"
        case transactions
    }
}

struct UpcomingEventPayload: Decodable, Hashable, Identifiable {
    let id: String
    let date: String
    let merchant: String?
    let amount: Double?
    let type: String?
    let cadence: String?
    let category: String?
    let accountID: Int?
    let payTarget: String?

    enum CodingKeys: String, CodingKey {
        case date
        case merchant
        case amount
        case type
        case cadence
        case category
        case accountID = "account_id"
        case payTarget = "pay_target"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        date = try container.decodeIfPresent(String.self, forKey: .date) ?? ""
        merchant = try container.decodeIfPresent(String.self, forKey: .merchant)
        amount = try container.decodeIfPresent(Double.self, forKey: .amount)
        type = try container.decodeIfPresent(String.self, forKey: .type)
        cadence = try container.decodeIfPresent(String.self, forKey: .cadence)
        category = try container.decodeIfPresent(String.self, forKey: .category)
        accountID = try? container.decodeIfPresent(Int.self, forKey: .accountID)
        payTarget = try container.decodeIfPresent(String.self, forKey: .payTarget)
        id = [
            date,
            merchant ?? "",
            String(amount ?? 0),
            type ?? "",
            cadence ?? "",
            String(accountID ?? -1),
            payTarget ?? ""
        ].joined(separator: "|")
    }
}

struct MonthBudgetPayload: Decodable {
    let safeToSpend: Double?
    let dailyLimit: Double?
    let daysLeft: Int?
    let asOf: String?
    let expectedIncome: Double?
    let baseIncome: Double?
    let spentSoFar: Double?
    let billsRemaining: Double?
    let savingsGoal: Double?
    let incomeBasisTotal: Double?
    let incomeBasisMonth: MonthBudgetIncomeBasisMonth?
    let incomeBasisPaychecks: [MonthBudgetIncomePaycheck]?
    let allocationsTotal: Double?
    let budgetedSpentTotal: Double?
    let billsTotal: Double?
    let freeSpendGoal: Double?
    let spentFree: Double?

    enum CodingKeys: String, CodingKey {
        case safeToSpend = "safe_to_spend"
        case dailyLimit = "daily_limit"
        case daysLeft = "days_left"
        case asOf = "as_of"
        case expectedIncome = "expected_income"
        case baseIncome = "base_income"
        case spentSoFar = "spent_so_far"
        case billsRemaining = "bills_remaining"
        case savingsGoal = "savings_goal"
        case incomeBasisTotal = "income_basis_total"
        case incomeBasisMonth = "income_basis_month"
        case incomeBasisPaychecks = "income_basis_paychecks"
        case allocationsTotal = "allocations_total"
        case budgetedSpentTotal = "budgeted_spent_total"
        case billsTotal = "bills_total"
        case freeSpendGoal = "free_spend_goal"
        case spentFree = "spent_free"
    }
}

struct PageBudgetPayload: Decodable {
    let ok: Bool?
    let month: MonthBudgetPayload?
    let groups: [BudgetGroupPayload]
    let funds: [SinkingFundPayload]
    let spentCategories: [BudgetSpentCategoryPayload]
    let savingsGoalConfig: SavingsGoalConfigPayload?

    enum CodingKeys: String, CodingKey {
        case ok
        case month
        case groups
        case funds
        case spentCategories = "spent_categories"
        case savingsGoalConfig = "savings_goal_cfg"
    }
}

struct BudgetGroupPayload: Decodable, Identifiable, Hashable {
    let id: Int
    let name: String
    let allocated: Double?
    let cap: Double?
    let categories: [String]
    let spent: Double?
    let remaining: Double?
    let overCap: Bool?
    let readOnly: Bool?
    let syntheticKind: String?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case allocated
        case cap
        case categories
        case spent
        case remaining
        case overCap = "over_cap"
        case readOnly = "read_only"
        case syntheticKind = "synthetic_kind"
    }
}

struct SinkingFundPayload: Decodable, Identifiable, Hashable {
    let id: Int
    let name: String
    let targetAmount: Double?
    let targetDate: String?
    let cadence: String?
    let contribAmount: Double?
    let reservedBalance: Double?
    let neededPerDay: Double?
    let isActive: Bool?

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case targetAmount = "target_amount"
        case targetDate = "target_date"
        case cadence
        case contribAmount = "contrib_amount"
        case reservedBalance = "reserved_balance"
        case neededPerDay = "needed_per_day"
        case isActive = "is_active"
    }
}

struct BudgetSpentCategoryPayload: Decodable, Hashable, Identifiable {
    let category: String
    let spent: Double
    var id: String { category }
}

struct SavingsGoalConfigPayload: Decodable, Hashable {
    let mode: String
    let value: Double
}

struct RoundUpSettingsPayload: Decodable, Hashable {
    let enabled: Bool
    let category: String?
}

struct MonthBudgetIncomeBasisMonth: Decodable, Hashable {
    let year: Int?
    let month: Int?
}

struct MonthBudgetIncomePaycheck: Decodable, Hashable {
    let date: String?
    let merchant: String?
    let amount: Double?
}

struct ExtraSavedPayload: Decodable {
    let ok: Bool?
    let extraSaved: Double?

    enum CodingKeys: String, CodingKey {
        case ok
        case extraSaved = "extra_saved"
    }
}

struct NotificationItemPayload: Decodable, Identifiable, Hashable {
    let id: Int
    let kind: String?
    let subject: String?
    let sender: String?
    let createdAt: String?
    let createdAtLocal: String?
    let isRead: Bool?

    enum CodingKeys: String, CodingKey {
        case id
        case kind
        case subject
        case sender
        case createdAt = "created_at"
        case createdAtLocal = "created_at_local"
        case isRead = "is_read"
    }
}

struct DayLimitPayload: Decodable {
    let baseline: Double?
    let remainingToday: Double?
    let spentTodayFree: Double?
    let day: String?

    enum CodingKeys: String, CodingKey {
        case baseline
        case remainingToday = "remaining_today"
        case spentTodayFree = "spent_today_free"
        case day
    }
}

struct ChartSeriesPoint: Decodable, Hashable {
    let date: String
    let value: Double
    let banks: Double?
    let savings: Double?
    let cards: Double?
    let cardsBalance: Double?

    enum CodingKeys: String, CodingKey {
        case date
        case value
        case banks
        case savings
        case cards
        case cardsBalance = "cards_balance"
    }
}

struct SettingsGoogleOAuthStatusPayload: Decodable {
    let ok: Bool?
    let connected: Bool?
    let email: String?
    let scope: String?
    let expiresAt: String?
    let hasRefreshToken: Bool?

    enum CodingKeys: String, CodingKey {
        case ok
        case connected
        case email
        case scope
        case expiresAt = "expires_at"
        case hasRefreshToken = "has_refresh_token"
    }
}

struct SettingsInitialSetupCountsPayload: Decodable, Hashable {
    let accountsTotal: Int?
    let accountsWithCsvMapping: Int?
    let accountsExpectEmail: Int?
    let accountsWithParser: Int?
    let requirementsTotal: Int?
    let requirementsDone: Int?

    enum CodingKeys: String, CodingKey {
        case accountsTotal = "accounts_total"
        case accountsWithCsvMapping = "accounts_with_csv_mapping"
        case accountsExpectEmail = "accounts_expect_email"
        case accountsWithParser = "accounts_with_parser"
        case requirementsTotal = "requirements_total"
        case requirementsDone = "requirements_done"
    }
}

struct SettingsInitialSetupPayload: Decodable {
    let ok: Bool?
    let complete: Bool?
    let percent: Int?
    let counts: SettingsInitialSetupCountsPayload?
}

struct SettingsNotificationSettingsPayload: Decodable {
    let prefs: [String: Bool]
    let pushoverUserKeySet: Bool?
    let pushoverUserKey: String?

    enum CodingKeys: String, CodingKey {
        case prefs
        case pushoverUserKeySet = "pushover_user_key_set"
        case pushoverUserKey = "pushover_user_key"
    }
}

struct SettingsDailyWeightsPayload: Decodable {
    let weekdayPoints: Double?
    let weekendPoints: Double?

    enum CodingKeys: String, CodingKey {
        case weekdayPoints = "weekday_points"
        case weekendPoints = "weekend_points"
    }
}

struct SettingsCacheVersionsPayload: Decodable {
    let ok: Bool?
    let tenantID: Int?
    let homeSnapshotVersion: Int?
    let widgetVersion: Int?

    enum CodingKeys: String, CodingKey {
        case ok
        case tenantID = "tenant_id"
        case homeSnapshotVersion = "home_snapshot_version"
        case widgetVersion = "widget_version"
    }
}

struct SettingsViewFlagsPayload: Decodable {
    let ok: Bool?
    let isOwner: Bool?

    enum CodingKeys: String, CodingKey {
        case ok
        case isOwner = "is_owner"
    }
}

struct SettingsRefreshCachePayload: Decodable {
    let ok: Bool?
    let tenantID: Int?
    let homeSnapshotVersion: Int?
    let homeCacheWarmed: Bool?
    let widgetVersion: Int?

    enum CodingKeys: String, CodingKey {
        case ok
        case tenantID = "tenant_id"
        case homeSnapshotVersion = "home_snapshot_version"
        case homeCacheWarmed = "home_cache_warmed"
        case widgetVersion = "widget_version"
    }
}
