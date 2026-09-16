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
        const [timePerStatus, percentiles, flowEff, cfd, aging, percWeekly] = await Promise.all([
            fetch(`${API}/time-per-status?project_key=${key}`).then(r => r.json()),
            fetch(`${API}/percentiles?project_key=${key}`).then(r => r.json()),
            fetch(`${API}/flow-efficiency?project_key=${key}`).then(r => r.json()),
            fetch(`${API}/cfd?project_key=${key}`).then(r => r.json()),
            fetch(`${API}/aging-wip?project_key=${key}`).then(r => r.json()),
            fetch(`${API}/percentiles-weekly?project_key=${key}`).then(r => r.json()),
        ]);
        renderAll(timePerStatus, percentiles, flowEff, cfd, aging, percWeekly);
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

function renderAll(timePerStatus, percentiles, flowEff, cfd, aging, percWeekly) {
    const container = document.getElementById('content-container');
    let html = '<div class="metrics-grid">';

    // 1. Percentis + Flow Efficiency (unificados)
    html += renderPercentiles(percentiles, flowEff);

    // 1.5. Timeline semanal de percentis
    html += renderPercentilesWeekly(percWeekly);

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
}

// --- Percentis ---
function renderPercentiles(data, flowData) {
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
            analysis = `Das ${flowData.count} issues analisadas, o time apresentou ${eff}% de Flow Efficiency, classificado como <strong>desempenho excelente</strong>. Isso indica que ${workPct}% do lead time foi dedicado ao desenvolvimento efetivo, com apenas ${waitPct}% em periodos de espera. O fluxo esta altamente otimizado com minimo desperdicio.`;
        } else if (eff >= 25) {
            colorClass = 'good';
            classification = 'bom';
            analysis = `Das ${flowData.count} issues analisadas, o time apresentou ${eff}% de Flow Efficiency, classificado como <strong>bom desempenho</strong> e proximo da faixa de excelencia. Isso indica que cerca de ${workPct}% do lead time foi dedicado ao desenvolvimento efetivo, enquanto aproximadamente ${waitPct}% correspondeu a periodos de espera, apontando oportunidades de otimizacao principalmente nas etapas de bloqueio, testes e disponibilizacao para entrega.`;
        } else if (eff >= 15) {
            colorClass = 'moderate';
            classification = 'tipico';
            analysis = `Das ${flowData.count} issues analisadas, o time apresentou ${eff}% de Flow Efficiency, classificado como <strong>desempenho tipico</strong> do mercado. Isso indica que apenas ${workPct}% do lead time foi dedicado ao desenvolvimento efetivo, enquanto ${waitPct}% correspondeu a espera em filas (bloqueio, testes, disponibilizacao). Ha espaco significativo para melhoria reduzindo handoffs e tempos de espera entre etapas.`;
        } else {
            colorClass = 'danger';
            classification = 'baixo';
            analysis = `Das ${flowData.count} issues analisadas, o time apresentou ${eff}% de Flow Efficiency, classificado como <strong>desempenho baixo</strong>. Isso indica que apenas ${workPct}% do lead time foi dedicado ao desenvolvimento efetivo, enquanto ${waitPct}% foi espera. Issues passam a maior parte do tempo paradas em filas. Acoes urgentes: limitar WIP, reduzir handoffs e eliminar etapas desnecessarias de aprovacao.`;
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
                    <span class="flow-scale scale-moderate">● 15-25% tipica</span>
                    <span class="flow-scale scale-good">● 25-40% boa</span>
                    <span class="flow-scale scale-success">● &gt;40% excelente</span>
                </div>
            </div>
        `;
    }

    return `
        <section class="metric-section glass">
            <h2>Percentis de Lead Time, Cycle Time e Flow Efficiency</h2>
            <p class="metric-desc">Quanto tempo leva para completar issues e qual a eficiencia do fluxo.</p>
            ${flowHtml}
            <div class="charts-row">
                <div>
                    <h3 style="font-size:0.9rem; color: var(--text-muted); margin-bottom:0.4rem;">Lead Time (${lead.count || 0} issues Done)</h3>
                    <p class="inline-formula">Tempo total desde a criacao da issue ate sua resolucao (resolved_at − created_at). Tempo calendario.</p>
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
            <p class="inline-formula" style="margin-top:0.5rem;"><strong>Percentis</strong>: P85 = "85% das issues terminam em ate X dias" (metodo nearest-rank). Usa apenas issues com valor &gt; 0.</p>
        </section>
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

function renderPercentilesWeekly(data) {
    if (!data.weeks || data.weeks.length === 0) {
        return `<section class="metric-section glass">
            <h2>Evolução Semanal dos Percentis</h2>
            <p class="metric-desc">Sem dados. Execute sincronização com issues Done para popular.</p>
        </section>`;
    }

    return `
        <section class="metric-section glass">
            <h2>Evolução Semanal dos Percentis</h2>
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
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    beginAtZero: true,
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
                    grid: { color: 'rgba(255,255,255,0.05)' }
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
