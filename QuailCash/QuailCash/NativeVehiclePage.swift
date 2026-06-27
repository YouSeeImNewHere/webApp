import SwiftUI
import UniformTypeIdentifiers

// MARK: - Sheet Router

private enum VehicleSheet: Identifiable {
    case recordMaintenance(typeID: UUID?)
    case recordFuel(pending: PendingGasDetection?)
    case addIssue
    case addCorrective(issueID: UUID?)
    case addTireSet
    case tirePressureCheck
    case editProcedure(MaintenanceProcedure?)

    var id: String {
        switch self {
        case .recordMaintenance(let t): return "rm-\(t?.uuidString ?? "nil")"
        case .recordFuel:               return "recordFuel"
        case .addIssue:                 return "addIssue"
        case .addCorrective(let i):     return "ac-\(i?.uuidString ?? "nil")"
        case .addTireSet:               return "addTire"
        case .tirePressureCheck:        return "pressureCheck"
        case .editProcedure(let p):     return "proc-\(p?.id.uuidString ?? "new")"
        }
    }
}

// MARK: - Quail Car Page Shell

/// Wraps AppChromeFrame with no main bottom bar, then injects the Quail Car
/// Dashboard bar as a safeAreaInset so every Quail Car page shares it.
struct QuailCarPageShell<Content: View>: View {
    @EnvironmentObject private var navigator: AppNavigator
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"

    let title: String
    let badgeValue: Int?
    let homeSelected: Bool
    let onLeadingTap: () -> Void
    let onTrailingTap: () -> Void
    let content: Content

    init(
        title: String,
        badgeValue: Int? = nil,
        homeSelected: Bool = false,
        onLeadingTap: @escaping () -> Void,
        onTrailingTap: @escaping () -> Void,
        @ViewBuilder content: () -> Content
    ) {
        self.title = title
        self.badgeValue = badgeValue
        self.homeSelected = homeSelected
        self.onLeadingTap = onLeadingTap
        self.onTrailingTap = onTrailingTap
        self.content = content()
    }

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        AppChromeFrame(
            title: title,
            badgeValue: badgeValue,
            selectedTab: nil,
            showsBottomBar: false,
            onLeadingTap: onLeadingTap,
            onTrailingTap: onTrailingTap,
            onSelectTab: { _ in }
        ) {
            content
        }
        .safeAreaInset(edge: .bottom, spacing: 0) {
            carBottomBar(palette: palette)
        }
    }

    private func carBottomBar(palette: QuailThemePalette) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                Button { navigator.setRoot(.vehicle) } label: {
                    VStack(spacing: 4) {
                        Image(systemName: "house.fill").font(.system(size: 16, weight: .semibold))
                        Text("Home").font(.system(size: 12, weight: .medium, design: .rounded))
                    }
                    .frame(minWidth: 84)
                    .padding(.vertical, 8)
                    .foregroundStyle(homeSelected ? palette.chromeIconForeground : palette.chromeIconForeground.opacity(0.72))
                    .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(homeSelected ? palette.selectedTabFill : .clear))
                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(homeSelected ? palette.border : .clear, lineWidth: 1))
                }
                .buttonStyle(.plain)
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
}

// MARK: - Main Page

struct VehiclePageView: View {
    @EnvironmentObject private var navigator: AppNavigator
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = VehicleStore.shared

    @State private var activeSheet: VehicleSheet?

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        QuailCarPageShell(
            title: "Quail Car",
            homeSelected: true,
            onLeadingTap: { navigator.show(.vehicleSettings) },
            onTrailingTap: { navigator.show(.vehicleNotifications) }
        ) {
            AppPageScroll(contentPadding: 14) {
                VStack(alignment: .leading, spacing: 14) {
                    profileCard(palette: palette)
                    if let pending = store.pendingGasDetection {
                        gasDetectionBanner(pending: pending, palette: palette)
                    }
                    maintenanceSection(palette: palette)
                    inspectionsSection(palette: palette)
                    fuelSection(palette: palette)
                    tiresSection(palette: palette)
                    issuesSection(palette: palette)
                    proceduresSection(palette: palette)
                    Color.clear.frame(height: 60)
                }
            }
        }
        .sheet(item: $activeSheet) { sheet in
            sheetContent(sheet, palette: palette)
        }
        .task { await store.refresh() }
    }

    @ViewBuilder
    private func sheetContent(_ sheet: VehicleSheet, palette: QuailThemePalette) -> some View {
        switch sheet {
        case .recordMaintenance(let tid):
            RecordMaintenanceSheet(preselectedTypeID: tid, palette: palette)
        case .recordFuel(let pending):
            RecordFuelSheet(pending: pending, palette: palette)
        case .addIssue:
            AddIssueSheet(palette: palette)
        case .addCorrective(let issueID):
            AddCorrectiveSheet(linkedIssueID: issueID, palette: palette)
        case .addTireSet:
            AddTireSetSheet(palette: palette)
        case .tirePressureCheck:
            TirePressureCheckSheet(palette: palette)
        case .editProcedure(let p):
            ProcedureEditSheet(existing: p, palette: palette)
        }
    }
}

// MARK: - Profile Card

private extension VehiclePageView {
    func profileCard(palette: QuailThemePalette) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    if store.profile.isEmpty {
                        Text("Set up your vehicle")
                            .font(.system(size: 18, weight: .bold, design: .rounded))
                        Text("Tap Edit to add your car's details")
                            .font(.system(size: 13, weight: .regular, design: .rounded))
                            .foregroundStyle(.secondary)
                    } else {
                        Text(store.profile.displayName)
                            .font(.system(size: 18, weight: .bold, design: .rounded))
                        if !store.profile.licensePlate.isEmpty {
                            Text(store.profile.licensePlate)
                                .font(.system(size: 13, weight: .semibold, design: .rounded).monospaced())
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                Spacer()
                Button { navigator.show(.vehicleSettings) } label: {
                    Text("Edit")
                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                        .foregroundStyle(palette.accent)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 7)
                        .background(palette.accent.opacity(0.12), in: Capsule())
                }
                .buttonStyle(.plain)
            }

            if !store.profile.isEmpty {
                Divider()
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                    profileStat(label: "Mileage", value: "\(store.profile.currentMileage.formatted()) mi")
                    profileStat(label: "VIN", value: store.profile.vin.isEmpty ? "—" : String(store.profile.vin.suffix(6)))
                    profileStat(label: "Oil", value: store.profile.oilType.isEmpty ? "—" : store.profile.oilType)
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    func profileStat(label: String, value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.system(size: 10, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
            Text(value).font(.system(size: 13, weight: .semibold, design: .rounded)).lineLimit(1)
        }
    }

    func gasDetectionBanner(pending: PendingGasDetection, palette: QuailThemePalette) -> some View {
        HStack(spacing: 12) {
            Image(systemName: "fuelpump.fill")
                .font(.system(size: 18))
                .foregroundStyle(Color(red: 0.95, green: 0.55, blue: 0.10))

            VStack(alignment: .leading, spacing: 2) {
                Text("Gas purchase detected")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                Text("\(pending.merchant) · $\(String(format: "%.2f", pending.amount))")
                    .font(.system(size: 12, weight: .regular, design: .rounded))
                    .foregroundStyle(.secondary)
            }

            Spacer()

            HStack(spacing: 8) {
                Button {
                    activeSheet = .recordFuel(pending: pending)
                } label: {
                    Text("Log It")
                        .font(.system(size: 12, weight: .bold, design: .rounded))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(Color(red: 0.95, green: 0.55, blue: 0.10), in: Capsule())
                }
                .buttonStyle(.plain)

                Button { store.pendingGasDetection = nil } label: {
                    Image(systemName: "xmark").font(.system(size: 12, weight: .bold)).foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(14)
        .background(Color(red: 0.95, green: 0.55, blue: 0.10).opacity(0.10), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Color(red: 0.95, green: 0.55, blue: 0.10).opacity(0.3), lineWidth: 1))
    }
}

// MARK: - Maintenance Section

private extension VehiclePageView {
    func maintenanceSection(palette: QuailThemePalette) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Scheduled Maintenance")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)
                Spacer()
                Button { navigator.show(.vehicleSettings) } label: {
                    Image(systemName: "slider.horizontal.3")
                        .font(.system(size: 14))
                        .foregroundStyle(palette.accent)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 4)

            Button {
                activeSheet = .recordMaintenance(typeID: nil)
            } label: {
                Label("Record Maintenance", systemImage: "plus.circle.fill")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .frame(maxWidth: .infinity, minHeight: 40)
                    .foregroundStyle(palette.primaryButtonText)
                    .background(palette.primaryButton, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
            .buttonStyle(.plain)

            let types = store.maintenanceTypes.filter { $0.isEnabled }
            VStack(spacing: 0) {
                ForEach(Array(types.enumerated()), id: \.element.id) { idx, type in
                    maintenanceRow(type: type, palette: palette)
                    if idx < types.count - 1 {
                        Divider().padding(.leading, 52)
                    }
                }
            }
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }

    func maintenanceRow(type: MaintenanceTypeDefinition, palette: QuailThemePalette) -> some View {
        let st = store.status(for: type)
        let last = store.lastRecord(for: type.id)

        return Button {
            activeSheet = .recordMaintenance(typeID: type.id)
        } label: {
            HStack(spacing: 12) {
                ZStack {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(type.colorName.color.opacity(0.15))
                        .frame(width: 36, height: 36)
                    Image(systemName: type.icon)
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(type.colorName.color)
                }

                VStack(alignment: .leading, spacing: 2) {
                    Text(type.name)
                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                        .foregroundStyle(.primary)
                    Text(last == nil ? "Never recorded" : "Last: \(last!.date.formatted(date: .abbreviated, time: .omitted))")
                        .font(.system(size: 11, weight: .regular, design: .rounded))
                        .foregroundStyle(.secondary)
                }

                Spacer(minLength: 8)

                VStack(alignment: .trailing, spacing: 3) {
                    Text(store.nextDueDescription(for: type))
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.trailing)
                    statusPill(st, palette: palette)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Inspections Section

private extension VehiclePageView {
    func inspectionsSection(palette: QuailThemePalette) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Inspections")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)
                Spacer()
                Button { navigator.show(.vehicleSettings) } label: {
                    Image(systemName: "slider.horizontal.3")
                        .font(.system(size: 14))
                        .foregroundStyle(palette.accent)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 4)

            let weekly = store.inspectionItems.filter { $0.periodicityDays <= 7 }
            let monthly = store.inspectionItems.filter { $0.periodicityDays > 7 }

            if !weekly.isEmpty {
                inspectionGroup(title: "Weekly", items: weekly, palette: palette)
            }
            if !monthly.isEmpty {
                inspectionGroup(title: "Monthly", items: monthly, palette: palette)
            }
        }
    }

    func inspectionGroup(title: String, items: [InspectionCheckItem], palette: QuailThemePalette) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title)
                .font(.system(size: 11, weight: .bold, design: .rounded))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 14)
                .padding(.top, 12)
                .padding(.bottom, 6)

            ForEach(Array(items.enumerated()), id: \.element.id) { idx, item in
                HStack(spacing: 12) {
                    Button {
                        store.checkInspectionItem(item.id)
                    } label: {
                        Image(systemName: item.isDue ? "circle" : "checkmark.circle.fill")
                            .font(.system(size: 22))
                            .foregroundStyle(item.isDue ? palette.border : palette.positive)
                            .animation(.easeInOut(duration: 0.15), value: item.isDue)
                    }
                    .buttonStyle(.plain)

                    VStack(alignment: .leading, spacing: 1) {
                        Text(item.name)
                            .font(.system(size: 14, weight: .medium, design: .rounded))
                        if let last = item.lastCheckedDate, !item.isDue {
                            Text("Checked \(last.formatted(.relative(presentation: .named)))")
                                .font(.system(size: 11, weight: .regular, design: .rounded))
                                .foregroundStyle(.secondary)
                        } else if !item.isDue {
                            Text("Due")
                                .font(.system(size: 11, weight: .regular, design: .rounded))
                                .foregroundStyle(Color(red: 0.95, green: 0.60, blue: 0.10))
                        } else {
                            Text(item.isDue ? "Needs check" : "OK")
                                .font(.system(size: 11, weight: .regular, design: .rounded))
                                .foregroundStyle(item.isDue ? .secondary : palette.positive)
                        }
                    }

                    Spacer()

                    if item.isDue {
                        Text("Due")
                            .font(.system(size: 10, weight: .bold, design: .rounded))
                            .foregroundStyle(.white)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(Color(red: 0.95, green: 0.60, blue: 0.10), in: Capsule())
                    }
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 10)

                if idx < items.count - 1 {
                    Divider().padding(.leading, 52)
                }
            }

            Spacer(minLength: 10)
        }
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

// MARK: - Fuel Section

private extension VehiclePageView {
    func fuelSection(palette: QuailThemePalette) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Fuel & Mileage")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)
                Spacer()
                Button { activeSheet = .recordFuel(pending: nil) } label: {
                    Label("Log Fill-Up", systemImage: "plus")
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundStyle(palette.accent)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 4)

            VStack(alignment: .leading, spacing: 12) {
                if let mpg = store.averageMPG() {
                    HStack(alignment: .firstTextBaseline, spacing: 4) {
                        Text(String(format: "%.1f", mpg))
                            .font(.system(size: 36, weight: .bold, design: .rounded))
                        Text("MPG avg")
                            .font(.system(size: 14, weight: .semibold, design: .rounded))
                            .foregroundStyle(.secondary)
                            .padding(.bottom, 3)
                    }
                    Divider()
                } else {
                    Text("Log at least 2 fill-ups to calculate MPG")
                        .font(.system(size: 13, weight: .regular, design: .rounded))
                        .foregroundStyle(.secondary)
                }

                let recent = store.fuelRecords.sorted { $0.date > $1.date }.prefix(3)
                if recent.isEmpty {
                    Text("No fill-ups logged yet")
                        .font(.system(size: 13, weight: .regular, design: .rounded))
                        .foregroundStyle(.secondary)
                } else {
                    VStack(spacing: 8) {
                        ForEach(recent) { record in
                            fuelRecordRow(record: record, palette: palette)
                        }
                    }
                }
            }
            .padding(16)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }

    func fuelRecordRow(record: FuelRecord, palette: QuailThemePalette) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(record.date.formatted(date: .abbreviated, time: .omitted))
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                Text(record.stationName.isEmpty ? "\(record.mileage.formatted()) mi" : "\(record.stationName) · \(record.mileage.formatted()) mi")
                    .font(.system(size: 11, weight: .regular, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text(String(format: "%.3f gal", record.gallons))
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                if let cost = record.totalCost {
                    Text(String(format: "$%.2f", cost))
                        .font(.system(size: 11, weight: .regular, design: .rounded))
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}

// MARK: - Tires Section

private extension VehiclePageView {
    func tiresSection(palette: QuailThemePalette) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Tires")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)
                Spacer()
                Button { activeSheet = .addTireSet } label: {
                    Label("Add Set", systemImage: "plus")
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundStyle(palette.accent)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 4)

            if let tires = store.activeTireSet {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(alignment: .top) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(tires.displayName)
                                .font(.system(size: 15, weight: .bold, design: .rounded))
                            Text("On since \(tires.installDate.formatted(date: .abbreviated, time: .omitted)) · \(tires.installMileage.formatted()) mi")
                                .font(.system(size: 12, weight: .regular, design: .rounded))
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button { activeSheet = .tirePressureCheck } label: {
                            Text("Check Pressure")
                                .font(.system(size: 12, weight: .semibold, design: .rounded))
                                .foregroundStyle(palette.accent)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 6)
                                .background(palette.accent.opacity(0.12), in: Capsule())
                        }
                        .buttonStyle(.plain)
                    }

                    Divider()

                    HStack(spacing: 0) {
                        tireStatBox(label: "Required F", value: "\(tires.requiredPressureFront) PSI")
                        Divider().frame(height: 32)
                        tireStatBox(label: "Required R", value: "\(tires.requiredPressureRear) PSI")
                        if let last = tires.lastPressureCheck {
                            Divider().frame(height: 32)
                            tireStatBox(label: "Last Check", value: last.date.formatted(date: .abbreviated, time: .omitted))
                        }
                    }

                    if let last = tires.lastPressureCheck {
                        Divider()
                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                            pressureCell(pos: "FL", psi: last.frontLeft, required: tires.requiredPressureFront, palette: palette)
                            pressureCell(pos: "FR", psi: last.frontRight, required: tires.requiredPressureFront, palette: palette)
                            pressureCell(pos: "RL", psi: last.rearLeft, required: tires.requiredPressureRear, palette: palette)
                            pressureCell(pos: "RR", psi: last.rearRight, required: tires.requiredPressureRear, palette: palette)
                        }
                    }
                }
                .padding(16)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
            } else {
                emptyCard(icon: "circle.grid.cross.fill", text: "No active tire set", action: "Add Tires", palette: palette) {
                    activeSheet = .addTireSet
                }
            }
        }
    }

    func tireStatBox(label: String, value: String) -> some View {
        VStack(alignment: .center, spacing: 2) {
            Text(value).font(.system(size: 13, weight: .bold, design: .rounded))
            Text(label).font(.system(size: 10, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    func pressureCell(pos: String, psi: Int, required: Int, palette: QuailThemePalette) -> some View {
        let delta = psi - required
        let color: Color = abs(delta) <= 3 ? palette.positive :
                           abs(delta) <= 6 ? Color(red: 0.95, green: 0.60, blue: 0.10) : palette.negative
        return VStack(spacing: 3) {
            Text(pos).font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
            Text("\(psi)").font(.system(size: 16, weight: .bold, design: .rounded)).foregroundStyle(color)
            Text("PSI").font(.system(size: 9, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 8)
        .background(color.opacity(0.10), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }
}

// MARK: - Issues & Corrective Section

private extension VehiclePageView {
    func issuesSection(palette: QuailThemePalette) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Issues & Repairs")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)
                Spacer()
                Button { activeSheet = .addIssue } label: {
                    Label("Report Issue", systemImage: "exclamationmark.triangle")
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundStyle(palette.negative)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 4)

            let open = store.openIssues
            let corrective = store.correctiveRecords.sorted { $0.date > $1.date }.prefix(3)

            if open.isEmpty && corrective.isEmpty {
                emptyCard(icon: "checkmark.shield.fill", text: "No open issues", action: "Report an Issue", palette: palette) {
                    activeSheet = .addIssue
                }
            } else {
                VStack(spacing: 0) {
                    if !open.isEmpty {
                        HStack {
                            Text("OPEN ISSUES").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                            Spacer()
                        }
                        .padding(.horizontal, 14)
                        .padding(.top, 12)
                        .padding(.bottom, 4)

                        ForEach(Array(open.enumerated()), id: \.element.id) { idx, issue in
                            issueRow(issue: issue, palette: palette)
                            Divider().padding(.leading, 14)
                        }

                        Button { activeSheet = .addCorrective(issueID: nil) } label: {
                            Label("Record Repair", systemImage: "wrench.and.screwdriver.fill")
                                .font(.system(size: 13, weight: .semibold, design: .rounded))
                                .foregroundStyle(palette.accent)
                                .frame(maxWidth: .infinity, minHeight: 40)
                        }
                        .buttonStyle(.plain)
                        .padding(.horizontal, 14)
                        .padding(.bottom, 8)
                    }

                    if !corrective.isEmpty {
                        HStack {
                            Text("RECENT REPAIRS").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                            Spacer()
                            Button { activeSheet = .addCorrective(issueID: nil) } label: {
                                Image(systemName: "plus").font(.system(size: 12)).foregroundStyle(palette.accent)
                            }.buttonStyle(.plain)
                        }
                        .padding(.horizontal, 14)
                        .padding(.top, open.isEmpty ? 12 : 4)
                        .padding(.bottom, 4)

                        ForEach(Array(corrective.enumerated()), id: \.element.id) { idx, rec in
                            correctiveRow(rec: rec, palette: palette)
                            if idx < corrective.count - 1 { Divider().padding(.leading, 14) }
                        }
                        Spacer(minLength: 12)
                    }
                }
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
            }
        }
    }

    func issueRow(issue: VehicleIssue, palette: QuailThemePalette) -> some View {
        HStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 16))
                .foregroundStyle(palette.negative)
                .frame(width: 24)

            VStack(alignment: .leading, spacing: 2) {
                Text(issue.title.isEmpty ? "Untitled Issue" : issue.title)
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                Text("\(issue.dateNoticed.formatted(date: .abbreviated, time: .omitted)) · \(issue.mileageNoticed.formatted()) mi")
                    .font(.system(size: 11, weight: .regular, design: .rounded))
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Button { activeSheet = .addCorrective(issueID: issue.id) } label: {
                Text("Fix")
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .foregroundStyle(palette.accent)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(palette.accent.opacity(0.12), in: Capsule())
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    func correctiveRow(rec: CorrectiveRecord, palette: QuailThemePalette) -> some View {
        HStack(spacing: 12) {
            Image(systemName: "wrench.and.screwdriver.fill")
                .font(.system(size: 14))
                .foregroundStyle(palette.accent)
                .frame(width: 24)

            VStack(alignment: .leading, spacing: 2) {
                Text(rec.description.isEmpty ? "Repair" : rec.description)
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .lineLimit(1)
                Text("\(rec.date.formatted(date: .abbreviated, time: .omitted)) · \(rec.mileage.formatted()) mi")
                    .font(.system(size: 11, weight: .regular, design: .rounded))
                    .foregroundStyle(.secondary)
            }

            Spacer()

            if rec.resolvedIssue {
                Image(systemName: "checkmark.circle.fill").foregroundStyle(palette.positive)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }
}

// MARK: - Procedures Section

private extension VehiclePageView {
    func proceduresSection(palette: QuailThemePalette) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("DIY Procedures")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)
                Spacer()
                Button { activeSheet = .editProcedure(nil) } label: {
                    Label("New", systemImage: "plus")
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundStyle(palette.accent)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 4)

            if store.procedures.isEmpty {
                emptyCard(icon: "doc.text.fill", text: "No procedures saved", action: "Write a Procedure", palette: palette) {
                    activeSheet = .editProcedure(nil)
                }
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(store.procedures.enumerated()), id: \.element.id) { idx, proc in
                        Button { activeSheet = .editProcedure(proc) } label: {
                            HStack(spacing: 12) {
                                Image(systemName: "doc.text")
                                    .font(.system(size: 15))
                                    .foregroundStyle(palette.accent)
                                    .frame(width: 24)

                                VStack(alignment: .leading, spacing: 2) {
                                    Text(proc.title.isEmpty ? "Untitled" : proc.title)
                                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                                        .foregroundStyle(.primary)
                                    Text("\(proc.steps.count) steps · \(proc.tools.count) tools")
                                        .font(.system(size: 11, weight: .regular, design: .rounded))
                                        .foregroundStyle(.secondary)
                                }

                                Spacer()
                                Image(systemName: "chevron.right")
                                    .font(.system(size: 12, weight: .semibold))
                                    .foregroundStyle(.tertiary)
                            }
                            .padding(.horizontal, 14)
                            .padding(.vertical, 12)
                        }
                        .buttonStyle(.plain)
                        if idx < store.procedures.count - 1 { Divider().padding(.leading, 52) }
                    }
                }
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
            }
        }
    }
}

// MARK: - Shared Helpers

private extension VehiclePageView {
    func statusPill(_ status: VehicleMaintenanceStatus, palette: QuailThemePalette) -> some View {
        let label: String
        let color: Color
        switch status {
        case .ok:      label = "OK";       color = palette.positive
        case .dueSoon: label = "Due Soon"; color = Color(red: 0.95, green: 0.60, blue: 0.10)
        case .overdue: label = "Overdue";  color = palette.negative
        case .never:   label = "Never";    color = Color(UIColor.secondaryLabel)
        }
        let isNever = status == .never
        return Text(label)
            .font(.system(size: 10, weight: .bold, design: .rounded))
            .foregroundStyle(isNever ? Color(UIColor.secondaryLabel) : Color.white)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(isNever ? Color(UIColor.secondaryLabel).opacity(0.15) : color, in: Capsule())
    }

    func emptyCard(icon: String, text: String, action: String, palette: QuailThemePalette, onTap: @escaping () -> Void) -> some View {
        VStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 24))
                .foregroundStyle(palette.accent.opacity(0.5))
            Text(text)
                .font(.system(size: 13, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
            Button(action: onTap) {
                Text(action)
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                    .foregroundStyle(palette.accent)
            }
            .buttonStyle(.plain)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

// MARK: - Vehicle Profile Edit Sheet

private struct VehicleProfileEditSheet: View {
    @ObservedObject private var store = VehicleStore.shared
    @Environment(\.dismiss) private var dismiss
    let palette: QuailThemePalette
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"

    @State private var profile: VehicleProfile

    init(palette: QuailThemePalette) {
        self.palette = palette
        _profile = State(initialValue: VehicleStore.shared.profile)
    }

    var body: some View {
        VehicleSheetContainer(title: "Vehicle Profile", palette: palette, onDismiss: { dismiss() }) {
            Group {
                sheetSection("Identity") {
                    sheetField("Make", value: $profile.make, palette: palette)
                    sheetField("Model", value: $profile.model, palette: palette)
                    sheetIntField("Year", value: $profile.year, palette: palette)
                    sheetField("VIN", value: $profile.vin, palette: palette)
                    sheetField("License Plate", value: $profile.licensePlate, palette: palette)
                    sheetIntField("Current Mileage", value: $profile.currentMileage, palette: palette)
                }

                sheetSection("Engine Oil") {
                    sheetField("Oil Type (e.g. 5W-30)", value: $profile.oilType, palette: palette)
                    sheetDoubleField("Capacity w/ Filter (qt)", value: $profile.oilCapacityWithFilter, palette: palette)
                    sheetDoubleField("Capacity w/o Filter (qt)", value: $profile.oilCapacityWithoutFilter, palette: palette)
                }

                sheetSection("Transmission") {
                    sheetField("Fluid Type", value: $profile.transmissionFluidType, palette: palette)
                    sheetDoubleField("Fluid Capacity (qt)", value: $profile.transmissionFluidCapacity, palette: palette)
                }

                sheetSection("Coolant") {
                    sheetField("Coolant Type", value: $profile.coolantType, palette: palette)
                }
            }

            Button {
                store.profile = profile
                store.save()
                dismiss()
            } label: {
                Text("Save")
                    .font(.system(size: 15, weight: .semibold, design: .rounded))
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .foregroundStyle(palette.primaryButtonText)
                    .background(palette.primaryButton, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .buttonStyle(.plain)
        }
    }
}

// MARK: - Record Maintenance Sheet

private struct RecordMaintenanceSheet: View {
    @ObservedObject private var store = VehicleStore.shared
    @Environment(\.dismiss) private var dismiss
    let preselectedTypeID: UUID?
    let palette: QuailThemePalette

    @State private var selectedTypeID: UUID?
    @State private var date = Date()
    @State private var mileageStr = ""
    @State private var isShop = false
    @State private var shopName = ""
    @State private var transactionRef = ""
    @State private var costStr = ""
    @State private var notes = ""
    @State private var showTypePicker = false

    init(preselectedTypeID: UUID?, palette: QuailThemePalette) {
        self.preselectedTypeID = preselectedTypeID
        self.palette = palette
        _selectedTypeID = State(initialValue: preselectedTypeID)
        _mileageStr = State(initialValue: VehicleStore.shared.profile.currentMileage > 0
                            ? String(VehicleStore.shared.profile.currentMileage) : "")
    }

    private var selectedType: MaintenanceTypeDefinition? {
        guard let id = selectedTypeID else { return nil }
        return store.maintenanceTypes.first { $0.id == id }
    }

    var body: some View {
        VehicleSheetContainer(title: "Record Maintenance", palette: palette, onDismiss: { dismiss() }) {
            // Type picker
            VStack(alignment: .leading, spacing: 6) {
                Text("Service Type")
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)

                Button { showTypePicker.toggle() } label: {
                    HStack {
                        if let type = selectedType {
                            Image(systemName: type.icon).foregroundStyle(type.colorName.color)
                            Text(type.name).font(.system(size: 14, weight: .medium, design: .rounded)).foregroundStyle(.primary)
                        } else {
                            Text("Select service type...").font(.system(size: 14, design: .rounded)).foregroundStyle(.secondary)
                        }
                        Spacer()
                        Image(systemName: showTypePicker ? "chevron.up" : "chevron.down")
                            .font(.system(size: 12)).foregroundStyle(.secondary)
                    }
                    .padding(12)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
                }
                .buttonStyle(.plain)

                if showTypePicker {
                    VStack(spacing: 0) {
                        ForEach(store.maintenanceTypes.filter { $0.isEnabled }) { type in
                            Button {
                                selectedTypeID = type.id
                                showTypePicker = false
                            } label: {
                                HStack(spacing: 10) {
                                    Image(systemName: type.icon).foregroundStyle(type.colorName.color).frame(width: 20)
                                    Text(type.name).font(.system(size: 14, weight: .medium, design: .rounded)).foregroundStyle(.primary)
                                    Spacer()
                                    if selectedTypeID == type.id {
                                        Image(systemName: "checkmark").foregroundStyle(palette.accent)
                                    }
                                }
                                .padding(.horizontal, 12)
                                .padding(.vertical, 10)
                            }
                            .buttonStyle(.plain)
                            Divider().padding(.leading, 12)
                        }
                    }
                    .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
                }
            }

            VStack(spacing: 10) {
                DatePicker("Date", selection: $date, displayedComponents: .date)
                    .font(.system(size: 14, design: .rounded))
                    .padding(12)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))

                sheetField("Mileage", value: $mileageStr, keyboard: .numberPad, palette: palette)
                sheetField("Cost (optional)", value: $costStr, keyboard: .decimalPad, palette: palette)
            }

            VStack(alignment: .leading, spacing: 8) {
                Toggle(isOn: $isShop) {
                    Text("Shop Performed")
                        .font(.system(size: 14, weight: .medium, design: .rounded))
                }
                .tint(palette.accent)
                .padding(12)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))

                if isShop {
                    sheetField("Shop Name", value: $shopName, palette: palette)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Link Transaction (optional)")
                            .font(.system(size: 12, weight: .semibold, design: .rounded))
                            .foregroundStyle(.secondary)
                        TextField("Transaction ID or description", text: $transactionRef)
                            .font(.system(size: 14, design: .rounded))
                            .padding(12)
                            .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
                        Text("Paste a transaction ID to link this service record to a bank transaction.")
                            .font(.system(size: 11, weight: .regular, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }
            }

            sheetField("Notes (optional)", value: $notes, palette: palette)

            Button {
                guard let typeID = selectedTypeID,
                      let type = selectedType,
                      let mileage = Int(mileageStr) else { return }
                store.addMaintenanceRecord(MaintenanceRecord(
                    typeID: typeID,
                    typeName: type.name,
                    date: date,
                    mileage: mileage,
                    isShopPerformed: isShop,
                    shopName: shopName,
                    linkedTransactionID: transactionRef,
                    cost: Double(costStr.replacingOccurrences(of: "$", with: "")),
                    notes: notes
                ))
                dismiss()
            } label: {
                Text("Save Record")
                    .font(.system(size: 15, weight: .semibold, design: .rounded))
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .foregroundStyle(selectedTypeID == nil || mileageStr.isEmpty ? .secondary : palette.primaryButtonText)
                    .background(
                        selectedTypeID == nil || mileageStr.isEmpty ? palette.border : palette.primaryButton,
                        in: RoundedRectangle(cornerRadius: 14, style: .continuous)
                    )
            }
            .buttonStyle(.plain)
            .disabled(selectedTypeID == nil || mileageStr.isEmpty)
        }
    }
}

// MARK: - Record Fuel Sheet

private struct RecordFuelSheet: View {
    @ObservedObject private var store = VehicleStore.shared
    @Environment(\.dismiss) private var dismiss
    let pending: PendingGasDetection?
    let palette: QuailThemePalette

    @State private var date: Date
    @State private var mileageStr: String
    @State private var gallonsStr = ""
    @State private var priceStr = ""
    @State private var stationName: String
    @State private var transactionRef: String
    @State private var notes = ""

    init(pending: PendingGasDetection?, palette: QuailThemePalette) {
        self.pending = pending
        self.palette = palette
        let current = VehicleStore.shared.profile.currentMileage
        _date = State(initialValue: pending?.date ?? Date())
        _mileageStr = State(initialValue: current > 0 ? String(current) : "")
        _stationName = State(initialValue: pending?.merchant ?? "")
        _transactionRef = State(initialValue: pending?.transactionID ?? "")
    }

    var body: some View {
        VehicleSheetContainer(title: "Log Fill-Up", palette: palette, onDismiss: { dismiss() }) {
            if let pending {
                HStack(spacing: 10) {
                    Image(systemName: "link").foregroundStyle(palette.accent)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Linked to transaction")
                            .font(.system(size: 13, weight: .semibold, design: .rounded))
                        Text("\(pending.merchant) · $\(String(format: "%.2f", pending.amount))")
                            .font(.system(size: 12, weight: .regular, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(12)
                .background(palette.accent.opacity(0.10), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.accent.opacity(0.3), lineWidth: 1))
            }

            DatePicker("Date", selection: $date, displayedComponents: .date)
                .font(.system(size: 14, design: .rounded))
                .padding(12)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))

            sheetField("Current Mileage", value: $mileageStr, keyboard: .numberPad, palette: palette)
            sheetField("Gallons Pumped", value: $gallonsStr, keyboard: .decimalPad, palette: palette)
            sheetField("Price per Gallon (optional)", value: $priceStr, keyboard: .decimalPad, palette: palette)
            sheetField("Station Name (optional)", value: $stationName, palette: palette)

            if pending == nil {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Link Transaction (optional)")
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundStyle(.secondary)
                    TextField("Transaction ID or description", text: $transactionRef)
                        .font(.system(size: 14, design: .rounded))
                        .padding(12)
                        .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
                }
            }

            sheetField("Notes (optional)", value: $notes, palette: palette)

            Button {
                guard let mileage = Int(mileageStr),
                      let gallons = Double(gallonsStr), gallons > 0 else { return }
                store.addFuelRecord(FuelRecord(
                    date: date,
                    mileage: mileage,
                    gallons: gallons,
                    pricePerGallon: Double(priceStr),
                    stationName: stationName,
                    linkedTransactionID: transactionRef,
                    notes: notes
                ))
                store.pendingGasDetection = nil
                dismiss()
            } label: {
                Text("Save Fill-Up")
                    .font(.system(size: 15, weight: .semibold, design: .rounded))
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .foregroundStyle(mileageStr.isEmpty || gallonsStr.isEmpty ? .secondary : palette.primaryButtonText)
                    .background(
                        mileageStr.isEmpty || gallonsStr.isEmpty ? palette.border : palette.primaryButton,
                        in: RoundedRectangle(cornerRadius: 14, style: .continuous)
                    )
            }
            .buttonStyle(.plain)
            .disabled(mileageStr.isEmpty || gallonsStr.isEmpty)
        }
    }
}

// MARK: - Add Issue Sheet

private struct AddIssueSheet: View {
    @ObservedObject private var store = VehicleStore.shared
    @Environment(\.dismiss) private var dismiss
    let palette: QuailThemePalette

    @State private var title = ""
    @State private var description = ""
    @State private var howOccurred = ""
    @State private var date = Date()
    @State private var mileageStr: String

    init(palette: QuailThemePalette) {
        self.palette = palette
        _mileageStr = State(initialValue: VehicleStore.shared.profile.currentMileage > 0
                            ? String(VehicleStore.shared.profile.currentMileage) : "")
    }

    var body: some View {
        VehicleSheetContainer(title: "Report Issue", palette: palette, onDismiss: { dismiss() }) {
            sheetField("Title (required)", value: $title, palette: palette)

            DatePicker("Date Noticed", selection: $date, displayedComponents: .date)
                .font(.system(size: 14, design: .rounded))
                .padding(12)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))

            sheetField("Mileage When Noticed", value: $mileageStr, keyboard: .numberPad, palette: palette)

            VStack(alignment: .leading, spacing: 4) {
                Text("Description").font(.system(size: 12, weight: .semibold, design: .rounded)).foregroundStyle(.secondary)
                TextEditor(text: $description)
                    .font(.system(size: 14, design: .rounded))
                    .frame(minHeight: 80)
                    .padding(10)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
            }

            sheetField("How / When It Occurred (optional)", value: $howOccurred, palette: palette)

            Button {
                guard !title.isEmpty else { return }
                store.addIssue(VehicleIssue(
                    dateNoticed: date,
                    mileageNoticed: Int(mileageStr) ?? store.profile.currentMileage,
                    title: title,
                    description: description,
                    howOccurred: howOccurred
                ))
                dismiss()
            } label: {
                Text("Report Issue")
                    .font(.system(size: 15, weight: .semibold, design: .rounded))
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .foregroundStyle(title.isEmpty ? .secondary : palette.primaryButtonText)
                    .background(title.isEmpty ? palette.border : palette.negative, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .buttonStyle(.plain)
            .disabled(title.isEmpty)
        }
    }
}

// MARK: - Add Corrective Sheet

private struct AddCorrectiveSheet: View {
    @ObservedObject private var store = VehicleStore.shared
    @Environment(\.dismiss) private var dismiss
    let linkedIssueID: UUID?
    let palette: QuailThemePalette

    @State private var description = ""
    @State private var reason = ""
    @State private var date = Date()
    @State private var mileageStr: String
    @State private var parts: [String] = []
    @State private var newPart = ""
    @State private var costStr = ""
    @State private var resolvedIssue: Bool
    @State private var selectedIssueID: UUID?
    @State private var notes = ""

    init(linkedIssueID: UUID?, palette: QuailThemePalette) {
        self.linkedIssueID = linkedIssueID
        self.palette = palette
        _resolvedIssue = State(initialValue: linkedIssueID != nil)
        _selectedIssueID = State(initialValue: linkedIssueID)
        _mileageStr = State(initialValue: VehicleStore.shared.profile.currentMileage > 0
                            ? String(VehicleStore.shared.profile.currentMileage) : "")
    }

    var body: some View {
        VehicleSheetContainer(title: "Record Repair", palette: palette, onDismiss: { dismiss() }) {
            sheetField("Description (required)", value: $description, palette: palette)
            sheetField("Reason / Root Cause", value: $reason, palette: palette)

            DatePicker("Date", selection: $date, displayedComponents: .date)
                .font(.system(size: 14, design: .rounded))
                .padding(12)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))

            sheetField("Mileage", value: $mileageStr, keyboard: .numberPad, palette: palette)
            sheetField("Cost (optional)", value: $costStr, keyboard: .decimalPad, palette: palette)

            VStack(alignment: .leading, spacing: 6) {
                Text("Parts Replaced")
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)

                ForEach(parts, id: \.self) { part in
                    HStack {
                        Text(part).font(.system(size: 14, design: .rounded))
                        Spacer()
                        Button { parts.removeAll { $0 == part } } label: {
                            Image(systemName: "minus.circle.fill").foregroundStyle(palette.negative)
                        }.buttonStyle(.plain)
                    }
                    .padding(10)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(palette.border, lineWidth: 1))
                }

                HStack(spacing: 8) {
                    TextField("Add part...", text: $newPart)
                        .font(.system(size: 14, design: .rounded))
                        .padding(10)
                        .background(palette.surface, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(palette.border, lineWidth: 1))

                    Button {
                        let trimmed = newPart.trimmingCharacters(in: .whitespaces)
                        if !trimmed.isEmpty { parts.append(trimmed); newPart = "" }
                    } label: {
                        Image(systemName: "plus.circle.fill").font(.system(size: 22)).foregroundStyle(palette.accent)
                    }
                    .buttonStyle(.plain)
                }
            }

            if !store.openIssues.isEmpty {
                Toggle(isOn: $resolvedIssue) {
                    Text("Resolves an Open Issue")
                        .font(.system(size: 14, weight: .medium, design: .rounded))
                }
                .tint(palette.accent)
                .padding(12)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))

                if resolvedIssue {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Which Issue")
                            .font(.system(size: 12, weight: .semibold, design: .rounded))
                            .foregroundStyle(.secondary)
                        VStack(spacing: 0) {
                            ForEach(store.openIssues) { issue in
                                Button {
                                    selectedIssueID = issue.id
                                } label: {
                                    HStack {
                                        Text(issue.title.isEmpty ? "Untitled Issue" : issue.title)
                                            .font(.system(size: 14, design: .rounded))
                                            .foregroundStyle(.primary)
                                        Spacer()
                                        if selectedIssueID == issue.id {
                                            Image(systemName: "checkmark").foregroundStyle(palette.accent)
                                        }
                                    }
                                    .padding(10)
                                }
                                .buttonStyle(.plain)
                                Divider()
                            }
                        }
                        .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
                    }
                }
            }

            sheetField("Notes (optional)", value: $notes, palette: palette)

            Button {
                guard !description.isEmpty else { return }
                store.addCorrectiveRecord(CorrectiveRecord(
                    date: date,
                    mileage: Int(mileageStr) ?? store.profile.currentMileage,
                    description: description,
                    reason: reason,
                    partsReplaced: parts,
                    cost: Double(costStr),
                    resolvedIssue: resolvedIssue,
                    linkedIssueID: resolvedIssue ? selectedIssueID : nil,
                    notes: notes
                ))
                dismiss()
            } label: {
                Text("Save Repair")
                    .font(.system(size: 15, weight: .semibold, design: .rounded))
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .foregroundStyle(description.isEmpty ? .secondary : palette.primaryButtonText)
                    .background(description.isEmpty ? palette.border : palette.primaryButton, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .buttonStyle(.plain)
            .disabled(description.isEmpty)
        }
    }
}

// MARK: - Add Tire Set Sheet

private struct AddTireSetSheet: View {
    @ObservedObject private var store = VehicleStore.shared
    @Environment(\.dismiss) private var dismiss
    let palette: QuailThemePalette

    @State private var brand = ""
    @State private var model = ""
    @State private var size = ""
    @State private var installDate = Date()
    @State private var installMileageStr: String
    @State private var frontPressure = 35
    @State private var rearPressure = 35
    @State private var isActive = true

    init(palette: QuailThemePalette) {
        self.palette = palette
        _installMileageStr = State(initialValue: VehicleStore.shared.profile.currentMileage > 0
                                   ? String(VehicleStore.shared.profile.currentMileage) : "")
    }

    var body: some View {
        VehicleSheetContainer(title: "Add Tire Set", palette: palette, onDismiss: { dismiss() }) {
            sheetField("Brand (e.g. Michelin)", value: $brand, palette: palette)
            sheetField("Model (e.g. Pilot Sport 4)", value: $model, palette: palette)
            sheetField("Size (e.g. 225/45R17)", value: $size, palette: palette)

            DatePicker("Install Date", selection: $installDate, displayedComponents: .date)
                .font(.system(size: 14, design: .rounded))
                .padding(12)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))

            sheetField("Install Mileage", value: $installMileageStr, keyboard: .numberPad, palette: palette)

            VStack(spacing: 10) {
                Stepper("Front Pressure: \(frontPressure) PSI", value: $frontPressure, in: 20...60)
                    .font(.system(size: 14, design: .rounded))
                    .padding(12)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))

                Stepper("Rear Pressure: \(rearPressure) PSI", value: $rearPressure, in: 20...60)
                    .font(.system(size: 14, design: .rounded))
                    .padding(12)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
            }

            Toggle(isOn: $isActive) {
                Text("Set as Active Tires")
                    .font(.system(size: 14, weight: .medium, design: .rounded))
            }
            .tint(palette.accent)
            .padding(12)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))

            Button {
                store.addTireSet(TireSet(
                    brand: brand,
                    model: model,
                    size: size,
                    installDate: installDate,
                    installMileage: Int(installMileageStr) ?? 0,
                    requiredPressureFront: frontPressure,
                    requiredPressureRear: rearPressure,
                    isActive: isActive
                ))
                dismiss()
            } label: {
                Text("Save Tire Set")
                    .font(.system(size: 15, weight: .semibold, design: .rounded))
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .foregroundStyle(palette.primaryButtonText)
                    .background(palette.primaryButton, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .buttonStyle(.plain)
        }
    }
}

// MARK: - Tire Pressure Check Sheet

private struct TirePressureCheckSheet: View {
    @ObservedObject private var store = VehicleStore.shared
    @Environment(\.dismiss) private var dismiss
    let palette: QuailThemePalette

    @State private var date = Date()
    @State private var mileageStr: String
    @State private var fl = 35
    @State private var fr = 35
    @State private var rl = 35
    @State private var rr = 35
    @State private var notes = ""

    init(palette: QuailThemePalette) {
        self.palette = palette
        let current = VehicleStore.shared.profile.currentMileage
        _mileageStr = State(initialValue: current > 0 ? String(current) : "")
        if let tires = VehicleStore.shared.activeTireSet {
            _fl = State(initialValue: tires.requiredPressureFront)
            _fr = State(initialValue: tires.requiredPressureFront)
            _rl = State(initialValue: tires.requiredPressureRear)
            _rr = State(initialValue: tires.requiredPressureRear)
        }
    }

    var body: some View {
        VehicleSheetContainer(title: "Pressure Check", palette: palette, onDismiss: { dismiss() }) {
            DatePicker("Date", selection: $date, displayedComponents: .date)
                .font(.system(size: 14, design: .rounded))
                .padding(12)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))

            sheetField("Mileage", value: $mileageStr, keyboard: .numberPad, palette: palette)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                pressureStepper(label: "Front Left", value: $fl, palette: palette)
                pressureStepper(label: "Front Right", value: $fr, palette: palette)
                pressureStepper(label: "Rear Left", value: $rl, palette: palette)
                pressureStepper(label: "Rear Right", value: $rr, palette: palette)
            }

            sheetField("Notes (optional)", value: $notes, palette: palette)

            Button {
                guard let tires = store.activeTireSet else { return }
                store.addPressureCheck(
                    TirePressureCheck(
                        date: date,
                        mileage: Int(mileageStr) ?? store.profile.currentMileage,
                        frontLeft: fl, frontRight: fr, rearLeft: rl, rearRight: rr,
                        notes: notes
                    ),
                    tireID: tires.id
                )
                dismiss()
            } label: {
                Text("Save Check")
                    .font(.system(size: 15, weight: .semibold, design: .rounded))
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .foregroundStyle(palette.primaryButtonText)
                    .background(palette.primaryButton, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .buttonStyle(.plain)
        }
    }

    private func pressureStepper(label: String, value: Binding<Int>, palette: QuailThemePalette) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(.system(size: 11, weight: .semibold, design: .rounded)).foregroundStyle(.secondary)
            HStack {
                Button { value.wrappedValue = max(20, value.wrappedValue - 1) } label: {
                    Image(systemName: "minus").font(.system(size: 14, weight: .bold)).frame(width: 32, height: 32)
                        .background(palette.elevatedSurface, in: Circle())
                }
                .buttonStyle(.plain)
                Spacer()
                Text("\(value.wrappedValue) PSI").font(.system(size: 15, weight: .bold, design: .rounded))
                Spacer()
                Button { value.wrappedValue = min(60, value.wrappedValue + 1) } label: {
                    Image(systemName: "plus").font(.system(size: 14, weight: .bold)).frame(width: 32, height: 32)
                        .background(palette.elevatedSurface, in: Circle())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(12)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

// MARK: - Procedure Edit Sheet

private struct ProcedureEditSheet: View {
    @ObservedObject private var store = VehicleStore.shared
    @Environment(\.dismiss) private var dismiss
    let existing: MaintenanceProcedure?
    let palette: QuailThemePalette

    @State private var title: String
    @State private var relatedTypeName: String
    @State private var steps: [ProcedureStep]
    @State private var tools: [String]
    @State private var parts: [String]
    @State private var notes: String
    @State private var newStep = ""
    @State private var newTool = ""
    @State private var newPart = ""

    init(existing: MaintenanceProcedure?, palette: QuailThemePalette) {
        self.existing = existing
        self.palette = palette
        _title = State(initialValue: existing?.title ?? "")
        _relatedTypeName = State(initialValue: existing?.relatedTypeName ?? "")
        _steps = State(initialValue: existing?.steps ?? [])
        _tools = State(initialValue: existing?.tools ?? [])
        _parts = State(initialValue: existing?.parts ?? [])
        _notes = State(initialValue: existing?.notes ?? "")
    }

    var body: some View {
        VehicleSheetContainer(title: existing == nil ? "New Procedure" : "Edit Procedure", palette: palette, onDismiss: { dismiss() }) {
            sheetField("Title (required)", value: $title, palette: palette)
            sheetField("Related Service (optional)", value: $relatedTypeName, palette: palette)

            dynamicList(label: "Tools", items: $tools, newItem: $newTool, placeholder: "Add tool...", palette: palette)
            dynamicList(label: "Parts", items: $parts, newItem: $newPart, placeholder: "Add part...", palette: palette)

            VStack(alignment: .leading, spacing: 6) {
                Text("Steps")
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)

                ForEach(Array(steps.enumerated()), id: \.element.id) { idx, step in
                    HStack(alignment: .top, spacing: 10) {
                        Text("\(idx + 1).")
                            .font(.system(size: 14, weight: .bold, design: .rounded))
                            .frame(width: 24)
                            .padding(.top, 12)

                        TextField("Step description", text: Binding(
                            get: { steps[safe: idx]?.text ?? "" },
                            set: { if idx < steps.count { steps[idx].text = $0 } }
                        ))
                        .font(.system(size: 14, design: .rounded))
                        .padding(10)
                        .background(palette.surface, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(palette.border, lineWidth: 1))

                        Button { steps.remove(at: idx) } label: {
                            Image(systemName: "minus.circle.fill")
                                .foregroundStyle(palette.negative)
                                .padding(.top, 12)
                        }
                        .buttonStyle(.plain)
                    }
                }

                HStack(spacing: 8) {
                    TextField("Add step...", text: $newStep)
                        .font(.system(size: 14, design: .rounded))
                        .padding(10)
                        .background(palette.surface, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(palette.border, lineWidth: 1))

                    Button {
                        let trimmed = newStep.trimmingCharacters(in: .whitespaces)
                        if !trimmed.isEmpty {
                            steps.append(ProcedureStep(text: trimmed))
                            newStep = ""
                        }
                    } label: {
                        Image(systemName: "plus.circle.fill").font(.system(size: 22)).foregroundStyle(palette.accent)
                    }
                    .buttonStyle(.plain)
                }
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Notes").font(.system(size: 12, weight: .semibold, design: .rounded)).foregroundStyle(.secondary)
                TextEditor(text: $notes)
                    .font(.system(size: 14, design: .rounded))
                    .frame(minHeight: 80)
                    .padding(10)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
            }

            Button {
                guard !title.isEmpty else { return }
                var proc = existing ?? MaintenanceProcedure()
                proc.title = title
                proc.relatedTypeName = relatedTypeName
                proc.steps = steps
                proc.tools = tools
                proc.parts = parts
                proc.notes = notes
                proc.lastUpdated = Date()
                store.saveProcedure(proc)
                dismiss()
            } label: {
                Text(existing == nil ? "Create Procedure" : "Save Changes")
                    .font(.system(size: 15, weight: .semibold, design: .rounded))
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .foregroundStyle(title.isEmpty ? .secondary : palette.primaryButtonText)
                    .background(title.isEmpty ? palette.border : palette.primaryButton, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .buttonStyle(.plain)
            .disabled(title.isEmpty)
        }
    }

    private func dynamicList(label: String, items: Binding<[String]>, newItem: Binding<String>, placeholder: String, palette: QuailThemePalette) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(.system(size: 12, weight: .semibold, design: .rounded)).foregroundStyle(.secondary)

            ForEach(items.wrappedValue, id: \.self) { item in
                HStack {
                    Text("• \(item)").font(.system(size: 14, design: .rounded))
                    Spacer()
                    Button { items.wrappedValue.removeAll { $0 == item } } label: {
                        Image(systemName: "minus.circle.fill").foregroundStyle(palette.negative)
                    }.buttonStyle(.plain)
                }
                .padding(10)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(palette.border, lineWidth: 1))
            }

            HStack(spacing: 8) {
                TextField(placeholder, text: newItem)
                    .font(.system(size: 14, design: .rounded))
                    .padding(10)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(palette.border, lineWidth: 1))

                Button {
                    let trimmed = newItem.wrappedValue.trimmingCharacters(in: .whitespaces)
                    if !trimmed.isEmpty { items.wrappedValue.append(trimmed); newItem.wrappedValue = "" }
                } label: {
                    Image(systemName: "plus.circle.fill").font(.system(size: 22)).foregroundStyle(palette.accent)
                }
                .buttonStyle(.plain)
            }
        }
    }
}

// MARK: - Maintenance Type Settings Sheet

private struct MaintenanceTypeSettingsSheet: View {
    @ObservedObject private var store = VehicleStore.shared
    @Environment(\.dismiss) private var dismiss
    let palette: QuailThemePalette

    @State private var editingType: MaintenanceTypeDefinition?
    @State private var showingAdd = false

    var body: some View {
        VehicleSheetContainer(title: "Maintenance Types", palette: palette, onDismiss: { dismiss() }) {
            Button { showingAdd = true } label: {
                Label("Add Custom Type", systemImage: "plus.circle.fill")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                    .foregroundStyle(palette.accent)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .background(palette.accent.opacity(0.12), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            }
            .buttonStyle(.plain)

            VStack(spacing: 0) {
                ForEach(Array(store.maintenanceTypes.enumerated()), id: \.element.id) { idx, type in
                    HStack(spacing: 10) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .fill(type.colorName.color.opacity(0.15))
                                .frame(width: 30, height: 30)
                            Image(systemName: type.icon)
                                .font(.system(size: 13))
                                .foregroundStyle(type.colorName.color)
                        }

                        VStack(alignment: .leading, spacing: 1) {
                            Text(type.name).font(.system(size: 13, weight: .semibold, design: .rounded))
                            Text(intervalText(type)).font(.system(size: 11, design: .rounded)).foregroundStyle(.secondary)
                        }

                        Spacer()

                        Toggle("", isOn: Binding(
                            get: { type.isEnabled },
                            set: { var t = type; t.isEnabled = $0; store.saveMaintenanceType(t) }
                        ))
                        .labelsHidden()
                        .tint(palette.accent)
                        .scaleEffect(0.8)

                        if !type.isBuiltIn {
                            Button { editingType = type } label: {
                                Image(systemName: "pencil").font(.system(size: 12)).foregroundStyle(palette.accent)
                            }
                            .buttonStyle(.plain)

                            Button { store.deleteMaintenanceType(type.id) } label: {
                                Image(systemName: "trash").font(.system(size: 12)).foregroundStyle(palette.negative)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    if idx < store.maintenanceTypes.count - 1 { Divider().padding(.leading, 52) }
                }
            }
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
        .sheet(isPresented: $showingAdd) {
            MaintenanceTypeEditSheet(existing: nil, palette: palette)
        }
        .sheet(item: $editingType) { type in
            MaintenanceTypeEditSheet(existing: type, palette: palette)
        }
    }

    private func intervalText(_ type: MaintenanceTypeDefinition) -> String {
        var parts: [String] = []
        if let mo = type.monthInterval { parts.append("Every \(mo)mo") }
        if let mi = type.mileageInterval { parts.append("Every \(mi.formatted())mi") }
        return parts.isEmpty ? "No interval set" : parts.joined(separator: " · ")
    }
}

private struct MaintenanceTypeEditSheet: View {
    @ObservedObject private var store = VehicleStore.shared
    @Environment(\.dismiss) private var dismiss
    let existing: MaintenanceTypeDefinition?
    let palette: QuailThemePalette

    @State private var name: String
    @State private var monthStr: String
    @State private var mileageStr: String
    @State private var color: MaintenanceColor
    @State private var icon: String

    let icons = ["wrench.and.screwdriver.fill","drop.fill","circle.grid.cross.fill","slowmo","drop.halffull","bolt.fill","aqi.medium","wind","thermometer.medium","gearshape.fill","battery.100","gearshape.2.fill","car.fill","oilcan.fill"]

    init(existing: MaintenanceTypeDefinition?, palette: QuailThemePalette) {
        self.existing = existing
        self.palette = palette
        _name = State(initialValue: existing?.name ?? "")
        _monthStr = State(initialValue: existing?.monthInterval.map { String($0) } ?? "")
        _mileageStr = State(initialValue: existing?.mileageInterval.map { String($0) } ?? "")
        _color = State(initialValue: existing?.colorName ?? .blue)
        _icon = State(initialValue: existing?.icon ?? "wrench.and.screwdriver.fill")
    }

    var body: some View {
        VehicleSheetContainer(title: existing == nil ? "New Type" : "Edit Type", palette: palette, onDismiss: { dismiss() }) {
            sheetField("Name (required)", value: $name, palette: palette)
            sheetField("Month Interval (e.g. 6 for every 6 months)", value: $monthStr, keyboard: .numberPad, palette: palette)
            sheetField("Mileage Interval (e.g. 5000)", value: $mileageStr, keyboard: .numberPad, palette: palette)

            VStack(alignment: .leading, spacing: 6) {
                Text("Color").font(.system(size: 12, weight: .semibold, design: .rounded)).foregroundStyle(.secondary)
                LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 8), spacing: 8) {
                    ForEach(MaintenanceColor.allCases) { c in
                        Button { color = c } label: {
                            Circle().fill(c.color)
                                .frame(width: 32, height: 32)
                                .overlay(Circle().stroke(Color.white, lineWidth: color == c ? 3 : 0))
                                .overlay(Circle().stroke(c.color, lineWidth: color == c ? 1 : 0))
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(12)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("Icon").font(.system(size: 12, weight: .semibold, design: .rounded)).foregroundStyle(.secondary)
                LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 7), spacing: 8) {
                    ForEach(icons, id: \.self) { ic in
                        Button { icon = ic } label: {
                            ZStack {
                                RoundedRectangle(cornerRadius: 8, style: .continuous)
                                    .fill(icon == ic ? color.color.opacity(0.2) : palette.elevatedSurface)
                                    .frame(width: 40, height: 40)
                                Image(systemName: ic)
                                    .font(.system(size: 16))
                                    .foregroundStyle(icon == ic ? color.color : .secondary)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(12)
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
            }

            Button {
                guard !name.isEmpty else { return }
                var t = existing ?? MaintenanceTypeDefinition(name: "")
                t.name = name
                t.monthInterval = Int(monthStr)
                t.mileageInterval = Int(mileageStr)
                t.colorName = color
                t.icon = icon
                store.saveMaintenanceType(t)
                dismiss()
            } label: {
                Text(existing == nil ? "Add Type" : "Save Changes")
                    .font(.system(size: 15, weight: .semibold, design: .rounded))
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .foregroundStyle(name.isEmpty ? .secondary : palette.primaryButtonText)
                    .background(name.isEmpty ? palette.border : palette.primaryButton, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .buttonStyle(.plain)
            .disabled(name.isEmpty)
        }
    }
}

// MARK: - Inspection Item Settings Sheet

private struct InspectionItemSettingsSheet: View {
    @ObservedObject private var store = VehicleStore.shared
    @Environment(\.dismiss) private var dismiss
    let palette: QuailThemePalette

    @State private var newName = ""
    @State private var newPeriodicity = 7

    var body: some View {
        VehicleSheetContainer(title: "Inspection Items", palette: palette, onDismiss: { dismiss() }) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Add Item")
                    .font(.system(size: 12, weight: .semibold, design: .rounded))
                    .foregroundStyle(.secondary)

                sheetField("Item Name", value: $newName, palette: palette)

                Picker("Frequency", selection: $newPeriodicity) {
                    Text("Weekly").tag(7)
                    Text("Monthly").tag(30)
                }
                .pickerStyle(.segmented)

                Button {
                    let trimmed = newName.trimmingCharacters(in: .whitespaces)
                    if !trimmed.isEmpty {
                        store.saveInspectionItem(InspectionCheckItem(name: trimmed, periodicityDays: newPeriodicity))
                        newName = ""
                    }
                } label: {
                    Text("Add Item")
                        .font(.system(size: 14, weight: .semibold, design: .rounded))
                        .frame(maxWidth: .infinity, minHeight: 40)
                        .foregroundStyle(newName.isEmpty ? .secondary : palette.primaryButtonText)
                        .background(newName.isEmpty ? palette.border : palette.primaryButton, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
                .buttonStyle(.plain)
                .disabled(newName.isEmpty)
            }

            VStack(spacing: 0) {
                ForEach(Array(store.inspectionItems.enumerated()), id: \.element.id) { idx, item in
                    HStack(spacing: 10) {
                        VStack(alignment: .leading, spacing: 1) {
                            Text(item.name).font(.system(size: 13, weight: .semibold, design: .rounded))
                            Text(item.periodicityLabel).font(.system(size: 11, design: .rounded)).foregroundStyle(.secondary)
                        }
                        Spacer()
                        if !item.isBuiltIn {
                            Button { store.deleteInspectionItem(item.id) } label: {
                                Image(systemName: "trash").font(.system(size: 12)).foregroundStyle(palette.negative)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    if idx < store.inspectionItems.count - 1 { Divider().padding(.leading, 12) }
                }
            }
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }
}

// MARK: - Shared Sheet Container

private struct VehicleSheetContainer<Content: View>: View {
    let title: String
    let palette: QuailThemePalette
    let onDismiss: () -> Void
    let content: Content

    init(title: String, palette: QuailThemePalette, onDismiss: @escaping () -> Void, @ViewBuilder content: () -> Content) {
        self.title = title
        self.palette = palette
        self.onDismiss = onDismiss
        self.content = content()
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 14) {
                HStack {
                    Text(title).font(.system(size: 17, weight: .bold, design: .rounded))
                    Spacer()
                    Button(action: onDismiss) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 24))
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.top, 20)

                content
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 32)
        }
        .background(palette.backgroundTop.ignoresSafeArea())
    }
}

// MARK: - Form Helpers (file-scope for shared use)

private func sheetSection<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
    VStack(alignment: .leading, spacing: 8) {
        Text(title)
            .font(.system(size: 12, weight: .bold, design: .rounded))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 4)
        content()
    }
}

private func sheetField(_ label: String, value: Binding<String>, keyboard: UIKeyboardType = .default, palette: QuailThemePalette) -> some View {
    VStack(alignment: .leading, spacing: 4) {
        Text(label).font(.system(size: 12, weight: .semibold, design: .rounded)).foregroundStyle(.secondary)
        TextField(label, text: value)
            .font(.system(size: 14, design: .rounded))
            .keyboardType(keyboard)
            .padding(12)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

private func sheetIntField(_ label: String, value: Binding<Int>, palette: QuailThemePalette) -> some View {
    let strBinding = Binding<String>(
        get: { String(value.wrappedValue) },
        set: { if let i = Int($0) { value.wrappedValue = i } }
    )
    return sheetField(label, value: strBinding, keyboard: .numberPad, palette: palette)
}

private func sheetDoubleField(_ label: String, value: Binding<Double>, palette: QuailThemePalette) -> some View {
    let strBinding = Binding<String>(
        get: { value.wrappedValue == 0 ? "" : String(format: "%.1f", value.wrappedValue) },
        set: { if let d = Double($0) { value.wrappedValue = d } else if $0.isEmpty { value.wrappedValue = 0 } }
    )
    return sheetField(label, value: strBinding, keyboard: .decimalPad, palette: palette)
}

// MARK: - Safe Array Subscript

private extension Array {
    subscript(safe index: Int) -> Element? {
        indices.contains(index) ? self[index] : nil
    }
}

// MARK: - Quail Car Settings Page

struct QuailCarSettingsPageView: View {
    @EnvironmentObject private var navigator: AppNavigator
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = VehicleStore.shared

    @State private var showProfileEdit = false
    @State private var showMaintenanceTypes = false
    @State private var showInspectionItems = false
    @State private var showHistoryImport = false
    @State private var showPairTransactions = false

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        QuailCarPageShell(
            title: "Settings",
            onLeadingTap: { navigator.goBack() },
            onTrailingTap: { navigator.show(.vehicleNotifications) }
        ) {
            AppPageScroll(contentPadding: 14) {
                VStack(alignment: .leading, spacing: 14) {
                    carSettingsSection(title: "Vehicle") {
                        carSettingsRow(
                            icon: "car.fill", iconColor: .orange,
                            title: "Vehicle Profile",
                            subtitle: store.profile.isEmpty ? "Not configured" : store.profile.displayName
                        ) { showProfileEdit = true }
                    }

                    carSettingsSection(title: "Maintenance") {
                        carSettingsRow(
                            icon: "wrench.and.screwdriver.fill", iconColor: palette.accent,
                            title: "Service Types",
                            subtitle: "\(store.maintenanceTypes.filter { $0.isEnabled }.count) of \(store.maintenanceTypes.count) enabled"
                        ) { showMaintenanceTypes = true }
                        Divider().padding(.leading, 60)
                        carSettingsRow(
                            icon: "checkmark.circle.fill", iconColor: palette.positive,
                            title: "Inspection Items",
                            subtitle: "\(store.inspectionItems.count) items · \(store.inspectionItems.filter { $0.periodicityDays <= 7 }.count) weekly, \(store.inspectionItems.filter { $0.periodicityDays > 7 }.count) monthly"
                        ) { showInspectionItems = true }
                    }

                    carSettingsSection(title: "Tires") {
                        carSettingsRow(
                            icon: "circle.grid.cross.fill", iconColor: Color(red: 0.40, green: 0.60, blue: 0.95),
                            title: "Tire Sets",
                            subtitle: store.activeTireSet.map { "Active: \($0.displayName)" } ?? "No active set"
                        ) { }
                    }

                    carSettingsSection(title: "Data") {
                        carSettingsRow(
                            icon: "square.and.arrow.down.fill", iconColor: Color(red: 0.20, green: 0.60, blue: 0.40),
                            title: "Import History CSV",
                            subtitle: "Load fuel and oil change history from a CSV file"
                        ) { showHistoryImport = true }
                        Divider().padding(.leading, 60)
                        carSettingsRow(
                            icon: "link", iconColor: Color(red: 0.40, green: 0.55, blue: 0.95),
                            title: "Pair Transactions",
                            subtitle: "Link fuel and maintenance records to bank transactions"
                        ) { showPairTransactions = true }
                    }

                    carSettingsSection(title: "Notifications") {
                        notificationsSection()
                    }
                }
            }
        }
        .sheet(isPresented: $showHistoryImport) {
            VehicleHistoryImportSheet()
        }
        .sheet(isPresented: $showPairTransactions) {
            VehiclePairTransactionsSheet()
        }
        .sheet(isPresented: $showProfileEdit) {
            VehicleProfileEditSheet(palette: palette)
        }
        .sheet(isPresented: $showMaintenanceTypes) {
            MaintenanceTypeSettingsSheet(palette: palette)
        }
        .sheet(isPresented: $showInspectionItems) {
            InspectionItemSettingsSheet(palette: palette)
        }
    }

    private func carSettingsSection<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
                .padding(.leading, 4)
            VStack(spacing: 0) {
                content()
            }
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
    }

    private func carSettingsRow(icon: String, iconColor: Color, title: String, subtitle: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 14) {
                ZStack {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(iconColor.opacity(0.15))
                        .frame(width: 36, height: 36)
                    Image(systemName: icon)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(iconColor)
                }
                VStack(alignment: .leading, spacing: 3) {
                    Text(title)
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                        .foregroundStyle(.primary)
                    Text(subtitle)
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                }
                Spacer(minLength: 12)
                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.tertiary)
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func notificationsSection() -> some View {
        notifyToggleRow(
            icon: "wrench.and.screwdriver.fill", iconColor: palette.accent,
            title: "Service Due Reminders",
            subtitle: "Approaching oil changes, rotations, and more",
            key: "vehicle.notify.maintenanceDue", defaultOn: true
        )
        Divider().padding(.leading, 60)
        notifyToggleRow(
            icon: "exclamationmark.triangle.fill", iconColor: palette.negative,
            title: "Overdue Service Alerts",
            subtitle: "Past-due date or mileage threshold",
            key: "vehicle.notify.overdue", defaultOn: true
        )
        Divider().padding(.leading, 60)
        notifyToggleRow(
            icon: "calendar.badge.checkmark", iconColor: Color(red: 0.20, green: 0.55, blue: 0.95),
            title: "Weekly Inspection Reminders",
            subtitle: "Tire pressure, fluids, lights, wipers",
            key: "vehicle.notify.inspectionWeekly", defaultOn: true
        )
        Divider().padding(.leading, 60)
        notifyToggleRow(
            icon: "calendar", iconColor: Color(red: 0.55, green: 0.35, blue: 0.90),
            title: "Monthly Inspection Reminders",
            subtitle: "Battery, belts, brake pads visual, tread depth",
            key: "vehicle.notify.inspectionMonthly", defaultOn: true
        )
        Divider().padding(.leading, 60)
        notifyToggleRow(
            icon: "fuelpump.fill", iconColor: Color(red: 0.95, green: 0.55, blue: 0.10),
            title: "Gas Station Detection",
            subtitle: "Prompt to log a fill-up when a gas transaction appears",
            key: "vehicle.notify.gasDetection", defaultOn: true
        )
        Divider().padding(.leading, 60)
        notifyToggleRow(
            icon: "circle.grid.cross.fill", iconColor: Color(red: 0.40, green: 0.60, blue: 0.95),
            title: "Tire Pressure Reminders",
            subtitle: "Remind me when pressure check is overdue",
            key: "vehicle.notify.tirePressure", defaultOn: false
        )
    }

    private func notifyToggleRow(icon: String, iconColor: Color, title: String, subtitle: String, key: String, defaultOn: Bool) -> some View {
        HStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(iconColor.opacity(0.15))
                    .frame(width: 36, height: 36)
                Image(systemName: icon)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(iconColor)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(.system(size: 14, weight: .bold, design: .rounded))
                Text(subtitle)
                    .font(.system(size: 12, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 8)
            NotifyToggle(key: key, defaultOn: defaultOn, palette: palette)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }
}

private struct NotifyToggle: View {
    let key: String
    let defaultOn: Bool
    let palette: QuailThemePalette
    @State private var isOn: Bool

    init(key: String, defaultOn: Bool, palette: QuailThemePalette) {
        self.key = key
        self.defaultOn = defaultOn
        self.palette = palette
        _isOn = State(initialValue: UserDefaults.standard.object(forKey: key) as? Bool ?? defaultOn)
    }

    var body: some View {
        Toggle("", isOn: $isOn)
            .labelsHidden()
            .tint(palette.accent)
            .onChange(of: isOn) { _, val in
                UserDefaults.standard.set(val, forKey: key)
            }
    }
}

// MARK: - Quail Car Notifications Page

struct VehicleNotificationsContent: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @ObservedObject private var store = VehicleStore.shared

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    struct CarAlert: Identifiable {
        var id = UUID()
        var icon: String
        var iconColor: Color
        var title: String
        var subtitle: String
        var severity: Severity
        enum Severity {
            case critical, warning, info
            var order: Int {
                switch self {
                case .critical: return 0
                case .warning:  return 1
                case .info:     return 2
                }
            }
        }
    }

    var alerts: [CarAlert] {
        var items: [CarAlert] = []

        if let pending = store.pendingGasDetection {
            items.append(CarAlert(
                icon: "fuelpump.fill",
                iconColor: Color(red: 0.95, green: 0.55, blue: 0.10),
                title: "Unlogged Gas Purchase",
                subtitle: "\(pending.merchant) · $\(String(format: "%.2f", pending.amount)) — tap to log fill-up",
                severity: .info
            ))
        }

        for type in store.maintenanceTypes where type.isEnabled {
            let st = store.status(for: type)
            if st == .overdue {
                items.append(CarAlert(
                    icon: type.icon, iconColor: type.colorName.color,
                    title: "\(type.name) Overdue",
                    subtitle: "Next due: \(store.nextDueDescription(for: type))",
                    severity: .critical
                ))
            } else if st == .dueSoon {
                items.append(CarAlert(
                    icon: type.icon, iconColor: type.colorName.color,
                    title: "\(type.name) Due Soon",
                    subtitle: "Next due: \(store.nextDueDescription(for: type))",
                    severity: .warning
                ))
            }
        }

        for item in store.inspectionItems where item.isDue {
            items.append(CarAlert(
                icon: "checkmark.circle",
                iconColor: Color(red: 0.20, green: 0.55, blue: 0.95),
                title: "\(item.name) Inspection Due",
                subtitle: item.lastCheckedDate == nil ? "Never completed" : "Periodicity: \(item.periodicityLabel)",
                severity: .warning
            ))
        }

        for issue in store.openIssues {
            items.append(CarAlert(
                icon: "exclamationmark.triangle.fill",
                iconColor: palette.negative,
                title: "Open Issue: \(issue.title.isEmpty ? "Untitled" : issue.title)",
                subtitle: issue.description.isEmpty ? "Reported \(issue.dateNoticed.formatted(date: .abbreviated, time: .omitted))" : issue.description,
                severity: .critical
            ))
        }

        return items.sorted { $0.severity.order < $1.severity.order }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if alerts.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "checkmark.shield.fill").font(.system(size: 40)).foregroundStyle(palette.positive)
                    Text("All clear").font(.system(size: 20, weight: .bold, design: .rounded))
                    Text("No overdue maintenance, open issues, or pending reminders.")
                        .font(.system(size: 14, weight: .medium, design: .rounded)).foregroundStyle(.secondary).multilineTextAlignment(.center)
                }
                .frame(maxWidth: .infinity).padding(.vertical, 48)
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(alerts.enumerated()), id: \.element.id) { idx, alert in
                        alertRow(alert: alert)
                        if idx < alerts.count - 1 { Divider().padding(.leading, 60) }
                    }
                }
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(palette.border, lineWidth: 1))
            }
        }
    }

    private func alertRow(alert: CarAlert) -> some View {
        HStack(spacing: 14) {
            ZStack {
                RoundedRectangle(cornerRadius: 10, style: .continuous).fill(alert.iconColor.opacity(0.15)).frame(width: 36, height: 36)
                Image(systemName: alert.icon).font(.system(size: 16, weight: .semibold)).foregroundStyle(alert.iconColor)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(alert.title).font(.system(size: 14, weight: .bold, design: .rounded))
                Text(alert.subtitle).font(.system(size: 12, weight: .medium, design: .rounded)).foregroundStyle(.secondary).lineLimit(2)
            }
            Spacer(minLength: 8)
            severityBadge(alert.severity)
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
    }

    private func severityBadge(_ severity: CarAlert.Severity) -> some View {
        let (label, color): (String, Color) = switch severity {
        case .critical: ("Urgent",  palette.negative)
        case .warning:  ("Soon",    Color(red: 0.95, green: 0.60, blue: 0.10))
        case .info:     ("Pending", palette.accent)
        }
        return Text(label).font(.system(size: 10, weight: .bold, design: .rounded))
            .foregroundStyle(.white).padding(.horizontal, 8).padding(.vertical, 4).background(color, in: Capsule())
    }
}

struct QuailCarNotificationsPageView: View {
    @EnvironmentObject private var navigator: AppNavigator
    var body: some View {
        QuailCarPageShell(
            title: "Notifications",
            onLeadingTap: { navigator.goBack() },
            onTrailingTap: { navigator.show(.vehicleSettings) }
        ) {
            AppPageScroll(contentPadding: 14) { VehicleNotificationsContent() }
        }
    }
}

// MARK: - Transaction Pairing

struct VehiclePairTransactionsSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @Environment(\.dismiss) private var dismiss
    @ObservedObject private var store = VehicleStore.shared

    @State private var fuel: [QuailCashAPI.VehicleFuelPayload] = []
    @State private var maintenance: [QuailCashAPI.VehicleMaintenancePayload] = []
    @State private var selectedKind: String = "fuel"
    @State private var expandedRecordId: Int? = nil
    @State private var candidates: [QuailCashAPI.VehicleTxCandidate] = []
    @State private var loadingCandidates = false
    @State private var statusMessage = ""

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Picker("Kind", selection: $selectedKind) {
                    Text("Fuel").tag("fuel")
                    Text("Maintenance").tag("maintenance")
                }
                .pickerStyle(.segmented)
                .padding(.horizontal, 16)
                .padding(.vertical, 10)

                ScrollView {
                    LazyVStack(spacing: 10) {
                        let records = selectedKind == "fuel"
                            ? fuel.map { AnyVehicleRecord(id: $0.id, kind: "fuel", date: $0.date, label: "Fill-up", amount: $0.totalCost, gallons: $0.gallons, linkedMerchant: $0.linkedMerchant, linkedTransactionId: $0.linkedTransactionId) }
                            : maintenance.map { AnyVehicleRecord(id: $0.id, kind: "maintenance", date: $0.date, label: $0.typeName, amount: $0.cost, gallons: nil, linkedMerchant: $0.linkedMerchant, linkedTransactionId: $0.linkedTransactionId) }

                        if records.isEmpty {
                            Text("No records found.")
                                .font(.system(size: 13, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, minHeight: 80)
                        }

                        ForEach(records) { rec in
                            VStack(alignment: .leading, spacing: 0) {
                                Button {
                                    if expandedRecordId == rec.id {
                                        expandedRecordId = nil
                                        candidates = []
                                    } else {
                                        expandedRecordId = rec.id
                                        candidates = []
                                        Task { await loadCandidates(kind: rec.kind, id: rec.id) }
                                    }
                                } label: {
                                    HStack(spacing: 10) {
                                        VStack(alignment: .leading, spacing: 3) {
                                            Text(rec.label)
                                                .font(.system(size: 13, weight: .bold, design: .rounded))
                                            HStack(spacing: 6) {
                                                Text(rec.date)
                                                if let gal = rec.gallons {
                                                    Text("·")
                                                    Text(String(format: "%.3f gal", gal))
                                                }
                                            }
                                            .font(.system(size: 11, weight: .medium, design: .rounded))
                                            .foregroundStyle(.secondary)
                                        }
                                        Spacer()
                                        if let amt = rec.amount {
                                            Text(String(format: "$%.2f", amt))
                                                .font(.system(size: 13, weight: .semibold, design: .rounded))
                                                .foregroundStyle(.secondary)
                                        }
                                        if let merchant = rec.linkedMerchant, !merchant.isEmpty {
                                            Label(merchant, systemImage: "link")
                                                .font(.system(size: 11, weight: .semibold, design: .rounded))
                                                .foregroundStyle(palette.positive)
                                                .lineLimit(1)
                                        }
                                        Image(systemName: expandedRecordId == rec.id ? "chevron.up" : "chevron.down")
                                            .font(.system(size: 11, weight: .semibold))
                                            .foregroundStyle(.tertiary)
                                    }
                                    .padding(.horizontal, 14)
                                    .padding(.vertical, 12)
                                }
                                .buttonStyle(.plain)

                                if expandedRecordId == rec.id {
                                    Divider().opacity(0.15)
                                    if loadingCandidates {
                                        Text("Loading candidates...")
                                            .font(.system(size: 12, weight: .medium, design: .rounded))
                                            .foregroundStyle(.secondary)
                                            .padding(.horizontal, 14)
                                            .padding(.vertical, 10)
                                    } else if candidates.isEmpty {
                                        Text("No transactions found within 7 days.")
                                            .font(.system(size: 12, weight: .medium, design: .rounded))
                                            .foregroundStyle(.secondary)
                                            .padding(.horizontal, 14)
                                            .padding(.vertical, 10)
                                    } else {
                                        VStack(spacing: 0) {
                                            ForEach(candidates) { tx in
                                                Button {
                                                    Task { await linkTx(rec: rec, tx: tx) }
                                                } label: {
                                                    HStack(spacing: 10) {
                                                        VStack(alignment: .leading, spacing: 2) {
                                                            Text(tx.merchant ?? "Unknown")
                                                                .font(.system(size: 12, weight: .semibold, design: .rounded))
                                                            HStack(spacing: 6) {
                                                                Text(tx.date ?? "")
                                                                    .font(.system(size: 11, weight: .medium, design: .rounded))
                                                                    .foregroundStyle(.secondary)
                                                                if let cat = tx.category, !cat.isEmpty {
                                                                    Text(cat)
                                                                        .font(.system(size: 10, weight: .semibold, design: .rounded))
                                                                        .foregroundStyle(.secondary)
                                                                        .padding(.horizontal, 6)
                                                                        .padding(.vertical, 2)
                                                                        .background(.secondary.opacity(0.12), in: Capsule())
                                                                }
                                                            }
                                                        }
                                                        Spacer()
                                                        if let amt = tx.amount {
                                                            Text(String(format: "$%.2f", amt))
                                                                .font(.system(size: 12, weight: .semibold, design: .rounded))
                                                        }
                                                        Image(systemName: "link.badge.plus")
                                                            .font(.system(size: 12))
                                                            .foregroundStyle(palette.accent)
                                                    }
                                                    .padding(.horizontal, 14)
                                                    .padding(.vertical, 10)
                                                }
                                                .buttonStyle(.plain)
                                                Divider().padding(.leading, 14).opacity(0.1)
                                            }
                                        }
                                    }
                                    if rec.linkedTransactionId != nil {
                                        Button(role: .destructive) {
                                            Task { await unlinkTx(rec: rec) }
                                        } label: {
                                            Label("Remove Link", systemImage: "link.badge.minus")
                                                .font(.system(size: 12, weight: .semibold, design: .rounded))
                                                .foregroundStyle(palette.negative)
                                                .padding(.horizontal, 14)
                                                .padding(.vertical, 10)
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                            }
                            .background(palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(palette.border, lineWidth: 1))
                        }

                        if !statusMessage.isEmpty {
                            Text(statusMessage)
                                .font(.system(size: 12, weight: .medium, design: .rounded))
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    .padding(16)
                }
            }
            .navigationTitle("Pair Transactions")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
        .task { await loadRecords() }
        .onChange(of: selectedKind) { _ in expandedRecordId = nil; candidates = [] }
    }

    private func loadRecords() async {
        do {
            fuel = try await QuailCashAPI.shared.fetchVehicleFuel(limit: 500)
            maintenance = try await QuailCashAPI.shared.fetchVehicleMaintenance(limit: 500)
        } catch {
            statusMessage = "Failed to load records."
        }
    }

    private func loadCandidates(kind: String, id: Int) async {
        loadingCandidates = true
        defer { loadingCandidates = false }
        do {
            candidates = try await QuailCashAPI.shared.fetchVehicleTxCandidates(kind: kind, recordId: id)
        } catch {
            statusMessage = "Failed to load candidates."
        }
    }

    private func linkTx(rec: AnyVehicleRecord, tx: QuailCashAPI.VehicleTxCandidate) async {
        do {
            try await QuailCashAPI.shared.linkVehicleTransaction(kind: rec.kind, recordId: rec.id, transactionId: tx.id, merchant: tx.merchant)
            statusMessage = "Linked to \(tx.merchant ?? "transaction")."
            expandedRecordId = nil
            candidates = []
            await loadRecords()
        } catch {
            statusMessage = "Failed to link."
        }
    }

    private func unlinkTx(rec: AnyVehicleRecord) async {
        do {
            try await QuailCashAPI.shared.unlinkVehicleTransaction(kind: rec.kind, recordId: rec.id)
            statusMessage = "Link removed."
            expandedRecordId = nil
            candidates = []
            await loadRecords()
        } catch {
            statusMessage = "Failed to unlink."
        }
    }
}

private struct AnyVehicleRecord: Identifiable {
    let id: Int
    let kind: String
    let date: String
    let label: String
    let amount: Double?
    let gallons: Double?
    let linkedMerchant: String?
    let linkedTransactionId: String?
}

// MARK: - Vehicle History CSV Importer

struct VehicleHistoryImportSheet: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @Environment(\.dismiss) private var dismiss

    @State private var showFilePicker = false
    @State private var parsedFuel: [[String: Any]] = []
    @State private var parsedMaintenance: [[String: Any]] = []
    @State private var previewText = ""
    @State private var statusMessage = ""
    @State private var isImporting = false
    @State private var isDone = false

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Pick your vehicle maintenance CSV file. The importer reads fuel fill-up rows (Date, Mileage, Difference, Gas got, MPG) and oil change history rows automatically.")
                            .font(.system(size: 13, weight: .medium, design: .rounded))
                            .foregroundStyle(.secondary)
                    }
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(palette.border, lineWidth: 1))

                    Button {
                        showFilePicker = true
                    } label: {
                        Label("Choose CSV File", systemImage: "doc.badge.plus")
                            .font(.system(size: 14, weight: .semibold, design: .rounded))
                            .frame(maxWidth: .infinity, minHeight: 46)
                            .foregroundStyle(palette.primaryButtonText)
                            .background(palette.primaryButton, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    }
                    .buttonStyle(.plain)

                    if !previewText.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Preview")
                                .font(.system(size: 12, weight: .bold, design: .rounded))
                                .foregroundStyle(.secondary)
                            Text(previewText)
                                .font(.system(size: 13, weight: .medium, design: .rounded))
                        }
                        .padding(14)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(palette.surface, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(palette.border, lineWidth: 1))

                        Button {
                            Task { await runImport() }
                        } label: {
                            Text(isImporting ? "Importing..." : "Import \(parsedFuel.count) Fuel + \(parsedMaintenance.count) Maintenance Records")
                                .font(.system(size: 14, weight: .semibold, design: .rounded))
                                .frame(maxWidth: .infinity, minHeight: 46)
                                .foregroundStyle(palette.primaryButtonText)
                                .background(isDone ? palette.positive : palette.primaryButton, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        }
                        .buttonStyle(.plain)
                        .disabled(isImporting || isDone)
                    }

                    if !statusMessage.isEmpty {
                        Text(statusMessage)
                            .font(.system(size: 13, weight: .medium, design: .rounded))
                            .foregroundStyle(isDone ? palette.positive : .secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                .padding(16)
            }
            .navigationTitle("Import Vehicle History")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
        .fileImporter(isPresented: $showFilePicker, allowedContentTypes: [.commaSeparatedText, .text], allowsMultipleSelection: false) { result in
            guard let url = try? result.get().first else { return }
            parseCSV(url: url)
        }
    }

    private func parseCSV(url: URL) {
        guard url.startAccessingSecurityScopedResource() else {
            statusMessage = "Could not access file."
            return
        }
        defer { url.stopAccessingSecurityScopedResource() }
        guard let raw = try? String(contentsOf: url, encoding: .utf8) else {
            statusMessage = "Could not read file."
            return
        }

        var fuelRecords: [[String: Any]] = []
        var maintenanceRecords: [[String: Any]] = []
        let lines = raw.components(separatedBy: .newlines)

        // Fuel section: rows where column 0 looks like a date and column 1 is a mileage integer
        let dateFormatter = DateFormatter()
        dateFormatter.locale = Locale(identifier: "en_US_POSIX")
        let dateFormats = ["M/d/yy", "M/d/yyyy"]

        for line in lines {
            let cols = line.components(separatedBy: ",").map { $0.trimmingCharacters(in: .whitespaces) }
            guard cols.count >= 2 else { continue }
            // Try to parse as a fuel row: date, mileage, difference, gallons, mpg
            var parsedDate: Date? = nil
            for fmt in dateFormats {
                dateFormatter.dateFormat = fmt
                if let d = dateFormatter.date(from: cols[0]) { parsedDate = d; break }
            }
            guard let date = parsedDate else { continue }
            let mileageStr = cols[1].replacingOccurrences(of: ",", with: "")
            guard let mileage = Int(mileageStr), mileage > 100000 else { continue }

            let iso = ISO8601DateFormatter()
            iso.formatOptions = [.withFullDate]
            let dateStr = iso.string(from: date)

            var record: [String: Any] = ["date": dateStr, "mileage": mileage]
            if cols.count > 2, let diff = Double(cols[2].replacingOccurrences(of: ",", with: "")), diff > 0 {
                record["miles_since_last"] = diff
            }
            if cols.count > 3, let gal = Double(cols[3].replacingOccurrences(of: ",", with: "")), gal > 0 {
                record["gallons"] = gal
            }
            if cols.count > 4, let mpg = Double(cols[4].replacingOccurrences(of: ",", with: "")), mpg > 0 {
                record["mpg"] = mpg
            }
            fuelRecords.append(record)
        }

        // Oil change section: two-column blocks of "Changed (time), Changed (mi)"
        // These appear after the fuel rows. Find the first occurrence of that header.
        var inOilSection = false
        for line in lines {
            let cols = line.components(separatedBy: ",").map { $0.trimmingCharacters(in: .whitespaces) }
            if cols.count >= 2 && cols[0].lowercased().contains("changed (time)") && cols[1].lowercased().contains("changed (mi)") {
                inOilSection = true
                continue
            }
            guard inOilSection, cols.count >= 2, !cols[0].isEmpty else {
                if inOilSection && cols.allSatisfy({ $0.isEmpty }) { inOilSection = false }
                continue
            }
            var parsedDate: Date? = nil
            for fmt in dateFormats {
                dateFormatter.dateFormat = fmt
                if let d = dateFormatter.date(from: cols[0]) { parsedDate = d; break }
            }
            guard let date = parsedDate else { continue }
            let mileageStr = cols[1].replacingOccurrences(of: ",", with: "")
            guard let mileage = Int(mileageStr) else { continue }

            let iso = ISO8601DateFormatter()
            iso.formatOptions = [.withFullDate]
            maintenanceRecords.append(["type_name": "Oil Change", "date": iso.string(from: date), "mileage": mileage])
        }

        parsedFuel = fuelRecords
        parsedMaintenance = maintenanceRecords
        previewText = "\(fuelRecords.count) fuel fill-up rows found.\n\(maintenanceRecords.count) oil change rows found."
        statusMessage = ""
        isDone = false
    }

    private func runImport() async {
        isImporting = true
        defer { isImporting = false }
        do {
            var messages: [String] = []
            if !parsedFuel.isEmpty {
                let n = try await QuailCashAPI.shared.bulkImportVehicleFuel(parsedFuel)
                messages.append("\(n) fuel records imported.")
            }
            if !parsedMaintenance.isEmpty {
                let n = try await QuailCashAPI.shared.bulkImportVehicleMaintenance(parsedMaintenance)
                messages.append("\(n) oil changes imported.")
            }
            statusMessage = messages.joined(separator: " ")
            isDone = true
            await VehicleStore.shared.refresh()
        } catch {
            statusMessage = "Import failed: \(error.localizedDescription)"
        }
    }
}


