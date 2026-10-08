// Wave 2: Previsibilidade
const API2 = '/api/metrics/wave2';
let throughputChart = null;
let forecastChart = null;
let currentProject = null;

// --- Estado do modo "Analisar melhoria (marco)" ---
let markerMode = false;     // ligado/desligado
let markerCutIdx = null;    // indice da 1a semana "depois" do marco
let throughputData = null;  // guarda o payload de throughput do projeto atual

// Cores de grafico via tokens (CTUI.token) — sem hex solto, sem cor de alerta em decoracao.
const CH = {
    series: () => CTUI.token('--chart-1'),
    seriesFill: () => CTUI.token('--chart-1') + '99',
    refLine: () => CTUI.token('--text-2'),   // linha de media = referencia neutra
    axis: () => CTUI.token('--text-2'),
    grid: (window.CTUI ? CTUI.token('--chart-grid') : 'rgba(16,32,58,0.08)'),
    legend: () => CTUI.token('--text-1'),
};

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
        CTContext.bindProjectSelect(select, onProjectChange);
    } catch (e) { console.error(e); }
}

async function onProjectChange() {
    const key = document.getElementById('projectFilter').value;
    const container = document.getElementById('content-container');
    currentProject = key;
    // Reseta o modo marco ao trocar de projeto.
    markerMode = false;
    markerCutIdx = null;

    if (!key) {
        container.innerHTML = '<p class="empty-state">Selecione um projeto para visualizar as métricas de previsibilidade.</p>';
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
        container.innerHTML = '<p class="empty-state">Erro ao carregar métricas.</p>';
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
        throughputData = throughput;
        renderThroughputChart(throughput);
    }
}

// --- Throughput ---
function renderThroughput(data) {
    if (!data.weekly || data.weekly.length === 0) {
        return `<section class="metric-section glass">
            <h2>Throughput Semanal</h2>
            <p class="metric-desc">Sem dados. Execute sincronização para popular.</p>
        </section>`;
    }

    const s = data.summary;

    return `
        <section class="metric-section glass">
            <h2>Throughput Semanal</h2>
            <p class="metric-desc">Issues concluídas por semana. Estabilidade do throughput indica previsibilidade.</p>
            <details class="formula-details">
                <summary>Como é calculado?</summary>
                <div class="formula-content">
                    <p><strong>Throughput</strong> = quantidade de issues que passaram para Done em cada semana (agrupadas pela data de resolução).</p>
                    <p><strong>Média</strong> = soma / N semanas. <strong>Desvio padrão</strong> = variabilidade (menor = mais previsível).</p>
                    <p><strong>Uso</strong>: alimenta o Monte Carlo Forecast. Throughput estável = forecast confiável.</p>
                </div>
            </details>
            <div class="kpis-row">
                <div class="kpi-box"><div class="kpi-label">Média/semana</div><div class="kpi-value">${s.avg}</div></div>
                <div class="kpi-box"><div class="kpi-label">Desvio Padrão</div><div class="kpi-value">${s.stddev}</div></div>
                <div class="kpi-box"><div class="kpi-label">Min</div><div class="kpi-value">${s.min}</div></div>
                <div class="kpi-box"><div class="kpi-label">Max</div><div class="kpi-value">${s.max}</div></div>
            </div>
            <div class="tp-marker-bar">
                <button id="tp-marker-toggle" class="btn btn--sm tp-marker-btn" onclick="toggleMarkerMode()">📊 Analisar melhoria (marco)</button>
                <span id="tp-marker-hint" class="tp-marker-hint" style="display:none">Clique em uma semana no gráfico para posicionar o marco.</span>
            </div>
            <div id="tp-impact" class="tp-impact" style="display:none"></div>
            <div class="chart-container">
                <canvas id="throughputCanvas"></canvas>
            </div>
        </section>
    `;
}

// --- Persistencia do marco por projeto (localStorage) ---
const _markerKey = (pk) => `wave2.marker.${pk}`;
function saveMarker(pk, weekKey) {
    try { localStorage.setItem(_markerKey(pk), weekKey); } catch (e) {}
}
function loadMarker(pk) {
    try { return localStorage.getItem(_markerKey(pk)); } catch (e) { return null; }
}

// --- Modo "Analisar melhoria (marco)" ---
function toggleMarkerMode() {
    markerMode = !markerMode;
    const btn = document.getElementById('tp-marker-toggle');
    const hint = document.getElementById('tp-marker-hint');
    const impact = document.getElementById('tp-impact');
    if (markerMode) {
        const weeks = throughputData.weekly;
        const n = weeks.length;
        // Restaura o marco salvo para este projeto; senao usa o meio da serie.
        if (markerCutIdx === null) {
            const saved = loadMarker(currentProject);
            const savedIdx = saved ? weeks.findIndex(w => w.week === saved) : -1;
            markerCutIdx = savedIdx > 0 ? savedIdx : Math.max(1, Math.round(n / 2));
        }
        btn.textContent = '✕ Desativar marco';
        btn.classList.add('tp-marker-btn--on');
        hint.style.display = '';
        impact.style.display = '';
    } else {
        btn.textContent = '📊 Analisar melhoria (marco)';
        btn.classList.remove('tp-marker-btn--on');
        hint.style.display = 'none';
        impact.style.display = 'none';
    }
    renderThroughputChart(throughputData);
}
window.toggleMarkerMode = toggleMarkerMode;

const _r1 = (x) => Math.round(x * 10) / 10;

// Calcula o impacto antes/depois a partir do indice de corte.
function computeImpact(weekly, cutIdx) {
    const totals = weekly.map(w => w.total);
    const antes = totals.slice(0, cutIdx);
    const depois = totals.slice(cutIdx);
    const mAntes = antes.length ? antes.reduce((a, b) => a + b, 0) / antes.length : 0;
    const mDepois = depois.length ? depois.reduce((a, b) => a + b, 0) / depois.length : 0;
    const n = Math.min(antes.length, depois.length);
    const compAntes = antes.slice(antes.length - n).reduce((a, b) => a + b, 0);
    const compDepois = depois.slice(0, n).reduce((a, b) => a + b, 0);
    const ganho = mAntes > 0 ? (mDepois / mAntes - 1) * 100 : null;
    const fator = compAntes > 0 ? compDepois / compAntes : null;
    const totalDepois = depois.reduce((a, b) => a + b, 0);
    return { mAntes, mDepois, n, compAntes, compDepois, ganho, fator, totalDepois };
}

// Monta o HTML dos callouts de impacto a partir de um objeto normalizado.
function impactHtml(d, cutLabel) {
    const ganho = d.ganho_pct;
    const fator = d.fator;
    return `
        <div class="tp-impact-grid">
            <div class="tp-cal"><div class="tp-cal-v good">${ganho === null || ganho === undefined ? '∞' : '+' + Math.round(ganho) + '%'}</div><div class="tp-cal-l">Ganho de ritmo</div><div class="tp-cal-s">${_r1(d.media_antes)} → ${_r1(d.media_depois)}/sem</div></div>
            <div class="tp-cal"><div class="tp-cal-v good">${fator === null || fator === undefined ? '—' : _r1(fator) + '×'}</div><div class="tp-cal-l">Janela comparável</div><div class="tp-cal-s">${d.comp_antes} → ${d.comp_depois} em ${d.janela_semanas} sem.</div></div>
            <div class="tp-cal"><div class="tp-cal-v">${d.total_depois}</div><div class="tp-cal-l">Entregas pós-marco</div><div class="tp-cal-s">a partir de ${cutLabel}</div></div>
        </div>
        <p class="tp-impact-note">A <strong>janela comparável</strong> (mesmo nº de semanas antes/depois) é o número mais defensável; o "ganho de ritmo" infla com janelas desiguais.</p>
    `;
}

// Busca o impacto no BACKEND (fonte unica). Em caso de falha, cai no calculo local.
async function renderImpact(weekly, cutIdx) {
    const el = document.getElementById('tp-impact');
    if (!el) return;
    const cutWeek = weekly[cutIdx] ? weekly[cutIdx].week : '';
    const cutLabel = weekly[cutIdx] ? weekly[cutIdx].week_label : '';
    try {
        const r = await fetch(`${API2}/throughput-impact?project_key=${encodeURIComponent(currentProject)}&cutoff_week=${encodeURIComponent(cutWeek)}`);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const d = await r.json();
        if (d.error) throw new Error(d.error);
        el.innerHTML = impactHtml(d, d.cutoff_label || cutLabel);
    } catch (e) {
        // Fallback: calcula no front (mesma regra) se o endpoint falhar.
        const m = computeImpact(weekly, cutIdx);
        el.innerHTML = impactHtml({
            ganho_pct: m.ganho, fator: m.fator, media_antes: m.mAntes, media_depois: m.mDepois,
            comp_antes: m.compAntes, comp_depois: m.compDepois, janela_semanas: m.n, total_depois: m.totalDepois,
        }, cutLabel);
    }
}

function renderThroughputChart(data) {
    const ctx = document.getElementById('throughputCanvas').getContext('2d');
    const labels = data.weekly.map(w => w.week_label);
    const totals = data.weekly.map(w => w.total);
    const avg = data.summary.avg;

    // No modo marco: barras coloridas por periodo + anotacoes de marco/medias.
    let barColors = CH.seriesFill();
    const datasets = [];
    const annotations = {};
    const extraOptions = {};

    if (markerMode && markerCutIdx !== null) {
        const cut = markerCutIdx;
        barColors = data.weekly.map((w, i) => i >= cut ? (CTUI.token('--action') + 'cc') : (CTUI.token('--text-3') + '66'));
        const m = computeImpact(data.weekly, cut);
        annotations.marco = {
            type: 'line', scaleID: 'x', value: cut - 0.5,
            borderColor: CTUI.token('--risk'), borderWidth: 2, borderDash: [4, 3],
            label: { display: true, content: 'marco: ' + (data.weekly[cut] ? data.weekly[cut].week_label : ''),
                     position: 'start', backgroundColor: CTUI.token('--risk'), color: '#fff', font: { size: 11, weight: 'bold' } }
        };
        annotations.mAntes = {
            type: 'line', scaleID: 'y', value: m.mAntes,
            borderColor: '#5b6b82', borderWidth: 2, borderDash: [6, 4],
            label: { display: true, content: 'média antes ' + _r1(m.mAntes), position: 'start',
                     backgroundColor: '#334155', color: '#fff', font: { size: 10, weight: 'bold' }, borderRadius: 6 }
        };
        annotations.mDepois = {
            type: 'line', scaleID: 'y', value: m.mDepois,
            borderColor: CTUI.token('--action'), borderWidth: 2, borderDash: [6, 4],
            label: { display: true, content: 'média depois ' + _r1(m.mDepois), position: 'end',
                     backgroundColor: CTUI.token('--action'), color: '#fff', font: { size: 10, weight: 'bold' }, borderRadius: 6 }
        };
        datasets.push({
            label: 'Throughput', data: totals,
            backgroundColor: barColors, borderColor: CTUI.token('--action'), borderWidth: 1, borderRadius: 4,
        });
        extraOptions.onClick = (evt) => {
            const pts = throughputChart.getElementsAtEventForMode(evt, 'index', { intersect: false }, true);
            if (pts.length) {
                const idx = Math.max(1, Math.min(data.weekly.length - 1, pts[0].index));
                if (idx !== markerCutIdx) {
                    markerCutIdx = idx;
                    saveMarker(currentProject, data.weekly[idx].week); // persiste o marco escolhido
                    renderThroughputChart(data);
                }
            }
        };
        renderImpact(data.weekly, cut);
    } else {
        datasets.push({
            label: 'Throughput', data: totals,
            backgroundColor: CH.seriesFill(), borderColor: CH.series(), borderWidth: 1, borderRadius: 4,
        });
        datasets.push({
            label: `Média (${avg})`, data: Array(labels.length).fill(avg), type: 'line',
            borderColor: CH.refLine(), borderWidth: 2, borderDash: [6, 3], pointRadius: 0, fill: false,
        });
    }

    if (throughputChart) throughputChart.destroy();
    throughputChart = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            onClick: extraOptions.onClick,
            plugins: {
                legend: { display: !markerMode, position: 'bottom', labels: { color: CH.legend(), font: { size: 11 } } },
                annotation: { annotations },
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
                x: { ticks: { color: CH.axis(), maxTicksLimit: 13, font: { size: 10 } }, grid: { display: false } },
                y: { ticks: { color: CH.axis() }, grid: { color: CH.grid }, beginAtZero: true }
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
            <p class="metric-desc">Nenhum épico/parent aberto com subtasks encontrado.</p>
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
            <p class="metric-desc">Previsão probabilística de conclusão. Selecione uma issue-pai para simular com base no throughput histórico.</p>
            <details class="formula-details">
                <summary>Como é calculado?</summary>
                <div class="formula-content">
                    <p><strong>Monte Carlo</strong>: executa 10.000 simulações. Cada simulação sorteia semanas aleatórias do throughput histórico e soma até atingir os itens restantes.</p>
                    <p><strong>P85</strong> = "em 85% das simulações, o trabalho termina em até X semanas".</p>
                    <p><strong>Premissa</strong>: throughput futuro se comporta como o passado recente (últimas 12 semanas).</p>
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
    resultDiv.innerHTML = '<p class="loading">Simulando 10.000 cenários...</p>';

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
                    <div class="kpi-box"><div class="kpi-label">50% confiança</div><div class="kpi-value">${p.p50} sem.</div></div>
                    <div class="kpi-box"><div class="kpi-label">70% confiança</div><div class="kpi-value">${p.p70} sem.</div></div>
                    <div class="kpi-box"><div class="kpi-label">85% confiança</div><div class="kpi-value accent">${p.p85} sem.</div></div>
                    <div class="kpi-box"><div class="kpi-label">95% confiança</div><div class="kpi-value warning">${p.p95} sem.</div></div>
                </div>
                <p class="forecast-detail">Baseado em throughput histórico: média ${t.avg} items/semana (min: ${t.min}, max: ${t.max}, ${t.weeks_sampled} semanas amostradas). ${data.simulations.toLocaleString()} simulações.</p>
                <div class="chart-container chart-small">
                    <canvas id="forecastCanvas"></canvas>
                </div>
            </div>
        `;
        renderForecastChart(data);
    } catch (e) {
        resultDiv.innerHTML = `<p class="error">Erro na simulação: ${e.message}</p>`;
    }
}

function renderForecastChart(data) {
    const ctx = document.getElementById('forecastCanvas').getContext('2d');
    const hist = data.histogram;
    const labels = hist.map(h => `${h.weeks} sem`);
    const counts = hist.map(h => h.count);
    const maxCount = Math.max(...counts);

    // Colorir barras por risco de prazo (uso semantico legitimo, via tokens):
    // ate P50 = confortavel (ok), ate P85 = atencao (warn), depois = risco (risk).
    const p = data.percentiles;
    const colors = hist.map(h => {
        if (h.weeks <= p.p50) return CTUI.token('--ok') + 'b3';
        if (h.weeks <= p.p85) return CTUI.token('--warn') + 'b3';
        return CTUI.token('--risk') + 'b3';
    });

    if (forecastChart) forecastChart.destroy();
    forecastChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Simulações',
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
                        label: (ctx) => `${ctx.raw.toLocaleString()} simulações (${(ctx.raw / data.simulations * 100).toFixed(1)}%)`
                    }
                }
            },
            scales: {
                x: { ticks: { color: CH.axis(), font: { size: 10 } }, grid: { display: false } },
                y: { ticks: { color: CH.axis() }, grid: { color: CH.grid } }
            }
        }
    });
}

// --- Aging Backlog ---
function renderAgingBacklog(data) {
    if (!data.total || data.total === 0) {
        return `<section class="metric-section glass">
            <h2>Aging Backlog</h2>
            <p class="metric-desc">Nenhuma issue inativa encontrada. Backlog saudável!</p>
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
            <p class="metric-desc">${data.total} issues sem atividade há mais de ${data.min_days} dias. Candidatas a revisão ou cancelamento.</p>
            <details class="formula-details">
                <summary>Como é calculado?</summary>
                <div class="formula-content">
                    <p><strong>Aging Backlog</strong> = issues que NÃO estão Done e cuja última atualização (updated_at) foi há mais de ${data.min_days} dias.</p>
                    <p><strong>Dias inativo</strong> = dias desde a última atualização. <strong>Idade</strong> = dias desde a criação.</p>
                    <p><strong>Recomendação</strong>: issues com >180d de inatividade provavelmente devem ser canceladas — se fossem importantes, alguém já teria mexido.</p>
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
