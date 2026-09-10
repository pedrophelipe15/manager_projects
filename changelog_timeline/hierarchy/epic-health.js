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

function buildFilterOptions(stories) {
    const projects = [...new Set(stories.map(s => s.project_key).filter(Boolean))].sort();
    const statuses = [...new Set(stories.map(s => s.status).filter(Boolean))].sort();
    const assignees = [...new Set(stories.map(s => s.assignee_name).filter(Boolean))].sort();
    return { projects, statuses, assignees };
}

function renderFilters(options) {
    return `
        <div class="filters-row">
            ${renderDropdown("filter-project", "Projeto", options.projects)}
            ${renderDropdown("filter-status", "Status", options.statuses)}
            ${renderDropdown("filter-assignee", "Assignee", options.assignees)}
            <button class="btn-clear-filters" onclick="clearFilters()">Limpar</button>
        </div>
    `;
}

function renderDropdown(id, label, options) {
    const checkboxes = options.map(o => `
        <label class="dd-option">
            <input type="checkbox" value="${o}" onchange="onFilterChange()">
            <span>${o}</span>
        </label>
    `).join("");

    return `
        <div class="dd-wrapper" id="${id}">
            <button class="dd-toggle" onclick="toggleDropdown('${id}')">
                <span class="dd-label">${label}</span>
                <span class="dd-count" id="${id}-count"></span>
                <span class="dd-arrow">&#9662;</span>
            </button>
            <div class="dd-menu">${checkboxes}</div>
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

    updateCountBadges();
    renderStoriesTable();
}

function getCheckedValues(wrapperId) {
    const wrapper = document.getElementById(wrapperId);
    if (!wrapper) return [];
    return [...wrapper.querySelectorAll("input[type=checkbox]:checked")].map(cb => cb.value);
}

function updateCountBadges() {
    ["filter-project", "filter-status", "filter-assignee"].forEach(id => {
        const count = getCheckedValues(id).length;
        const badge = document.getElementById(id + "-count");
        if (badge) badge.textContent = count > 0 ? `(${count})` : "";
    });
}

function clearFilters() {
    filters = { project: [], status: [], assignee: [] };
    document.querySelectorAll(".dd-wrapper input[type=checkbox]").forEach(cb => cb.checked = false);
    updateCountBadges();
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
                <div class="kpi-label">Progresso</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">${pr.done}/${pr.total}</div>
                <div class="kpi-label">Stories Done</div>
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

        // Build filter options
        const filterOpts = buildFilterOptions(stories);

        // Cabeçalhos com sort
        const thSort = (label, col) => `<th class="sortable" onclick="handleSort('${col}')">${label}${sortIndicator(col)}</th>`;

        container.innerHTML = `
            <div class="metric-section glass">
                <h2>Throughput Mensal</h2>
                <p class="metric-desc">Stories concluidas por mes (especifico deste epico). Media: ${tp.avg_per_month || 0}/mes</p>
                <div class="chart-container">
                    <canvas id="throughput-chart"></canvas>
                </div>
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

            <div class="metric-section glass">
                <h2>Stories (<span id="stories-count">${stories.length}/${stories.length}</span>)</h2>
                <p class="metric-desc">Lista completa de stories filhas deste epico. Use os filtros para refinar.</p>
                ${renderFilters(filterOpts)}
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

        // Render throughput chart (mensal)
        renderThroughputChart(tp.monthly || tp.weekly);

    } catch (err) {
        container.innerHTML = `<p class="empty-state">Erro ao carregar detalhes: ${err.message}</p>`;
        console.error(err);
    }
}

function renderThroughputChart(data) {
    const ctx = document.getElementById("throughput-chart");
    if (!ctx) return;

    const labels = data.map(d => d.month || d.week.replace(/^\d{4}-/, ""));
    const doneValues = data.map(d => d.done !== undefined ? d.done : (d.count || 0));
    const canceledValues = data.map(d => d.canceled || 0);
    const hasCanceled = canceledValues.some(v => v > 0);

    if (throughputChart) throughputChart.destroy();

    const datasets = [
        {
            label: "Done",
            data: doneValues,
            backgroundColor: "rgba(16, 185, 129, 0.7)",
            borderColor: "rgba(16, 185, 129, 1)",
            borderWidth: 1,
            borderRadius: 4,
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
        });
    }

    throughputChart = new Chart(ctx, {
        type: "bar",
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: hasCanceled, position: "bottom", labels: { color: "#f8fafc", font: { size: 11 } } },
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
