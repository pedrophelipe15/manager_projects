/**
 * Initiative Health — Visão corporativa por iniciativa.
 * Se ?key=INI-123 na URL, mostra detalhes dessa iniciativa (épicos filhos).
 * Caso contrário, mostra lista de todas as iniciativas.
 */

const MS_TO_DAYS = 1 / 86400000;

// Le um token de cor do design system (tokens.css) com fallback.
function CT(name, fallback) {
    try {
        const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
        return v || fallback;
    } catch (e) {
        return fallback;
    }
}

let throughputChart = null;
let allStories = []; // stories agregadas de todos os epicos da iniciativa (fonte do painel de detalhe)

function formatDays(ms) {
    if (!ms || ms <= 0) return "—";
    const days = ms * MS_TO_DAYS;
    return days < 1 ? `${Math.round(days * 24)}h` : `${Math.round(days)}d`;
}

function formatDateBR(isoDate) {
    if (!isoDate) return "—";
    const [y, m, d] = isoDate.split("-");
    return `${d}/${m}/${y}`;
}

// Formata timestamp ISO (com ou sem hora) -> 'DD/MM/YYYY'.
function formatTimestampBR(iso) {
    if (!iso) return "—";
    return formatDateBR(String(iso).split("T")[0]);
}

function statusRowClass(status) {
    switch (status) {
        case "Done": case "Resolved": return "row-done";
        case "In Progress": return "row-in-progress";
        case "Blocked": return "row-blocked";
        case "Test": return "row-test";
        case "Waiting for Delivery": return "row-waiting";
        case "Canceled": case "Reject": return "row-canceled";
        default: return "";
    }
}

function riskBadge(risk) {
    const labels = { done: "Done", low: "Low", medium: "Medium", high: "High", critical: "Critical" };
    return `<span class="risk-badge risk-${risk}">${labels[risk] || risk}</span>`;
}

function jiraLink(key) {
    return `<a href="https://jiraps.atlassian.net/browse/${key}" target="_blank" rel="noopener" style="color:var(--accent);text-decoration:none">${key}</a>`;
}

function progressBar(pct, width = 100) {
    let color = "blue";
    if (pct >= 80) color = "green";
    else if (pct >= 50) color = "blue";
    else if (pct >= 25) color = "amber";
    else color = "red";
    return `<div class="progress-bar" style="width:${width}px"><div class="progress-fill ${color}" style="width:${Math.min(pct, 100)}%"></div></div><span class="progress-label">${pct}%</span>`;
}

async function init() {
    const params = new URLSearchParams(window.location.search);
    const key = params.get("key");

    if (key) {
        await loadInitiativeDetail(key);
    } else {
        await loadAllInitiatives();
    }
}

async function loadAllInitiatives() {
    const container = document.getElementById("content-container");
    try {
        const res = await fetch("/api/hierarchy/initiative-health");
        const data = await res.json();

        if (!data.initiatives || data.initiatives.length === 0) {
            container.innerHTML = `<p class="empty-state">Nenhuma iniciativa encontrada no hierarchy.db. Execute uma sincronização primeiro.</p>`;
            return;
        }

        let rows = "";
        for (const ini of data.initiatives) {
            const i = ini.initiative;
            const pr = ini.progress;
            const fc = ini.forecast;
            rows += `
                <tr class="clickable" onclick="window.location.href='?key=${i.key}'">
                    <td><strong>${jiraLink(i.key)}</strong></td>
                    <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${i.summary}</td>
                    <td>${progressBar(pr.weighted_progress_pct)}</td>
                    <td style="text-align:center">${pr.done_stories}/${pr.total_stories}</td>
                    <td style="text-align:center">${pr.total_epics}</td>
                    <td style="text-align:center">${ini.teams.length}</td>
                    <td style="text-align:center">${fc.p85 > 0 ? fc.p85 + "w" : "—"}</td>
                    <td>${riskBadge(ini.risk)}</td>
                </tr>
            `;
        }

        container.innerHTML = `
            <div class="metric-section glass">
                <h2>Iniciativas</h2>
                <p class="metric-desc">Visão corporativa. Clique em uma iniciativa para ver os épicos filhos com detalhes.</p>
                <table class="metric-table">
                    <thead>
                        <tr>
                            <th>Key</th>
                            <th>Iniciativa</th>
                            <th>Progresso</th>
                            <th>Stories Done/Total</th>
                            <th>Épicos</th>
                            <th>Times</th>
                            <th>Forecast P85</th>
                            <th>Risco</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
                <details class="formula-details">
                    <summary>Como é calculado?</summary>
                    <div class="formula-content">
                        <p><strong>Progresso:</strong> Stories Done de todos os épicos / Total de stories (ponderado)</p>
                        <p><strong>Risco corporativo:</strong> Composição dos riscos individuais dos épicos filhos</p>
                        <p><strong>Forecast P85:</strong> Monte Carlo com throughput agregado de toda a iniciativa</p>
                        <p><strong>Times:</strong> Projetos distintos que possuem stories filhas nos épicos</p>
                    </div>
                </details>
            </div>
        `;
    } catch (err) {
        container.innerHTML = `<p class="empty-state">Erro ao carregar: ${err.message}</p>`;
    }
}

async function loadInitiativeDetail(key) {
    const container = document.getElementById("content-container");
    const kpiContainer = document.getElementById("kpi-container");
    const titleEl = document.getElementById("page-title");
    const subtitleEl = document.getElementById("page-subtitle");

    try {
        const [res, treeRes] = await Promise.all([
            fetch(`/api/hierarchy/initiative-health?key=${key}`),
            fetch(`/api/hierarchy/tree?key=${key}`),
        ]);
        if (!res.ok) {
            container.innerHTML = `<p class="empty-state">Iniciativa "${key}" não encontrada.</p>`;
            return;
        }

        const data = await res.json();
        const ini = data.initiative;
        const pr = data.progress;
        const fc = data.forecast;
        const tp = data.throughput;
        const mt = data.metrics;

        // Agrega as stories de todos os epicos da iniciativa (fonte do painel de detalhe).
        const tree = treeRes.ok ? await treeRes.json() : null;
        allStories = [];
        if (tree && Array.isArray(tree.epics)) {
            for (const ep of tree.epics) {
                for (const s of (ep.stories || [])) allStories.push(s);
            }
        }
        plannedRange = pr.planned_range || null;
        kpiActiveMetric = null;
        kpiDetailState = null;
        const kpiPanelReset = document.getElementById("kpi-detail-panel");
        if (kpiPanelReset) { kpiPanelReset.style.display = "none"; kpiPanelReset.innerHTML = ""; }

        // Header
        titleEl.textContent = `${ini.key}: ${ini.summary}`;
        subtitleEl.textContent = "";

        // KPIs
        kpiContainer.style.display = "grid";
        kpiContainer.innerHTML = `
            <div class="kpi-card">
                <div class="kpi-value accent">${pr.weighted_progress_pct}%</div>
                <div class="kpi-label">Progresso Atual</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value accent">${pr.planned_progress_pct}%</div>
                <div class="kpi-label">Progresso Planejado Próximas 5 Semanas</div>
                <div class="kpi-sublabel">${formatDateBR(pr.planned_range.start)} a ${formatDateBR(pr.planned_range.end)}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">${pr.done_stories}/${pr.total_stories}</div>
                <div class="kpi-label">Stories Done</div>
            </div>
            <div class="kpi-card kpi-clickable" data-metric="pending" onclick="showKpiDetail('pending')" title="Ver atividades pendentes">
                <div class="kpi-value warning">${pr.pending_count}</div>
                <div class="kpi-label">Atividades Pendentes</div>
            </div>
            <div class="kpi-card kpi-clickable" data-metric="no_duedate" onclick="showKpiDetail('no_duedate')" title="Ver pendentes sem due date">
                <div class="kpi-value ${(pr.no_duedate_count ?? 0) > 0 ? 'danger' : ''}">${pr.no_duedate_count ?? 0}</div>
                <div class="kpi-label">Pendentes sem Due Date</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">${data.teams.length}</div>
                <div class="kpi-label">Times Envolvidos</div>
            </div>
        `;

        // Tabela de épicos filhos
        let epicRows = "";
        for (const e of data.epics) {
            const ep = e.epic;
            const epr = e.progress;
            const efc = e.forecast;
            epicRows += `
                <tr class="clickable" onclick="window.location.href='/hierarchy/epic-health.html?key=${ep.key}'">
                    <td style="white-space:nowrap"><strong>${jiraLink(ep.key)}</strong></td>
                    <td class="epic-summary-cell">${ep.summary}</td>
                    <td style="white-space:nowrap">${progressBar(epr.progress_pct, 80)}</td>
                    <td style="text-align:center;white-space:nowrap">${epr.done}/${epr.total}</td>
                    <td style="text-align:center;white-space:nowrap">${efc.p85 > 0 ? efc.p85 + "w" : "—"}</td>
                    <td style="text-align:center;white-space:nowrap">${formatDays(e.metrics.avg_cycle_time_ms)}</td>
                    <td style="text-align:center;white-space:nowrap">${formatDays(e.metrics.avg_lead_time_ms)}</td>
                    <td style="white-space:nowrap">${riskBadge(e.risk)}</td>
                </tr>
            `;
        }

        container.innerHTML = `
            <div class="metric-section glass">
                <h2>Throughput Agregado</h2>
                <p class="metric-desc">Stories concluídas por mês (todos os épicos da iniciativa). Média: ${tp.avg_per_month || 0}/mês</p>
                <div class="chart-container">
                    <canvas id="throughput-chart"></canvas>
                </div>
            </div>

            <div class="metric-section glass">
                <h2>Épicos (${data.epics.length})</h2>
                <p class="metric-desc">Épicos filhos com métricas individuais. Clique para ver detalhes do épico.</p>
                <table class="metric-table">
                    <thead>
                        <tr>
                            <th>Key</th>
                            <th>Epic</th>
                            <th>Progresso</th>
                            <th>Done/Total</th>
                            <th>Forecast P85</th>
                            <th>Cycle Time</th>
                            <th>Lead Time</th>
                            <th>Risco</th>
                        </tr>
                    </thead>
                    <tbody>${epicRows}</tbody>
                </table>
            </div>
        `;

        // "← VOLTAR" (nav do modulo) assume a funcao de voltar para a lista de
        // iniciativas quando estamos no detalhe de uma iniciativa (?key=...).
        retargetNavBackToInitiatives();

        // Move o painel de detalhe para abaixo da tabela de Epicos (ultima metric-section).
        const kpiPanel = document.getElementById("kpi-detail-panel");
        if (kpiPanel) {
            const sections = container.querySelectorAll(".metric-section");
            const lastSection = sections[sections.length - 1];
            if (lastSection) lastSection.insertAdjacentElement("afterend", kpiPanel);
        }

        // Render throughput chart (mensal) com pending stories por due_date
        renderThroughputChart(tp.monthly || tp.weekly, tp.pending_monthly || []);

    } catch (err) {
        container.innerHTML = `<p class="empty-state">Erro ao carregar detalhes: ${err.message}</p>`;
        console.error(err);
    }
}

// No detalhe de uma iniciativa, o botao "← VOLTAR" da nav do modulo passa a
// voltar para a LISTA de iniciativas (dashboard-v2) em vez do projeto principal.
// Substitui o antigo link textual "Voltar para todas as iniciativas".
function retargetNavBackToInitiatives() {
    const apply = () => {
        const back = document.querySelector("#hierarchy-nav .nav-back");
        if (!back) return false;
        back.setAttribute("href", "/hierarchy/dashboard-v2.html");
        back.setAttribute("title", "Voltar para todas as iniciativas");
        return true;
    };
    if (apply()) return;
    // A nav e injetada por nav.js; se ainda nao estiver pronta, tenta de novo.
    let tries = 0;
    const t = setInterval(() => {
        if (apply() || ++tries > 20) clearInterval(t);
    }, 50);
}

function renderThroughputChart(data, pendingData) {
    const ctx = document.getElementById("throughput-chart");
    if (!ctx) return;

    // Calendário fixo 2026 (Jan-Dez)
    const months2026 = [];
    for (let m = 1; m <= 12; m++) {
        months2026.push(`2026-${String(m).padStart(2, "0")}`);
    }

    const labels = months2026;

    // Mapeia Done e Canceled do throughput mensal para o calendário 2026
    const doneValues = labels.map(label => {
        const match = data.find(d => d.month === label);
        return match ? (match.done !== undefined ? match.done : (match.count || 0)) : 0;
    });
    const canceledValues = labels.map(label => {
        const match = data.find(d => d.month === label);
        return match ? (match.canceled || 0) : 0;
    });
    const hasCanceled = canceledValues.some(v => v > 0);

    // Pending stories por due_date (calendário fixo 2026)
    const pendingValues = labels.map(label => {
        const match = pendingData.find(p => p.month === label);
        return match ? match.pending : 0;
    });
    const hasPending = pendingValues.some(v => v > 0);

    if (throughputChart) throughputChart.destroy();

    const datasets = [
        {
            label: "Done",
            data: doneValues,
            backgroundColor: "rgba(16, 185, 129, 0.7)",
            borderColor: "rgba(16, 185, 129, 1)",
            borderWidth: 1,
            borderRadius: 4,
            stack: "throughput",
        },
    ];

    if (hasCanceled) {
        datasets.push({
            label: "Canceled",
            data: canceledValues,
            backgroundColor: "rgba(239, 68, 68, 0.7)",
            borderColor: "rgba(239, 68, 68, 1)",
            borderWidth: 1,
            borderRadius: 4,
            stack: "throughput",
        });
    }

    if (hasPending) {
        datasets.push({
            label: "Pendentes (due date)",
            data: pendingValues,
            backgroundColor: "rgba(234, 179, 8, 0.7)",
            borderColor: "rgba(234, 179, 8, 1)",
            borderWidth: 1,
            borderRadius: 4,
            stack: "pending",
        });
    }

    throughputChart = new Chart(ctx, {
        type: "bar",
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: hasCanceled || hasPending, position: "bottom", labels: { color: CT("--text-1", "#10203a"), font: { size: 11 } } },
                datalabels: {
                    color: "#ffffff",
                    font: { size: 16, weight: "bold" },
                    anchor: "center",
                    align: "center",
                    formatter: (val) => val > 0 ? val : "",
                },
            },
            scales: {
                x: {
                    stacked: true,
                    grid: { color: CT("--chart-grid", "rgba(16,32,58,0.08)") },
                    ticks: { color: CT("--text-2", "#4a5a70"), font: { size: 12 } },
                },
                y: {
                    stacked: true,
                    beginAtZero: true,
                    grid: { color: CT("--chart-grid", "rgba(16,32,58,0.08)") },
                    ticks: {
                        color: CT("--text-2", "#4a5a70"),
                        font: { size: 11 },
                        stepSize: 1,
                    },
                },
            },
        },
        plugins: [ChartDataLabels],
    });
}

// ==================== PAINEL DE DETALHE DOS BIG NUMBERS (KPIs) ====================
// Mesmo padrao de epic-health.js: ao clicar num KPI, abre um painel inline abaixo
// do grafico listando as issues correspondentes, com filtros dropdown, ordenacao e paginacao.

let kpiActiveMetric = null;
let kpiDetailState = null;
let plannedRange = null;

const KPI_METRICS = {
    pending:    { title: "Atividades Pendentes",    desc: "Stories que ainda não foram concluídas nem canceladas." },
    no_duedate: { title: "Pendentes sem Due Date", desc: "Stories pendentes sem due date definido — não entram no calendário do gráfico nem no Progresso Planejado." },
};

// "Resolved" é tratado como "Done" (status equivalentes).
const DONE_STATUS = new Set(["Done", "Resolved"]);
const CANCELED_STATUS = new Set(["Canceled", "Reject"]);
function isDone(s) { return DONE_STATUS.has(s.status); }
function isCanceled(s) { return CANCELED_STATUS.has(s.status); }
function isPending(s) { return !isDone(s) && !isCanceled(s); }

function storiesForMetric(metric) {
    switch (metric) {
        case "pending": return allStories.filter(isPending);
        case "no_duedate": return allStories.filter(s => isPending(s) && !s.due_date);
        default: return allStories.slice();
    }
}

function markActiveKpi(metric) {
    document.querySelectorAll(".kpi-card.kpi-clickable.active").forEach(c => c.classList.remove("active"));
    if (!metric) return;
    const card = document.querySelector(`.kpi-card.kpi-clickable[data-metric="${metric}"]`);
    if (card) card.classList.add("active");
}

function showKpiDetail(metric) {
    const panel = document.getElementById("kpi-detail-panel");
    if (!panel) return;

    if (kpiActiveMetric === metric) {
        kpiActiveMetric = null;
        kpiDetailState = null;
        markActiveKpi(null);
        panel.style.display = "none";
        panel.innerHTML = "";
        return;
    }

    kpiActiveMetric = metric;
    markActiveKpi(metric);

    const meta = KPI_METRICS[metric] || { title: "Detalhe", desc: "" };
    kpiDetailState = {
        title: meta.title,
        description: meta.desc,
        all: storiesForMetric(metric),
        filters: { project: [], assignee: [], status: [] },
        sort: { col: null, dir: "asc" },
        page: 1, pageSize: 15,
    };
    panel.style.display = "block";
    renderKpiDetail();
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

const KPI_DETAIL_COLS = [
    { key: "key",        label: "Issue",         type: "text" },
    { key: "summary",    label: "Resumo",        type: "text" },
    { key: "assignee",   label: "Assignee",      type: "text" },
    { key: "status",     label: "Status",        type: "text" },
    { key: "due_date",   label: "Due Date",      type: "date" },
    { key: "created_at", label: "Criado em",     type: "date" },
    { key: "updated_at", label: "Atualizado em", type: "date" },
];

function kpiCell(s, col) {
    switch (col) {
        case "project": return s.project_key || "";
        case "assignee": return s.assignee_name || "";
        case "due_date": return s.due_date || "";
        case "created_at": return s.created_at || "";
        case "updated_at": return s.updated_at || "";
        default: return s[col] == null ? "" : s[col];
    }
}

function kpiFiltered(exceptCol) {
    let rows = kpiDetailState.all;
    for (const col of ["project", "assignee", "status"]) {
        if (col === exceptCol) continue;
        const sel = kpiDetailState.filters[col];
        if (sel && sel.length) rows = rows.filter(r => sel.includes(kpiCell(r, col)));
    }
    return rows;
}

function kpiOptions(col) {
    const ctx = kpiFiltered(col);
    return [...new Set(ctx.map(r => kpiCell(r, col)).filter(v => v !== ""))].sort();
}

function kpiVisibleRows() {
    let rows = kpiFiltered(null);
    const s = kpiDetailState.sort;
    if (s.col) {
        rows = rows.slice().sort((a, b) => {
            const va = String(kpiCell(a, s.col));
            const vb = String(kpiCell(b, s.col));
            const cmp = va.localeCompare(vb, "pt-BR", { numeric: true });
            return s.dir === "asc" ? cmp : -cmp;
        });
    }
    return rows;
}

function renderKpiDetail() {
    const panel = document.getElementById("kpi-detail-panel");
    if (!panel || !kpiDetailState) return;
    const st = kpiDetailState;

    const head = `<div class="detail-head">
        <div>
            <h2>${st.title} <span class="detail-count">${st.all.length}</span></h2>
            <p class="metric-desc" style="margin:0">${st.description}</p>
        </div>
        <button class="btn-clear-filters" onclick="showKpiDetail('${kpiActiveMetric}')">Fechar</button>
    </div>`;

    if (!st.all.length) {
        panel.innerHTML = head + `<p class="empty-state">Nenhuma issue neste indicador.</p>`;
        return;
    }

    const rows = kpiVisibleRows();
    const total = rows.length;
    const totalPages = Math.max(1, Math.ceil(total / st.pageSize));
    if (st.page > totalPages) st.page = totalPages;
    if (st.page < 1) st.page = 1;
    const start = (st.page - 1) * st.pageSize;
    const pageRows = rows.slice(start, start + st.pageSize);
    const shownFrom = total ? start + 1 : 0;
    const shownTo = Math.min(start + st.pageSize, total);

    const anyFilter = st.filters.project.length || st.filters.assignee.length || st.filters.status.length;
    const pager = `<div class="detail-pager">
        <span class="detail-pager-info">${shownFrom}–${shownTo} de ${total}</span>
        <button class="detail-pager-btn" onclick="kpiDetailPage(-1)"${st.page <= 1 ? " disabled" : ""} title="Anterior">&#8249;</button>
        <span class="detail-pager-page">Pág. ${st.page}/${totalPages}</span>
        <button class="detail-pager-btn" onclick="kpiDetailPage(1)"${st.page >= totalPages ? " disabled" : ""} title="Próxima">&#8250;</button>
    </div>`;
    const filtersBar = `<div class="filters-row">
        ${kpiDropdown("project", "Projeto")}
        ${kpiDropdown("assignee", "Assignee")}
        ${kpiDropdown("status", "Status")}
        <button class="btn-clear-filters" onclick="clearKpiFilters()"${anyFilter ? "" : " disabled"}>Limpar filtros</button>
        ${pager}
    </div>`;

    const ind = (col) => st.sort.col === col ? (st.sort.dir === "asc" ? "↑" : "↓") : "↕";
    const ths = KPI_DETAIL_COLS.map(c =>
        `<th class="sortable" onclick="sortKpiDetail('${c.key}')">${c.label} <span class="sort-ind">${ind(c.key)}</span></th>`
    ).join("");

    const body = pageRows.length
        ? pageRows.map(i => `<tr class="${statusRowClass(i.status)}">
            <td>${jiraLink(i.key)}</td>
            <td class="mm-summary" title="${(i.summary || '').replace(/"/g, '&quot;')}">${i.summary || ''}</td>
            <td>${i.assignee_name || "—"}</td>
            <td>${i.status || "—"}</td>
            <td class="mm-date">${formatDateBR(i.due_date)}</td>
            <td class="mm-date">${formatTimestampBR(i.created_at)}</td>
            <td class="mm-date">${formatTimestampBR(i.updated_at)}</td>
        </tr>`).join("")
        : `<tr><td colspan="7" class="empty-state">Nenhuma issue no filtro atual.</td></tr>`;

    panel.innerHTML = head + filtersBar + `<div class="detail-table-wrap"><table class="data-table">
        <thead><tr>${ths}</tr></thead>
        <tbody>${body}</tbody>
    </table></div>`;
}

function kpiDropdown(col, label) {
    const sel = kpiDetailState.filters[col];
    const opts = kpiOptions(col);
    const count = sel.length ? `<span class="dd-count">(${sel.length})</span>` : "";
    const items = opts.length
        ? opts.map(o => {
            const checked = sel.includes(o) ? "checked" : "";
            return `<label class="dd-option">
                <input type="checkbox" value="${String(o).replace(/"/g, '&quot;')}" ${checked} onchange="onKpiFilterChange('${col}', this)">
                <span>${o}</span>
            </label>`;
        }).join("")
        : `<div class="dd-option" style="opacity:.6">Sem opções</div>`;
    return `<div class="dd-wrapper" id="kpi-dd-${col}">
        <button class="dd-toggle" onclick="toggleKpiDropdown('kpi-dd-${col}')">
            <span class="dd-label">${label}</span> ${count}
            <span class="dd-arrow">&#9662;</span>
        </button>
        <div class="dd-menu">${items}</div>
    </div>`;
}

function toggleKpiDropdown(id) {
    const menu = document.getElementById(id).querySelector(".dd-menu");
    const open = menu.classList.contains("open");
    document.querySelectorAll("#kpi-detail-panel .dd-menu.open").forEach(m => m.classList.remove("open"));
    if (!open) menu.classList.add("open");
}

function onKpiFilterChange(col, input) {
    const v = input.value;
    const sel = kpiDetailState.filters[col];
    if (input.checked) { if (!sel.includes(v)) sel.push(v); }
    else { kpiDetailState.filters[col] = sel.filter(x => x !== v); }
    for (const other of ["project", "assignee", "status"]) {
        if (other === col) continue;
        const valid = kpiOptions(other);
        kpiDetailState.filters[other] = kpiDetailState.filters[other].filter(x => valid.includes(x));
    }
    kpiDetailState.page = 1;
    renderKpiDetail();
}

function clearKpiFilters() {
    kpiDetailState.filters = { project: [], assignee: [], status: [] };
    kpiDetailState.page = 1;
    renderKpiDetail();
}

function sortKpiDetail(col) {
    const s = kpiDetailState.sort;
    if (s.col === col) { s.dir = s.dir === "asc" ? "desc" : "asc"; }
    else { s.col = col; s.dir = "asc"; }
    kpiDetailState.page = 1;
    renderKpiDetail();
}

function kpiDetailPage(delta) {
    kpiDetailState.page += delta;
    renderKpiDetail();
}

// Fecha dropdowns do painel de detalhe ao clicar fora.
document.addEventListener("click", (e) => {
    if (!e.target.closest("#kpi-detail-panel .dd-wrapper")) {
        document.querySelectorAll("#kpi-detail-panel .dd-menu.open").forEach(m => m.classList.remove("open"));
    }
});

init();
