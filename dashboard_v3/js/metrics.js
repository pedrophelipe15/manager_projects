/* =========================================================================
   CONFIGURAÇÃO & CONSTANTES
   ========================================================================= */

const TEAM_DISPLAY_NAME = {
  // 'ATL': 'Squad Atlas',
};

const TEAM_WIP_LIMITS = {
  // 'ATL': 16,
};

const STATUS_CATEGORY_FALLBACK = {
  'Backlog': 'new', 'To Do': 'new', 'Open': 'new',
  'In Progress': 'indeterminate', 'Em Andamento': 'indeterminate', 'Code Review': 'indeterminate',
  'Done': 'done', 'Concluído': 'done', 'Resolved': 'done'
};

const COLORS = ['var(--teal)', 'var(--amber)', 'var(--coral)', 'var(--blue)', '#B084F0', '#4FD1E8'];

/* =========================================================================
   NÚCLEO DE CÁLCULO E ESTATÍSTICA DE FLUXO
   ========================================================================= */

function daysBetween(a, b) {
  if (!a || !b) return null;
  return (new Date(b) - new Date(a)) / 86400000;
}

function percentile(sortedArr, p) {
  if (!sortedArr.length) return null;
  const idx = (p / 100) * (sortedArr.length - 1);
  const lo = Math.floor(idx), hi = Math.ceil(idx);
  if (lo === hi) return sortedArr[lo];
  return sortedArr[lo] + (sortedArr[hi] - sortedArr[lo]) * (idx - lo);
}

function monthKey(dateStr) {
  const d = new Date(dateStr);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function statusCategoryOf(issue, toStringName) {
  if (toStringName) return STATUS_CATEGORY_FALLBACK[toStringName] || null;
  return issue.fields.status.statusCategory.key;
}

function isDone(issue) { return issue.fields.status.statusCategory.key === 'done'; }
function isWip(issue) { return issue.fields.status.statusCategory.key === 'indeterminate'; }

function getCycleTimeDays(issue) {
  const histories = issue.changelog && issue.changelog.histories;
  if (!histories || !histories.length) return { value: null, reason: 'sem changelog' };
  let startTs = null, endTs = null;
  for (const h of histories) {
    for (const item of (h.items || [])) {
      if (item.field !== 'status') continue;
      const toCat = statusCategoryOf(issue, item.toString);
      if (toCat === 'indeterminate' && !startTs) startTs = h.created;
      if (toCat === 'done') endTs = h.created;
    }
  }
  if (!endTs && issue.fields.resolutiondate) endTs = issue.fields.resolutiondate;
  if (!startTs || !endTs) return { value: null, reason: 'transições incompletas' };
  return { value: daysBetween(startTs, endTs) };
}

function getCycleTimeApprox(issue) {
  if (!isDone(issue)) return null;
  const end = issue.fields.resolutiondate || issue.fields.updated;
  return daysBetween(issue.fields.created, end);
}

function getLeadTimeDays(issue) {
  if (!isDone(issue)) return null;
  const end = issue.fields.resolutiondate || issue.fields.updated;
  return daysBetween(issue.fields.created, end);
}

function lastClosedMonths(n) {
  const now = new Date();
  const out = [];
  for (let i = 1; i <= n; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  }
  return out;
}

function aggregateByTeam(issues) {
  const byProject = {};
  for (const iss of issues) {
    const pk = iss.fields.project.key;
    if (!byProject[pk]) byProject[pk] = { key: pk, name: TEAM_DISPLAY_NAME[pk] || iss.fields.project.name, issues: [] };
    byProject[pk].issues.push(iss);
  }
  const [lastMonth, prevMonth] = lastClosedMonths(2);
  const result = {};
  Object.keys(byProject).forEach((pk, i) => {
    const group = byProject[pk];
    const doneIssues = group.issues.filter(isDone);
    const wipCount = group.issues.filter(isWip).length;

    const cycleTimes = [];
    let approxUsed = false;
    for (const iss of doneIssues) {
      const ct = getCycleTimeDays(iss);
      if (ct.value !== null && ct.value >= 0) { cycleTimes.push(ct.value); }
      else {
        const approx = getCycleTimeApprox(iss);
        if (approx !== null && approx >= 0) { cycleTimes.push(approx); approxUsed = true; }
      }
    }
    cycleTimes.sort((a, b) => a - b);

    const throughputByMonth = {};
    for (const iss of doneIssues) {
      const end = iss.fields.resolutiondate || iss.fields.updated;
      const mk = monthKey(end);
      throughputByMonth[mk] = (throughputByMonth[mk] || 0) + 1;
    }

    result[pk] = {
      key: pk,
      name: group.name,
      color: COLORS[i % COLORS.length],
      totalIssues: group.issues.length,
      doneCount: doneIssues.length,
      wip: wipCount,
      wipLimit: TEAM_WIP_LIMITS[pk] || null,
      approxUsed,
      cycle: {
        p50: percentile(cycleTimes, 50),
        p85: percentile(cycleTimes, 85),
        p95: percentile(cycleTimes, 95),
        n: cycleTimes.length
      },
      throughputLastMonth: throughputByMonth[lastMonth] || 0,
      throughputPrevMonth: throughputByMonth[prevMonth] || 0,
      lastMonthLabel: lastMonth
    };
  });
  return result;
}
