package com.quail.android.ui.overlay

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/** All screens use the same standard Material3 TopAppBar height (56dp content
 * + system status bar inset handled separately below). Popups used to render
 * in their own Android window (ModalBottomSheet/AlertDialog/Dialog all do
 * this) — meaning their scrim covered literally everything, including the
 * top bar and the bug-report button living in it. Routing popups through
 * this instead keeps them in the same window as the rest of the screen and
 * physically incapable of drawing over the top bar. */
private val TOP_BAR_CLEARANCE = 64.dp

/** Single global overlay slot. Only one popup can be "in front" at a time,
 * same as the native dialog/sheet APIs this replaces.
 *
 * [onDismissed] fires exactly once, whether the overlay was closed from
 * inside (a Cancel/close button calling the caller's own onDismiss) or from
 * outside (scrim tap, back press). Screens that mount a sheet/dialog based
 * on their own nullable state (e.g. `activeSheet?.let { SheetHost(...) }`)
 * pass their state-clearing lambda here so an outside dismissal stays in
 * sync with that state instead of leaving it stale. */
object AppOverlayHost {
    var content by mutableStateOf<(@Composable () -> Unit)?>(null)
        private set
    private var onDismissed: (() -> Unit)? = null

    val isShowing: Boolean get() = content != null

    fun show(onDismissed: (() -> Unit)? = null, content: @Composable () -> Unit) {
        this.onDismissed = onDismissed
        this.content = content
    }

    fun showBottomSheet(onDismissed: (() -> Unit)? = null, content: @Composable () -> Unit) {
        show(onDismissed) { AppBottomSheetOverlay(content) }
    }

    fun showDialog(onDismissed: (() -> Unit)? = null, content: @Composable () -> Unit) {
        show(onDismissed) { AppDialogOverlay(content) }
    }

    fun dismiss() {
        content = null
        val callback = onDismissed
        onDismissed = null
        callback?.invoke()
    }
}

/** Mounted once at the root of the app (see MainActivity's AppNav), above
 * the NavHost so it renders on top of whatever screen is showing but still
 * inside the same window — constrained to start below the top bar. */
@Composable
fun AppOverlayRoot() {
    val current = AppOverlayHost.content ?: return
    BackHandler(enabled = true) { AppOverlayHost.dismiss() }
    Box(
        modifier = Modifier
            .fillMaxSize()
            .statusBarsPadding()
            .padding(top = TOP_BAR_CLEARANCE)
            .background(Color.Black.copy(alpha = 0.55f))
            .pointerInput(Unit) { detectTapGestures(onTap = { AppOverlayHost.dismiss() }) },
    ) {
        current()
    }
}

/** Mirrors ModalBottomSheet's look/placement: anchored to the bottom of the
 * (top-bar-excluded) area, rounded top corners. Content supplies its own
 * scrolling/padding, same as it did inside a real ModalBottomSheet. Taps
 * inside the sheet are swallowed so they don't fall through to the scrim's
 * dismiss handler in AppOverlayRoot. */
@Composable
fun AppBottomSheetOverlay(content: @Composable () -> Unit) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.BottomCenter) {
        Surface(
            color = MaterialTheme.colorScheme.surface,
            shape = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp),
            modifier = Modifier
                .fillMaxWidth()
                .pointerInput(Unit) { detectTapGestures(onTap = {}) },
        ) {
            Box(Modifier.padding(top = 8.dp)) {
                content()
            }
        }
    }
}

/** Mirrors AlertDialog's look/placement: centered card. */
@Composable
fun AppDialogOverlay(content: @Composable () -> Unit) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Surface(
            color = MaterialTheme.colorScheme.surface,
            shape = RoundedCornerShape(20.dp),
            modifier = Modifier
                .widthIn(max = 400.dp)
                .padding(24.dp)
                .pointerInput(Unit) { detectTapGestures(onTap = {}) },
        ) {
            content()
        }
    }
}

/** Stand-in for AlertDialog's confirm/cancel prompt, rendered inline in the
 * caller's own layout instead of a separate Dialog window. Needed for
 * "are you sure?" prompts nested inside a bottom sheet — routing those
 * through AppOverlayHost too would just replace the sheet underneath it
 * (the host is a single slot), so they're composed directly in place
 * instead, which also keeps them inside the same window as everything else. */
@Composable
fun InlineConfirmCard(
    title: String,
    text: String,
    confirmLabel: String,
    onConfirm: () -> Unit,
    onCancel: () -> Unit,
    confirmColor: Color = MaterialTheme.colorScheme.error,
) {
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(16.dp),
        modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
    ) {
        Column(Modifier.padding(16.dp)) {
            Text(title, fontWeight = FontWeight.Bold)
            Text(text, modifier = Modifier.padding(top = 4.dp, bottom = 12.dp))
            Row(horizontalArrangement = Arrangement.End, modifier = Modifier.fillMaxWidth()) {
                TextButton(onClick = onCancel) { Text("Cancel") }
                TextButton(onClick = onConfirm) { Text(confirmLabel, color = confirmColor) }
            }
        }
    }
}
