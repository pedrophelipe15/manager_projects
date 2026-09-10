// Utilitários de Data
function formatDuration(ms) {
    if (!ms || ms === 0) return "--";
    const days = Math.floor(ms / (1000 * 60 * 60 * 24));
    const hours = Math.floor((ms % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    if (days > 0) return `${days}d ${hours}h`;
    return `${hours}h`;
}

function formatDate(dateStr) {
    if (!dateStr) return "--";
    const parts = dateStr.split('T')[0].split('-');
    if (parts.length === 3) {
        return `${parts[2]}/${parts[1]}/${parts[0]}`;
    }
    return dateStr;
}

// Estado Global
const state = {
    allData: [],
    filteredData: [],
    currentPage: 1,
    itemsPerPage: 15,
    statusChartInstance: null
};

// Inicialização
document.addEventListener('DOMContentLoaded', async () => {
    console.time("Buscando dados da API");
    try {
        const response = await fetch('/api/issues');
        state.allData = await response.json();
    } catch (error) {
        console.error("Erro ao buscar issues da API:", error);
        state.allData = [];
    }
    console.timeEnd("Buscando dados da API");

    // Popular dropdown de projetos dinamicamente
    populateProjectDropdown();

    // Ligar eventos
    bindEvents();
    
    // Dispara populateDropdowns com o valor selecionado (auto ou manual)
    const selectedProject = document.getElementById('projectFilter').value;
    if (selectedProject) {
        populateDropdowns(selectedProject);
    }

    // Disparar filtro inicial
    applyFilters();
});

function populateProjectDropdown() {
    const select = document.getElementById('projectFilter');
    const projects = new Map();
    
    state.allData.forEach(item => {
        if (item.project_key && !projects.has(item.project_key)) {
            projects.set(item.project_key, item.project_key);
        }
    });

    projects.forEach((name, key) => {
        const option = document.createElement('option');
        option.value = key;
        option.textContent = `${key}`;
        select.appendChild(option);
    });

    // Se só tem um projeto, seleciona automaticamente
    if (projects.size === 1) {
        select.value = projects.keys().next().value;
    }
}

function bindEvents() {
    document.getElementById('btn-prev').addEventListener('click', () => {
        if (state.currentPage > 1) {
            state.currentPage--;
            renderTable();
        }
    });

    document.getElementById('btn-next').addEventListener('click', () => {
        const maxPage = Math.ceil(state.filteredData.length / state.itemsPerPage);
        if (state.currentPage < maxPage) {
            state.currentPage++;
            renderTable();
        }
    });

    // projectFilter triggers dropdown population and resets dependent filters
    document.getElementById('projectFilter').addEventListener('change', (e) => {
        resetDependentFilters();
        populateDropdowns(e.target.value);
        applyFilters();
    });

    // Outros inputs disparam applyFilters diretamente
    const filterInputs = [
        'searchInput', 'filterCreatedStart', 
        'filterCreatedEnd', 'filterParentKey'
    ];
    
    filterInputs.forEach(id => {
        document.getElementById(id).addEventListener('input', applyFilters);
    });
}

function resetDependentFilters() {
    // Limpa filtros que dependem do projeto selecionado
    document.getElementById('searchInput').value = '';
    document.getElementById('filterCreatedStart').value = '';
    document.getElementById('filterCreatedEnd').value = '';
    document.getElementById('filterParentKey').value = '';
}

function populateDropdowns(project) {
    const statusDiv = document.getElementById('status-dropdown');
    const assigneeDiv = document.getElementById('assignee-dropdown');
    
    // Clear current options
    statusDiv.innerHTML = '';
    assigneeDiv.innerHTML = '';
    
    // Reset headers
    const statusHeader = document.querySelector('#status-multiselect .multiselect-header');
    const assigneeHeader = document.querySelector('#assignee-multiselect .multiselect-header');
    statusHeader.innerHTML = '<span class="placeholder-text">Status: Todos</span>';
    assigneeHeader.innerHTML = '<span class="placeholder-text">Assignee: Todos</span>';
    
    if (!project) return;
    
    const projectData = state.allData.filter(item => item.project_key === project);
    
    const uniqueStatuses = [...new Set(projectData.map(i => i.status))].sort();
    const uniqueAssignees = [...new Set(projectData.map(i => i.assignee).filter(Boolean))].sort();
    
    uniqueStatuses.forEach(status => {
        const label = document.createElement('label');
        label.innerHTML = `<input type="checkbox" value="${status}" class="status-check" onchange="updateHeader('status'); applyFilters();"> ${status}`;
        statusDiv.appendChild(label);
    });
    
    uniqueAssignees.forEach(assignee => {
        const label = document.createElement('label');
        label.innerHTML = `<input type="checkbox" value="${assignee}" class="assignee-check" onchange="updateHeader('assignee'); applyFilters();"> ${assignee}`;
        assigneeDiv.appendChild(label);
    });
}

function toggleDropdown(id) {
    document.getElementById(id).classList.toggle('open');
}

function updateHeader(type) {
    const checked = document.querySelectorAll(`#${type}-dropdown input:checked`);
    const header = document.querySelector(`#${type}-multiselect .multiselect-header`);
    
    header.innerHTML = '';
    
    if (checked.length === 0) {
        const placeholder = type === 'status' ? 'Status: Todos' : 'Assignee: Todos';
        header.innerHTML = `<span class="placeholder-text">${placeholder}</span>`;
    } else {
        checked.forEach(cb => {
            const tag = document.createElement('span');
            tag.className = 'multiselect-tag';
            tag.innerHTML = `${cb.value} <span class="tag-remove" onclick="removeTag(event, '${type}', '${cb.value}')">×</span>`;
            header.appendChild(tag);
        });
    }
}

window.removeTag = function(event, type, value) {
    event.stopPropagation();
    const cb = document.querySelector(`#${type}-dropdown input[value="${value}"]`);
    if (cb) {
        cb.checked = false;
        updateHeader(type);
        applyFilters();
    }
}

// Close dropdowns when clicking outside
window.addEventListener('click', function(e) {
    if (!e.target.closest('.custom-multiselect')) {
        document.querySelectorAll('.multiselect-options').forEach(el => el.classList.remove('open'));
    }
});

function applyFilters() {
    const project = document.getElementById('projectFilter').value;
    const search = document.getElementById('searchInput').value.toLowerCase();
    const createdStart = document.getElementById('filterCreatedStart').value;
    const createdEnd = document.getElementById('filterCreatedEnd').value;
    const parentKey = document.getElementById('filterParentKey').value.toLowerCase();
    
    const statusOptions = Array.from(document.querySelectorAll('.status-check:checked')).map(cb => cb.value);
    const assigneeOptions = Array.from(document.querySelectorAll('.assignee-check:checked')).map(cb => cb.value);

    if (!project) {
        state.filteredData = [];
    } else {
        state.filteredData = state.allData.filter(item => {
            if (item.project_key !== project) return false;
            if (search && !item.key.toLowerCase().includes(search)) return false;
            if (statusOptions.length > 0 && !statusOptions.includes(item.status)) return false;
            if (assigneeOptions.length > 0 && !assigneeOptions.includes(item.assignee)) return false;
            if (parentKey && (!item.parent_key || !item.parent_key.toLowerCase().includes(parentKey))) return false;
            
            if (createdStart || createdEnd) {
                const itemDate = new Date(item.created_at).getTime();
                if (createdStart) {
                    const start = new Date(createdStart + 'T00:00:00').getTime();
                    if (itemDate < start) return false;
                }
                if (createdEnd) {
                    const end = new Date(createdEnd + 'T23:59:59').getTime();
                    if (itemDate > end) return false;
                }
            }
            
            return true;
        });
    }

    state.currentPage = 1;
    document.getElementById('total-issues-count').innerText = state.filteredData.length.toLocaleString('pt-BR');
    
    updateKPIs();
    renderCharts();
    renderTable();
}

window.clearFilters = function() {
    document.getElementById('searchInput').value = '';
    document.getElementById('filterCreatedStart').value = '';
    document.getElementById('filterCreatedEnd').value = '';
    document.getElementById('filterParentKey').value = '';
    
    document.querySelectorAll('.status-check').forEach(cb => cb.checked = false);
    document.querySelectorAll('.assignee-check').forEach(cb => cb.checked = false);
    
    updateHeader('status');
    updateHeader('assignee');
    
    applyFilters();
};

function updateKPIs() {
    const now = new Date();
    const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    const activeStates = new Set(['In Progress', 'Blocked', 'Test', 'Waiting for Delivery']);

    // Done esta semana: issues resolvidas nos últimos 7 dias
    const doneThisWeek = state.filteredData.filter(i => {
        if (i.status !== 'Done' || !i.resolved_at) return false;
        const resolved = new Date(i.resolved_at);
        return resolved >= sevenDaysAgo;
    });
    document.getElementById('kpi-done-week').innerText = doneThisWeek.length;

    // WIP: issues em estados ativos
    const wipIssues = state.filteredData.filter(i => activeStates.has(i.status));
    document.getElementById('kpi-wip').innerText = wipIssues.length;

    // Paradas >7 dias: issues ativas com updated_at > 7 dias
    const staleIssues = wipIssues.filter(i => {
        if (!i.updated_at) return false;
        const updated = new Date(i.updated_at);
        return updated < sevenDaysAgo;
    });
    const staleEl = document.getElementById('kpi-stale');
    staleEl.innerText = staleIssues.length;
    staleEl.style.color = staleIssues.length > 0 ? '#f87171' : '';
}

window.viewTimeline = function(key) {
    document.getElementById('modalKey').innerText = key;
    const modal = document.getElementById('timelineModal');
    const modalBody = modal.querySelector('.modal-body');
    
    modalBody.innerHTML = `<iframe src="/?issue=${key}" style="width: 100%; height: 70vh; border: none; border-radius: 8px;"></iframe>`;
    
    modal.style.display = 'flex';
    setTimeout(() => {
        modal.classList.add('active');
    }, 10);
}

window.closeModal = function(e) {
    if (e && e.target !== e.currentTarget) return;
    const modal = document.getElementById('timelineModal');
    modal.classList.remove('active');
    setTimeout(() => {
        modal.style.display = 'none';
    }, 300);
}

function renderTable() {
    const tbody = document.getElementById('table-body');
    tbody.innerHTML = '';

    const start = (state.currentPage - 1) * state.itemsPerPage;
    const end = start + state.itemsPerPage;
    const pageData = state.filteredData.slice(start, end);

    if (pageData.length === 0) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td colspan="12" style="text-align:center; padding: 2rem;">Nenhum registro encontrado. Selecione um projeto ou ajuste os filtros.</td>`;
        tbody.appendChild(tr);
    }

    pageData.forEach(item => {
        const tr = document.createElement('tr');
        
        let statusClass = 'status-open';
        if(item.status === 'Done') statusClass = 'status-done';
        if(item.status === 'In Progress') statusClass = 'status-progress';
        if(item.status === 'Blocked') statusClass = 'status-blocked';

        tr.innerHTML = `
            <td><strong><a href="https://jiraps.atlassian.net/browse/${item.key}" target="_blank" rel="noopener" style="color:#3b82f6;text-decoration:none">${item.key}</a></strong></td>
            <td>${item.parent_key ? `<a href="https://jiraps.atlassian.net/browse/${item.parent_key}" target="_blank" rel="noopener" style="color:#3b82f6;text-decoration:none">${item.parent_key}</a>` : '--'}</td>
            <td class="cell-assignee">${item.assignee || '--'}</td>
            <td class="cell-summary" title="${item.summary}">${item.summary}</td>
            <td><span class="status-badge ${statusClass}">${item.status}</span></td>
            <td>${formatDate(item.created_at)}</td>
            <td>${formatDate(item.due_date)}</td>
            <td>${formatDate(item.updated_at)}</td>
            <td>${formatDate(item.resolved_at)}</td>
            <td>${formatDuration(item.lead_time_ms)}</td>
            <td>${formatDuration(item.cycle_time_ms)}</td>
            <td><button class="btn-drill" onclick="viewTimeline('${item.key}')">Ver Timeline</button></td>
        `;
        tbody.appendChild(tr);
    });

    const maxPage = Math.ceil(state.filteredData.length / state.itemsPerPage);
    document.getElementById('page-info').innerText = `Página ${state.currentPage} de ${maxPage || 1}`;
    document.getElementById('btn-prev').disabled = state.currentPage <= 1;
    document.getElementById('btn-next').disabled = state.currentPage >= maxPage || maxPage === 0;
}

function renderCharts() {
    // Charts removidos — dados analíticos estão nas waves
}
