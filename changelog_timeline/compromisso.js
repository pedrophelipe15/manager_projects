/**
 * compromisso.js — Compromisso de Prazo (Onda 1/2 UX).
 * Consome /api/metrics/wave5/slippage?project_key=X.
 */
const JIRA_BASE_URL = 'https://jiraps.atlassian.net/browse/';

const CLASS_LABEL = {
    kept: 'Compromisso mantido',
    replanned: 'Replanejamento normal',
    attention: 'Atencao',
    pushing: 'Prazo sendo empurrado',
};
const CLASS_ORDER = { pushing: 0, attention: 1, replanned: 2, kept: 3 };

let currentProject = null;
let currentData = null;
// Estado dos filtros e ordenacao da tabela de piores issues.
let filters = { classification: [], assignee: [] };
let sort = { col: 'reschedules', dir: 'desc' };

document.addEventListener('DOMContentLoaded', () => {
    loadProjects();
    document.getElementById('projectFilter').addEventListener('change', onProjectChange);
});

async function loadProjects() {
    try {
        const r = await fetch('/api/settings/projects');
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const projects = await r.json();
        const select = document.getElementById('projectFilter');
        projects.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.key;
            opt.textContent = `${p.key} - ${p.name}`;
            select.appendChild(opt);
        });
        CTContext.bindProjectSelect(select, onProjectChange);
    } catch (e) {
        console.error('Erro ao carregar projetos:', e);
        renderError('Nao foi possivel carregar a lista de projetos.', loadProjects);
    }
}

function onProjectChange() {
    const key = document.getElementById('projectFilter').value;
    currentProject = key;
    filters = { classification: [], assignee: [] };
    if (!key) {
        document.getElementById('content-container').innerHTML =
            '<p class="empty-state">Selecione um projeto para ver o compromisso de prazo.</p>';
        return;
    }
    loadSlippage(key);
}

async function loadSlippage(key) {
    renderSkeleton();
    try {
        const r = await fetch(`/api/metrics/wave5/slippage?project_key=${encodeURIComponent(key)}`);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        currentData = await r.json();
        render();
    } catch (e) {
        console.error(e);
        renderError('Erro ao carregar o compromisso de prazo deste projeto.', () => loadSlippage(key));
    }
}

/* ---------- Estados ---------- */
function renderSkeleton() {
    document.getElementById('content-container').innerHTML = `
        <div class="skel-kpis">
            <div class="skel-card"></div><div class="skel-card"></div>
            <div class="skel-card"></div><div class="skel-card"></div>
        </div>
        <div class="section glass skeleton">
            <div class="skel-line" style="width:30%"></div>
            <div class="skel-line" style="width:100%"></div>
            <div class="skel-line" style="width:100%"></div>
            <div class="skel-line" style="width:80%"></div>
        </div>`;
}

function renderError(msg, retryFn) {
    const c = document.getElementById('content-container');
    c.innerHTML = `<div class="section glass state-box">
        <div class="state-title">Algo deu errado</div>
        <div>${msg}</div>
        <button class="btn btn--primary btn--md" id="btn-retry">Tentar de novo</button>
    </div>`;
    const btn = document.getElementById('btn-retry');
    if (btn && typeof retryFn === 'function') btn.addEventListener('click', retryFn);
}

/* ---------- Render principal ---------- */
function render() {
    const d = currentData;
    if (!d || !d.summary || d.summary.total_issues === 0) {
        document.getElementById('content-container').innerHTML =
            `<div class="section glass state-box">
                <div class="state-title">Sem historico de prazo</div>
                <div>Este projeto ainda nao tem reprogramacoes de due date registradas.</div>
            </div>`;
        return;
    }

    const s = d.summary;
    const score = s.commitment_score;
    const scoreClass = score >= 70 ? 'good' : (score >= 50 ? 'warn' : 'bad');
    const scoreColor = score >= 70 ? '#34d399' : (score >= 50 ? '#fbbf24' : '#f87171');
    const pushing = s.counts.pushing || 0;
    const attention = s.counts.attention || 0;

    const html = `
        <section class="kpi-grid">
            <div class="kpi-card glass">
                <h3>Commitment Score</h3>
                <p class="kpi-value ${scoreClass}">${score}%</p>
                <div class="score-bar"><div class="score-fill" style="width:${score}%;background:${scoreColor}"></div></div>
                <p class="kpi-sub">${s.counts.kept} de ${s.total_issues} issues entregues na 1a data</p>
            </div>
            <div class="kpi-card glass">
                <h3>Prazo Empurrado (3x+)</h3>
                <p class="kpi-value ${pushing > 0 ? 'bad' : 'good'}">${pushing}</p>
                <p class="kpi-sub">issues remarcadas 3 ou mais vezes</p>
            </div>
            <div class="kpi-card glass">
                <h3>Em Atencao (2x)</h3>
                <p class="kpi-value ${attention > 0 ? 'warn' : 'good'}">${attention}</p>
                <p class="kpi-sub">issues remarcadas 2 vezes</p>
            </div>
            <div class="kpi-card glass">
                <h3>Dias Empurrados</h3>
                <p class="kpi-value ${s.total_days_pushed > 0 ? 'warn' : 'good'}">${s.total_days_pushed}</p>
                <p class="kpi-sub">soma de dias adiados no projeto</p>
            </div>
        </section>

        <section class="section glass" id="people-section">
            <div class="table-actions">
                <div>
                    <h2>Por Responsavel</h2>
                    <p class="section-desc" style="margin:0">Commitment score por pessoa. Menor score no topo. Nao e ranking de performance — e mapa de risco de previsibilidade.</p>
                </div>
                <button class="btn btn--secondary btn--sm btn-copy-table" id="btn-copy-people">Copiar tabela</button>
            </div>
            <div class="table-scroll">${renderPeopleTable(d.by_assignee)}</div>
        </section>

        <section class="section glass" id="worst-section">
            <div class="table-actions">
                <div>
                    <h2>Issues com Prazo Empurrado</h2>
                    <p class="section-desc" style="margin:0">Issues que tiveram due date reprogramado. Ordene e filtre para investigar.</p>
                </div>
                <button class="btn btn--secondary btn--sm btn-copy-table" id="btn-copy-worst">Copiar tabela</button>
            </div>
            <div id="worst-filters"></div>
            <div class="table-scroll" id="worst-table"></div>
        </section>
    `;
    document.getElementById('content-container').innerHTML = html;
    renderWorstFilters();
    renderWorstTable();

    const cp = document.getElementById('btn-copy-people');
    if (cp) cp.addEventListener('click', () => CTUI.copyTable('#people-section', cp));
    const cw = document.getElementById('btn-copy-worst');
    if (cw) cw.addEventListener('click', () => CTUI.copyTable('#worst-table', cw));
}

function renderPeopleTable(people) {
    if (!people || !people.length) return '<p class="section-desc">Sem dados.</p>';
    const maxDays = Math.max(1, ...people.map(p => p.total_days_pushed));
    const rows = people.map(p => {
        const sc = p.commitment_score;
        const color = sc >= 70 ? '#34d399' : (sc >= 50 ? '#fbbf24' : '#f87171');
        const barW = Math.round((p.total_days_pushed / maxDays) * 100);
        return `<tr>
            <td>${escapeHtml(p.assignee)}</td>
            <td class="num" style="color:${color};font-weight:600">${sc}%</td>
            <td class="num">${p.total_issues}</td>
            <td class="num">${p.counts.pushing || 0}</td>
            <td class="num">${p.counts.attention || 0}</td>
            <td class="num">${p.total_days_pushed}
                <span class="mini-bar"><span style="width:${barW}%;background:${color}"></span></span>
            </td>
        </tr>`;
    }).join('');
    return `<table class="data-table">
        <thead><tr>
            <th>Responsavel</th><th class="num">Score</th><th class="num">Issues</th>
            <th class="num">Empurrado 3x+</th><th class="num">Atencao 2x</th><th class="num">Dias adiados</th>
        </tr></thead>
        <tbody>${rows}</tbody></table>`;
}

/* ---------- Piores issues: filtros + ordenacao ---------- */
function renderWorstFilters() {
    const issues = currentData.worst_issues || [];
    const classOptions = [...new Set(issues.map(i => i.classification))]
        .sort((a, b) => CLASS_ORDER[a] - CLASS_ORDER[b]);
    const assigneeOptions = [...new Set(issues.map(i => i.assignee).filter(Boolean))].sort();

    filters.classification = filters.classification.filter(c => classOptions.includes(c));
    filters.assignee = filters.assignee.filter(a => assigneeOptions.includes(a));

    const el = document.getElementById('worst-filters');
    el.innerHTML = `<div class="filters-row">
        ${buildDropdown('f-class', 'Classificacao', classOptions, filters.classification, CLASS_LABEL)}
        ${buildDropdown('f-assignee', 'Responsavel', assigneeOptions, filters.assignee)}
        <button class="btn-clear-filters" onclick="clearFilters()">Limpar</button>
    </div>`;
}

function buildDropdown(id, label, options, selected, labelMap) {
    const count = selected.length ? `<span class="dd-count">(${selected.length})</span>` : '';
    const opts = options.map(o => {
        const checked = selected.includes(o) ? 'checked' : '';
        const text = labelMap && labelMap[o] ? labelMap[o] : o;
        return `<label class="dd-option">
            <input type="checkbox" value="${escapeHtml(o)}" ${checked} onchange="onFilterChange()">
            <span>${escapeHtml(text)}</span>
        </label>`;
    }).join('');
    return `<div class="dd-wrapper" id="${id}">
        <button class="dd-toggle" onclick="toggleDropdown('${id}')">
            <span class="dd-label">${label}</span> ${count}
            <span class="dd-arrow">&#9662;</span>
        </button>
        <div class="dd-menu">${opts || '<div class="dd-option">Sem opcoes</div>'}</div>
    </div>`;
}

function toggleDropdown(id) {
    const menu = document.getElementById(id).querySelector('.dd-menu');
    const isOpen = menu.classList.contains('open');
    document.querySelectorAll('.dd-menu.open').forEach(m => m.classList.remove('open'));
    if (!isOpen) menu.classList.add('open');
}

document.addEventListener('click', (e) => {
    if (!e.target.closest('.dd-wrapper')) {
        document.querySelectorAll('.dd-menu.open').forEach(m => m.classList.remove('open'));
    }
});

function getChecked(id) {
    return Array.prototype.map.call(
        document.querySelectorAll(`#${id} input:checked`), el => el.value
    );
}

function onFilterChange() {
    filters.classification = getChecked('f-class');
    filters.assignee = getChecked('f-assignee');
    renderWorstFilters();
    renderWorstTable();
}

function clearFilters() {
    filters = { classification: [], assignee: [] };
    renderWorstFilters();
    renderWorstTable();
}

function setSort(col) {
    if (sort.col === col) {
        sort.dir = sort.dir === 'asc' ? 'desc' : 'asc';
    } else {
        sort.col = col;
        sort.dir = 'desc';
    }
    renderWorstTable();
}

function renderWorstTable() {
    let issues = (currentData.worst_issues || []).slice();
    if (filters.classification.length) issues = issues.filter(i => filters.classification.includes(i.classification));
    if (filters.assignee.length) issues = issues.filter(i => filters.assignee.includes(i.assignee));

    issues.sort((a, b) => {
        let va, vb;
        if (sort.col === 'issue_key' || sort.col === 'assignee' || sort.col === 'classification') {
            va = String(a[sort.col] || ''); vb = String(b[sort.col] || '');
            return sort.dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
        }
        va = a[sort.col] || 0; vb = b[sort.col] || 0;
        return sort.dir === 'asc' ? va - vb : vb - va;
    });

    const ind = (col) => sort.col === col ? (sort.dir === 'asc' ? '↑' : '↓') : '↕';
    const rows = issues.map(i => `<tr>
        <td><a class="jira-link" href="${JIRA_BASE_URL}${i.issue_key}" target="_blank" rel="noopener">${i.issue_key}</a></td>
        <td>${escapeHtml(i.assignee)}</td>
        <td class="num">${i.reschedules}</td>
        <td class="num">${i.total_days_pushed}</td>
        <td>${fmtBR(i.original_due)}</td>
        <td>${fmtBR(i.current_due)}</td>
        <td><span class="badge ${i.classification}">${CLASS_LABEL[i.classification] || i.classification}</span></td>
    </tr>`).join('');

    document.getElementById('worst-table').innerHTML = `<table class="data-table">
        <thead><tr>
            <th class="sortable" onclick="setSort('issue_key')">Issue <span class="sort-ind">${ind('issue_key')}</span></th>
            <th class="sortable" onclick="setSort('assignee')">Responsavel <span class="sort-ind">${ind('assignee')}</span></th>
            <th class="sortable num" onclick="setSort('reschedules')">Reprogramacoes <span class="sort-ind">${ind('reschedules')}</span></th>
            <th class="sortable num" onclick="setSort('total_days_pushed')">Dias adiados <span class="sort-ind">${ind('total_days_pushed')}</span></th>
            <th>Prazo original</th>
            <th>Prazo atual</th>
            <th class="sortable" onclick="setSort('classification')">Classificacao <span class="sort-ind">${ind('classification')}</span></th>
        </tr></thead>
        <tbody>${rows || '<tr><td colspan="7" class="empty-state">Nenhuma issue no filtro atual.</td></tr>'}</tbody></table>`;
}

/* ---------- Utils ---------- */
function fmtBR(iso) {
    if (!iso) return '--';
    const p = String(iso).split('T')[0].split('-');
    return p.length === 3 ? `${p[2]}/${p[1]}/${p[0]}` : iso;
}

function escapeHtml(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
