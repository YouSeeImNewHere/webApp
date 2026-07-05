package com.quail.android.ui.screens.bugs

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.bugs.BugsRepository
import com.quail.android.data.model.BugNoteRecord
import com.quail.android.data.model.BugReportRecord
import com.quail.android.data.model.BugStatus
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class BugsData(val reports: List<BugReportRecord>, val notes: List<BugNoteRecord>) {
    val openCount: Int get() = reports.count { it.status == "open" } + notes.count { !it.isResolved }
}

class BugsViewModel(private val repository: BugsRepository) : ViewModel() {
    val uiState: StateFlow<BugsData?> = combine(repository.reports, repository.notes) { reports, notes ->
        BugsData(reports, notes)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    fun addReport(title: String, description: String) {
        if (title.isBlank()) return
        viewModelScope.launch {
            repository.saveReport(BugReportRecord(clientId = BugsRepository.newClientId(), title = title.trim(), description = description, status = BugStatus.OPEN.serverValue))
        }
    }

    fun updateReportStatus(report: BugReportRecord, status: BugStatus) {
        viewModelScope.launch { repository.saveReport(report.copy(status = status.serverValue)) }
    }

    fun updateReport(report: BugReportRecord, title: String, description: String) {
        viewModelScope.launch { repository.saveReport(report.copy(title = title, description = description)) }
    }

    fun deleteReport(clientId: String) {
        viewModelScope.launch { repository.deleteReport(clientId) }
    }

    fun addNote(text: String) {
        if (text.isBlank()) return
        viewModelScope.launch {
            repository.saveNote(BugNoteRecord(clientId = BugsRepository.newClientId(), text = text.trim()))
        }
    }

    fun toggleNote(note: BugNoteRecord) {
        viewModelScope.launch { repository.saveNote(note.copy(isResolved = !note.isResolved)) }
    }

    fun deleteNote(clientId: String) {
        viewModelScope.launch { repository.deleteNote(clientId) }
    }

    class Factory(private val repository: BugsRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = BugsViewModel(repository) as T
    }
}
