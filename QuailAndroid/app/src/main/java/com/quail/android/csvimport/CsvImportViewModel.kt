package com.quail.android.csvimport

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.network.QuailApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class CsvImportProgress(val processed: Int, val total: Int, val statusText: String)

class CsvImportViewModel(
    private val api: QuailApi,
    private val repository: CsvImportRepository,
    private val appContext: Context,
) : ViewModel() {
    val items: StateFlow<List<CsvImportQueueEntity>> =
        repository.items.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    private val _processing = MutableStateFlow<CsvImportProgress?>(null)
    val processing: StateFlow<CsvImportProgress?> = _processing

    fun processAll() {
        if (_processing.value != null) return
        viewModelScope.launch {
            _processing.value = CsvImportProgress(0, 0, "Starting")
            val summary = CsvImportProcessor.processAll(api, repository) { processed, total, statusText ->
                _processing.value = CsvImportProgress(processed, total, statusText)
                CsvImportNotifier.showProgress(appContext, processed, total, statusText)
            }
            CsvImportNotifier.showDone(appContext, summary)
            _processing.value = null
        }
    }

    fun deleteItem(id: String) {
        viewModelScope.launch { repository.remove(id) }
    }

    class Factory(
        private val api: QuailApi,
        private val repository: CsvImportRepository,
        private val appContext: Context,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = CsvImportViewModel(api, repository, appContext) as T
    }
}
