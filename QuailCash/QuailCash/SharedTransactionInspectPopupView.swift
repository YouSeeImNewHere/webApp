import SwiftUI

private struct SharedTransactionPrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        let palette = QuailTheme.palette(for: UserDefaults.standard.string(forKey: "quail.settings.theme") ?? "system")
        configuration.label
            .foregroundStyle(palette.primaryButtonText)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(palette.primaryButton.opacity(configuration.isPressed ? 0.78 : 1.0))
            )
    }
}

private struct SharedTransactionSecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        let palette = QuailTheme.palette(for: UserDefaults.standard.string(forKey: "quail.settings.theme") ?? "system")
        configuration.label
            .foregroundStyle(palette.secondaryButtonText)
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(palette.secondaryButton.opacity(configuration.isPressed ? 0.88 : 1.0))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .stroke(palette.border, lineWidth: 1)
            )
    }
}

private struct SharedTransactionHeaderActionStyle: ButtonStyle {
    let primary: Bool

    func makeBody(configuration: Configuration) -> some View {
        let palette = QuailTheme.palette(for: UserDefaults.standard.string(forKey: "quail.settings.theme") ?? "system")
        configuration.label
            .font(.system(size: 11, weight: .semibold, design: .rounded))
            .foregroundStyle(primary ? palette.primaryButtonText : palette.secondaryButtonText)
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(primary ? palette.primaryButton.opacity(configuration.isPressed ? 0.78 : 1.0) : palette.secondaryButton.opacity(configuration.isPressed ? 0.88 : 1.0))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(primary ? .clear : palette.border, lineWidth: 1)
            )
    }
}

private func sharedTransactionAmountColor(_ value: Double) -> Color {
    if value >= 0 { return .red }
    return .green
}

struct SharedTransactionInspectPopupView: View {
    @AppStorage("quail.settings.theme") private var themeSelection: String = "system"
    let transaction: TransactionItem
    let onDismiss: () -> Void
    let onRefresh: () -> Void

    @State private var detail: TransactionDetailPayload?
    @State private var categoryText = ""
    @State private var statusText = "posted"
    @State private var postedDateText = ""
    @State private var metaEditing = false
    @State private var saveStatus: String = ""
    @State private var actionStatus: String = ""
    @State private var showDeleteConfirm = false
    @State private var showInvertConfirm = false
    @State private var isSaving = false

    private var palette: QuailThemePalette { QuailTheme.palette(for: themeSelection) }

    var body: some View {
        ZStack(alignment: .top) {
            palette.surface
                .ignoresSafeArea()

            VStack(spacing: 0) {
                header
                ScrollView {
                    popupContent
                }
                .scrollIndicators(.hidden)
                .scrollContentBackground(.hidden)
                .scrollBounceBehavior(.basedOnSize)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
        .task { await load() }
        .confirmationDialog("Delete this transaction?", isPresented: $showDeleteConfirm, titleVisibility: .visible) {
            Button("Delete", role: .destructive) { Task { await deleteTransaction() } }
            Button("Cancel", role: .cancel) {}
        }
        .confirmationDialog("Invert this transaction amount?", isPresented: $showInvertConfirm, titleVisibility: .visible) {
            Button("Invert", role: .destructive) { Task { await invertAmount() } }
            Button("Cancel", role: .cancel) {}
        }
    }

    private var header: some View {
        VStack(spacing: 0) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(transactionTitle)
                        .font(.system(size: 18, weight: .bold, design: .rounded))
                        .lineLimit(2)
                    Text(subtitleText)
                        .font(.system(size: 12, weight: .medium, design: .rounded))
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                Spacer(minLength: 10)

                Button(action: close) {
                    Image(systemName: "xmark")
                        .font(.system(size: 12, weight: .bold))
                        .frame(width: 30, height: 30)
                        .background(palette.secondaryButton, in: Circle())
                        .overlay(Circle().stroke(palette.border, lineWidth: 1))
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            .padding(.top, 16)
            .padding(.bottom, 12)

            Rectangle()
                .fill(palette.border)
                .frame(height: 1)
        }
        .background(palette.surface)
    }

    @ViewBuilder
    private var popupContent: some View {
        VStack(alignment: .leading, spacing: 16) {
            txGrid
            categoryEditor
            technicalDetailsSection
            actionToolbar
            if metaEditing {
                metaEditor
            }
            if !saveStatus.isEmpty {
                Text(saveStatus)
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
            if !actionStatus.isEmpty {
                Text(actionStatus)
                    .font(.system(size: 11, weight: .medium, design: .rounded))
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
    }

    private var subtitleText: String {
        let amount = nativeMoneyValue(detail?.amount ?? transaction.amount)
        let bankCard = [detail?.bank ?? transaction.bank, detail?.card ?? transaction.card]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .joined(separator: "  ")
        let idText = "id \(detail?.id ?? transaction.id)"
        let parts = [amount, bankCard, idText].filter { !$0.isEmpty }
        return parts.joined(separator: "  •  ")
    }

    private var transactionTitle: String {
        let title = detail?.merchant.isEmpty == false ? detail!.merchant : transaction.merchant
        return title.isEmpty ? "Transaction" : title
    }

    private var txGrid: some View {
        VStack(alignment: .leading, spacing: 10) {
            txKV(label: "merchant", value: transactionTitle)
            txKV(label: "amount", value: nativeMoneyValue(detail?.amount ?? transaction.amount), valueColor: sharedTransactionAmountColor(detail?.amount ?? transaction.amount))
            txKV(label: "status", value: detail?.status ?? transaction.status ?? "posted")
            txKV(label: "time", value: detail?.postedDate ?? transaction.dateISO ?? transaction.date ?? "—")
            txKV(label: "purchase date", value: detail?.purchaseDate ?? "—")
            txKV(label: "posted date", value: detail?.postedDate ?? transaction.postedDate ?? transaction.dateISO ?? "—")
            txKV(label: "bank", value: detail?.bank ?? transaction.bank ?? "—")
            txKV(label: "card", value: detail?.card ?? transaction.card ?? "—")
            txKV(label: "account type", value: detail?.accountType ?? transaction.accountType ?? "—")
        }
        .padding(.vertical, 4)
    }

    private var categoryEditor: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("category")
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)

            HStack(spacing: 8) {
                TextField("Set category", text: $categoryText)
                    .font(.system(size: 13, weight: .medium, design: .rounded))
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .background(palette.elevatedSurface, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(palette.border, lineWidth: 1))

                Button("Save") { Task { await saveCategory() } }
                    .buttonStyle(SharedTransactionPrimaryButtonStyle())
            }
            .disabled(isSaving)
        }
    }

    private var technicalDetailsSection: some View {
        let rows = technicalFieldRows()
        return VStack(alignment: .leading, spacing: 8) {
            Text("details")
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)

            VStack(alignment: .leading, spacing: 6) {
                if rows.isEmpty {
                    Text("No additional fields.")
                        .font(.system(size: 12, weight: .regular, design: .rounded))
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(rows, id: \.key) { row in
                        txTechRow(label: row.key, value: row.value)
                    }
                }
            }
        }
    }

    private var actionToolbar: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Button(metaEditing ? "Close edit" : "Edit status/date") {
                    metaEditing.toggle()
                }
                .buttonStyle(SharedTransactionHeaderActionStyle(primary: false))

                Button("Invert amount") { showInvertConfirm = true }
                    .buttonStyle(SharedTransactionHeaderActionStyle(primary: false))

                Button((detail?.isIgnored ?? false) ? "Unignore" : "Ignore") {
                    Task { await toggleIgnore() }
                }
                .buttonStyle(SharedTransactionHeaderActionStyle(primary: false))

                Button("Delete") { showDeleteConfirm = true }
                    .buttonStyle(SharedTransactionHeaderActionStyle(primary: true))
            }
        }
    }

    private var metaEditor: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Status")
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundStyle(.secondary)
                    Picker("", selection: $statusText) {
                        Text("posted").tag("posted")
                        Text("pending").tag("pending")
                    }
                    .pickerStyle(.menu)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text("Posted date")
                        .font(.system(size: 12, weight: .semibold, design: .rounded))
                        .foregroundStyle(.secondary)
                    TextField("MM/DD/YYYY or unknown", text: $postedDateText)
                        .font(.system(size: 13, weight: .medium, design: .rounded))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)
                        .background(Color.white, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(.black.opacity(0.06), lineWidth: 1))
                }
            }
            HStack(spacing: 8) {
                Button("Save") { Task { await saveMeta() } }
                    .buttonStyle(SharedTransactionPrimaryButtonStyle())
                Button("Cancel") {
                    if let detail {
                        statusText = (detail.status ?? "posted").lowercased()
                        postedDateText = detail.postedDate ?? detail.purchaseDate ?? ""
                    }
                    metaEditing = false
                    saveStatus = ""
                }
                .buttonStyle(SharedTransactionSecondaryButtonStyle())
            }
        }
    }

    private func txKV(label: String, value: String, valueColor: Color = .primary) -> some View {
        HStack {
            Text(label)
                .font(.system(size: 12, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.system(size: 13, weight: .bold, design: .rounded))
                .foregroundStyle(valueColor)
        }
    }

    private func txDetailRow(label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.system(size: 11, weight: .bold, design: .rounded))
                .foregroundStyle(.primary)
        }
    }

    private func txTechRow(label: String, value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text("\(label):")
                .font(.system(size: 11, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 11, weight: .regular, design: .rounded))
                .foregroundStyle(.primary)
                .lineLimit(3)
        }
    }

    private func technicalFieldRows() -> [(key: String, value: String)] {
        let source: Any = detail ?? transaction
        let priority = ["id", "status", "posteddate", "purchasedate", "amount", "merchant", "bank", "card", "accounttype", "category", "source", "time", "transferpeer"]
        let summaryNorms = Set([
            "merchant", "amount", "status", "time",
            "purchasedate", "posteddate", "bank", "card", "accounttype", "category",
        ])

        func normalize(_ s: String) -> String {
            s.lowercased().replacingOccurrences(of: "[^a-z0-9]", with: "", options: .regularExpression)
        }

        func displayValue(_ value: Any) -> String {
            let mirror = Mirror(reflecting: value)
            if mirror.displayStyle == .optional {
                guard let child = mirror.children.first else { return "—" }
                return displayValue(child.value)
            }
            if let value = value as? String {
                return value.isEmpty ? "—" : value
            }
            return String(describing: value)
        }

        let mirror = Mirror(reflecting: source)
        var entries: [(key: String, value: String)] = []
        for child in mirror.children {
            guard let key = child.label else { continue }
            let norm = normalize(key)
            if summaryNorms.contains(norm) { continue }
            let raw = displayValue(child.value)
            if raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || raw == "—" { continue }
            let label = key
                .replacingOccurrences(of: "([a-z])([A-Z])", with: "$1 $2", options: .regularExpression)
                .replacingOccurrences(of: "_", with: " ")
                .lowercased()
            entries.append((key: label, value: raw))
        }
        entries.sort {
            let ai = priority.firstIndex(of: normalize($0.key)) ?? Int.max
            let bi = priority.firstIndex(of: normalize($1.key)) ?? Int.max
            if ai != bi { return ai < bi }
            return $0.key < $1.key
        }
        return entries
    }

    private func load() async {
        do {
            let next = try await QuailCashAPI.shared.fetchTransactionDetail(txId: transaction.id)
            await MainActor.run {
                detail = next
                categoryText = next.category ?? transaction.category ?? ""
                statusText = (next.status ?? transaction.status ?? "posted").lowercased()
                postedDateText = next.postedDate ?? next.purchaseDate ?? transaction.postedDate ?? transaction.dateISO ?? ""
                saveStatus = ""
                actionStatus = ""
            }
        } catch {
            await MainActor.run {
                categoryText = transaction.category ?? ""
                statusText = (transaction.status ?? "posted").lowercased()
                postedDateText = transaction.postedDate ?? transaction.dateISO ?? ""
                saveStatus = error.localizedDescription
            }
        }
    }

    private func saveCategory() async {
        isSaving = true
        defer { isSaving = false }
        do {
            _ = try await QuailCashAPI.shared.updateTransactionCategory(txId: transaction.id, category: categoryText)
            saveStatus = "Saved."
            onRefresh()
            await load()
        } catch {
            saveStatus = "Failed to save category."
        }
    }

    private func saveMeta() async {
        isSaving = true
        defer { isSaving = false }
        do {
            _ = try await QuailCashAPI.shared.updateTransactionMeta(txId: transaction.id, status: statusText, postedDate: postedDateText)
            saveStatus = "Saved."
            metaEditing = false
            onRefresh()
            await load()
        } catch {
            saveStatus = "Failed to save metadata."
        }
    }

    private func toggleIgnore() async {
        do {
            let next = !((detail?.isIgnored ?? false))
            _ = try await QuailCashAPI.shared.ignoreTransaction(txId: transaction.id, ignored: next)
            actionStatus = next ? "Ignored from calculations." : "Included in calculations."
            onRefresh()
            await load()
        } catch {
            actionStatus = "Failed to update ignore state."
        }
    }

    private func invertAmount() async {
        do {
            _ = try await QuailCashAPI.shared.invertTransactionAmount(txId: transaction.id)
            actionStatus = "Amount inverted."
            onRefresh()
            await load()
        } catch {
            actionStatus = "Failed to invert amount."
        }
    }

    private func deleteTransaction() async {
        do {
            _ = try await QuailCashAPI.shared.deleteTransaction(txId: transaction.id)
            actionStatus = "Deleted."
            onDismiss()
            onRefresh()
        } catch {
            actionStatus = "Failed to delete transaction."
        }
    }

    private func close() {
        onDismiss()
    }
}
