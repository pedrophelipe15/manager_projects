/* =========================================================================
   RENDERIZAÇÃO DA INTERFACE (CAMADAS 1, 2 e 3)
   ========================================================================= */

function fmt(n, decimals = 1) {
  return n === null || n === undefined ? '—' : n.toFixed(decimals);
}

function renderTeamCards(agg) {
  const container = document.getElementById('teamCardsContainer');
  if (!container) return;
  
  const maxP95 = Math.max(...Object.values(agg).map(t => t.cycle.p95 || 0), 1);
  container.innerHTML = Object.values(agg).map(t => {
    const p50pct = (t.cycle.p50 || 0) / maxP95 * 100;
    const p85pct = (t.cycle.p85 || 0) / maxP95 * 100;
    const p95pct = (t.cycle.p95 || 0) / maxP95 * 100;
    const wipHtml = t.wipLimit
      ? `<div class="wip-gauge" style="background:conic-gradient(${t.wip > t.wipLimit ? 'var(--coral)' : 'var(--teal)'} 0deg ${Math.min(360, (t.wip / t.wipLimit) * 360)}deg, var(--line-soft) 0deg);"><span>${Math.round(t.wip / t.wipLimit * 100)}%</span></div>`
      : `<div class="wip-gauge" style="background:var(--panel-2); font-size:14px;"><span style="background:var(--panel-2);">${t.wip}</span></div>`;
    return `
    <div class="card">
      <div class="card-top">
        <div>
          <div class="team-name">${t.name}</div>
          <div class="team-size mono">${t.totalIssues} issues no período · ${t.doneCount} concluídas</div>
        </div>
        <div class="dot" style="background:${t.color}; box-shadow:0 0 0 4px ${t.color}22;"></div>
      </div>
      <div class="metric-row"><span class="metric-label">Throughput · ${t.lastMonthLabel}</span></div>
      <div class="metric-value">${t.throughputLastMonth}<span class="metric-unit">itens concluídos</span></div>
      <div class="pct-track" style="margin-top:20px;">
        <div class="pct-seg" style="left:0; width:${p50pct}%; background:var(--teal);"></div>
        <div class="pct-seg" style="left:${p50pct}%; width:${Math.max(0, p85pct - p50pct)}%; background:var(--amber);"></div>
        <div class="pct-seg" style="left:${p85pct}%; width:${Math.max(0, p95pct - p85pct)}%; background:var(--coral);"></div>
      </div>
      <div class="pct-labels">
        <span>P50 <b>${fmt(t.cycle.p50)}d</b></span><span>P85 <b>${fmt(t.cycle.p85)}d</b></span><span>P95 <b>${fmt(t.cycle.p95)}d</b></span>
      </div>
      ${t.approxUsed ? '<div style="font-size:10px;color:var(--amber);margin-top:8px;">⚠ parte do cycle time usa aproximação (sem changelog completo)</div>' : ''}
      <div class="card-sub">
        <div class="wip-label">WIP atual${t.wipLimit ? ' / limite' : ''}<b>${t.wip}${t.wipLimit ? ' / ' + t.wipLimit : ''}</b></div>
        ${wipHtml}
      </div>
    </div>`;
  }).join('');
}

function renderPortfolio(agg) {
  const containerKpis = document.getElementById('portfolioKpis');
  const containerTable = document.getElementById('portfolioTableBody');
  if (!containerKpis || !containerTable) return;

  const teams = Object.values(agg);
  const totalThroughput = teams.reduce((s, t) => s + t.throughputLastMonth, 0);
  const p50s = teams.map(t => t.cycle.p50).filter(v => v !== null);
  const rangeMin = p50s.length ? Math.min(...p50s).toFixed(1) : '—';
  const rangeMax = p50s.length ? Math.max(...p50s).toFixed(1) : '—';

  containerKpis.innerHTML = `
    <div class="kpi-card">
      <span class="metric-label">Throughput total · ${teams[0]?.lastMonthLabel || ''}</span>
      <div class="metric-value">${totalThroughput}<span class="metric-unit">itens (soma dos times)</span></div>
    </div>
    <div class="kpi-card">
      <span class="metric-label">Faixa de cycle time (P50)</span>
      <div class="metric-value">${rangeMin}–${rangeMax}<span class="metric-unit">dias — não é média</span></div>
      <div class="kpi-note">Do time mais rápido ao mais lento. A média esconde qual time precisa de atenção.</div>
    </div>
    <div class="kpi-card">
      <span class="metric-label">Lead time fim-a-fim</span>
      <div class="metric-value" style="color:var(--blue);">—<span class="metric-unit">requer vínculo entre issues (Camada 02)</span></div>
    </div>
  `;

  containerTable.innerHTML = teams.map(t => {
    const trendVal = t.throughputPrevMonth > 0 ? ((t.throughputLastMonth - t.throughputPrevMonth) / t.throughputPrevMonth * 100) : null;
    const trendHtml = trendVal === null ? '<span class="trend">sem base</span>' :
      trendVal >= 0 ? `<span class="trend up">↑ ${trendVal.toFixed(0)}% throughput</span>` :
      `<span class="trend down">↓ ${Math.abs(trendVal).toFixed(0)}% throughput</span>`;
    return `
    <tr>
      <td>${t.name}</td>
      <td class="num">${fmt(t.cycle.p50)}d</td>
      <td class="num">${fmt(t.cycle.p95)}d</td>
      <td class="num">${t.throughputLastMonth}</td>
      <td class="num" style="${t.wipLimit && t.wip > t.wipLimit ? 'color:var(--coral);' : ''}">${t.wip}${t.wipLimit ? ' / ' + t.wipLimit : ''}</td>
      <td class="num">${trendHtml}</td>
    </tr>`;
  }).join('');
}

function render(issues, sourceLabel) {
  const agg = aggregateByTeam(issues);
  renderTeamCards(agg);
  renderPortfolio(agg);
  const metaSource = document.getElementById('metaSource');
  const metaCount = document.getElementById('metaCount');
  if (metaSource) metaSource.textContent = sourceLabel;
  if (metaCount) metaCount.textContent = issues.length;
}
