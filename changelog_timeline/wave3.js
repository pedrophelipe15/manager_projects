// Wave 3: Pessoas e Qualidade
const API3 = '/api/metrics/wave3';
let workloadChart = null;

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

    if (!key) {
        container.innerHTML = '<p class="empty-state">Selecione um projeto para visualizar as metricas de pessoas.</p>';
        return;
    }

    container.innerHTML = '<p class="empty-state">Carregando...</p>';

    try {
        const [wip, workload, handoff, rework] = await Promise.all([
            fetch(`${API3}/wip?project_key=${key}`).then(r => r.json()),
            fetch(`${API3}/workload?project_key=${key}`).then(r => r.json()),
            fetch(`${API3}/handoff?project_key=${key}`).then(r => r.json()),
            fetch(`${API3}/rework?project_key=${key}`).then(r => r.json()),
        ]);
        renderAll(wip, workload, handoff, rework);
    } catch (e) {
        container.innerHTML = '<p class="empty-state">Erro ao carregar metricas.</p>';
        console.error(e);
    }
}

function renderAll(wip, workload, handoff, rework) {
    const container = document.getElementById('content-container');
    let html = '<div class="metrics-grid">';

    html += renderWIP(wip);
    html += renderWorkload(workload);
    html += renderHandoff(handoff);
    html += renderRework(rework);

    html += '</div>';
    container.innerHTML = html;

    if (workload.people && workload.people.length > 0) {
        renderWorkloadChart(workload);
    }
}

// --- WIP por pessoa ---
function renderWIP(data) {
    if (!data.people || data.people.length === 0) {
        return `<section class="metric-section glass">
            <h2>WIP por Pessoa</h2>
            <p class="metric-desc">Nenhuma issue ativa com assignee encontrada.</p>
        </section>`;
    }

    const s = data.summary;
    let rows = data.people.map(p => {
        const riskClass = p.risk === 'high' ? 'risk-high' : (p.risk === 'medium' ? 'risk-medium' : '');
        const issues = p.issues.map(i => `<a href="https://jiraps.atlassian.net/browse/${i.key}" target="_blank" rel="noopener" class="wip-issue" title="${escapeHTML(i.summary)}" style="color:#3b82f6;text-decoration:none">${i.key}</a>`).join(' ');
        const blockedCount = p.blocked_count || 0;
        const blockedIssues = (p.blocked_issues || []).map(i => `<a href="https://jiraps.atlassian.net/browse/${i.key}" target="_blank" rel="noopener" class="wip-issue blocked-issue" title="${escapeHTML(i.summary)}" style="color:#3b82f6;text-decoration:none">${i.key}</a>`).join(' ');
        return `
            <tr class="${riskClass}">
                <td><strong>${escapeHTML(p.name)}</strong></td>
                <td class="wip-count ${p.wip_count >= 6 ? 'highlight-danger' : (p.wip_count >= 4 ? 'highlight-warning' : '')}">${p.wip_count}</td>
                <td class="wip-issues-cell">${issues}</td>
                <td class="wip-count ${blockedCount > 0 ? 'highlight-blocked' : ''}">${blockedCount}</td>
                <td class="wip-issues-cell">${blockedIssues || '—'}</td>
            </tr>
        `;
    }).join('');

    return `
        <section class="metric-section glass">
            <h2>WIP por Pessoa</h2>
            <p class="metric-desc">Issues simultaneas em estados ativos por pessoa. Acima de 3 indica multitasking excessivo.</p>
            <details class="formula-details">
                <summary>Como e calculado?</summary>
                <div class="formula-content">
                    <p><strong>WIP</strong> = quantidade de issues atribuidas a uma pessoa que estao em estados ativos (In Progress, Test) neste momento.</p>
                    <p><strong>Risco</strong>: 1-3 = saudavel, 4-5 = atencao (multitasking), 6+ = critico (context-switching constante).</p>
                    <p><strong>Referencia</strong>: limite ideal de WIP individual e 2-3 itens simultaneos.</p>
                </div>
            </details>
            <div class="kpis-row">
                <div class="kpi-box"><div class="kpi-label">Pessoas ativas</div><div class="kpi-value">${s.total_people}</div></div>
                <div class="kpi-box"><div class="kpi-label">WIP medio</div><div class="kpi-value">${s.avg_wip}</div></div>
                <div class="kpi-box"><div class="kpi-label">Sobrecarregados (4+)</div><div class="kpi-value ${s.overloaded > 0 ? 'warning' : ''}">${s.overloaded}</div></div>
                <div class="kpi-box"><div class="kpi-label">Max WIP</div><div class="kpi-value ${s.max_wip >= 6 ? 'warning' : ''}">${s.max_wip}</div></div>
            </div>
            <table class="metric-table">
                <thead><tr><th>Pessoa</th><th>WIP</th><th>Issues</th><th>Blocked</th><th>Issues Blocked</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </section>
    `;
}

// --- Distribuição de carga ---
function renderWorkload(data) {
    if (!data.people || data.people.length === 0) {
        return `<section class="metric-section glass">
            <h2>Distribuicao de Carga</h2>
            <p class="metric-desc">Sem dados de entregas.</p>
        </section>`;
    }

    const s = data.summary;
    let giniClass = s.gini > 0.5 ? 'warning' : (s.gini > 0.35 ? '' : 'accent');
    let busClass = s.bus_factor <= 2 ? 'warning' : '';

    let rows = data.people.slice(0, 15).map(p => {
        const bar = `<div class="bar-container"><div class="bar-fill" style="width:${p.percentage}%"></div></div>`;
        return `
            <tr>
                <td><strong>${escapeHTML(p.name)}</strong></td>
                <td>${p.done_count}</td>
                <td>${p.percentage}%</td>
                <td>${p.cumulative_pct}%</td>
                <td style="min-width:100px;">${bar}</td>
            </tr>
        `;
    }).join('');

    return `
        <section class="metric-section glass">
            <h2>Distribuicao de Carga</h2>
            <p class="metric-desc">${s.total_done} issues Done nas ultimas ${data.weeks} semanas por ${s.total_people} pessoas.</p>
            <details class="formula-details">
                <summary>Como e calculado?</summary>
                <div class="formula-content">
                    <p><strong>Distribuicao</strong> = issues resolvidas agrupadas por assignee nas ultimas ${data.weeks} semanas.</p>
                    <p><strong>Gini</strong> = coeficiente de desigualdade (0 = carga igual, 1 = tudo em 1 pessoa). Acima de 0.5 = concentracao preocupante.</p>
                    <p><strong>Bus Factor</strong> = minimo de pessoas que fazem 50%+ das entregas. Se = 1-2, risco alto de parar se alguem sair.</p>
                </div>
            </details>
            <div class="kpis-row">
                <div class="kpi-box"><div class="kpi-label">Gini (desigualdade)</div><div class="kpi-value ${giniClass}">${s.gini}</div></div>
                <div class="kpi-box"><div class="kpi-label">Bus Factor</div><div class="kpi-value ${busClass}">${s.bus_factor}</div></div>
                <div class="kpi-box"><div class="kpi-label">Top contribuidor</div><div class="kpi-value">${s.top_contributor_pct}%</div></div>
                <div class="kpi-box"><div class="kpi-label">Total entregas</div><div class="kpi-value">${s.total_done}</div></div>
            </div>
            <div class="chart-container chart-medium">
                <canvas id="workloadCanvas"></canvas>
            </div>
            <table class="metric-table">
                <thead><tr><th>Pessoa</th><th>Entregas</th><th>%</th><th>Acum.</th><th>Proporcao</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        </section>
    `;
}

function renderWorkloadChart(data) {
    const ctx = document.getElementById('workloadCanvas').getContext('2d');
    const people = data.people.slice(0, 12);
    const labels = people.map(p => p.name.split(' ').slice(0, 2).join(' '));
    const values = people.map(p => p.done_count);

    if (workloadChart) workloadChart.destroy();
    workloadChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Issues Done',
                data: values,
                backgroundColor: 'rgba(59, 130, 246, 0.6)',
                borderColor: '#3b82f6',
                borderWidth: 1,
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.05)' }, beginAtZero: true },
                y: { ticks: { color: '#f8fafc', font: { size: 11 } }, grid: { display: false } }
            }
        }
    });
}

// --- Handoff ---
function renderHandoff(data) {
    const s = data.summary;
    if (!s || s.total_handoffs === 0) {
        return `<section class="metric-section glass">
            <h2>Handoff Time</h2>
            <p class="metric-desc">Nenhuma mudanca de assignee registrada.</p>
        </section>`;
    }

    let pairRows = (data.pairs || []).slice(0, 8).map(p => `
        <tr>
            <td>${escapeHTML(p.from)}</td>
            <td>→</td>
            <td>${escapeHTML(p.to)}</td>
            <td><strong>${p.count}</strong></td>
        </tr>
    `).join('');

    let issueRows = (data.top_issues || []).slice(0, 8).map(i => `
        <tr><td><strong><a href="https://jiraps.atlassian.net/browse/${i.key}" target="_blank" rel="noopener" style="color:#3b82f6;text-decoration:none">${i.key}</a></strong></td><td>${i.handoff_count} handoffs</td></tr>
    `).join('');

    return `
        <section class="metric-section glass">
            <h2>Handoff Time</h2>
            <p class="metric-desc">Transferencias de responsabilidade entre pessoas. Handoffs frequentes indicam gargalo de coordenacao.</p>
            <details class="formula-details">
                <summary>Como e calculado?</summary>
                <div class="formula-content">
                    <p><strong>Handoff</strong> = mudanca no campo "assignee" do Jira (uma pessoa passa a issue para outra).</p>
                    <p><strong>Tempo entre handoffs</strong> = intervalo medio entre transferencias consecutivas na mesma issue.</p>
                    <p><strong>Risco</strong>: muitos handoffs por issue = coordenacao excessiva, cada transferencia adiciona espera.</p>
                </div>
            </details>
            <div class="kpis-row">
                <div class="kpi-box"><div class="kpi-label">Total handoffs</div><div class="kpi-value">${s.total_handoffs}</div></div>
                <div class="kpi-box"><div class="kpi-label">Issues afetadas</div><div class="kpi-value">${s.issues_with_handoffs}</div></div>
                <div class="kpi-box"><div class="kpi-label">Media por issue</div><div class="kpi-value">${s.avg_handoffs_per_issue}</div></div>
                <div class="kpi-box"><div class="kpi-label">Tempo medio entre</div><div class="kpi-value">${formatHours(s.avg_time_between_handoffs_hours)}</div></div>
            </div>
            <div class="two-col">
                <div>
                    <h3 class="sub-title">Pares mais frequentes</h3>
                    <table class="metric-table compact">
                        <thead><tr><th>De</th><th></th><th>Para</th><th>Qtd</th></tr></thead>
                        <tbody>${pairRows}</tbody>
                    </table>
                </div>
                <div>
                    <h3 class="sub-title">Issues com mais handoffs</h3>
                    <table class="metric-table compact">
                        <thead><tr><th>Issue</th><th>Handoffs</th></tr></thead>
                        <tbody>${issueRows}</tbody>
                    </table>
                </div>
            </div>
        </section>
    `;
}

// --- Retrabalho ---
function renderRework(data) {
    const s = data.summary;
    if (!s || s.total_issues === 0) {
        return `<section class="metric-section glass">
            <h2>Retrabalho</h2>
            <p class="metric-desc">Sem dados de transicoes.</p>
        </section>`;
    }

    let reworkClass = s.rework_rate_pct > 30 ? 'warning' : (s.rework_rate_pct > 15 ? '' : 'accent');

    let typeRows = (data.top_rework_types || []).map(t => `
        <tr><td>${escapeHTML(t.type)}</td><td><strong>${t.count}</strong></td></tr>
    `).join('');

    let issueRows = (data.issues || []).slice(0, 10).map(i => `
        <tr>
            <td><strong><a href="https://jiraps.atlassian.net/browse/${i.key}" target="_blank" rel="noopener" style="color:#3b82f6;text-decoration:none">${i.key}</a></strong></td>
            <td style="max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHTML(i.summary)}</td>
            <td>${i.status}</td>
            <td>${i.assignee || '--'}</td>
            <td class="highlight-warning">${i.rework_count}x</td>
        </tr>
    `).join('');

    return `
        <section class="metric-section glass">
            <h2>Retrabalho</h2>
            <p class="metric-desc">Issues com transicoes "para tras" no fluxo (ex: Done→In Progress). Indica qualidade ou escopo mal definido.</p>
            <details class="formula-details">
                <summary>Como e calculado?</summary>
                <div class="formula-content">
                    <p><strong>Retrabalho</strong> = transicao de status para um estado anterior na ordem logica do fluxo (Open → To do → Refinement → In Progress → Test → Waiting for Delivery → Done).</p>
                    <p><strong>Taxa</strong> = % de issues que tiveram pelo menos 1 transicao para tras.</p>
                    <p><strong>Causa tipica</strong>: requisito incompleto, bug encontrado em QA, ou mudanca de escopo apos inicio do trabalho.</p>
                </div>
            </details>
            <div class="kpis-row">
                <div class="kpi-box"><div class="kpi-label">Taxa de retrabalho</div><div class="kpi-value ${reworkClass}">${s.rework_rate_pct}%</div></div>
                <div class="kpi-box"><div class="kpi-label">Issues com retrabalho</div><div class="kpi-value">${s.issues_with_rework}</div></div>
                <div class="kpi-box"><div class="kpi-label">Transicoes para tras</div><div class="kpi-value">${s.total_rework_transitions}</div></div>
                <div class="kpi-box"><div class="kpi-label">% das transicoes</div><div class="kpi-value">${s.rework_transition_pct}%</div></div>
            </div>
            <div class="two-col">
                <div>
                    <h3 class="sub-title">Tipos de retrabalho mais comuns</h3>
                    <table class="metric-table compact">
                        <thead><tr><th>Transicao</th><th>Qtd</th></tr></thead>
                        <tbody>${typeRows}</tbody>
                    </table>
                </div>
                <div>
                    <h3 class="sub-title">Issues com mais retrabalho</h3>
                    <table class="metric-table compact">
                        <thead><tr><th>Key</th><th>Summary</th><th>Status</th><th>Assignee</th><th>Vezes</th></tr></thead>
                        <tbody>${issueRows}</tbody>
                    </table>
                </div>
            </div>
        </section>
    `;
}

// --- Utils ---
function formatHours(hours) {
    if (!hours || hours === 0) return '--';
    if (hours < 24) return `${hours.toFixed(0)}h`;
    return `${(hours / 24).toFixed(1)}d`;
}

function escapeHTML(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, tag => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[tag] || tag));
}
