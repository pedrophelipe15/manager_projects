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

    document.getElementById('preview-active').textContent = `${base} AND status in (${statusList})`;
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

window.executePurge = async function() {
    const btn = document.getElementById('btnPurge');

    if (!confirm('Isso vai remover permanentemente issues Done com mais de 6 meses do banco. Confirma?')) return;

    btn.disabled = true;
    btn.textContent = 'Expurgando...';

    try {
        const response = await fetch('/api/settings/purge', { method: 'POST' });
        const data = await response.json();

        if (response.ok) {
            showToast(`Expurgo concluído: ${data.issues_removed} issues removidas`, 'success');
            await loadPurgeStatus();
        } else {
            showToast(data.detail || 'Erro no expurgo', 'error');
        }
    } catch (error) {
        showToast('Erro de conexão', 'error');
    }

    btn.disabled = false;
    btn.textContent = 'Executar Expurgo';
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
