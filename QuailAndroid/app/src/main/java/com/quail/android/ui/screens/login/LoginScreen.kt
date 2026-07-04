package com.quail.android.ui.screens.login

import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.net.toUri
import com.quail.android.AppConfig
import com.quail.android.ui.theme.QuailAccent
import com.quail.android.ui.theme.QuailTextDim

@Composable
fun LoginScreen() {
    val context = LocalContext.current

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            "Quail",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.ExtraBold,
        )
        Text(
            "Sign in to see your accounts, spending, and budget.",
            style = MaterialTheme.typography.bodyMedium,
            color = QuailTextDim,
            modifier = Modifier.padding(top = 8.dp, bottom = 32.dp),
        )
        Button(
            onClick = {
                val customTabsIntent = CustomTabsIntent.Builder()
                    .setDefaultColorSchemeParams(
                        androidx.browser.customtabs.CustomTabColorSchemeParams.Builder()
                            .setToolbarColor(QuailAccent.toArgb())
                            .build()
                    )
                    .build()
                customTabsIntent.launchUrl(context, AppConfig.oauthStartUrl().toUri())
            },
            colors = ButtonDefaults.buttonColors(containerColor = QuailAccent),
            shape = RoundedCornerShape(14.dp),
            modifier = Modifier
                .fillMaxWidth()
                .height(56.dp),
        ) {
            Text("Sign in with Google", fontWeight = FontWeight.Bold)
        }
    }
}
