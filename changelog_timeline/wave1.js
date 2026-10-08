const API = '/api/metrics/wave1';
let cfdChart = null;
let pollInterval = null;
let currentProject = null;

// Cores de grafico via tokens do design system (sem hex solto).
const T = (n) => (window.CTUI ? CTUI.token(n) : '#888');
const hexA = (hex, a) => hex + a; // sufixo de alpha em hex de 2 digitos

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
            opt.dataset.lastSync = p.last_sync ? p.last_sync.date : '';
            select.appendChild(opt);
        });
        // Restaura o projeto salvo (contexto compartilhado) ou auto-seleciona se houver 1.
        CTContext.bindProjectSelect(select, onProjectChange);
    } catch (e) { console.error(e); }
}

async function onProjectChange() {
    const key = document.getElementById('projectFilter').value;
    const container = document.getElementById('content-container');
    const btnSync = document.getElementById('btnSync');
    const lastInfo = document.getElementById('lastSyncInfo');
    currentProject = key;

    if (!key) {
        container.innerHTML = '<p class="empty-state">Selecione um projeto para visualizar as métricas.</p>';
        btnSync.style.display = 'none';
        lastInfo.textContent = '';
        return;
    }

    // Mostra botão e última sync
    btnSync.style.display = 'inline-block';
    const opt = document.querySelector(`#projectFilter option[value="${key}"]`);
    const lastSyncDate = opt ? opt.dataset.lastSync : '';

    let infoText = '';
    if (lastSyncDate) {
        infoText = `Última sync: ${new Date(lastSyncDate).toLocaleString('pt-BR')}`;
    } else {
        infoText = 'Nunca sincronizado';
    }

    // Busca última atualização Wave1
    try {
        const waveR = await fetch(`/api/metrics/wave1/last-update?project_key=${key}`);
        const waveData = await waveR.json();
        if (waveData.last_wave1_update) {
            infoText += ` | Última métricas: ${new Date(waveData.last_wave1_update).toLocaleString('pt-BR')}`;
        } else {
            infoText += ' | Métricas: nunca calculadas';
        }
    } catch (e) {}

    lastInfo.textContent = infoText;

    container.innerHTML = '<p class="empty-state">Carregando...</p>';

    try {
        const [timePerStatus, percentiles, flowEff, cfd, aging, percWeekly, flowEffWeekly] = await Promise.all([
            fetch(`${API}/time-per-status?project_key=${key}`).then(r => r.json()),
            fetch(`${API}/percentiles?project_key=${key}`).then(r => r.json()),
            fetch(`${API}/flow-efficiency?project_key=${key}`).then(r => r.json()),
            fetch(`${API}/cfd?project_key=${key}`).then(r => r.json()),
            fetch(`${API}/aging-wip?project_key=${key}`).then(r => r.json()),
            fetch(`${API}/percentiles-weekly?project_key=${key}`).then(r => r.json()),
            fetch(`${API}/flow-efficiency-weekly?project_key=${key}`).then(r => r.json()),
        ]);
        renderAll(timePerStatus, percentiles, flowEff, cfd, aging, percWeekly, flowEffWeekly);
    } catch (e) {
        container.innerHTML = '<p class="empty-state">Erro ao carregar métricas.</p>';
        console.error(e);
    }
}

// --- Recalculate ---

async function startSync() {
    if (!currentProject) return;

    const btnSync = document.getElementById('btnSync');
    const logContainer = document.getElementById('sync-log-container');
    const logEl = document.getElementById('sync-log');
    const badge = document.getElementById('sync-badge');

    try {
        const response = await fetch(`/api/metrics/wave1/recalculate?project_key=${currentProject}`, {
            method: 'POST',
        });

        const data = await response.json();

        if (!response.ok) {
            logContainer.style.display = 'block';
            logEl.innerHTML = `<div class="log-line error">${escapeHTML(data.detail)}</div>`;
            badge.className = 'sync-status-badge';
            badge.style.background = 'rgba(239,68,68,0.2)';
            badge.style.color = '#f87171';
            badge.textContent = 'Erro';
            return;
        }

        // Iniciou com sucesso — começa polling
        btnSync.disabled = true;
        btnSync.textContent = 'Recalculando...';
        logContainer.style.display = 'block';
        badge.className = 'sync-status-badge running';
        badge.textContent = 'Em execução';
        logEl.innerHTML = '<div class="log-line info">Iniciando recálculo...</div>';

        startPolling();

    } catch (e) {
        logContainer.style.display = 'block';
        logEl.innerHTML = `<div class="log-line error">Erro de conexão: ${e.message}</div>`;
    }
}

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(pollRecalcStatus, 1000);
}

function stopPolling() {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
}

async function pollRecalcStatus() {
    try {
        const r = await fetch('/api/metrics/wave1/recalculate/status');
        const status = await r.json();
        renderRecalcLog(status);

        if (!status.running) {
            stopPolling();
            const btnSync = document.getElementById('btnSync');
            const badge = document.getElementById('sync-badge');
            btnSync.disabled = false;
            btnSync.textContent = 'Atualizar Dados';
            badge.className = 'sync-status-badge completed';
            badge.textContent = 'Concluído';

            // Recarrega dados
            await onProjectChange();
        }
    } catch (e) {
        stopPolling();
    }
}

function renderRecalcLog(status) {
    const logEl = document.getElementById('sync-log');
    logEl.innerHTML = status.progress.map(line => {
        let cls = '';
        if (line.includes('\u2713') || line.includes('finalizado')) cls = 'success';
        else if (line.includes('\u2717') || line.includes('Erro')) cls = 'error';
        else if (line.includes('...')) cls = 'info';
        return `<div class="log-line ${cls}">${escapeHTML(line)}</div>`;
    }).join('');
    logEl.scrollTop = logEl.scrollHeight;
}

window.cancelSync = function() {};  // Não aplicável

function escapeHTML(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, tag => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[tag] || tag));
}

function renderAll(timePerStatus, percentiles, flowEff, cfd, aging, percWeekly, flowEffWeekly) {
    const container = document.getElementById('content-container');
    let html = '<div class="metrics-grid">';

    // 1. Flow Efficiency (esquerda, 1/3) + Flow Efficiency semanal (direita, 2/3)
    html += '<div class="side-by-side side-by-side--1-2">';
    html += renderPercentiles(percentiles, flowEff, flowEffWeekly);
    html += renderFlowEfficiencyWeekly(flowEffWeekly);
    html += '</div>';

    // 1.5. Lead/Cycle Time: percentis atuais + evolução semanal (full width, abaixo)
    html += renderPercentilesWeekly(percWeekly, percentiles);

    // 2. Tempo por status (gargalo)
    html += renderTimePerStatus(timePerStatus);

    // 4. CFD (canvas para chart)
    html += renderCFDSection(cfd);

    // 5. Aging WIP
    html += renderAgingWIP(aging);

    html += '</div>';
    container.innerHTML = html;

    // Renderiza charts após inserir no DOM
    if (cfd.data && cfd.data.length > 0) {
        renderCFDChart(cfd);
    }
    if (percWeekly.weeks && percWeekly.weeks.length > 0) {
        renderPercentilesWeeklyChart(percWeekly);
    }
    if (flowEffWeekly && flowEffWeekly.weeks && flowEffWeekly.weeks.length > 0) {
        renderFlowEfficiencyWeeklyChart(flowEffWeekly, flowEff);
    }
}

// --- Percentis ---
function renderPercentiles(data, flowData, weeklyData) {
    const p = data.percentiles || {};
    const lead = p.lead_time || {};
    const cycle = p.cycle_time || {};

    // Flow Efficiency
    let flowHtml = '';
    if (flowData && flowData.count > 0) {
        let colorClass = 'danger';
        let classification = '';
        let analysis = '';
        const eff = flowData.avg_efficiency;
        const waitPct = (100 - eff).toFixed(0);
        const workPct = eff.toFixed(0);

        if (eff >= 40) {
            colorClass = 'success';
            classification = 'excelente';
            analysis = `Das ${flowData.count} issues analisadas, o time apresentou ${eff}% de Flow Efficiency, classificado como <strong>desempenho excelente</strong>. Isso indica que ${workPct}% do lead time foi dedicado ao desenvolvimento efetivo, com apenas ${waitPct}% em períodos de espera. O fluxo está altamente otimizado com mínimo desperdício.`;
        } else if (eff >= 25) {
            colorClass = 'good';
            classification = 'bom';
            analysis = `Das ${flowData.count} issues analisadas, o time apresentou ${eff}% de Flow Efficiency, classificado como <strong>bom desempenho</strong> e próximo da faixa de excelência. Isso indica que cerca de ${workPct}% do lead time foi dedicado ao desenvolvimento efetivo, enquanto aproximadamente ${waitPct}% correspondeu a períodos de espera, apontando oportunidades de otimização principalmente nas etapas de bloqueio, testes e disponibilização para entrega.`;
        } else if (eff >= 15) {
            colorClass = 'moderate';
            classification = 'tipico';
            analysis = `Das ${flowData.count} issues analisadas, o time apresentou ${eff}% de Flow Efficiency, classificado como <strong>desempenho típico</strong> do mercado. Isso indica que apenas ${workPct}% do lead time foi dedicado ao desenvolvimento efetivo, enquanto ${waitPct}% correspondeu a espera em filas (bloqueio, testes, disponibilização). Há espaço significativo para melhoria reduzindo handoffs e tempos de espera entre etapas.`;
        } else {
            colorClass = 'danger';
            classification = 'baixo';
            analysis = `Das ${flowData.count} issues analisadas, o time apresentou ${eff}% de Flow Efficiency, classificado como <strong>desempenho baixo</strong>. Isso indica que apenas ${workPct}% do lead time foi dedicado ao desenvolvimento efetivo, enquanto ${waitPct}% foi espera. Issues passam a maior parte do tempo paradas em filas. Ações urgentes: limitar WIP, reduzir handoffs e eliminar etapas desnecessárias de aprovação.`;
        }

        flowHtml = `
            <div class="flow-efficiency-row">
                <div class="flow-main">
                    <span class="flow-label">Flow Efficiency</span>
                    <span class="flow-value ${colorClass}">${eff}%</span>
                    <span class="flow-meta">(${flowData.count} issues Done analisadas)</span>
                </div>
                <p class="inline-formula flow-analysis">${analysis}</p>
                <div class="flow-ref">
                    <span class="flow-scale scale-danger">● &lt;15% baixa</span>
                    <span class="flow-scale scale-moderate">● 15-25% típica</span>
                    <span class="flow-scale scale-good">● 25-40% boa</span>
                    <span class="flow-scale scale-success">● &gt;40% excelente</span>
                </div>
            </div>
        `;
    }

    // Nota comparando o card (este número) com o gráfico ao lado (semanal)
    const avgGeral = (flowData && flowData.count > 0) ? flowData.avg_efficiency : null;
    const weeksCount = (weeklyData && weeklyData.weeks) ? weeklyData.weeks.length : 0;
    const explicacao = (avgGeral !== null && weeksCount > 0) ? `
        <div class="flow-week-note">
            <p><strong>Este número e o gráfico ao lado ("Evolução Semanal") não batem — por quê?</strong></p>
            <p>Os dois medem a mesma coisa por issue, mas resumem de formas diferentes:</p>
            <ul>
                <li><strong>Este card (${avgGeral}%)</strong> = média de <em>todas</em> as issues Done do projeto, de toda a história. É a "eficiência média geral".</li>
                <li><strong>Gráfico ao lado</strong> = uma média <em>por semana</em>, apenas das últimas ${weeksCount} semanas. Cada ponto é a média daquela semana isolada.</li>
            </ul>
            <p>Por isso a linha do gráfico oscila mais que este card: uma semana com poucas issues sobe ou desce fácil. A <strong>linha tracejada</strong> do gráfico marca justamente esta média geral (${avgGeral}%), para comparar cada semana com o histórico — pontos acima dela = semana melhor que a média; abaixo = pior.</p>
        </div>
    ` : '';

    return `
        <section class="metric-section glass">
            <h2>Flow Efficiency</h2>
            <p class="metric-desc">Qual a eficiência do fluxo: proporção do lead time gasta trabalhando vs. em espera.</p>
            ${flowHtml || '<p class="metric-desc">Sem dados de Flow Efficiency.</p>'}
            ${explicacao}
        </section>
    `;
}

// Bloco de KPIs de Lead Time e Cycle Time (P50/P70/P85/P95).
// Renderizado junto da "Evolução Semanal dos Percentis".
function renderPercentilesKpis(data) {
    const p = data.percentiles || {};
    const lead = p.lead_time || {};
    const cycle = p.cycle_time || {};
    return `
        <div class="charts-row">
            <div>
                <h3 style="font-size:0.9rem; color: var(--text-muted); margin-bottom:0.4rem;">Lead Time (${lead.count || 0} issues Done)</h3>
                <p class="inline-formula">Tempo total desde a criação da issue até sua resolução (resolved_at − created_at). Tempo calendário.</p>
                <div class="kpis-row">
                    <div class="kpi-box"><div class="kpi-label">P50</div><div class="kpi-value">${fmtDays(lead.p50_ms)}</div></div>
                    <div class="kpi-box"><div class="kpi-label">P70</div><div class="kpi-value">${fmtDays(lead.p70_ms)}</div></div>
                    <div class="kpi-box"><div class="kpi-label">P85</div><div class="kpi-value accent">${fmtDays(lead.p85_ms)}</div></div>
                    <div class="kpi-box"><div class="kpi-label">P95</div><div class="kpi-value warning">${fmtDays(lead.p95_ms)}</div></div>
                </div>
            </div>
            <div>
                <h3 style="font-size:0.9rem; color: var(--text-muted); margin-bottom:0.4rem;">Cycle Time (${cycle.count || 0} issues)</h3>
                <p class="inline-formula">Soma dos intervalos em estados ativos (In Progress, Blocked, Test, Waiting for Delivery). Inclui intervalo aberto para issues ativas.</p>
                <div class="kpis-row">
                    <div class="kpi-box"><div class="kpi-label">P50</div><div class="kpi-value">${fmtDays(cycle.p50_ms)}</div></div>
                    <div class="kpi-box"><div class="kpi-label">P70</div><div class="kpi-value">${fmtDays(cycle.p70_ms)}</div></div>
                    <div class="kpi-box"><div class="kpi-label">P85</div><div class="kpi-value accent">${fmtDays(cycle.p85_ms)}</div></div>
                    <div class="kpi-box"><div class="kpi-label">P95</div><div class="kpi-value warning">${fmtDays(cycle.p95_ms)}</div></div>
                </div>
            </div>
        </div>
        <p class="inline-formula" style="margin-top:0.5rem;"><strong>Percentis</strong>: P85 = "85% das issues terminam em até X dias" (método nearest-rank). Usa apenas issues com valor &gt; 0.</p>
    `;
}

// --- Tempo por status ---
function renderTimePerStatus(data) {
    if (!data.statuses || data.statuses.length === 0) {
        return `<section class="metric-section glass">
            <h2>Tempo Médio por Status (Gargalo)</h2>
            <p class="metric-desc">Sem dados. Execute a sincronização com issues Done para popular esta métrica.</p>
        </section>`;
    }

    const maxP85 = Math.max(...data.statuses.map(s => s.p85_ms));

    let rows = data.statuses.map((s, idx) => {
        const pct = maxP85 > 0 ? (s.p85_ms / maxP85 * 100) : 0;
        const isBottleneck = idx === 0;
        return `
            <tr>
                <td><strong>${s.status}</strong></td>
                <td>${s.count}</td>
                <td>${fmtDays(s.avg_ms)}</td>
                <td>${fmtDays(s.p50_ms)}</td>
                <td class="${isBottleneck ? 'highlight' : ''}">${fmtDays(s.p85_ms)}</td>
                <td>${fmtDays(s.p95_ms)}</td>
                <td style="min-width:120px;">
                    <div class="bar-container">
                        <div class="bar-fill ${isBottleneck ? 'bottleneck' : ''}" style="width:${pct}%"></div>
                    </div>
                </td>
            </tr>
        `;
    }).join('');

    return `
        <section class="metric-section glass">
            <h2>Tempo Médio por Status (Gargalo)</h2>
            <p class="metric-desc">${data.total_issues} issues Done analisadas. Ordenado pelo P85 — gargalo principal no topo.</p>
            <details class="formula-details">
                <summary>Como é calculado?</summary>
                <div class="formula-content">
                    <p><strong>Duração por status</strong> = tempo entre a entrada e a saída de cada status (em dias calendário).</p>
                    <p>A entrada no primeiro status usa a <em>data de criação</em> da issue. Cada transição seguinte marca a saída do status anterior e entrada no próximo.</p>
                    <p><strong>Filtros</strong>: apenas issues <em>Done</em>. Exclui statuses: Open, Backlog, To do, Canceled, Reject, Removed, Done.</p>
                    <p><strong>Agregação</strong>: para cada status, calcula média, P50, P70, P85 e P95 de todas as durações registradas.</p>
                </div>
            </details>
            <table class="metric-table">
                <thead>
                    <tr>
                        <th>Status</th>
                        <th>Qtd</th>
                        <th>Média</th>
                        <th>P50</th>
                        <th>P85</th>
                        <th>P95</th>
                        <th>Proporção</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </section>
    `;
}

// --- Percentiles Weekly Timeline ---
let percWeeklyChart = null;

function renderPercentilesWeekly(data, percentiles) {
    // KPIs de Lead/Cycle Time (P50/P70/P85/P95) exibidos junto do gráfico semanal.
    const kpisHtml = percentiles ? renderPercentilesKpis(percentiles) : '';

    if (!data.weeks || data.weeks.length === 0) {
        return `<section class="metric-section glass">
            <h2>Lead Time e Cycle Time — Percentis</h2>
            <p class="metric-desc">Quanto tempo leva para completar issues.</p>
            ${kpisHtml}
            <h3 style="font-size:1rem;margin-top:1.5rem;">Evolução Semanal</h3>
            <p class="metric-desc">Sem dados semanais. Execute sincronização com issues Done para popular.</p>
        </section>`;
    }

    return `
        <section class="metric-section glass">
            <h2>Lead Time e Cycle Time — Percentis</h2>
            <p class="metric-desc">Quanto tempo leva para completar issues. Percentis atuais acima; evolução semanal abaixo.</p>
            ${kpisHtml}
            <h3 style="font-size:1rem;margin-top:1.5rem;margin-bottom:0.3rem;">Evolução Semanal dos Percentis</h3>
            <p class="metric-desc">Tendência do P50 e P85 de Lead Time e Cycle Time por semana de resolução. Permite identificar se o fluxo está melhorando ou piorando ao longo do tempo.</p>
            <details class="formula-details">
                <summary>Como é calculado?</summary>
                <div class="formula-content">
                    <p><strong>Agrupamento</strong>: issues Done agrupadas pela semana ISO em que foram resolvidas.</p>
                    <p><strong>P50/P85 por semana</strong>: calculados com o mesmo método nearest-rank, mas apenas com as issues daquela semana.</p>
                    <p><strong>Lead Time</strong> = resolved_at − created_at. <strong>Cycle Time</strong> = soma dos intervalos em estados ativos.</p>
                    <p><strong>Leitura</strong>: tendência descendente = melhoria contínua. Picos indicam semanas com entregas problemáticas ou issues antigas sendo fechadas.</p>
                </div>
            </details>
            <div class="chart-container">
                <canvas id="percWeeklyCanvas"></canvas>
            </div>
        </section>
    `;
}

function renderPercentilesWeeklyChart(data) {
    const ctx = document.getElementById('percWeeklyCanvas').getContext('2d');

    // Converte "2026-W11" para "10/03 - 16/03"
    function weekToDateRange(weekStr) {
        const [yearStr, wStr] = weekStr.split('-W');
        const year = parseInt(yearStr);
        const week = parseInt(wStr);
        // ISO week: segunda-feira da semana 1 é a que contém 4 de janeiro
        const jan4 = new Date(year, 0, 4);
        const dayOfWeek = jan4.getDay() || 7; // 1=seg ... 7=dom
        const monday = new Date(jan4);
        monday.setDate(jan4.getDate() - dayOfWeek + 1 + (week - 1) * 7);
        const sunday = new Date(monday);
        sunday.setDate(monday.getDate() + 6);
        const fmt = (d) => `${String(d.getDate()).padStart(2,'0')}/${String(d.getMonth()+1).padStart(2,'0')}`;
        return `${fmt(monday)} - ${fmt(sunday)}`;
    }

    const labels = data.weeks.map(w => weekToDateRange(w.week));

    const msToDay = (ms) => ms > 0 ? (ms / (1000 * 60 * 60 * 24)).toFixed(1) : 0;

    const datasets = [
        {
            // Lead Time = matizes QUENTES (laranja/amarelo)
            label: 'Lead Time P85',
            data: data.weeks.map(w => msToDay(w.lead_time.p85_ms)),
            borderColor: T('--chart-2'),
            backgroundColor: hexA(T('--chart-2'), '1a'),
            borderWidth: 2,
            tension: 0.3,
            fill: false,
        },
        {
            label: 'Lead Time P50',
            data: data.weeks.map(w => msToDay(w.lead_time.p50_ms)),
            borderColor: T('--chart-4'),
            backgroundColor: hexA(T('--chart-4'), '1a'),
            borderWidth: 1.5,
            borderDash: [5, 3],
            tension: 0.3,
            fill: false,
        },
        {
            // Cycle Time = azul (P85) / verde (P50) — hues bem distantes do par Lead
            label: 'Cycle Time P85',
            data: data.weeks.map(w => msToDay(w.cycle_time.p85_ms)),
            borderColor: T('--chart-1'),
            backgroundColor: hexA(T('--chart-1'), '1a'),
            borderWidth: 2,
            tension: 0.3,
            fill: false,
        },
        {
            label: 'Cycle Time P50',
            data: data.weeks.map(w => msToDay(w.cycle_time.p50_ms)),
            borderColor: T('--chart-3'),
            backgroundColor: hexA(T('--chart-3'), '1a'),
            borderWidth: 1.5,
            borderDash: [5, 3],
            tension: 0.3,
            fill: false,
        },
    ];

    if (percWeeklyChart) percWeeklyChart.destroy();
    percWeeklyChart = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'bottom', labels: { color: T('--text-1'), font: { size: 11 } } },
                tooltip: {
                    callbacks: {
                        afterTitle: function(items) {
                            const idx = items[0].dataIndex;
                            return `${data.weeks[idx].count} issues resolvidas`;
                        },
                        label: function(ctx) {
                            return `${ctx.dataset.label}: ${ctx.raw}d`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: { color: T('--text-2'), maxTicksLimit: 13, font: { size: 10 } },
                    grid: { display: false }
                },
                y: {
                    title: { display: true, text: 'Dias', color: T('--text-2'), font: { size: 11 } },
                    ticks: { color: T('--text-2') },
                    grid: { color: T('--chart-grid') },
                    beginAtZero: true,
                }
            }
        }
    });
}

// --- Flow Efficiency Weekly (gráfico separado) ---
let flowEffWeeklyChart = null;

function renderFlowEfficiencyWeekly(data) {
    if (!data || !data.weeks || data.weeks.length === 0) {
        return `<section class="metric-section glass">
            <h2>Evolução Semanal da Flow Efficiency</h2>
            <p class="metric-desc">Sem dados. Execute sincronização com issues Done para popular.</p>
        </section>`;
    }

    return `
        <section class="metric-section glass">
            <h2>Evolução Semanal da Flow Efficiency</h2>
            <p class="metric-desc">Média da Flow Efficiency (%) das issues resolvidas em cada semana ISO. Tendência ascendente = mais tempo trabalhando vs. esperando em filas. A linha tracejada marca a média geral do projeto (card ao lado).</p>
            <details class="formula-details">
                <summary>Como é calculado?</summary>
                <div class="formula-content">
                    <p><strong>Flow Efficiency por issue</strong> = tempo em "In Progress" / Lead Time.</p>
                    <p><strong>Média semanal (linha cheia)</strong>: agrupa as issues Done pela semana ISO de resolução (resolved_at) e tira a média das eficiências daquela semana.</p>
                    <p><strong>Média geral (linha tracejada)</strong>: média de todas as issues Done do projeto — é o valor exibido no card "Flow Efficiency".</p>
                    <p><strong>Atenção</strong>: semanas com poucas issues (veja a contagem no tooltip) oscilam bastante — uma issue "presa" derruba a média.</p>
                </div>
            </details>
            <div class="chart-container">
                <canvas id="flowEffWeeklyCanvas"></canvas>
            </div>
            <div class="flow-interpret">
                <div class="flow-interpret-col flow-interpret-up">
                    <h4>▲ O que faz o valor SUBIR (positivo)</h4>
                    <p><strong>Causa:</strong> a issue passa mais tempo sendo efetivamente trabalhada (In Progress) e menos tempo parada em filas ou espera (aguardando aprovação, teste, deploy, dependência ou bloqueio).</p>
                    <p><strong>Exemplos do que fazer:</strong></p>
                    <ul>
                        <li>Limitar o WIP (trabalho em progresso) para o time terminar o que começou antes de puxar novas issues.</li>
                        <li>Reduzir handoffs e tempo de espera entre etapas (ex.: revisar/testar assim que a issue chega, sem deixar na fila).</li>
                        <li>Resolver bloqueios rápido — escalar dependências no mesmo dia em vez de deixar a issue "esperando".</li>
                        <li>Quebrar issues grandes em menores, que fluem sem ficar dias em uma só etapa.</li>
                    </ul>
                </div>
                <div class="flow-interpret-col flow-interpret-down">
                    <h4>▼ O que faz o valor DESCER (negativo)</h4>
                    <p><strong>Causa:</strong> a issue fica muito tempo parada em relação ao tempo trabalhado — ou seja, o Lead Time cresce por causa de espera, não de trabalho.</p>
                    <p><strong>Exemplos do que evitar (não fazer):</strong></p>
                    <ul>
                        <li>Não abrir muitas issues em paralelo e deixá-las todas "In Progress" sem concluir (WIP alto).</li>
                        <li>Não deixar issues paradas aguardando revisão, teste ou aprovação por dias.</li>
                        <li>Não ignorar bloqueios — uma issue bloqueada e esquecida derruba a eficiência da semana.</li>
                        <li>Não reabrir/empurrar issues repetidamente sem trabalhá-las, inflando o tempo de espera.</li>
                    </ul>
                </div>
            </div>
        </section>
    `;
}

function renderFlowEfficiencyWeeklyChart(data, flowData) {
    const ctx = document.getElementById('flowEffWeeklyCanvas').getContext('2d');

    function weekToDateRange(weekStr) {
        const [yearStr, wStr] = weekStr.split('-W');
        const year = parseInt(yearStr);
        const week = parseInt(wStr);
        const jan4 = new Date(year, 0, 4);
        const dayOfWeek = jan4.getDay() || 7;
        const monday = new Date(jan4);
        monday.setDate(jan4.getDate() - dayOfWeek + 1 + (week - 1) * 7);
        const sunday = new Date(monday);
        sunday.setDate(monday.getDate() + 6);
        const fmt = (d) => `${String(d.getDate()).padStart(2,'0')}/${String(d.getMonth()+1).padStart(2,'0')}`;
        return `${fmt(monday)} - ${fmt(sunday)}`;
    }

    const labels = data.weeks.map(w => weekToDateRange(w.week));

    const datasets = [{
        label: 'Flow Efficiency semanal (%)',
        data: data.weeks.map(w => w.avg_efficiency),
        borderColor: T('--chart-5'),
        backgroundColor: hexA(T('--chart-5'), '1a'),
        borderWidth: 2,
        tension: 0.3,
        fill: true,
    }];

    // Linha de referência: média histórica geral (mesmo valor do card à esquerda)
    const avgGeral = (flowData && flowData.count > 0) ? flowData.avg_efficiency : null;
    if (avgGeral !== null) {
        datasets.push({
            label: `Média geral (${avgGeral}%)`,
            data: labels.map(() => avgGeral),
            borderColor: T('--text-2'),
            borderWidth: 1.5,
            borderDash: [6, 4],
            pointRadius: 0,
            tension: 0,
            fill: false,
        });
    }

    if (flowEffWeeklyChart) flowEffWeeklyChart.destroy();
    flowEffWeeklyChart = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'bottom', labels: { color: T('--text-1'), font: { size: 11 } } },
                tooltip: {
                    callbacks: {
                        afterTitle: (items) => `${data.weeks[items[0].dataIndex].count} issues resolvidas`,
                        label: (c) => `${c.dataset.label}: ${c.raw}%`
                    }
                }
            },
            scales: {
                x: {
                    ticks: { color: T('--text-2'), maxTicksLimit: 13, font: { size: 10 } },
                    grid: { display: false }
                },
                y: {
                    title: { display: true, text: 'Flow Efficiency (%)', color: T('--text-2'), font: { size: 11 } },
                    ticks: { color: T('--text-2'), callback: (v) => v + '%' },
                    grid: { color: T('--chart-grid') },
                    beginAtZero: true,
                    max: 100,
                }
            }
        }
    });
}

// --- CFD ---
function renderCFDSection(data) {
    if (!data.data || data.data.length === 0) {
        return `<section class="metric-section glass">
            <h2>Cumulative Flow Diagram</h2>
            <p class="metric-desc">Sem dados.</p>
        </section>`;
    }

    return `
        <section class="metric-section glass">
            <h2>Cumulative Flow Diagram (90 dias)</h2>
            <p class="metric-desc">Mostra quantidade de issues em cada status ao longo do tempo. "Barrigas" indicam acúmulo (gargalo).</p>
            <details class="formula-details">
                <summary>Como é calculado?</summary>
                <div class="formula-content">
                    <p><strong>CFD</strong> = snapshot diário de quantas issues estavam em cada status naquele dia.</p>
                    <p><strong>Algoritmo</strong>: coleta todos os eventos (criação de issue = entra em "Open", cada transição de status = sai do anterior e entra no novo). Varre dia a dia mantendo contadores por status.</p>
                    <p><strong>Janela</strong>: últimos 90 dias.</p>
                    <p><strong>Leitura</strong>: bandas estreitas e paralelas = fluxo saudável. Bandas que se abrem ("barrigas") = acúmulo naquele status (gargalo). Bandas que convergem = trabalho sendo completado.</p>
                </div>
            </details>
            <div class="chart-container">
                <canvas id="cfdCanvas"></canvas>
            </div>
        </section>
    `;
}

function renderCFDChart(data) {
    const ctx = document.getElementById('cfdCanvas').getContext('2d');
    const labels = data.data.map(d => d.date);
    // Done/Blocked usam cor semantica (leitura direta de bom/ruim); os demais
    // status sao categoricos e usam a paleta de grafico do design system.
    const statusColors = {
        'Done': T('--ok'), 'Blocked': T('--risk'),
        'In Progress': T('--chart-1'), 'Test': T('--chart-3'),
        'Waiting for Delivery': T('--chart-4'), 'Review': T('--chart-3'),
        'Refinement': T('--chart-2'), 'To do': T('--warn'),
        'Open': T('--text-3'), 'Backlog': T('--chart-5')
    };

    const datasets = data.statuses.map(status => ({
        label: status,
        data: data.data.map(d => d.counts[status] || 0),
        backgroundColor: (statusColors[status] || T('--chart-6')) + '80',
        borderColor: statusColors[status] || T('--chart-6'),
        borderWidth: 1,
        fill: true,
        tension: 0.3,
    }));

    if (cfdChart) cfdChart.destroy();
    cfdChart = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { position: 'bottom', labels: { color: T('--text-1'), font: { size: 11 } } },
            },
            scales: {
                x: {
                    ticks: { color: T('--text-2'), maxTicksLimit: 15, font: { size: 10 } },
                    grid: { display: false }
                },
                y: {
                    stacked: true,
                    ticks: { color: T('--text-2') },
                    grid: { color: T('--chart-grid') }
                }
            }
        }
    });
}

// --- Aging WIP ---
function renderAgingWIP(data) {
    if (!data.p85_ms || data.p85_ms === 0) {
        return `<section class="metric-section glass">
            <h2>Aging WIP</h2>
            <p class="metric-desc">Sem dados de P85 para comparar. Execute sincronização para popular.</p>
        </section>`;
    }

    let rows = '';
    if (data.issues.length === 0) {
        rows = '<tr><td colspan="7" style="text-align:center; color: var(--success); padding: 1rem;">Nenhuma issue acima do P85. Fluxo saudável!</td></tr>';
    } else {
        rows = data.issues.map(i => {
            const statusClass = i.status === 'In Progress' ? 'progress' : (i.status === 'Blocked' ? 'blocked' : 'other');
            return `
                <tr>
                    <td><strong><a href="https://jiraps.atlassian.net/browse/${i.key}" target="_blank" rel="noopener" style="color:#3b82f6;text-decoration:none">${i.key}</a></strong></td>
                    <td style="max-width:300px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${i.summary || ''}</td>
                    <td><span class="status-badge status-${statusClass}">${i.status}</span></td>
                    <td>${i.assignee || '--'}</td>
                    <td>${formatDateShort(i.due_date)}</td>
                    <td>${formatDateShort(i.updated_at)}</td>
                    <td class="highlight">${fmtDays(i.cycle_time_ms)} (${fmtDays(i.over_p85_ms)} acima)</td>
                </tr>
            `;
        }).join('');
    }

    return `
        <section class="metric-section glass">
            <h2>Aging WIP</h2>
            <p class="metric-desc">Issues ativas com cycle time acima do P85 histórico de Cycle Time (${fmtDays(data.p85_ms)}). Estas issues precisam de atenção.</p>
            <details class="formula-details">
                <summary>Como é calculado?</summary>
                <div class="formula-content">
                    <p><strong>Aging WIP</strong> = issues em estados ativos (In Progress, Blocked, Test, Waiting for Delivery) cujo <em>cycle time acumulado até agora</em> excede o P85 histórico do projeto.</p>
                    <p><strong>P85 de referência</strong>: calculado com base em todas as issues que já tiveram cycle time (inclui Done e ativas). Representa "85% das issues completam o ciclo ativo em até X dias".</p>
                    <p><strong>Cycle time (intervalo aberto)</strong>: para issues ainda ativas, o cycle time inclui o tempo desde a última entrada em estado ativo até agora.</p>
                    <p><strong>"Acima"</strong> = cycle_time atual − P85. Quanto maior, mais urgente a atenção.</p>
                </div>
            </details>
            <table class="metric-table">
                <thead>
                    <tr><th>Key</th><th>Summary</th><th>Status</th><th>Assignee</th><th>Due Date</th><th>Updated</th><th>Cycle Time</th></tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </section>
    `;
}

// --- Utils ---
function formatDateShort(dateStr) {
    if (!dateStr) return '--';
    const parts = dateStr.split('T')[0].split('-');
    if (parts.length === 3) {
        return `${parts[2]}/${parts[1]}/${parts[0]}`;
    }
    return dateStr;
}

function fmtDays(ms) {
    if (!ms || ms === 0) return '--';
    const days = ms / (1000 * 60 * 60 * 24);
    if (days < 1) {
        const hours = Math.round(ms / (1000 * 60 * 60));
        return `${hours}h`;
    }
    return `${days.toFixed(1)}d`;
}
