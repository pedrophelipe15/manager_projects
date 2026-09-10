// Wave 2: Previsibilidade
const API2 = '/api/metrics/wave2';
let throughputChart = null;
let forecastChart = null;
let currentProject = null;

document.addEventListener('DOMContentLoaded', () => {
    loadProjects();
    document.getElementById('projectFilter').addEventListener('change', onProjectChange);
});

async function loadProjects() {
    try {
        const r = await fetch('/api/settings/projects');
        const projects = await r.json();
        const select = document.getElementById('projectFilter');
        projects.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.key;
            opt.textContent = `${p.key} - ${p.name}`;
            select.appendChild(opt);
        });
        if (projects.length === 1) {
            select.value = projects[0].key;
            onProjectChange();
        }
    } catch (e) { console.error(e); }
}

async function onProjectChange() {
    const key = document.getElementById('projectFilter').value;
    const container = document.getElementById('content-container');
    currentProject = key;

    if (!key) {
        container.innerHTML = '<p class="empty-state">Selecione um projeto para visualizar as metricas de previsibilidade.</p>';
        return;
    }

    container.innerHTML = '<p class="empty-state">Carregando...</p>';

    try {
        const [throughput, epics, aging] = await Promise.all([
            fetch(`${API2}/throughput?project_key=${key}`).then(r => r.json()),
            fetch(`${API2}/open-epics?project_key=${key}`).then(r => r.json()),
            fetch(`${API2}/aging-backlog?project_key=${key}`).then(r => r.json()),
        ]);
        renderAll(throughput, epics, aging);
    } catch (e) {
        container.innerHTML = '<p class="empty-state">Erro ao carregar metricas.</p>';
        console.error(e);
    }
}

function renderAll(throughput, epics, aging) {
    const container = document.getElementById('content-container');
    let html = '<div class="metrics-grid">';

    // 1. Throughput semanal
    html += renderThroughput(throughput);

    // 2. Monte Carlo Forecast (épicos abertos)
    html += renderForecastSection(epics);

    // 3. Aging Backlog
    html += renderAgingBacklog(aging);

    html += '</div>';
    container.innerHTML = html;

    // Renderiza charts após DOM
    if (throughput.weekly && throughput.weekly.length > 0) {
        renderThroughputChart(throughput);
    }
}

// --- Throughput ---
function renderThroughput(data) {
    if (!data.weekly || data.weekly.length === 0) {
        return `<section class="metric-section glass">
            <h2>Throughput Semanal</h2>
            <p class="metric-desc">Sem dados. Execute sincronizacao para popular.</p>
        </section>`;
    }

    const s = data.summary;

    return `
        <section class="metric-section glass">
            <h2>Throughput Semanal</h2>
            <p class="metric-desc">Issues concluidas por semana. Estabilidade do throughput indica previsibilidade.</p>
            <details class="formula-details">
                <summary>Como e calculado?</summary>
                <div class="formula-content">
                    <p><strong>Throughput</strong> = quantidade de issues que passaram para Done em cada semana (agrupadas pela data de resolucao).</p>
                    <p><strong>Media</strong> = soma / N semanas. <strong>Desvio padrao</strong> = variabilidade (menor = mais previsivel).</p>
                    <p><strong>Uso</strong>: alimenta o Monte Carlo Forecast. Throughput estavel = forecast confiavel.</p>
                </div>
            </details>
            <div class="kpis-row">
                <div class="kpi-box"><div class="kpi-label">Media/semana</div><div class="kpi-value">${s.avg}</div></div>
                <div class="kpi-box"><div class="kpi-label">Desvio Padrao</div><div class="kpi-value">${s.stddev}</div></div>
                <div class="kpi-box"><div class="kpi-label">Min</div><div class="kpi-value">${s.min}</div></div>
                <div class="kpi-box"><div class="kpi-label">Max</div><div class="kpi-value">${s.max}</div></div>
            </div>
            <div class="chart-container">
                <canvas id="throughputCanvas"></canvas>
            </div>
        </section>
    `;
}

function renderThroughputChart(data) {
    const ctx = document.getElementById('throughputCanvas').getContext('2d');
    const labels = data.weekly.map(w => w.week_label);
    const totals = data.weekly.map(w => w.total);
    const avg = data.summary.avg;

    if (throughputChart) throughputChart.destroy();
    throughputChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                {
                    label: 'Throughput',
                    data: totals,
                    backgroundColor: 'rgba(59, 130, 246, 0.6)',
                    borderColor: '#3b82f6',
                    borderWidth: 1,
                    borderRadius: 4,
                },
                {
                    label: `Media (${avg})`,
                    data: Array(labels.length).fill(avg),
                    type: 'line',
                    borderColor: '#f59e0b',
                    borderWidth: 2,
                    borderDash: [6, 3],
                    pointRadius: 0,
                    fill: false,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'bottom', labels: { color: '#f8fafc', font: { size: 11 } } },
                tooltip: {
                    callbacks: {
                        afterBody: function(items) {
                            const idx = items[0].dataIndex;
                            const w = data.weekly[idx];
                            if (!w.by_type || Object.keys(w.by_type).length === 0) return '';
                            return '\n' + Object.entries(w.by_type).map(([t, c]) => `  ${t}: ${c}`).join('\n');
                        }
                    }
                }
            },
            scales: {
                x: { ticks: { color: '#94a3b8', maxTicksLimit: 13, font: { size: 10 } }, grid: { display: false } },
                y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.05)' }, beginAtZero: true }
            }
        }
    });
}

// --- Forecast ---
function renderForecastSection(epicsData) {
    const epics = epicsData.epics || [];

    if (epics.length === 0) {
        return `<section class="metric-section glass">
            <h2>Monte Carlo Forecast</h2>
            <p class="metric-desc">Nenhum epico/parent aberto com subtasks encontrado.</p>
        </section>`;
    }

    let epicRows = epics.slice(0, 15).map(e => {
        const progressBar = `<div class="progress-bar"><div class="progress-fill" style="width:${e.progress_pct}%"></div></div>`;
        return `
            <tr>
                <td><strong><a href="https://jiraps.atlassian.net/browse/${e.key}" target="_blank" rel="noopener" style="color:#3b82f6;text-decoration:none">${e.key}</a></strong></td>
                <td style="max-width:250px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHTML(e.summary)}</td>
                <td>${e.issue_type || '--'}</td>
                <td>${e.assignee || '--'}</td>
                <td>${e.status}</td>
                <td>${e.done}/${e.total}</td>
                <td style="min-width:100px;">${progressBar} <span class="progress-label">${e.progress_pct}%</span></td>
                <td><strong>${e.remaining}</strong></td>
                <td><button class="btn-forecast" onclick="runForecast('${e.key}', ${e.remaining})">Simular</button></td>
            </tr>
        `;
    }).join('');

    return `
        <section class="metric-section glass">
            <h2>Monte Carlo Forecast</h2>
            <p class="metric-desc">Previsao probabilistica de conclusao. Selecione uma issue-pai para simular com base no throughput historico.</p>
            <details class="formula-details">
                <summary>Como e calculado?</summary>
                <div class="formula-content">
                    <p><strong>Monte Carlo</strong>: executa 10.000 simulacoes. Cada simulacao sorteia semanas aleatorias do throughput historico e soma ate atingir os itens restantes.</p>
                    <p><strong>P85</strong> = "em 85% das simulacoes, o trabalho termina em ate X semanas".</p>
                    <p><strong>Premissa</strong>: throughput futuro se comporta como o passado recente (ultimas 12 semanas).</p>
                </div>
            </details>
            <table class="metric-table">
                <thead>
                    <tr><th>Key</th><th>Summary</th><th>Tipo</th><th>Assignee</th><th>Status</th><th>Done/Total</th><th>Progresso</th><th>Restantes</th><th>Forecast</th></tr>
                </thead>
                <tbody>${epicRows}</tbody>
            </table>
            <div id="forecast-result" class="forecast-result"></div>
        </section>
    `;
}

async function runForecast(epicKey, remaining) {
    const resultDiv = document.getElementById('forecast-result');
    resultDiv.innerHTML = '<p class="loading">Simulando 10.000 cenarios...</p>';

    try {
        const r = await fetch(`${API2}/forecast?project_key=${currentProject}&remaining_items=${remaining}`);
        const data = await r.json();

        if (data.error) {
            resultDiv.innerHTML = `<p class="error">${data.error}</p>`;
            return;
        }

        const p = data.percentiles;
        const t = data.throughput_used;

        resultDiv.innerHTML = `
            <div class="forecast-card glass">
                <h3>Forecast: ${epicKey} (${remaining} itens restantes)</h3>
                <div class="kpis-row">
                    <div class="kpi-box"><div class="kpi-label">50% confianca</div><div class="kpi-value">${p.p50} sem.</div></div>
                    <div class="kpi-box"><div class="kpi-label">70% confianca</div><div class="kpi-value">${p.p70} sem.</div></div>
                    <div class="kpi-box"><div class="kpi-label">85% confianca</div><div class="kpi-value accent">${p.p85} sem.</div></div>
                    <div class="kpi-box"><div class="kpi-label">95% confianca</div><div class="kpi-value warning">${p.p95} sem.</div></div>
                </div>
                <p class="forecast-detail">Baseado em throughput historico: media ${t.avg} items/semana (min: ${t.min}, max: ${t.max}, ${t.weeks_sampled} semanas amostradas). ${data.simulations.toLocaleString()} simulacoes.</p>
                <div class="chart-container chart-small">
                    <canvas id="forecastCanvas"></canvas>
                </div>
            </div>
        `;
        renderForecastChart(data);
    } catch (e) {
        resultDiv.innerHTML = `<p class="error">Erro na simulacao: ${e.message}</p>`;
    }
}

function renderForecastChart(data) {
    const ctx = document.getElementById('forecastCanvas').getContext('2d');
    const hist = data.histogram;
    const labels = hist.map(h => `${h.weeks} sem`);
    const counts = hist.map(h => h.count);
    const maxCount = Math.max(...counts);

    // Colorir barras: verde até P50, amarelo até P85, vermelho depois
    const p = data.percentiles;
    const colors = hist.map(h => {
        if (h.weeks <= p.p50) return 'rgba(16, 185, 129, 0.7)';
        if (h.weeks <= p.p85) return 'rgba(245, 158, 11, 0.7)';
        return 'rgba(239, 68, 68, 0.7)';
    });

    if (forecastChart) forecastChart.destroy();
    forecastChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Simulacoes',
                data: counts,
                backgroundColor: colors,
                borderWidth: 0,
                borderRadius: 3,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.raw.toLocaleString()} simulacoes (${(ctx.raw / data.simulations * 100).toFixed(1)}%)`
                    }
                }
            },
            scales: {
                x: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { display: false } },
                y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.05)' } }
            }
        }
    });
}

// --- Aging Backlog ---
function renderAgingBacklog(data) {
    if (!data.total || data.total === 0) {
        return `<section class="metric-section glass">
            <h2>Aging Backlog</h2>
            <p class="metric-desc">Nenhuma issue inativa encontrada. Backlog saudavel!</p>
        </section>`;
    }

    const b = data.brackets;
    let bracketHtml = Object.entries(b).map(([label, count]) => {
        if (count === 0) return '';
        const cls = label === '180d+' ? 'danger' : (label === '90-180d' ? 'warning' : 'info');
        return `<span class="bracket-badge ${cls}">${label}: ${count}</span>`;
    }).join('');

    let rows = data.issues.slice(0, 20).map(i => `
        <tr>
            <td><strong><a href="https://jiraps.atlassian.net/browse/${i.key}" target="_blank" rel="noopener" style="color:#3b82f6;text-decoration:none">${i.key}</a></strong></td>
            <td style="max-width:250px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHTML(i.summary)}</td>
            <td>${i.issue_type || '--'}</td>
            <td>${i.status}</td>
            <td>${i.assignee || '--'}</td>
            <td class="${i.days_stale >= 180 ? 'highlight-danger' : (i.days_stale >= 90 ? 'highlight-warning' : '')}">${i.days_stale}d</td>
            <td>${i.age_days ? i.age_days + 'd' : '--'}</td>
        </tr>
    `).join('');

    return `
        <section class="metric-section glass">
            <h2>Aging Backlog</h2>
            <p class="metric-desc">${data.total} issues sem atividade ha mais de ${data.min_days} dias. Candidatas a revisao ou cancelamento.</p>
            <details class="formula-details">
                <summary>Como e calculado?</summary>
                <div class="formula-content">
                    <p><strong>Aging Backlog</strong> = issues que NAO estao Done e cuja ultima atualizacao (updated_at) foi ha mais de ${data.min_days} dias.</p>
                    <p><strong>Dias inativo</strong> = dias desde a ultima atualizacao. <strong>Idade</strong> = dias desde a criacao.</p>
                    <p><strong>Recomendacao</strong>: issues com >180d de inatividade provavelmente devem ser canceladas — se fossem importantes, alguem ja teria mexido.</p>
                </div>
            </details>
            <div class="brackets-row">${bracketHtml}</div>
            <table class="metric-table">
                <thead>
                    <tr><th>Key</th><th>Summary</th><th>Tipo</th><th>Status</th><th>Assignee</th><th>Inativo</th><th>Idade</th></tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
            ${data.total > 20 ? `<p class="table-footer">Mostrando 20 de ${data.total} issues (ordenadas por inatividade).</p>` : ''}
        </section>
    `;
}

// --- Utils ---
function escapeHTML(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, tag => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[tag] || tag));
}
