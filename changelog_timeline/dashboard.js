// Utilitários de Data e Mock
function getRandomDate(start, end) {
    return new Date(start.getTime() + Math.random() * (end.getTime() - start.getTime()));
}

function formatDuration(ms) {
    if (!ms || ms === 0) return "--";
    const days = Math.floor(ms / (1000 * 60 * 60 * 24));
    const hours = Math.floor((ms % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    if (days > 0) return `${days}d ${hours}h`;
    return `${hours}h`;
}

function formatDate(dateStr) {
    if (!dateStr) return "--";
    return new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(dateStr));
}

// Estado Global
const state = {
    allData: [],
    filteredData: [],
    currentPage: 1,
    itemsPerPage: 15,
    leadChartInstance: null,
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

    // Ligar eventos
    bindEvents();
    
    // Disparar filtro inicial (projetos vazios = array vazio)
    applyFilters();
});

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

    // projectFilter triggers dropdown population first
    document.getElementById('projectFilter').addEventListener('input', (e) => {
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

function populateDropdowns(project) {
    const statusDiv = document.getElementById('status-dropdown');
    const assigneeDiv = document.getElementById('assignee-dropdown');
    
    // Clear current options
    statusDiv.innerHTML = '';
    assigneeDiv.innerHTML = '';
    
    // Update headers
    document.querySelector('#status-multiselect .multiselect-header').textContent = 'Status: Todos';
    document.querySelector('#assignee-multiselect .multiselect-header').textContent = 'Assignee: Todos';
    
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

    // Se o filtro de projeto estiver no default (""), não mostramos NADA.
    if (!project) {
        state.filteredData = [];
    } else {
        state.filteredData = state.allData.filter(item => {
            // Project
            if (item.project_key !== project) return false;
            
            // Search (Key)
            if (search && !item.key.toLowerCase().includes(search)) return false;
            
            // Status (Multi-select)
            if (statusOptions.length > 0 && !statusOptions.includes(item.status)) return false;
            
            // Assignee (Multi-select)
            if (assigneeOptions.length > 0 && !assigneeOptions.includes(item.assignee)) return false;
            
            // Parent Key
            if (parentKey && (!item.parent_key || !item.parent_key.toLowerCase().includes(parentKey))) return false;
            
            // Created Date Range
            if (createdStart || createdEnd) {
                const itemDate = new Date(item.created_at).getTime();
                if (createdStart) {
                    const start = new Date(createdStart).getTime();
                    if (itemDate < start) return false;
                }
                if (createdEnd) {
                    const end = new Date(createdEnd).getTime() + 86400000; // Add 1 day to include end of day
                    if (itemDate >= end) return false;
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
    const resolvedIssues = state.filteredData.filter(i => i.status === 'Done');
    
    if (resolvedIssues.length === 0) {
        document.getElementById('kpi-lead-time').innerText = "--";
        document.getElementById('kpi-cycle-time').innerText = "--";
        document.getElementById('kpi-efficiency').innerText = "--";
        return;
    }

    const avgLeadTimeMs = resolvedIssues.reduce((acc, curr) => acc + curr.lead_time_ms, 0) / resolvedIssues.length;
    const avgCycleTimeMs = resolvedIssues.reduce((acc, curr) => acc + curr.cycle_time_ms, 0) / resolvedIssues.length;
    
    document.getElementById('kpi-lead-time').innerText = formatDuration(avgLeadTimeMs);
    document.getElementById('kpi-cycle-time').innerText = formatDuration(avgCycleTimeMs);
    
    let efficiency = 0;
    if (avgLeadTimeMs > 0) {
        efficiency = ((avgCycleTimeMs / avgLeadTimeMs) * 100).toFixed(1);
    }
    document.getElementById('kpi-efficiency').innerText = `${efficiency}%`;
}

async function viewDetails(key) {
    document.getElementById('modalKey').innerText = key;
    const modal = document.getElementById('timelineModal');
    const modalBody = modal.querySelector('.modal-body');
    
    // Mostra loading
    modalBody.innerHTML = `<p style="text-align: center; color: #94a3b8;">Carregando histórico completo...</p>`;
    
    modal.style.display = 'flex';
    setTimeout(() => {
        modal.classList.add('active');
    }, 10);

    try {
        const response = await fetch(`/api/issues/${key}/timeline`);
        const timelineData = await response.json();
        
        // Pega as métricas totais consolidadas do array em memória
        const issue = state.allData.find(i => i.key === key);
        const leadTimeTxt = issue && issue.lead_time_ms ? formatDuration(issue.lead_time_ms) : "--";
        const cycleTimeTxt = issue && issue.cycle_time_ms ? formatDuration(issue.cycle_time_ms) : "--";
        
        // Calcular intervalos para a tabela
        let intervals = [];
        let inProgressStart = null;
        
        timelineData.forEach(history => {
            if (history.field === 'status') {
                const date = new Date(history.event_date);
                const toStatus = history.to_value;

                if (toStatus === 'In Progress') {
                    inProgressStart = date;
                }
                
                if ((toStatus === 'Blocked' || toStatus === 'Done') && inProgressStart) {
                    const durationMs = date - inProgressStart;
                    intervals.push({
                        phase: `Intervalo ${intervals.length + 1}`,
                        transition: `In Progress ➔ ${toStatus}`,
                        start: inProgressStart,
                        end: date,
                        durationMs: durationMs
                    });
                    inProgressStart = null;
                }
            }
        });

        // HTML base recuperado do index.html
        let html = `
            <section class="metrics-section" style="margin-bottom: 2rem;">
                <h3 style="margin-bottom: 1rem; font-size: 1.1rem;">Métricas de Tempo</h3>
                <div style="display: flex; gap: 1rem; margin-bottom: 1rem;">
                    <div style="background: rgba(255,255,255,0.05); padding: 1rem; border-radius: 8px; flex: 1;">
                        <span style="display: block; font-size: 0.8rem; color: #94a3b8; text-transform: uppercase;">Total Cycle Time</span>
                        <strong style="font-size: 1.5rem; color: var(--accent);">${cycleTimeTxt}</strong>
                    </div>
                    <div style="background: rgba(255,255,255,0.05); padding: 1rem; border-radius: 8px; flex: 1;">
                        <span style="display: block; font-size: 0.8rem; color: #94a3b8; text-transform: uppercase;">Total Lead Time</span>
                        <strong style="font-size: 1.5rem; color: var(--accent);">${leadTimeTxt}</strong>
                    </div>
                </div>
        `;
        
        if (intervals.length > 0) {
            html += `
                <table class="data-table" style="width: 100%; font-size: 0.8rem; margin-bottom: 1rem;">
                    <thead>
                        <tr style="text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1);">
                            <th style="padding: 0.5rem;">Fase</th>
                            <th style="padding: 0.5rem;">Transição</th>
                            <th style="padding: 0.5rem;">Início</th>
                            <th style="padding: 0.5rem;">Fim</th>
                            <th style="padding: 0.5rem;">Duração</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            intervals.forEach(inv => {
                html += `
                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                        <td style="padding: 0.5rem;">${inv.phase}</td>
                        <td style="padding: 0.5rem;">${inv.transition}</td>
                        <td style="padding: 0.5rem;">${formatDate(inv.start)}</td>
                        <td style="padding: 0.5rem;">${formatDate(inv.end)}</td>
                        <td style="padding: 0.5rem; color: var(--accent); font-weight: 500;">${formatDuration(inv.durationMs)}</td>
                    </tr>
                `;
            });
            html += `</tbody></table>`;
        }

        html += `</section>`;

        if (timelineData.length === 0) {
            html += `<p style="text-align: center; color: #94a3b8;">Nenhum evento no histórico.</p>`;
        } else {
            html += `<h3 style="margin-bottom: 1rem; font-size: 1.1rem;">Changelog</h3>`;
            html += `<div style="display: flex; flex-direction: column; gap: 1rem; max-height: 300px; overflow-y: auto; padding-right: 10px;">`;
            
            // Exibir todos os changelogs
            timelineData.forEach(event => {
                html += `
                    <div style="background: rgba(255,255,255,0.05); padding: 1rem; border-radius: 8px; border-left: 3px solid var(--accent);">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                            <strong style="color: #f8fafc;">${event.author_name}</strong>
                            <span style="color: #94a3b8; font-size: 0.8rem;">${formatDate(event.event_date)}</span>
                        </div>
                        <div style="font-size: 0.9rem;">
                            Alterou <strong style="color: #cbd5e1;">${event.field}</strong> 
                            de <span style="text-decoration: line-through; color: #ef4444;">${event.from_value || '(vazio)'}</span> 
                            para <span style="color: #34d399;">${event.to_value || '(vazio)'}</span>
                        </div>
                    </div>
                `;
            });
            
            html += `</div>`;
        }
        
        modalBody.innerHTML = html;
        
    } catch (error) {
        console.error("Erro ao buscar timeline:", error);
        modalBody.innerHTML = `<p style="text-align: center; color: #ef4444;">Erro ao carregar os dados.</p>`;
    }
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
            <td><strong>${item.key}</strong></td>
            <td>${item.parent_key || '--'}</td>
            <td>${item.assignee || '--'}</td>
            <td style="max-width: 400px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${item.summary}">${item.summary}</td>
            <td><span class="status-badge ${statusClass}">${item.status}</span></td>
            <td>${formatDate(item.created_at)}</td>
            <td>${formatDate(item.due_date)}</td>
            <td>${formatDate(item.updated_at)}</td>
            <td>${formatDate(item.resolved_at)}</td>
            <td>${formatDuration(item.lead_time_ms)}</td>
            <td>${formatDuration(item.cycle_time_ms)}</td>
            <td><button class="btn-drill" onclick="viewDetails('${item.key}')">Ver Detalhes</button></td>
        `;
        tbody.appendChild(tr);
    });

    // Update Pagination UI
    const maxPage = Math.ceil(state.filteredData.length / state.itemsPerPage);
    document.getElementById('page-info').innerText = `Página ${state.currentPage} de ${maxPage || 1}`;
    document.getElementById('btn-prev').disabled = state.currentPage <= 1;
    document.getElementById('btn-next').disabled = state.currentPage >= maxPage || maxPage === 0;
}

function renderCharts() {
    // Destroy previous charts if they exist
    if (state.leadChartInstance) state.leadChartInstance.destroy();
    if (state.statusChartInstance) state.statusChartInstance.destroy();

    if (state.filteredData.length === 0) return;

    // Chart 1: Distribuição de Lead Time (Histograma)
    const weeksMap = { '0-1w': 0, '1-2w': 0, '2-4w': 0, '4-8w': 0, '8w+': 0 };
    
    state.filteredData.forEach(i => {
        if (i.lead_time_ms === 0) return;
        const days = i.lead_time_ms / (1000 * 60 * 60 * 24);
        if (days <= 7) weeksMap['0-1w']++;
        else if (days <= 14) weeksMap['1-2w']++;
        else if (days <= 28) weeksMap['2-4w']++;
        else if (days <= 56) weeksMap['4-8w']++;
        else weeksMap['8w+']++;
    });

    const ctxLead = document.getElementById('leadTimeChart').getContext('2d');
    state.leadChartInstance = new Chart(ctxLead, {
        type: 'bar',
        data: {
            labels: Object.keys(weeksMap),
            datasets: [{
                label: 'Qtd de Issues Resolvidas',
                data: Object.values(weeksMap),
                backgroundColor: 'rgba(59, 130, 246, 0.7)',
                borderColor: 'rgba(59, 130, 246, 1)',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, grid: { color: 'rgba(255, 255, 255, 0.1)' } },
                x: { grid: { display: false } }
            }
        }
    });

    // Chart 2: Status Donuts
    const statusMap = { 'Done': 0, 'In Progress': 0, 'Blocked': 0, 'Open': 0 };
    state.filteredData.forEach(i => { 
        if (statusMap[i.status] !== undefined) statusMap[i.status]++; 
    });

    const ctxStatus = document.getElementById('statusChart').getContext('2d');
    state.statusChartInstance = new Chart(ctxStatus, {
        type: 'doughnut',
        data: {
            labels: Object.keys(statusMap),
            datasets: [{
                data: Object.values(statusMap),
                backgroundColor: [
                    'rgba(16, 185, 129, 0.7)', // Done
                    'rgba(59, 130, 246, 0.7)', // In Progress
                    'rgba(239, 68, 68, 0.7)',  // Blocked
                    'rgba(148, 163, 184, 0.7)' // Open
                ],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: {
                legend: { position: 'bottom', labels: { color: '#f8fafc' } }
            }
        }
    });
}
