/**
 * minha-visao.js — Home 'Minha Visao' (Onda 2 UX).
 * Consome /api/home/overview e /api/settings/projects.
 * O gestor escolhe seus projetos (chips); a selecao persiste em localStorage.
 */
const JIRA_BASE_URL = 'https://jiraps.atlassian.net/browse/';
const LS_KEY = 'ct.myProjects';

const TYPE_LABEL = { pushing: 'Prazo empurrado', blocked: 'Bloqueado', no_assignee: 'Sem responsavel' };

let allProjects = [];
let selected = [];

document.addEventListener('DOMContentLoaded', init);

async function init() {
    document.getElementById('btn-all').addEventListener('click', () => {
        selected = allProjects.map(p => p.key);
        persist();
        renderPicker();
        load();
    });
    document.getElementById('btn-clear').addEventListener('click', () => {
        selected = [];
        persist();
        renderPicker();
        load();
    });
    await loadProjects();
}

function getSaved() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || '[]'); }
    catch (e) { return []; }
}
function persist() {
    try { localStorage.setItem(LS_KEY, JSON.stringify(selected)); } catch (e) { /* ignore */ }
}

async function loadProjects() {
    try {
        const r = await fetch('/api/settings/projects');
        if (!r.ok) throw new Error('HTTP ' + r.status);
        allProjects = await r.json();
        const saved = getSaved().filter(k => allProjects.some(p => p.key === k));
        selected = saved.length ? saved : allProjects.map(p => p.key);
        persist();
        renderPicker();
        load();
    } catch (e) {
        console.error('Erro ao carregar projetos:', e);
        renderError('Nao foi possivel carregar os projetos.', loadProjects);
    }
}

function renderPicker() {
    const el = document.getElementById('projectPicker');
    el.innerHTML = allProjects.map(p => {
        const on = selected.includes(p.key) ? ' selected' : '';
        return `<span class="project-chip${on}" data-key="${p.key}" title="${escapeHtml(p.name)}">${p.key}</span>`;
    }).join('');
    el.querySelectorAll('.project-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const k = chip.dataset.key;
            const i = selected.indexOf(k);
            if (i === -1) selected.push(k); else selected.splice(i, 1);
            persist();
            renderPicker();
            load();
        });
    });
}

async function load() {
    const c = document.getElementById('content-container');
    if (!selected.length) {
        c.innerHTML = '<p class="empty-state">Selecione ao menos um projeto acima.</p>';
        return;
    }
    c.innerHTML = `<div class="skel-cards"><div class="skel-card"></div><div class="skel-card"></div></div>`;
    try {
        const r = await fetch(`/api/home/overview?project_keys=${encodeURIComponent(selected.join(','))}`);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        render(await r.json());
    } catch (e) {
        console.error(e);
        renderError('Erro ao carregar a visao dos projetos.', load);
    }
}

function render(data) {
    const projects = data.projects || [];
    activeDetail = null; detailState = null; // reseta o painel de detalhe ao re-renderizar a home
    const cards = projects.map(renderProjectCard).join('');

    document.getElementById('content-container').innerHTML = `
        <p class="hint-clique">Clique em qualquer indicador de um projeto para ver as issues correspondentes abaixo.</p>
        <section class="projects-grid">${cards || '<p class="empty-state">Sem dados.</p>'}</section>
        <section class="section glass" id="detail-panel">
            <p class="section-desc" style="margin:0">Selecione um indicador em qualquer projeto acima para listar as issues aqui.</p>
        </section>`;
}

function renderProjectCard(p) {
    const proj = allProjects.find(a => a.key === p.project_key);
    const name = proj ? proj.name : p.project_key;
    const score = (p.commitment_score == null) ? null : p.commitment_score;
    const scoreClass = score == null ? '' : (score >= 70 ? 'good' : (score >= 50 ? 'warn' : 'bad'));
    const scoreColor = score == null ? '#94a3b8' : (score >= 70 ? '#34d399' : (score >= 50 ? '#fbbf24' : '#f87171'));
    const scoreTxt = score == null ? '--' : score + '%';

    // Descritivo do commitment score: veredito + como e calculado.
    let scoreVerdict, scoreVerdictCls;
    if (score == null) { scoreVerdict = 'Sem historico de prazo'; scoreVerdictCls = 'neutral'; }
    else if (score >= 70) { scoreVerdict = 'Aceitavel'; scoreVerdictCls = 'good'; }
    else if (score >= 50) { scoreVerdict = 'Atencao'; scoreVerdictCls = 'warn'; }
    else { scoreVerdict = 'Critico'; scoreVerdictCls = 'bad'; }

    // Tooltip explicativo (componente reutilizavel do design system): a conta do score.
    const cc = p.commitment_counts || { kept: 0, replanned: 0, attention: 0, pushing: 0 };
    const total = p.commitment_total || 0;
    const kept = cc.kept || 0;
    const scoreTip = CTUI.infoTooltip(total === 0 ? {
        title: 'Commitment Score',
        empty: 'Sem issues com prazo registrado neste projeto.',
    } : {
        title: 'Como o score e calculado',
        formula: 'Score = mantidas &divide; total &times; 100',
        calc: `${kept} &divide; ${total} &times; 100 = <strong>${score}%</strong>`,
        rows: [
            { label: 'Mantidas (1a data)', value: kept, tone: 'good' },
            { label: 'Replanejadas (1x)', value: cc.replanned || 0, tone: 'info' },
            { label: 'Atencao (2x)', value: cc.attention || 0, tone: 'warn' },
            { label: 'Prazo empurrado (3x+)', value: cc.pushing || 0, tone: 'bad' },
            { label: 'Total com prazo', value: total, total: true },
        ],
        note: '"Mantidas" = entregues na 1a data prometida, sem reprogramar o due date.',
    });

    // Cada linha de indicador e clicavel e abre o modal do respectivo metric.
    const pk = p.project_key;
    const row = (label, dot, num, cls, metric) => `
        <button class="pc-row pc-row-btn" data-pk="${pk}" data-metric="${metric}" onclick="showMetricDetail('${pk}','${metric}')" title="Ver issues de '${label}'">
            <span class="pc-label"><span class="pc-dot" style="background:${dot}"></span>${label}</span>
            <span class="pc-num ${cls}">${num}<span class="pc-chevron">&#8250;</span></span>
        </button>`;

    return `<div class="project-card glass">
        <div class="pc-head">
            <div>
                <div class="pc-key">${p.project_key}</div>
                <div class="section-desc" style="margin:0">${escapeHtml(name)}</div>
            </div>
            <div class="ct-tip-wrap pc-score-tip" tabindex="0" role="button" aria-label="Ver como o commitment score foi calculado">
                <div class="pc-score ${scoreClass}">${scoreTxt}</div>
                ${scoreTip}
            </div>
        </div>
        <div class="score-bar"><div class="score-fill" style="width:${score == null ? 0 : score}%;background:${scoreColor}"></div></div>
        <div class="pc-score-desc">
            <span class="pc-verdict ${scoreVerdictCls}">${scoreVerdict}</span>
            <span class="pc-score-help">Commitment Score = % de issues entregues na 1a data prometida (sem reprogramar). Meta &ge; 70%.</span>
        </div>
        <div class="pc-metrics">
            ${row('Prazo empurrado 3x+', 'var(--risk)', p.pushing, p.pushing > 0 ? 'bad' : 'ok', 'pushing')}
            ${row('Bloqueado', 'var(--warn)', p.blocked, p.blocked > 0 ? 'warn' : 'ok', 'blocked')}
            ${row('Sem responsavel', 'var(--action)', p.no_assignee, p.no_assignee > 0 ? 'bad' : 'ok', 'no_assignee')}
            ${row('Em andamento', 'var(--ok)', p.in_flight, 'ok', 'in_flight')}
            ${row('Paradas >14 dias', 'var(--text-3)', p.stale, p.stale > 0 ? 'warn' : 'ok', 'stale')}
        </div>
        <div class="pc-links">
            <a class="pc-link" href="/compromisso.html" onclick="goToProject('${p.project_key}')">Compromisso</a>
            <a class="pc-link" href="/maturidade.html" onclick="goToProject('${p.project_key}')">Maturidade</a>
            <a class="pc-link" href="/wave1.html" onclick="goToProject('${p.project_key}')">Fluxo</a>
        </div>
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

// Define o projeto no contexto compartilhado antes de navegar para a tela
// destino, para que ela abra ja escopada ao projeto do card clicado.
function goToProject(key) {
    if (window.CTContext) CTContext.setProject(key);
}

/* ============ DETALHE INLINE DE INDICADOR (painel abaixo dos cards) ============ */
let activeDetail = null;  // { projectKey, metric } atualmente exibido
let detailState = null;   // { all, filters, sort, ... } do painel aberto

function markActiveRow(projectKey, metric) {
    document.querySelectorAll('.pc-row-btn.active').forEach(b => b.classList.remove('active'));
    if (!projectKey) return;
    const btn = document.querySelector(`.pc-row-btn[data-pk="${projectKey}"][data-metric="${metric}"]`);
    if (btn) btn.classList.add('active');
}

async function showMetricDetail(projectKey, metric) {
    const panel = document.getElementById('detail-panel');
    if (!panel) return;

    // Toggle: clicar de novo no mesmo indicador fecha o painel.
    if (activeDetail && activeDetail.projectKey === projectKey && activeDetail.metric === metric) {
        activeDetail = null;
        detailState = null;
        markActiveRow(null);
        panel.innerHTML = `<p class="section-desc" style="margin:0">Selecione um indicador em qualquer projeto acima para listar as issues aqui.</p>`;
        return;
    }

    activeDetail = { projectKey, metric };
    markActiveRow(projectKey, metric);
    panel.innerHTML = `<div class="skeleton"><div class="skel-line" style="width:40%"></div><div class="skel-line" style="width:100%"></div><div class="skel-line" style="width:90%"></div></div>`;

    try {
        const r = await fetch(`/api/home/detail?project_key=${encodeURIComponent(projectKey)}&metric=${encodeURIComponent(metric)}`);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const data = await r.json();
        // Estado do painel: dados + filtros (multi-selecao) + ordenacao.
        detailState = {
            projectKey, metric,
            title: data.title, description: data.description, count: data.count,
            all: data.issues || [],
            filters: { assignee: [], status: [] },
            sort: { col: null, dir: 'asc' },
            page: 1, pageSize: 15,
        };
        renderDetailPanel();
    } catch (e) {
        console.error(e);
        panel.innerHTML = `<div class="state-box"><div class="state-title">Erro ao carregar</div>
            <button class="btn btn--primary btn--sm" onclick="showMetricDetail('${projectKey}','${metric}')">Tentar de novo</button></div>`;
    }
}

// Colunas do painel de detalhe. filterable = tem dropdown-checkbox.
const DETAIL_COLS = [
    { key: 'key',      label: 'Issue',       filterable: false, type: 'text' },
    { key: 'summary',  label: 'Resumo',      filterable: false, type: 'text' },
    { key: 'assignee', label: 'Responsavel', filterable: true,  type: 'text' },
    { key: 'status',   label: 'Status',      filterable: true,  type: 'text' },
    { key: 'due_date', label: 'Due Date',    filterable: false, type: 'date' },
    { key: 'detail',   label: 'Detalhe',     filterable: false, type: 'text' },
];

// Formata 'YYYY-MM-DD' (ou ISO) para 'DD/MM/YYYY'; vazio vira '--'.
function fmtDate(iso) {
    if (!iso) return '--';
    const p = String(iso).split('T')[0].split('-');
    return p.length === 3 ? `${p[2]}/${p[1]}/${p[0]}` : iso;
}

// Aplica os filtros ativos, opcionalmente ignorando o de uma coluna
// (para recalcular as opcoes daquela coluna dentro do contexto dos demais).
function detailFiltered(exceptCol) {
    let rows = detailState.all;
    for (const col of ['assignee', 'status']) {
        if (col === exceptCol) continue;
        const sel = detailState.filters[col];
        if (sel && sel.length) rows = rows.filter(r => sel.includes(r[col] || ''));
    }
    return rows;
}

function detailOptions(col) {
    // Opcoes cascateantes: valores possiveis dado o contexto dos OUTROS filtros.
    const ctx = detailFiltered(col);
    return [...new Set(ctx.map(r => r[col] || '').filter(v => v !== ''))].sort();
}

function detailVisibleRows() {
    let rows = detailFiltered(null);
    const s = detailState.sort;
    if (s.col) {
        rows = rows.slice().sort((a, b) => {
            const va = String(a[s.col] == null ? '' : a[s.col]);
            const vb = String(b[s.col] == null ? '' : b[s.col]);
            const cmp = va.localeCompare(vb, 'pt-BR', { numeric: true });
            return s.dir === 'asc' ? cmp : -cmp;
        });
    }
    return rows;
}

function renderDetailPanel() {
    const panel = document.getElementById('detail-panel');
    if (!panel || !detailState) return;
    const st = detailState;

    const head = `<div class="detail-head">
        <div>
            <h2>${escapeHtml(st.projectKey)} · ${escapeHtml(st.title)} <span class="detail-count">${st.count}</span></h2>
            <p class="section-desc" style="margin:0">${escapeHtml(st.description || '')}</p>
        </div>
        <button class="btn btn--ghost btn--sm" onclick="showMetricDetail('${st.projectKey}','${st.metric}')">Fechar</button>
    </div>`;

    if (!st.all.length) {
        panel.innerHTML = head + `<div class="state-box"><div class="state-title">Nada aqui</div>
            <div>Nenhuma issue neste indicador agora.</div></div>`;
        return;
    }

    // Linhas filtradas/ordenadas + paginacao
    const rows = detailVisibleRows();
    const total = rows.length;
    const totalPages = Math.max(1, Math.ceil(total / st.pageSize));
    if (st.page > totalPages) st.page = totalPages;
    if (st.page < 1) st.page = 1;
    const start = (st.page - 1) * st.pageSize;
    const pageRows = rows.slice(start, start + st.pageSize);
    const shownFrom = total ? start + 1 : 0;
    const shownTo = Math.min(start + st.pageSize, total);

    // Barra de filtros (dropdown-checkbox) + limpar + paginacao na MESMA linha
    const anyFilter = st.filters.assignee.length || st.filters.status.length;
    const pager = `<div class="detail-pager">
        <span class="detail-pager-info">${shownFrom}–${shownTo} de ${total}</span>
        <button class="detail-pager-btn" onclick="detailPage(-1)"${st.page <= 1 ? ' disabled' : ''} title="Anterior">&#8249;</button>
        <span class="detail-pager-page">Pag. ${st.page}/${totalPages}</span>
        <button class="detail-pager-btn" onclick="detailPage(1)"${st.page >= totalPages ? ' disabled' : ''} title="Proxima">&#8250;</button>
    </div>`;
    const filtersBar = `<div class="filters-row">
        ${detailDropdown('assignee', 'Responsavel')}
        ${detailDropdown('status', 'Status')}
        <button class="btn-clear-filters" onclick="clearDetailFilters()"${anyFilter ? '' : ' disabled'}>Limpar filtros</button>
        ${pager}
    </div>`;

    const ind = (col) => st.sort.col === col ? (st.sort.dir === 'asc' ? '↑' : '↓') : '↕';
    const ths = DETAIL_COLS.map(c =>
        `<th class="sortable" onclick="sortDetail('${c.key}')">${c.label} <span class="sort-ind">${ind(c.key)}</span></th>`
    ).join('');

    const body = pageRows.length
        ? pageRows.map(i => `<tr>
            <td><a class="jira-link" href="${i.url}" target="_blank" rel="noopener">${escapeHtml(i.key)}</a></td>
            <td class="mm-summary" title="${escapeHtml(i.summary)}">${escapeHtml(i.summary)}</td>
            <td>${escapeHtml(i.assignee)}</td>
            <td>${escapeHtml(i.status)}</td>
            <td class="mm-date">${fmtDate(i.due_date)}</td>
            <td class="mm-detail">${escapeHtml(i.detail || '')}</td>
        </tr>`).join('')
        : `<tr><td colspan="6" class="empty-state">Nenhuma issue no filtro atual.</td></tr>`;

    panel.innerHTML = head + filtersBar + `<div class="detail-table-wrap"><table class="data-table">
        <thead><tr>${ths}</tr></thead>
        <tbody>${body}</tbody>
    </table></div>`;
}

function detailDropdown(col, label) {
    const sel = detailState.filters[col];
    const opts = detailOptions(col);
    const count = sel.length ? `<span class="dd-count">(${sel.length})</span>` : '';
    const items = opts.length
        ? opts.map(o => {
            const checked = sel.includes(o) ? 'checked' : '';
            return `<label class="dd-option">
                <input type="checkbox" value="${escapeHtml(o)}" ${checked} onchange="onDetailFilterChange('${col}', this)">
                <span>${escapeHtml(o)}</span>
            </label>`;
        }).join('')
        : `<div class="dd-option" style="opacity:.6">Sem opcoes</div>`;
    return `<div class="dd-wrapper" id="dd-${col}">
        <button class="dd-toggle" onclick="toggleDetailDropdown('dd-${col}')">
            <span class="dd-label">${label}</span> ${count}
            <span class="dd-arrow">&#9662;</span>
        </button>
        <div class="dd-menu">${items}</div>
    </div>`;
}

function toggleDetailDropdown(id) {
    const menu = document.getElementById(id).querySelector('.dd-menu');
    const open = menu.classList.contains('open');
    document.querySelectorAll('#detail-panel .dd-menu.open').forEach(m => m.classList.remove('open'));
    if (!open) menu.classList.add('open');
}

function onDetailFilterChange(col, input) {
    const v = input.value;
    const sel = detailState.filters[col];
    if (input.checked) { if (!sel.includes(v)) sel.push(v); }
    else { detailState.filters[col] = sel.filter(x => x !== v); }
    // Poda selecoes que se tornaram invalidas nos OUTROS filtros (cascata).
    for (const other of ['assignee', 'status']) {
        if (other === col) continue;
        const valid = detailOptions(other);
        detailState.filters[other] = detailState.filters[other].filter(x => valid.includes(x));
    }
    detailState.page = 1; // filtrar volta para a primeira pagina
    renderDetailPanel();
}

function clearDetailFilters() {
    detailState.filters = { assignee: [], status: [] };
    detailState.page = 1;
    renderDetailPanel();
}

function sortDetail(col) {
    const s = detailState.sort;
    if (s.col === col) { s.dir = s.dir === 'asc' ? 'desc' : 'asc'; }
    else { s.col = col; s.dir = 'asc'; }
    detailState.page = 1; // ordenar volta para a primeira pagina
    renderDetailPanel();
}

function detailPage(delta) {
    detailState.page += delta;
    renderDetailPanel();
}

// Fecha dropdowns do painel ao clicar fora.
document.addEventListener('click', (e) => {
    if (!e.target.closest('#detail-panel .dd-wrapper')) {
        document.querySelectorAll('#detail-panel .dd-menu.open').forEach(m => m.classList.remove('open'));
    }
});

function escapeHtml(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
