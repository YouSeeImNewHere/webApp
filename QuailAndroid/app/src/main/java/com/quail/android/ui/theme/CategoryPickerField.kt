package com.quail.android.ui.theme

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier

/** Category reassignment field: typing filters the tenant's existing
 * categories into a suggestion dropdown, or the arrow button lists all of
 * them — but since categories are free-form (see
 * HomeRepository.getCategories()), typing a brand-new one is still allowed. */
@Composable
fun CategoryPickerField(
    value: String,
    onValueChange: (String) -> Unit,
    categories: List<String>,
    modifier: Modifier = Modifier,
    label: String? = null,
) {
    var expanded by remember { mutableStateOf(false) }
    val filtered = remember(value, categories) {
        if (value.isBlank()) categories else categories.filter { it.contains(value, ignoreCase = true) }
    }
    Box(modifier = modifier) {
        OutlinedTextField(
            value = value,
            onValueChange = {
                onValueChange(it)
                expanded = categories.isNotEmpty()
            },
            label = label?.let { { Text(it) } },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
            trailingIcon = {
                IconButton(onClick = { expanded = !expanded }) {
                    Icon(Icons.Filled.ArrowDropDown, contentDescription = "Choose category")
                }
            },
        )
        DropdownMenu(expanded = expanded && filtered.isNotEmpty(), onDismissRequest = { expanded = false }) {
            filtered.forEach { category ->
                DropdownMenuItem(
                    text = { Text(category) },
                    onClick = {
                        onValueChange(category)
                        expanded = false
                    },
                )
            }
        }
    }
}
