// Wave 4: Cross-time e Portfólio
const API4 = '/api/metrics/wave4';
let crossChart = null;

document.addEventListener('DOMContentLoaded', () => {
    loadAll();
});

async function loadAll() {
    const container = document.getElementById('content-container');
    container.innerHTML = '<p class="empty-state">Carregando dados de portfolio...</p>';

    try {
        const [benchmarking, crossThroughput] = await Promise.all([
            fetch(`${API4}/benchmarking`).then(r => r.json()),
            fetch(`${API4}/cross-project-throughput`).then(r => r.json()),
        ]);

        // Carrega epic health de cada projeto
        const projectKeys = benchmarking.projects.map(p => p.project_key);
        const epicHealthResults = await Promise.all(
            projectKeys.map(k => fetch(`${API4}/epic-health?project_key=${k}`).then(r => r.json()))
        );

        renderAll(benchmarking, crossThroughput, epicHealthResults);
    } catch (e) {
        container.innerHTML = '<p class="empty-state">Erro ao carregar dados de portfolio.</p>';
        console.error(e);
    }
}

function renderAll(benchmarking, crossThroughput, epicHealthResults) {
    const container = document.getElementById('content-container');
    let html = '<div class="metrics-grid">';

    // 1. Benchmarking
    html += renderBenchmarking(benchmarking);

    // 2. Cross-project throughput
    html += renderCrossThroughput(crossThroughput);

    // 3. Epic Health (todos os projetos)
    html += renderEpicHealth(epicHealthResults);

    html += '</div>';
    container.innerHTML = html;

    // Render chart
    if (crossThroughput.weekly && crossThroughput.weekly.length > 0) {
        renderCrossChart(crossThroughput);
    }
}

// --- Benchmarking ---
function renderBenchmarking(data) {
    if (!data.projects || data.projects.length === 0) {
        return `<section class="metric-section glass">
            <h2>Benchmarking entre Projetos</h2>
            <p class="metric-desc">Sem dados.</p>
        </section>`;
    }

    let rows = data.projects.map(p => `
        <tr>
            <td><strong>${p.project_key}</strong></td>
            <td>${fmtDays(p.lead_time_p50_ms)}</td>
            <td>${fmtDays(p.lead_time_p85_ms)}</td>
            <td>${fmtDays(p.cycle_time_p50_ms)}</td>
            <td>${fmtDays(p.cycle_time_p85_ms)}</td>
            <td>${p.throughput_avg_weekly}/sem</td>
            <td>${p.flow_efficiency_avg}%</td>
            <td>${p.rework_rate_pct}%</td>
            <td>${p.active_issues}</td>
        </tr>
    `).join('');

    return `
        <section class="metric-section glass">
            <h2>Benchmarking entre Projetos</h2>
            <p class="metric-desc">Comparacao de metricas entre projetos. Nao e ranking — e para identificar praticas melhores e replicar.</p>
            <details class="formula-details">
                <summary>Como e calculado?</summary>
                <div class="formula-content">
                    <p>Cada coluna usa os mesmos calculos das waves individuais, agregados por projeto.</p>
                    <p><strong>Throughput</strong> = media de issues Done/semana nas ultimas 12 semanas.</p>
                    <p><strong>Flow Eff.</strong> = media de (tempo em In Progress / lead time) das issues Done.</p>
                    <p><strong>Rework</strong> = % de issues com transicoes para tras no fluxo.</p>
                </div>
            </details>
            <table class="metric-table">
                <thead>
                    <tr>
                        <th>Projeto</th>
                        <th>Lead P50</th>
                        <th>Lead P85</th>
                        <th>Cycle P50</th>
                        <th>Cycle P85</th>
                        <th>Throughput</th>
                        <th>Flow Eff.</th>
                        <th>Rework</th>
                        <th>Ativas</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </section>
    `;
}

// --- Cross-project throughput ---
function renderCrossThroughput(data) {
    if (!data.weekly || data.weekly.length === 0) {
        return `<section class="metric-section glass">
            <h2>Throughput Consolidado</h2>
            <p class="metric-desc">Sem dados.</p>
        </section>`;
    }

    return `
        <section class="metric-section glass">
            <h2>Throughput Consolidado (todos os projetos)</h2>
            <p class="metric-desc">Issues Done por semana de todos os projetos. Permite comparar ritmo entre times ao longo do tempo.</p>
            <details class="formula-details">
                <summary>Como e calculado?</summary>
                <div class="formula-content">
                    <p>Cada barra representa o total de issues resolvidas naquela semana, separado por projeto (cores).</p>
                    <p>Permite identificar semanas com picos (releases) e quedas (ferias, bloqueios).</p>
                </div>
            </details>
            <div class="chart-container">
                <canvas id="crossCanvas"></canvas>
            </div>
        </section>
    `;
}

function renderCrossChart(data) {
    const ctx = document.getElementById('crossCanvas').getContext('2d');
    const labels = data.weekly.map(w => w.week_label);

    const projectColors = {
        'REYK': '#3b82f6', 'STN': '#10b981', 'BL': '#f59e0b', 'BKA': '#a855f7',
    };
    const defaultColors = ['#3b82f6', '#10b981', '#f59e0b', '#a855f7', '#ef4444', '#06b6d4'];

    const datasets = data.projects.map((project, idx) => ({
        label: project,
        data: data.weekly.map(w => w.by_project[project] || 0),
        backgroundColor: (projectColors[project] || defaultColors[idx % defaultColors.length]) + 'cc',
        borderWidth: 0,
        borderRadius: 2,
    }));

    if (crossChart) crossChart.destroy();
    crossChart = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'bottom', labels: { color: '#f8fafc', font: { size: 11 } } },
                tooltip: {
                    callbacks: {
                        footer: function(items) {
                            const total = items.reduce((s, i) => s + i.raw, 0);
                            return `Total: ${total}`;
                        }
                    }
                },
                datalabels: {
                    color: "#f8fafc",
                    font: { size: 14, weight: "bold" },
                    anchor: "end",
                    align: "end",
                    display: function(context) {
                        // Mostra label apenas no último dataset (topo do stack)
                        return context.datasetIndex === context.chart.data.datasets.length - 1;
                    },
                    formatter: function(value, context) {
                        // Soma todos os datasets nesse index para mostrar o total
                        const total = context.chart.data.datasets.reduce((s, ds) => s + (ds.data[context.dataIndex] || 0), 0);
                        return total > 0 ? total : "";
                    },
                },
            },
            scales: {
                x: { stacked: true, ticks: { color: '#94a3b8', maxTicksLimit: 13, font: { size: 10 } }, grid: { display: false } },
                y: { stacked: true, ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.05)' }, beginAtZero: true }
            }
        },
        plugins: [ChartDataLabels],
    });
}

// --- Epic Health ---
function renderEpicHealth(epicHealthResults) {
    // Combina todos os épicos de todos os projetos
    let allEpics = [];
    for (const result of epicHealthResults) {
        if (result.epics) {
            for (const epic of result.epics) {
                epic._project = result.project_key;
                allEpics.push(epic);
            }
        }
    }

    // Filtra apenas não-done
    allEpics = allEpics.filter(e => e.risk !== 'done');

    if (allEpics.length === 0) {
        return `<section class="metric-section glass">
            <h2>Saude das Issues-Pai</h2>
            <p class="metric-desc">Nenhuma issue-pai aberta encontrada.</p>
        </section>`;
    }

    // Ordena por risco
    const riskOrder = { critical: 0, high: 1, medium: 2, low: 3 };
    allEpics.sort((a, b) => (riskOrder[a.risk] || 9) - (riskOrder[b.risk] || 9));

    let rows = allEpics.slice(0, 25).map(e => {
        const riskBadge = `<span class="risk-badge risk-${e.risk}">${e.risk}</span>`;
        const progressBar = `<div class="progress-bar"><div class="progress-fill" style="width:${e.progress_pct}%"></div></div>`;
        const forecast = e.forecast_p85_weeks > 0 ? `${e.forecast_p85_weeks} sem` : '--';
        const dueDate = e.due_date ? formatDateShort(e.due_date) : '--';
        return `
            <tr>
                <td>${e._project}</td>
                <td><strong><a href="https://jiraps.atlassian.net/browse/${e.key}" target="_blank" rel="noopener" style="color:#3b82f6;text-decoration:none">${e.key}</a></strong></td>
                <td style="max-width:220px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHTML(e.summary)}</td>
                <td>${e.issue_type || '--'}</td>
                <td>${e.assignee || '--'}</td>
                <td>${dueDate}</td>
                <td>${e.done}/${e.total}</td>
                <td style="min-width:90px;">${progressBar} <span class="progress-label">${e.progress_pct}%</span></td>
                <td>${forecast}</td>
                <td>${riskBadge}</td>
            </tr>
        `;
    }).join('');

    const atRisk = allEpics.filter(e => e.risk === 'critical' || e.risk === 'high').length;

    return `
        <section class="metric-section glass">
            <h2>Saude das Issues-Pai</h2>
            <p class="metric-desc">${allEpics.length} issues-pai abertas em todos os projetos. ${atRisk > 0 ? `<strong>${atRisk} em risco.</strong>` : 'Nenhuma em risco critico.'}</p>
            <details class="formula-details">
                <summary>Como e calculado?</summary>
                <div class="formula-content">
                    <p><strong>Progresso</strong> = subtasks Done / total subtasks.</p>
                    <p><strong>Forecast P85</strong> = Monte Carlo com throughput do projeto (1000 simulacoes).</p>
                    <p><strong>Risco</strong> = composicao de: due date vs forecast, progresso baixo com muitos itens restantes, e forecast longo (&gt;8 semanas).</p>
                    <p>Niveis: <span class="risk-badge risk-low">low</span> <span class="risk-badge risk-medium">medium</span> <span class="risk-badge risk-high">high</span> <span class="risk-badge risk-critical">critical</span></p>
                </div>
            </details>
            <table class="metric-table">
                <thead>
                    <tr><th>Projeto</th><th>Key</th><th>Summary</th><th>Tipo</th><th>Assignee</th><th>Due Date</th><th>Done/Total</th><th>Progresso</th><th>Forecast P85</th><th>Risco</th></tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
            ${allEpics.length > 25 ? `<p class="table-footer">Mostrando 25 de ${allEpics.length} epicos.</p>` : ''}
        </section>
    `;
}

// --- Utils ---
function fmtDays(ms) {
    if (!ms || ms === 0) return '--';
    const days = ms / (1000 * 60 * 60 * 24);
    if (days < 1) return `${Math.round(ms / (1000 * 60 * 60))}h`;
    return `${days.toFixed(1)}d`;
}

function formatDateShort(dateStr) {
    if (!dateStr) return '--';
    const parts = dateStr.split('T')[0].split('-');
    if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
    return dateStr;
}

function escapeHTML(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, tag => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[tag] || tag));
}
