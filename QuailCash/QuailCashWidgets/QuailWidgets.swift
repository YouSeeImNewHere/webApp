import WidgetKit
import SwiftUI
import AppIntents
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

struct QuailWidgetEntry: TimelineEntry {
    let date: Date
    let payload: WidgetSummaryPayload
    let state: WidgetEntryState
}

enum WidgetEntryState: String {
    case live
    case stale
    case tokenMissing
    case failed
}

private func sharedToken() -> String? {
    let defaults = UserDefaults(suiteName: "group.quail.shared")
    let value = defaults?.string(forKey: "quail.mobile.api.token") ?? ""
    return value.isEmpty ? nil : value
}

struct QuailWidgetProvider: TimelineProvider {
    func placeholder(in context: Context) -> QuailWidgetEntry {
        QuailWidgetEntry(date: .now, payload: .preview, state: .live)
    }

    func getSnapshot(in context: Context, completion: @escaping (QuailWidgetEntry) -> Void) {
        guard let token = sharedToken() else {
            completion(QuailWidgetEntry(date: .now, payload: .preview, state: .tokenMissing))
            return
        }
        Task {
            let entry: QuailWidgetEntry
            do {
                let payload = try await WidgetAPI.fetchSummary(widgetToken: token)
                entry = QuailWidgetEntry(date: .now, payload: payload, state: payload.entryState)
            } catch {
                entry = QuailWidgetEntry(date: .now, payload: .preview, state: .failed)
            }
            completion(entry)
        }
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<QuailWidgetEntry>) -> Void) {
        guard let token = sharedToken() else {
            let entry = QuailWidgetEntry(date: .now, payload: .preview, state: .tokenMissing)
            completion(Timeline(entries: [entry], policy: .after(.now.addingTimeInterval(60 * 30))))
            return
        }
        Task {
            let entry: QuailWidgetEntry
            let policy: TimelineReloadPolicy
            do {
                let payload = try await WidgetAPI.fetchSummary(widgetToken: token)
                entry = QuailWidgetEntry(date: .now, payload: payload, state: payload.entryState)
                policy = .after(.now.addingTimeInterval(60 * 15))
            } catch {
                entry = QuailWidgetEntry(date: .now, payload: .preview, state: .failed)
                policy = .after(.now.addingTimeInterval(60 * 15))
            }
            completion(Timeline(entries: [entry], policy: policy))
        }
    }
}

struct QuailHomeWidget: Widget {
    let kind: String = "QuailHomeWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: QuailWidgetProvider()) { entry in
            QuailWidgetView(entry: entry)
                .containerBackground(for: .widget) {
                    LinearGradient(
                        colors: [Color(red: 0.10, green: 0.11, blue: 0.13), Color(red: 0.15, green: 0.16, blue: 0.19)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                }
        }
        .configurationDisplayName("Quail Finance")
        .description("Safe to spend, daily limit, credit usage, and alerts.")
        .supportedFamilies([.systemSmall, .systemMedium, .systemLarge, .accessoryInline, .accessoryCircular, .accessoryRectangular])
        .contentMarginsDisabled()
    }
}

struct QuailWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: QuailWidgetEntry

    var body: some View {
        switch family {
        case .systemSmall:
            QuailSmallWidget(entry: entry)
        case .systemLarge:
            QuailLargeWidget(entry: entry)
        case .accessoryInline:
            Text("Left \(entry.payload.today.remainingToday.money0)")
        case .accessoryCircular:
            ZStack {
                Circle().fill(Color.black.opacity(0.18))
                Text(entry.payload.today.remainingToday.money0)
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .minimumScaleFactor(0.55)
            }
        case .accessoryRectangular:
            QuailRectangularWidget(entry: entry)
        default:
            QuailMediumWidget(entry: entry)
        }
    }
}

private struct QuailMediumWidget: View {
    let entry: QuailWidgetEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 16) {
                VStack(alignment: .leading, spacing: 0) {
                    WidgetMetricBar(
                        title: "CREDIT USAGE",
                        trailing: "\(Int((entry.payload.credit.pct.clamped01 * 100).rounded()))%",
                        trailingColor: WidgetPalette.creditColor(entry.payload.credit.pct.clamped01),
                        fill: entry.payload.credit.pct.clamped01,
                        fillColor: WidgetPalette.creditColor(entry.payload.credit.pct.clamped01),
                        label: entry.payload.credit.available.money0,
                        barWidth: 170
                    )
                    Spacer().frame(height: 4)
                    WidgetMetricBar(
                        title: "SAFE TO SPEND",
                        trailing: entry.payload.month.freeSpendGoal.money0,
                        fill: entry.payload.month.freeSpendGoal > 0 ? max(0, min(1, entry.payload.safeToSpend / entry.payload.month.freeSpendGoal)) : 0,
                        fillColor: WidgetPalette.safePaceColor(remaining: entry.payload.safeToSpend, total: entry.payload.month.freeSpendGoal),
                        label: entry.payload.safeToSpend.money2,
                        barWidth: 170
                    )
                    Spacer().frame(height: 4)
                    WidgetMetricBar(
                        title: "DAILY LIMIT",
                        trailing: entry.payload.today.baseline.money0,
                        fill: entry.payload.today.baseline > 0 ? max(0, min(1, entry.payload.today.remainingToday / entry.payload.today.baseline)) : 0,
                        fillColor: WidgetPalette.dayColor(remaining: entry.payload.today.remainingToday, baseline: entry.payload.today.baseline),
                        label: entry.payload.today.remainingToday.money2,
                        barWidth: 170
                    )
                }
                .frame(width: 170, alignment: .leading)

                VStack(alignment: .leading, spacing: 8) {
                    WidgetKV(label: "Checking", value: entry.payload.totals.checking.money2)
                    WidgetKV(label: "Savings", value: entry.payload.totals.savings.money2)
                    WidgetKV(label: "Alerts", value: "\(max(0, entry.payload.notificationsUnread))")
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            Text(entry.payload.footerText(for: entry.state))
                .font(.system(size: 10, weight: .medium, design: .rounded))
                .foregroundStyle(.white.opacity(0.60))
        }
        .widgetPadding()
    }
}

private struct QuailLargeWidget: View {
    let entry: QuailWidgetEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 10) {
                VStack(alignment: .leading, spacing: 6) {
                    WidgetMetricBar(
                        title: "CREDIT USAGE",
                        trailing: "\(Int((entry.payload.credit.pct.clamped01 * 100).rounded()))%",
                        trailingColor: WidgetPalette.creditColor(entry.payload.credit.pct.clamped01),
                        fill: entry.payload.credit.pct.clamped01,
                        fillColor: WidgetPalette.creditColor(entry.payload.credit.pct.clamped01),
                        label: entry.payload.credit.available.money0,
                        barWidth: 204
                    )
                    WidgetMetricBar(
                        title: "SAFE TO SPEND",
                        trailing: entry.payload.month.freeSpendGoal.money0,
                        fill: entry.payload.month.freeSpendGoal > 0 ? max(0, min(1, entry.payload.safeToSpend / entry.payload.month.freeSpendGoal)) : 0,
                        fillColor: WidgetPalette.safePaceColor(remaining: entry.payload.safeToSpend, total: entry.payload.month.freeSpendGoal),
                        label: entry.payload.safeToSpend.money2,
                        barWidth: 204
                    )
                    WidgetMetricBar(
                        title: "DAILY LIMIT",
                        trailing: entry.payload.today.baseline.money0,
                        fill: entry.payload.today.baseline > 0 ? max(0, min(1, entry.payload.today.remainingToday / entry.payload.today.baseline)) : 0,
                        fillColor: WidgetPalette.dayColor(remaining: entry.payload.today.remainingToday, baseline: entry.payload.today.baseline),
                        label: entry.payload.today.remainingToday.money2,
                        barWidth: 204
                    )
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("TOTALS")
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                        .foregroundStyle(.white.opacity(0.92))
                    WidgetKV(label: "Checking", value: entry.payload.totals.checking.money2)
                    WidgetKV(label: "Savings", value: entry.payload.totals.savings.money2)
                    WidgetKV(label: "Alerts", value: "\(max(0, entry.payload.notificationsUnread))")
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack(spacing: 10) {
                WidgetPill(label: "Today", value: entry.payload.today.remainingToday.money2)
                WidgetPill(label: "Safe", value: entry.payload.safeToSpend.money0)
                WidgetPill(label: "Credit Avail", value: entry.payload.credit.available.money0)
            }
            Text(entry.payload.footerText(for: entry.state))
                .font(.system(size: 10, weight: .medium, design: .rounded))
                .foregroundStyle(.white.opacity(0.60))
        }
        .widgetPadding()
    }
}

private struct QuailSmallWidget: View {
    let entry: QuailWidgetEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            WidgetMetricBar(
                title: "CREDIT USAGE",
                trailing: "\(Int((entry.payload.credit.pct.clamped01 * 100).rounded()))%",
                trailingColor: WidgetPalette.creditColor(entry.payload.credit.pct.clamped01),
                fill: entry.payload.credit.pct.clamped01,
                fillColor: WidgetPalette.creditColor(entry.payload.credit.pct.clamped01),
                label: entry.payload.credit.available.money0,
                barWidth: 142
            )
            WidgetMetricBar(
                title: "SAFE TO SPEND",
                trailing: entry.payload.month.freeSpendGoal.money0,
                fill: entry.payload.month.freeSpendGoal > 0 ? max(0, min(1, entry.payload.safeToSpend / entry.payload.month.freeSpendGoal)) : 0,
                fillColor: WidgetPalette.safePaceColor(remaining: entry.payload.safeToSpend, total: entry.payload.month.freeSpendGoal),
                label: entry.payload.safeToSpend.money2,
                barWidth: 142
            )
            WidgetMetricBar(
                title: "DAILY LIMIT",
                trailing: entry.payload.today.baseline.money0,
                fill: entry.payload.today.baseline > 0 ? max(0, min(1, entry.payload.today.remainingToday / entry.payload.today.baseline)) : 0,
                fillColor: WidgetPalette.dayColor(remaining: entry.payload.today.remainingToday, baseline: entry.payload.today.baseline),
                label: entry.payload.today.remainingToday.money2,
                barWidth: 142
            )
            Text(entry.payload.footerText(for: entry.state))
                .font(.system(size: 10, weight: .medium, design: .rounded))
                .foregroundStyle(.white.opacity(0.60))
        }
        .widgetPadding()
    }
}

private struct QuailRectangularWidget: View {
    let entry: QuailWidgetEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(entry.payload.today.remainingToday.money2)
                    .font(.system(size: 22, weight: .bold, design: .rounded))
                    .minimumScaleFactor(0.55)
                    .foregroundStyle(.white)
                Spacer(minLength: 6)
                Text("\(Int((entry.payload.credit.pct.clamped01 * 100).rounded()))%")
                    .font(.system(size: 12, weight: .bold, design: .rounded))
                    .foregroundStyle(WidgetPalette.creditColor(entry.payload.credit.pct.clamped01))
            }
            Text("Base \(entry.payload.today.baseline.money0)/day")
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(.white.opacity(0.74))
            Text("Safe \(entry.payload.safeToSpend.money0)")
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(.white.opacity(0.74))
        }
        .widgetPadding()
    }
}

private struct WidgetMetricBar: View {
    let title: String
    let trailing: String
    var trailingColor: Color = .white
    let fill: Double
    let fillColor: Color
    let label: String
    var barWidth: CGFloat = 182

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 6) {
                Text(title)
                    .font(.system(size: 10, weight: .bold, design: .rounded))
                    .foregroundStyle(.white.opacity(0.55))
                Spacer(minLength: 6)
                Text(trailing)
                    .font(.system(size: 10, weight: .bold, design: .rounded))
                    .foregroundStyle(trailingColor)
            }
            WidgetBar(fill: fill, fillColor: fillColor, label: label)
                .frame(width: barWidth, height: 12)
        }
    }
}

private struct WidgetBar: View {
    let fill: Double
    let fillColor: Color
    let label: String

    var body: some View {
        GeometryReader { geo in
            let clamped = max(0, min(1, fill))
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .fill(Color.white.opacity(0.22))
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .fill(fillColor)
                    .frame(width: max(1, geo.size.width * clamped))
                Text(label)
                    .font(.system(size: 9, weight: .bold, design: .rounded))
                    .foregroundStyle(.white.opacity(0.95))
                    .frame(maxWidth: .infinity)
            }
        }
    }
}

private struct WidgetKV: View {
    let label: String
    let value: String

    var body: some View {
        HStack(spacing: 6) {
            Text(label)
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(.white.opacity(0.75))
            Spacer(minLength: 6)
            Text(value)
                .font(.system(size: 12, weight: .bold, design: .rounded))
                .foregroundStyle(.white)
        }
    }
}

private struct WidgetPill: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label)
                .font(.system(size: 10, weight: .medium, design: .rounded))
                .foregroundStyle(.white.opacity(0.65))
            Text(value)
                .font(.system(size: 12, weight: .bold, design: .rounded))
                .foregroundStyle(.white)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 8)
        .padding(.horizontal, 10)
        .background(Color.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

private enum WidgetPalette {
    static func creditColor(_ pct: Double) -> Color {
        if pct < 0.3 { return Color(red: 0.20, green: 0.78, blue: 0.35) }
        if pct < 0.6 { return Color(red: 1.00, green: 0.62, blue: 0.05) }
        return Color(red: 1.00, green: 0.27, blue: 0.23)
    }

    static func safePaceColor(remaining: Double, total: Double) -> Color {
        guard total > 0 else { return creditColor(0.2) }
        let elapsed = monthElapsedPct()
        let expectedRemaining = total * (1 - elapsed)
        let tolerance = max(total * 0.05, 25)
        if remaining > expectedRemaining + tolerance { return creditColor(0.2) }
        if remaining < expectedRemaining - tolerance { return creditColor(0.8) }
        return creditColor(0.45)
    }

    static func dayColor(remaining: Double, baseline: Double) -> Color {
        if remaining < 0 { return creditColor(0.8) }
        let pct = baseline > 0 ? remaining / baseline : 0
        if pct < 0.3 { return creditColor(0.45) }
        return creditColor(0.2)
    }

    static func monthElapsedPct() -> Double {
        let now = Date()
        let calendar = Calendar.current
        let daysInMonth = calendar.range(of: .day, in: .month, for: now)?.count ?? 30
        let day = calendar.component(.day, from: now)
        let hour = calendar.component(.hour, from: now)
        let minute = calendar.component(.minute, from: now)
        let fracDay = (Double(hour) + (Double(minute) / 60.0)) / 24.0
        return max(0, min(1, ((Double(day - 1)) + fracDay) / Double(daysInMonth)))
    }
}

private extension View {
    func widgetPadding() -> some View {
        padding(.horizontal, 4)
            .padding(.vertical, 4)
    }
}

struct QuailImportLiveActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: ImportBatchAttributes.self) { context in
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 10) {
                    Image(systemName: "square.and.arrow.down.on.square.fill")
                        .foregroundStyle(.blue)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(context.state.title)
                            .font(.system(size: 14, weight: .bold, design: .rounded))
                            .lineLimit(1)
                        Text(context.state.status)
                            .font(.system(size: 12, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 8)
                    Text("\(context.state.processedFileCount)/\(context.state.totalFileCount)")
                        .font(.system(size: 12, weight: .bold, design: .rounded))
                }
                HStack(spacing: 10) {
                    liveStat(label: "File Tx", value: "\(context.state.currentFileTransactions)")
                    liveStat(label: "Imported", value: "\(context.state.importedTransactions)")
                    liveStat(label: "Skipped", value: "\(context.state.skippedTransactions)")
                }
                ProgressView(value: Double(context.state.processedFileCount), total: Double(max(context.state.totalFileCount, 1)))
                    .tint(.blue)
            }
            .padding(14)
            .activityBackgroundTint(Color(.systemBackground))
            .activitySystemActionForegroundColor(.blue)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Image(systemName: "square.and.arrow.down.on.square.fill")
                        .foregroundStyle(.blue)
                }
                DynamicIslandExpandedRegion(.center) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(context.state.title)
                            .font(.system(size: 13, weight: .bold, design: .rounded))
                            .lineLimit(1)
                        Text(context.state.status)
                            .font(.system(size: 11, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text("\(context.state.processedFileCount)/\(context.state.totalFileCount)")
                        .font(.system(size: 11, weight: .bold, design: .rounded))
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack(spacing: 12) {
                            liveStat(label: "File Tx", value: "\(context.state.currentFileTransactions)")
                            liveStat(label: "Imported", value: "\(context.state.importedTransactions)")
                            liveStat(label: "Skipped", value: "\(context.state.skippedTransactions)")
                        }
                        ProgressView(value: Double(context.state.processedFileCount), total: Double(max(context.state.totalFileCount, 1)))
                            .tint(.blue)
                    }
                }
            } compactLeading: {
                Image(systemName: "square.and.arrow.down.on.square.fill")
            } compactTrailing: {
                Text("\(context.state.processedFileCount)/\(context.state.totalFileCount)")
                    .font(.system(size: 11, weight: .bold, design: .rounded))
            } minimal: {
                Image(systemName: "square.and.arrow.down.on.square.fill")
            }
        }
    }

    private func liveStat(label: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.system(size: 10, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 12, weight: .bold, design: .rounded))
                .foregroundStyle(.primary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

@main
struct QuailWidgetsBundle: WidgetBundle {
    var body: some Widget {
        QuailHomeWidget()
        QuailImportLiveActivityWidget()
    }
}
