import Foundation
import HealthKit

enum HealthKitHelper {
    static var isAvailable: Bool { HKHealthStore.isHealthDataAvailable() }
    private static let store = HKHealthStore()

    static func fetchAverageWalkingSpeed(completion: @escaping (Double?) -> Void) {
        guard isAvailable,
              let type = HKQuantityType.quantityType(forIdentifier: .walkingSpeed) else {
            completion(nil)
            return
        }
        store.requestAuthorization(toShare: [], read: [type]) { granted, _ in
            guard granted else { completion(nil); return }
            let query = HKStatisticsQuery(
                quantityType: type,
                quantitySamplePredicate: nil,
                options: .discreteAverage
            ) { _, stats, _ in
                let mps = stats?.averageQuantity()?.doubleValue(for: HKUnit(from: "m/s"))
                completion(mps)
            }
            store.execute(query)
        }
    }
}
