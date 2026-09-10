// Inconsistencies with filters and pagination per section
const ITEMS_PER_PAGE = 15;
let sectionsData = {};

const JIRA_BASE_URL = 'https://jiraps.atlassian.net/browse/';

function jiraKeyLink(key) {
    if (!key) return '--';
    return `<a href="${JIRA_BASE_URL}${key}" target="_blank" rel="noopener" style="color:#3b82f6;text-decoration:none">${key}</a>`;
}

document.addEventListener('DOMContentLoaded', () => {
    loadProjects();
    document.getElementById('projectFilter').addEventListener('change', onProjectChange);
});

async function loadProjects() {
    try {
        const response = await fetch('/api/settings/projects');
        const projects = await response.json();
        const select = document.getElementById('projectFilter');
        projects.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.key;
            opt.textContent = `${p.key} - ${p.name}`;
            select.appendChild(opt);
        });
        if (projects.length === 1) {
            select.value = projects[0].key;
            onProjectChange();
        }
    } catch (error) {
        console.error('Erro ao carregar projetos:', error);
    }
}

async function onProjectChange() {
    const projectKey = document.getElementById('projectFilter').value;
    const container = document.getElementById('results-container');
    const badge = document.getElementById('totalBadge');

    if (!projectKey) {
        container.innerHTML = '<p class="empty-state">Selecione um projeto para verificar inconsistências.</p>';
        badge.style.display = 'none';
        return;
    }

    container.innerHTML = '<p class="loading">Analisando...</p>';

    try {
        const [incResponse, rulesResponse] = await Promise.all([
            fetch(`/api/inconsistencies?project_key=${projectKey}`),
            fetch('/api/settings/validations'),
        ]);
        const data = await incResponse.json();
        const rules = await rulesResponse.json();
        renderResults(data, rules);
    } catch (error) {
        container.innerHTML = '<p class="error-state">Erro ao carregar inconsistências.</p>';
        console.error(error);
    }
}

function renderResults(data, rules) {
    const container = document.getElementById('results-container');
    const badge = document.getElementById('totalBadge');
    const totals = data.totals;
    const inc = data.inconsistencies;

    badge.textContent = `${totals.total} inconsistência(s)`;
    badge.style.display = 'inline-block';
    badge.className = totals.total > 0 ? 'total-badge warn' : 'total-badge ok';

    // Monta mapa de regras para usar nome/descrição dinâmicos
    const rulesMap = {};
    rules.forEach(r => { rulesMap[r.id] = r; });

    // Armazena dados por seção para filtros e paginação
    sectionsData = {
        sec1: { items: inc.due_date_parent_vs_subtask, page: 1, filter: '', type: 'duedate_parent' },
        sec2: { items: inc.due_date_empty, page: 1, filter: '', type: 'simple' },
        sec3: { items: inc.done_without_metrics, page: 1, filter: '', type: 'simple' },
        sec4: { items: inc.active_without_cycle, page: 1, filter: '', type: 'simple' },
        sec5: { items: inc.active_without_assignee, page: 1, filter: '', type: 'noassignee' },
    };

    const ruleFor = (id) => rulesMap[id] || { name: id, description: '' };

    let html = '';

    html += renderSection('sec1',
        ruleFor('due_date_parent_vs_subtask').name,
        ruleFor('due_date_parent_vs_subtask').description,
        totals.due_date_parent_vs_subtask);

    html += renderSection('sec2',
        ruleFor('due_date_empty').name,
        ruleFor('due_date_empty').description,
        totals.due_date_empty);

    html += renderSection('sec3',
        ruleFor('done_without_metrics').name,
        ruleFor('done_without_metrics').description,
        totals.done_without_metrics);

    html += renderSection('sec4',
        ruleFor('active_without_cycle').name,
        ruleFor('active_without_cycle').description,
        totals.active_without_cycle);

    html += renderSection('sec5',
        ruleFor('active_without_assignee').name,
        ruleFor('active_without_assignee').description,
        totals.active_without_assignee);

    container.innerHTML = html;

    // Renderiza tabelas iniciais
    Object.keys(sectionsData).forEach(secId => {
        renderSectionTable(secId);
    });
}

function renderSection(secId, title, description, count) {
    const statusClass = count > 0 ? 'section-warn' : 'section-ok';
    const statusIcon = count > 0 ? '⚠️' : '✅';
    const collapsed = count === 0 ? '' : 'open';

    return `
        <details class="inconsistency-section glass ${statusClass}" ${collapsed}>
            <summary class="section-summary">
                <span class="section-icon">${statusIcon}</span>
                <span class="section-title">${title}</span>
                <span class="section-count">${count}</span>
            </summary>
            <div class="section-body">
                <p class="section-desc">${description}</p>
                ${count > 0 ? `
                    <div class="section-filters">
                        <input type="text" class="filter-input" placeholder="Filtrar por key, summary, assignee..."
                               oninput="onSectionFilter('${secId}', this.value)">
                    </div>
                    <div id="table-${secId}"></div>
                    <div class="section-pagination" id="pagination-${secId}"></div>
                ` : '<p class="section-ok-msg">Nenhuma inconsistência encontrada.</p>'}
            </div>
        </details>
    `;
}

window.onSectionFilter = function(secId, value) {
    sectionsData[secId].filter = value.toLowerCase();
    sectionsData[secId].page = 1;
    renderSectionTable(secId);
};

window.goToPage = function(secId, page) {
    sectionsData[secId].page = page;
    renderSectionTable(secId);
};

function getFilteredItems(secId) {
    const sec = sectionsData[secId];
    if (!sec.filter) return sec.items;

    const q = sec.filter;
    return sec.items.filter(item => {
        const key = (item.key || item.child_key || '').toLowerCase();
        const parentKey = (item.parent_key || '').toLowerCase();
        const summary = (item.summary || item.child_summary || '').toLowerCase();
        const assignee = (item.assignee || item.child_assignee || '').toLowerCase();
        const status = (item.status || item.child_status || '').toLowerCase();
        return key.includes(q) || parentKey.includes(q) || summary.includes(q) || assignee.includes(q) || status.includes(q);
    });
}

function renderSectionTable(secId) {
    const sec = sectionsData[secId];
    const tableContainer = document.getElementById(`table-${secId}`);
    const paginationContainer = document.getElementById(`pagination-${secId}`);

    if (!tableContainer) return;

    const filtered = getFilteredItems(secId);
    const totalPages = Math.ceil(filtered.length / ITEMS_PER_PAGE) || 1;
    const page = Math.min(sec.page, totalPages);
    const start = (page - 1) * ITEMS_PER_PAGE;
    const pageItems = filtered.slice(start, start + ITEMS_PER_PAGE);

    // Render table based on type
    let tableHtml = '';
    if (sec.type === 'duedate_parent') {
        tableHtml = renderDueDateParentTable(pageItems);
    } else if (sec.type === 'noassignee') {
        tableHtml = renderNoAssigneeTable(pageItems);
    } else {
        tableHtml = renderSimpleTable(pageItems);
    }

    tableContainer.innerHTML = tableHtml;

    // Pagination
    if (filtered.length > ITEMS_PER_PAGE) {
        paginationContainer.innerHTML = `
            <div class="pagination">
                <button onclick="goToPage('${secId}', ${page - 1})" ${page <= 1 ? 'disabled' : ''}>Anterior</button>
                <span class="page-info">Página ${page} de ${totalPages} (${filtered.length} itens)</span>
                <button onclick="goToPage('${secId}', ${page + 1})" ${page >= totalPages ? 'disabled' : ''}>Próxima</button>
            </div>
        `;
    } else {
        paginationContainer.innerHTML = filtered.length > 0 ? `<span class="page-info-small">${filtered.length} itens</span>` : '';
    }
}

function renderDueDateParentTable(items) {
    if (items.length === 0) return '<p class="no-results">Nenhum resultado para o filtro.</p>';
    let html = `
        <table class="inc-table">
            <thead>
                <tr>
                    <th>Key</th>
                    <th>Parent Key</th>
                    <th>Assignee</th>
                    <th>Status</th>
                    <th>Summary</th>
                    <th>Date Create</th>
                    <th>Updated</th>
                    <th>Due Date</th>
                </tr>
            </thead>
            <tbody>
    `;
    items.forEach(item => {
        let statusClass = 'open';
        if (item.child_status === 'In Progress') statusClass = 'progress';
        else if (item.child_status === 'Blocked') statusClass = 'blocked';
        else if (item.child_status === 'Done') statusClass = 'done';
        html += `
            <tr>
                <td><strong>${jiraKeyLink(item.child_key)}</strong></td>
                <td>${jiraKeyLink(item.parent_key)}</td>
                <td>${item.child_assignee || '--'}</td>
                <td><span class="status-badge status-${statusClass}">${item.child_status}</span></td>
                <td><span class="cell-summary">${escapeHTML(item.child_summary || '')}</span></td>
                <td>${formatDate(item.child_created_at)}</td>
                <td>${formatDate(item.child_updated_at)}</td>
                <td>${formatDate(item.child_due_date)}</td>
            </tr>
        `;
    });
    html += '</tbody></table>';
    return html;
}

function renderSimpleTable(items) {
    if (items.length === 0) return '<p class="no-results">Nenhum resultado para o filtro.</p>';
    let html = `
        <table class="inc-table">
            <thead>
                <tr>
                    <th>Key</th>
                    <th>Parent Key</th>
                    <th>Assignee</th>
                    <th>Status</th>
                    <th>Summary</th>
                    <th>Date Create</th>
                    <th>Updated</th>
                    <th>Due Date</th>
                </tr>
            </thead>
            <tbody>
    `;
    items.forEach(item => {
        let statusClass = 'open';
        if (item.status === 'In Progress') statusClass = 'progress';
        if (item.status === 'Blocked') statusClass = 'blocked';
        if (item.status === 'Done') statusClass = 'done';
        html += `
            <tr>
                <td><strong>${jiraKeyLink(item.key)}</strong></td>
                <td>${jiraKeyLink(item.parent_key)}</td>
                <td>${item.assignee || '--'}</td>
                <td><span class="status-badge status-${statusClass}">${item.status}</span></td>
                <td><span class="cell-summary">${escapeHTML(item.summary || '')}</span></td>
                <td>${formatDate(item.created_at)}</td>
                <td>${formatDate(item.updated_at)}</td>
                <td>${formatDate(item.due_date)}</td>
            </tr>
        `;
    });
    html += '</tbody></table>';
    return html;
}

function renderNoAssigneeTable(items) {
    if (items.length === 0) return '<p class="no-results">Nenhum resultado para o filtro.</p>';
    let html = `
        <table class="inc-table">
            <thead>
                <tr>
                    <th>Key</th>
                    <th>Parent Key</th>
                    <th>Assignee</th>
                    <th>Status</th>
                    <th>Summary</th>
                    <th>Date Create</th>
                    <th>Updated</th>
                    <th>Due Date</th>
                </tr>
            </thead>
            <tbody>
    `;
    items.forEach(item => {
        let statusClass = 'open';
        if (item.status === 'In Progress') statusClass = 'progress';
        if (item.status === 'Blocked') statusClass = 'blocked';
        if (item.status === 'Done') statusClass = 'done';
        html += `
            <tr>
                <td><strong>${jiraKeyLink(item.key)}</strong></td>
                <td>${jiraKeyLink(item.parent_key)}</td>
                <td>${item.assignee || '--'}</td>
                <td><span class="status-badge status-${statusClass}">${item.status}</span></td>
                <td><span class="cell-summary">${escapeHTML(item.summary || '')}</span></td>
                <td>${formatDate(item.created_at)}</td>
                <td>${formatDate(item.updated_at)}</td>
                <td>${formatDate(item.due_date)}</td>
            </tr>
        `;
    });
    html += '</tbody></table>';
    return html;
}

function formatDate(dateStr) {
    if (!dateStr) return '--';
    // Parseia como local (evita shift de timezone com datas ISO sem horário)
    const parts = dateStr.split('T')[0].split('-');
    if (parts.length === 3) {
        return `${parts[2]}/${parts[1]}/${parts[0]}`;
    }
    return dateStr;
}

function escapeHTML(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, tag => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[tag] || tag));
}


// --- Validation Settings Modal ---

let validationRules = [];

window.openValidationSettings = async function() {
    const modal = document.getElementById('validationModal');
    const body = document.getElementById('validationModalBody');
    const status = document.getElementById('saveStatus');

    modal.style.display = 'flex';
    setTimeout(() => modal.classList.add('active'), 10);
    body.innerHTML = '<p>Carregando...</p>';
    status.textContent = '';

    try {
        const r = await fetch('/api/settings/validations');
        validationRules = await r.json();
        renderValidationRules();
    } catch (e) {
        body.innerHTML = '<p style="color:#f87171;">Erro ao carregar validações.</p>';
    }
};

window.closeValidationModal = function(e) {
    if (e && e.target !== e.currentTarget && !e.target.classList.contains('close-btn')) return;
    const modal = document.getElementById('validationModal');
    modal.classList.remove('active');
    setTimeout(() => { modal.style.display = 'none'; }, 300);
};

function renderValidationRules() {
    const body = document.getElementById('validationModalBody');

    let html = '<div class="validation-rules-list">';
    validationRules.forEach((rule, idx) => {
        html += `
            <div class="validation-rule-card">
                <div class="rule-header">
                    <label class="toggle-switch">
                        <input type="checkbox" id="rule-enabled-${idx}" ${rule.enabled ? 'checked' : ''}>
                        <span class="toggle-slider"></span>
                    </label>
                    <input type="text" class="rule-name-input" id="rule-name-${idx}" value="${escapeHTML(rule.name)}">
                </div>
                <div class="rule-fields">
                    <label class="rule-field-label">Descrição</label>
                    <textarea class="rule-desc-input" id="rule-desc-${idx}" rows="2">${escapeHTML(rule.description || '')}</textarea>
                    <label class="rule-field-label">Status avaliados (separados por vírgula)</label>
                    <input type="text" class="rule-statuses-input" id="rule-statuses-${idx}" value="${escapeHTML(rule.statuses)}">
                </div>
            </div>
        `;
    });
    html += '</div>';
    body.innerHTML = html;
}

window.saveAllValidations = async function() {
    const status = document.getElementById('saveStatus');
    const btn = document.querySelector('.btn-modal-save');

    btn.disabled = true;
    btn.textContent = 'Salvando...';
    status.textContent = '';
    status.className = 'save-status';

    let errors = 0;

    for (let idx = 0; idx < validationRules.length; idx++) {
        const rule = validationRules[idx];
        const enabled = document.getElementById(`rule-enabled-${idx}`).checked;
        const name = document.getElementById(`rule-name-${idx}`).value.trim();
        const description = document.getElementById(`rule-desc-${idx}`).value.trim();
        const statuses = document.getElementById(`rule-statuses-${idx}`).value.trim();

        try {
            await fetch(`/api/settings/validations/${rule.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled, name, description, statuses })
            });
        } catch (e) {
            errors++;
        }
    }

    btn.disabled = false;
    btn.textContent = 'Salvar';

    if (errors === 0) {
        status.textContent = '✓ Salvo com sucesso';
        status.className = 'save-status success';
    } else {
        status.textContent = `✗ ${errors} erro(s) ao salvar`;
        status.className = 'save-status error';
    }

    // Hot reload: recarrega inconsistências com dados atualizados
    const projectKey = document.getElementById('projectFilter').value;
    if (projectKey) onProjectChange();

    // Remove mensagem após 3s
    setTimeout(() => { status.textContent = ''; }, 3000);
};

window.toggleValidation = null;
window.saveValidationField = null;
