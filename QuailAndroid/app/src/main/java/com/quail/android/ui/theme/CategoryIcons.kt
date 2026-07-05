package com.quail.android.ui.theme

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Autorenew
import androidx.compose.material.icons.filled.AttachMoney
import androidx.compose.material.icons.filled.CardGiftcard
import androidx.compose.material.icons.filled.DirectionsCar
import androidx.compose.material.icons.filled.Flight
import androidx.compose.material.icons.filled.HelpOutline
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.LocalHospital
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.Pets
import androidx.compose.material.icons.filled.Receipt
import androidx.compose.material.icons.filled.Restaurant
import androidx.compose.material.icons.filled.School
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material.icons.filled.ShoppingBag
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material.icons.filled.SwapHoriz
import androidx.compose.ui.graphics.vector.ImageVector

/** Transaction categories are free-form tenant-defined strings (see
 * HomeRepository.getCategories()), not a fixed enum — so this matches on
 * keyword substrings rather than an exact lookup table. Falls back to a
 * generic receipt icon for anything unrecognized. */
fun categoryIcon(category: String?): ImageVector {
    val c = category?.trim()?.lowercase().orEmpty()
    if (c.isEmpty()) return Icons.Filled.Receipt
    return when {
        listOf("grocery", "groceries", "supermarket").any { c.contains(it) } -> Icons.Filled.ShoppingCart
        listOf("restaurant", "dining", "food", "coffee", "cafe", "bar").any { c.contains(it) } -> Icons.Filled.Restaurant
        listOf("gas", "fuel", "auto", "car", "transport", "uber", "lyft", "parking", "transit").any { c.contains(it) } -> Icons.Filled.DirectionsCar
        listOf("travel", "flight", "airline", "hotel", "vacation").any { c.contains(it) } -> Icons.Filled.Flight
        listOf("entertainment", "movie", "streaming", "music", "game", "subscription", "membership").any { c.contains(it) } ->
            if (c.contains("subscription") || c.contains("membership")) Icons.Filled.Autorenew else Icons.Filled.Movie
        listOf("health", "medical", "doctor", "pharmacy", "fitness", "gym").any { c.contains(it) } -> Icons.Filled.LocalHospital
        listOf("shopping", "clothing", "retail", "amazon").any { c.contains(it) } -> Icons.Filled.ShoppingBag
        listOf("rent", "mortgage", "home", "housing").any { c.contains(it) } -> Icons.Filled.Home
        listOf("income", "paycheck", "salary", "deposit").any { c.contains(it) } -> Icons.Filled.AttachMoney
        listOf("transfer", "payment").any { c.contains(it) } -> Icons.Filled.SwapHoriz
        listOf("education", "school", "tuition", "book").any { c.contains(it) } -> Icons.Filled.School
        listOf("insurance").any { c.contains(it) } -> Icons.Filled.Shield
        listOf("pet").any { c.contains(it) } -> Icons.Filled.Pets
        listOf("gift", "donation", "charity").any { c.contains(it) } -> Icons.Filled.CardGiftcard
        listOf("unassigned", "uncategorized").any { c.contains(it) } -> Icons.Filled.HelpOutline
        listOf("utilities", "electric", "water", "internet", "phone", "bill").any { c.contains(it) } -> Icons.Filled.Receipt
        else -> Icons.Filled.Receipt
    }
}
