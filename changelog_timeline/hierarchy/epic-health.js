/**
 * Epic Health — Detalhes de saúde de um épico específico ou visão geral.
 * Se ?key=EPIC-123 na URL, mostra detalhes desse épico.
 * Caso contrário, mostra tabela geral.
 * Inclui: filtros multi-select (projeto, status, assignee) + ordenação em todas as colunas.
 */

const MS_TO_DAYS = 1 / 86400000;
let throughputChart = null;
let allStories = []; // dados brutos para filtros/ordenação
let currentSort = { col: null, asc: true };
let filters = { project: [], status: [], assignee: [] };

function formatDays(ms) {
    if (!ms || ms <= 0) return "—";
    const days = ms * MS_TO_DAYS;
    return days < 1 ? `${Math.round(days * 24)}h` : `${Math.round(days)}d`;
}

function formatDate(dateStr) {
    if (!dateStr) return "—";
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString("pt-BR");
    } catch { return "—"; }
}

// Formata 'YYYY-MM-DD' -> 'DD/MM/YYYY' sem shift de fuso (mesmo padrão do initiative-health)
function formatDateBR(isoDate) {
    if (!isoDate) return "—";
    const [y, m, d] = isoDate.split("-");
    return `${d}/${m}/${y}`;
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

// ==================== FILTROS MULTI-SELECT (Dropdown com Checkboxes) ====================

// Filtros dinâmicos e cascateantes (hierarquia: Projeto → Status → Assignee).
// Cada nível recalcula as opções dos níveis inferiores com base no que já foi
// selecionado acima, preservando as seleções válidas. Padrão: hierarchy/roadmap.js.

function buildDropdown(id, label, options, selected) {
    const cbs = options.map(o => {
        const checked = selected.includes(o) ? " checked" : "";
        return `<label class="dd-option"><input type="checkbox" value="${o}"${checked} onchange="onFilterChange()"><span>${o}</span></label>`;
    }).join("");
    const count = selected.length;
    const countHtml = count > 0 ? `(${count})` : "";
    return `<div class="dd-wrapper" id="${id}"><button class="dd-toggle" onclick="toggleDropdown('${id}')"><span class="dd-label">${label}</span><span class="dd-count" id="${id}-count">${countHtml}</span><span class="dd-arrow">&#9662;</span></button><div class="dd-menu">${cbs}</div></div>`;
}

// Aplica todos os filtros EXCETO o informado em `except`.
// Assim cada dropdown mostra apenas opções coerentes com as seleções dos demais
// (cascata bidirecional: selecionar Status limita os Projetos, e vice-versa).
function storiesFilteredExcept(except) {
    return allStories.filter(s => {
        if (except !== "project" && filters.project.length > 0 && !filters.project.includes(s.project_key)) return false;
        if (except !== "status" && filters.status.length > 0 && !filters.status.includes(s.status)) return false;
        if (except !== "assignee" && filters.assignee.length > 0 && !filters.assignee.includes(s.assignee_name)) return false;
        return true;
    });
}

function renderFilters() {
    // Cada campo considera os filtros dos OUTROS campos (não o próprio),
    // permitindo múltipla seleção dentro de um mesmo campo sem se autoexcluir.
    const projectOptions = [...new Set(storiesFilteredExcept("project").map(s => s.project_key).filter(Boolean))].sort();
    const statusOptions = [...new Set(storiesFilteredExcept("status").map(s => s.status).filter(Boolean))].sort();
    const assigneeOptions = [...new Set(storiesFilteredExcept("assignee").map(s => s.assignee_name).filter(Boolean))].sort();

    // Remove seleções que deixaram de existir no contexto atual.
    filters.project = filters.project.filter(p => projectOptions.includes(p));
    filters.status = filters.status.filter(s => statusOptions.includes(s));
    filters.assignee = filters.assignee.filter(a => assigneeOptions.includes(a));

    return `
        <div class="filters-row">
            ${buildDropdown("filter-project", "Projeto", projectOptions, filters.project)}
            ${buildDropdown("filter-status", "Status", statusOptions, filters.status)}
            ${buildDropdown("filter-assignee", "Assignee", assigneeOptions, filters.assignee)}
            <button class="btn-clear-filters" onclick="clearFilters()">Limpar</button>
        </div>
    `;
}

function toggleDropdown(id) {
    const wrapper = document.getElementById(id);
    const menu = wrapper.querySelector(".dd-menu");
    const isOpen = menu.classList.contains("open");

    // Fecha todos
    document.querySelectorAll(".dd-menu.open").forEach(m => m.classList.remove("open"));

    if (!isOpen) menu.classList.add("open");
}

function onFilterChange() {
    filters.project = getCheckedValues("filter-project");
    filters.status = getCheckedValues("filter-status");
    filters.assignee = getCheckedValues("filter-assignee");

    // Reconstrói a linha de filtros (opções cascateantes + badges + seleções preservadas)
    const filtersContainer = document.querySelector("#stories-section .filters-row");
    if (filtersContainer) filtersContainer.outerHTML = renderFilters();

    renderStoriesTable();
}

function getCheckedValues(wrapperId) {
    const wrapper = document.getElementById(wrapperId);
    if (!wrapper) return [];
    return [...wrapper.querySelectorAll("input[type=checkbox]:checked")].map(cb => cb.value);
}

function clearFilters() {
    filters = { project: [], status: [], assignee: [] };
    const filtersContainer = document.querySelector("#stories-section .filters-row");
    if (filtersContainer) filtersContainer.outerHTML = renderFilters();
    renderStoriesTable();
}

function bindFilterEvents() {
    // Fecha dropdown ao clicar fora
    document.addEventListener("click", (e) => {
        if (!e.target.closest(".dd-wrapper")) {
            document.querySelectorAll(".dd-menu.open").forEach(m => m.classList.remove("open"));
        }
    });
}

// ==================== ORDENAÇÃO ====================

function sortStories(stories, col, asc) {
    return [...stories].sort((a, b) => {
        let va = getSortValue(a, col);
        let vb = getSortValue(b, col);
        if (va === null || va === undefined || va === "—") va = "";
        if (vb === null || vb === undefined || vb === "—") vb = "";
        if (typeof va === "number" && typeof vb === "number") {
            return asc ? va - vb : vb - va;
        }
        return asc ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
    });
}

function getSortValue(story, col) {
    switch (col) {
        case "key": return story.key;
        case "linked_key": return (story.issue_links || []).map(l => l.linked_key).join(",");
        case "summary": return story.summary;
        case "status": return story.status;
        case "assignee": return story.assignee_name || "";
        case "project": return story.project_key || "";
        case "created": return story.created_at || "";
        case "resolved": return story.resolved_at || "";
        case "due_date": return story.due_date || "";
        case "cycle_time": return story.cycle_time_ms || 0;
        case "lead_time": return story.lead_time_ms || 0;
        case "subtasks": return (story.subtasks || []).length;
        default: return "";
    }
}

function handleSort(col) {
    if (currentSort.col === col) {
        currentSort.asc = !currentSort.asc;
    } else {
        currentSort.col = col;
        currentSort.asc = true;
    }
    renderStoriesTable();
}

function sortIndicator(col) {
    if (currentSort.col !== col) return " ↕";
    return currentSort.asc ? " ↑" : " ↓";
}

// ==================== RENDER TABELA STORIES ====================

function renderStoriesTable() {
    const tbody = document.getElementById("stories-tbody");
    const countEl = document.getElementById("stories-count");
    if (!tbody) return;

    // Aplica filtros
    let filtered = allStories;
    if (filters.project.length > 0) filtered = filtered.filter(s => filters.project.includes(s.project_key));
    if (filters.status.length > 0) filtered = filtered.filter(s => filters.status.includes(s.status));
    if (filters.assignee.length > 0) filtered = filtered.filter(s => filters.assignee.includes(s.assignee_name));

    // Aplica ordenação
    if (currentSort.col) {
        filtered = sortStories(filtered, currentSort.col, currentSort.asc);
    }

    // Atualiza contador
    if (countEl) countEl.textContent = `${filtered.length}/${allStories.length}`;

    // Render
    tbody.innerHTML = filtered.map(s => {
        const lt = formatDays(s.lead_time_ms);
        const ct = formatDays(s.cycle_time_ms);
        const subtaskCount = (s.subtasks || []).length;
        const rowClass = statusRowClass(s.status);
        const created = formatDate(s.created_at);
        const resolved = formatDate(s.resolved_at);
        const dueDate = formatDate(s.due_date);
        const linkedKeys = (s.issue_links || []).map(l => jiraLink(l.linked_key)).join(", ") || "—";
        return `
            <tr class="${rowClass}">
                <td><strong>${jiraLink(s.key)}</strong></td>
                <td>${linkedKeys}</td>
                <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${(s.summary || '').replace(/"/g, '&quot;')}">${s.summary}</td>
                <td>${s.status}</td>
                <td style="text-align:center">${s.assignee_name || "—"}</td>
                <td style="text-align:center">${s.project_key || "—"}</td>
                <td style="text-align:center">${created}</td>
                <td style="text-align:center">${resolved}</td>
                <td style="text-align:center">${dueDate}</td>
                <td style="text-align:center">${ct}</td>
                <td style="text-align:center">${lt}</td>
                <td style="text-align:center">${subtaskCount}</td>
            </tr>
        `;
    }).join("");
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
        kpiContainer.innerHTML = `
            <div class="kpi-card">
                <div class="kpi-value accent">${pr.progress_pct}%</div>
                <div class="kpi-label">Progresso Atual</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value accent">${pr.planned_progress_pct ?? 0}%</div>
                <div class="kpi-label">Progresso Planejado Proximas 5 Semanas</div>
                ${pr.planned_range ? `<div class="kpi-sublabel">${formatDateBR(pr.planned_range.start)} a ${formatDateBR(pr.planned_range.end)}</div>` : ""}
            </div>
            <div class="kpi-card">
                <div class="kpi-value">${pr.done}/${pr.total}</div>
                <div class="kpi-label">Stories Done</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value warning">${pr.pending_count ?? 0}</div>
                <div class="kpi-label">Atividades Pendentes</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value ${fc.p85 >= 12 ? 'danger' : fc.p85 >= 8 ? 'warning' : ''}">${fc.p85 > 0 ? fc.p85 + "w" : "—"}</div>
                <div class="kpi-label">Forecast P85</div>
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

        // Cabeçalhos com sort
        const thSort = (label, col) => `<th class="sortable" onclick="handleSort('${col}')">${label}${sortIndicator(col)}</th>`;

        container.innerHTML = `
            <div class="metric-section glass">
                <h2>Throughput Mensal</h2>
                <p class="metric-desc">Stories concluidas por mes (especifico deste epico). Media: ${tp.avg_per_month || 0}/mes</p>
                <div class="chart-container">
                    <canvas id="throughput-chart"></canvas>
                </div>
                ${(() => {
                    const somaBarras = (tp.pending_monthly || []).reduce((a, p) => a + (p.pending || 0), 0);
                    const semData = pr.no_duedate_count || 0;
                    const foraCalendario = Math.max(0, (pr.pending_count || 0) - somaBarras - semData);
                    if (semData === 0 && foraCalendario === 0) return "";
                    const partes = [];
                    if (semData > 0) partes.push(`<strong>${semData} sem due date</strong> (coluna cinza "Sem data")`);
                    if (foraCalendario > 0) partes.push(`<strong>${foraCalendario} com due date fora de 2026</strong> (nao cabem no calendario do grafico)`);
                    return `<div class="pending-alert"><span class="pending-alert-icon">⚠</span><span>Das <strong>${pr.pending_count}</strong> pendentes, ${partes.join(" e ")} nao aparecem nas barras amarelas. Todas contam em "Atividades Pendentes"; apenas as com due date nos proximos 35 dias entram no "Progresso Planejado".</span></div>`;
                })()}
            </div>

            <div class="metric-section glass">
                <h2>Forecast Monte Carlo</h2>
                <p class="metric-desc">Previsao de conclusao baseada em ${tp.weekly.length} semanas de historico (${pr.remaining} stories restantes)</p>
                <div class="kpi-grid" style="margin-top:1rem">
                    <div class="kpi-card">
                        <div class="kpi-value">${fc.p50 > 0 ? fc.p50 + "w" : "—"}</div>
                        <div class="kpi-label">P50 (otimista)</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-value">${fc.p70 > 0 ? fc.p70 + "w" : "—"}</div>
                        <div class="kpi-label">P70</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-value accent">${fc.p85 > 0 ? fc.p85 + "w" : "—"}</div>
                        <div class="kpi-label">P85 (referencia)</div>
                    </div>
                    <div class="kpi-card">
                        <div class="kpi-value">${fc.p95 > 0 ? fc.p95 + "w" : "—"}</div>
                        <div class="kpi-label">P95 (pessimista)</div>
                    </div>
                </div>
                ${ep.due_date ? `<p class="sync-info" style="margin-top:0.75rem">Due date: ${new Date(ep.due_date).toLocaleDateString("pt-BR")}</p>` : ""}
                <details class="formula-details">
                    <summary>Como e calculado?</summary>
                    <div class="formula-content">
                        <p><strong>Monte Carlo:</strong> 1000 simulacoes aleatorias usando o throughput semanal historico deste epico.</p>
                        <p>Cada simulacao sorteia valores de throughput passados ate completar as ${pr.remaining} stories restantes.</p>
                        <p><strong>P85:</strong> Em 85% das simulacoes, o epico termina em ate ${fc.p85} semanas.</p>
                    </div>
                </details>
            </div>

            <div class="metric-section glass" id="stories-section">
                <h2>Stories (<span id="stories-count">${stories.length}/${stories.length}</span>)</h2>
                <p class="metric-desc">Lista completa de stories filhas deste epico. Use os filtros para refinar (filtros aninhados: Projeto → Status → Assignee).</p>
                ${renderFilters()}
                <table class="metric-table">
                    <thead>
                        <tr>
                            ${thSort("Key", "key")}
                            ${thSort("Linked Key", "linked_key")}
                            ${thSort("Story", "summary")}
                            ${thSort("Status", "status")}
                            ${thSort("Assignee", "assignee")}
                            ${thSort("Projeto", "project")}
                            ${thSort("Created", "created")}
                            ${thSort("Resolved", "resolved")}
                            ${thSort("Due Date", "due_date")}
                            ${thSort("Cycle Time", "cycle_time")}
                            ${thSort("Lead Time", "lead_time")}
                            ${thSort("Subtasks", "subtasks")}
                        </tr>
                    </thead>
                    <tbody id="stories-tbody"></tbody>
                </table>
            </div>

            <div style="text-align:center; margin-top:1rem;">
                <a href="/hierarchy/dashboard-v2.html" class="nav-link" style="color:var(--accent)">&larr; Voltar para todos os epicos</a>
            </div>
        `;

        // Render tabela inicial
        renderStoriesTable();

        // Bind filter events
        bindFilterEvents();

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

init();
