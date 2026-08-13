/* =========================================================================
   DADOS DE EXEMPLO (GERADOR SINTÉTICO)
   ========================================================================= */

function seededRandom(seed) {
  let s = seed;
  return function () { s = (s * 9301 + 49297) % 233280; return s / 233280; };
}

function mkIssue({ key, projectKey, projectName, created, transitions, resolutiondate, currentStatus, currentCat }) {
  const histories = transitions.map(t => ({ created: t.at, items: [{ field: 'status', toString: t.to, fromString: t.from }] }));
  return {
    key,
    fields: {
      summary: 'Item de exemplo',
      created,
      updated: transitions.length ? transitions[transitions.length - 1].at : created,
      resolutiondate: resolutiondate || null,
      project: { key: projectKey, name: projectName },
      assignee: null,
      priority: { name: 'P3' },
      status: { name: currentStatus, statusCategory: { key: currentCat, name: currentCat } }
    },
    changelog: { histories }
  };
}

function generateSampleData() {
  const teams = [
    { key: 'ATL', name: 'Atlas', baseCycle: 2.5, spread: 1.0, volume: 46 },
    { key: 'VEG', name: 'Vega', baseCycle: 5.5, spread: 2.2, volume: 30 },
    { key: 'NIM', name: 'Nimbus', baseCycle: 3.5, spread: 1.3, volume: 38 },
    { key: 'ORI', name: 'Orion', baseCycle: 8.0, spread: 3.5, volume: 21 }
  ];
  const rnd = seededRandom(42);
  const now = new Date();
  const issues = [];
  let counter = 1000;
  for (const team of teams) {
    for (let i = 0; i < team.volume; i++) {
      counter++;
      const daysAgo = 5 + rnd() * 80;
      const created = new Date(now.getTime() - daysAgo * 86400000);
      const cycleDays = Math.max(0.3, team.baseCycle + (rnd() - 0.3) * team.spread * 2);
      const startWip = new Date(created.getTime() + (0.5 + rnd() * 1.5) * 86400000);
      const finishDone = new Date(startWip.getTime() + cycleDays * 86400000);
      const isDoneFlag = finishDone < now && rnd() > 0.08;
      const isWipFlag = !isDoneFlag && startWip < now;
      const transitions = [];
      if (startWip < now) transitions.push({ at: startWip.toISOString(), from: 'To Do', to: 'In Progress' });
      if (isDoneFlag) transitions.push({ at: finishDone.toISOString(), from: 'In Progress', to: 'Done' });
      issues.push(mkIssue({
        key: `${team.key}-${counter}`, projectKey: team.key, projectName: team.name,
        created: created.toISOString(), transitions,
        resolutiondate: isDoneFlag ? finishDone.toISOString() : null,
        currentStatus: isDoneFlag ? 'Done' : (isWipFlag ? 'In Progress' : 'To Do'),
        currentCat: isDoneFlag ? 'done' : (isWipFlag ? 'indeterminate' : 'new')
      }));
    }
  }
  return issues;
}
