package com.quailcash.android.data.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class BankInfoAccount(
    @SerialName("account_id") val accountId: Int = 0,
    val bank: String? = null,
    val name: String? = null,
    val type: String? = null,
)

@Serializable
data class BankInfoCard(
    @SerialName("card_id") val cardId: Int = 0,
    val bank: String? = null,
    val name: String? = null,
)

@Serializable
data class BankInfoOptions(
    val accounts: List<BankInfoAccount> = emptyList(),
    @SerialName("credit_cards") val creditCards: List<BankInfoCard> = emptyList(),
)
