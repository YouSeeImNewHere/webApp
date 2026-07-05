package com.quail.android.ui.screens.vehicle

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.Checkbox
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.CorrectiveRecord
import com.quail.android.data.model.DEFAULT_MAINTENANCE_TYPES
import com.quail.android.data.model.MaintenanceProcedure
import com.quail.android.data.model.ProcedureStep
import com.quail.android.data.model.TirePressureCheck
import com.quail.android.data.model.TireSet
import com.quail.android.data.model.VehicleProfileUpdateRequest
import com.quail.android.ui.overlay.AppOverlayHost
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset

private fun LocalDate.toUtcMillis(): Long = atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli()
private fun Long.toLocalDateUtc(): LocalDate = Instant.ofEpochMilli(this).atZone(ZoneOffset.UTC).toLocalDate()

@Composable
fun VehicleSheetHost(sheet: VehicleSheet, viewModel: VehicleViewModel, uiState: VehicleUiState, onDismiss: () -> Unit) {
    val data = (uiState as? VehicleUiState.Success)?.data ?: return
    val content: @Composable () -> Unit = {
        when (sheet) {
            is VehicleSheet.EditProfile -> EditProfileSheet(data, viewModel, onDismiss)
            is VehicleSheet.RecordMaintenance -> RecordMaintenanceSheet(sheet.typeName, data, viewModel, onDismiss)
            is VehicleSheet.RecordFuel -> RecordFuelSheet(data, viewModel, onDismiss)
            is VehicleSheet.AddIssue -> AddIssueSheet(data, viewModel, onDismiss)
            is VehicleSheet.AddCorrective -> AddCorrectiveSheet(sheet.issueId, data, viewModel, onDismiss)
            is VehicleSheet.AddTireSet -> AddTireSetSheet(viewModel, onDismiss)
            is VehicleSheet.TirePressureCheck -> TirePressureCheckSheet(data, viewModel, onDismiss)
            is VehicleSheet.EditProcedure -> EditProcedureSheet(sheet.existing, viewModel, onDismiss)
        }
    }
    SideEffect { AppOverlayHost.showBottomSheet(onDismissed = onDismiss, content = content) }
    DisposableEffect(Unit) { onDispose { AppOverlayHost.dismiss() } }
}

@Composable
private fun SheetScaffold(title: String, onDismiss: () -> Unit, content: @Composable () -> Unit) {
    Column(
        Modifier.verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 24.dp),
    ) {
        Row(Modifier.fillMaxWidth().padding(bottom = 12.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
            IconButton(onClick = onDismiss) { Icon(Icons.Filled.Close, contentDescription = "Close") }
        }
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { content() }
    }
}

@Composable
private fun LabeledField(label: String, value: String, numeric: Boolean = false, onValueChange: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = { new -> onValueChange(if (numeric) new.filter { it.isDigit() || it == '.' } else new) },
        label = { Text(label) },
        singleLine = true,
        modifier = Modifier.fillMaxWidth(),
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DateField(label: String, date: LocalDate, onChange: (LocalDate) -> Unit) {
    var showPicker by remember { mutableStateOf(false) }
    Surface(onClick = { showPicker = true }, color = QuailSurfaceRaised, shape = RoundedCornerShape(12.dp), modifier = Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().padding(14.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(label, color = QuailTextDim)
            Text(date.toString(), fontWeight = FontWeight.SemiBold)
        }
    }
    if (showPicker) {
        val pickerState = rememberDatePickerState(initialSelectedDateMillis = date.toUtcMillis())
        DatePickerDialog(
            onDismissRequest = { showPicker = false },
            confirmButton = {
                TextButton(onClick = {
                    pickerState.selectedDateMillis?.let { onChange(it.toLocalDateUtc()) }
                    showPicker = false
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { showPicker = false }) { Text("Cancel") } },
        ) { DatePicker(state = pickerState) }
    }
}

@Composable
private fun SaveButton(label: String, enabled: Boolean, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        color = if (enabled) MaterialTheme.colorScheme.primary else QuailSurfaceRaised,
        shape = RoundedCornerShape(14.dp),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column {
            Text(
                label,
                fontWeight = FontWeight.Bold,
                color = if (enabled) Color.Black else QuailTextDim,
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(vertical = 14.dp),
            )
        }
    }
}

// ---- Edit profile ----

@Composable
private fun EditProfileSheet(data: VehicleData, viewModel: VehicleViewModel, onDismiss: () -> Unit) {
    val p = data.profile
    var make by remember { mutableStateOf(p.make) }
    var model by remember { mutableStateOf(p.model) }
    var year by remember { mutableStateOf(p.year?.toString() ?: "") }
    var vin by remember { mutableStateOf(p.vin) }
    var plate by remember { mutableStateOf(p.licensePlate) }
    var mileage by remember { mutableStateOf(p.currentMileage.toString()) }
    var tankCapacity by remember { mutableStateOf(p.tankCapacityGallons?.toString() ?: "") }
    var oilType by remember { mutableStateOf(p.oilType) }
    var oilCapacityWithFilter by remember { mutableStateOf(p.oilCapacityWithFilter?.toString() ?: "") }
    var oilCapacityWithoutFilter by remember { mutableStateOf(p.oilCapacityWithoutFilter?.toString() ?: "") }
    var transmissionFluidType by remember { mutableStateOf(p.transmissionFluidType) }
    var transmissionFluidCapacity by remember { mutableStateOf(p.transmissionFluidCapacity?.toString() ?: "") }
    var coolantType by remember { mutableStateOf(p.coolantType) }
    var notes by remember { mutableStateOf(p.notes) }

    SheetScaffold("Vehicle Profile", onDismiss) {
        LabeledField("Make", make) { make = it }
        LabeledField("Model", model) { model = it }
        LabeledField("Year", year, numeric = true) { year = it }
        LabeledField("VIN", vin) { vin = it }
        LabeledField("License Plate", plate) { plate = it }
        LabeledField("Current Mileage", mileage, numeric = true) { mileage = it }
        LabeledField("Tank Capacity (gal)", tankCapacity, numeric = true) { tankCapacity = it }
        LabeledField("Oil Type (e.g. 5W-30)", oilType) { oilType = it }
        LabeledField("Oil Capacity w/ Filter (qt)", oilCapacityWithFilter, numeric = true) { oilCapacityWithFilter = it }
        LabeledField("Oil Capacity w/o Filter (qt)", oilCapacityWithoutFilter, numeric = true) { oilCapacityWithoutFilter = it }
        LabeledField("Transmission Fluid Type", transmissionFluidType) { transmissionFluidType = it }
        LabeledField("Transmission Fluid Capacity (qt)", transmissionFluidCapacity, numeric = true) { transmissionFluidCapacity = it }
        LabeledField("Coolant Type", coolantType) { coolantType = it }
        LabeledField("Notes (optional)", notes) { notes = it }

        SaveButton("Save", enabled = true) {
            viewModel.saveProfile(
                VehicleProfileUpdateRequest(
                    make = make,
                    model = model,
                    year = year.toIntOrNull(),
                    vin = vin,
                    licensePlate = plate,
                    oilType = oilType,
                    oilCapacityWithFilter = oilCapacityWithFilter.toDoubleOrNull(),
                    oilCapacityWithoutFilter = oilCapacityWithoutFilter.toDoubleOrNull(),
                    transmissionFluidType = transmissionFluidType,
                    transmissionFluidCapacity = transmissionFluidCapacity.toDoubleOrNull(),
                    coolantType = coolantType,
                    currentMileage = mileage.toIntOrNull() ?: 0,
                    tankCapacityGallons = tankCapacity.toDoubleOrNull(),
                    notes = notes,
                ),
            )
            onDismiss()
        }
    }
}

// ---- Record maintenance ----

@Composable
private fun RecordMaintenanceSheet(preselectedType: String?, data: VehicleData, viewModel: VehicleViewModel, onDismiss: () -> Unit) {
    var selectedType by remember { mutableStateOf(preselectedType) }
    var showPicker by remember { mutableStateOf(false) }
    var date by remember { mutableStateOf(LocalDate.now()) }
    var mileage by remember { mutableStateOf(if (data.profile.currentMileage > 0) data.profile.currentMileage.toString() else "") }
    var cost by remember { mutableStateOf("") }
    var isShop by remember { mutableStateOf(false) }
    var shopName by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }

    SheetScaffold("Record Maintenance", onDismiss) {
        Column {
            Text("Service Type", color = QuailTextDim, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(bottom = 6.dp))
            Surface(onClick = { showPicker = !showPicker }, color = QuailSurfaceRaised, shape = RoundedCornerShape(10.dp), modifier = Modifier.fillMaxWidth()) {
                Text(selectedType ?: "Select service type...", modifier = Modifier.padding(12.dp))
            }
            if (showPicker) {
                Column(Modifier.fillMaxWidth()) {
                    DEFAULT_MAINTENANCE_TYPES.forEach { type ->
                        Surface(
                            onClick = { selectedType = type.name; showPicker = false },
                            color = if (selectedType == type.name) QuailSurfaceRaised else Color.Transparent,
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text(type.name, modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp))
                        }
                    }
                }
            }
        }

        DateField("Date", date) { date = it }
        LabeledField("Mileage", mileage, numeric = true) { mileage = it }
        LabeledField("Cost (optional)", cost, numeric = true) { cost = it }

        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(checked = isShop, onCheckedChange = { isShop = it })
            Text("Shop Performed")
        }
        if (isShop) LabeledField("Shop Name", shopName) { shopName = it }
        LabeledField("Notes (optional)", notes) { notes = it }

        val canSave = selectedType != null && mileage.isNotBlank()
        SaveButton("Save Record", enabled = canSave) {
            val mi = mileage.toIntOrNull()
            if (selectedType != null && mi != null) {
                viewModel.addMaintenanceRecord(selectedType!!, date.toString(), mi, cost.toDoubleOrNull(), isShop, shopName, notes)
                onDismiss()
            }
        }
    }
}

// ---- Record fuel ----

@Composable
private fun RecordFuelSheet(data: VehicleData, viewModel: VehicleViewModel, onDismiss: () -> Unit) {
    var date by remember { mutableStateOf(LocalDate.now()) }
    var mileage by remember { mutableStateOf(if (data.profile.currentMileage > 0) data.profile.currentMileage.toString() else "") }
    var gallons by remember { mutableStateOf("") }
    var price by remember { mutableStateOf("") }
    var station by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }

    SheetScaffold("Log Fill-Up", onDismiss) {
        DateField("Date", date) { date = it }
        LabeledField("Current Mileage", mileage, numeric = true) { mileage = it }
        LabeledField("Gallons Pumped", gallons, numeric = true) { gallons = it }
        LabeledField("Price per Gallon (optional)", price, numeric = true) { price = it }
        LabeledField("Station Name (optional)", station) { station = it }
        LabeledField("Notes (optional)", notes) { notes = it }

        val canSave = mileage.isNotBlank() && gallons.isNotBlank()
        SaveButton("Save Fill-Up", enabled = canSave) {
            val mi = mileage.toIntOrNull()
            val gal = gallons.toDoubleOrNull()
            if (mi != null && gal != null && gal > 0) {
                viewModel.addFuelRecord(date.toString(), mi, gal, price.toDoubleOrNull(), station, notes)
                onDismiss()
            }
        }
    }
}

// ---- Add issue ----

@Composable
private fun AddIssueSheet(data: VehicleData, viewModel: VehicleViewModel, onDismiss: () -> Unit) {
    var title by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var howOccurred by remember { mutableStateOf("") }
    var date by remember { mutableStateOf(LocalDate.now()) }
    var mileage by remember { mutableStateOf(if (data.profile.currentMileage > 0) data.profile.currentMileage.toString() else "") }

    SheetScaffold("Report Issue", onDismiss) {
        LabeledField("Title (required)", title) { title = it }
        DateField("Date Noticed", date) { date = it }
        LabeledField("Mileage When Noticed", mileage, numeric = true) { mileage = it }
        LabeledField("Description", description) { description = it }
        LabeledField("How / When It Occurred (optional)", howOccurred) { howOccurred = it }

        SaveButton("Report Issue", enabled = title.isNotBlank()) {
            if (title.isNotBlank()) {
                viewModel.addIssue(title, description, date.toString(), mileage.toIntOrNull() ?: data.profile.currentMileage, howOccurred)
                onDismiss()
            }
        }
    }
}

// ---- Add corrective ----

@Composable
private fun AddCorrectiveSheet(linkedIssueId: Int?, data: VehicleData, viewModel: VehicleViewModel, onDismiss: () -> Unit) {
    var description by remember { mutableStateOf("") }
    var reason by remember { mutableStateOf("") }
    var date by remember { mutableStateOf(LocalDate.now()) }
    var mileage by remember { mutableStateOf(if (data.profile.currentMileage > 0) data.profile.currentMileage.toString() else "") }
    var parts by remember { mutableStateOf(listOf<String>()) }
    var newPart by remember { mutableStateOf("") }
    var cost by remember { mutableStateOf("") }
    var resolvedIssue by remember { mutableStateOf(linkedIssueId != null) }
    var selectedIssueId by remember { mutableStateOf(linkedIssueId) }
    var notes by remember { mutableStateOf("") }

    SheetScaffold("Record Repair", onDismiss) {
        LabeledField("Description (required)", description) { description = it }
        LabeledField("Reason / Root Cause", reason) { reason = it }
        DateField("Date", date) { date = it }
        LabeledField("Mileage", mileage, numeric = true) { mileage = it }
        LabeledField("Cost (optional)", cost, numeric = true) { cost = it }

        Column {
            Text("Parts Replaced", color = QuailTextDim, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(bottom = 6.dp))
            parts.forEach { part ->
                Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(part)
                    Surface(onClick = { parts = parts - part }, color = Color.Transparent) {
                        Text("Remove", color = MaterialTheme.colorScheme.primary, modifier = Modifier.padding(start = 8.dp))
                    }
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(value = newPart, onValueChange = { newPart = it }, label = { Text("Add part...") }, modifier = Modifier.weight(1f), singleLine = true)
                Surface(
                    onClick = { if (newPart.isNotBlank()) { parts = parts + newPart.trim(); newPart = "" } },
                    color = QuailSurfaceRaised,
                    shape = RoundedCornerShape(10.dp),
                    modifier = Modifier.padding(start = 8.dp),
                ) { Text("Add", modifier = Modifier.padding(horizontal = 14.dp, vertical = 14.dp)) }
            }
        }

        if (data.openIssues.isNotEmpty()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = resolvedIssue, onCheckedChange = { resolvedIssue = it })
                Text("Resolves an Open Issue")
            }
            if (resolvedIssue) {
                Column {
                    data.openIssues.forEach { issue ->
                        Surface(
                            onClick = { selectedIssueId = issue.id },
                            color = if (selectedIssueId == issue.id) QuailSurfaceRaised else Color.Transparent,
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text(issue.title.ifBlank { "Untitled Issue" }, modifier = Modifier.padding(10.dp))
                        }
                    }
                }
            }
        }

        LabeledField("Notes (optional)", notes) { notes = it }

        SaveButton("Save Repair", enabled = description.isNotBlank()) {
            if (description.isNotBlank()) {
                viewModel.addCorrectiveRecord(
                    CorrectiveRecord(
                        id = VehicleViewModel.newId(),
                        date = date.toString(),
                        mileage = mileage.toIntOrNull() ?: data.profile.currentMileage,
                        description = description,
                        reason = reason,
                        partsReplaced = parts,
                        cost = cost.toDoubleOrNull(),
                        resolvedIssue = resolvedIssue,
                        linkedIssueId = if (resolvedIssue) selectedIssueId else null,
                        notes = notes,
                    ),
                )
                onDismiss()
            }
        }
    }
}

// ---- Add tire set ----

@Composable
private fun AddTireSetSheet(viewModel: VehicleViewModel, onDismiss: () -> Unit) {
    var brand by remember { mutableStateOf("") }
    var model by remember { mutableStateOf("") }
    var size by remember { mutableStateOf("") }
    var installDate by remember { mutableStateOf(LocalDate.now()) }
    var installMileage by remember { mutableStateOf("") }
    var frontPressure by remember { mutableStateOf(35) }
    var rearPressure by remember { mutableStateOf(35) }
    var isActive by remember { mutableStateOf(true) }

    SheetScaffold("Add Tire Set", onDismiss) {
        LabeledField("Brand (e.g. Michelin)", brand) { brand = it }
        LabeledField("Model (e.g. Pilot Sport 4)", model) { model = it }
        LabeledField("Size (e.g. 225/45R17)", size) { size = it }
        DateField("Install Date", installDate) { installDate = it }
        LabeledField("Install Mileage", installMileage, numeric = true) { installMileage = it }

        PressureStepper("Front Pressure", frontPressure) { frontPressure = it }
        PressureStepper("Rear Pressure", rearPressure) { rearPressure = it }

        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(checked = isActive, onCheckedChange = { isActive = it })
            Text("Set as Active Tires")
        }

        SaveButton("Save Tire Set", enabled = true) {
            viewModel.addTireSet(
                TireSet(
                    id = VehicleViewModel.newId(),
                    brand = brand,
                    model = model,
                    size = size,
                    installDate = installDate.toString(),
                    installMileage = installMileage.toIntOrNull() ?: 0,
                    requiredPressureFront = frontPressure,
                    requiredPressureRear = rearPressure,
                    isActive = isActive,
                ),
            )
            onDismiss()
        }
    }
}

@Composable
private fun PressureStepper(label: String, value: Int, onChange: (Int) -> Unit) {
    Column {
        Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
        Row(Modifier.fillMaxWidth().padding(top = 4.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Surface(onClick = { onChange(maxOf(20, value - 1)) }, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
                Text("−", modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp), fontWeight = FontWeight.Bold)
            }
            Text("$value PSI", fontWeight = FontWeight.Bold)
            Surface(onClick = { onChange(minOf(60, value + 1)) }, color = QuailSurfaceRaised, shape = RoundedCornerShape(999.dp)) {
                Text("+", modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp), fontWeight = FontWeight.Bold)
            }
        }
    }
}

// ---- Tire pressure check ----

@Composable
private fun TirePressureCheckSheet(data: VehicleData, viewModel: VehicleViewModel, onDismiss: () -> Unit) {
    val tires = data.activeTireSet
    var date by remember { mutableStateOf(LocalDate.now()) }
    var mileage by remember { mutableStateOf(if (data.profile.currentMileage > 0) data.profile.currentMileage.toString() else "") }
    var fl by remember { mutableStateOf(tires?.requiredPressureFront ?: 35) }
    var fr by remember { mutableStateOf(tires?.requiredPressureFront ?: 35) }
    var rl by remember { mutableStateOf(tires?.requiredPressureRear ?: 35) }
    var rr by remember { mutableStateOf(tires?.requiredPressureRear ?: 35) }
    var notes by remember { mutableStateOf("") }

    SheetScaffold("Pressure Check", onDismiss) {
        DateField("Date", date) { date = it }
        LabeledField("Mileage", mileage, numeric = true) { mileage = it }
        PressureStepper("Front Left", fl) { fl = it }
        PressureStepper("Front Right", fr) { fr = it }
        PressureStepper("Rear Left", rl) { rl = it }
        PressureStepper("Rear Right", rr) { rr = it }
        LabeledField("Notes (optional)", notes) { notes = it }

        SaveButton("Save Check", enabled = tires != null) {
            if (tires != null) {
                viewModel.addPressureCheck(
                    tires.id,
                    TirePressureCheck(
                        id = VehicleViewModel.newId(),
                        date = date.toString(),
                        mileage = mileage.toIntOrNull() ?: data.profile.currentMileage,
                        frontLeft = fl,
                        frontRight = fr,
                        rearLeft = rl,
                        rearRight = rr,
                        notes = notes,
                    ),
                )
                onDismiss()
            }
        }
    }
}

// ---- Edit procedure ----

@Composable
private fun EditProcedureSheet(existing: MaintenanceProcedure?, viewModel: VehicleViewModel, onDismiss: () -> Unit) {
    var title by remember { mutableStateOf(existing?.title ?: "") }
    var relatedType by remember { mutableStateOf(existing?.relatedTypeName ?: "") }
    var steps by remember { mutableStateOf(existing?.steps ?: emptyList()) }
    var tools by remember { mutableStateOf(existing?.tools ?: emptyList()) }
    var parts by remember { mutableStateOf(existing?.parts ?: emptyList()) }
    var notes by remember { mutableStateOf(existing?.notes ?: "") }
    var newStep by remember { mutableStateOf("") }
    var newTool by remember { mutableStateOf("") }
    var newPart by remember { mutableStateOf("") }

    SheetScaffold(if (existing == null) "New Procedure" else "Edit Procedure", onDismiss) {
        LabeledField("Title (required)", title) { title = it }
        LabeledField("Related Service (optional)", relatedType) { relatedType = it }

        DynamicList("Tools", tools, newTool, { newTool = it }, onAdd = { tools = tools + it }, onRemove = { tools = tools - it })
        DynamicList("Parts", parts, newPart, { newPart = it }, onAdd = { parts = parts + it }, onRemove = { parts = parts - it })

        Column {
            Text("Steps", color = QuailTextDim, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(bottom = 6.dp))
            steps.forEachIndexed { idx, step ->
                Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("${idx + 1}.", fontWeight = FontWeight.Bold, modifier = Modifier.padding(end = 8.dp))
                    OutlinedTextField(
                        value = step.text,
                        onValueChange = { new -> steps = steps.toMutableList().also { it[idx] = it[idx].copy(text = new) } },
                        modifier = Modifier.weight(1f),
                        singleLine = true,
                    )
                    Surface(onClick = { steps = steps.toMutableList().also { it.removeAt(idx) } }, color = Color.Transparent) {
                        Text("✕", modifier = Modifier.padding(8.dp))
                    }
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(value = newStep, onValueChange = { newStep = it }, label = { Text("Add step...") }, modifier = Modifier.weight(1f), singleLine = true)
                Surface(
                    onClick = { if (newStep.isNotBlank()) { steps = steps + ProcedureStep(VehicleViewModel.newId(), newStep.trim()); newStep = "" } },
                    color = QuailSurfaceRaised,
                    shape = RoundedCornerShape(10.dp),
                    modifier = Modifier.padding(start = 8.dp),
                ) { Text("Add", modifier = Modifier.padding(horizontal = 14.dp, vertical = 14.dp)) }
            }
        }

        LabeledField("Notes", notes) { notes = it }

        SaveButton(if (existing == null) "Create Procedure" else "Save Changes", enabled = title.isNotBlank()) {
            if (title.isNotBlank()) {
                viewModel.saveProcedure(
                    MaintenanceProcedure(
                        id = existing?.id ?: VehicleViewModel.newId(),
                        title = title,
                        relatedTypeName = relatedType,
                        tools = tools,
                        parts = parts,
                        steps = steps,
                        notes = notes,
                        lastUpdated = LocalDate.now().toString(),
                    ),
                )
                onDismiss()
            }
        }
    }
}

@Composable
private fun DynamicList(
    label: String,
    items: List<String>,
    newItem: String,
    onNewItemChange: (String) -> Unit,
    onAdd: (String) -> Unit,
    onRemove: (String) -> Unit,
) {
    Column {
        Text(label, color = QuailTextDim, style = MaterialTheme.typography.labelMedium, modifier = Modifier.padding(bottom = 6.dp))
        items.forEach { item ->
            Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("• $item")
                Surface(onClick = { onRemove(item) }, color = Color.Transparent) { Text("✕", modifier = Modifier.padding(horizontal = 8.dp)) }
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(value = newItem, onValueChange = onNewItemChange, modifier = Modifier.weight(1f), singleLine = true)
            Surface(
                onClick = { if (newItem.isNotBlank()) { onAdd(newItem.trim()); onNewItemChange("") } },
                color = QuailSurfaceRaised,
                shape = RoundedCornerShape(10.dp),
                modifier = Modifier.padding(start = 8.dp),
            ) { Text("Add", modifier = Modifier.padding(horizontal = 14.dp, vertical = 14.dp)) }
        }
    }
}
