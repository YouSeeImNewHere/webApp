import SwiftUI

// MARK: - Page Shell

enum FitnessBarTab { case home, goals }

struct QuailFitnessPageShell<Content: View>: View {
    @EnvironmentObject private var navigator: AppNavigator
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"

    let title: String
    let badgeValue: Int?
    let selectedBarTab: FitnessBarTab?
    let onLeadingTap: () -> Void
    let onTrailingTap: () -> Void
    let content: Content

    init(
        title: String,
        badgeValue: Int? = nil,
        selectedBarTab: FitnessBarTab? = nil,
        onLeadingTap: @escaping () -> Void,
        onTrailingTap: @escaping () -> Void,
        @ViewBuilder content: () -> Content
    ) {
        self.title = title; self.badgeValue = badgeValue
        self.selectedBarTab = selectedBarTab
        self.onLeadingTap = onLeadingTap; self.onTrailingTap = onTrailingTap
        self.content = content()
    }

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        AppChromeFrame(
            title: title, badgeValue: badgeValue, selectedTab: nil,
            showsBottomBar: false,
            onLeadingTap: onLeadingTap, onTrailingTap: onTrailingTap,
            onSelectTab: { _ in }
        ) { content }
        .safeAreaInset(edge: .bottom, spacing: 0) { fitnessBottomBar(palette: palette) }
    }

    private func fitnessBottomBar(palette: QuailThemePalette) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                fitnessBarTab("Home", icon: "house.fill", tab: .home) { navigator.setRoot(.fitness) }
                fitnessBarTab("Goals", icon: "target", tab: .goals) { navigator.show(.fitnessGoals) }
                Button { navigator.setRoot(.dashboard) } label: {
                    VStack(spacing: 4) {
                        Image(systemName: "square.grid.2x2.fill").font(.system(size: 16, weight: .semibold))
                        Text("Dashboard").font(.system(size: 12, weight: .medium, design: .rounded))
                    }
                    .frame(minWidth: 108)
                    .padding(.vertical, 8)
                    .foregroundStyle(palette.primaryButtonText)
                    .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(palette.primaryButton))
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 8).padding(.top, 6).padding(.bottom, 2)
        }
        .background(palette.barBackground)
        .overlay(Rectangle().fill(palette.barDivider).frame(height: 1), alignment: .top)
    }

    private func fitnessBarTab(_ title: String, icon: String, tab: FitnessBarTab, action: @escaping () -> Void) -> some View {
        let palette = QuailTheme.palette(for: themeSelection)
        let isSelected = selectedBarTab == tab
        return Button(action: action) {
            VStack(spacing: 4) {
                Image(systemName: icon).font(.system(size: 16, weight: .semibold))
                Text(title).font(.system(size: 12, weight: .medium, design: .rounded))
            }
            .frame(minWidth: 84)
            .padding(.vertical, 8)
            .foregroundStyle(isSelected ? palette.chromeIconForeground : palette.chromeIconForeground.opacity(0.72))
            .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(isSelected ? palette.selectedTabFill : .clear))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(isSelected ? palette.border : .clear, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Fitness Sheet Enum

private enum FitnessSheet: Identifiable {
    case exerciseDetail(Exercise)
    case addMilestone
    case addExercise(session: Binding<WorkoutSession>)
    case bodyweightEntry(onSet: (Double) -> Void)
    case sessionDetail(WorkoutSession)

    var id: String {
        switch self {
        case .exerciseDetail(let e):  return "ex-\(e.id)"
        case .addMilestone:           return "milestone"
        case .addExercise:            return "addExercise"
        case .bodyweightEntry:        return "bwEntry"
        case .sessionDetail(let s):   return "sess-\(s.id)"
        }
    }
}

// MARK: - Main Fitness Page

struct FitnessPageView: View {
    @EnvironmentObject private var navigator: AppNavigator
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = FitnessStore.shared

    @State private var activeSheet: FitnessSheet?
    @State private var showActiveWorkout = false
    @State private var showCreateRoutine = false
    @State private var showTrainingPlan = false

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        QuailFitnessPageShell(
            title: "Quail Fitness",
            selectedBarTab: .home,
            onLeadingTap: { navigator.show(.fitnessSettings) },
            onTrailingTap: { navigator.show(.fitnessNotifications) }
        ) {
            AppPageScroll(contentPadding: 14) {
                VStack(alignment: .leading, spacing: 14) {
                    readinessCard
                    healthMetricsSection
                    trainingPlanCard
                    startWorkoutCard
                    routinesSection
                    if !store.recentSessions().isEmpty {
                        recentSessionsSection
                    }
                    progressionSection
                    weeklyVolumeSection
                    if !store.milestones.isEmpty {
                        milestonesSection
                    }
                    Color.clear.frame(height: 60)
                }
            }
        }
        .sheet(isPresented: $showTrainingPlan) {
            TrainingPlanSheet()
        }
        .sheet(item: $activeSheet) { sheet in
            sheetContent(sheet)
        }
        .fullScreenCover(isPresented: $showActiveWorkout) {
            ActiveWorkoutView(isPresented: $showActiveWorkout)
                .environmentObject(navigator)
        }
        .sheet(isPresented: $showCreateRoutine) {
            CreateRoutineSheet()
        }
        .onAppear {
            Task { await store.refreshHealthData() }
            Task { await store.refreshFromBackend() }
        }
    }

    // MARK: - Training Plan Card

    private var trainingPlanCard: some View {
        Button { showTrainingPlan = true } label: {
            HStack(spacing: 14) {
                ZStack {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(palette.accent.opacity(0.15)).frame(width: 40, height: 40)
                    Image(systemName: "calendar.badge.clock").font(.system(size: 18, weight: .semibold)).foregroundStyle(palette.accent)
                }
                VStack(alignment: .leading, spacing: 3) {
                    Text("Training Plan").font(.system(size: 14, weight: .bold, design: .rounded)).foregroundStyle(.primary)
                    Text(trainingPlanSubtitle).font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                }
                Spacer(minLength: 12)
                Image(systemName: "chevron.right").font(.system(size: 12, weight: .semibold)).foregroundStyle(.tertiary)
            }
            .padding(14)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    private var trainingPlanSubtitle: String {
        switch store.planStatus {
        case .none:    return "Not started — tap to set up"
        case .testing: return "Testing week in progress"
        case .active:  return "\(store.scheduledWorkouts.filter { $0.status == "PLANNED" }.count) workouts scheduled"
        }
    }

    // MARK: - Readiness Card

    private var readinessCard: some View {
        let snap = store.healthSnapshot
        let r = snap.readiness
        return VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: r.icon)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(r.color)
                Text(r.label)
                    .font(.system(size: 16, weight: .bold, design: .rounded))
                Spacer()
                Text("HealthKit")
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                    .foregroundStyle(.tertiary)
            }

            HStack(spacing: 0) {
                readinessStat(label: "Resting HR",
                              value: snap.restingHR.map { "\(Int($0))" } ?? "—",
                              unit: "bpm",
                              icon: "heart.fill",
                              color: Color(red: 0.90, green: 0.25, blue: 0.30))
                Divider().frame(height: 36)
                readinessStat(label: "HRV",
                              value: snap.hrv.map { "\(Int($0))" } ?? "—",
                              unit: "ms",
                              icon: "waveform.path.ecg",
                              color: Color(red: 0.25, green: 0.65, blue: 0.95))
                Divider().frame(height: 36)
                readinessStat(label: "Sleep",
                              value: snap.sleepHours.map { String(format: "%.1f", $0) } ?? "—",
                              unit: "hrs",
                              icon: "moon.fill",
                              color: Color(red: 0.55, green: 0.35, blue: 0.90))
                Divider().frame(height: 36)
                readinessStat(label: "Steps",
                              value: snap.todaySteps > 0 ? "\(snap.todaySteps / 1000)k" : "—",
                              unit: "today",
                              icon: "figure.walk",
                              color: Color(red: 0.25, green: 0.75, blue: 0.45))
            }

            if !store.healthKitAuthorized {
                Button {
                    Task { await store.requestHealthKitAuthorization() }
                } label: {
                    Label("Connect Apple Health", systemImage: "heart.fill")
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                        .foregroundStyle(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 10)
                        .background(Color(red: 0.90, green: 0.25, blue: 0.30), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(16)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func readinessStat(label: String, value: String, unit: String, icon: String, color: Color) -> some View {
        VStack(spacing: 4) {
            Image(systemName: icon)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(color)
            HStack(alignment: .firstTextBaseline, spacing: 1) {
                Text(value).font(.system(size: 18, weight: .bold, design: .rounded))
                Text(unit).font(.system(size: 10, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
            }
            Text(label).font(.system(size: 10, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
    }

    // MARK: - Health Metrics Section

    private var healthMetricsSection: some View {
        let snap = store.healthSnapshot
        return VStack(alignment: .leading, spacing: 14) {
            sleepCard(snap: snap)
            todayActivityCard(snap: snap)
            if snap.rhrHistory.count >= 2 {
                trendChartCard(
                    title: "Resting HR — 30 days",
                    points: snap.rhrHistory,
                    unitLabel: "bpm",
                    lineColor: Color(red: 0.90, green: 0.25, blue: 0.30)
                )
            }
            weightTrendCard(snap: snap)
            vo2MaxCard(snap: snap)
        }
    }

    // MARK: Sleep Card

    private func sleepCard(snap: HealthSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionHeader("Sleep")
            VStack(alignment: .leading, spacing: 12) {
                if let breakdown = snap.sleepBreakdown {
                    HStack(alignment: .firstTextBaseline, spacing: 4) {
                        Text(String(format: "%.1f", breakdown.total))
                            .font(.system(size: 32, weight: .bold, design: .rounded))
                        Text("hrs")
                            .font(.system(size: 14, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                            .padding(.bottom, 2)
                        Spacer()
                        Image(systemName: "moon.fill")
                            .font(.system(size: 18))
                            .foregroundStyle(Color(red: 0.55, green: 0.35, blue: 0.90))
                    }
                    // Segmented bar
                    GeometryReader { geo in
                        HStack(spacing: 2) {
                            let total = max(breakdown.total, 0.01)
                            RoundedRectangle(cornerRadius: 4, style: .continuous)
                                .fill(Color(red: 0.35, green: 0.55, blue: 0.95))
                                .frame(width: geo.size.width * CGFloat(breakdown.core / total))
                            RoundedRectangle(cornerRadius: 4, style: .continuous)
                                .fill(Color(red: 0.55, green: 0.25, blue: 0.85))
                                .frame(width: geo.size.width * CGFloat(breakdown.deep / total))
                            RoundedRectangle(cornerRadius: 4, style: .continuous)
                                .fill(Color(red: 0.20, green: 0.75, blue: 0.45))
                                .frame(width: geo.size.width * CGFloat(breakdown.rem / total))
                        }
                    }
                    .frame(height: 10)
                    .clipShape(Capsule())
                    HStack(spacing: 0) {
                        sleepStageStat(label: "Core", hours: breakdown.core, color: Color(red: 0.35, green: 0.55, blue: 0.95))
                        Divider().frame(height: 28)
                        sleepStageStat(label: "Deep", hours: breakdown.deep, color: Color(red: 0.55, green: 0.25, blue: 0.85))
                        Divider().frame(height: 28)
                        sleepStageStat(label: "REM", hours: breakdown.rem, color: Color(red: 0.20, green: 0.75, blue: 0.45))
                    }
                } else {
                    HStack(spacing: 10) {
                        Image(systemName: "moon.zzz.fill")
                            .font(.system(size: 20))
                            .foregroundStyle(Color(red: 0.55, green: 0.35, blue: 0.90).opacity(0.5))
                        Text("No sleep data from last night")
                            .font(.system(size: 14, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                }
            }
            .padding(16)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }

    private func sleepStageStat(label: String, hours: Double, color: Color) -> some View {
        VStack(spacing: 3) {
            Circle().fill(color).frame(width: 8, height: 8)
            Text(String(format: "%.1fh", hours))
                .font(.system(size: 14, weight: .bold, design: .rounded))
            Text(label)
                .font(.system(size: 10, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 6)
    }

    // MARK: Today Activity Card

    private func todayActivityCard(snap: HealthSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionHeader("Today")
            HStack(spacing: 0) {
                VStack(spacing: 6) {
                    Image(systemName: "flame.fill")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(Color(red: 0.95, green: 0.45, blue: 0.10))
                    HStack(alignment: .firstTextBaseline, spacing: 2) {
                        Text(snap.activeCalories.map { "\(Int($0))" } ?? "—")
                            .font(.system(size: 20, weight: .bold, design: .rounded))
                        Text("kcal").font(.system(size: 10, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                    }
                    Text("Active Cal").font(.system(size: 10, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
                Divider().frame(height: 44)
                VStack(spacing: 6) {
                    Image(systemName: "figure.walk")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(Color(red: 0.25, green: 0.75, blue: 0.45))
                    HStack(alignment: .firstTextBaseline, spacing: 2) {
                        Text(snap.todaySteps > 0 ? "\(snap.todaySteps)" : "—")
                            .font(.system(size: 20, weight: .bold, design: .rounded))
                        Text("steps").font(.system(size: 10, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                    }
                    Text("Steps").font(.system(size: 10, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
            }
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }

    // MARK: Trend Chart (reusable for RHR and Weight)

    private func trendChartCard(title: String, points: [(Date, Double)], unitLabel: String, lineColor: Color) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionHeader(title)
            VStack(alignment: .leading, spacing: 8) {
                if points.count >= 2 {
                    let values = points.map(\.1)
                    let minVal = values.min() ?? 0
                    let maxVal = max(values.max() ?? 1, minVal + 1)
                    HStack(alignment: .top, spacing: 6) {
                        VStack(alignment: .trailing, spacing: 0) {
                            Text(String(format: "%.0f", maxVal))
                                .font(.system(size: 10, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(String(format: "%.0f", minVal))
                                .font(.system(size: 10, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                        .frame(width: 30, height: 120)
                        GeometryReader { geo in
                            ZStack {
                                lineChartPath(points: points, minVal: minVal, maxVal: maxVal, size: geo.size)
                                    .stroke(lineColor, style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
                                // Dot at last point
                                let last = points.last!
                                let allDates = points.map(\.0)
                                let minDate = allDates.min()!.timeIntervalSinceReferenceDate
                                let maxDate = allDates.max()!.timeIntervalSinceReferenceDate
                                let xFrac = maxDate > minDate
                                    ? CGFloat((last.0.timeIntervalSinceReferenceDate - minDate) / (maxDate - minDate))
                                    : 1.0
                                let yFrac = CGFloat(1.0 - (last.1 - minVal) / max(maxVal - minVal, 0.01))
                                Circle()
                                    .fill(lineColor)
                                    .frame(width: 7, height: 7)
                                    .position(x: xFrac * geo.size.width, y: yFrac * geo.size.height)
                            }
                        }
                        .frame(height: 120)
                    }
                    HStack {
                        Text("\(unitLabel)")
                            .font(.system(size: 10, weight: .medium, design: .rounded))
                            .foregroundStyle(.tertiary)
                        Spacer()
                        Text(String(format: "Latest: %.0f \(unitLabel)", points.last?.1 ?? 0))
                            .font(.system(size: 11, weight: .semibold, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                } else {
                    Text("Not enough data yet")
                        .font(.system(size: 13, design: .rounded))
                        .foregroundStyle(.secondary)
                        .padding(.vertical, 8)
                }
            }
            .padding(16)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }

    private func lineChartPath(points: [(Date, Double)], minVal: Double, maxVal: Double, size: CGSize) -> Path {
        let allDates = points.map { $0.0.timeIntervalSinceReferenceDate }
        let minDate = allDates.min() ?? 0
        let maxDate = allDates.max() ?? 1
        let dateRange = max(maxDate - minDate, 1)
        let valRange = max(maxVal - minVal, 0.01)
        return Path { path in
            for (i, point) in points.enumerated() {
                let x = CGFloat((point.0.timeIntervalSinceReferenceDate - minDate) / dateRange) * size.width
                let y = CGFloat(1.0 - (point.1 - minVal) / valRange) * size.height
                if i == 0 { path.move(to: CGPoint(x: x, y: y)) }
                else { path.addLine(to: CGPoint(x: x, y: y)) }
            }
        }
    }

    // MARK: Weight Trend Card

    private var showWeightSheet: Bool { false } // placeholder; sheet triggered via activeSheet

    private func weightTrendCard(snap: HealthSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionHeader("Body Weight — 90 days")
            VStack(alignment: .leading, spacing: 8) {
                if snap.weightHistory.count >= 2 {
                    let points = snap.weightHistory
                    let values = points.map(\.1)
                    let minVal = values.min() ?? 0
                    let maxVal = max(values.max() ?? 1, minVal + 1)
                    HStack(alignment: .top, spacing: 6) {
                        VStack(alignment: .trailing, spacing: 0) {
                            Text(String(format: "%.0f", maxVal))
                                .font(.system(size: 10, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(String(format: "%.0f", minVal))
                                .font(.system(size: 10, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                        .frame(width: 30, height: 120)
                        GeometryReader { geo in
                            ZStack {
                                lineChartPath(points: points, minVal: minVal, maxVal: maxVal, size: geo.size)
                                    .stroke(palette.accent, style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
                                let last = points.last!
                                let allDates = points.map(\.0)
                                let minDate = allDates.min()!.timeIntervalSinceReferenceDate
                                let maxDate = allDates.max()!.timeIntervalSinceReferenceDate
                                let xFrac = maxDate > minDate
                                    ? CGFloat((last.0.timeIntervalSinceReferenceDate - minDate) / (maxDate - minDate))
                                    : 1.0
                                let yFrac = CGFloat(1.0 - (last.1 - minVal) / max(maxVal - minVal, 0.01))
                                Circle()
                                    .fill(palette.accent)
                                    .frame(width: 7, height: 7)
                                    .position(x: xFrac * geo.size.width, y: yFrac * geo.size.height)
                            }
                        }
                        .frame(height: 120)
                    }
                    HStack {
                        if let latest = snap.weightHistory.last?.1 {
                            Text(String(format: "Latest: %.1f kg", latest))
                                .font(.system(size: 11, weight: .semibold, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button {
                            activeSheet = .bodyweightEntry { kg in
                                Task { await store.saveBodyMass(kg) }
                            }
                        } label: {
                            Text("Log Weight")
                                .font(.system(size: 12, weight: .semibold, design: .rounded))
                                .foregroundStyle(palette.accent)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 6)
                                .background(palette.accent.opacity(0.12), in: Capsule())
                        }
                        .buttonStyle(.plain)
                    }
                } else {
                    HStack {
                        Text("No weight data yet")
                            .font(.system(size: 13, design: .rounded))
                            .foregroundStyle(.secondary)
                        Spacer()
                        Button {
                            activeSheet = .bodyweightEntry { kg in
                                Task { await store.saveBodyMass(kg) }
                            }
                        } label: {
                            Text("Log Weight")
                                .font(.system(size: 12, weight: .semibold, design: .rounded))
                                .foregroundStyle(palette.accent)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 6)
                                .background(palette.accent.opacity(0.12), in: Capsule())
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.vertical, 4)
                }
            }
            .padding(16)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }

    // MARK: VO2 Max Card

    private func vo2MaxCard(snap: HealthSnapshot) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionHeader("Cardio Fitness")
            HStack(spacing: 16) {
                Image(systemName: "lungs.fill")
                    .font(.system(size: 28, weight: .semibold))
                    .foregroundStyle(Color(red: 0.20, green: 0.55, blue: 0.95))
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline, spacing: 4) {
                        Text(snap.vo2Max.map { String(format: "%.1f", $0) } ?? "—")
                            .font(.system(size: 26, weight: .bold, design: .rounded))
                        if snap.vo2Max != nil {
                            Text("ml/kg/min")
                                .font(.system(size: 11, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                    }
                    Text("VO\u{2082} Max (Apple Health)")
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }
            .padding(16)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }

    // MARK: Section Header Helper

    private func sectionHeader(_ title: String) -> some View {
        Text(title)
            .font(.system(size: 13, weight: .semibold, design: .rounded))
            .foregroundStyle(.secondary)
            .padding(.leading, 4)
    }

    // MARK: - Start Workout

    private var startWorkoutCard: some View {
        HStack(spacing: 14) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Start Workout")
                    .font(.system(size: 18, weight: .bold, design: .rounded))
                Text("\(store.totalWorkoutsThisWeek()) sessions this week")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button {
                store.startWorkout()
                showActiveWorkout = true
            } label: {
                Image(systemName: "play.fill")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: 48, height: 48)
                    .background(palette.accent, in: Circle())
            }
            .buttonStyle(.plain)
        }
        .padding(16)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    // MARK: - Routines

    private var routinesSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Routines")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)
                    .padding(.leading, 4)
                Spacer()
                Button { showCreateRoutine = true } label: {
                    Image(systemName: "plus.circle.fill")
                        .font(.system(size: 18))
                        .foregroundStyle(palette.accent)
                }
                .buttonStyle(.plain)
            }

            if store.routines.isEmpty {
                Button { showCreateRoutine = true } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "doc.badge.plus")
                            .font(.system(size: 20))
                            .foregroundStyle(palette.accent.opacity(0.6))
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Create a Routine")
                                .font(.system(size: 14, weight: .semibold, design: .rounded))
                            Text("Plan your workout before you start")
                                .font(.system(size: 12, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                    }
                    .padding(16)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
                }
                .buttonStyle(.plain)
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(store.routines.enumerated()), id: \.element.id) { idx, routine in
                        routineRow(routine: routine)
                        if idx < store.routines.count - 1 { Divider().padding(.leading, 14) }
                    }
                }
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
            }
        }
    }

    private func routineRow(routine: WorkoutRoutine) -> some View {
        HStack(spacing: 14) {
            VStack(alignment: .leading, spacing: 3) {
                Text(routine.name)
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                Text("\(routine.exercises.count) exercises")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button {
                store.startWorkout(from: routine)
                showActiveWorkout = true
            } label: {
                Image(systemName: "play.fill")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: 36, height: 36)
                    .background(palette.accent, in: Circle())
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .contextMenu {
            Button(role: .destructive) {
                store.deleteRoutine(id: routine.id)
            } label: {
                Label("Delete", systemImage: "trash")
            }
        }
    }

    // MARK: - Recent Sessions

    private var recentSessionsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Recent Sessions")
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .padding(.leading, 4)

            VStack(spacing: 0) {
                ForEach(Array(store.recentSessions(count: 5).enumerated()), id: \.element.id) { idx, session in
                    sessionRow(session: session)
                    if idx < min(4, store.sessions.count - 1) {
                        Divider().padding(.leading, 14)
                    }
                }
            }
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }

    private func sessionRow(session: WorkoutSession) -> some View {
        Button { activeSheet = .sessionDetail(session) } label: {
            HStack(spacing: 14) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(sessionTitle(session))
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                        .foregroundStyle(.primary)
                    Text("\(session.totalSets) sets · \(session.durationMinutes)min")
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 4) {
                    Text(session.date, style: .date)
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                    if session.hkWorkoutUUID != nil {
                        Image(systemName: "heart.fill")
                            .font(.system(size: 10))
                            .foregroundStyle(Color(red: 0.90, green: 0.25, blue: 0.30))
                    }
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
        }
        .buttonStyle(.plain)
    }

    private func sessionTitle(_ session: WorkoutSession) -> String {
        let names = session.exercises.compactMap { we in
            store.exercise(id: we.exerciseID)?.name
        }
        if names.isEmpty { return "Workout" }
        if names.count == 1 { return names[0] }
        return "\(names[0]) + \(names.count - 1) more"
    }

    // MARK: - Progression Section

    private var progressionSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Progressions")
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .padding(.leading, 4)

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 12) {
                    ForEach(store.progressionPaths) { path in
                        progressionCard(path: path)
                    }
                }
                .padding(.horizontal, 1)
            }
        }
    }

    private func progressionCard(path: ProgressionPath) -> some View {
        let current = store.currentProgressionStep(in: path)
        let stepIndex = current?.stepIndex ?? 0
        let total = path.exerciseIDs.count
        let fraction = total > 1 ? Double(stepIndex) / Double(total - 1) : 1.0

        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                ZStack {
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(path.category.color.opacity(0.15))
                        .frame(width: 32, height: 32)
                    Image(systemName: path.category.icon)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(path.category.color)
                }
                Spacer()
                Text("\(stepIndex + 1)/\(total)")
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .foregroundStyle(.secondary)
            }

            Text(path.name)
                .font(.system(size: 14, weight: .bold, design: .rounded))

            Text(current?.exercise.name ?? "Complete!")
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
                .lineLimit(1)

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(path.category.color.opacity(0.15)).frame(height: 5)
                    Capsule().fill(path.category.color).frame(width: geo.size.width * fraction, height: 5)
                }
            }
            .frame(height: 5)
        }
        .padding(14)
        .frame(width: 170)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    // MARK: - Weekly Volume

    private var weeklyVolumeSection: some View {
        let volume = store.weeklyVolume()
        let sorted = volume.sorted { $0.value > $1.value }.prefix(6)
        guard !sorted.isEmpty else { return AnyView(EmptyView()) }
        let max = sorted.first?.value ?? 1

        return AnyView(VStack(alignment: .leading, spacing: 8) {
            Text("This Week's Volume")
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .padding(.leading, 4)

            VStack(spacing: 10) {
                ForEach(sorted, id: \.key) { muscle, reps in
                    HStack(spacing: 10) {
                        Text(muscle.displayName)
                            .font(.system(size: 13, weight: .semibold, design: .rounded))
                            .frame(width: 90, alignment: .leading)
                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                Capsule().fill(palette.accent.opacity(0.12)).frame(height: 8)
                                Capsule().fill(palette.accent).frame(width: geo.size.width * CGFloat(reps) / CGFloat(max), height: 8)
                            }
                        }
                        .frame(height: 8)
                        Text("\(reps)")
                            .font(.system(size: 12, weight: .bold, design: .rounded))
                            .foregroundStyle(.secondary)
                            .frame(width: 36, alignment: .trailing)
                    }
                }
            }
            .padding(16)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
        })
    }

    // MARK: - Milestones

    private var milestonesSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Milestones")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)
                    .padding(.leading, 4)
                Spacer()
                Button { activeSheet = .addMilestone } label: {
                    Image(systemName: "plus.circle.fill")
                        .font(.system(size: 18))
                        .foregroundStyle(palette.accent)
                }
                .buttonStyle(.plain)
            }

            VStack(spacing: 0) {
                ForEach(Array(store.milestones.prefix(5).enumerated()), id: \.element.id) { idx, m in
                    milestoneRow(m)
                    if idx < min(4, store.milestones.count - 1) {
                        Divider().padding(.leading, 14)
                    }
                }
            }
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }

    private func milestoneRow(_ m: FitnessMilestone) -> some View {
        HStack(spacing: 14) {
            Image(systemName: "trophy.fill")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Color(red: 0.90, green: 0.65, blue: 0.10))
                .frame(width: 28)
            VStack(alignment: .leading, spacing: 3) {
                Text(m.title)
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                if !m.notes.isEmpty {
                    Text(m.notes).font(.system(size: 12, design: .rounded)).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            Spacer()
            Text(m.date, style: .date)
                .font(.system(size: 11, weight: .medium, design: .rounded))
                .foregroundStyle(.tertiary)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }

    // MARK: - Sheet Router

    @ViewBuilder
    private func sheetContent(_ sheet: FitnessSheet) -> some View {
        switch sheet {
        case .exerciseDetail(let ex):
            ExerciseDetailSheet(exercise: ex)
        case .addMilestone:
            AddMilestoneSheet()
        case .addExercise(let binding):
            AddExerciseToWorkoutSheet(session: binding)
        case .bodyweightEntry(let onSet):
            BodyweightEntrySheet(onSet: onSet)
        case .sessionDetail(let s):
            SessionDetailSheet(session: s)
        }
    }
}

// MARK: - Active Workout

struct ActiveWorkoutView: View {
    @EnvironmentObject private var navigator: AppNavigator
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = FitnessStore.shared
    @Binding var isPresented: Bool

    @State private var session: WorkoutSession = WorkoutSession()
    @State private var startDate = Date()
    @State private var showExercisePicker = false
    @State private var showCancelAlert = false
    @State private var showSaveRoutine = false
    @State private var viewingExercise: Exercise?
    @State private var timer: Timer?
    @State private var elapsedSeconds: Int = 0
    @AppStorage("fitness.lastRestSeconds") private var lastRestSeconds: Int = 60

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    timerHeader

                    if session.exercises.isEmpty {
                        emptyWorkoutState
                    } else {
                        ForEach($session.exercises) { $we in
                            workoutExerciseCard(we: $we)
                        }
                    }

                    addExerciseButton

                    if !session.exercises.isEmpty {
                        finishButton
                    }

                    Color.clear.frame(height: 20)
                }
                .padding(14)
            }
            .background(LinearGradient(colors: [palette.backgroundTop, palette.backgroundBottom], startPoint: .top, endPoint: .bottom).ignoresSafeArea())
            .navigationTitle("Workout")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { showCancelAlert = true }
                }
                ToolbarItem(placement: .primaryAction) {
                    if !session.exercises.isEmpty {
                        Button { showSaveRoutine = true } label: {
                            Image(systemName: "bookmark")
                        }
                    }
                }
            }
            .alert("Cancel Workout?", isPresented: $showCancelAlert) {
                Button("Keep Going", role: .cancel) {}
                Button("Discard", role: .destructive) {
                    store.cancelSession()
                    isPresented = false
                }
            } message: {
                Text("Your progress will not be saved.")
            }
            .sheet(isPresented: $showExercisePicker) {
                AddExerciseToWorkoutSheet(session: $session)
            }
            .sheet(isPresented: $showSaveRoutine) {
                SaveRoutineSheet(session: session)
            }
            .sheet(item: $viewingExercise) { ex in
                ExerciseDetailSheet(exercise: ex)
            }
        }
        .onAppear {
            session = store.activeSession ?? WorkoutSession()
            startDate = Date()
            timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { _ in
                elapsedSeconds = Int(Date().timeIntervalSince(startDate))
            }
        }
        .onDisappear { timer?.invalidate() }
    }

    private var timerHeader: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(formatElapsed(elapsedSeconds))
                    .font(.system(size: 32, weight: .bold, design: .rounded).monospacedDigit())
                Text("Elapsed").font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text("\(session.totalSets)").font(.system(size: 32, weight: .bold, design: .rounded))
                Text("Sets Done").font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private var emptyWorkoutState: some View {
        VStack(spacing: 12) {
            Image(systemName: "figure.strengthtraining.functional")
                .font(.system(size: 40))
                .foregroundStyle(palette.accent.opacity(0.5))
            Text("No exercises yet")
                .font(.system(size: 16, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Text("Tap Add Exercise to get started")
                .font(.system(size: 13, design: .rounded))
                .foregroundStyle(.tertiary)
        }
        .frame(maxWidth: .infinity)
        .padding(48)
    }

    private func workoutExerciseCard(we: Binding<WorkoutExercise>) -> some View {
        let ex = store.exercise(id: we.wrappedValue.exerciseID)
        let isTimed = ex?.isTimedExercise ?? false
        return VStack(alignment: .leading, spacing: 12) {
            HStack {
                if let ex = ex {
                    ZStack {
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .fill(ex.category.color.opacity(0.15))
                            .frame(width: 32, height: 32)
                        Image(systemName: ex.category.icon)
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(ex.category.color)
                    }
                }
                Button { viewingExercise = ex } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 4) {
                            Text(ex?.name ?? "Unknown").font(.system(size: 15, weight: .bold, design: .rounded))
                            Image(systemName: "info.circle").font(.system(size: 12)).foregroundStyle(palette.accent.opacity(0.7))
                        }
                        if let pb = ex.flatMap({ store.personalBest(for: $0.id) }) {
                            Text("PB: \(pb.displayValue)")
                                .font(.system(size: 11, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .buttonStyle(.plain)
                Spacer()
                Button {
                    if let idx = session.exercises.firstIndex(where: { $0.id == we.wrappedValue.id }) {
                        let newSet = isTimed
                            ? WorkoutSet(durationSeconds: ex?.defaultDurationSeconds ?? 30)
                            : WorkoutSet(reps: ex?.defaultReps ?? 10)
                        session.exercises[idx].sets.append(newSet)
                    }
                } label: {
                    Image(systemName: "plus.circle").font(.system(size: 18)).foregroundStyle(palette.accent)
                }
                .buttonStyle(.plain)
            }

            Divider()

            ForEach(we.wrappedValue.sets.indices, id: \.self) { idx in
                setRow(
                    set: Binding(
                        get: { we.wrappedValue.sets[idx] },
                        set: { we.wrappedValue.sets[idx] = $0 }
                    ),
                    isTimed: isTimed,
                    onDelete: {
                        if let exIdx = session.exercises.firstIndex(where: { $0.id == we.wrappedValue.id }) {
                            session.exercises[exIdx].sets.remove(at: idx)
                        }
                    }
                )
                if idx < we.wrappedValue.sets.count - 1 { Divider().padding(.leading, 34) }
            }
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func setRow(set: Binding<WorkoutSet>, isTimed: Bool, onDelete: @escaping () -> Void) -> some View {
        VStack(spacing: 6) {
            HStack(spacing: 10) {
                Button {
                    set.wrappedValue.isCompleted.toggle()
                } label: {
                    Image(systemName: set.wrappedValue.isCompleted ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: 22))
                        .foregroundStyle(set.wrappedValue.isCompleted ? palette.positive : palette.border)
                }
                .buttonStyle(.plain)

                if isTimed {
                    Stepper(value: Binding(
                        get: { set.wrappedValue.durationSeconds ?? 30 },
                        set: { set.wrappedValue.durationSeconds = $0 }
                    ), in: 5...300, step: 5) {
                        Text("\(set.wrappedValue.durationSeconds ?? 30)s")
                            .font(.system(size: 16, weight: .semibold, design: .rounded).monospacedDigit())
                    }
                } else {
                    Stepper(value: Binding(
                        get: { set.wrappedValue.reps ?? 10 },
                        set: { set.wrappedValue.reps = $0 }
                    ), in: 1...999) {
                        Text("\(set.wrappedValue.reps ?? 10) reps")
                            .font(.system(size: 16, weight: .semibold, design: .rounded).monospacedDigit())
                    }
                }

                Spacer(minLength: 4)
                Button(action: onDelete) {
                    Image(systemName: "minus.circle").font(.system(size: 18)).foregroundStyle(Color(red: 0.85, green: 0.20, blue: 0.25))
                }
                .buttonStyle(.plain)
            }

            HStack(spacing: 8) {
                Image(systemName: "timer").font(.system(size: 11)).foregroundStyle(.secondary)
                Text("Rest:")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                Stepper(value: Binding(
                    get: { set.wrappedValue.restSeconds ?? lastRestSeconds },
                    set: { set.wrappedValue.restSeconds = $0; lastRestSeconds = $0 }
                ), in: 0...600, step: 15) {
                    Text(set.wrappedValue.restSeconds.map { "\($0)s" } ?? "–")
                        .font(.system(size: 12, weight: .semibold, design: .rounded).monospacedDigit())
                        .foregroundStyle(.secondary)
                }
                if set.wrappedValue.restSeconds == nil {
                    Button {
                        set.wrappedValue.restSeconds = lastRestSeconds
                    } label: {
                        Text("Use \(lastRestSeconds)s")
                            .font(.system(size: 11, weight: .semibold, design: .rounded))
                            .foregroundStyle(palette.accent)
                            .padding(.horizontal, 8).padding(.vertical, 3)
                            .background(palette.accent.opacity(0.10), in: Capsule())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.leading, 32)
        }
    }

    private var addExerciseButton: some View {
        Button { showExercisePicker = true } label: {
            Label("Add Exercise", systemImage: "plus")
                .font(.system(size: 15, weight: .semibold, design: .rounded))
                .foregroundStyle(palette.accent)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(palette.accent.opacity(0.10), in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.accent.opacity(0.25), lineWidth: 1))
        }
        .buttonStyle(.plain)
    }

    private var finishButton: some View {
        Button {
            let minutes = max(1, elapsedSeconds / 60)
            store.finishSession(session, durationMinutes: minutes)
            isPresented = false
        } label: {
            Text("Finish Workout")
                .font(.system(size: 16, weight: .bold, design: .rounded))
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(palette.accent, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        }
        .buttonStyle(.plain)
    }

    private func formatElapsed(_ seconds: Int) -> String {
        let m = seconds / 60
        let s = seconds % 60
        return String(format: "%d:%02d", m, s)
    }
}

// MARK: - Save Routine Sheet

private struct SaveRoutineSheet: View {
    @ObservedObject private var store = FitnessStore.shared
    @Environment(\.dismiss) private var dismiss
    let session: WorkoutSession

    @State private var name: String = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("e.g. Push Day A, Upper Body", text: $name)
                        .onAppear {
                            name = session.exercises.compactMap { store.exercise(id: $0.exerciseID)?.name }.prefix(2).joined(separator: " + ")
                        }
                } header: {
                    Text("Routine Name")
                }
                Section {
                    ForEach(session.exercises) { we in
                        if let ex = store.exercise(id: we.exerciseID) {
                            Label("\(ex.name) — \(we.sets.count) sets", systemImage: ex.category.icon)
                                .font(.system(size: 14, design: .rounded))
                        }
                    }
                } header: {
                    Text("Exercises")
                }
            }
            .navigationTitle("Save as Routine")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        store.saveAsRoutine(name: name, from: session)
                        dismiss()
                    }
                    .disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
        }
    }
}

// MARK: - Routine Manager Sheet

private struct RoutineManagerSheet: View {
    @ObservedObject private var store = FitnessStore.shared
    @Environment(\.dismiss) private var dismiss
    @State private var showCreate = false

    var body: some View {
        NavigationStack {
            List {
                ForEach(store.routines) { routine in
                    HStack(spacing: 12) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(routine.name).font(.system(size: 14, weight: .semibold, design: .rounded))
                            Text("\(routine.exercises.count) exercises")
                                .font(.system(size: 12, design: .rounded)).foregroundStyle(.secondary)
                        }
                        Spacer()
                    }
                }
                .onDelete { idx in idx.map { store.routines[$0].id }.forEach { store.deleteRoutine(id: $0) } }
            }
            .listStyle(.insetGrouped)
            .overlay {
                if store.routines.isEmpty {
                    ContentUnavailableView("No Routines", systemImage: "list.clipboard", description: Text("Tap + to build a routine."))
                }
            }
            .navigationTitle("Routines")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } }
                ToolbarItem(placement: .primaryAction) {
                    Button { showCreate = true } label: { Image(systemName: "plus") }
                }
            }
            .sheet(isPresented: $showCreate) { CreateRoutineSheet() }
        }
    }
}

// MARK: - Create Routine Sheet

private struct CreateRoutineSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = FitnessStore.shared
    @Environment(\.dismiss) private var dismiss

    @State private var name: String = ""
    @State private var draft = WorkoutSession()
    @State private var showAddExercise = false

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    TextField("e.g. Push Day A, Full Body", text: $name)
                } header: { Text("Routine Name") }

                Section {
                    ForEach(draft.exercises.indices, id: \.self) { idx in
                        let we = draft.exercises[idx]
                        if let ex = store.exercise(id: we.exerciseID) {
                            HStack(spacing: 12) {
                                Image(systemName: ex.category.icon)
                                    .font(.system(size: 14, weight: .semibold))
                                    .foregroundStyle(ex.category.color)
                                    .frame(width: 28)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(ex.name).font(.system(size: 14, weight: .semibold, design: .rounded))
                                    Text("\(we.sets.count) sets").font(.system(size: 12, design: .rounded)).foregroundStyle(.secondary)
                                }
                                Spacer()
                                Stepper("", value: Binding(
                                    get: { draft.exercises[idx].sets.count },
                                    set: { target in
                                        let current = draft.exercises[idx].sets.count
                                        if target > current {
                                            let newSet = ex.isTimedExercise
                                                ? WorkoutSet(durationSeconds: ex.defaultDurationSeconds)
                                                : WorkoutSet(reps: ex.defaultReps)
                                            draft.exercises[idx].sets.append(newSet)
                                        } else if target < current && current > 1 {
                                            draft.exercises[idx].sets.removeLast()
                                        }
                                    }
                                ), in: 1...20)
                                .labelsHidden()
                            }
                        }
                    }
                    .onDelete { idx in draft.exercises.remove(atOffsets: idx) }
                    .onMove { from, to in draft.exercises.move(fromOffsets: from, toOffset: to) }

                    Button { showAddExercise = true } label: {
                        Label("Add Exercise", systemImage: "plus")
                            .foregroundStyle(palette.accent)
                    }
                } header: { Text("Exercises") }
            }
            .environment(\.editMode, .constant(.active))
            .navigationTitle("New Routine")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        store.saveAsRoutine(name: name, from: draft)
                        dismiss()
                    }
                    .disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || draft.exercises.isEmpty)
                }
            }
            .sheet(isPresented: $showAddExercise) {
                AddExerciseToWorkoutSheet(session: $draft)
            }
        }
    }
}

// MARK: - Exercise Detail Sheet

struct ExerciseDetailSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = FitnessStore.shared
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL

    let exercise: Exercise
    @State private var showAllInstructions = false

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    headerSection
                    muscleSection
                    progressionPathSection
                    instructionsSection
                    videoSection
                    historySection
                }
                .padding(16)
                .padding(.bottom, 24)
            }
            .background(LinearGradient(colors: [palette.backgroundTop, palette.backgroundBottom], startPoint: .top, endPoint: .bottom).ignoresSafeArea())
            .navigationTitle(exercise.name)
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }

    private var headerSection: some View {
        HStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(exercise.category.color.opacity(0.15))
                    .frame(width: 56, height: 56)
                Image(systemName: exercise.category.icon)
                    .font(.system(size: 24, weight: .semibold))
                    .foregroundStyle(exercise.category.color)
            }
            VStack(alignment: .leading, spacing: 6) {
                Text(exercise.category.displayName)
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(exercise.category.color)
                Text(exercise.difficulty.displayName)
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(exercise.difficulty.color, in: Capsule())
            }
            Spacer()
            if let pb = store.personalBest(for: exercise.id) {
                VStack(alignment: .trailing, spacing: 2) {
                    Text(pb.displayValue)
                        .font(.system(size: 18, weight: .bold, design: .rounded))
                    Text("Personal Best")
                        .font(.system(size: 10, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private var muscleSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Muscles")
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            FlowLayout(spacing: 8) {
                ForEach(exercise.muscleGroups, id: \.self) { muscle in
                    Text(muscle.displayName)
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundStyle(exercise.category.color)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(exercise.category.color.opacity(0.12), in: Capsule())
                }
            }
        }
    }

    private var instructionsSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("How to Perform")
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 12) {
                let steps = showAllInstructions ? exercise.instructions : Array(exercise.instructions.prefix(3))
                ForEach(Array(steps.enumerated()), id: \.offset) { idx, step in
                    HStack(alignment: .top, spacing: 12) {
                        Text("\(idx + 1)")
                            .font(.system(size: 13, weight: .bold, design: .rounded))
                            .foregroundStyle(.white)
                            .frame(width: 24, height: 24)
                            .background(exercise.category.color, in: Circle())
                        Text(step)
                            .font(.system(size: 14, weight: .regular, design: .rounded))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                if exercise.instructions.count > 3 {
                    Button {
                        withAnimation(.spring(duration: 0.3)) { showAllInstructions.toggle() }
                    } label: {
                        Text(showAllInstructions ? "Show Less" : "Show All \(exercise.instructions.count) Steps")
                            .font(.system(size: 13, weight: .semibold, design: .rounded))
                            .foregroundStyle(palette.accent)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(14)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }

    @ViewBuilder
    private var videoSection: some View {
        if let urlString = exercise.videoURL, let url = URL(string: urlString) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Tutorial")
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)
                Button { openURL(url) } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "play.rectangle.fill")
                            .font(.system(size: 24))
                            .foregroundStyle(Color(red: 0.90, green: 0.20, blue: 0.20))
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Watch Tutorial")
                                .font(.system(size: 15, weight: .bold, design: .rounded))
                            Text(urlString)
                                .font(.system(size: 11, design: .rounded))
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                        Spacer()
                        Image(systemName: "arrow.up.right").font(.system(size: 13)).foregroundStyle(.tertiary)
                    }
                    .padding(14)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
                }
                .buttonStyle(.plain)
            }
        }
    }

    private var progressionPathSection: some View {
        Group {
            if let pathID = exercise.progressionPathID,
               let path = store.progressionPaths.first(where: { $0.id == pathID }),
               let order = exercise.progressionOrder {
                let total = path.exerciseIDs.count
                let fraction = total > 1 ? Double(order) / Double(total - 1) : 1.0
                let nextEx = order + 1 < path.exerciseIDs.count ? store.exercise(id: path.exerciseIDs[order + 1]) : nil
                let threshold = exercise.isTimedExercise ? exercise.defaultDurationSeconds : exercise.defaultReps
                let pb = store.personalBest(for: exercise.id)
                let current = exercise.isTimedExercise ? (pb?.durationSeconds ?? 0) : (pb?.reps ?? 0)
                let unit = exercise.isTimedExercise ? "s" : " reps"

                VStack(alignment: .leading, spacing: 10) {
                    Text("Progression Path")
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundStyle(.secondary)

                    VStack(alignment: .leading, spacing: 12) {
                        HStack {
                            Label(path.name, systemImage: path.category.icon)
                                .font(.system(size: 14, weight: .bold, design: .rounded))
                                .foregroundStyle(path.category.color)
                            Spacer()
                            Text("Step \(order + 1) of \(total)")
                                .font(.system(size: 12, weight: .semibold, design: .rounded))
                                .foregroundStyle(.secondary)
                        }

                        GeometryReader { geo in
                            ZStack(alignment: .leading) {
                                Capsule().fill(path.category.color.opacity(0.15)).frame(height: 8)
                                Capsule().fill(path.category.color).frame(width: geo.size.width * fraction, height: 8)
                            }
                        }
                        .frame(height: 8)

                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Unlock target")
                                    .font(.system(size: 11, weight: .medium, design: .rounded))
                                    .foregroundStyle(.secondary)
                                Text("\(threshold)\(unit)")
                                    .font(.system(size: 14, weight: .bold, design: .rounded))
                                    .foregroundStyle(current >= threshold ? palette.positive : .primary)
                            }
                            Spacer()
                            if let next = nextEx {
                                VStack(alignment: .trailing, spacing: 2) {
                                    Text("Next exercise")
                                        .font(.system(size: 11, weight: .medium, design: .rounded))
                                        .foregroundStyle(.secondary)
                                    Text(next.name)
                                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                                        .foregroundStyle(path.category.color)
                                }
                            } else {
                                Text("Final step ✓")
                                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                                    .foregroundStyle(palette.positive)
                            }
                        }

                        if current > 0 {
                            Text("Your best: \(current)\(unit)")
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(current >= threshold ? palette.positive : .secondary)
                        } else {
                            Text("No sessions yet — start training to track progress.")
                                .font(.system(size: 12, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(14)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
                }
            }
        }
    }

    private var historySection: some View {
        let recent = store.sessions(containing: exercise.id, last: 60)
        guard !recent.isEmpty else { return AnyView(EmptyView()) }

        return AnyView(VStack(alignment: .leading, spacing: 8) {
            Text("Recent Performance")
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)

            VStack(spacing: 0) {
                ForEach(Array(recent.prefix(5).enumerated()), id: \.element.id) { idx, session in
                    let sets = session.exercises.first(where: { $0.exerciseID == exercise.id })?.sets ?? []
                    let completed = sets.filter(\.isCompleted)
                    HStack {
                        Text(session.date, style: .date)
                            .font(.system(size: 13, weight: .medium, design: .rounded))
                        Spacer()
                        Text("\(completed.count) sets")
                            .font(.system(size: 13, weight: .semibold, design: .rounded))
                            .foregroundStyle(.secondary)
                        if let best = completed.compactMap(\.reps).max() {
                            Text("· \(best) reps max")
                                .font(.system(size: 13, design: .rounded))
                                .foregroundStyle(.secondary)
                        } else if let best = completed.compactMap(\.durationSeconds).max() {
                            Text("· \(best)s best")
                                .font(.system(size: 13, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    if idx < min(4, recent.count - 1) { Divider().padding(.leading, 14) }
                }
            }
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
        })
    }
}

// MARK: - Fitness Goals Page

struct FitnessGoalsPageView: View {
    @EnvironmentObject private var navigator: AppNavigator
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = FitnessStore.shared

    @AppStorage("fitness.profile.primaryGoal") private var primaryGoalRaw: String = FitnessGoalType.muscleMass.rawValue
    @AppStorage("fitness.profile.ageYears") private var ageYears: Int = 25
    @AppStorage("fitness.profile.heightCm") private var heightCm: Double = 175
    @AppStorage("fitness.profile.trainingYears") private var trainingYears: Int = 0

    @State private var showAddGoal = false

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }
    private var primaryGoal: FitnessGoalType { FitnessGoalType(rawValue: primaryGoalRaw) ?? .muscleMass }

    var body: some View {
        QuailFitnessPageShell(
            title: "Goals",
            selectedBarTab: .goals,
            onLeadingTap: { navigator.goBack() },
            onTrailingTap: { navigator.show(.fitnessNotifications) }
        ) {
            AppPageScroll(contentPadding: 14) {
                VStack(alignment: .leading, spacing: 16) {
                    primaryGoalCard
                    recommendationsSection
                    activeGoalsSection
                    Color.clear.frame(height: 40)
                }
            }
        }
        .sheet(isPresented: $showAddGoal) { AddFitnessGoalSheet() }
    }

    // MARK: Primary Goal Card
    private var primaryGoalCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(primaryGoal.displayName, systemImage: primaryGoal.icon)
                .font(.system(size: 16, weight: .bold, design: .rounded))
                .foregroundStyle(primaryGoal.color)
            HStack(spacing: 0) {
                statPill(title: "Reps", value: primaryGoal.repRange)
                Divider().frame(height: 32)
                statPill(title: "Sets", value: primaryGoal.setsAdvice.components(separatedBy: " ").prefix(2).joined(separator: " "))
                Divider().frame(height: 32)
                statPill(title: "Rest", value: primaryGoal.restAdvice.components(separatedBy: " ").prefix(2).joined(separator: " "))
            }
            Text(primaryGoal.frequencyAdvice)
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func statPill(title: String, value: String) -> some View {
        VStack(spacing: 3) {
            Text(value)
                .font(.system(size: 13, weight: .bold, design: .rounded))
                .multilineTextAlignment(.center)
            Text(title)
                .font(.system(size: 10, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 6)
    }

    // MARK: Recommendations
    private var recommendationsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("How To Get There")
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .padding(.leading, 4)

            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(primaryGoal.strategyNotes.enumerated()), id: \.offset) { i, note in
                    HStack(alignment: .top, spacing: 12) {
                        ZStack {
                            Circle().fill(primaryGoal.color.opacity(0.15)).frame(width: 24, height: 24)
                            Text("\(i + 1)").font(.system(size: 11, weight: .bold, design: .rounded)).foregroundStyle(primaryGoal.color)
                        }
                        Text(note)
                            .font(.system(size: 13, design: .rounded))
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.horizontal, 14).padding(.vertical, 10)
                    if i < primaryGoal.strategyNotes.count - 1 { Divider().padding(.leading, 50) }
                }
            }
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }

    // MARK: Active Goals
    private var activeGoalsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("My Goals")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)
                    .padding(.leading, 4)
                Spacer()
                Button { showAddGoal = true } label: {
                    Image(systemName: "plus.circle.fill").font(.system(size: 18)).foregroundStyle(palette.accent)
                }
                .buttonStyle(.plain)
            }

            if store.goals.isEmpty {
                Button { showAddGoal = true } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "plus.circle").font(.system(size: 20)).foregroundStyle(palette.accent.opacity(0.6))
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Set a Goal").font(.system(size: 14, weight: .semibold, design: .rounded))
                            Text("Track a specific exercise target with a deadline")
                                .font(.system(size: 12, design: .rounded)).foregroundStyle(.secondary)
                        }
                        Spacer()
                    }
                    .padding(16)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
                }
                .buttonStyle(.plain)
            } else {
                VStack(spacing: 10) {
                    ForEach(store.goals) { goal in
                        goalCard(goal)
                    }
                }
            }
        }
    }

    private func goalCard(_ goal: FitnessGoal) -> some View {
        let progress = store.progressForGoal(goal)
        let daysLeft = Calendar.current.dateComponents([.day], from: Date(), to: goal.targetDate).day ?? 0
        let ex = goal.targetExerciseID.flatMap { store.exercise(id: $0) }
        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label(goal.title, systemImage: goal.goalType.icon)
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                    .foregroundStyle(goal.goalType.color)
                Spacer()
                Button(role: .destructive) { store.deleteGoal(id: goal.id) } label: {
                    Image(systemName: "xmark").font(.system(size: 12)).foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
            }
            if let ex = ex {
                let target = goal.targetReps.map { "\($0) reps" } ?? goal.targetDurationSeconds.map { "\($0)s" } ?? ""
                Text("\(ex.name): \(target)")
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(goal.goalType.color.opacity(0.15)).frame(height: 10)
                    Capsule().fill(goal.goalType.color).frame(width: geo.size.width * progress, height: 10)
                }
            }
            .frame(height: 10)
            HStack {
                Text("\(Int(progress * 100))% complete")
                    .font(.system(size: 11, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                Spacer()
                Text(daysLeft > 0 ? "\(daysLeft) days left" : (daysLeft == 0 ? "Due today" : "Overdue"))
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                    .foregroundStyle(daysLeft < 7 ? Color(red: 0.90, green: 0.30, blue: 0.20) : .secondary)
            }
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

// MARK: - Add Fitness Goal Sheet

private struct AddFitnessGoalSheet: View {
    @ObservedObject private var store = FitnessStore.shared
    @Environment(\.dismiss) private var dismiss

    @State private var title = ""
    @State private var goalType: FitnessGoalType = .muscleMass
    @State private var targetExerciseID: UUID?
    @State private var targetReps: Int = 10
    @State private var targetDurationSeconds: Int = 60
    @State private var useReps = true
    @State private var targetDate = Calendar.current.date(byAdding: .month, value: 3, to: Date()) ?? Date()

    var selectedExercise: Exercise? { targetExerciseID.flatMap { store.exercise(id: $0) } }

    var body: some View {
        NavigationStack {
            Form {
                Section("Goal") {
                    TextField("e.g. 10 Pull-ups, Run 5K", text: $title)
                    Picker("Type", selection: $goalType) {
                        ForEach(FitnessGoalType.allCases, id: \.self) { t in
                            Label(t.displayName, systemImage: t.icon).tag(t)
                        }
                    }
                }
                Section("Target Exercise (optional)") {
                    Picker("Exercise", selection: $targetExerciseID) {
                        Text("None").tag(Optional<UUID>.none)
                        ForEach(store.exercises.sorted { $0.name < $1.name }) { ex in
                            Text(ex.name).tag(Optional(ex.id))
                        }
                    }
                    if targetExerciseID != nil {
                        if let ex = selectedExercise, ex.isTimedExercise {
                            Stepper("Target: \(targetDurationSeconds)s", value: $targetDurationSeconds, in: 5...3600, step: 5)
                        } else {
                            Stepper("Target: \(targetReps) reps", value: $targetReps, in: 1...500)
                        }
                    }
                }
                Section("Deadline") {
                    DatePicker("Target Date", selection: $targetDate, in: Date()..., displayedComponents: .date)
                }
            }
            .navigationTitle("New Goal")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Add") {
                        let isTimed = selectedExercise?.isTimedExercise ?? false
                        let goal = FitnessGoal(
                            title: title.isEmpty ? goalType.displayName : title,
                            goalType: goalType,
                            targetExerciseID: targetExerciseID,
                            targetReps: (targetExerciseID != nil && !isTimed) ? targetReps : nil,
                            targetDurationSeconds: (targetExerciseID != nil && isTimed) ? targetDurationSeconds : nil,
                            targetDate: targetDate
                        )
                        store.addGoal(goal)
                        dismiss()
                    }
                }
            }
        }
    }
}

// MARK: - Training Plan Sheet
//
// Minimal parity with Android's FitnessPlanScreen: status card, generate /
// start-testing-week actions, and a list of scheduled workouts with
// complete/skip. Presented as a sheet from FitnessPageView since adding a
// dedicated AppRoute would require editing AppNavigator.swift/NativePages.swift.

private struct TrainingPlanSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = FitnessStore.shared
    @Environment(\.dismiss) private var dismiss
    @State private var isBusy = false

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        NavigationStack {
            AppPageScroll(contentPadding: 14) {
                VStack(alignment: .leading, spacing: 16) {
                    statusCard
                    if store.planStatus == .none {
                        actionButton(title: "Start Testing Week", icon: "flag.checkered") {
                            await store.startTestingWeek()
                        }
                        Text("A testing week measures your current ability on each training goal before building a progressive plan around it.")
                            .font(.system(size: 12, design: .rounded))
                            .foregroundStyle(.secondary)
                    } else if store.planStatus == .testing {
                        actionButton(title: "Generate Plan From Test Results", icon: "wand.and.stars") {
                            await store.generatePlan()
                        }
                    }
                    if !store.scheduledWorkouts.isEmpty {
                        scheduledSection
                    }
                    Color.clear.frame(height: 30)
                }
            }
            .navigationTitle("Training Plan")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
        .task {
            await store.refreshPlanStatus()
            await store.refreshScheduledWorkouts()
        }
    }

    private var statusCard: some View {
        HStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(palette.accent.opacity(0.15)).frame(width: 40, height: 40)
                Image(systemName: "chart.line.uptrend.xyaxis").font(.system(size: 18, weight: .semibold)).foregroundStyle(palette.accent)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(statusLabel).font(.system(size: 15, weight: .bold, design: .rounded))
                Text(statusSubtitle).font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private var statusLabel: String {
        switch store.planStatus {
        case .none:    return "No Plan Yet"
        case .testing: return "Testing Week"
        case .active:  return "Plan Active"
        }
    }

    private var statusSubtitle: String {
        switch store.planStatus {
        case .none:    return "Set training goals, then start a testing week"
        case .testing: return "Complete the scheduled test workouts below"
        case .active:  return "\(store.scheduledWorkouts.filter { $0.status == "PLANNED" }.count) upcoming workouts"
        }
    }

    private func actionButton(title: String, icon: String, action: @escaping () async -> Void) -> some View {
        Button {
            guard !isBusy else { return }
            isBusy = true
            Task {
                await action()
                isBusy = false
            }
        } label: {
            HStack {
                if isBusy { ProgressView().tint(.white) } else { Image(systemName: icon) }
                Text(title)
            }
            .font(.system(size: 15, weight: .bold, design: .rounded))
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 14)
            .background(palette.accent, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
        .buttonStyle(.plain)
        .disabled(isBusy)
    }

    private var scheduledSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Scheduled Workouts")
                .font(.system(size: 13, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .padding(.leading, 4)
            VStack(spacing: 0) {
                ForEach(Array(store.scheduledWorkouts.enumerated()), id: \.element.id) { idx, workout in
                    scheduledRow(workout)
                    if idx < store.scheduledWorkouts.count - 1 { Divider().padding(.leading, 14) }
                }
            }
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }

    private func scheduledRow(_ workout: ScheduledWorkout) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(workout.workoutType.capitalized)
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                Text(workout.scheduledDate, style: .date)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                Text(workout.status.capitalized)
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                    .foregroundStyle(statusColor(workout.status))
            }
            Spacer()
            if workout.status == "PLANNED" {
                Button {
                    Task { await store.skipScheduledWorkout(workout) }
                } label: {
                    Image(systemName: "xmark.circle").font(.system(size: 20)).foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                Button {
                    Task { await store.completeScheduledWorkout(workout) }
                } label: {
                    Image(systemName: "checkmark.circle.fill").font(.system(size: 20)).foregroundStyle(palette.positive)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }

    private func statusColor(_ status: String) -> Color {
        switch status {
        case "COMPLETED": return palette.positive
        case "SKIPPED":   return Color(red: 0.85, green: 0.25, blue: 0.25)
        default:          return .secondary
        }
    }
}

// MARK: - Fitness Profile Sheet

private struct FitnessProfileSheet: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject private var store = FitnessStore.shared
    @AppStorage("fitness.profile.primaryGoal") private var primaryGoalRaw: String = FitnessGoalType.muscleMass.rawValue
    @AppStorage("fitness.profile.ageYears") private var ageYears: Int = 25
    @AppStorage("fitness.profile.heightCm") private var heightCm: Double = 175
    @AppStorage("fitness.profile.trainingYears") private var trainingYears: Int = 0
    @State private var manualWeightKg: Double = 0

    private var primaryGoal: Binding<FitnessGoalType> {
        Binding(get: { FitnessGoalType(rawValue: primaryGoalRaw) ?? .muscleMass },
                set: { primaryGoalRaw = $0.rawValue })
    }

    private var displayWeightKg: Double { store.latestBodyMassKg ?? manualWeightKg }

    var body: some View {
        NavigationStack {
            Form {
                Section("Primary Goal") {
                    Picker("Goal", selection: primaryGoal) {
                        ForEach(FitnessGoalType.allCases, id: \.self) { t in
                            Label(t.displayName, systemImage: t.icon).tag(t)
                        }
                    }
                    .pickerStyle(.inline)
                    .labelsHidden()
                }
                Section {
                    Stepper("Age: \(ageYears)", value: $ageYears, in: 13...99)
                    HStack {
                        Text("Height")
                        Spacer()
                        TextField("cm", value: $heightCm, format: .number)
                            .keyboardType(.decimalPad)
                            .multilineTextAlignment(.trailing)
                            .frame(width: 80)
                        Text("cm").foregroundStyle(.secondary)
                    }
                    HStack {
                        Text("Weight")
                        Spacer()
                        if store.latestBodyMassKg != nil {
                            Text(String(format: "%.1f kg", displayWeightKg))
                                .foregroundStyle(.secondary)
                            Text("from Health").font(.caption).foregroundStyle(.tertiary)
                        } else {
                            TextField("kg", value: $manualWeightKg, format: .number)
                                .keyboardType(.decimalPad)
                                .multilineTextAlignment(.trailing)
                                .frame(width: 80)
                            Text("kg").foregroundStyle(.secondary)
                        }
                    }
                } header: {
                    Text("Personal Stats")
                } footer: {
                    if store.latestBodyMassKg == nil {
                        Text("Grant Health access to sync weight automatically, or enter it manually.")
                    } else {
                        Text("Weight synced from Apple Health.")
                    }
                }
                Section("Training Experience") {
                    Picker("Experience", selection: $trainingYears) {
                        Text("Beginner (< 6 months)").tag(0)
                        Text("Novice (6–18 months)").tag(1)
                        Text("Intermediate (1.5–3 years)").tag(2)
                        Text("Advanced (3+ years)").tag(3)
                    }
                    .pickerStyle(.inline)
                    .labelsHidden()
                }
            }
            .navigationTitle("My Profile")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {
                        if store.latestBodyMassKg == nil && manualWeightKg > 0 {
                            Task { await store.saveBodyMass(manualWeightKg) }
                        }
                        dismiss()
                    }
                }
            }
            .onAppear { manualWeightKg = store.latestBodyMassKg ?? 0 }
        }
    }
}

// MARK: - Flow Layout (for muscle group pills)

private struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 0
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x + size.width > width, x > 0 { x = 0; y += rowHeight + spacing; rowHeight = 0 }
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: width, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, rowHeight: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX, x > bounds.minX { x = bounds.minX; y += rowHeight + spacing; rowHeight = 0 }
            view.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}

// MARK: - Add Exercise to Workout Sheet

struct AddExerciseToWorkoutSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = FitnessStore.shared
    @Environment(\.dismiss) private var dismiss
    @Binding var session: WorkoutSession

    @State private var searchText = ""
    @State private var selectedCategory: ExerciseCategory?

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    private var filtered: [Exercise] {
        store.exercises.filter { ex in
            (selectedCategory == nil || ex.category == selectedCategory) &&
            (searchText.isEmpty || ex.name.localizedCaseInsensitiveContains(searchText))
        }
        .sorted { $0.name < $1.name }
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                categoryFilter
                Divider()
                List(filtered) { ex in
                    Button {
                        store.addExercise(ex, to: &session)
                        dismiss()
                    } label: {
                        exerciseRow(ex)
                    }
                    .buttonStyle(.plain)
                }
                .listStyle(.plain)
            }
            .searchable(text: $searchText, prompt: "Search exercises")
            .navigationTitle("Add Exercise")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }

    private var categoryFilter: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                filterChip(label: "All", icon: "square.grid.2x2", category: nil)
                ForEach(ExerciseCategory.allCases, id: \.self) { cat in
                    filterChip(label: cat.displayName, icon: cat.icon, category: cat)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
        }
    }

    private func filterChip(label: String, icon: String, category: ExerciseCategory?) -> some View {
        let selected = selectedCategory == category
        let color = category?.color ?? palette.accent
        return Button { selectedCategory = category } label: {
            Label(label, systemImage: icon)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(selected ? .white : color)
                .padding(.horizontal, 12)
                .padding(.vertical, 7)
                .background(selected ? color : color.opacity(0.12), in: Capsule())
        }
        .buttonStyle(.plain)
    }

    private func exerciseRow(_ ex: Exercise) -> some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(ex.category.color.opacity(0.15))
                    .frame(width: 36, height: 36)
                Image(systemName: ex.category.icon)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(ex.category.color)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(ex.name).font(.system(size: 14, weight: .bold, design: .rounded))
                HStack(spacing: 6) {
                    Text(ex.difficulty.displayName)
                        .font(.system(size: 10, weight: .bold, design: .rounded))
                        .foregroundStyle(ex.difficulty.color)
                    Text(ex.muscleGroups.prefix(2).map(\.displayName).joined(separator: ", "))
                        .font(.system(size: 11, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            if let pb = store.personalBest(for: ex.id) {
                Text(pb.displayValue)
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Session Detail Sheet

private struct SessionDetailSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = FitnessStore.shared
    @Environment(\.dismiss) private var dismiss
    let session: WorkoutSession

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    statsRow
                    ForEach(session.exercises) { we in
                        exerciseCard(we: we)
                    }
                    if !session.notes.isEmpty {
                        noteCard
                    }
                }
                .padding(16)
            }
            .background(LinearGradient(colors: [palette.backgroundTop, palette.backgroundBottom], startPoint: .top, endPoint: .bottom).ignoresSafeArea())
            .navigationTitle(session.date.formatted(date: .abbreviated, time: .omitted))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
    }

    private var statsRow: some View {
        HStack {
            statCell(value: "\(session.durationMinutes)min", label: "Duration")
            Divider().frame(height: 40)
            statCell(value: "\(session.totalSets)", label: "Sets")
            Divider().frame(height: 40)
            statCell(value: "\(session.totalReps)", label: "Total Reps")
            if session.hkWorkoutUUID != nil {
                Divider().frame(height: 40)
                statCell(value: "✓", label: "Health")
            }
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func statCell(value: String, label: String) -> some View {
        VStack(spacing: 2) {
            Text(value).font(.system(size: 18, weight: .bold, design: .rounded))
            Text(label).font(.system(size: 11, design: .rounded)).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private func exerciseCard(we: WorkoutExercise) -> some View {
        let ex = store.exercise(id: we.exerciseID)
        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                if let ex = ex {
                    ZStack {
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .fill(ex.category.color.opacity(0.15)).frame(width: 28, height: 28)
                        Image(systemName: ex.category.icon)
                            .font(.system(size: 12, weight: .semibold)).foregroundStyle(ex.category.color)
                    }
                }
                Text(ex?.name ?? "Unknown").font(.system(size: 14, weight: .bold, design: .rounded))
            }
            ForEach(Array(we.sets.enumerated()), id: \.element.id) { idx, set in
                HStack {
                    Text("Set \(idx + 1)").font(.system(size: 13, design: .rounded)).foregroundStyle(.secondary)
                    Spacer()
                    Text(set.displayValue).font(.system(size: 13, weight: .semibold, design: .rounded))
                    Image(systemName: set.isCompleted ? "checkmark.circle.fill" : "xmark.circle")
                        .foregroundStyle(set.isCompleted ? palette.positive : palette.negative)
                        .font(.system(size: 14))
                }
            }
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private var noteCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Notes").font(.system(size: 12, weight: .semibold, design: .rounded)).foregroundStyle(.secondary)
            Text(session.notes).font(.system(size: 14, design: .rounded))
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

// MARK: - Add Milestone Sheet

private struct AddMilestoneSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = FitnessStore.shared
    @Environment(\.dismiss) private var dismiss

    @State private var title = ""
    @State private var notes = ""
    @State private var date = Date()
    @State private var selectedExerciseID: UUID?

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        NavigationStack {
            Form {
                Section("Achievement") {
                    TextField("e.g. First unassisted pull-up", text: $title)
                    DatePicker("Date", selection: $date, displayedComponents: .date)
                }
                Section("Details") {
                    Picker("Exercise (optional)", selection: $selectedExerciseID) {
                        Text("None").tag(UUID?.none)
                        ForEach(store.exercises) { ex in
                            Text(ex.name).tag(Optional(ex.id))
                        }
                    }
                    TextField("Notes", text: $notes, axis: .vertical).lineLimit(3...5)
                }
            }
            .navigationTitle("Log Milestone")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        guard !title.isEmpty else { return }
                        store.addMilestone(FitnessMilestone(
                            title: title, date: date,
                            exerciseID: selectedExerciseID, notes: notes
                        ))
                        dismiss()
                    }
                    .disabled(title.isEmpty)
                }
            }
        }
    }
}

// MARK: - Bodyweight Entry Sheet

private struct BodyweightEntrySheet: View {
    @Environment(\.dismiss) private var dismiss
    let onSet: (Double) -> Void

    @State private var lbs: Double = 170
    @AppStorage("fitness.bodyweight.lbs") private var savedLbs: Double = 170

    var body: some View {
        NavigationStack {
            Form {
                Section("Current Bodyweight") {
                    HStack {
                        TextField("lbs", value: $lbs, format: .number)
                            .keyboardType(.decimalPad)
                        Text("lbs").foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle("Bodyweight")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Skip") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Set") {
                        savedLbs = lbs
                        onSet(lbs * 0.453592)
                        dismiss()
                    }
                }
            }
            .onAppear { lbs = savedLbs }
        }
    }
}

// MARK: - Fitness Settings Page

struct QuailFitnessSettingsPageView: View {
    @EnvironmentObject private var navigator: AppNavigator
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = FitnessStore.shared

    @State private var showExerciseLibrary = false
    @State private var showProgressionEditor = false
    @State private var showNotificationSettings = false
    @State private var showRoutineManager = false
    @State private var showProfile = false
    @State private var showGarmin = false

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        QuailFitnessPageShell(
            title: "Settings",
            onLeadingTap: { navigator.goBack() },
            onTrailingTap: { navigator.show(.fitnessNotifications) }
        ) {
            AppPageScroll(contentPadding: 14) {
                VStack(alignment: .leading, spacing: 14) {
                    fitnessSettingsSection(title: "Profile") {
                        fitnessSettingsRow(
                            icon: "person.fill", iconColor: palette.accent,
                            title: "My Profile",
                            subtitle: "Age, height, training experience & primary goal"
                        ) { showProfile = true }
                    }

                    fitnessSettingsSection(title: "Health") {
                        fitnessSettingsRow(
                            icon: "heart.fill", iconColor: Color(red: 0.90, green: 0.25, blue: 0.30),
                            title: "Apple Health",
                            subtitle: store.healthKitAuthorized ? "Connected" : "Tap to connect"
                        ) {
                            Task { await store.requestHealthKitAuthorization() }
                        }
                        Divider().padding(.leading, 60)
                        fitnessSettingsRow(
                            icon: "figure.run.circle.fill", iconColor: Color(red: 0.10, green: 0.55, blue: 0.85),
                            title: "Garmin",
                            subtitle: store.garminConnected ? "Connected" : "Not connected"
                        ) { showGarmin = true }
                    }

                    fitnessSettingsSection(title: "Library") {
                        fitnessSettingsRow(
                            icon: "books.vertical.fill", iconColor: palette.accent,
                            title: "Exercise Library",
                            subtitle: "\(store.exercises.count) exercises · \(store.exercises.filter { !$0.isBuiltIn }.count) custom"
                        ) { showExerciseLibrary = true }
                        Divider().padding(.leading, 60)
                        fitnessSettingsRow(
                            icon: "list.clipboard.fill", iconColor: ExerciseCategory.cardio.color,
                            title: "Routines",
                            subtitle: "\(store.routines.count) saved routines"
                        ) { showRoutineManager = true }
                        Divider().padding(.leading, 60)
                        fitnessSettingsRow(
                            icon: "arrow.up.arrow.down.circle.fill", iconColor: ExerciseCategory.skill.color,
                            title: "Progression Paths",
                            subtitle: "\(store.progressionPaths.count) paths"
                        ) { showProgressionEditor = true }
                    }

                    fitnessSettingsSection(title: "Notifications") {
                        fitnessSettingsRow(
                            icon: "bell.badge.fill", iconColor: palette.accent,
                            title: "Notification Settings",
                            subtitle: "Reminders, milestones, recovery alerts"
                        ) { showNotificationSettings = true }
                    }
                }
            }
        }
        .sheet(isPresented: $showExerciseLibrary) {
            ExerciseLibraryManagerSheet()
        }
        .sheet(isPresented: $showNotificationSettings) {
            FitnessNotificationSettingsSheet()
        }
        .sheet(isPresented: $showRoutineManager) {
            RoutineManagerSheet()
        }
        .sheet(isPresented: $showProfile) {
            FitnessProfileSheet()
        }
        .sheet(isPresented: $showProgressionEditor) {
            ProgressionPathEditorSheet()
        }
        .sheet(isPresented: $showGarmin) {
            GarminSettingsSheet()
        }
        .task {
            await store.refreshGarminStatus()
        }
    }

    private func fitnessSettingsSection<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .padding(.leading, 4)
            VStack(spacing: 0) { content() }
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }

    private func fitnessSettingsRow(icon: String, iconColor: Color, title: String, subtitle: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 14) {
                ZStack {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(iconColor.opacity(0.15)).frame(width: 36, height: 36)
                    Image(systemName: icon).font(.system(size: 16, weight: .semibold)).foregroundStyle(iconColor)
                }
                VStack(alignment: .leading, spacing: 3) {
                    Text(title).font(.system(size: 14, weight: .bold, design: .rounded)).foregroundStyle(.primary)
                    Text(subtitle).font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
                }
                Spacer(minLength: 12)
                Image(systemName: "chevron.right").font(.system(size: 12, weight: .semibold)).foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 14).padding(.vertical, 12)
        }
        .buttonStyle(.plain)
    }

}

// MARK: - Garmin Settings Sheet

private struct GarminSettingsSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = FitnessStore.shared
    @Environment(\.dismiss) private var dismiss

    @State private var email = ""
    @State private var password = ""
    @State private var mfaCode = ""
    @State private var pendingSessionID: String?
    @State private var isBusy = false
    @State private var message: String?

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        NavigationStack {
            Form {
                Section("Status") {
                    HStack {
                        Text(store.garminConnected ? "Connected" : "Not Connected")
                            .foregroundStyle(store.garminConnected ? palette.positive : .secondary)
                        Spacer()
                        if store.garminConnected {
                            Button("Disconnect", role: .destructive) {
                                Task {
                                    isBusy = true
                                    await store.garminDisconnect()
                                    isBusy = false
                                }
                            }
                        }
                    }
                }

                if !store.garminConnected {
                    Section("Connect Garmin") {
                        TextField("Email", text: $email)
                            .keyboardType(.emailAddress)
                            .textInputAutocapitalization(.never)
                        SecureField("Password", text: $password)
                        Button {
                            Task {
                                isBusy = true
                                message = nil
                                let result = await store.garminConnect(email: email, password: password)
                                if result.needsMFA {
                                    pendingSessionID = result.sessionID
                                    message = "Enter the MFA code sent to your device."
                                } else if store.garminConnected {
                                    message = "Connected."
                                } else {
                                    message = "Could not connect. Check your credentials."
                                }
                                isBusy = false
                            }
                        } label: {
                            if isBusy { ProgressView() } else { Text("Connect") }
                        }
                        .disabled(email.isEmpty || password.isEmpty || isBusy)
                    }

                    if let pendingSessionID {
                        Section("Two-Factor Code") {
                            TextField("MFA Code", text: $mfaCode)
                                .keyboardType(.numberPad)
                            Button {
                                Task {
                                    isBusy = true
                                    let ok = await store.garminSubmitMFA(sessionID: pendingSessionID, code: mfaCode)
                                    message = ok ? "Connected." : "Invalid code."
                                    if ok { self.pendingSessionID = nil }
                                    isBusy = false
                                }
                            } label: {
                                if isBusy { ProgressView() } else { Text("Submit Code") }
                            }
                            .disabled(mfaCode.isEmpty || isBusy)
                        }
                    }
                }

                if let message {
                    Section { Text(message).font(.system(size: 12, design: .rounded)).foregroundStyle(.secondary) }
                }
            }
            .navigationTitle("Garmin")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
        .task { await store.refreshGarminStatus() }
    }
}

private struct FitnessNotificationSettingsSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @Environment(\.dismiss) private var dismiss
    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    notifyRow(icon: "bell.badge.fill", iconColor: palette.accent,
                              title: "Workout Reminders", subtitle: "Daily reminder to stay consistent",
                              key: "fitness.notify.dailyReminder", defaultOn: false)
                    notifyRow(icon: "trophy.fill", iconColor: Color(red: 0.90, green: 0.65, blue: 0.10),
                              title: "Milestone Alerts", subtitle: "Notify when a progression threshold is reached",
                              key: "fitness.notify.milestones", defaultOn: true)
                    notifyRow(icon: "heart.fill", iconColor: Color(red: 0.90, green: 0.25, blue: 0.30),
                              title: "Recovery Insights", subtitle: "Morning readiness summary from HealthKit",
                              key: "fitness.notify.recovery", defaultOn: true)
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Notification Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
    }

    private func notifyRow(icon: String, iconColor: Color, title: String, subtitle: String, key: String, defaultOn: Bool) -> some View {
        HStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(iconColor.opacity(0.15)).frame(width: 36, height: 36)
                Image(systemName: icon).font(.system(size: 16, weight: .semibold)).foregroundStyle(iconColor)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.system(size: 14, weight: .bold, design: .rounded))
                Text(subtitle).font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            FitnessNotifyToggle(key: key, defaultOn: defaultOn, palette: palette)
        }
        .padding(.vertical, 4)
    }
}

private struct FitnessNotifyToggle: View {
    let key: String; let defaultOn: Bool; let palette: QuailThemePalette
    @State private var isOn: Bool
    init(key: String, defaultOn: Bool, palette: QuailThemePalette) {
        self.key = key; self.defaultOn = defaultOn; self.palette = palette
        _isOn = State(initialValue: UserDefaults.standard.object(forKey: key) as? Bool ?? defaultOn)
    }
    var body: some View {
        Toggle("", isOn: $isOn).labelsHidden().tint(palette.accent)
            .onChange(of: isOn) { _, v in UserDefaults.standard.set(v, forKey: key) }
    }
}

// MARK: - Progression Path Editor Sheet

private struct ProgressionPathEditorSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = FitnessStore.shared
    @Environment(\.dismiss) private var dismiss
    @State private var selectedPath: ProgressionPath?

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        NavigationStack {
            List {
                ForEach(store.progressionPaths) { path in
                    Button { selectedPath = path } label: {
                        HStack(spacing: 14) {
                            ZStack {
                                RoundedRectangle(cornerRadius: 8, style: .continuous)
                                    .fill(path.category.color.opacity(0.15)).frame(width: 32, height: 32)
                                Image(systemName: path.category.icon)
                                    .font(.system(size: 14, weight: .semibold)).foregroundStyle(path.category.color)
                            }
                            VStack(alignment: .leading, spacing: 3) {
                                Text(path.name).font(.system(size: 14, weight: .bold, design: .rounded)).foregroundStyle(.primary)
                                Text(path.description).font(.system(size: 12, design: .rounded)).foregroundStyle(.secondary).lineLimit(1)
                            }
                            Spacer()
                            let step = store.currentProgressionStep(in: path)
                            let stepIdx = step?.stepIndex ?? 0
                            Text("\(stepIdx + 1)/\(path.exerciseIDs.count)")
                                .font(.system(size: 12, weight: .semibold, design: .rounded))
                                .foregroundStyle(path.category.color)
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
            .listStyle(.insetGrouped)
            .navigationTitle("Progression Paths")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
            .sheet(item: $selectedPath) { path in
                ProgressionPathDetailSheet(path: path)
            }
        }
    }
}

private struct ProgressionPathDetailSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = FitnessStore.shared
    @Environment(\.dismiss) private var dismiss
    let path: ProgressionPath

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }
    private var currentStep: (exercise: Exercise, stepIndex: Int)? { store.currentProgressionStep(in: path) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text(path.description)
                        .font(.system(size: 14, design: .rounded))
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 16)

                    VStack(spacing: 0) {
                        ForEach(Array(path.exerciseIDs.enumerated()), id: \.offset) { idx, eid in
                            if let ex = store.exercise(id: eid) {
                                let isCurrent = currentStep?.stepIndex == idx
                                let isDone = (currentStep?.stepIndex ?? 0) > idx
                                let pb = store.personalBest(for: eid)
                                let threshold = ex.isTimedExercise ? ex.defaultDurationSeconds : ex.defaultReps
                                let pbValue = ex.isTimedExercise ? pb?.durationSeconds : pb?.reps
                                let unit = ex.isTimedExercise ? "s" : " reps"

                                HStack(spacing: 14) {
                                    ZStack {
                                        Circle()
                                            .fill(isDone ? path.category.color : isCurrent ? path.category.color.opacity(0.2) : Color.clear)
                                            .frame(width: 28, height: 28)
                                        if isDone {
                                            Image(systemName: "checkmark").font(.system(size: 12, weight: .bold)).foregroundStyle(.white)
                                        } else {
                                            Text("\(idx + 1)").font(.system(size: 12, weight: .bold, design: .rounded))
                                                .foregroundStyle(isCurrent ? path.category.color : .secondary)
                                        }
                                    }
                                    VStack(alignment: .leading, spacing: 3) {
                                        Text(ex.name)
                                            .font(.system(size: 14, weight: isCurrent ? .bold : .medium, design: .rounded))
                                            .foregroundStyle(isCurrent ? .primary : isDone ? .secondary : .primary)
                                        if isCurrent {
                                            Text("Current — reach \(threshold)\(unit) to advance")
                                                .font(.system(size: 11, weight: .medium, design: .rounded))
                                                .foregroundStyle(path.category.color)
                                        } else if isDone, let pv = pbValue {
                                            Text("Done — best: \(pv)\(unit)")
                                                .font(.system(size: 11, design: .rounded)).foregroundStyle(.secondary)
                                        }
                                    }
                                    Spacer()
                                    if let pv = pbValue {
                                        Text("\(pv)\(unit)")
                                            .font(.system(size: 13, weight: .semibold, design: .rounded).monospacedDigit())
                                            .foregroundStyle(isDone ? path.category.color : .secondary)
                                    } else {
                                        Text("No data").font(.system(size: 11, design: .rounded)).foregroundStyle(.tertiary)
                                    }
                                }
                                .padding(.horizontal, 16).padding(.vertical, 12)
                                .background(isCurrent ? path.category.color.opacity(0.06) : .clear)
                                if idx < path.exerciseIDs.count - 1 {
                                    Divider().padding(.leading, 58)
                                }
                            }
                        }
                    }
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
                    .padding(.horizontal, 16)
                }
                .padding(.vertical, 14)
            }
            .background(LinearGradient(colors: [palette.backgroundTop, palette.backgroundBottom], startPoint: .top, endPoint: .bottom).ignoresSafeArea())
            .navigationTitle(path.name)
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
    }
}

// MARK: - Exercise Library Manager Sheet

private enum ExerciseLibrarySortOrder { case name, difficulty }

private struct ExerciseLibraryManagerSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = FitnessStore.shared
    @Environment(\.dismiss) private var dismiss

    @State private var showAddExercise = false
    @State private var editingExercise: Exercise?
    @State private var selectedCategory: ExerciseCategory?
    @State private var searchText = ""
    @State private var sortOrder: ExerciseLibrarySortOrder = .name

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    private var filtered: [Exercise] {
        let base = store.exercises.filter { ex in
            (selectedCategory == nil || ex.category == selectedCategory) &&
            (searchText.isEmpty || ex.name.localizedCaseInsensitiveContains(searchText))
        }
        switch sortOrder {
        case .name:       return base.sorted { $0.name < $1.name }
        case .difficulty: return base.sorted { $0.difficulty.sortKey < $1.difficulty.sortKey }
        }
    }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        filterChip("All", icon: "square.grid.2x2", cat: nil)
                        ForEach(ExerciseCategory.allCases, id: \.self) { cat in
                            filterChip(cat.displayName, icon: cat.icon, cat: cat)
                        }
                        Divider().frame(height: 24).padding(.horizontal, 4)
                        sortChip("A–Z", icon: "textformat.abc", order: .name)
                        sortChip("Difficulty", icon: "flame", order: .difficulty)
                    }
                    .padding(.horizontal, 14).padding(.vertical, 10)
                }
                Divider()
                List {
                    ForEach(filtered) { ex in
                        Button { editingExercise = ex } label: {
                            HStack(spacing: 12) {
                                ZStack {
                                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                                        .fill(ex.category.color.opacity(0.15)).frame(width: 32, height: 32)
                                    Image(systemName: ex.category.icon)
                                        .font(.system(size: 13, weight: .semibold)).foregroundStyle(ex.category.color)
                                }
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(ex.name).font(.system(size: 14, weight: .semibold, design: .rounded)).foregroundStyle(.primary)
                                    Text(ex.difficulty.displayName)
                                        .font(.system(size: 11, weight: .bold, design: .rounded))
                                        .foregroundStyle(ex.difficulty.color)
                                }
                                Spacer()
                                if ex.videoURL != nil {
                                    Image(systemName: "play.circle.fill")
                                        .font(.system(size: 16)).foregroundStyle(.secondary)
                                }
                                Image(systemName: "chevron.right").font(.system(size: 12)).foregroundStyle(.tertiary)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                    .onDelete { idx in
                        let ids = idx.map { filtered[$0].id }
                        store.exercises.removeAll { ids.contains($0.id) && !$0.isBuiltIn }
                        store.saveExercises()
                    }
                }
                .listStyle(.plain)
            }
            .searchable(text: $searchText, prompt: "Search")
            .navigationTitle("Exercise Library")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } }
                ToolbarItem(placement: .primaryAction) {
                    Button { showAddExercise = true } label: {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $showAddExercise) { ExerciseEditSheet(existing: nil) }
            .sheet(item: $editingExercise) { ex in ExerciseEditSheet(existing: ex) }
        }
    }

    private func filterChip(_ label: String, icon: String, cat: ExerciseCategory?) -> some View {
        let sel = selectedCategory == cat
        let color = cat?.color ?? palette.accent
        return Button { selectedCategory = cat } label: {
            Label(label, systemImage: icon)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(sel ? .white : color)
                .padding(.horizontal, 12).padding(.vertical, 7)
                .background(sel ? color : color.opacity(0.12), in: Capsule())
        }
        .buttonStyle(.plain)
    }

    private func sortChip(_ label: String, icon: String, order: ExerciseLibrarySortOrder) -> some View {
        let sel = sortOrder == order
        return Button { sortOrder = order } label: {
            Label(label, systemImage: icon)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(sel ? .white : palette.accent)
                .padding(.horizontal, 12).padding(.vertical, 7)
                .background(sel ? palette.accent : palette.accent.opacity(0.12), in: Capsule())
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Exercise Edit Sheet

struct ExerciseEditSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = FitnessStore.shared
    @Environment(\.dismiss) private var dismiss

    let existing: Exercise?

    @State private var name: String = ""
    @State private var category: ExerciseCategory = .push
    @State private var difficulty: ExerciseDifficulty = .intermediate
    @State private var muscleGroups: Set<MuscleGroup> = []
    @State private var isTimed: Bool = false
    @State private var defaultSets: Int = 3
    @State private var defaultReps: Int = 10
    @State private var defaultDuration: Int = 30
    @State private var videoURL: String = ""
    @State private var instructions: [String] = [""]

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }
    private var isNew: Bool { existing == nil }

    var body: some View {
        NavigationStack {
            Form {
                Section("Exercise") {
                    TextField("Name", text: $name)
                    Picker("Category", selection: $category) {
                        ForEach(ExerciseCategory.allCases, id: \.self) { Text($0.displayName).tag($0) }
                    }
                    Picker("Difficulty", selection: $difficulty) {
                        ForEach(ExerciseDifficulty.allCases, id: \.self) { Text($0.displayName).tag($0) }
                    }
                }

                Section("Muscles") {
                    ForEach(MuscleGroup.allCases, id: \.self) { muscle in
                        Button {
                            if muscleGroups.contains(muscle) { muscleGroups.remove(muscle) }
                            else { muscleGroups.insert(muscle) }
                        } label: {
                            HStack {
                                Text(muscle.displayName).foregroundStyle(.primary)
                                Spacer()
                                if muscleGroups.contains(muscle) {
                                    Image(systemName: "checkmark").foregroundStyle(palette.accent)
                                }
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }

                Section("Defaults") {
                    Toggle("Timed Exercise", isOn: $isTimed)
                    Stepper("Sets: \(defaultSets)", value: $defaultSets, in: 1...10)
                    if isTimed {
                        Stepper("Duration: \(defaultDuration)s", value: $defaultDuration, in: 5...300, step: 5)
                    } else {
                        Stepper("Reps: \(defaultReps)", value: $defaultReps, in: 1...100)
                    }
                }

                Section("Tutorial") {
                    TextField("YouTube or video URL (optional)", text: $videoURL)
                        .keyboardType(.URL)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.never)
                }

                Section("Instructions") {
                    ForEach($instructions.indices, id: \.self) { idx in
                        HStack(alignment: .top, spacing: 8) {
                            Text("\(idx + 1).").foregroundStyle(.secondary).font(.system(size: 14, design: .rounded))
                            TextField("Step \(idx + 1)", text: $instructions[idx], axis: .vertical)
                                .lineLimit(2...4)
                        }
                    }
                    Button { instructions.append("") } label: {
                        Label("Add Step", systemImage: "plus.circle")
                    }
                    if instructions.count > 1 {
                        Button(role: .destructive) { instructions.removeLast() } label: {
                            Label("Remove Last Step", systemImage: "minus.circle")
                        }
                    }
                }
            }
            .navigationTitle(isNew ? "New Exercise" : "Edit Exercise")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save(); dismiss() }.disabled(name.isEmpty)
                }
            }
            .onAppear { loadExisting() }
        }
    }

    private func loadExisting() {
        guard let ex = existing else { return }
        name = ex.name; category = ex.category; difficulty = ex.difficulty
        muscleGroups = Set(ex.muscleGroups); isTimed = ex.isTimedExercise
        defaultSets = ex.defaultSets; defaultReps = ex.defaultReps; defaultDuration = ex.defaultDurationSeconds
        videoURL = ex.videoURL ?? ""; instructions = ex.instructions.isEmpty ? [""] : ex.instructions
    }

    private func save() {
        let cleaned = instructions.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
        var ex = Exercise(
            name: name.trimmingCharacters(in: .whitespacesAndNewlines),
            category: category, muscleGroups: Array(muscleGroups),
            difficulty: difficulty, instructions: cleaned,
            videoURL: videoURL.isEmpty ? nil : videoURL,
            isTimedExercise: isTimed, defaultSets: defaultSets,
            defaultReps: defaultReps, defaultDurationSeconds: defaultDuration,
            isBuiltIn: false
        )
        if let existing = existing {
            ex.id = existing.id
            ex.progressionPathID = existing.progressionPathID
            ex.progressionOrder = existing.progressionOrder
            if let idx = store.exercises.firstIndex(where: { $0.id == existing.id }) {
                store.exercises[idx] = ex
            }
        } else {
            store.exercises.append(ex)
        }
        store.saveExercises()
    }
}

// MARK: - Fitness Notifications Page

struct FitnessNotificationsContent: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = FitnessStore.shared

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    struct FitnessAlert: Identifiable {
        var id = UUID(); var icon: String; var iconColor: Color
        var title: String; var subtitle: String
    }

    var alerts: [FitnessAlert] {
        var items: [FitnessAlert] = []
        let snap = store.healthSnapshot
        if snap.readiness == .rest || snap.readiness == .moderate {
            items.append(FitnessAlert(
                icon: snap.readiness.icon, iconColor: snap.readiness.color,
                title: snap.readiness.label,
                subtitle: "HRV: \(snap.hrv.map { "\(Int($0))ms" } ?? "—") · Sleep: \(snap.sleepHours.map { String(format: "%.1f", $0) + "h" } ?? "—")"
            ))
        }
        for path in store.progressionPaths {
            if let (ex, step) = store.currentProgressionStep(in: path), step == 0 {
                if store.sessions(containing: ex.id).isEmpty {
                    items.append(FitnessAlert(icon: path.category.icon, iconColor: path.category.color,
                        title: "\(path.name): Not Started", subtitle: "Start with \(ex.name) to begin this progression"))
                }
            }
        }
        if store.totalWorkoutsThisWeek() == 0 {
            items.append(FitnessAlert(icon: "figure.strengthtraining.functional", iconColor: palette.accent,
                title: "No Workouts This Week", subtitle: "Tap the Fitness tab to start a session"))
        }
        return items
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            readinessSnapshot
            if alerts.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "checkmark.shield.fill").font(.system(size: 40)).foregroundStyle(palette.positive)
                    Text("You're on track").font(.system(size: 20, weight: .bold, design: .rounded))
                    Text("No alerts or reminders right now. Keep it up.")
                        .font(.system(size: 14, weight: .medium, design: .rounded)).foregroundStyle(.secondary).multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity).padding(.vertical, 48)
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(alerts.enumerated()), id: \.element.id) { idx, alert in
                        alertRow(alert)
                        if idx < alerts.count - 1 { Divider().padding(.leading, 60) }
                    }
                }
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
            }
        }
        .onAppear { Task { await store.refreshHealthData() } }
    }

    private var readinessSnapshot: some View {
        let r = store.healthSnapshot.readiness
        return HStack(spacing: 14) {
            Image(systemName: r.icon).font(.system(size: 28)).foregroundStyle(r.color)
            VStack(alignment: .leading, spacing: 3) {
                Text(r.label).font(.system(size: 17, weight: .bold, design: .rounded))
                Text("Based on HRV, resting HR, and sleep").font(.system(size: 12, design: .rounded)).foregroundStyle(.secondary)
            }
        }
        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
        .background(r.color.opacity(0.08), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(r.color.opacity(0.20), lineWidth: 1))
    }

    private func alertRow(_ alert: FitnessAlert) -> some View {
        HStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 10, style: .continuous).fill(alert.iconColor.opacity(0.15)).frame(width: 36, height: 36)
                Image(systemName: alert.icon).font(.system(size: 16, weight: .semibold)).foregroundStyle(alert.iconColor)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(alert.title).font(.system(size: 14, weight: .bold, design: .rounded))
                Text(alert.subtitle).font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary).lineLimit(2)
            }
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
    }
}

struct QuailFitnessNotificationsPageView: View {
    @EnvironmentObject private var navigator: AppNavigator
    var body: some View {
        QuailFitnessPageShell(
            title: "Notifications",
            onLeadingTap: { navigator.goBack() },
            onTrailingTap: { navigator.show(.fitnessSettings) }
        ) {
            AppPageScroll(contentPadding: 14) { FitnessNotificationsContent() }
        }
    }
}
