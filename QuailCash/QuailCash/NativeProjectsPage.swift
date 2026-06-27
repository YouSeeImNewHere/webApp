import SwiftUI
import PhotosUI
import Combine

// MARK: - Quick Notes

struct QuickNote: Codable, Identifiable {
    let id: UUID
    var text: String
    var createdAt: Date
}

final class QuickNoteStore: ObservableObject {
    static let shared = QuickNoteStore()
    @Published var notes: [QuickNote] = []
    private let key = "quail.projects.quickNotes"

    init() { load() }

    func load() {
        guard let data = UserDefaults.standard.data(forKey: key),
              let decoded = try? JSONDecoder().decode([QuickNote].self, from: data) else { return }
        notes = decoded
    }

    func save() {
        if let data = try? JSONEncoder().encode(notes) { UserDefaults.standard.set(data, forKey: key) }
    }

    func add(text: String) {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        notes.insert(QuickNote(id: UUID(), text: text, createdAt: Date()), at: 0)
        save()
    }

    func update(_ note: QuickNote) {
        if let i = notes.firstIndex(where: { $0.id == note.id }) { notes[i] = note; save() }
    }

    func delete(at offsets: IndexSet) { notes.remove(atOffsets: offsets); save() }
}

private struct QuickNotesSection: View {
    @ObservedObject private var store = QuickNoteStore.shared
    let palette: QuailThemePalette
    @State private var newText = ""
    @State private var isExpanded = true
    @FocusState private var inputFocused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            Button {
                withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) { isExpanded.toggle() }
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: "note.text")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.yellow)
                    Text("Quick Notes")
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                    if !store.notes.isEmpty {
                        Text("\(store.notes.count)")
                            .font(.system(size: 10, weight: .bold, design: .rounded))
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(palette.elevatedSurface, in: Capsule())
                    }
                    Spacer()
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
                }
                .padding(12)
            }
            .buttonStyle(.plain)

            if isExpanded {
                Divider().padding(.horizontal, 12)

                // Input row
                HStack(spacing: 8) {
                    TextField("Add a note or idea…", text: $newText, axis: .vertical)
                        .font(.system(size: 13, design: .rounded))
                        .lineLimit(1...4)
                        .focused($inputFocused)
                        .onSubmit { commitNote() }
                    if !newText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        Button(action: commitNote) {
                            Image(systemName: "arrow.up.circle.fill")
                                .font(.system(size: 22))
                                .foregroundStyle(palette.primaryButton)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.horizontal, 12).padding(.vertical, 8)

                if !store.notes.isEmpty {
                    Divider().padding(.horizontal, 12)
                    ForEach(Array(store.notes.enumerated()), id: \.element.id) { idx, note in
                        QuickNoteRow(note: note, palette: palette)
                        if idx < store.notes.count - 1 {
                            Divider().padding(.leading, 36)
                        }
                    }
                }
            }
        }
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(palette.border, lineWidth: 1))
    }

    private func commitNote() {
        store.add(text: newText)
        newText = ""
        inputFocused = false
    }
}

private struct QuickNoteRow: View {
    @State var note: QuickNote
    let palette: QuailThemePalette
    @State private var isEditing = false
    @State private var editText = ""
    @FocusState private var focused: Bool

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "circle.fill")
                .font(.system(size: 6))
                .foregroundStyle(.secondary)
                .padding(.top, 6)
                .frame(width: 20)

            if isEditing {
                TextField("Note", text: $editText, axis: .vertical)
                    .font(.system(size: 13, design: .rounded))
                    .lineLimit(1...6)
                    .focused($focused)
                    .onSubmit { commitEdit() }
                    .onAppear { focused = true }
                Button(action: commitEdit) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(.green).font(.system(size: 20))
                }
                .buttonStyle(.plain)
            } else {
                Text(note.text)
                    .font(.system(size: 13, design: .rounded))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .onTapGesture { editText = note.text; isEditing = true }
                Button {
                    QuickNoteStore.shared.delete(at: IndexSet([QuickNoteStore.shared.notes.firstIndex(where: { $0.id == note.id }) ?? 0]))
                } label: {
                    Image(systemName: "xmark").font(.system(size: 11)).foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 7)
    }

    private func commitEdit() {
        note.text = editText
        QuickNoteStore.shared.update(note)
        isEditing = false
    }
}

// MARK: - Models

enum ProjectType: String, Codable, CaseIterable {
    case generic, carBuild, software, home, other

    var label: String {
        switch self {
        case .generic: return "General"
        case .carBuild: return "Car Build"
        case .software: return "Software"
        case .home: return "Home"
        case .other: return "Other"
        }
    }

    var icon: String {
        switch self {
        case .generic: return "doc.text.fill"
        case .carBuild: return "car.fill"
        case .software: return "swift"
        case .home: return "house.fill"
        case .other: return "folder.fill"
        }
    }

    var color: Color {
        switch self {
        case .generic: return .blue
        case .carBuild: return .orange
        case .software: return .purple
        case .home: return .green
        case .other: return .gray
        }
    }
}

enum ProjectItemType: String, Codable, CaseIterable {
    case note, decision, budget, reference, photo

    var icon: String {
        switch self {
        case .note: return "text.alignleft"
        case .decision: return "arrow.trianglehead.branch"
        case .budget: return "dollarsign.circle.fill"
        case .reference: return "link"
        case .photo: return "photo.fill"
        }
    }

    var label: String {
        switch self {
        case .note: return "Note"
        case .decision: return "Decision"
        case .budget: return "Budget Item"
        case .reference: return "Reference"
        case .photo: return "Photo"
        }
    }
}

struct DecisionOption: Codable, Identifiable {
    let id: UUID
    var title: String
    var notes: String
    var pros: [String]
    var cons: [String]
    var estimatedCost: Double?
    var isSelected: Bool
}

struct ProjectItem: Codable, Identifiable {
    let id: UUID
    var type: ProjectItemType
    var title: String
    var body: String
    var options: [DecisionOption]       // for .decision
    var amount: Double?                 // for .budget
    var amountLabel: String             // for .budget (e.g. "Estimated", "Actual")
    var url: String                     // for .reference
    var imageFilename: String?          // for .photo
    var createdAt: Date
}

struct ProjectSection: Codable, Identifiable {
    let id: UUID
    var title: String
    var icon: String
    var items: [ProjectItem]
    var isExpanded: Bool
}

struct Project: Codable, Identifiable {
    let id: UUID
    var name: String
    var type: ProjectType
    var description: String
    var sections: [ProjectSection]
    var createdAt: Date
    var updatedAt: Date

    var totalBudget: Double {
        sections.flatMap(\.items).compactMap { $0.type == .budget ? $0.amount : nil }.reduce(0, +)
    }
}

// MARK: - Templates

extension Project {
    static func carBuildTemplate(name: String) -> Project {
        func sec(_ title: String, _ icon: String, _ items: [ProjectItem] = []) -> ProjectSection {
            ProjectSection(id: UUID(), title: title, icon: icon, items: items, isExpanded: false)
        }
        func decision(_ title: String, options: [String]) -> ProjectItem {
            ProjectItem(
                id: UUID(), type: .decision, title: title, body: "",
                options: options.map { DecisionOption(id: UUID(), title: $0, notes: "", pros: [], cons: [], estimatedCost: nil, isSelected: false) },
                amount: nil, amountLabel: "Estimated", url: "", imageFilename: nil, createdAt: Date()
            )
        }
        func note(_ title: String, body: String = "") -> ProjectItem {
            ProjectItem(id: UUID(), type: .note, title: title, body: body, options: [], amount: nil, amountLabel: "", url: "", imageFilename: nil, createdAt: Date())
        }

        return Project(
            id: UUID(),
            name: name,
            type: .carBuild,
            description: "Custom car build project",
            sections: [
                sec("Frame & Chassis", "wrench.and.screwdriver.fill", [
                    decision("Frame Type", options: ["Tube chassis", "Space frame", "Ladder frame", "Monocoque", "Custom fab"]),
                    note("Frame Specs", body: "Dimensions, material, wall thickness…"),
                ]),
                sec("Engine & Drivetrain", "gearshape.2.fill", [
                    decision("Engine", options: ["V8 LS", "Inline 6", "4-cylinder turbo", "Electric", "Rotary"]),
                    decision("Transmission", options: ["Manual 5-speed", "Manual 6-speed", "Automatic", "Sequential"]),
                    decision("Drivetrain", options: ["RWD", "AWD", "4WD"]),
                    note("Engine Notes"),
                ]),
                sec("Suspension", "arrow.up.and.down.and.arrow.left.and.right", [
                    decision("Front Suspension", options: ["Double wishbone", "MacPherson strut", "Solid axle"]),
                    decision("Rear Suspension", options: ["4-link", "3-link", "Watts link", "Solid axle", "IRS"]),
                ]),
                sec("Brakes", "circle.slash.fill", [
                    decision("Brake Setup", options: ["4-wheel disc", "Front disc / rear drum", "Big brake kit"]),
                ]),
                sec("Interior", "car.side.fill", [
                    decision("Dashboard Style", options: ["Touchscreen head unit", "Classic gauges", "Hybrid (gauges + small screen)", "Digital cluster"]),
                    decision("Seats", options: ["Racing bucket seats", "Stock reskin", "Custom upholstery"]),
                    decision("Roll Cage", options: ["Full cage", "Half cage", "Bolt-in", "None"]),
                    note("Interior Notes"),
                ]),
                sec("Exterior", "paintbrush.fill", [
                    decision("Body Style", options: ["Street body", "Track widebody", "Sleeper stock", "Custom panels"]),
                    decision("Paint / Finish", options: ["Single color", "Two-tone", "Wrap", "Bare metal"]),
                    note("Exterior Notes"),
                ]),
                sec("Electrical", "bolt.fill", [
                    decision("Wiring", options: ["Full custom harness", "OEM modified", "Aftermarket kit"]),
                    decision("Battery", options: ["Standard lead-acid", "Lithium", "Dual battery setup"]),
                    note("Electrical Notes"),
                ]),
                sec("Budget", "dollarsign.circle.fill"),
                sec("References & Inspiration", "photo.on.rectangle.angled"),
            ],
            createdAt: Date(),
            updatedAt: Date()
        )
    }

    static func genericTemplate(name: String, type: ProjectType) -> Project {
        Project(
            id: UUID(), name: name, type: type, description: "",
            sections: [
                ProjectSection(id: UUID(), title: "Overview", icon: "doc.text.fill", items: [], isExpanded: true),
                ProjectSection(id: UUID(), title: "Tasks", icon: "checklist", items: [], isExpanded: false),
                ProjectSection(id: UUID(), title: "Budget", icon: "dollarsign.circle.fill", items: [], isExpanded: false),
                ProjectSection(id: UUID(), title: "References", icon: "link", items: [], isExpanded: false),
            ],
            createdAt: Date(), updatedAt: Date()
        )
    }
}

// MARK: - Store

final class ProjectStore: ObservableObject {
    static let shared = ProjectStore()
    @Published var projects: [Project] = []

    private let key = "quail.projects.list"
    private let docsDir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]

    init() { load() }

    func load() {
        guard let data = UserDefaults.standard.data(forKey: key),
              let decoded = try? JSONDecoder().decode([Project].self, from: data) else { return }
        projects = decoded.sorted { $0.updatedAt > $1.updatedAt }
    }

    func save() {
        if let data = try? JSONEncoder().encode(projects) {
            UserDefaults.standard.set(data, forKey: key)
        }
    }

    func add(_ p: Project) { projects.insert(p, at: 0); save() }

    func update(_ p: Project) {
        if let i = projects.firstIndex(where: { $0.id == p.id }) {
            projects[i] = p; save()
        }
    }

    func delete(_ p: Project) {
        // clean up images
        for section in p.sections {
            for item in section.items where item.type == .photo {
                if let fn = item.imageFilename {
                    let url = docsDir.appendingPathComponent(fn)
                    try? FileManager.default.removeItem(at: url)
                }
            }
        }
        projects.removeAll { $0.id == p.id }
        save()
    }

    func saveImage(_ image: UIImage, id: UUID) -> String {
        let filename = "proj_\(id.uuidString).jpg"
        let url = docsDir.appendingPathComponent(filename)
        if let data = image.jpegData(compressionQuality: 0.8) {
            try? data.write(to: url)
        }
        return filename
    }

    func loadImage(filename: String) -> UIImage? {
        let url = docsDir.appendingPathComponent(filename)
        guard let data = try? Data(contentsOf: url) else { return nil }
        return UIImage(data: data)
    }
}

// MARK: - Projects list page

struct ProjectsPageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @EnvironmentObject private var navigator: AppNavigator
    @StateObject private var store = ProjectStore.shared
    @State private var showingNew = false
    @State private var selectedProject: Project?

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        AppChromeFrame(
            title: "Quail Projects",
            badgeValue: nil,
            selectedTab: nil,
            showsBottomBar: false,
            showsStandaloneBar: true,
            onLeadingTap: { navigator.goBack() },
            onTrailingTap: { showingNew = true },
            trailingIcon: "plus"
        ) {
            AppPageScroll {
                VStack(spacing: 12) {
                    QuickNotesSection(palette: palette)

                    if !store.projects.isEmpty {
                        HStack {
                            Text("Projects")
                                .font(.system(size: 13, weight: .bold, design: .rounded))
                                .foregroundStyle(.secondary)
                            Spacer()
                            Button("New") { showingNew = true }
                                .font(.system(size: 12, weight: .semibold, design: .rounded))
                                .foregroundStyle(palette.primaryButton)
                        }

                        ForEach(store.projects) { proj in
                            ProjectCard(project: proj, palette: palette) {
                                selectedProject = proj
                            }
                        }
                    }
                }
            }
        }
        .sheet(isPresented: $showingNew) {
            NewProjectSheet(palette: QuailTheme.palette(for: themeSelection)) { proj in
                store.add(proj)
                selectedProject = proj
            }
            .presentationDetents([.medium])
        }
        .sheet(item: $selectedProject) { proj in
            ProjectDetailSheet(project: proj, palette: QuailTheme.palette(for: themeSelection)) { updated in
                store.update(updated)
            } onDelete: {
                store.delete(proj)
                selectedProject = nil
            }
        }
    }
}

private struct ProjectCard: View {
    let project: Project
    let palette: QuailThemePalette
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 14) {
                ZStack {
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(project.type.color.opacity(0.15))
                        .frame(width: 44, height: 44)
                    Image(systemName: project.type.icon)
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(project.type.color)
                }

                VStack(alignment: .leading, spacing: 3) {
                    Text(project.name)
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                    Text(project.type.label)
                        .font(.system(size: 11, design: .rounded)).foregroundStyle(.secondary)
                    if project.totalBudget > 0 {
                        Text("Budget: \(project.totalBudget, format: .currency(code: "USD"))")
                            .font(.system(size: 11, design: .rounded)).foregroundStyle(.secondary)
                    }
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 4) {
                    Text("\(project.sections.count) sections")
                        .font(.system(size: 11, design: .rounded)).foregroundStyle(.secondary)
                    Text(project.updatedAt.formatted(.relative(presentation: .named)))
                        .font(.system(size: 10, design: .rounded)).foregroundStyle(.tertiary)
                }
            }
            .padding(14)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(palette.border, lineWidth: 1))
        }
        .buttonStyle(.plain)
    }
}

// MARK: - New project sheet

private struct NewProjectSheet: View {
    let palette: QuailThemePalette
    let onSave: (Project) -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var name = ""
    @State private var type: ProjectType = .generic
    @State private var description = ""

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Button("Cancel") { dismiss() }.foregroundStyle(.secondary)
                Spacer()
                Text("New Project").font(.system(size: 15, weight: .bold, design: .rounded))
                Spacer()
                Button("Create") {
                    let proj = type == .carBuild
                        ? Project.carBuildTemplate(name: name.isEmpty ? "Car Build" : name)
                        : Project.genericTemplate(name: name.isEmpty ? type.label : name, type: type)
                    onSave(proj)
                    dismiss()
                }
                .font(.system(size: 14, weight: .semibold, design: .rounded))
                .disabled(name.isEmpty && type != .carBuild)
            }
            .padding(.horizontal, 16).padding(.vertical, 14)
            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    // Type selector
                    Text("PROJECT TYPE").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                        ForEach(ProjectType.allCases, id: \.rawValue) { t in
                            Button {
                                type = t
                                if name.isEmpty { name = t == .carBuild ? "Car Build" : "" }
                            } label: {
                                HStack(spacing: 8) {
                                    Image(systemName: t.icon)
                                        .font(.system(size: 14, weight: .semibold))
                                        .foregroundStyle(t.color)
                                    Text(t.label)
                                        .font(.system(size: 13, weight: .semibold, design: .rounded))
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(12)
                                .background(type == t ? t.color.opacity(0.15) : palette.surface, in: RoundedRectangle(cornerRadius: 10))
                                .overlay(RoundedRectangle(cornerRadius: 10).stroke(type == t ? t.color : palette.border, lineWidth: 1))
                                .foregroundStyle(palette.chromeIconForeground)
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        Text("NAME").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                        TextField("Project name", text: $name)
                            .font(.system(size: 14, design: .rounded))
                            .padding(10)
                            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 8))
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        Text("DESCRIPTION").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                        TextField("Optional overview…", text: $description, axis: .vertical)
                            .font(.system(size: 14, design: .rounded))
                            .lineLimit(2...)
                            .padding(10)
                            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 8))
                    }

                    if type == .carBuild {
                        HStack(spacing: 8) {
                            Image(systemName: "wand.and.stars.inverse").foregroundStyle(.orange)
                            Text("Car Build template includes sections for frame, engine, drivetrain, interior, exterior, electrical, and budget.")
                                .font(.system(size: 12, design: .rounded)).foregroundStyle(.secondary)
                        }
                        .padding(10)
                        .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
                    }
                }
                .padding(16)
            }
        }
    }
}

// MARK: - Project detail sheet

struct ProjectDetailSheet: View {
    @State var project: Project
    let palette: QuailThemePalette
    let onUpdate: (Project) -> Void
    let onDelete: () -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var selectedSection: ProjectSection?
    @State private var showingAddSection = false
    @State private var showingDeleteConfirm = false
    @State private var newSectionTitle = ""
    @State private var newSectionIcon = "folder.fill"

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    // Header
                    HStack(spacing: 14) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .fill(project.type.color.opacity(0.15))
                                .frame(width: 52, height: 52)
                            Image(systemName: project.type.icon)
                                .font(.system(size: 22, weight: .semibold))
                                .foregroundStyle(project.type.color)
                        }
                        VStack(alignment: .leading, spacing: 3) {
                            TextField("Project Name", text: $project.name)
                                .font(.system(size: 17, weight: .bold, design: .rounded))
                            Text(project.type.label)
                                .font(.system(size: 12, design: .rounded)).foregroundStyle(.secondary)
                        }
                        Spacer()
                        if project.totalBudget > 0 {
                            VStack(alignment: .trailing, spacing: 2) {
                                Text("BUDGET").font(.system(size: 9, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                                Text(project.totalBudget, format: .currency(code: "USD"))
                                    .font(.system(size: 14, weight: .bold, design: .rounded))
                            }
                        }
                    }
                    .padding(14)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(palette.border, lineWidth: 1))

                    if !project.description.isEmpty {
                        TextField("Description", text: $project.description, axis: .vertical)
                            .font(.system(size: 13, design: .rounded))
                            .foregroundStyle(.secondary)
                            .padding(12)
                            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 10))
                    }

                    // Sections
                    ForEach($project.sections) { $section in
                        SectionCard(section: $section, palette: palette) {
                            selectedSection = section
                        }
                    }

                    // Add section
                    Button {
                        showingAddSection = true
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: "plus.circle.fill").foregroundStyle(palette.primaryButton)
                            Text("Add Section")
                                .font(.system(size: 13, weight: .semibold, design: .rounded))
                                .foregroundStyle(palette.primaryButton)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(12)
                        .background(palette.primaryButton.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(palette.primaryButton.opacity(0.3), lineWidth: 1))
                    }
                    .buttonStyle(.plain)
                }
                .padding(16)
            }
            .background(
                LinearGradient(colors: [palette.backgroundTop, palette.backgroundBottom], startPoint: .top, endPoint: .bottom)
                    .ignoresSafeArea()
            )
            .navigationTitle(project.name)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { onUpdate(project); dismiss() }
                }
                ToolbarItem(placement: .destructiveAction) {
                    Button(role: .destructive) { showingDeleteConfirm = true } label: {
                        Image(systemName: "trash").foregroundStyle(.red)
                    }
                }
            }
        }
        .sheet(item: $selectedSection) { sec in
            if let i = project.sections.firstIndex(where: { $0.id == sec.id }) {
                SectionDetailSheet(section: $project.sections[i], palette: palette) {
                    selectedSection = nil
                }
            }
        }
        .alert("New Section", isPresented: $showingAddSection) {
            TextField("Section title", text: $newSectionTitle)
            Button("Add") {
                let sec = ProjectSection(id: UUID(), title: newSectionTitle.isEmpty ? "New Section" : newSectionTitle, icon: "folder.fill", items: [], isExpanded: true)
                project.sections.append(sec)
                newSectionTitle = ""
                project.updatedAt = Date()
            }
            Button("Cancel", role: .cancel) { newSectionTitle = "" }
        }
        .confirmationDialog("Delete Project?", isPresented: $showingDeleteConfirm, titleVisibility: .visible) {
            Button("Delete", role: .destructive) { onDelete(); dismiss() }
        }
    }
}

private struct SectionCard: View {
    @Binding var section: ProjectSection
    let palette: QuailThemePalette
    let onOpenDetail: () -> Void

    var completedDecisions: Int {
        section.items.filter { $0.type == .decision && $0.options.contains(where: \.isSelected) }.count
    }
    var totalDecisions: Int {
        section.items.filter { $0.type == .decision }.count
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Section header
            Button(action: onOpenDetail) {
                HStack(spacing: 10) {
                    Image(systemName: section.icon)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(.secondary)
                        .frame(width: 22)
                    Text(section.title)
                        .font(.system(size: 14, weight: .bold, design: .rounded))
                    Spacer()
                    // Progress indicator for decisions
                    if totalDecisions > 0 {
                        Text("\(completedDecisions)/\(totalDecisions) decided")
                            .font(.system(size: 10, weight: .medium, design: .rounded))
                            .foregroundStyle(completedDecisions == totalDecisions ? .green : .secondary)
                    }
                    if !section.items.isEmpty {
                        Text("\(section.items.count)")
                            .font(.system(size: 10, weight: .bold, design: .rounded))
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 6).padding(.vertical, 3)
                            .background(palette.elevatedSurface, in: Capsule())
                    }
                    Image(systemName: "chevron.right")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundStyle(.secondary)
                }
                .padding(12)
            }
            .buttonStyle(.plain)

            // Preview first 2 items
            if !section.items.isEmpty {
                Divider().padding(.horizontal, 12)
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(section.items.prefix(2)) { item in
                        ItemPreviewRow(item: item, palette: palette)
                        if item.id != section.items.prefix(2).last?.id {
                            Divider().padding(.leading, 36)
                        }
                    }
                    if section.items.count > 2 {
                        Text("+ \(section.items.count - 2) more")
                            .font(.system(size: 11, design: .rounded))
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 12).padding(.vertical, 6)
                    }
                }
            }
        }
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

private struct ItemPreviewRow: View {
    let item: ProjectItem
    let palette: QuailThemePalette

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: item.type.icon)
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
                .frame(width: 22)

            switch item.type {
            case .decision:
                let selected = item.options.first(where: \.isSelected)
                VStack(alignment: .leading, spacing: 1) {
                    Text(item.title).font(.system(size: 12, weight: .medium, design: .rounded)).lineLimit(1)
                    if let sel = selected {
                        Text("→ \(sel.title)")
                            .font(.system(size: 10, design: .rounded))
                            .foregroundStyle(.green)
                    } else {
                        Text("Undecided")
                            .font(.system(size: 10, design: .rounded))
                            .foregroundStyle(.orange)
                    }
                }
            case .budget:
                HStack {
                    Text(item.title).font(.system(size: 12, weight: .medium, design: .rounded)).lineLimit(1)
                    Spacer()
                    if let amt = item.amount {
                        Text(amt, format: .currency(code: "USD"))
                            .font(.system(size: 12, weight: .semibold, design: .rounded))
                    }
                }
            default:
                Text(item.title).font(.system(size: 12, weight: .medium, design: .rounded)).lineLimit(1)
                if !item.body.isEmpty {
                    Spacer()
                    Text(item.body).font(.system(size: 10, design: .rounded)).foregroundStyle(.secondary).lineLimit(1)
                }
            }

            Spacer(minLength: 0)
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
    }
}

// MARK: - Section detail sheet

struct SectionDetailSheet: View {
    @Binding var section: ProjectSection
    let palette: QuailThemePalette
    let onDone: () -> Void

    @State private var showingAddItem = false
    @State private var addingItemType: ProjectItemType = .note
    @State private var selectedItem: ProjectItem?

    var body: some View {
        NavigationStack {
            List {
                ForEach($section.items) { $item in
                    Button {
                        selectedItem = item
                    } label: {
                        ItemRow(item: item, palette: palette)
                    }
                    .listRowBackground(palette.surface)
                    .listRowInsets(EdgeInsets(top: 4, leading: 12, bottom: 4, trailing: 12))
                }
                .onDelete { section.items.remove(atOffsets: $0) }
                .onMove { section.items.move(fromOffsets: $0, toOffset: $1) }
            }
            .listStyle(.plain)
            .background(
                LinearGradient(colors: [palette.backgroundTop, palette.backgroundBottom], startPoint: .top, endPoint: .bottom).ignoresSafeArea()
            )
            .navigationTitle(section.title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done", action: onDone)
                }
                ToolbarItem(placement: .primaryAction) {
                    Menu {
                        ForEach(ProjectItemType.allCases, id: \.rawValue) { t in
                            Button {
                                addingItemType = t
                                showingAddItem = true
                            } label: {
                                Label(t.label, systemImage: t.icon)
                            }
                        }
                    } label: {
                        Image(systemName: "plus")
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    EditButton()
                }
            }
        }
        .sheet(isPresented: $showingAddItem) {
            AddItemSheet(type: addingItemType, palette: palette) { newItem in
                section.items.append(newItem)
            }
            .presentationDetents([.large])
        }
        .sheet(item: $selectedItem) { item in
            if let i = section.items.firstIndex(where: { $0.id == item.id }) {
                ItemDetailSheet(item: $section.items[i], palette: palette) {
                    selectedItem = nil
                }
                .presentationDetents([.large])
            }
        }
    }
}

private struct ItemRow: View {
    let item: ProjectItem
    let palette: QuailThemePalette

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: item.type.icon)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(.secondary)
                .frame(width: 20)

            VStack(alignment: .leading, spacing: 2) {
                Text(item.title).font(.system(size: 13, weight: .semibold, design: .rounded))

                switch item.type {
                case .decision:
                    if let sel = item.options.first(where: \.isSelected) {
                        HStack(spacing: 4) {
                            Image(systemName: "checkmark.circle.fill").font(.system(size: 10)).foregroundStyle(.green)
                            Text(sel.title).font(.system(size: 11, design: .rounded)).foregroundStyle(.green)
                        }
                    } else {
                        Text("\(item.options.count) options · Undecided")
                            .font(.system(size: 11, design: .rounded)).foregroundStyle(.orange)
                    }
                case .budget:
                    if let a = item.amount {
                        Text("\(item.amountLabel.isEmpty ? "Estimated" : item.amountLabel): \(a, format: .currency(code: "USD"))")
                            .font(.system(size: 11, design: .rounded)).foregroundStyle(.secondary)
                    }
                case .reference:
                    if !item.url.isEmpty {
                        Text(item.url).font(.system(size: 10, design: .rounded)).foregroundStyle(.blue).lineLimit(1)
                    }
                case .photo:
                    if item.imageFilename != nil { Text("Photo attached").font(.system(size: 11, design: .rounded)).foregroundStyle(.secondary) }
                case .note:
                    if !item.body.isEmpty {
                        Text(item.body).font(.system(size: 11, design: .rounded)).foregroundStyle(.secondary).lineLimit(1)
                    }
                }
            }

            Spacer()
            Image(systemName: "chevron.right").font(.system(size: 11)).foregroundStyle(.secondary)
        }
        .padding(.vertical, 6)
    }
}

// MARK: - Add item sheet

private struct AddItemSheet: View {
    let type: ProjectItemType
    let palette: QuailThemePalette
    let onSave: (ProjectItem) -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var title = ""
    @State private var noteBody = ""
    @State private var url = ""
    @State private var amount: String = ""
    @State private var amountLabel = "Estimated"
    @State private var options: [DecisionOption] = []
    @State private var newOptionTitle = ""
    @State private var pickerItem: PhotosPickerItem?
    @State private var selectedImage: UIImage?

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Button("Cancel") { dismiss() }.foregroundStyle(.secondary)
                Spacer()
                HStack(spacing: 6) {
                    Image(systemName: type.icon)
                    Text("New \(type.label)")
                }
                .font(.system(size: 15, weight: .bold, design: .rounded))
                Spacer()
                Button("Add") { save() }
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
            }
            .padding(.horizontal, 16).padding(.vertical, 14)
            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    inputField("Title", binding: $title, placeholder: titlePlaceholder)

                    switch type {
                    case .note:
                        inputField("Content", binding: $noteBody, placeholder: "Write your note…", multiline: true)

                    case .decision:
                        VStack(alignment: .leading, spacing: 8) {
                            Text("OPTIONS").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                            ForEach($options) { $opt in
                                HStack(spacing: 8) {
                                    TextField("Option", text: $opt.title)
                                        .font(.system(size: 13, design: .rounded))
                                        .padding(9)
                                        .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 8))
                                    Button { options.removeAll { $0.id == opt.id } } label: {
                                        Image(systemName: "xmark.circle.fill").foregroundStyle(.secondary)
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                            HStack {
                                TextField("Add option…", text: $newOptionTitle)
                                    .font(.system(size: 13, design: .rounded))
                                    .onSubmit { addOption() }
                                Button(action: addOption) {
                                    Image(systemName: "plus.circle.fill").foregroundStyle(palette.primaryButton)
                                }
                                .buttonStyle(.plain)
                                .disabled(newOptionTitle.isEmpty)
                            }
                            .padding(9)
                            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 8))
                        }

                    case .budget:
                        HStack(spacing: 10) {
                            VStack(alignment: .leading, spacing: 6) {
                                Text("LABEL").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                                TextField("Estimated / Actual", text: $amountLabel)
                                    .font(.system(size: 13, design: .rounded)).padding(9)
                                    .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 8))
                            }
                            VStack(alignment: .leading, spacing: 6) {
                                Text("AMOUNT").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                                TextField("0.00", text: $amount).keyboardType(.decimalPad)
                                    .font(.system(size: 13, design: .rounded)).padding(9)
                                    .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 8))
                            }
                        }

                    case .reference:
                        inputField("URL", binding: $url, placeholder: "https://…")
                        inputField("Notes", binding: $noteBody, placeholder: "Why this reference is useful…", multiline: true)

                    case .photo:
                        VStack(alignment: .leading, spacing: 8) {
                            Text("PHOTO").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                            PhotosPicker(selection: $pickerItem, matching: .images) {
                                if let img = selectedImage {
                                    Image(uiImage: img)
                                        .resizable().scaledToFit()
                                        .frame(maxWidth: .infinity, maxHeight: 180)
                                        .clipShape(RoundedRectangle(cornerRadius: 10))
                                } else {
                                    HStack {
                                        Image(systemName: "photo.badge.plus")
                                        Text("Choose Photo")
                                    }
                                    .frame(maxWidth: .infinity, minHeight: 80)
                                    .foregroundStyle(palette.primaryButton)
                                    .background(palette.primaryButton.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
                                }
                            }
                            .onChange(of: pickerItem) { _, item in
                                Task {
                                    if let data = try? await item?.loadTransferable(type: Data.self) {
                                        selectedImage = UIImage(data: data)
                                    }
                                }
                            }
                        }
                        inputField("Caption", binding: $noteBody, placeholder: "Optional caption…")
                    }
                }
                .padding(16)
            }
        }
    }

    private var titlePlaceholder: String {
        switch type {
        case .note: return "Note title"
        case .decision: return "What are you deciding?"
        case .budget: return "Item name"
        case .reference: return "Reference title"
        case .photo: return "Photo title"
        }
    }

    @ViewBuilder private func inputField(_ label: String, binding: Binding<String>, placeholder: String, multiline: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label.uppercased()).font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
            if multiline {
                TextField(placeholder, text: binding, axis: .vertical)
                    .lineLimit(3...).font(.system(size: 13, design: .rounded)).padding(9)
                    .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 8))
            } else {
                TextField(placeholder, text: binding)
                    .font(.system(size: 13, design: .rounded)).padding(9)
                    .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    private func addOption() {
        guard !newOptionTitle.isEmpty else { return }
        options.append(DecisionOption(id: UUID(), title: newOptionTitle, notes: "", pros: [], cons: [], estimatedCost: nil, isSelected: false))
        newOptionTitle = ""
    }

    private func save() {
        var filename: String?
        if let img = selectedImage {
            filename = ProjectStore.shared.saveImage(img, id: UUID())
        }
        let item = ProjectItem(
            id: UUID(), type: type, title: title.isEmpty ? type.label : title,
            body: noteBody, options: options,
            amount: Double(amount),
            amountLabel: amountLabel.isEmpty ? "Estimated" : amountLabel,
            url: url, imageFilename: filename, createdAt: Date()
        )
        onSave(item)
        dismiss()
    }
}

// MARK: - Item detail sheet

struct ItemDetailSheet: View {
    @Binding var item: ProjectItem
    let palette: QuailThemePalette
    let onDone: () -> Void

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    // Title
                    TextField("Title", text: $item.title)
                        .font(.system(size: 18, weight: .bold, design: .rounded))
                        .padding(12)
                        .background(palette.surface, in: RoundedRectangle(cornerRadius: 10))

                    switch item.type {
                    case .note:
                        NoteItemView(item: $item, palette: palette)
                    case .decision:
                        DecisionItemView(item: $item, palette: palette)
                    case .budget:
                        BudgetItemView(item: $item, palette: palette)
                    case .reference:
                        ReferenceItemView(item: $item, palette: palette)
                    case .photo:
                        PhotoItemView(item: $item, palette: palette)
                    }
                }
                .padding(16)
            }
            .background(
                LinearGradient(colors: [palette.backgroundTop, palette.backgroundBottom], startPoint: .top, endPoint: .bottom).ignoresSafeArea()
            )
            .navigationTitle(item.type.label)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done", action: onDone)
                }
            }
        }
    }
}

private struct NoteItemView: View {
    @Binding var item: ProjectItem
    let palette: QuailThemePalette
    var body: some View {
        TextField("Write your note…", text: $item.body, axis: .vertical)
            .font(.system(size: 14, design: .rounded)).lineLimit(5...)
            .padding(12)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 10))
    }
}

private struct DecisionItemView: View {
    @Binding var item: ProjectItem
    let palette: QuailThemePalette
    @State private var newOptionTitle = ""
    @State private var expandedOptionId: UUID?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("OPTIONS").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                Spacer()
                if let sel = item.options.first(where: \.isSelected) {
                    HStack(spacing: 4) {
                        Image(systemName: "checkmark.circle.fill").font(.system(size: 11)).foregroundStyle(.green)
                        Text(sel.title).font(.system(size: 11, weight: .semibold, design: .rounded)).foregroundStyle(.green)
                    }
                }
            }

            ForEach($item.options) { $opt in
                VStack(alignment: .leading, spacing: 0) {
                    HStack(spacing: 10) {
                        Button {
                            // Toggle selection — only one selected at a time
                            for i in item.options.indices { item.options[i].isSelected = (item.options[i].id == opt.id && !opt.isSelected) }
                        } label: {
                            Image(systemName: opt.isSelected ? "checkmark.circle.fill" : "circle")
                                .font(.system(size: 18))
                                .foregroundStyle(opt.isSelected ? .green : .secondary)
                        }
                        .buttonStyle(.plain)

                        TextField("Option name", text: $opt.title)
                            .font(.system(size: 13, weight: .semibold, design: .rounded))

                        Spacer()

                        if let cost = opt.estimatedCost {
                            Text(cost, format: .currency(code: "USD"))
                                .font(.system(size: 12, design: .rounded)).foregroundStyle(.secondary)
                        }

                        Button {
                            expandedOptionId = expandedOptionId == opt.id ? nil : opt.id
                        } label: {
                            Image(systemName: expandedOptionId == opt.id ? "chevron.up" : "chevron.down")
                                .font(.system(size: 11)).foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(12)

                    if expandedOptionId == opt.id {
                        Divider().padding(.horizontal, 12)
                        VStack(alignment: .leading, spacing: 10) {
                            TextField("Notes", text: $opt.notes, axis: .vertical)
                                .font(.system(size: 12, design: .rounded)).lineLimit(2...)
                                .padding(8)
                                .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))

                            HStack(spacing: 10) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("PROS").font(.system(size: 9, weight: .bold, design: .rounded)).foregroundStyle(.green)
                                    ForEach($opt.pros, id: \.self) { $pro in
                                        TextField("Pro", text: $pro).font(.system(size: 11, design: .rounded))
                                    }
                                    Button {
                                        opt.pros.append("")
                                    } label: {
                                        Text("+ Add").font(.system(size: 11, design: .rounded)).foregroundStyle(.green)
                                    }.buttonStyle(.plain)
                                }
                                Divider()
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("CONS").font(.system(size: 9, weight: .bold, design: .rounded)).foregroundStyle(.red)
                                    ForEach($opt.cons, id: \.self) { $con in
                                        TextField("Con", text: $con).font(.system(size: 11, design: .rounded))
                                    }
                                    Button {
                                        opt.cons.append("")
                                    } label: {
                                        Text("+ Add").font(.system(size: 11, design: .rounded)).foregroundStyle(.red)
                                    }.buttonStyle(.plain)
                                }
                            }

                            HStack {
                                Text("Est. Cost").font(.system(size: 11, design: .rounded)).foregroundStyle(.secondary)
                                Spacer()
                                TextField("0.00", value: $opt.estimatedCost, format: .number)
                                    .keyboardType(.decimalPad)
                                    .font(.system(size: 12, design: .rounded))
                                    .multilineTextAlignment(.trailing)
                            }
                        }
                        .padding(.horizontal, 12).padding(.bottom, 10)
                    }
                }
                .background(palette.surface, in: RoundedRectangle(cornerRadius: 10))
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(opt.isSelected ? Color.green : palette.border, lineWidth: opt.isSelected ? 2 : 1)
                )
            }

            // Add option
            HStack {
                TextField("Add option…", text: $newOptionTitle)
                    .font(.system(size: 13, design: .rounded))
                    .onSubmit {
                        if !newOptionTitle.isEmpty {
                            item.options.append(DecisionOption(id: UUID(), title: newOptionTitle, notes: "", pros: [], cons: [], estimatedCost: nil, isSelected: false))
                            newOptionTitle = ""
                        }
                    }
                Button {
                    if !newOptionTitle.isEmpty {
                        item.options.append(DecisionOption(id: UUID(), title: newOptionTitle, notes: "", pros: [], cons: [], estimatedCost: nil, isSelected: false))
                        newOptionTitle = ""
                    }
                } label: {
                    Image(systemName: "plus.circle.fill").foregroundStyle(palette.primaryButton)
                }.buttonStyle(.plain)
            }
            .padding(10)
            .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 10))
        }
    }
}

private struct BudgetItemView: View {
    @Binding var item: ProjectItem
    let palette: QuailThemePalette
    @State private var amountString = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("LABEL").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                    TextField("Estimated / Actual", text: $item.amountLabel)
                        .font(.system(size: 13, design: .rounded)).padding(10)
                        .background(palette.surface, in: RoundedRectangle(cornerRadius: 8))
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("AMOUNT ($)").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                    TextField("0.00", text: $amountString)
                        .keyboardType(.decimalPad)
                        .font(.system(size: 13, design: .rounded)).padding(10)
                        .background(palette.surface, in: RoundedRectangle(cornerRadius: 8))
                        .onChange(of: amountString) { _, v in item.amount = Double(v) }
                }
            }
            TextField("Notes", text: $item.body, axis: .vertical)
                .font(.system(size: 13, design: .rounded)).lineLimit(2...)
                .padding(10).background(palette.surface, in: RoundedRectangle(cornerRadius: 8))
        }
        .onAppear { amountString = item.amount.map { String($0) } ?? "" }
    }
}

private struct ReferenceItemView: View {
    @Binding var item: ProjectItem
    let palette: QuailThemePalette

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                Text("URL").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                TextField("https://…", text: $item.url)
                    .keyboardType(.URL).autocapitalization(.none)
                    .font(.system(size: 13, design: .rounded)).padding(10)
                    .background(palette.surface, in: RoundedRectangle(cornerRadius: 8))
            }
            VStack(alignment: .leading, spacing: 6) {
                Text("NOTES").font(.system(size: 10, weight: .bold, design: .rounded)).foregroundStyle(.secondary)
                TextField("Why this is useful…", text: $item.body, axis: .vertical)
                    .font(.system(size: 13, design: .rounded)).lineLimit(3...)
                    .padding(10).background(palette.surface, in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }
}

private struct PhotoItemView: View {
    @Binding var item: ProjectItem
    let palette: QuailThemePalette
    @State private var pickerItem: PhotosPickerItem?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let fn = item.imageFilename, let img = ProjectStore.shared.loadImage(filename: fn) {
                Image(uiImage: img)
                    .resizable().scaledToFit()
                    .frame(maxWidth: .infinity)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
            }

            PhotosPicker(selection: $pickerItem, matching: .images) {
                Label(item.imageFilename == nil ? "Choose Photo" : "Replace Photo", systemImage: "photo.badge.plus")
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .foregroundStyle(palette.primaryButton)
                    .frame(maxWidth: .infinity)
                    .padding(10)
                    .background(palette.primaryButton.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
            }
            .onChange(of: pickerItem) { _, newItem in
                Task {
                    if let data = try? await newItem?.loadTransferable(type: Data.self),
                       let img = UIImage(data: data) {
                        item.imageFilename = ProjectStore.shared.saveImage(img, id: item.id)
                    }
                }
            }

            TextField("Caption", text: $item.body, axis: .vertical)
                .font(.system(size: 13, design: .rounded)).lineLimit(2...)
                .padding(10).background(palette.surface, in: RoundedRectangle(cornerRadius: 8))
        }
    }
}
