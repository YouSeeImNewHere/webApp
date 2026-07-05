package com.quail.android.bugreport

import android.graphics.Bitmap
import android.graphics.Canvas as AndroidCanvas
import android.graphics.Color as AndroidColor
import android.graphics.Paint as AndroidPaint
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import com.quail.android.ui.theme.QuailSurface
import com.quail.android.ui.theme.QuailSurfaceRaised
import com.quail.android.ui.theme.QuailTextDim

private fun compositeAnnotations(original: Bitmap, strokes: List<List<Offset>>, displaySize: IntSize): Bitmap {
    if (strokes.isEmpty() || displaySize.width == 0 || displaySize.height == 0) return original
    val out = original.copy(Bitmap.Config.ARGB_8888, true)
    val canvas = AndroidCanvas(out)
    val scaleX = original.width.toFloat() / displaySize.width.toFloat()
    val scaleY = original.height.toFloat() / displaySize.height.toFloat()
    val paint = AndroidPaint().apply {
        color = AndroidColor.RED
        strokeWidth = 7f * scaleX
        strokeCap = AndroidPaint.Cap.ROUND
        style = AndroidPaint.Style.STROKE
        isAntiAlias = true
    }
    strokes.forEach { stroke ->
        for (i in 0 until stroke.size - 1) {
            canvas.drawLine(
                stroke[i].x * scaleX, stroke[i].y * scaleY,
                stroke[i + 1].x * scaleX, stroke[i + 1].y * scaleY,
                paint,
            )
        }
    }
    return out
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BugReportScreen(
    screenshot: Bitmap?,
    route: String,
    networkLog: String,
    onSubmit: (description: String, annotatedScreenshot: Bitmap?) -> Unit,
    onCancel: () -> Unit,
) {
    var description by remember { mutableStateOf("") }
    var strokes by remember { mutableStateOf(listOf<List<Offset>>()) }
    var currentStroke by remember { mutableStateOf(listOf<Offset>()) }
    var displaySize by remember { mutableStateOf(IntSize.Zero) }
    var showNetworkLog by remember { mutableStateOf(false) }
    val imageBitmap = remember(screenshot) { screenshot?.asImageBitmap() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Report a Bug", fontWeight = FontWeight.Bold) },
                navigationIcon = { IconButton(onClick = onCancel) { Icon(Icons.Filled.Close, contentDescription = "Cancel") } },
                actions = {
                    if (strokes.isNotEmpty()) {
                        IconButton(onClick = { strokes = emptyList() }) {
                            Icon(Icons.Filled.Delete, contentDescription = "Clear drawing")
                        }
                    }
                },
            )
        },
    ) { padding ->
        Column(Modifier.padding(padding).verticalScroll(rememberScrollState())) {
            if (imageBitmap != null) {
                Text(
                    "Draw on the screenshot to highlight the issue",
                    color = QuailTextDim,
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                )
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .aspectRatio(imageBitmap.width.toFloat() / imageBitmap.height.toFloat())
                        .padding(horizontal = 16.dp)
                        .onSizeChanged { displaySize = it }
                        .pointerInput(Unit) {
                            detectDragGestures(
                                onDragStart = { offset -> currentStroke = listOf(offset) },
                                onDrag = { change, _ -> currentStroke = currentStroke + change.position },
                                onDragEnd = {
                                    if (currentStroke.size > 1) strokes = strokes + listOf(currentStroke)
                                    currentStroke = emptyList()
                                },
                            )
                        },
                ) {
                    Image(bitmap = imageBitmap, contentDescription = "Screenshot", modifier = Modifier.fillMaxSize())
                    Canvas(Modifier.fillMaxSize()) {
                        (strokes + listOf(currentStroke)).forEach { stroke ->
                            for (i in 0 until stroke.size - 1) {
                                drawLine(
                                    color = Color.Red,
                                    start = stroke[i],
                                    end = stroke[i + 1],
                                    strokeWidth = 7f,
                                    cap = StrokeCap.Round,
                                )
                            }
                        }
                    }
                }
            }

            OutlinedTextField(
                value = description,
                onValueChange = { description = it },
                label = { Text("What went wrong?") },
                minLines = 3,
                modifier = Modifier.fillMaxWidth().padding(16.dp),
            )

            if (route.isNotBlank()) {
                Text(
                    "Screen path: $route",
                    color = QuailTextDim,
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.padding(horizontal = 16.dp),
                )
            }

            Surface(
                onClick = { showNetworkLog = !showNetworkLog },
                color = QuailSurface,
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth().padding(16.dp),
            ) {
                Column(Modifier.padding(12.dp)) {
                    Text(
                        if (showNetworkLog) "Hide recent network calls" else "Show recent network calls (included automatically)",
                        color = MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.SemiBold,
                        style = MaterialTheme.typography.labelMedium,
                    )
                    if (showNetworkLog) {
                        Surface(
                            color = QuailSurfaceRaised,
                            shape = RoundedCornerShape(8.dp),
                            modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
                        ) {
                            Text(
                                networkLog,
                                color = QuailTextDim,
                                style = MaterialTheme.typography.labelSmall,
                                modifier = Modifier.padding(10.dp),
                            )
                        }
                    }
                }
            }

            Button(
                onClick = {
                    val annotated = screenshot?.let { compositeAnnotations(it, strokes, displaySize) }
                    onSubmit(description, annotated)
                },
                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary),
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            ) {
                Text("Submit Bug Report", fontWeight = FontWeight.Bold, color = Color.Black, modifier = Modifier.padding(vertical = 6.dp))
            }
        }
    }
}
