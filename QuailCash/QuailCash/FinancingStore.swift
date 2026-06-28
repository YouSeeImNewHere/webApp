import Foundation
import Combine

struct FinancingPlan: Identifiable, Codable, Equatable {
    let id: Int
    var label: String
    var totalAmount: Double
    var monthlyPayment: Double
    var totalMonths: Int
    var monthsPaid: Int
    var startDate: String
    var transactionId: String?
    var isComplete: Bool
    var amountPaid: Double
    var amountRemaining: Double

    var monthsRemaining: Int { max(0, totalMonths - monthsPaid) }
    var progressFraction: Double { totalMonths > 0 ? Double(monthsPaid) / Double(totalMonths) : 0 }

    enum CodingKeys: String, CodingKey {
        case id, label
        case totalAmount = "total_amount"
        case monthlyPayment = "monthly_payment"
        case totalMonths = "total_months"
        case monthsPaid = "months_paid"
        case startDate = "start_date"
        case transactionId = "transaction_id"
        case isComplete = "is_complete"
        case amountPaid = "amount_paid"
        case amountRemaining = "amount_remaining"
    }
}

@MainActor
final class FinancingStore: ObservableObject {
    static let shared = FinancingStore()
    @Published var plans: [FinancingPlan] = []
    @Published var isLoading = false

    var activePlans: [FinancingPlan] { plans.filter { !$0.isComplete } }
    var completedPlans: [FinancingPlan] { plans.filter { $0.isComplete } }

    func refresh() async {
        isLoading = true
        defer { isLoading = false }
        plans = (try? await QuailCashAPI.shared.fetchFinancingPlans()) ?? []
    }

    func createPlan(label: String, totalAmount: Double, totalMonths: Int, transactionId: String?) async {
        guard let plan = try? await QuailCashAPI.shared.createFinancingPlan(
            label: label, totalAmount: totalAmount, totalMonths: totalMonths, transactionId: transactionId
        ) else { return }
        plans.insert(plan, at: 0)
    }

    func recordPayment(_ plan: FinancingPlan) async {
        try? await QuailCashAPI.shared.recordFinancingPayment(planId: plan.id)
        await refresh()
    }

    func deletePlan(_ plan: FinancingPlan) async {
        try? await QuailCashAPI.shared.deleteFinancingPlan(planId: plan.id)
        plans.removeAll { $0.id == plan.id }
    }
}
