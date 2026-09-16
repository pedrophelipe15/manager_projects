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
    activeDetail = null; // reseta o painel de detalhe ao re-renderizar a home
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
            <div class="pc-score ${scoreClass}">${scoreTxt}</div>
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
let activeDetail = null; // { projectKey, metric } atualmente exibido

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
        renderDetailPanel(projectKey, await r.json());
    } catch (e) {
        console.error(e);
        panel.innerHTML = `<div class="state-box"><div class="state-title">Erro ao carregar</div>
            <button class="btn btn--primary btn--sm" onclick="showMetricDetail('${projectKey}','${metric}')">Tentar de novo</button></div>`;
    }
}

function renderDetailPanel(projectKey, data) {
    const panel = document.getElementById('detail-panel');
    if (!panel) return;

    const head = `<div class="detail-head">
        <div>
            <h2>${escapeHtml(projectKey)} · ${escapeHtml(data.title)} <span class="detail-count">${data.count}</span></h2>
            <p class="section-desc" style="margin:0">${escapeHtml(data.description || '')}</p>
        </div>
        <button class="btn btn--ghost btn--sm" onclick="showMetricDetail('${projectKey}','${data.metric}')">Fechar</button>
    </div>`;

    if (!data.issues || !data.issues.length) {
        panel.innerHTML = head + `<div class="state-box"><div class="state-title">Nada aqui</div>
            <div>Nenhuma issue neste indicador agora.</div></div>`;
        return;
    }

    const rows = data.issues.map(i => `<tr>
        <td><a class="jira-link" href="${i.url}" target="_blank" rel="noopener">${escapeHtml(i.key)}</a></td>
        <td class="mm-summary" title="${escapeHtml(i.summary)}">${escapeHtml(i.summary)}</td>
        <td>${escapeHtml(i.assignee)}</td>
        <td>${escapeHtml(i.status)}</td>
        <td class="mm-detail">${escapeHtml(i.detail || '')}</td>
    </tr>`).join('');

    panel.innerHTML = head + `<div class="detail-table-wrap"><table class="data-table">
        <thead><tr><th>Issue</th><th>Resumo</th><th>Responsavel</th><th>Status</th><th>Detalhe</th></tr></thead>
        <tbody>${rows}</tbody>
    </table></div>`;
}

function escapeHtml(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
