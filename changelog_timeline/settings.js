// Settings - Blacklist CRUD + Projects Sync (novo modelo 3 pipelines)
const API_BASE = '/api/settings/blacklist';
const API_PROJECTS = '/api/settings/projects';

let rules = [];
let projects = [];
let pollInterval = null;

document.addEventListener('DOMContentLoaded', () => {
    loadRules();
    loadProjects();
    loadPurgeStatus();
    bindEvents();
});

function bindEvents() {
    document.getElementById('btnAddRule').addEventListener('click', addRule);
    document.getElementById('newRuleValue').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') addRule();
    });
    document.getElementById('btnSyncAll').addEventListener('click', () => startSync(null));

    // Adicionar Projeto
    document.getElementById('btnToggleAddProject').addEventListener('click', toggleAddProjectForm);
    document.getElementById('btnCancelAddProject').addEventListener('click', hideAddProjectForm);
    document.getElementById('btnSaveProject').addEventListener('click', saveProject);
    ['projJql', 'projActive'].forEach(id => {
        document.getElementById(id).addEventListener('input', updateJqlPreview);
    });
}

// ==================== ADD PROJECT ====================

const DEFAULT_ACTIVE = 'In Progress, Blocked, Test, Waiting for Delivery';
const DEFAULT_EXCLUDE = 'Canceled, Reject, Open, To do, Backlog, Refinement';

function toggleAddProjectForm() {
    const form = document.getElementById('add-project-form');
    if (form.style.display === 'none') {
        form.style.display = 'block';
        updateJqlPreview();
        document.getElementById('projKey').focus();
    } else {
        hideAddProjectForm();
    }
}

function hideAddProjectForm() {
    const form = document.getElementById('add-project-form');
    form.style.display = 'none';
    ['projKey', 'projName', 'projJql', 'projActive', 'projExclude'].forEach(id => {
        document.getElementById(id).value = '';
    });
}

function parseCsvStatuses(raw, fallbackCsv) {
    const source = (raw && raw.trim()) ? raw : fallbackCsv;
    return source.split(',').map(s => s.trim()).filter(Boolean);
}

function updateJqlPreview() {
    const jqlProject = document.getElementById('projJql').value.trim();
    const activeStatuses = parseCsvStatuses(document.getElementById('projActive').value, DEFAULT_ACTIVE);
    const base = jqlProject || 'project = ...';
    const statusList = activeStatuses.map(s => `"${s}"`).join(', ');

    document.getElementById('preview-active').textContent = `${base} AND (status in (${statusList}) OR (issuetype in subTaskIssueTypes() AND status in (${statusList})))`;
    document.getElementById('preview-done').textContent = `${base} AND status = Done AND resolved >= -26w`;
    document.getElementById('preview-delta').textContent = `${base} AND updated >= -10d`;
}

async function saveProject() {
    const key = document.getElementById('projKey').value.trim();
    const name = document.getElementById('projName').value.trim();
    const jqlProject = document.getElementById('projJql').value.trim();

    if (!key) { showToast('Informe a key do projeto', 'error'); document.getElementById('projKey').focus(); return; }
    if (!name) { showToast('Informe o nome do projeto', 'error'); document.getElementById('projName').focus(); return; }
    if (!jqlProject) { showToast('Informe a cláusula de projeto (JQL)', 'error'); document.getElementById('projJql').focus(); return; }

    const payload = {
        key,
        name,
        jql_project: jqlProject,
        active_statuses: parseCsvStatuses(document.getElementById('projActive').value, DEFAULT_ACTIVE),
        exclude_statuses: parseCsvStatuses(document.getElementById('projExclude').value, DEFAULT_EXCLUDE),
    };

    const btn = document.getElementById('btnSaveProject');
    btn.disabled = true;
    try {
        const response = await fetch(API_PROJECTS, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) {
            showToast(data.detail || 'Erro ao adicionar projeto', 'error');
            return;
        }
        showToast(`Projeto ${key} adicionado`, 'success');
        hideAddProjectForm();
        await loadProjects();
    } catch (error) {
        showToast('Erro de conexão ao adicionar projeto', 'error');
    } finally {
        btn.disabled = false;
    }
}

window.deleteProject = async function(key) {
    if (!confirm(`Remover o projeto "${key}" da configuração?\n\nIsso NÃO apaga os dados já coletados no banco — apenas remove o projeto do projects.yaml.`)) return;
    try {
        const response = await fetch(`${API_PROJECTS}/${encodeURIComponent(key)}`, { method: 'DELETE' });
        const data = await response.json();
        if (!response.ok) {
            showToast(data.detail || 'Erro ao remover projeto', 'error');
            return;
        }
        showToast(`Projeto ${key} removido da configuração`, 'success');
        await loadProjects();
    } catch (error) {
        showToast('Erro de conexão ao remover projeto', 'error');
    }
};

window.purgeProjectData = async function(key) {
    // 1. Busca o preview do que seria removido
    let stats;
    try {
        const res = await fetch(`${API_PROJECTS}/${encodeURIComponent(key)}/data-stats`);
        stats = await res.json();
        if (!res.ok) { showToast(stats.detail || 'Erro ao consultar dados', 'error'); return; }
    } catch (error) {
        showToast('Erro de conexão ao consultar dados', 'error');
        return;
    }

    if (!stats.has_data) {
        showToast(`Nenhum dado no banco para "${key}"`, 'success');
        return;
    }

    // 2. Confirmação forte com as contagens exatas
    const msg =
        `APAGAR os dados do projeto "${key}" do banco?\n\n` +
        `Serão removidos:\n` +
        `  • ${stats.issues.toLocaleString('pt-BR')} issues\n` +
        `  • ${stats.changelogs.toLocaleString('pt-BR')} eventos de changelog\n` +
        `  • ${stats.metrics.toLocaleString('pt-BR')} registros de métricas\n\n` +
        `Esta ação é IRREVERSÍVEL. A configuração (projects.yaml) NÃO é alterada — ` +
        `você poderá recoletar os dados via "Atualizar".\n\nConfirmar?`;
    if (!confirm(msg)) return;

    // 3. Executa a remoção
    try {
        const res = await fetch(`${API_PROJECTS}/${encodeURIComponent(key)}/data`, { method: 'DELETE' });
        const data = await res.json();
        if (!res.ok) { showToast(data.detail || 'Erro ao apagar dados', 'error'); return; }
        showToast(`Dados de ${key} removidos: ${data.issues_removed} issues, ${data.changelogs_removed} changelogs`, 'success');
        await loadProjects();
    } catch (error) {
        showToast('Erro de conexão ao apagar dados', 'error');
    }
};

// ==================== PROJECTS ====================

async function loadProjects() {
    try {
        const response = await fetch(API_PROJECTS);
        projects = await response.json();
        renderProjects();
        checkSyncStatus();
    } catch (error) {
        console.error('Erro ao carregar projetos:', error);
        document.getElementById('projects-list').innerHTML = '<p class="empty-state">Erro ao carregar projetos</p>';
    }
}

function renderProjects() {
    const container = document.getElementById('projects-list');

    if (projects.length === 0) {
        container.innerHTML = '<p class="empty-state">Nenhum projeto configurado em projects.yaml</p>';
        return;
    }

    container.innerHTML = projects.map(p => {
        const sync = p.last_sync;
        let syncInfo = '';

        if (sync) {
            const date = new Date(sync.date).toLocaleString('pt-BR');
            syncInfo = `
                <div class="project-sync-info">
                    <span class="sync-meta"><strong>Última sync:</strong> ${date}</span>
                    <span class="sync-meta"><strong>Duração:</strong> ${formatSyncDuration(sync.duration_seconds)}</span>
                    <span class="sync-meta"><strong>Issues:</strong> ${(sync.issues_inserted + sync.issues_updated).toLocaleString('pt-BR')} (${sync.issues_inserted} novos · ${sync.issues_updated} atualizados)</span>
                    <span class="sync-meta"><strong>Changelogs:</strong> ${sync.changelogs_count.toLocaleString('pt-BR')}</span>
                </div>
            `;
        } else {
            syncInfo = '<div class="project-sync-info"><span class="sync-meta muted">Nunca sincronizado</span></div>';
        }

        // Pipelines expandíveis
        const pipelines = p.pipelines || {};
        let pipelinesHtml = '';
        for (const [pipeKey, pipe] of Object.entries(pipelines)) {
            pipelinesHtml += `
                <div class="pipeline-item">
                    <span class="pipeline-name">${escapeHTML(pipe.name || pipeKey)}</span>
                    <code class="pipeline-jql">${escapeHTML(pipe.jql || '')}</code>
                </div>
            `;
        }

        return `
            <div class="project-card" id="project-card-${p.key}">
                <div class="project-card-header">
                    <div class="project-info">
                        <span class="project-key">${escapeHTML(p.key)}</span>
                        <span class="project-name">${escapeHTML(p.name)}</span>
                        ${syncInfo}
                    </div>
                    <div class="project-actions">
                        <button class="btn-sync" onclick="startSync('${p.key}')">Atualizar</button>
                        <button class="btn-purge-project" onclick="purgeProjectData('${escapeHTML(p.key)}')" title="Apagar os dados coletados deste projeto no banco">Limpar dados</button>
                        <button class="btn-remove-project" onclick="deleteProject('${escapeHTML(p.key)}')" title="Remover apenas da configuração (projects.yaml)">Remover</button>
                    </div>
                </div>
                <details class="pipelines-details">
                    <summary class="pipelines-toggle">Pipelines</summary>
                    <div class="pipelines-content">
                        ${pipelinesHtml}
                    </div>
                </details>
            </div>
        `;
    }).join('');
}

function formatSyncDuration(seconds) {
    if (!seconds) return '--';
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const min = Math.floor(seconds / 60);
    const sec = Math.round(seconds % 60);
    return `${min}m ${sec}s`;
}

// ==================== SYNC ====================

async function startSync(projectKey) {
    const body = {
        project_keys: projectKey ? [projectKey] : null,
        mode: "delta"
    };

    try {
        const response = await fetch(`${API_PROJECTS}/sync`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (response.status === 409) {
            showToast('Sincronização já em andamento', 'error');
            return;
        }

        if (!response.ok) {
            const err = await response.json();
            showToast(err.detail || 'Erro ao iniciar sync', 'error');
            return;
        }

        showToast('Sincronização iniciada', 'success');
        setSyncUI(true);
        startPolling();
    } catch (error) {
        console.error('Erro ao iniciar sync:', error);
        showToast('Erro de conexão', 'error');
    }
}

window.cancelSync = async function() {
    try {
        const response = await fetch(`${API_PROJECTS}/sync/cancel`, { method: 'POST' });
        if (response.ok) {
            showToast('Cancelamento solicitado', 'success');
            const btn = document.getElementById('btnCancelSync');
            if (btn) {
                btn.disabled = true;
                btn.textContent = 'Cancelando...';
            }
        } else {
            const err = await response.json();
            showToast(err.detail || 'Erro ao cancelar', 'error');
        }
    } catch (error) {
        showToast('Erro de conexão', 'error');
    }
};

function setSyncUI(running) {
    const btnAll = document.getElementById('btnSyncAll');
    const btnCancel = document.getElementById('btnCancelSync');
    const logContainer = document.getElementById('sync-log-container');
    const badge = document.getElementById('sync-status-badge');

    if (running) {
        btnAll.disabled = true;
        btnAll.textContent = 'Sincronizando...';
        btnCancel.style.display = 'inline-block';
        btnCancel.disabled = false;
        btnCancel.textContent = 'Cancelar';
        logContainer.style.display = 'block';
        badge.className = 'sync-status-badge running';
        badge.textContent = 'Em execução';
        document.querySelectorAll('.btn-sync').forEach(btn => btn.disabled = true);
    } else {
        btnAll.disabled = false;
        btnAll.textContent = 'Atualizar Todos';
        btnCancel.style.display = 'none';
        badge.className = 'sync-status-badge completed';
        badge.textContent = 'Concluído';
        document.querySelectorAll('.btn-sync').forEach(btn => btn.disabled = false);
    }
}

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(pollSyncStatus, 2000);
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

async function checkSyncStatus() {
    try {
        const response = await fetch(`${API_PROJECTS}/sync/status`);
        const status = await response.json();
        if (status.running) {
            setSyncUI(true);
            renderSyncLog(status);
            startPolling();
        }
    } catch (error) {
        // Ignora
    }
}

async function pollSyncStatus() {
    try {
        const response = await fetch(`${API_PROJECTS}/sync/status`);
        const status = await response.json();
        renderSyncLog(status);
        updateProjectCards(status);

        if (!status.running) {
            stopPolling();
            setSyncUI(false);
            showToast('Sincronização concluída', 'success');
            await loadProjects();
        }
    } catch (error) {
        console.error('Erro no polling:', error);
        stopPolling();
        setSyncUI(false);
    }
}

function renderSyncLog(status) {
    const logEl = document.getElementById('sync-log');

    logEl.innerHTML = status.progress.map(line => {
        let cls = '';
        if (line.includes('concluído') || line.includes('finalizada') || line.includes('\u2713')) cls = 'success';
        else if (line.includes('ERRO') || line.includes('cancelad')) cls = 'error';
        else if (line.includes('Pipeline:') || line.includes('Extraindo') || line.includes('Ingest')) cls = 'info';
        return `<div class="log-line ${cls}">${escapeHTML(line)}</div>`;
    }).join('');

    logEl.scrollTop = logEl.scrollHeight;
}

function updateProjectCards(status) {
    document.querySelectorAll('.project-card').forEach(card => {
        card.classList.remove('syncing', 'done');
    });

    if (status.current_project) {
        const card = document.getElementById(`project-card-${status.current_project}`);
        if (card) card.classList.add('syncing');
    }

    status.completed.forEach(key => {
        const card = document.getElementById(`project-card-${key}`);
        if (card) card.classList.add('done');
    });
}

// ==================== BLACKLIST ====================

async function loadRules() {
    try {
        const response = await fetch(API_BASE);
        rules = await response.json();
        renderRules();
    } catch (error) {
        console.error('Erro ao carregar regras:', error);
        showToast('Erro ao carregar regras', 'error');
    }
}

function renderRules() {
    const authorRules = rules.filter(r => r.type === 'author');
    const fieldRules = rules.filter(r => r.type === 'field');
    renderTable('author-rules-body', authorRules);
    renderTable('field-rules-body', fieldRules);
}

function renderTable(tbodyId, items) {
    const tbody = document.getElementById(tbodyId);

    if (items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" class="empty-state">Nenhuma regra cadastrada</td></tr>';
        return;
    }

    tbody.innerHTML = items.map(rule => `
        <tr>
            <td>${escapeHTML(rule.value)}</td>
            <td>
                <button class="btn btn-toggle ${rule.enabled ? 'enabled' : 'disabled'}" 
                        onclick="toggleRule(${rule.id}, ${rule.enabled})">
                    ${rule.enabled ? 'Ativo' : 'Inativo'}
                </button>
            </td>
            <td class="actions-cell">
                <button class="btn btn-delete" onclick="deleteRule(${rule.id})">Excluir</button>
            </td>
        </tr>
    `).join('');
}

async function addRule() {
    const typeEl = document.getElementById('newRuleType');
    const valueEl = document.getElementById('newRuleValue');
    const type = typeEl.value;
    const value = valueEl.value.trim();

    if (!value) {
        showToast('Informe o valor da regra', 'error');
        valueEl.focus();
        return;
    }

    try {
        const response = await fetch(API_BASE, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ type, value })
        });

        if (response.status === 409) {
            showToast('Essa regra já existe', 'error');
            return;
        }

        if (!response.ok) {
            const err = await response.json();
            showToast(err.detail || 'Erro ao criar regra', 'error');
            return;
        }

        valueEl.value = '';
        showToast('Regra adicionada', 'success');
        await loadRules();
    } catch (error) {
        console.error('Erro ao adicionar regra:', error);
        showToast('Erro de conexão', 'error');
    }
}

window.toggleRule = async function(id, currentEnabled) {
    try {
        const response = await fetch(`${API_BASE}/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: !currentEnabled })
        });

        if (!response.ok) {
            showToast('Erro ao atualizar regra', 'error');
            return;
        }

        showToast(currentEnabled ? 'Regra desativada' : 'Regra ativada', 'success');
        await loadRules();
    } catch (error) {
        console.error('Erro ao toggle regra:', error);
        showToast('Erro de conexão', 'error');
    }
};

window.deleteRule = async function(id) {
    if (!confirm('Tem certeza que deseja excluir esta regra?')) return;

    try {
        const response = await fetch(`${API_BASE}/${id}`, { method: 'DELETE' });

        if (!response.ok) {
            showToast('Erro ao excluir regra', 'error');
            return;
        }

        showToast('Regra excluída', 'success');
        await loadRules();
    } catch (error) {
        console.error('Erro ao excluir regra:', error);
        showToast('Erro de conexão', 'error');
    }
};

// ==================== PURGE (EXPURGO) ====================

async function loadPurgeStatus() {
    try {
        const response = await fetch('/api/settings/purge/status');
        const data = await response.json();
        renderPurgeCard(data);
    } catch (error) {
        console.error('Erro ao carregar status do expurgo:', error);
    }
    loadPurgeHistory();
}

// Recarrega o historico e leva a atencao do usuario ate a tabela (apos um expurgo),
// destacando a linha mais recente — e para onde vai o "changelog da execucao".
async function focusPurgeHistory() {
    await loadPurgeHistory();
    const wrap = document.querySelector('.purge-history-wrap');
    const firstRow = document.querySelector('#purge-history-body tr');
    if (wrap) wrap.scrollIntoView({ behavior: 'smooth', block: 'center' });
    if (firstRow) {
        firstRow.classList.add('row-flash');
        setTimeout(() => firstRow.classList.remove('row-flash'), 2200);
    }
}

async function loadPurgeHistory() {
    const tbody = document.getElementById('purge-history-body');
    if (!tbody) return;
    try {
        const res = await fetch('/api/settings/purge/history');
        const rows = await res.json();
        if (!rows || rows.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Nenhum expurgo executado ainda.</td></tr>`;
            return;
        }
        const fmtDT = (s) => { try { return new Date(s).toLocaleString('pt-BR'); } catch (e) { return s || '--'; } };
        const fmtCut = (s) => s ? (String(s).split('T')[0].split('-').reverse().join('/')) : '--';
        const scopeLabel = (sc) => sc === 'filtered'
            ? '<span class="status-badge" style="background:var(--warn-bg);color:var(--warn)">Filtrado</span>'
            : '<span class="status-badge" style="background:var(--action-quiet);color:var(--action)">Tudo</span>';
        tbody.innerHTML = rows.map(r => {
            const sample = r.sample_keys ? escapeHTML(r.sample_keys.split(',').slice(0, 5).join(', ')) + (r.sample_keys.split(',').length > 5 ? ' …' : '') : '--';
            return `<tr>
                <td>${fmtDT(r.executed_at)}</td>
                <td>${scopeLabel(r.scope)}</td>
                <td>${(r.issues_removed || 0).toLocaleString('pt-BR')}</td>
                <td>${(r.changelogs_removed || 0).toLocaleString('pt-BR')}</td>
                <td>${fmtCut(r.cutoff_date)}</td>
                <td style="color:var(--text-2);font-size:0.78rem">${sample}</td>
            </tr>`;
        }).join('');
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="6" class="empty-state">Erro ao carregar histórico</td></tr>`;
    }
}

function renderPurgeCard(data) {
    const card = document.getElementById('purge-card');
    const info = document.getElementById('purge-info');
    const btn = document.getElementById('btnPurge');

    let html = '';

    if (data.last_purge) {
        const date = new Date(data.last_purge.date).toLocaleString('pt-BR');
        const daysText = data.days_since !== null ? `há ${data.days_since} dia(s)` : '';
        html += `<span class="purge-meta"><strong>Último expurgo:</strong> ${date} (${daysText})</span>`;
        html += `<span class="purge-meta"><strong>Removidos:</strong> ${data.last_purge.issues_removed} issues, ${data.last_purge.changelogs_removed} changelogs</span>`;
    } else {
        html += `<span class="purge-meta muted">Nenhum expurgo executado ainda</span>`;
    }

    const hasItemsToPurge = data.estimated.issues > 0;

    if (hasItemsToPurge) {
        html += `<span class="purge-meta"><strong>Estimativa:</strong> ${data.estimated.issues} issues e ${data.estimated.changelogs.toLocaleString('pt-BR')} changelogs para expurgar</span>`;
    }

    if (hasItemsToPurge && data.recommended) {
        html += `<span class="purge-badge warn">Recomendado</span>`;
        card.classList.add('warning');
        card.classList.remove('ok');
        btn.style.display = 'inline-block';
    } else {
        html += `<span class="purge-badge ok">Em dia — nada para expurgar</span>`;
        card.classList.remove('warning');
        card.classList.add('ok');
        btn.style.display = 'none';
    }

    info.innerHTML = html;
}

// ==================== PREVIEW DO EXPURGO (detalhamento) ====================
// Lista as issues que serao removidas, com tabela + filtros no padrao do dashboard.

const purgeState = {
    all: [],
    filtered: [],
    page: 1,
    pageSize: 15,
    sort: { col: null, dir: 'asc' },
    open: false,
};
const PURGE_JIRA = 'https://jiraps.atlassian.net/browse/';

function purgeFmtDate(s) {
    if (!s) return '--';
    const p = String(s).split('T')[0].split('-');
    return p.length === 3 ? `${p[2]}/${p[1]}/${p[0]}` : s;
}

// Classe de cor do badge de status (mesmo sistema da coluna Status).
function purgeStatusClass(status) {
    switch (status) {
        case 'Done': case 'Resolved': return 'status-done';
        case 'In Progress': return 'status-progress';
        case 'Blocked': return 'status-blocked';
        case 'Test': return 'status-test';
        case 'Waiting for Delivery': return 'status-waiting';
        default: return 'status-open';
    }
}

// Renderiza o badge de status (ou '--' quando vazio).
function purgeStatusBadge(status) {
    if (!status) return '--';
    return `<span class="status-badge ${purgeStatusClass(status)}">${escapeHTML(status)}</span>`;
}

window.togglePurgePreview = async function() {
    const panel = document.getElementById('purge-detail');
    const btn = document.getElementById('btnPurgePreview');
    if (purgeState.open) {
        purgeState.open = false;
        panel.style.display = 'none';
        panel.innerHTML = '';
        btn.textContent = 'Ver issues que serão removidas';
        return;
    }
    btn.disabled = true;
    try {
        const res = await fetch('/api/settings/purge/preview');
        const data = await res.json();
        purgeState.all = data.issues || [];
    } catch (e) {
        showToast('Erro ao carregar issues do expurgo', 'error');
        btn.disabled = false;
        return;
    }
    btn.disabled = false;
    purgeState.open = true;
    btn.textContent = 'Ocultar lista';
    panel.style.display = 'block';
    renderPurgeDetail();
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
};

function purgeUniq(vals) { return [...new Set(vals.filter(v => v !== '' && v != null))].sort(); }

function purgeSel(type) {
    return Array.from(document.querySelectorAll(`#purge-detail .${type}-check:checked`)).map(cb => cb.value);
}

function purgeApplyFilters() {
    const search = (document.getElementById('purgeSearch') || {}).value?.toLowerCase() || '';
    const projects = purgeSel('pproject');
    const assignees = purgeSel('passignee');
    purgeState.filtered = purgeState.all.filter(i => {
        if (search && !i.key.toLowerCase().includes(search)) return false;
        if (projects.length && !projects.includes(i.project_key)) return false;
        if (assignees.length && !assignees.includes(i.assignee)) return false;
        return true;
    });
    purgeState.page = 1;
    renderPurgeDetailBody();
}
window.purgeApplyFilters = purgeApplyFilters;

window.purgeToggleDropdown = function(id) {
    document.getElementById(id).classList.toggle('open');
};

window.purgeUpdateHeader = function(type) {
    const checked = document.querySelectorAll(`#purge-detail .${type}-check:checked`);
    const header = document.querySelector(`#purge-${type}-multiselect .multiselect-header`);
    const labels = { pproject: 'Projeto', passignee: 'Assignee' };
    header.innerHTML = '';
    if (checked.length === 0) {
        header.innerHTML = `<span class="placeholder-text">${labels[type]}: Todos</span>`;
    } else {
        checked.forEach(cb => {
            const tag = document.createElement('span');
            tag.className = 'multiselect-tag';
            tag.innerHTML = `${escapeHTML(cb.value)} <span class="tag-remove" onclick="purgeRemoveTag(event,'${type}','${escapeHTML(cb.value)}')">×</span>`;
            header.appendChild(tag);
        });
    }
};

window.purgeRemoveTag = function(event, type, value) {
    event.stopPropagation();
    const cb = document.querySelector(`#purge-detail .${type}-check[value="${value}"]`);
    if (cb) { cb.checked = false; purgeUpdateHeader(type); purgeApplyFilters(); }
};

window.purgeClearFilters = function() {
    const s = document.getElementById('purgeSearch'); if (s) s.value = '';
    document.querySelectorAll('#purge-detail .pproject-check, #purge-detail .passignee-check').forEach(cb => cb.checked = false);
    purgeUpdateHeader('pproject'); purgeUpdateHeader('passignee');
    purgeApplyFilters();
};

window.purgeSort = function(col) {
    const s = purgeState.sort;
    if (s.col === col) s.dir = s.dir === 'asc' ? 'desc' : 'asc';
    else { s.col = col; s.dir = 'asc'; }
    renderPurgeDetailBody();
};

function purgeSortedRows() {
    const { col, dir } = purgeState.sort;
    if (!col) return purgeState.filtered;
    return purgeState.filtered.slice().sort((a, b) => {
        const c = String(a[col] == null ? '' : a[col]).localeCompare(String(b[col] == null ? '' : b[col]), 'pt-BR', { numeric: true });
        return dir === 'asc' ? c : -c;
    });
}

window.purgePage = function(delta) {
    purgeState.page += delta;
    renderPurgeDetailBody();
};

function purgeDropdown(type, label, options) {
    const items = options.length
        ? options.map(o => `<label><input type="checkbox" value="${escapeHTML(o)}" class="${type}-check" onchange="purgeUpdateHeader('${type}'); purgeApplyFilters();"> ${escapeHTML(o)}</label>`).join('')
        : '<label class="empty-state" style="padding:.4rem .7rem">Sem opções</label>';
    return `<div class="custom-multiselect" id="purge-${type}-multiselect">
        <div class="multiselect-header" onclick="purgeToggleDropdown('purge-${type}-dropdown')"><span class="placeholder-text">${label}: Todos</span></div>
        <div class="multiselect-options" id="purge-${type}-dropdown">${items}</div>
    </div>`;
}

window.purgeFiltered = async function() {
    const keys = purgeState.filtered.map(i => i.key);
    if (!keys.length) { showToast('Nenhuma issue no filtro atual', 'error'); return; }

    const msg = `Expurgar as ${keys.length.toLocaleString('pt-BR')} issue(s) atualmente filtradas?\n\n` +
        `Serão apagadas PERMANENTEMENTE do banco (issues, changelogs e métricas). ` +
        `Subtasks cujo pai permaneça no banco são ignoradas por segurança.\n\nConfirmar?`;
    if (!confirm(msg)) return;

    const btn = document.getElementById('btnPurgeFiltered');
    btn.disabled = true; btn.textContent = 'Expurgando...';
    try {
        const res = await fetch('/api/settings/purge/selected', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keys }),
        });
        const data = await res.json();
        if (!res.ok) { showToast(data.detail || 'Erro no expurgo', 'error'); return; }
        let txt = `Expurgo concluído: ${data.issues_removed} issue(s) removida(s). Registrado no Histórico de Expurgos abaixo.`;
        if (data.skipped && data.skipped.length) txt += ` · ${data.skipped.length} ignorada(s) (pai vivo)`;
        showToast(txt, 'success');
        // Fecha o painel e atualiza o status (dados obsoletos).
        const panel = document.getElementById('purge-detail');
        panel.style.display = 'none'; panel.innerHTML = '';
        purgeState.open = false;
        const pbtn = document.getElementById('btnPurgePreview');
        if (pbtn) pbtn.textContent = 'Ver issues que serão removidas';
        await loadPurgeStatus();
        await focusPurgeHistory();
    } catch (e) {
        showToast('Erro de conexão', 'error');
    } finally {
        if (document.getElementById('btnPurgeFiltered')) { btn.disabled = false; btn.textContent = 'Expurgar filtradas'; }
    }
};

function renderPurgeDetail() {
    const panel = document.getElementById('purge-detail');
    const total = purgeState.all.length;
    if (!total) {
        panel.innerHTML = `<div class="data-section glass"><p class="empty-state">Nenhuma issue sera removida com o criterio atual.</p></div>`;
        return;
    }
    const projects = purgeUniq(purgeState.all.map(i => i.project_key));
    const assignees = purgeUniq(purgeState.all.map(i => i.assignee));
    panel.innerHTML = `
        <div class="data-section glass">
            <div class="table-header">
                <h3>Issues que serão removidas (${total})</h3>
                <div style="display:flex;gap:0.5rem;align-items:center;flex-wrap:wrap">
                    <input type="text" id="purgeSearch" placeholder="Pesquisar chave..." class="filter-input" style="width:220px" oninput="purgeApplyFilters()">
                    <button class="btn btn-purge" id="btnPurgeFiltered" onclick="purgeFiltered()">Expurgar filtradas</button>
                </div>
            </div>
            <div class="table-filters toolbar-glass">
                <div class="toolbar-label">Filtros</div>
                ${purgeDropdown('pproject', 'Projeto', projects)}
                ${purgeDropdown('passignee', 'Assignee', assignees)}
                <button class="btn-clear" onclick="purgeClearFilters()">Limpar</button>
            </div>
            <div class="table-wrapper">
                <table class="data-table" id="purge-table">
                    <thead><tr>
                        <th class="sortable" onclick="purgeSort('key')">Key <span class="sort-ind">↕</span></th>
                        <th class="sortable" onclick="purgeSort('parent_key')">Parent <span class="sort-ind">↕</span></th>
                        <th class="sortable" onclick="purgeSort('parent_status')">Parent Status <span class="sort-ind">↕</span></th>
                        <th class="sortable" onclick="purgeSort('assignee')">Assignee <span class="sort-ind">↕</span></th>
                        <th class="sortable" onclick="purgeSort('summary')">Summary <span class="sort-ind">↕</span></th>
                        <th class="sortable" onclick="purgeSort('status')">Status <span class="sort-ind">↕</span></th>
                        <th class="sortable" onclick="purgeSort('created_at')">Created <span class="sort-ind">↕</span></th>
                        <th class="sortable" onclick="purgeSort('due_date')">Due Date <span class="sort-ind">↕</span></th>
                        <th class="sortable" onclick="purgeSort('updated_at')">Updated <span class="sort-ind">↕</span></th>
                        <th class="sortable" onclick="purgeSort('resolved_at')">Resolved <span class="sort-ind">↕</span></th>
                    </tr></thead>
                    <tbody id="purge-tbody"></tbody>
                </table>
            </div>
            <div class="pagination">
                <button id="purge-prev" onclick="purgePage(-1)" disabled>Anterior</button>
                <span id="purge-pageinfo">Página 1 de X</span>
                <button id="purge-next" onclick="purgePage(1)">Próxima</button>
            </div>
        </div>`;
    purgeState.filtered = purgeState.all.slice();
    renderPurgeDetailBody();
    // Fecha dropdowns ao clicar fora
    panel.addEventListener('click', (e) => {
        if (!e.target.closest('.custom-multiselect')) {
            panel.querySelectorAll('.multiselect-options').forEach(el => el.classList.remove('open'));
        }
    });
}

function renderPurgeDetailBody() {
    const tbody = document.getElementById('purge-tbody');
    if (!tbody) return;
    const rows = purgeSortedRows();
    const total = rows.length;
    const maxP = Math.max(1, Math.ceil(total / purgeState.pageSize));
    if (purgeState.page > maxP) purgeState.page = maxP;
    const start = (purgeState.page - 1) * purgeState.pageSize;
    const pageRows = rows.slice(start, start + purgeState.pageSize);

    document.querySelectorAll('#purge-table th.sortable').forEach(th => {
        const ind = th.querySelector('.sort-ind');
        const onclick = th.getAttribute('onclick') || '';
        const col = onclick.replace("purgeSort('", '').replace("')", '');
        ind.textContent = col === purgeState.sort.col ? (purgeState.sort.dir === 'asc' ? '↑' : '↓') : '↕';
    });

    if (!pageRows.length) {
        tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;padding:1.5rem">Nenhuma issue no filtro atual.</td></tr>`;
    } else {
        tbody.innerHTML = pageRows.map(i => `<tr>
            <td><strong><a href="${PURGE_JIRA}${encodeURIComponent(i.key)}" target="_blank" rel="noopener" style="color:var(--brand-blue);text-decoration:none">${escapeHTML(i.key)}</a></strong></td>
            <td>${i.parent_key ? `<a href="${PURGE_JIRA}${encodeURIComponent(i.parent_key)}" target="_blank" rel="noopener" style="color:var(--brand-blue);text-decoration:none">${escapeHTML(i.parent_key)}</a>` : '--'}</td>
            <td>${purgeStatusBadge(i.parent_status)}</td>
            <td>${escapeHTML(i.assignee || '--')}</td>
            <td class="cell-summary" title="${escapeHTML(i.summary)}">${escapeHTML(i.summary)}</td>
            <td>${purgeStatusBadge(i.status)}</td>
            <td>${purgeFmtDate(i.created_at)}</td>
            <td>${purgeFmtDate(i.due_date)}</td>
            <td>${purgeFmtDate(i.updated_at)}</td>
            <td>${purgeFmtDate(i.resolved_at)}</td>
        </tr>`).join('');
    }

    document.getElementById('purge-pageinfo').textContent = `Página ${purgeState.page} de ${maxP}`;
    document.getElementById('purge-prev').disabled = purgeState.page <= 1;
    document.getElementById('purge-next').disabled = purgeState.page >= maxP;

    // Atualiza o label do botao com a contagem filtrada atual.
    const fbtn = document.getElementById('btnPurgeFiltered');
    if (fbtn) {
        fbtn.textContent = `Expurgar filtradas (${total})`;
        fbtn.disabled = total === 0;
    }
}

window.executePurge = async function() {
    const btn = document.getElementById('btnPurge');

    if (!confirm('Isso vai remover permanentemente issues Done com mais de 6 meses do banco. Confirma?')) return;

    btn.disabled = true;
    btn.textContent = 'Expurgando...';

    try {
        const response = await fetch('/api/settings/purge', { method: 'POST' });
        const data = await response.json();

        if (response.ok) {
            showToast(`Expurgo concluído: ${data.issues_removed} issues removidas. Registrado no Histórico de Expurgos abaixo.`, 'success');
            // Fecha/limpa o painel de detalhamento (dados agora obsoletos).
            const panel = document.getElementById('purge-detail');
            if (panel) { panel.style.display = 'none'; panel.innerHTML = ''; }
            purgeState.open = false;
            const pbtn = document.getElementById('btnPurgePreview');
            if (pbtn) pbtn.textContent = 'Ver issues que serão removidas';
            await loadPurgeStatus();
            await focusPurgeHistory();
        } else {
            showToast(data.detail || 'Erro no expurgo', 'error');
        }
    } catch (error) {
        showToast('Erro de conexão', 'error');
    }

    btn.disabled = false;
    btn.textContent = 'Expurgar tudo (elegível)';
};

// ==================== UTILS ====================

function showToast(message, type) {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add('show'));

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 2500);
}

function escapeHTML(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, tag => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[tag] || tag));
}
