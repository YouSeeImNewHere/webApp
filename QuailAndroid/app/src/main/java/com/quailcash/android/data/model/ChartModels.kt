package com.quailcash.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

enum class ChartMode(val label: String, val path: String) {
    NET_WORTH("Net Worth", "net-worth"),
    SAVINGS("Savings", "savings"),
    INVESTMENTS("Investments", "investments"),
    SPENDING("Spending", "spending"),
}

@Serializable
data class ChartPoint(
    val date: String,
    val value: Double = 0.0,
    // Only present for the net-worth series (analytics.py /net-worth);
    // /savings, /investments, /spending only ever send date + value.
    val banks: Double? = null,
    val savings: Double? = null,
    val cards: Double? = null,
    @SerialName("cards_balance") val cardsBalance: Double? = null,
)
