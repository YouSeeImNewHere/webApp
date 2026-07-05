package com.quail.android.ui.screens.projects

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.quail.android.data.model.ChecklistItemEntry
import com.quail.android.data.model.ProjectChecklistRecord
import com.quail.android.data.model.ProjectQuickNoteRecord
import com.quail.android.data.model.ProjectRecord
import com.quail.android.data.model.ProjectSection
import com.quail.android.data.model.ProjectType
import com.quail.android.data.model.projectTemplateSections
import com.quail.android.data.projects.ProjectsRepository
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import java.util.UUID

data class ProjectsData(
    val projects: List<ProjectRecord>,
    val quickNotes: List<ProjectQuickNoteRecord>,
    val checklists: List<ProjectChecklistRecord>,
)

class ProjectsViewModel(private val repository: ProjectsRepository) : ViewModel() {
    val uiState: StateFlow<ProjectsData?> = combine(
        repository.projects,
        repository.quickNotes,
        repository.checklists,
    ) { projects, quickNotes, checklists ->
        ProjectsData(projects, quickNotes, checklists)
    }.stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), null)

    fun createProject(name: String, type: ProjectType) {
        if (name.isBlank()) return
        viewModelScope.launch {
            repository.saveProject(
                ProjectRecord(
                    clientId = ProjectsRepository.newClientId(),
                    name = name.trim(),
                    type = type.serverValue,
                    sections = projectTemplateSections(type),
                ),
            )
        }
    }

    fun saveProject(project: ProjectRecord) {
        viewModelScope.launch { repository.saveProject(project) }
    }

    fun deleteProject(clientId: String) {
        viewModelScope.launch { repository.deleteProject(clientId) }
    }

    fun updateSection(project: ProjectRecord, section: ProjectSection) {
        saveProject(project.copy(sections = project.sections.map { if (it.id == section.id) section else it }))
    }

    fun addQuickNote(title: String, text: String) {
        if (text.isBlank()) return
        viewModelScope.launch {
            repository.saveQuickNote(ProjectQuickNoteRecord(clientId = ProjectsRepository.newClientId(), title = title, text = text.trim()))
        }
    }

    fun deleteQuickNote(clientId: String) {
        viewModelScope.launch { repository.deleteQuickNote(clientId) }
    }

    fun addChecklist(title: String) {
        if (title.isBlank()) return
        viewModelScope.launch {
            repository.saveChecklist(ProjectChecklistRecord(clientId = ProjectsRepository.newClientId(), title = title.trim()))
        }
    }

    fun addChecklistItem(checklist: ProjectChecklistRecord, text: String) {
        if (text.isBlank()) return
        val updated = checklist.copy(items = checklist.items + ChecklistItemEntry(id = UUID.randomUUID().toString(), text = text.trim()))
        viewModelScope.launch { repository.saveChecklist(updated) }
    }

    fun toggleChecklistItem(checklist: ProjectChecklistRecord, itemId: String) {
        val updated = checklist.copy(items = checklist.items.map { if (it.id == itemId) it.copy(isChecked = !it.isChecked) else it })
        viewModelScope.launch { repository.saveChecklist(updated) }
    }

    fun deleteChecklist(clientId: String) {
        viewModelScope.launch { repository.deleteChecklist(clientId) }
    }

    class Factory(private val repository: ProjectsRepository) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T = ProjectsViewModel(repository) as T
    }
}
