/**
 * Initiative Health — Visão corporativa por iniciativa.
 * Se ?key=INI-123 na URL, mostra detalhes dessa iniciativa (épicos filhos).
 * Caso contrário, mostra lista de todas as iniciativas.
 */

const MS_TO_DAYS = 1 / 86400000;
let throughputChart = null;

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
            container.innerHTML = `<p class="empty-state">Nenhuma iniciativa encontrada no hierarchy.db. Execute uma sincronizacao primeiro.</p>`;
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
                <p class="metric-desc">Visao corporativa. Clique em uma iniciativa para ver os epicos filhos com detalhes.</p>
                <table class="metric-table">
                    <thead>
                        <tr>
                            <th>Key</th>
                            <th>Iniciativa</th>
                            <th>Progresso</th>
                            <th>Stories Done/Total</th>
                            <th>Epicos</th>
                            <th>Times</th>
                            <th>Forecast P85</th>
                            <th>Risco</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
                <details class="formula-details">
                    <summary>Como e calculado?</summary>
                    <div class="formula-content">
                        <p><strong>Progresso:</strong> Stories Done de todos os epicos / Total de stories (ponderado)</p>
                        <p><strong>Risco corporativo:</strong> Composicao dos riscos individuais dos epicos filhos</p>
                        <p><strong>Forecast P85:</strong> Monte Carlo com throughput agregado de toda a iniciativa</p>
                        <p><strong>Times:</strong> Projetos distintos que possuem stories filhas nos epicos</p>
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
        const res = await fetch(`/api/hierarchy/initiative-health?key=${key}`);
        if (!res.ok) {
            container.innerHTML = `<p class="empty-state">Iniciativa "${key}" nao encontrada.</p>`;
            return;
        }

        const data = await res.json();
        const ini = data.initiative;
        const pr = data.progress;
        const fc = data.forecast;
        const tp = data.throughput;
        const mt = data.metrics;

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
                <div class="kpi-label">Progresso Planejado Proximas 5 Semanas</div>
                <div class="kpi-sublabel">${formatDateBR(pr.planned_range.start)} a ${formatDateBR(pr.planned_range.end)}</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">${pr.done_stories}/${pr.total_stories}</div>
                <div class="kpi-label">Stories Done</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value warning">${pr.pending_count}</div>
                <div class="kpi-label">Atividades Pendentes</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">${riskBadge(data.risk)}</div>
                <div class="kpi-label">Risco Corporativo</div>
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
                    <td><strong>${jiraLink(ep.key)}</strong></td>
                    <td style="max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${ep.summary}</td>
                    <td>${progressBar(epr.progress_pct, 80)}</td>
                    <td style="text-align:center">${epr.done}/${epr.total}</td>
                    <td style="text-align:center">${efc.p85 > 0 ? efc.p85 + "w" : "—"}</td>
                    <td style="text-align:center">${formatDays(e.metrics.avg_cycle_time_ms)}</td>
                    <td style="text-align:center">${formatDays(e.metrics.avg_lead_time_ms)}</td>
                    <td>${riskBadge(e.risk)}</td>
                </tr>
            `;
        }

        container.innerHTML = `
            <div class="metric-section glass">
                <h2>Throughput Agregado</h2>
                <p class="metric-desc">Stories concluidas por mes (todos os epicos da iniciativa). Media: ${tp.avg_per_month || 0}/mes</p>
                <div class="chart-container">
                    <canvas id="throughput-chart"></canvas>
                </div>
            </div>

            <div class="metric-section glass">
                <h2>Epicos (${data.epics.length})</h2>
                <p class="metric-desc">Epicos filhos com metricas individuais. Clique para ver detalhes do epico.</p>
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

            <div style="text-align:center; margin-top:1rem;">
                <a href="/hierarchy/dashboard-v2.html" class="nav-link" style="color:var(--accent)">&larr; Voltar para todas as iniciativas</a>
            </div>
        `;

        // Render throughput chart (mensal) com pending stories por due_date
        renderThroughputChart(tp.monthly || tp.weekly, tp.pending_monthly || []);

    } catch (err) {
        container.innerHTML = `<p class="empty-state">Erro ao carregar detalhes: ${err.message}</p>`;
        console.error(err);
    }
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
                legend: { display: hasCanceled || hasPending, position: "bottom", labels: { color: "#f8fafc", font: { size: 11 } } },
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
