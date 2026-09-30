/**
 * Epic Health — Detalhes de saúde de um épico específico ou visão geral.
 * Se ?key=EPIC-123 na URL, mostra detalhes desse épico.
 * Caso contrário, mostra tabela geral.
 * As stories do épico são exploradas via painel de detalhe dos big numbers (KPIs).
 */

const MS_TO_DAYS = 1 / 86400000;
let throughputChart = null;
let allStories = []; // dados brutos das stories do épico (fonte do painel de detalhe dos KPIs)

function formatDays(ms) {
    if (!ms || ms <= 0) return "—";
    const days = ms * MS_TO_DAYS;
    return days < 1 ? `${Math.round(days * 24)}h` : `${Math.round(days)}d`;
}

// Formata 'YYYY-MM-DD' -> 'DD/MM/YYYY' sem shift de fuso (mesmo padrão do initiative-health)
function formatDateBR(isoDate) {
    if (!isoDate) return "—";
    const [y, m, d] = isoDate.split("-");
    return `${d}/${m}/${y}`;
}

// Formata timestamp ISO (com ou sem hora) -> 'DD/MM/YYYY'. Usa só a parte da data.
function formatTimestampBR(iso) {
    if (!iso) return "—";
    const datePart = String(iso).split("T")[0];
    return formatDateBR(datePart);
}

function statusRowClass(status) {
    switch (status) {
        case "Done": return "row-done";
        case "In Progress": return "row-in-progress";
        case "Blocked": return "row-blocked";
        case "Test": return "row-test";
        case "Waiting for Delivery": return "row-waiting";
        case "Canceled": case "Reject": return "row-canceled";
        default: return "";
    }
}

function jiraLink(key) {
    return `<a href="https://jiraps.atlassian.net/browse/${key}" target="_blank" rel="noopener" style="color:var(--accent);text-decoration:none">${key}</a>`;
}

function riskBadge(risk) {
    const labels = { done: "Done", low: "Low", medium: "Medium", high: "High", critical: "Critical" };
    return `<span class="risk-badge risk-${risk}">${labels[risk] || risk}</span>`;
}

function progressBar(pct, width = 80) {
    let color = "blue";
    if (pct >= 80) color = "green";
    else if (pct >= 50) color = "blue";
    else if (pct >= 25) color = "amber";
    else color = "red";
    return `<div class="progress-bar" style="width:${width}px"><div class="progress-fill ${color}" style="width:${Math.min(pct, 100)}%"></div></div><span class="progress-label">${pct}%</span>`;
}

// ==================== PAGES ====================

async function init() {
    const params = new URLSearchParams(window.location.search);
    const key = params.get("key");

    if (key) {
        await loadEpicDetail(key);
    } else {
        await loadAllEpics();
    }
}

async function loadAllEpics() {
    const container = document.getElementById("content-container");
    try {
        const res = await fetch("/api/hierarchy/epic-health");
        const data = await res.json();

        let rows = "";
        for (const e of data.epics) {
            const ep = e.epic;
            const pr = e.progress;
            const fc = e.forecast;
            rows += `
                <tr class="clickable" onclick="window.location.href='?key=${ep.key}'">
                    <td><strong>${jiraLink(ep.key)}</strong></td>
                    <td style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${ep.summary}</td>
                    <td>${progressBar(pr.progress_pct)}</td>
                    <td style="text-align:center">${pr.done}/${pr.total}</td>
                    <td style="text-align:center">${fc.p85 > 0 ? fc.p85 + "w" : "—"}</td>
                    <td style="text-align:center">${formatDays(e.metrics.avg_cycle_time_ms)}</td>
                    <td>${riskBadge(e.risk)}</td>
                </tr>
            `;
        }

        container.innerHTML = `
            <div class="metric-section glass">
                <h2>Todos os Epicos</h2>
                <p class="metric-desc">Clique em um epico para ver detalhes de throughput, forecast e stories.</p>
                <table class="metric-table">
                    <thead>
                        <tr>
                            <th>Key</th>
                            <th>Epic</th>
                            <th>Progresso</th>
                            <th>Done/Total</th>
                            <th>Forecast P85</th>
                            <th>Cycle Time</th>
                            <th>Risco</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;
    } catch (err) {
        container.innerHTML = `<p class="empty-state">Erro ao carregar: ${err.message}</p>`;
    }
}

async function loadEpicDetail(key) {
    const container = document.getElementById("content-container");
    const kpiContainer = document.getElementById("kpi-container");
    const titleEl = document.getElementById("page-title");
    const subtitleEl = document.getElementById("page-subtitle");

    try {
        const [healthRes, treeRes] = await Promise.all([
            fetch(`/api/hierarchy/epic-health?key=${key}`),
            fetch(`/api/hierarchy/tree?key=${key}`),
        ]);

        if (!healthRes.ok) {
            container.innerHTML = `<p class="empty-state">Epico "${key}" nao encontrado.</p>`;
            return;
        }

        const health = await healthRes.json();
        const tree = await treeRes.json();
        const ep = health.epic;
        const pr = health.progress;
        const fc = health.forecast;
        const tp = health.throughput;
        const mt = health.metrics;

        // Update header
        titleEl.textContent = `${ep.key}: ${ep.summary}`;
        subtitleEl.textContent = `Status: ${ep.status} | Projeto: ${ep.project_key}`;

        // KPIs
        kpiContainer.style.display = "grid";
        // Cards com data-metric sao clicaveis e abrem o painel de detalhe abaixo.
        kpiContainer.innerHTML = `
            <div class="kpi-card kpi-clickable" data-metric="all" onclick="showKpiDetail('all')" title="Ver todas as stories">
                <div class="kpi-value accent">${pr.progress_pct}%</div>
                <div class="kpi-label">Progresso Atual</div>
            </div>
            <div class="kpi-card kpi-clickable" data-metric="planned" onclick="showKpiDetail('planned')" title="Ver stories pendentes com due date nas proximas 5 semanas">
                <div class="kpi-value accent">${pr.planned_progress_pct ?? 0}%</div>
                <div class="kpi-label">Progresso Planejado Proximas 5 Semanas</div>
                ${pr.planned_range ? `<div class="kpi-sublabel">${formatDateBR(pr.planned_range.start)} a ${formatDateBR(pr.planned_range.end)}</div>` : ""}
            </div>
            <div class="kpi-card kpi-clickable" data-metric="done" onclick="showKpiDetail('done')" title="Ver stories concluidas">
                <div class="kpi-value">${pr.done}/${pr.total}</div>
                <div class="kpi-label">Stories Done</div>
            </div>
            <div class="kpi-card kpi-clickable" data-metric="pending" onclick="showKpiDetail('pending')" title="Ver atividades pendentes">
                <div class="kpi-value warning">${pr.pending_count ?? 0}</div>
                <div class="kpi-label">Atividades Pendentes</div>
            </div>
            <div class="kpi-card kpi-clickable" data-metric="no_duedate" onclick="showKpiDetail('no_duedate')" title="Ver pendentes sem due date">
                <div class="kpi-value ${(pr.no_duedate_count ?? 0) > 0 ? 'danger' : ''}">${pr.no_duedate_count ?? 0}</div>
                <div class="kpi-label">Pendentes sem Due Date</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">${riskBadge(health.risk)}</div>
                <div class="kpi-label">Risco</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">${formatDays(mt.avg_cycle_time_ms)}</div>
                <div class="kpi-label">Cycle Time Medio</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">${formatDays(mt.avg_lead_time_ms)}</div>
                <div class="kpi-label">Lead Time Medio</div>
            </div>
        `;

        // Armazena stories para filtros/ordenação
        const stories = tree.epic ? tree.epic.stories || [] : [];
        allStories = stories;

        // Janela do "Progresso Planejado" + reset do painel de detalhe dos KPIs.
        plannedRange = pr.planned_range || null;
        kpiActiveMetric = null;
        kpiDetailState = null;
        const kpiPanel = document.getElementById("kpi-detail-panel");
        if (kpiPanel) { kpiPanel.style.display = "none"; kpiPanel.innerHTML = ""; }

        container.innerHTML = `
            <div class="metric-section glass">
                <h2>Throughput Mensal</h2>
                <p class="metric-desc">Stories concluidas por mes (especifico deste epico). Media: ${tp.avg_per_month || 0}/mes</p>
                <div class="chart-container">
                    <canvas id="throughput-chart"></canvas>
                </div>
            </div>

            <div style="text-align:center; margin-top:1rem;">
                <a href="/hierarchy/dashboard-v2.html" class="nav-link" style="color:var(--accent)">&larr; Voltar para todos os epicos</a>
            </div>
        `;

        // Move o painel de detalhe para logo abaixo do grafico (primeira metric-section).
        if (kpiPanel) {
            const chartSection = container.querySelector(".metric-section");
            if (chartSection) chartSection.insertAdjacentElement("afterend", kpiPanel);
        }

        // Render throughput chart (mensal) com pendentes por due_date + pendentes sem data
        renderThroughputChart(tp.monthly || tp.weekly, tp.pending_monthly || [], pr.no_duedate_count || 0);

    } catch (err) {
        container.innerHTML = `<p class="empty-state">Erro ao carregar detalhes: ${err.message}</p>`;
        console.error(err);
    }
}

function renderThroughputChart(data, pendingData, noDueDateCount) {
    const ctx = document.getElementById("throughput-chart");
    if (!ctx) return;

    pendingData = pendingData || [];
    noDueDateCount = noDueDateCount || 0;

    // Calendário fixo 2026 (Jan-Dez) — mesmo padrão do initiative-health.
    // Se houver pendentes sem due_date, adiciona uma coluna extra "Sem data" ao final.
    const monthLabels = [];
    for (let m = 1; m <= 12; m++) monthLabels.push(`2026-${String(m).padStart(2, "0")}`);
    const hasNoDate = noDueDateCount > 0;
    const labels = hasNoDate ? [...monthLabels, "Sem data"] : monthLabels;
    const extra = hasNoDate ? 1 : 0; // slot extra no fim dos arrays

    const doneValues = monthLabels.map(label => {
        const match = data.find(d => d.month === label);
        return match ? (match.done !== undefined ? match.done : (match.count || 0)) : 0;
    }).concat(Array(extra).fill(0));
    const canceledValues = monthLabels.map(label => {
        const match = data.find(d => d.month === label);
        return match ? (match.canceled || 0) : 0;
    }).concat(Array(extra).fill(0));
    const hasCanceled = canceledValues.some(v => v > 0);

    // Pending stories por due_date (calendário fixo 2026) — barra amarela, stack separado
    const pendingValues = monthLabels.map(label => {
        const match = pendingData.find(p => p.month === label);
        return match ? match.pending : 0;
    }).concat(Array(extra).fill(0));
    const hasPending = pendingValues.some(v => v > 0);

    // Pendentes SEM due_date — barra cinza, só na coluna "Sem data"
    const noDateValues = hasNoDate ? [...Array(12).fill(0), noDueDateCount] : [];

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

    if (hasNoDate) {
        datasets.push({
            label: "Pendentes sem due date",
            data: noDateValues,
            backgroundColor: "rgba(148, 163, 184, 0.6)",
            borderColor: "rgba(148, 163, 184, 1)",
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
                legend: { display: hasCanceled || hasPending || hasNoDate, position: "bottom", labels: { color: "#f8fafc", font: { size: 11 } } },
                datalabels: {
                    color: "#f8fafc",
                    font: { size: 16, weight: "bold" },
                    anchor: "center",
                    align: "center",
                    formatter: (val) => val > 0 ? val : "",
                },
            },
            scales: {
                x: {
                    stacked: true,
                    grid: { color: "rgba(255,255,255,0.05)" },
                    ticks: { color: "#94a3b8", font: { size: 12 } },
                },
                y: {
                    stacked: true,
                    beginAtZero: true,
                    grid: { color: "rgba(255,255,255,0.05)" },
                    ticks: {
                        color: "#94a3b8",
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
// Mesmo padrao de minha-visao.js: ao clicar num KPI, abre um painel inline abaixo
// listando as issues correspondentes, com filtros dropdown, ordenacao e paginacao.

let kpiActiveMetric = null;   // metric atualmente aberto
let kpiDetailState = null;    // { all, filters, sort, page, pageSize }
let plannedRange = null;      // { start, end } — janela do "Progresso Planejado"

const KPI_METRICS = {
    all:     { title: "Todas as stories",        desc: "Todas as stories filhas deste epico." },
    planned: { title: "Progresso Planejado (5 semanas)", desc: "Stories pendentes com due date dentro da janela planejada." },
    done:    { title: "Stories Done",            desc: "Stories concluidas neste epico." },
    pending: { title: "Atividades Pendentes",    desc: "Stories que ainda nao foram concluidas nem canceladas." },
    no_duedate: { title: "Pendentes sem Due Date", desc: "Stories pendentes sem due date definido — nao entram no calendario do grafico nem no Progresso Planejado." },
};

const DONE_STATUS = new Set(["Done"]);
const CANCELED_STATUS = new Set(["Canceled", "Reject"]);

function isDone(s) { return DONE_STATUS.has(s.status); }
function isCanceled(s) { return CANCELED_STATUS.has(s.status); }
function isPending(s) { return !isDone(s) && !isCanceled(s); }

// Retorna o subconjunto de allStories correspondente ao metric clicado.
function storiesForMetric(metric) {
    switch (metric) {
        case "done": return allStories.filter(isDone);
        case "pending": return allStories.filter(isPending);
        case "no_duedate": return allStories.filter(s => isPending(s) && !s.due_date);
        case "planned": {
            const inWindow = (s) => {
                if (!s.due_date) return false;
                if (!plannedRange) return isPending(s);
                return isPending(s) && s.due_date >= plannedRange.start && s.due_date <= plannedRange.end;
            };
            return allStories.filter(inWindow);
        }
        case "all":
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

    // Toggle: clicar de novo no mesmo KPI fecha o painel.
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

    const meta = KPI_METRICS[metric] || KPI_METRICS.all;
    const rows = storiesForMetric(metric);
    kpiDetailState = {
        title: meta.title,
        description: meta.desc,
        all: rows,
        filters: { project: [], assignee: [], status: [] },
        sort: { col: null, dir: "asc" },
        page: 1, pageSize: 15,
    };
    panel.style.display = "block";
    renderKpiDetail();
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

const KPI_DETAIL_COLS = [
    { key: "key",        label: "Issue",       type: "text" },
    { key: "summary",    label: "Resumo",      type: "text" },
    { key: "assignee",   label: "Assignee",    type: "text" },
    { key: "status",     label: "Status",      type: "text" },
    { key: "due_date",   label: "Due Date",    type: "date" },
    { key: "created_at", label: "Criado em",   type: "date" },
    { key: "updated_at", label: "Atualizado em", type: "date" },
];

// Valor de uma coluna do detalhe (normaliza assignee).
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

// Aplica filtros ativos, opcionalmente ignorando uma coluna (para cascata).
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
        <span class="detail-pager-page">Pag. ${st.page}/${totalPages}</span>
        <button class="detail-pager-btn" onclick="kpiDetailPage(1)"${st.page >= totalPages ? " disabled" : ""} title="Proxima">&#8250;</button>
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
        : `<div class="dd-option" style="opacity:.6">Sem opcoes</div>`;
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
    // Poda selecoes que se tornaram invalidas nos outros filtros (cascata).
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
