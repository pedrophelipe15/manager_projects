// Wave 4: Cross-time e Portfólio
const API4 = '/api/metrics/wave4';
let crossChart = null;

// Estado da tabela "Saude das Issues-Pai"
const epicState = {
    all: [],              // todos os épicos abertos (não-done)
    filterProject: '',    // '' = todos
    filterAssignee: '',   // '' = todos
    sortKey: 'risk',      // coluna ordenada
    sortDir: 'asc',       // 'asc' | 'desc'
    page: 1,
    pageSize: 25,
};

// Ordem de risco para ordenação
const RISK_ORDER = { critical: 0, high: 1, medium: 2, low: 3, done: 4 };

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

    // Inicializa filtros/ordenação/paginação da tabela de Issues-Pai
    initEpicHealth();
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

// Gera N cores distintas via HSL com matizes igualmente espaçados.
// Garante que cada projeto tenha uma cor diferente, independente da quantidade.
function distinctColors(n) {
    const colors = [];
    for (let i = 0; i < n; i++) {
        const hue = Math.round((360 / n) * i);
        // Alterna leve variação de saturação/luminosidade para vizinhos ficarem mais distinguíveis
        const sat = 65 + (i % 2) * 10;
        const light = 55 + (i % 3) * 5;
        colors.push(`hsl(${hue}, ${sat}%, ${light}%)`);
    }
    return colors;
}

function renderCrossChart(data) {
    const ctx = document.getElementById('crossCanvas').getContext('2d');
    const labels = data.weekly.map(w => w.week_label);

    const palette = distinctColors(data.projects.length);

    const datasets = data.projects.map((project, idx) => ({
        label: project,
        data: data.weekly.map(w => w.by_project[project] || 0),
        backgroundColor: palette[idx],
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

// Colunas ordenáveis: chave lógica -> rótulo
const EPIC_COLUMNS = [
    { key: '_project', label: 'Projeto' },
    { key: 'key', label: 'Key' },
    { key: 'summary', label: 'Summary' },
    { key: 'issue_type', label: 'Tipo' },
    { key: 'assignee', label: 'Assignee' },
    { key: 'due_date', label: 'Due Date' },
    { key: 'done_ratio', label: 'Done/Total' },
    { key: 'progress_pct', label: 'Progresso' },
    { key: 'forecast_p85_weeks', label: 'Forecast P85' },
    { key: 'risk', label: 'Risco' },
];

function renderEpicHealth(epicHealthResults) {
    // Combina todos os épicos de todos os projetos e filtra não-done
    let allEpics = [];
    for (const result of epicHealthResults) {
        if (result.epics) {
            for (const epic of result.epics) {
                epic._project = result.project_key;
                allEpics.push(epic);
            }
        }
    }
    allEpics = allEpics.filter(e => e.risk !== 'done');

    epicState.all = allEpics;
    epicState.page = 1;
    epicState.filterProject = '';
    epicState.filterAssignee = '';
    epicState.sortKey = 'risk';
    epicState.sortDir = 'asc';

    if (allEpics.length === 0) {
        return `<section class="metric-section glass">
            <h2>Saude das Issues-Pai</h2>
            <p class="metric-desc">Nenhuma issue-pai aberta encontrada.</p>
        </section>`;
    }

    return `
        <section class="metric-section glass">
            <h2>Saude das Issues-Pai</h2>
            <p class="metric-desc" id="epic-summary"></p>
            <details class="formula-details">
                <summary>Como e calculado?</summary>
                <div class="formula-content">
                    <p><strong>Progresso</strong> = subtasks Done / total subtasks.</p>
                    <p><strong>Forecast P85</strong> = Monte Carlo com throughput do projeto (1000 simulacoes).</p>
                    <p><strong>Risco</strong> = composicao de: due date vs forecast, progresso baixo com muitos itens restantes, e forecast longo (&gt;8 semanas).</p>
                    <p>Niveis: <span class="risk-badge risk-low">low</span> <span class="risk-badge risk-medium">medium</span> <span class="risk-badge risk-high">high</span> <span class="risk-badge risk-critical">critical</span></p>
                </div>
            </details>
            <div class="epic-filters">
                <label class="epic-filter">
                    <span>Projeto</span>
                    <select id="epicFilterProject" class="epic-select"></select>
                </label>
                <label class="epic-filter">
                    <span>Assignee</span>
                    <select id="epicFilterAssignee" class="epic-select"></select>
                </label>
                <label class="epic-filter">
                    <span>Por pagina</span>
                    <select id="epicPageSize" class="epic-select">
                        <option value="10">10</option>
                        <option value="25" selected>25</option>
                        <option value="50">50</option>
                        <option value="100">100</option>
                    </select>
                </label>
            </div>
            <table class="metric-table" id="epic-table">
                <thead><tr id="epic-thead-row"></tr></thead>
                <tbody id="epic-tbody"></tbody>
            </table>
            <div class="epic-pagination" id="epic-pagination"></div>
        </section>
    `;
}

// Popula filtros e desenha a tabela pela primeira vez (chamado após injetar o HTML)
function initEpicHealth() {
    if (!document.getElementById('epic-table')) return;
    if (!epicState.all.length) return;

    // Opções de filtro (distintos, ordenados)
    const projects = [...new Set(epicState.all.map(e => e._project).filter(Boolean))].sort();
    const assignees = [...new Set(epicState.all.map(e => e.assignee).filter(Boolean))].sort();

    const projSel = document.getElementById('epicFilterProject');
    projSel.innerHTML = `<option value="">Todos</option>` +
        projects.map(p => `<option value="${escapeHTML(p)}">${escapeHTML(p)}</option>`).join('');

    const asgSel = document.getElementById('epicFilterAssignee');
    asgSel.innerHTML = `<option value="">Todos</option>` +
        assignees.map(a => `<option value="${escapeHTML(a)}">${escapeHTML(a)}</option>`).join('');

    // Eventos
    projSel.addEventListener('change', () => { epicState.filterProject = projSel.value; epicState.page = 1; renderEpicTable(); });
    asgSel.addEventListener('change', () => { epicState.filterAssignee = asgSel.value; epicState.page = 1; renderEpicTable(); });
    document.getElementById('epicPageSize').addEventListener('change', (e) => {
        epicState.pageSize = parseInt(e.target.value, 10) || 25; epicState.page = 1; renderEpicTable();
    });

    renderEpicTable();
}

function getFilteredSortedEpics() {
    let list = epicState.all.slice();

    if (epicState.filterProject) list = list.filter(e => e._project === epicState.filterProject);
    if (epicState.filterAssignee) list = list.filter(e => (e.assignee || '') === epicState.filterAssignee);

    const key = epicState.sortKey;
    const dir = epicState.sortDir === 'desc' ? -1 : 1;

    list.sort((a, b) => {
        let va, vb;
        if (key === 'risk') { va = RISK_ORDER[a.risk] ?? 9; vb = RISK_ORDER[b.risk] ?? 9; }
        else if (key === 'done_ratio') { va = a.total ? a.done / a.total : 0; vb = b.total ? b.done / b.total : 0; }
        else if (key === 'progress_pct' || key === 'forecast_p85_weeks') { va = a[key] || 0; vb = b[key] || 0; }
        else if (key === 'due_date') { va = a.due_date || ''; vb = b.due_date || ''; }
        else { va = (a[key] || '').toString().toLowerCase(); vb = (b[key] || '').toString().toLowerCase(); }

        if (va < vb) return -1 * dir;
        if (va > vb) return 1 * dir;
        return 0;
    });

    return list;
}

function renderEpicTable() {
    const filtered = getFilteredSortedEpics();
    const total = filtered.length;
    const pageSize = epicState.pageSize;
    const totalPages = Math.max(1, Math.ceil(total / pageSize));
    if (epicState.page > totalPages) epicState.page = totalPages;
    const start = (epicState.page - 1) * pageSize;
    const pageItems = filtered.slice(start, start + pageSize);

    // Cabeçalho com indicadores de ordenação (clicável)
    const theadRow = document.getElementById('epic-thead-row');
    theadRow.innerHTML = EPIC_COLUMNS.map(col => {
        const isSorted = epicState.sortKey === col.key;
        const arrow = isSorted ? (epicState.sortDir === 'asc' ? ' ▲' : ' ▼') : '';
        return `<th class="epic-sortable${isSorted ? ' sorted' : ''}" data-key="${col.key}">${col.label}${arrow}</th>`;
    }).join('');
    theadRow.querySelectorAll('.epic-sortable').forEach(th => {
        th.addEventListener('click', () => {
            const key = th.dataset.key;
            if (epicState.sortKey === key) {
                epicState.sortDir = epicState.sortDir === 'asc' ? 'desc' : 'asc';
            } else {
                epicState.sortKey = key;
                epicState.sortDir = 'asc';
            }
            renderEpicTable();
        });
    });

    // Corpo
    const tbody = document.getElementById('epic-tbody');
    if (pageItems.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${EPIC_COLUMNS.length}" class="empty-state">Nenhuma issue-pai para os filtros selecionados.</td></tr>`;
    } else {
        tbody.innerHTML = pageItems.map(e => {
            const riskBadge = `<span class="risk-badge risk-${e.risk}">${e.risk}</span>`;
            const progressBar = `<div class="progress-bar"><div class="progress-fill" style="width:${e.progress_pct}%"></div></div>`;
            const forecast = e.forecast_p85_weeks > 0 ? `${e.forecast_p85_weeks} sem` : '--';
            const dueDate = e.due_date ? formatDateShort(e.due_date) : '--';
            return `
                <tr>
                    <td>${escapeHTML(e._project)}</td>
                    <td><strong><a href="https://jiraps.atlassian.net/browse/${e.key}" target="_blank" rel="noopener" style="color:#3b82f6;text-decoration:none">${escapeHTML(e.key)}</a></strong></td>
                    <td style="max-width:220px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHTML(e.summary)}</td>
                    <td>${escapeHTML(e.issue_type) || '--'}</td>
                    <td>${escapeHTML(e.assignee) || '--'}</td>
                    <td>${dueDate}</td>
                    <td>${e.done}/${e.total}</td>
                    <td style="min-width:90px;">${progressBar} <span class="progress-label">${e.progress_pct}%</span></td>
                    <td>${forecast}</td>
                    <td>${riskBadge}</td>
                </tr>
            `;
        }).join('');
    }

    // Resumo
    const atRisk = filtered.filter(e => e.risk === 'critical' || e.risk === 'high').length;
    const summary = document.getElementById('epic-summary');
    if (summary) {
        summary.innerHTML = `${total} issue(s)-pai (após filtros). ${atRisk > 0 ? `<strong>${atRisk} em risco.</strong>` : 'Nenhuma em risco critico/alto.'}`;
    }

    // Paginação
    const pag = document.getElementById('epic-pagination');
    const from = total === 0 ? 0 : start + 1;
    const to = Math.min(start + pageSize, total);
    pag.innerHTML = `
        <button class="epic-page-btn" id="epicPrev" ${epicState.page <= 1 ? 'disabled' : ''}>&larr; Anterior</button>
        <span class="epic-page-info">${from}–${to} de ${total} · pagina ${epicState.page}/${totalPages}</span>
        <button class="epic-page-btn" id="epicNext" ${epicState.page >= totalPages ? 'disabled' : ''}>Proxima &rarr;</button>
    `;
    const prev = document.getElementById('epicPrev');
    const next = document.getElementById('epicNext');
    if (prev) prev.addEventListener('click', () => { if (epicState.page > 1) { epicState.page--; renderEpicTable(); } });
    if (next) next.addEventListener('click', () => { if (epicState.page < totalPages) { epicState.page++; renderEpicTable(); } });
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
