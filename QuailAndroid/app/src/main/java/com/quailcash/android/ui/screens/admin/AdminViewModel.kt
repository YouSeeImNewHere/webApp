package com.quailcash.android.ui.screens.admin

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quailcash.android.data.model.HomelabMetrics
import com.quailcash.android.data.repository.HomeRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class AdminViewModel(private val repository: HomeRepository) : ViewModel() {
    private val _homelabMetrics = MutableStateFlow<HomelabMetrics?>(null)
    val homelabMetrics: StateFlow<HomelabMetrics?> = _homelabMetrics.asStateFlow()

    init {
        loadHomelabMetrics()
    }

    fun loadHomelabMetrics() {
        viewModelScope.launch {
            _homelabMetrics.value = null
            try {
                _homelabMetrics.value = repository.getHomelabMetrics()
            } catch (e: Exception) {
                _homelabMetrics.value = HomelabMetrics(error = e.message ?: "Unreachable")
            }
        }
    }

    class Factory(private val repository: HomeRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return AdminViewModel(repository) as T
        }
    }
}
