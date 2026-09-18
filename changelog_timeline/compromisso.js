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
// Estado dos filtros, ordenacao e paginacao da tabela de piores issues.
let filters = { classification: [], assignee: [], status: [] };
let sort = { col: 'reschedules', dir: 'desc' };
let worstPage = 1;
const WORST_PAGE_SIZE = 15;

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
    filters = { classification: [], assignee: [], status: [] };
    worstPage = 1;
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

    // Tooltip explicativo do calculo (componente compartilhado CTUI.infoTooltip).
    const cc = s.counts || {};
    const kept = cc.kept || 0;
    const scoreTip = (s.total_issues === 0) ? CTUI.infoTooltip({
        title: 'Commitment Score', empty: 'Sem issues com prazo registrado neste projeto.',
    }) : CTUI.infoTooltip({
        title: 'Como o score e calculado',
        formula: 'Score = mantidas &divide; total &times; 100',
        calc: `${kept} &divide; ${s.total_issues} &times; 100 = <strong>${score}%</strong>`,
        rows: [
            { label: 'Mantidas (1a data)', value: kept, tone: 'good' },
            { label: 'Replanejadas (1x)', value: cc.replanned || 0, tone: 'info' },
            { label: 'Atencao (2x)', value: cc.attention || 0, tone: 'warn' },
            { label: 'Prazo empurrado (3x+)', value: cc.pushing || 0, tone: 'bad' },
            { label: 'Total com prazo', value: s.total_issues, total: true },
        ],
        note: '"Mantidas" = entregues na 1a data prometida, sem reprogramar o due date.',
        position: 'left',
    });

    const html = `
        <section class="kpi-grid">
            <div class="kpi-card glass">
                <h3>Commitment Score</h3>
                <div class="ct-tip-wrap score-tip-wrap" tabindex="0" role="button" aria-label="Ver como o commitment score foi calculado">
                    <p class="kpi-value ${scoreClass}">${score}%</p>
                    ${scoreTip}
                </div>
                <div class="score-bar"><div class="score-fill" style="width:${score}%;background:${scoreColor}"></div></div>
                <p class="kpi-sub">${s.counts.kept} de ${s.total_issues} issues entregues na 1a data</p>
                <div class="score-legend">
                    <span class="score-legend-item"><span class="slg-dot good"></span>&ge; 70% Aceitavel</span>
                    <span class="score-legend-item"><span class="slg-dot warn"></span>50&ndash;69% Atencao</span>
                    <span class="score-legend-item"><span class="slg-dot bad"></span>&lt; 50% Critico</span>
                </div>
            </div>
            <div class="kpi-card glass kpi-clickable" id="kpi-pushing" onclick="filterByClass('pushing')" tabindex="0" role="button" title="Ver issues com prazo empurrado">
                <h3>Prazo Empurrado (3x+)</h3>
                <p class="kpi-value ${pushing > 0 ? 'bad' : 'good'}">${pushing}<span class="kpi-chevron">&#8250;</span></p>
                <p class="kpi-sub">issues remarcadas 3 ou mais vezes</p>
            </div>
            <div class="kpi-card glass kpi-clickable" id="kpi-attention" onclick="filterByClass('attention')" tabindex="0" role="button" title="Ver issues em atencao">
                <h3>Em Atencao (2x)</h3>
                <p class="kpi-value ${attention > 0 ? 'warn' : 'good'}">${attention}<span class="kpi-chevron">&#8250;</span></p>
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
            <div class="people-scroll">${renderPeopleTable(d.by_assignee)}</div>
        </section>

        <section class="section glass" id="worst-section" style="display:none;">
            <div class="table-actions">
                <div>
                    <h2 id="worst-title">Issues com Prazo Reprogramado</h2>
                    <p class="section-desc" style="margin:0">Ordene clicando nos cabecalhos. Use os filtros ou clique novamente no indicador para fechar.</p>
                </div>
                <button class="btn btn--secondary btn--sm btn-copy-table" id="btn-copy-worst">Copiar tabela</button>
            </div>
            <div id="worst-filters"></div>
            <div class="table-scroll" id="worst-table"></div>
        </section>
    `;
    document.getElementById('content-container').innerHTML = html;
    // O painel de detalhe comeca OCULTO; so aparece ao clicar num indicador.
    // (filters foi resetado no onProjectChange, entao ao trocar de projeto volta ao default.)

    const cp = document.getElementById('btn-copy-people');
    if (cp) cp.addEventListener('click', () => CTUI.copyTable('#people-section', cp));
    const cw = document.getElementById('btn-copy-worst');
    if (cw) cw.addEventListener('click', () => CTUI.copyTable('#worst-table', cw));
}

// Mostra/oculta a secao de detalhe conforme houver algum filtro ativo.
function updateWorstVisibility() {
    const sec = document.getElementById('worst-section');
    if (!sec) return;
    const active = filters.classification.length > 0 || filters.assignee.length > 0 || filters.status.length > 0;
    sec.style.display = active ? '' : 'none';
    return active;
}

function renderPeopleTable(people) {
    if (!people || !people.length) return '<p class="section-desc">Sem dados.</p>';
    const maxDays = Math.max(1, ...people.map(p => p.total_days_pushed));
    const rows = people.map(p => {
        const sc = p.commitment_score;
        const color = sc >= 70 ? '#34d399' : (sc >= 50 ? '#fbbf24' : '#f87171');
        const barW = Math.round((p.total_days_pushed / maxDays) * 100);
        const cc = p.counts || {};
        const kept = cc.kept || 0;
        // Tooltip explicativo do score DESTA pessoa (componente compartilhado).
        const tip = (p.total_issues === 0) ? CTUI.infoTooltip({
            title: 'Score de ' + p.assignee, empty: 'Sem issues com prazo registrado.',
        }) : CTUI.infoTooltip({
            title: 'Score de ' + p.assignee,
            formula: 'Score = mantidas &divide; total &times; 100',
            calc: `${kept} &divide; ${p.total_issues} &times; 100 = <strong>${sc}%</strong>`,
            rows: [
                { label: 'Mantidas (1a data)', value: kept, tone: 'good' },
                { label: 'Replanejadas (1x)', value: cc.replanned || 0, tone: 'info' },
                { label: 'Atencao (2x)', value: cc.attention || 0, tone: 'warn' },
                { label: 'Prazo empurrado (3x+)', value: cc.pushing || 0, tone: 'bad' },
                { label: 'Total com prazo', value: p.total_issues, total: true },
            ],
            note: '"Mantidas" = entregues na 1a data prometida, sem reprogramar o due date.',
        });
        return `<tr>
            <td>${escapeHtml(p.assignee)}</td>
            <td class="num">
                <span class="ct-tip-wrap people-score-tip" tabindex="0" role="button" aria-label="Como o score de ${escapeHtml(p.assignee)} foi calculado" style="color:${color};font-weight:600">${sc}%${tip}</span>
            </td>
            <td class="num">${p.total_issues}</td>
            <td class="num">${p.counts.pushing || 0}</td>
            <td class="num">${p.counts.attention || 0}</td>
            <td class="num">${p.total_days_pushed}
                <span class="mini-bar"><span style="width:${barW}%;background:${color}"></span></span>
            </td>
        </tr>`;
    }).join('');
    return `<table class="data-table people-table">
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
    const statusOptions = [...new Set(issues.map(i => i.status).filter(Boolean))].sort();

    filters.classification = filters.classification.filter(c => classOptions.includes(c));
    filters.assignee = filters.assignee.filter(a => assigneeOptions.includes(a));
    filters.status = filters.status.filter(s => statusOptions.includes(s));

    const el = document.getElementById('worst-filters');
    el.innerHTML = `<div class="filters-row">
        ${buildDropdown('f-class', 'Classificacao', classOptions, filters.classification, CLASS_LABEL)}
        ${buildDropdown('f-assignee', 'Responsavel', assigneeOptions, filters.assignee)}
        ${buildDropdown('f-status', 'Status', statusOptions, filters.status)}
        <button class="btn-clear-filters" onclick="clearFilters()">Limpar</button>
        <div class="worst-pager" id="worst-pager"></div>
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
    filters.status = getChecked('f-status');
    worstPage = 1; // filtrar volta para a primeira pagina
    // Sincroniza o destaque dos KPIs com o filtro de classificacao.
    const cls = filters.classification.length === 1 ? filters.classification[0] : null;
    markActiveKpi(cls === 'pushing' || cls === 'attention' ? cls : null);
    updateWorstTitle();
    // Se o usuario limpou tudo pelos dropdowns, fecha o painel; senao re-renderiza.
    if (!updateWorstVisibility()) return;
    renderWorstFilters();
    renderWorstTable();
}

function worstGoPage(delta) {
    worstPage += delta;
    renderWorstTable();
}

function clearFilters() {
    // Limpar dentro do painel fecha a secao (volta ao default oculto).
    filters = { classification: [], assignee: [], status: [] };
    worstPage = 1;
    markActiveKpi(null);
    updateWorstTitle();
    updateWorstVisibility();
}

// Clique num KPI (pushing/attention): mostra e filtra a lista por aquela
// classificacao, destaca o KPI e rola ate a secao. Clicar de novo fecha.
function filterByClass(cls) {
    const already = filters.classification.length === 1 && filters.classification[0] === cls;
    if (already) {
        // Toggle off: fecha o painel e volta ao default.
        filters = { classification: [], assignee: [], status: [] };
        worstPage = 1;
        markActiveKpi(null);
        updateWorstTitle();
        updateWorstVisibility();
        return;
    }
    filters = { classification: [cls], assignee: [], status: [] };
    worstPage = 1;
    markActiveKpi(cls);
    updateWorstTitle();
    updateWorstVisibility();
    renderWorstFilters();
    renderWorstTable();
    const sec = document.getElementById('worst-section');
    if (sec) sec.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function markActiveKpi(cls) {
    ['pushing', 'attention'].forEach(c => {
        const el = document.getElementById('kpi-' + c);
        if (el) el.classList.toggle('active', c === cls);
    });
}

function updateWorstTitle() {
    const el = document.getElementById('worst-title');
    if (!el) return;
    const cls = filters.classification.length === 1 ? filters.classification[0] : null;
    if (cls === 'pushing') el.textContent = 'Issues com Prazo Empurrado (3x+)';
    else if (cls === 'attention') el.textContent = 'Issues em Atencao (2x)';
    else el.textContent = 'Issues com Prazo Reprogramado';
}

function setSort(col) {
    if (sort.col === col) {
        sort.dir = sort.dir === 'asc' ? 'desc' : 'asc';
    } else {
        sort.col = col;
        sort.dir = 'desc';
    }
    worstPage = 1;
    renderWorstTable();
}

function renderWorstTable() {
    let issues = (currentData.worst_issues || []).slice();
    if (filters.classification.length) issues = issues.filter(i => filters.classification.includes(i.classification));
    if (filters.assignee.length) issues = issues.filter(i => filters.assignee.includes(i.assignee));
    if (filters.status.length) issues = issues.filter(i => filters.status.includes(i.status));

    issues.sort((a, b) => {
        let va, vb;
        if (sort.col === 'issue_key' || sort.col === 'assignee' || sort.col === 'classification'
            || sort.col === 'status' || sort.col === 'original_due' || sort.col === 'current_due') {
            va = String(a[sort.col] || ''); vb = String(b[sort.col] || '');
            return sort.dir === 'asc' ? va.localeCompare(vb, 'pt-BR', { numeric: true }) : vb.localeCompare(va, 'pt-BR', { numeric: true });
        }
        va = a[sort.col] || 0; vb = b[sort.col] || 0;
        return sort.dir === 'asc' ? va - vb : vb - va;
    });

    // Paginacao (15/pag por default)
    const total = issues.length;
    const totalPages = Math.max(1, Math.ceil(total / WORST_PAGE_SIZE));
    if (worstPage > totalPages) worstPage = totalPages;
    if (worstPage < 1) worstPage = 1;
    const start = (worstPage - 1) * WORST_PAGE_SIZE;
    const pageIssues = issues.slice(start, start + WORST_PAGE_SIZE);

    const ind = (col) => sort.col === col ? (sort.dir === 'asc' ? '↑' : '↓') : '↕';
    const rows = pageIssues.map(i => `<tr>
        <td><a class="jira-link" href="${JIRA_BASE_URL}${i.issue_key}" target="_blank" rel="noopener">${i.issue_key}</a></td>
        <td>${escapeHtml(i.assignee)}</td>
        <td>${escapeHtml(i.status)}</td>
        <td class="num">${i.reschedules}</td>
        <td class="num">${i.total_days_pushed}</td>
        <td class="num">${fmtBR(i.original_due)}</td>
        <td class="num">${fmtBR(i.current_due)}</td>
        <td class="num"><span class="badge ${i.classification}">${CLASS_LABEL[i.classification] || i.classification}</span></td>
    </tr>`).join('');

    document.getElementById('worst-table').innerHTML = `<table class="data-table worst-table">
        <thead><tr>
            <th class="sortable" onclick="setSort('issue_key')">Issue <span class="sort-ind">${ind('issue_key')}</span></th>
            <th class="sortable" onclick="setSort('assignee')">Responsavel <span class="sort-ind">${ind('assignee')}</span></th>
            <th class="sortable" onclick="setSort('status')">Status <span class="sort-ind">${ind('status')}</span></th>
            <th class="sortable num" onclick="setSort('reschedules')">Reprogramacoes <span class="sort-ind">${ind('reschedules')}</span></th>
            <th class="sortable num" onclick="setSort('total_days_pushed')">Dias adiados <span class="sort-ind">${ind('total_days_pushed')}</span></th>
            <th class="sortable num" onclick="setSort('original_due')">Prazo original <span class="sort-ind">${ind('original_due')}</span></th>
            <th class="sortable num" onclick="setSort('current_due')">Prazo atual <span class="sort-ind">${ind('current_due')}</span></th>
            <th class="sortable num" onclick="setSort('classification')">Classificacao <span class="sort-ind">${ind('classification')}</span></th>
        </tr></thead>
        <tbody>${rows || '<tr><td colspan="8" class="empty-state">Nenhuma issue no filtro atual.</td></tr>'}</tbody></table>`;

    // Paginacao na mesma linha dos filtros
    const pager = document.getElementById('worst-pager');
    if (pager) {
        const from = total ? start + 1 : 0;
        const to = Math.min(start + WORST_PAGE_SIZE, total);
        pager.innerHTML = `
            <span class="worst-pager-info">${from}&ndash;${to} de ${total}</span>
            <button class="worst-pager-btn" onclick="worstGoPage(-1)"${worstPage <= 1 ? ' disabled' : ''} title="Anterior">&#8249;</button>
            <span class="worst-pager-page">Pag. ${worstPage}/${totalPages}</span>
            <button class="worst-pager-btn" onclick="worstGoPage(1)"${worstPage >= totalPages ? ' disabled' : ''} title="Proxima">&#8250;</button>`;
    }
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
