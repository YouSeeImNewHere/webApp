package com.quail.android.ui.theme

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.quail.android.data.model.FinancingPlanResponse
import java.text.NumberFormat
import java.util.Locale

private val financingCurrency: NumberFormat = NumberFormat.getCurrencyInstance(Locale.US)

/** Shared between HomeScreen's "Monthly Spending" card and BudgetScreen —
 * both need to show the same "what's financed and what it's costing me
 * this month" list. Reused as-is rather than duplicated per screen. */
@Composable
fun FinancingPlansList(plans: List<FinancingPlanResponse>, onDelete: (FinancingPlanResponse) -> Unit) {
    if (plans.isEmpty()) return
    val totalMonthly = plans.filter { !it.isComplete }.sumOf { it.monthlyPayment }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Financing", fontWeight = FontWeight.SemiBold)
            Text("${financingCurrency.format(totalMonthly)}/mo", color = QuailTextDim, style = MaterialTheme.typography.labelSmall)
        }
        plans.forEach { plan -> FinancingPlanRow(plan, onDelete) }
    }
}

@Composable
private fun FinancingPlanRow(plan: FinancingPlanResponse, onDelete: (FinancingPlanResponse) -> Unit) {
    val progress = if (plan.totalAmount > 0) (plan.amountPaid / plan.totalAmount).coerceIn(0.0, 1.0) else 0.0
    Surface(color = QuailSurfaceRaised, shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column {
                    Text(plan.label, fontWeight = FontWeight.Bold)
                    Text(
                        if (plan.isComplete) "Paid off" else "${plan.monthsRemaining} months left • ${financingCurrency.format(plan.monthlyPayment)}/mo",
                        color = QuailTextDim,
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
                Text(
                    "${financingCurrency.format(plan.amountPaid)} / ${financingCurrency.format(plan.totalAmount)}",
                    color = if (plan.isComplete) QuailGoodGreen else QuailTextDim,
                    fontWeight = FontWeight.SemiBold,
                    style = MaterialTheme.typography.labelSmall,
                )
            }
            Box(
                Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp)
                    .height(6.dp)
                    .background(QuailSurface, RoundedCornerShape(4.dp)),
            ) {
                Box(
                    Modifier
                        .fillMaxWidth(fraction = progress.toFloat().coerceIn(0f, 1f))
                        .height(6.dp)
                        .background(if (plan.isComplete) QuailGoodGreen else MaterialTheme.colorScheme.primary, RoundedCornerShape(4.dp)),
                )
            }
            Row(Modifier.padding(top = 8.dp)) {
                Surface(onClick = { onDelete(plan) }, color = QuailSurface, shape = RoundedCornerShape(10.dp)) {
                    Text(
                        "Delete",
                        modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp),
                        fontWeight = FontWeight.SemiBold,
                        color = QuailBadRed,
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
            }
        }
    }
}
