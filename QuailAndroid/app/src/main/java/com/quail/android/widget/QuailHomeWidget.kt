package com.quail.android.widget

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.SizeMode
import androidx.glance.appwidget.action.ActionCallback
import androidx.glance.appwidget.action.actionRunCallback
import androidx.glance.appwidget.cornerRadius
import androidx.glance.appwidget.provideContent
import androidx.glance.background
import androidx.glance.action.ActionParameters
import androidx.glance.layout.Alignment
import androidx.glance.layout.Box
import androidx.glance.layout.Column
import androidx.glance.layout.Row
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.fillMaxWidth
import androidx.glance.layout.height
import androidx.glance.layout.padding
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider
import com.quail.android.MainActivity
import com.quail.android.data.model.WidgetSummaryResponse
import com.quail.android.data.network.NetworkModule
import com.quail.android.data.repository.AuthStore
import kotlinx.coroutines.flow.first
import java.text.NumberFormat
import java.time.Duration
import java.time.Instant
import java.util.Locale

private const val WIDGET_SCRIPT_VERSION = 3

private val WidgetBackgroundColor = Color(0xFF17191D)
private val WidgetSurfaceColor = Color(0xFF23262C)
private val WidgetGood = Color(0xFF35C759)
private val WidgetWarn = Color(0xFFFF9F0A)
private val WidgetBad = Color(0xFFFF4538)
private val WidgetTextDim = Color(0xB3FFFFFF)

private fun money(value: Double, fraction: Int = 0): String {
    val nf = NumberFormat.getCurrencyInstance(Locale.US)
    nf.maximumFractionDigits = fraction
    nf.minimumFractionDigits = fraction
    val sign = if (value < 0) "-" else ""
    return sign + nf.format(kotlin.math.abs(value))
}

private fun creditColor(pct: Double): Color = when {
    pct < 0.3 -> WidgetGood
    pct < 0.6 -> WidgetWarn
    else -> WidgetBad
}

private fun footerText(payload: WidgetSummaryResponse?, failed: Boolean, loggedOut: Boolean): String {
    if (loggedOut) return "Open app to sign in"
    if (failed) return "Refresh failed"
    val generatedAt = payload?.generatedAt ?: return "Live"
    return try {
        val ageMinutes = Duration.between(Instant.parse(generatedAt), Instant.now()).toMinutes()
        when {
            ageMinutes < 2 -> "Live"
            ageMinutes < 60 -> "${ageMinutes}m ago"
            else -> "${ageMinutes / 60}h ago"
        }
    } catch (_: Exception) {
        "Live"
    }
}

class QuailHomeWidget : GlanceAppWidget() {
    override val sizeMode = SizeMode.Single

    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val authStore = AuthStore.getInstance(context.applicationContext)
        val token = authStore.session.first()?.token

        var payload: WidgetSummaryResponse? = null
        var failed = false
        if (token != null) {
            try {
                val api = NetworkModule.create(authStore)
                payload = api.getWidgetSummary(widgetScriptVersion = WIDGET_SCRIPT_VERSION)
            } catch (_: Exception) {
                failed = true
            }
        }

        val loggedOut = token == null
        provideContent {
            WidgetContent(payload = payload, failed = failed, loggedOut = loggedOut)
        }
    }
}

@Composable
private fun WidgetContent(payload: WidgetSummaryResponse?, failed: Boolean, loggedOut: Boolean) {
    Column(
        modifier = GlanceModifier
            .fillMaxSize()
            .background(ColorProvider(WidgetBackgroundColor))
            .cornerRadius(20.dp)
            .padding(14.dp)
            .clickable(actionStartActivity<MainActivity>()),
    ) {
        Row(modifier = GlanceModifier.fillMaxWidth(), verticalAlignment = Alignment.Vertical.CenterVertically) {
            Text(
                "Quail Cash",
                style = TextStyle(color = ColorProvider(WidgetTextDim), fontSize = 11.sp, fontWeight = FontWeight.Bold),
            )
            Box(modifier = GlanceModifier.defaultWeight()) {}
            Text(
                "Refresh",
                style = TextStyle(color = ColorProvider(WidgetTextDim), fontSize = 11.sp, fontWeight = FontWeight.Bold),
                modifier = GlanceModifier.clickable(actionRunCallback<RefreshWidgetAction>()),
            )
        }

        Box(modifier = GlanceModifier.height(6.dp)) {}

        if (loggedOut) {
            Text(
                "Sign in to Quail Cash to see your safe-to-spend.",
                style = TextStyle(color = ColorProvider(WidgetTextDim), fontSize = 13.sp),
            )
            return@Column
        }

        val data = payload
        Text(
            "SAFE TO SPEND",
            style = TextStyle(color = ColorProvider(WidgetTextDim), fontSize = 10.sp, fontWeight = FontWeight.Bold),
        )
        Text(
            money(data?.safeToSpend ?: 0.0, 2),
            style = TextStyle(color = ColorProvider(Color.White), fontSize = 26.sp, fontWeight = FontWeight.Bold),
        )

        Box(modifier = GlanceModifier.height(10.dp)) {}

        val creditPct = data?.credit?.pct ?: 0.0
        MetricRow(title = "CREDIT USED", trailing = "${(creditPct * 100).toInt()}%", barColor = creditColor(creditPct))

        Box(modifier = GlanceModifier.height(6.dp)) {}
        val todayRemaining = data?.today?.remainingToday ?: 0.0
        MetricRow(
            title = "TODAY LEFT",
            trailing = money(todayRemaining, 0),
            barColor = if (todayRemaining < 0) WidgetBad else WidgetGood,
        )

        Box(modifier = GlanceModifier.height(10.dp)) {}

        Row(modifier = GlanceModifier.fillMaxWidth()) {
            Column(modifier = GlanceModifier.defaultWeight()) {
                Text("Checking", style = TextStyle(color = ColorProvider(WidgetTextDim), fontSize = 11.sp))
                Text(
                    money(data?.totals?.checking ?: 0.0, 2),
                    style = TextStyle(color = ColorProvider(Color.White), fontSize = 13.sp, fontWeight = FontWeight.Bold),
                )
            }
            Column(modifier = GlanceModifier.defaultWeight()) {
                Text("Savings", style = TextStyle(color = ColorProvider(WidgetTextDim), fontSize = 11.sp))
                Text(
                    money(data?.totals?.savings ?: 0.0, 2),
                    style = TextStyle(color = ColorProvider(Color.White), fontSize = 13.sp, fontWeight = FontWeight.Bold),
                )
            }
        }

        Box(modifier = GlanceModifier.height(8.dp)) {}
        Text(footerText(data, failed, loggedOut), style = TextStyle(color = ColorProvider(WidgetTextDim), fontSize = 10.sp))
    }
}

@Composable
private fun MetricRow(title: String, trailing: String, barColor: Color) {
    Column(modifier = GlanceModifier.fillMaxWidth()) {
        Row(modifier = GlanceModifier.fillMaxWidth()) {
            Text(title, style = TextStyle(color = ColorProvider(WidgetTextDim), fontSize = 10.sp, fontWeight = FontWeight.Bold))
            Box(modifier = GlanceModifier.defaultWeight()) {}
            Text(trailing, style = TextStyle(color = ColorProvider(barColor), fontSize = 10.sp, fontWeight = FontWeight.Bold))
        }
        Box(modifier = GlanceModifier.height(3.dp)) {}
        Box(
            modifier = GlanceModifier
                .fillMaxWidth()
                .height(6.dp)
                .background(ColorProvider(WidgetSurfaceColor))
                .cornerRadius(3.dp),
        ) {}
    }
}

class RefreshWidgetAction : ActionCallback {
    override suspend fun onAction(context: Context, glanceId: GlanceId, parameters: ActionParameters) {
        QuailHomeWidget().update(context, glanceId)
    }
}
