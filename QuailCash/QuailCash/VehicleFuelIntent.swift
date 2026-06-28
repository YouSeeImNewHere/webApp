import AppIntents
import Foundation

struct LogFuelFillupIntent: AppIntent {
    static var title: LocalizedStringResource = "Log Gas Fill-Up"
    static var description = IntentDescription("Record a fuel fill-up in Quail Car with your current odometer reading and gallons pumped.")

    static var parameterSummary: some ParameterSummary {
        Summary("Log \(\.$gallons) gal at \(\.$odometer) mi")
    }

    @Parameter(title: "Odometer Reading (mi)", description: "Your current odometer in miles", requestValueDialog: "What's your current odometer reading?")
    var odometer: Int

    @Parameter(title: "Gallons Pumped", description: "How many gallons did you pump? (e.g. 10.352)", requestValueDialog: "How many gallons did you pump?")
    var gallons: Double

    @Parameter(title: "Price per Gallon (optional)", description: "Price per gallon in dollars", requestValueDialog: "What was the price per gallon? (skip to leave blank)")
    var pricePerGallon: Double?

    @Parameter(title: "Station Name (optional)", description: "Name of the gas station")
    var stationName: String?

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let record = FuelRecord(
            date: Date(),
            mileage: odometer,
            gallons: gallons,
            pricePerGallon: pricePerGallon,
            stationName: stationName ?? ""
        )
        VehicleStore.shared.addFuelRecord(record)
        await VehicleStore.shared.refresh()

        let mpgText: String
        if let mpg = VehicleStore.shared.averageMPG() {
            mpgText = " Your running average is \(String(format: "%.1f", mpg)) MPG."
        } else {
            mpgText = ""
        }

        let totalText = pricePerGallon.map { " Total: $\(String(format: "%.2f", $0 * gallons))." } ?? ""
        return .result(dialog: "Logged \(String(format: "%.3f", gallons)) gallons at \(odometer.formatted()) miles.\(totalText)\(mpgText)")
    }
}
