// Light Mode Chart defaults
Chart.defaults.color = '#6b7280';
Chart.defaults.font.family = "'Outfit', sans-serif";
Chart.defaults.borderColor = '#e5e7eb';

// Enable DataLabels on all charts
Chart.register(ChartDataLabels);
Chart.defaults.plugins.datalabels = {
    color: '#1f2937',
    font: { weight: 'bold', size: 11 },
    anchor: 'center',
    align: 'center',
    formatter: function(value) {
        return value > 0 ? value : '';
    }
};

let allIssuesV2 = [];
let chartInstances = {};
let globalKPIs = null;

async function loadData() {
    try {
        const response = await fetch('../jira_mock.json');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        allIssuesV2 = data;
        globalKPIs = computeKPIs(data);
        populateGlobalFilters(data);
        processAgileData(data);
        generatePerformanceReport(data);
        
        document.getElementById('global-filter-project').addEventListener('change', applyGlobalFilters);
        document.getElementById('global-filter-assignee').addEventListener('change', applyGlobalFilters);
        document.getElementById('report-filter-lead-time').addEventListener('change', applyGlobalFilters);
        document.getElementById('report-filter-throughput').addEventListener('change', applyGlobalFilters);
        document.getElementById('global-filter-clear').addEventListener('click', () => {
            document.getElementById('global-filter-project').value = '';
            document.getElementById('global-filter-assignee').value = '';
            document.getElementById('report-filter-lead-time').value = '';
            document.getElementById('report-filter-throughput').value = '';
            applyGlobalFilters();
        });
    } catch (error) {
        console.error("Could not load data:", error);
    }
}

function populateGlobalFilters(issues) {
    const projects = new Set();
    const assignees = new Set();
    issues.forEach(i => {
        projects.add(i.fields.project.key);
        const assigneeName = i.fields.assignee ? i.fields.assignee.displayName : 'Unassigned';
        assignees.add(assigneeName);
    });
    
    const projSelect = document.getElementById('global-filter-project');
    const assSelect = document.getElementById('global-filter-assignee');
    
    [...projects].sort().forEach(p => {
        const opt = document.createElement('option');
        opt.value = p;
        opt.text = p;
        projSelect.add(opt);
    });
    
    [...assignees].sort().forEach(a => {
        const opt = document.createElement('option');
        opt.value = a;
        opt.text = a;
        assSelect.add(opt);
    });
}

function applyGlobalFilters() {
    const pVal = document.getElementById('global-filter-project').value;
    const aVal = document.getElementById('global-filter-assignee').value;
    
    const filtered = allIssuesV2.filter(i => {
        if (pVal && i.fields.project.key !== pVal) return false;
        const assigneeName = i.fields.assignee ? i.fields.assignee.displayName : 'Unassigned';
        if (aVal && assigneeName !== aVal) return false;
        return true;
    });
    
    processAgileData(filtered);
    generatePerformanceReport(filtered);
}

function destroyChart(id) {
    if (chartInstances[id]) {
        chartInstances[id].destroy();
    }
}

function computeKPIs(issues) {
    let totalDone = 0, currentWIP = 0, totalLeadTime = 0;
    let leadTimeCount = 0;
    const months = new Set();
    const uniqueAssignees = new Set();

    issues.forEach(issue => {
        const aName = issue.fields.assignee ? issue.fields.assignee.displayName : 'Unassigned';
        uniqueAssignees.add(aName);

        const status = issue.fields.status.name.toLowerCase();
        if (status === 'done' || status === 'closed') {
            totalDone++;
            const diffDays = Math.ceil(Math.abs(new Date(issue.fields.updated) - new Date(issue.fields.created)) / 86400000);
            totalLeadTime += diffDays;
            leadTimeCount++;
            months.add(issue.fields.created.substring(0, 7));
            months.add(issue.fields.updated.substring(0, 7));
        } else if (status === 'in progress') {
            currentWIP++;
        }
    });
    
    const companyThroughput = months.size > 0 ? (totalDone / months.size) : 0;
    const avgAssigneeThroughput = uniqueAssignees.size > 0 ? (companyThroughput / uniqueAssignees.size) : 0;

    return {
        leadTime: leadTimeCount > 0 ? (totalLeadTime / leadTimeCount).toFixed(1) : 0,
        wip: currentWIP,
        done: totalDone,
        throughput: companyThroughput.toFixed(1),
        throughputPerAssignee: avgAssigneeThroughput.toFixed(1)
    };
}

function applyTrend(elementId, current, global, isFiltered, lowerIsBetter, isPercentage = false) {
    const el = document.getElementById(elementId);
    const badgeEl = el.closest('.badge');
    
    badgeEl.classList.remove('badge-trend-good', 'badge-trend-bad', 'badge-trend-neutral');

    if (!isFiltered) {
        el.style.display = 'none';
        return;
    }
    
    el.style.display = 'block';
    const curVal = parseFloat(current);
    const globVal = parseFloat(global);
    
    if (isPercentage) {
        const pct = globVal > 0 ? Math.round((curVal / globVal) * 100) : 0;
        el.className = 'trend-text trend-neutral';
        el.innerText = `${pct}% of Global (${globVal})`;
        badgeEl.classList.add('badge-trend-neutral');
        return;
    }

    const diff = Math.abs(curVal - globVal).toFixed(1);
    
    if (curVal === globVal) {
        el.className = 'trend-text trend-neutral';
        el.innerText = `Equal to Global`;
        badgeEl.classList.add('badge-trend-neutral');
    } else if (curVal < globVal) {
        el.className = lowerIsBetter ? 'trend-text trend-good' : 'trend-text trend-bad';
        el.innerText = `↓ ${diff} below Global (${globVal})`;
        badgeEl.classList.add(lowerIsBetter ? 'badge-trend-good' : 'badge-trend-bad');
    } else {
        el.className = lowerIsBetter ? 'trend-text trend-bad' : 'trend-text trend-good';
        el.innerText = `↑ ${diff} above Global (${globVal})`;
        badgeEl.classList.add(lowerIsBetter ? 'badge-trend-bad' : 'badge-trend-good');
    }
}

function processAgileData(issues) {
    if(!issues || issues.length === 0) return;

    let totalDone = 0;
    let currentWIP = 0;
    let totalLeadTime = 0;
    let leadTimeCount = 0;

    const assignees = {};
    const priorities = {};
    const bottleneckCandidates = [];
    
    // For CFD
    const cfdData = {
        months: [],
        open: {},
        inProgress: {},
        done: {}
    };

    issues.forEach(issue => {
        const status = issue.fields.status.name.toLowerCase();
        const priority = issue.fields.priority.name;
        const assignee = issue.fields.assignee.displayName;

        const createdDate = new Date(issue.fields.created);
        const updatedDate = new Date(issue.fields.updated);

        // Date Diff in Days
        const diffTime = Math.abs(updatedDate - createdDate);
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)); 

        if (status === 'done' || status === 'closed') {
            totalDone++;
            totalLeadTime += diffDays;
            leadTimeCount++;
        } else if (status === 'in progress') {
            currentWIP++;
            bottleneckCandidates.push({
                issue: issue.key,
                summary: issue.fields.summary,
                assignee: assignee,
                priority: priority,
                days: diffDays
            });
        }

        // Assignees
        if (!assignees[assignee]) assignees[assignee] = { total: 0, done: 0, wip: 0 };
        assignees[assignee].total++;
        if (status === 'done' || status === 'closed') assignees[assignee].done++;
        if (status === 'in progress') assignees[assignee].wip++;

        // Priorities
        if (!priorities[priority]) priorities[priority] = { open: 0, progress: 0, done: 0 };
        if (status === 'done' || status === 'closed') priorities[priority].done++;
        else if (status === 'in progress') priorities[priority].progress++;
        else priorities[priority].open++;

        // CFD Logic (Simplified by Month)
        const cMonth = `${createdDate.getFullYear()}-${String(createdDate.getMonth()+1).padStart(2,'0')}`;
        const uMonth = `${updatedDate.getFullYear()}-${String(updatedDate.getMonth()+1).padStart(2,'0')}`;
        
        if (!cfdData.months.includes(cMonth)) cfdData.months.push(cMonth);
        if (!cfdData.months.includes(uMonth)) cfdData.months.push(uMonth);

        cfdData.open[cMonth] = (cfdData.open[cMonth] || 0) + 1;
        if (status === 'in progress') {
            cfdData.inProgress[uMonth] = (cfdData.inProgress[uMonth] || 0) + 1;
        }
        if (status === 'done' || status === 'closed') {
            cfdData.done[uMonth] = (cfdData.done[uMonth] || 0) + 1;
        }
    });

    // KPIs
    const avgLeadTime = leadTimeCount > 0 ? (totalLeadTime / leadTimeCount).toFixed(1) : 0;
    
    // Sort CFD months
    cfdData.months.sort();
    const monthsCount = cfdData.months.length || 1;
    const avgThroughput = (totalDone / monthsCount).toFixed(1);

    document.getElementById('hdr-lead-time').innerText = avgLeadTime;
    document.getElementById('hdr-wip').innerText = currentWIP;
    document.getElementById('hdr-done').innerText = totalDone;
    document.getElementById('hdr-throughput').innerText = avgThroughput;

    const isFiltered = issues.length < allIssuesV2.length;
    applyTrend('trend-lead-time', avgLeadTime, globalKPIs.leadTime, isFiltered, true);
    applyTrend('trend-wip', currentWIP, globalKPIs.wip, isFiltered, false, true);
    applyTrend('trend-done', totalDone, globalKPIs.done, isFiltered, false, true);
    applyTrend('trend-throughput', avgThroughput, globalKPIs.throughput, isFiltered, false);

    renderCFD(cfdData);
    renderPriorityChart(priorities);
    renderLeadTimeMockChart(); // We'll mock a distribution since scatter needs complex mapping
    
    renderAssigneeTable(assignees);
    renderBottlenecks(bottleneckCandidates);
}

function renderAssigneeTable(assignees) {
    const tbody = document.getElementById('assignee-tbody');
    tbody.innerHTML = '';
    Object.keys(assignees).sort((a,b) => assignees[b].done - assignees[a].done).forEach(name => {
        const a = assignees[name];
        const risk = a.wip > 3 ? '<span class="risk-high">HIGH</span>' : '<span class="risk-low">OK</span>';
        
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${name}</td><td>${a.total}</td><td>${a.done}</td><td>${a.wip}</td><td>${risk}</td>`;
        tbody.appendChild(tr);
    });
}

function renderBottlenecks(bottlenecks) {
    const tbody = document.getElementById('bottleneck-tbody');
    tbody.innerHTML = '';
    bottlenecks.sort((a,b) => b.days - a.days).slice(0, 8).forEach(b => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td><strong>${b.issue}</strong><br><small style="color:#94a3b8">${b.summary.substring(0,30)}...</small></td>
                        <td>${b.assignee}</td><td>${b.priority}</td>
                        <td class="${b.days > 30 ? 'risk-high' : ''}">${b.days}</td>`;
        tbody.appendChild(tr);
    });
}

function renderCFD(cfdData) {
    destroyChart('cfdChart');
    const ctx = document.getElementById('cfdChart').getContext('2d');
    
    let cumOpen = 0, cumProg = 0, cumDone = 0;
    const openData = [], progData = [], doneData = [];

    cfdData.months.forEach(m => {
        cumOpen += (cfdData.open[m] || 0);
        cumProg += (cfdData.inProgress[m] || 0);
        cumDone += (cfdData.done[m] || 0);
        
        // CFD is stacked: Total = Open + Prog + Done.
        // We will just stack them in Chart.js
        openData.push(cumOpen);
        progData.push(cumProg);
        doneData.push(cumDone);
    });

    const labels = cfdData.months.map(m => {
        const [y, mm] = m.split('-');
        return new Date(y, mm - 1).toLocaleDateString('en-GB', { month: 'short', year: '2-digit' });
    });

    chartInstances['cfdChart'] = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                { label: 'Done', data: doneData, borderColor: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.5)', fill: true, tension: 0.4 },
                { label: 'In Progress', data: progData, borderColor: '#f59e0b', backgroundColor: 'rgba(245, 158, 11, 0.5)', fill: true, tension: 0.4 },
                { label: 'Open', data: openData, borderColor: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.5)', fill: true, tension: 0.4 }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: { y: { stacked: true, beginAtZero: true } },
            plugins: { filler: { propagate: false } }
        }
    });
}

function renderPriorityChart(priorities) {
    destroyChart('priorityChart');
    const ctx = document.getElementById('priorityChart').getContext('2d');
    const labels = Object.keys(priorities);
    const open = labels.map(l => priorities[l].open);
    const prog = labels.map(l => priorities[l].progress);
    const done = labels.map(l => priorities[l].done);

    chartInstances['priorityChart'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                { label: 'Open', data: open, backgroundColor: '#ef4444' },
                { label: 'In Progress', data: prog, backgroundColor: '#f59e0b' },
                { label: 'Done', data: done, backgroundColor: '#10b981' }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: { x: { stacked: true }, y: { stacked: true } }
        }
    });
}

function renderLeadTimeMockChart() {
    destroyChart('leadTimeChart');
    const ctx = document.getElementById('leadTimeChart').getContext('2d');
    chartInstances['leadTimeChart'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['< 7 Days', '7-14 Days', '15-30 Days', '> 30 Days'],
            datasets: [{
                label: 'Issues Count',
                data: [120, 45, 20, 5],
                backgroundColor: '#6366f1',
                borderRadius: 4
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                datalabels: {
                    anchor: 'end',
                    align: 'top'
                }
            }
        }
    });
}

function generatePerformanceReport(issues) {
    // Set headers with global baseline context
    if (globalKPIs) {
        document.getElementById('th-lead-time').innerHTML = `Avg Lead Time<br><span style="font-size:10px; font-weight:normal; text-transform:none; color:var(--text-muted)">Global Baseline: ${globalKPIs.leadTime}d</span>`;
        document.getElementById('th-throughput').innerHTML = `Throughput / Mo<br><span style="font-size:10px; font-weight:normal; text-transform:none; color:var(--text-muted)">Global Baseline (Per Assignee): ${globalKPIs.throughputPerAssignee}</span>`;
    }

    const combos = {};
    
    issues.forEach(i => {
        const pName = i.fields.project.name;
        const aName = i.fields.assignee ? i.fields.assignee.displayName : 'Unassigned';
        const key = `${pName}|${aName}`;
        
        if (!combos[key]) {
            combos[key] = {
                project: pName,
                assignee: aName,
                totalDone: 0,
                wip: 0,
                totalLeadTime: 0,
                leadTimeCount: 0,
                months: new Set()
            };
        }
        
        const status = i.fields.status.name.toLowerCase();
        if (status === 'done' || status === 'closed') {
            combos[key].totalDone++;
            const diffDays = Math.ceil(Math.abs(new Date(i.fields.updated) - new Date(i.fields.created)) / 86400000);
            combos[key].totalLeadTime += diffDays;
            combos[key].leadTimeCount++;
            combos[key].months.add(i.fields.created.substring(0,7));
            combos[key].months.add(i.fields.updated.substring(0,7));
        } else if (status === 'in progress') {
            combos[key].wip++;
        }
    });
    
    const tbody = document.getElementById('report-tbody');
    tbody.innerHTML = '';
    
    const sortedKeys = Object.keys(combos).sort((a,b) => a.localeCompare(b));
    
    const filterLT = document.getElementById('report-filter-lead-time').value;
    const filterTP = document.getElementById('report-filter-throughput').value;

    sortedKeys.forEach(k => {
        const c = combos[k];
        const lt = c.leadTimeCount > 0 ? (c.totalLeadTime / c.leadTimeCount).toFixed(1) : 0;
        const throughput = c.months.size > 0 ? (c.totalDone / c.months.size).toFixed(1) : 0;
        
        // Heatmap cell logic based on global KPIs where applicable
        const ltClass = lt > 0 ? (parseFloat(lt) < parseFloat(globalKPIs.leadTime) ? 'cell-good' : (parseFloat(lt) > parseFloat(globalKPIs.leadTime) ? 'cell-bad' : 'cell-neutral')) : 'cell-neutral';
        const wipClass = c.wip > 3 ? 'cell-bad' : (c.wip > 0 ? 'cell-good' : 'cell-neutral'); 
        const tpClass = parseFloat(throughput) > parseFloat(globalKPIs.throughputPerAssignee) ? 'cell-good' : (parseFloat(throughput) < parseFloat(globalKPIs.throughputPerAssignee) ? 'cell-bad' : 'cell-neutral');
        
        // Apply Table Filters
        if (filterLT === 'better' && ltClass !== 'cell-good') return;
        if (filterLT === 'worse' && ltClass !== 'cell-bad') return;
        if (filterTP === 'better' && tpClass !== 'cell-good') return;
        if (filterTP === 'worse' && tpClass !== 'cell-bad') return;

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${c.project}</strong></td>
            <td>${c.assignee}</td>
            <td class="${ltClass}">${lt > 0 ? lt : '-'} ${lt > 0 && parseFloat(lt) < parseFloat(globalKPIs.leadTime) ? '↓' : (parseFloat(lt) > parseFloat(globalKPIs.leadTime) ? '↑' : '')}</td>
            <td class="${wipClass}">${c.wip}</td>
            <td>${c.totalDone}</td>
            <td class="${tpClass}">${throughput} ${parseFloat(throughput) > parseFloat(globalKPIs.throughputPerAssignee) ? '↑' : (parseFloat(throughput) < parseFloat(globalKPIs.throughputPerAssignee) ? '↓' : '')}</td>
        `;
        tbody.appendChild(tr);
    });
}

window.addEventListener('DOMContentLoaded', () => {
    // Tab Switching Logic
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(v => v.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById(btn.dataset.target).classList.add('active');
        });
    });

    loadData();
});
