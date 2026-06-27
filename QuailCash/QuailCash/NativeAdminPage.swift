import SwiftUI
import Combine

// MARK: - Payload models

struct InfraMetricsPayload: Decodable {
    let render: RenderMetrics
    let neon: NeonMetrics
}

struct RenderMetrics: Decodable {
    let error: String?
    let services: [RenderService]?
}

struct RenderService: Decodable, Identifiable {
    let id: String?
    let name: String?
    let type: String?
    let suspended: String?
    let serviceDetails: RenderServiceDetails?
    let latestDeploy: RenderDeploy?
    let updatedAt: String?
    let createdAt: String?
}

struct RenderServiceDetails: Decodable {
    let env: String?
    let region: String?
    let plan: String?
    let numInstances: Int?
    let healthCheckPath: String?
    let autoDeploy: String?
    let disk: RenderDisk?
}

struct RenderDisk: Decodable {
    let name: String?
    let sizeGB: Int?
    let mountPath: String?
}

struct RenderDeploy: Decodable {
    let id: String?
    let status: String?
    let trigger: String?
    let finishedAt: String?
    let commitMessage: String?
    let commitId: String?
}

struct NeonMetrics: Decodable {
    let error: String?
    let project: NeonProject?
    let branches: [NeonBranch]?
    let endpoints: [NeonEndpoint]?
    let recentOperations: [NeonOperation]?
}

struct NeonProject: Decodable {
    let id: String?
    let name: String?
    let region: String?
    let pgVersion: Int?
    let subscriptionType: String?
    let cpuUsedSec: Double?
    let dataStorageBytesHour: Double?
    let storageBytesUsed: Double?
    let dataTransferBytes: Double?
    let writtenDataBytes: Double?
    let activeTimeSeconds: Double?
    let computeTimeSeconds: Double?
    let createdAt: String?
    let updatedAt: String?
    let quota: NeonQuota?
    let defaultEndpointSettings: NeonDefaultEndpointSettings?
}

struct NeonQuota: Decodable {
    let activeTimeSeconds: Double?
    let computeTimeSeconds: Double?
    let writtenDataBytes: Double?
    let dataTransferBytes: Double?
    let storageLimitBytes: Double?
}

struct NeonDefaultEndpointSettings: Decodable {
    let autoscalingLimitMinCu: Double?
    let autoscalingLimitMaxCu: Double?
    let suspendTimeoutSeconds: Int?
}

struct NeonBranch: Decodable, Identifiable {
    let branchId: String?
    let name: String?
    let `default`: Bool?
    let currentState: String?
    let logicalSize: Int?
    let cpuUsedSec: Double?
    let updatedAt: String?

    var id: String { branchId ?? name ?? UUID().uuidString }

    enum CodingKeys: String, CodingKey {
        case branchId = "id"
        case name, `default`, currentState, logicalSize, cpuUsedSec, updatedAt
    }
}

struct NeonEndpoint: Decodable, Identifiable {
    let endpointId: String?
    let host: String?
    let type: String?
    let currentState: String?
    let pendingState: String?
    let region: String?
    let autoscalingLimitMinCu: Double?
    let autoscalingLimitMaxCu: Double?
    let suspendTimeoutSeconds: Int?
    let updatedAt: String?

    var id: String { endpointId ?? host ?? UUID().uuidString }

    enum CodingKeys: String, CodingKey {
        case endpointId = "id"
        case host, type, currentState, pendingState, region
        case autoscalingLimitMinCu, autoscalingLimitMaxCu, suspendTimeoutSeconds, updatedAt
    }
}

struct NeonOperation: Decodable, Identifiable {
    let opId: String?
    let action: String?
    let status: String?
    let error: String?
    let createdAt: String?
    let totalDurationMs: Int?

    var id: String { opId ?? UUID().uuidString }

    enum CodingKeys: String, CodingKey {
        case opId = "id"
        case action, status, error, createdAt, totalDurationMs
    }
}

// MARK: - View model

@MainActor
final class AdminDashboardViewModel: ObservableObject {
    @Published var metrics: InfraMetricsPayload?
    @Published var isLoading = false
    @Published var error: String?
    @Published var lastRefreshed: Date?

    func load() async {
        isLoading = true
        error = nil
        do {
            metrics = try await QuailCashAPI.shared.fetchInfraMetrics()
            lastRefreshed = Date()
        } catch QuailCashAPIError.unauthorized {
            error = "Access denied — admin only."
        } catch {
            self.error = "Failed to load metrics."
        }
        isLoading = false
    }
}

// MARK: - Page

struct AdminDashboardPageView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    @EnvironmentObject private var navigator: AppNavigator
    @StateObject private var vm = AdminDashboardViewModel()

    var body: some View {
        let palette = QuailTheme.palette(for: themeSelection)
        AppChromeFrame(
            title: "Quail Admin",
            badgeValue: nil,
            selectedTab: nil,
            showsBottomBar: false,
            showsStandaloneBar: true,
            onLeadingTap: { navigator.goBack() },
            onTrailingTap: { Task { await vm.load() } }
        ) {
            Group {
                if vm.isLoading && vm.metrics == nil {
                    VStack(spacing: 12) {
                        Spacer()
                        ProgressView()
                        Text("Loading metrics…")
                            .font(.system(size: 13, design: .rounded))
                            .foregroundStyle(.secondary)
                        Spacer()
                    }
                } else if let err = vm.error, vm.metrics == nil {
                    VStack(spacing: 12) {
                        Spacer()
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.system(size: 32))
                            .foregroundStyle(.orange)
                        Text(err)
                            .font(.system(size: 14, design: .rounded))
                            .foregroundStyle(.secondary)
                        Button("Retry") { Task { await vm.load() } }
                            .buttonStyle(.borderedProminent)
                        Spacer()
                    }
                } else {
                    AppPageScroll {
                        VStack(spacing: 24) {
                            if let m = vm.metrics {
                                RenderSection(render: m.render, palette: palette)
                                NeonSection(neon: m.neon, palette: palette)
                            }
                            if let refreshed = vm.lastRefreshed {
                                Text("Updated \(refreshed.formatted(.relative(presentation: .named)))")
                                    .font(.system(size: 11, design: .rounded))
                                    .foregroundStyle(.tertiary)
                                    .frame(maxWidth: .infinity, alignment: .center)
                            }
                        }
                    }
                }
            }
        }
        .task { await vm.load() }
    }
}

// MARK: - Render section

private struct RenderSection: View {
    let render: RenderMetrics
    let palette: QuailThemePalette

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "Render", icon: "cloud.fill", iconColor: .green)
            if let err = render.error {
                ErrorBanner(message: err, palette: palette)
            } else if let services = render.services, !services.isEmpty {
                VStack(spacing: 10) {
                    ForEach(services) { svc in
                        RenderServiceCard(service: svc, palette: palette)
                    }
                }
            } else {
                Text("No services found.")
                    .font(.system(size: 13, design: .rounded)).foregroundStyle(.secondary)
            }
        }
    }
}

private struct RenderServiceCard: View {
    let service: RenderService
    let palette: QuailThemePalette

    private var isSuspended: Bool { service.suspended?.lowercased() == "suspended" }

    private var deployStatusColor: Color {
        switch service.latestDeploy?.status?.lowercased() {
        case "live": return .green
        case "build_failed", "update_failed", "canceled": return .red
        case "building", "update_in_progress", "in_progress": return .orange
        default: return .secondary
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header row
            HStack(spacing: 8) {
                Circle()
                    .fill(isSuspended ? Color.orange : Color.green)
                    .frame(width: 8, height: 8)
                Text(service.name ?? "Unknown")
                    .font(.system(size: 15, weight: .bold, design: .rounded))
                Spacer()
                if let t = service.type {
                    Text(t.replacingOccurrences(of: "_", with: " ").capitalized)
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 8).padding(.vertical, 3)
                        .background(palette.elevatedSurface, in: Capsule())
                }
            }

            // Service detail chips
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    if let region = service.serviceDetails?.region {
                        MetaBadge(label: region, icon: "location.fill", palette: palette)
                    }
                    if let plan = service.serviceDetails?.plan {
                        MetaBadge(label: plan, icon: "creditcard.fill", palette: palette)
                    }
                    if let env = service.serviceDetails?.env {
                        MetaBadge(label: env, icon: "cpu.fill", palette: palette)
                    }
                    if let n = service.serviceDetails?.numInstances {
                        MetaBadge(label: "\(n) instance\(n == 1 ? "" : "s")", icon: "square.stack.fill", palette: palette)
                    }
                    if let autoDeploy = service.serviceDetails?.autoDeploy {
                        MetaBadge(label: "auto-deploy \(autoDeploy)", icon: "arrow.triangle.2.circlepath", palette: palette)
                    }
                    if let disk = service.serviceDetails?.disk, let gb = disk.sizeGB {
                        MetaBadge(label: "\(gb) GB disk", icon: "internaldrive.fill", palette: palette)
                    }
                }
            }

            // Latest deploy
            if let deploy = service.latestDeploy {
                Divider()
                HStack(spacing: 8) {
                    Image(systemName: "arrow.up.circle.fill")
                        .foregroundStyle(deployStatusColor)
                        .font(.system(size: 13))
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Text(deploy.status?.replacingOccurrences(of: "_", with: " ").capitalized ?? "Unknown")
                                .font(.system(size: 12, weight: .semibold, design: .rounded))
                                .foregroundStyle(deployStatusColor)
                            if let sha = deploy.commitId {
                                Text(sha)
                                    .font(.system(size: 11, design: .monospaced))
                                    .foregroundStyle(.secondary)
                            }
                        }
                        if let msg = deploy.commitMessage {
                            Text(msg)
                                .font(.system(size: 11, design: .rounded))
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
                    }
                    Spacer()
                    if let t = deploy.finishedAt {
                        Text(shortDate(t))
                            .font(.system(size: 10, design: .rounded))
                            .foregroundStyle(.tertiary)
                    }
                }
            }
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

// MARK: - Neon section

private struct NeonSection: View {
    let neon: NeonMetrics
    let palette: QuailThemePalette

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeader(title: "Neon", icon: "cylinder.split.1x2.fill", iconColor: .teal)
            if let err = neon.error {
                ErrorBanner(message: err, palette: palette)
            } else {
                if let proj = neon.project {
                    NeonProjectCard(project: proj, palette: palette)
                }
                if let endpoints = neon.endpoints, !endpoints.isEmpty {
                    SubSectionHeader(title: "Computes")
                    VStack(spacing: 8) {
                        ForEach(endpoints) { ep in
                            NeonEndpointRow(endpoint: ep, palette: palette)
                        }
                    }
                }
                if let branches = neon.branches, !branches.isEmpty {
                    SubSectionHeader(title: "Branches")
                    VStack(spacing: 6) {
                        ForEach(branches) { branch in
                            NeonBranchRow(branch: branch, palette: palette)
                        }
                    }
                }
                if let ops = neon.recentOperations, !ops.isEmpty {
                    SubSectionHeader(title: "Recent Operations")
                    VStack(spacing: 6) {
                        ForEach(ops.prefix(5)) { op in
                            NeonOperationRow(op: op, palette: palette)
                        }
                    }
                }
            }
        }
    }
}

private struct NeonProjectCard: View {
    let project: NeonProject
    let palette: QuailThemePalette

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text(project.name ?? "Unknown Project")
                    .font(.system(size: 15, weight: .bold, design: .rounded))
                Spacer()
                if let pg = project.pgVersion {
                    Text("pg\(pg)")
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 8).padding(.vertical, 3)
                        .background(palette.elevatedSurface, in: Capsule())
                }
            }

            if let region = project.region {
                MetaBadge(label: region, icon: "location.fill", palette: palette)
            }

            // Usage vs limits
            Divider()
            VStack(alignment: .leading, spacing: 8) {
                Text("USAGE vs LIMITS")
                    .font(.system(size: 10, weight: .bold, design: .rounded))
                    .foregroundStyle(.secondary)

                let quota = project.quota
                let hasAnyBar = (quota?.computeTimeSeconds ?? 0) > 0
                    || (quota?.activeTimeSeconds ?? 0) > 0
                    || (quota?.dataTransferBytes ?? 0) > 0
                    || (quota?.storageLimitBytes ?? 0) > 0

                if hasAnyBar {
                    if let used = project.computeTimeSeconds, let limit = quota?.computeTimeSeconds, limit > 0 {
                        UsageBar(label: "Compute", used: used, limit: limit, format: { formatSeconds($0) }, palette: palette)
                    }
                    if let used = project.activeTimeSeconds, let limit = quota?.activeTimeSeconds, limit > 0 {
                        UsageBar(label: "Active time", used: used, limit: limit, format: { formatSeconds($0) }, palette: palette)
                    }
                    if let used = project.dataTransferBytes, let limit = quota?.dataTransferBytes, limit > 0 {
                        UsageBar(label: "Transfer", used: used, limit: limit, format: { formatBytes($0) }, palette: palette)
                    }
                    if let used = project.storageBytesUsed, let limit = quota?.storageLimitBytes, limit > 0 {
                        UsageBar(label: "Storage", used: used, limit: limit, format: { formatBytes($0) }, palette: palette)
                    }
                } else {
                    // No limit info — show raw metrics grid
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                        if let v = project.computeTimeSeconds { MetricCell(label: "Compute", value: formatSeconds(v)) }
                        if let v = project.activeTimeSeconds  { MetricCell(label: "Active", value: formatSeconds(v)) }
                        if let v = project.dataTransferBytes  { MetricCell(label: "Transfer", value: formatBytes(v)) }
                        if let v = project.storageBytesUsed   { MetricCell(label: "Storage", value: formatBytes(v)) }
                    }
                }
            }

            // Default endpoint settings
            if let s = project.defaultEndpointSettings {
                Divider()
                VStack(alignment: .leading, spacing: 6) {
                    Text("DEFAULT ENDPOINT")
                        .font(.system(size: 10, weight: .bold, design: .rounded))
                        .foregroundStyle(.secondary)
                    HStack(spacing: 16) {
                        if let min = s.autoscalingLimitMinCu, let max = s.autoscalingLimitMaxCu {
                            MetricCell(label: "Autoscale", value: "\(formatCu(min))–\(formatCu(max)) CU")
                        }
                        if let timeout = s.suspendTimeoutSeconds {
                            MetricCell(label: "Suspend after", value: timeout == 0 ? "never" : formatSeconds(Double(timeout)))
                        }
                    }
                }
            }
        }
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

private struct UsageBar: View {
    let label: String
    let used: Double
    let limit: Double
    let format: (Double) -> String
    let palette: QuailThemePalette

    private var fraction: Double { min(used / limit, 1.0) }
    private var fillColor: Color {
        if fraction > 0.9 { return .red }
        if fraction > 0.7 { return .orange }
        return .teal
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(label)
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                Spacer()
                Text("\(format(used)) / \(format(limit))")
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                    .foregroundStyle(fillColor)
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 4).fill(Color.secondary.opacity(0.15))
                    RoundedRectangle(cornerRadius: 4).fill(fillColor)
                        .frame(width: max(2, geo.size.width * fraction))
                }
            }
            .frame(height: 6)
        }
    }
}

private struct NeonEndpointRow: View {
    let endpoint: NeonEndpoint
    let palette: QuailThemePalette

    private var stateColor: Color {
        switch endpoint.currentState?.lowercased() {
        case "active": return .green
        case "idle": return .yellow
        default: return .secondary
        }
    }

    var body: some View {
        HStack(spacing: 10) {
            Circle().fill(stateColor).frame(width: 8, height: 8)
            VStack(alignment: .leading, spacing: 2) {
                Text(endpoint.type?.capitalized ?? "endpoint")
                    .font(.system(size: 13, weight: .semibold, design: .rounded))
                if let host = endpoint.host {
                    Text(host)
                        .font(.system(size: 10, design: .rounded))
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                Text(endpoint.currentState ?? "unknown")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(stateColor)
                if let min = endpoint.autoscalingLimitMinCu, let max = endpoint.autoscalingLimitMaxCu {
                    Text("\(formatCu(min))–\(formatCu(max)) CU")
                        .font(.system(size: 10, design: .rounded)).foregroundStyle(.secondary)
                }
                if let timeout = endpoint.suspendTimeoutSeconds {
                    Text(timeout == 0 ? "no suspend" : "suspend \(formatSeconds(Double(timeout)))")
                        .font(.system(size: 10, design: .rounded)).foregroundStyle(.secondary)
                }
            }
        }
        .padding(10)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

private struct NeonBranchRow: View {
    let branch: NeonBranch
    let palette: QuailThemePalette

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: branch.default == true ? "star.fill" : "arrow.triangle.branch")
                .font(.system(size: 12))
                .foregroundStyle(branch.default == true ? .yellow : .secondary)
                .frame(width: 18)
            Text(branch.name ?? "branch")
                .font(.system(size: 13, weight: .medium, design: .rounded))
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                if let size = branch.logicalSize {
                    Text(formatBytes(Double(size)))
                        .font(.system(size: 11, design: .rounded)).foregroundStyle(.secondary)
                }
                Text(branch.currentState ?? "")
                    .font(.system(size: 11, weight: .medium, design: .rounded)).foregroundStyle(.secondary)
            }
        }
        .padding(10)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

private struct NeonOperationRow: View {
    let op: NeonOperation
    let palette: QuailThemePalette

    private var statusColor: Color {
        switch op.status?.lowercased() {
        case "finished": return .green
        case "failed": return .red
        case "running": return .orange
        default: return .secondary
        }
    }

    var body: some View {
        HStack(spacing: 10) {
            Circle().fill(statusColor).frame(width: 7, height: 7)
            Text(op.action?.replacingOccurrences(of: "_", with: " ") ?? "operation")
                .font(.system(size: 12, weight: .medium, design: .rounded))
                .lineLimit(1)
            Spacer()
            VStack(alignment: .trailing, spacing: 2) {
                if let ms = op.totalDurationMs {
                    Text("\(ms)ms")
                        .font(.system(size: 10, design: .rounded)).foregroundStyle(.secondary)
                }
                if let t = op.createdAt {
                    Text(shortDate(t))
                        .font(.system(size: 10, design: .rounded)).foregroundStyle(.tertiary)
                }
            }
        }
        .padding(.horizontal, 10).padding(.vertical, 8)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(palette.border, lineWidth: 1))
    }
}

// MARK: - Shared sub-views

private struct SectionHeader: View {
    let title: String
    let icon: String
    let iconColor: Color

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(iconColor)
            Text(title.uppercased())
                .font(.system(size: 13, weight: .bold, design: .rounded))
                .foregroundStyle(.secondary)
        }
    }
}

private struct SubSectionHeader: View {
    let title: String
    var body: some View {
        Text(title.uppercased())
            .font(.system(size: 11, weight: .bold, design: .rounded))
            .foregroundStyle(.secondary)
            .padding(.top, 4)
    }
}

private struct ErrorBanner: View {
    let message: String
    let palette: QuailThemePalette

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.circle.fill").foregroundStyle(.orange)
            Text(message).font(.system(size: 12, design: .rounded)).foregroundStyle(.secondary)
        }
        .padding(10)
        .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.orange.opacity(0.2), lineWidth: 1))
    }
}

private struct MetaBadge: View {
    let label: String
    let icon: String
    let palette: QuailThemePalette

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: icon).font(.system(size: 9))
            Text(label).font(.system(size: 11, design: .rounded))
        }
        .foregroundStyle(.secondary)
        .padding(.horizontal, 8).padding(.vertical, 4)
        .background(palette.elevatedSurface, in: Capsule())
        .overlay(Capsule().stroke(palette.border, lineWidth: 1))
    }
}

private struct MetricCell: View {
    let label: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.system(size: 10, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 13, weight: .semibold, design: .rounded))
        }
    }
}

// MARK: - Formatting helpers

private func formatBytes(_ bytes: Double) -> String {
    if bytes <= 0 { return "0 B" }
    if bytes < 1024 { return "\(Int(bytes)) B" }
    let kb = bytes / 1024
    if kb < 1024 { return String(format: "%.1f KB", kb) }
    let mb = kb / 1024
    if mb < 1024 { return String(format: "%.1f MB", mb) }
    return String(format: "%.2f GB", mb / 1024)
}

private func formatSeconds(_ s: Double) -> String {
    if s < 60 { return String(format: "%.0fs", s) }
    if s < 3600 { return String(format: "%.1f min", s / 60) }
    return String(format: "%.1f hr", s / 3600)
}

private func formatCu(_ cu: Double) -> String {
    cu == cu.rounded() ? String(Int(cu)) : String(format: "%.2g", cu)
}

private func shortDate(_ iso: String) -> String {
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let d = f.date(from: iso) {
        let rel = RelativeDateTimeFormatter()
        rel.unitsStyle = .abbreviated
        return rel.localizedString(for: d, relativeTo: Date())
    }
    return String(iso.prefix(10))
}
