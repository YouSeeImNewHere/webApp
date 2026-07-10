package com.quail.android.data.music

import com.quail.android.data.model.MusicAnalyticsResponse
import com.quail.android.data.model.MusicRecommendedResponse
import com.quail.android.data.model.MusicSearchResult
import com.quail.android.data.network.QuailApi

class MusicRepository(private val api: QuailApi) {
    suspend fun getRecommended(): MusicRecommendedResponse = api.getMusicRecommended()

    suspend fun search(query: String): List<MusicSearchResult> = api.searchMusic(query)

    suspend fun deleteTrack(id: String) {
        api.deleteMusicTrack(id)
    }

    suspend fun getAnalytics(): MusicAnalyticsResponse = api.getMusicAnalytics()
}
