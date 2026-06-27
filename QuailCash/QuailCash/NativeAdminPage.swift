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
    let status: String?
    let serviceDetails: RenderServiceDetails?
    let updatedAt: String?
    let createdAt: String?
    let dashboardUrl: String?
}

struct RenderServiceDetails: Decodable {
    let env: String?
    let region: String?
    let plan: String?
    let numInstances: Int?
    let healthCheckPath: String?
}

struct NeonMetrics: Decodable {
    let error: String?
    let project: NeonProject?
    let branches: [NeonBranch]?
    let endpoints: [NeonEndpoint]?
}

struct NeonProject: Decodable {
    let id: String?
    let name: String?
    let region: String?
    let pgVersion: Int?
    let cpuUsedSec: Double?
    let dataStorageBytesHour: Double?
    let dataTransferBytes: Double?
    let createdAt: String?
    let updatedAt: String?
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
            onLeadingTap: { navigator.goBack() },
            onTrailingTap: { Task { await vm.load() } },
            onSelectTab: { _ in }
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
                        VStack(spacing: 20) {
                            if let m = vm.metrics {
                                RenderSection(render: m.render, palette: palette)
                                NeonSection(neon: m.neon, palette: palette)
                            }

                            if let refreshed = vm.lastRefreshed {
                                Text("Last updated \(refreshed.formatted(.relative(presentation: .named)))")
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
                VStack(spacing: 8) {
                    ForEach(services) { svc in
                        RenderServiceRow(service: svc, palette: palette)
                    }
                }
            } else {
                Text("No services found.")
                    .font(.system(size: 13, design: .rounded))
                    .foregroundStyle(.secondary)
            }
        }
    }
}

private struct RenderServiceRow: View {
    let service: RenderService
    let palette: QuailThemePalette

    private var isSuspended: Bool {
        service.status?.lowercased() == "suspended"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Circle()
                    .fill(isSuspended ? Color.orange : Color.green)
                    .frame(width: 8, height: 8)
                Text(service.name ?? "Unknown")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                Spacer()
                Text(service.type?.replacingOccurrences(of: "_", with: " ").capitalized ?? "")
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 8).padding(.vertical, 3)
                    .background(palette.elevatedSurface, in: Capsule())
            }

            HStack(spacing: 16) {
                if let region = service.serviceDetails?.region {
                    MetaBadge(label: region, icon: "location.fill")
                }
                if let plan = service.serviceDetails?.plan {
                    MetaBadge(label: plan, icon: "creditcard.fill")
                }
                if let instances = service.serviceDetails?.numInstances {
                    MetaBadge(label: "\(instances) instance\(instances == 1 ? "" : "s")", icon: "square.stack.fill")
                }
            }
        }
        .padding(12)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
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
                    VStack(alignment: .leading, spacing: 6) {
                        Text("COMPUTES")
                            .font(.system(size: 11, weight: .bold, design: .rounded))
                            .foregroundStyle(.secondary)
                        VStack(spacing: 8) {
                            ForEach(endpoints) { ep in
                                NeonEndpointRow(endpoint: ep, palette: palette)
                            }
                        }
                    }
                }
                if let branches = neon.branches, !branches.isEmpty {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("BRANCHES")
                            .font(.system(size: 11, weight: .bold, design: .rounded))
                            .foregroundStyle(.secondary)
                        VStack(spacing: 8) {
                            ForEach(branches) { branch in
                                NeonBranchRow(branch: branch, palette: palette)
                            }
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
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(project.name ?? "Unknown Project")
                    .font(.system(size: 14, weight: .semibold, design: .rounded))
                Spacer()
                if let pg = project.pgVersion {
                    Text("pg\(pg)")
                        .font(.system(size: 11, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 8).padding(.vertical, 3)
                        .background(palette.elevatedSurface, in: Capsule())
                }
            }

            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 8) {
                GridRow {
                    if let region = project.region {
                        MetricCell(label: "Region", value: region)
                    }
                    if let cpu = project.cpuUsedSec {
                        MetricCell(label: "CPU used", value: formatCpu(cpu))
                    }
                }
                GridRow {
                    if let storage = project.dataStorageBytesHour {
                        MetricCell(label: "Storage", value: formatBytes(storage))
                    }
                    if let transfer = project.dataTransferBytes {
                        MetricCell(label: "Transfer", value: formatBytes(transfer))
                    }
                }
            }
        }
        .padding(12)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
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
                if let minCu = endpoint.autoscalingLimitMinCu, let maxCu = endpoint.autoscalingLimitMaxCu {
                    Text("\(formatCu(minCu))–\(formatCu(maxCu)) CU")
                        .font(.system(size: 10, design: .rounded))
                        .foregroundStyle(.secondary)
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
            if let size = branch.logicalSize {
                Text(formatBytes(Double(size)))
                    .font(.system(size: 11, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            Text(branch.currentState ?? "")
                .font(.system(size: 11, weight: .medium, design: .rounded))
                .foregroundStyle(.secondary)
        }
        .padding(10)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(palette.border, lineWidth: 1))
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

private struct ErrorBanner: View {
    let message: String
    let palette: QuailThemePalette

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.circle.fill").foregroundStyle(.orange)
            Text(message)
                .font(.system(size: 12, design: .rounded))
                .foregroundStyle(.secondary)
        }
        .padding(10)
        .background(Color.orange.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.orange.opacity(0.2), lineWidth: 1))
    }
}

private struct MetaBadge: View {
    let label: String
    let icon: String

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: icon).font(.system(size: 9))
            Text(label).font(.system(size: 11, design: .rounded))
        }
        .foregroundStyle(.secondary)
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
    if bytes < 1024 { return "\(Int(bytes)) B" }
    let kb = bytes / 1024
    if kb < 1024 { return String(format: "%.1f KB", kb) }
    let mb = kb / 1024
    if mb < 1024 { return String(format: "%.1f MB", mb) }
    return String(format: "%.2f GB", mb / 1024)
}

private func formatCpu(_ seconds: Double) -> String {
    if seconds < 60 { return String(format: "%.1fs", seconds) }
    return String(format: "%.1f min", seconds / 60)
}

private func formatCu(_ cu: Double) -> String {
    cu == cu.rounded() ? String(Int(cu)) : String(format: "%.2g", cu)
}
