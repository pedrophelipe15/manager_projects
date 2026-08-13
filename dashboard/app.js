let allIssues = [];

// Tab Switching Logic
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.view-section').forEach(v => v.classList.remove('active'));
        
        btn.classList.add('active');
        document.getElementById(btn.dataset.target).classList.add('active');
    });
});

// Data Loading and Processing
async function loadData() {
    try {
        const response = await fetch('../jira_mock.json');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        allIssues = data;
        processData(data);
        initFilters();
    } catch (error) {
        console.error("Could not load data:", error);
        document.getElementById('hdr-proj-code').innerText = "ERROR LOADING DATA";
    }
}

function processData(issues) {
    if(!issues || issues.length === 0) return;

    const totalIssues = issues.length;
    let doneIssues = 0;
    let inProgressIssues = 0;
    
    const projects = {};
    const assignees = {};
    const createdByMonth = {};
    const closedByMonth = {};

    let minDate = new Date();
    let maxDate = new Date('2000-01-01');

    issues.forEach(issue => {
        const status = issue.fields.status.name.toLowerCase();
        if (status === 'done' || status === 'closed') doneIssues++;
        else if (status === 'in progress') inProgressIssues++;

        // Project Grouping
        const projKey = issue.fields.project.key;
        if (!projects[projKey]) {
            projects[projKey] = { name: issue.fields.project.name, total: 0, done: 0, inProgress: 0 };
        }
        projects[projKey].total++;
        if (status === 'done' || status === 'closed') projects[projKey].done++;
        if (status === 'in progress') projects[projKey].inProgress++;

        // Assignee Grouping
        const assigneeName = issue.fields.assignee.displayName;
        if (!assignees[assigneeName]) {
            assignees[assigneeName] = { total: 0, done: 0, inProgress: 0 };
        }
        assignees[assigneeName].total++;
        if (status === 'done' || status === 'closed') assignees[assigneeName].done++;
        if (status === 'in progress') assignees[assigneeName].inProgress++;

        // Dates for S-Curve
        const createdDate = new Date(issue.fields.created);
        const cMonth = `${createdDate.getFullYear()}-${String(createdDate.getMonth()+1).padStart(2,'0')}`;
        createdByMonth[cMonth] = (createdByMonth[cMonth] || 0) + 1;

        if (createdDate < minDate) minDate = createdDate;

        if (status === 'done' || status === 'closed') {
            const updatedDate = new Date(issue.fields.updated);
            const uMonth = `${updatedDate.getFullYear()}-${String(updatedDate.getMonth()+1).padStart(2,'0')}`;
            closedByMonth[uMonth] = (closedByMonth[uMonth] || 0) + 1;
            
            if (updatedDate > maxDate) maxDate = updatedDate;
        }
    });

    const progressPercent = ((doneIssues / totalIssues) * 100).toFixed(1);

    document.getElementById('hdr-proj-code').innerText = "MULTI-PROJ";
    const today = new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
    document.getElementById('hdr-report-date').innerText = today;
    document.getElementById('hdr-data-date').innerText = today;
    
    const spi = (progressPercent / 50).toFixed(2);
    document.getElementById('hdr-spi').innerText = spi;
    document.getElementById('hdr-cpi').innerText = (spi * 0.95).toFixed(2);
    document.getElementById('hdr-eac').innerText = totalIssues;

    document.getElementById('sum-start').innerText = minDate.toLocaleDateString();
    document.getElementById('sum-finish').innerText = maxDate > new Date('2000-01-01') ? maxDate.toLocaleDateString() : 'N/A';
    document.getElementById('sum-duration').innerText = Math.max(1, Math.ceil(Math.abs(maxDate - minDate) / (1000 * 60 * 60 * 24))) + " Days";
    
    document.getElementById('sum-progress').innerText = `${progressPercent}%`;
    document.getElementById('sum-bac').innerText = totalIssues;
    document.getElementById('sum-eac').innerText = totalIssues;
    document.getElementById('sum-vac').innerText = totalIssues - doneIssues - inProgressIssues; // Open/Blocked

    renderQuantityTable(projects);
    renderAssigneeTable(assignees);
    // renderTimelineTable is now called by initFilters / filterTimeline

    renderSCurve(createdByMonth, closedByMonth);
    renderBarCharts(projects);
}

function renderQuantityTable(projects) {
    const tbody = document.getElementById('qty-tbody');
    tbody.innerHTML = '';
    
    let totalP = 0, totalD = 0, totalI = 0;
    Object.keys(projects).forEach(key => {
        const p = projects[key];
        const percent = ((p.done / p.total) * 100).toFixed(1);
        
        totalP += p.total; totalD += p.done; totalI += p.inProgress;
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${p.name}</td><td>${p.total}</td><td>${p.done}</td><td>${p.inProgress}</td><td>${percent}%</td>`;
        tbody.appendChild(tr);
    });

    const tr = document.createElement('tr');
    tr.style.fontWeight = 'bold';
    tr.style.background = '#f0f2f5';
    tr.innerHTML = `<td>TOTAL</td><td>${totalP}</td><td>${totalD}</td><td>${totalI}</td><td>${((totalD / totalP) * 100).toFixed(1)}%</td>`;
    tbody.appendChild(tr);
}

function renderAssigneeTable(assignees) {
    const tbody = document.getElementById('assignee-tbody');
    tbody.innerHTML = '';
    
    Object.keys(assignees).sort((a,b) => assignees[b].done - assignees[a].done).forEach(name => {
        const a = assignees[name];
        const percent = ((a.done / a.total) * 100).toFixed(1);
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${name}</td><td>${a.total}</td><td>${a.done}</td><td>${a.inProgress}</td><td>${percent}%</td>`;
        tbody.appendChild(tr);
    });
}

function renderTimelineTable(issues) {
    const tbody = document.getElementById('timeline-tbody');
    tbody.innerHTML = '';
    const displayIssues = issues.slice(0, 50);

    displayIssues.forEach(issue => {
        const tr = document.createElement('tr');
        const status = issue.fields.status.name;
        
        let statusClass = 'status-open';
        if (status.toLowerCase().includes('done') || status.toLowerCase().includes('closed')) statusClass = 'status-done';
        else if (status.toLowerCase().includes('progress')) statusClass = 'status-progress';

        tr.innerHTML = `
            <td>${issue.key}: ${issue.fields.summary.substring(0, 40)}...</td>
            <td>${issue.fields.assignee.displayName}</td>
            <td><span class="status-dot ${statusClass}"></span>${status}</td>
            <td>${new Date(issue.fields.created).toLocaleDateString()}</td>
            <td>${new Date(issue.fields.updated).toLocaleDateString()}</td>
        `;
        tbody.appendChild(tr);
    });
}

Chart.defaults.font.family = "'Inter', sans-serif";

function renderSCurve(createdData, closedData) {
    const ctx = document.getElementById('sCurveChart').getContext('2d');
    
    // Sort and get unique months
    const allMonths = [...new Set([...Object.keys(createdData), ...Object.keys(closedData)])].sort();
    
    let cumCreated = 0;
    let cumClosed = 0;
    
    const planned = [];
    const actual = [];

    allMonths.forEach(m => {
        cumCreated += (createdData[m] || 0);
        cumClosed += (closedData[m] || 0);
        
        planned.push(cumCreated);
        actual.push(cumClosed);
    });

    // Formatting YYYY-MM to better labels
    const labels = allMonths.map(m => {
        const [yyyy, mm] = m.split('-');
        const date = new Date(yyyy, mm - 1);
        return date.toLocaleDateString('en-GB', { month: 'short', year: '2-digit' });
    });

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Tickets Created (PV)',
                    data: planned,
                    borderColor: '#17a2b8',
                    tension: 0.4,
                    borderWidth: 2
                },
                {
                    label: 'Tickets Done (AC)',
                    data: actual,
                    borderColor: '#00a88f',
                    tension: 0.4,
                    borderWidth: 2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'top', labels: { boxWidth: 12, font: { size: 10 } } } },
            scales: { y: { beginAtZero: true } }
        }
    });
}

function renderBarCharts(projects) {
    const ctxQty = document.getElementById('qtyChart').getContext('2d');
    const ctxStatus = document.getElementById('statusChart').getContext('2d');
    
    const labels = Object.keys(projects);
    const totalData = labels.map(l => projects[l].total);
    const doneData = labels.map(l => projects[l].done);
    const progData = labels.map(l => projects[l].inProgress);

    new Chart(ctxQty, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                { label: 'Total Tickets', data: totalData, backgroundColor: '#17a2b8' },
                { label: 'Delivered (Done)', data: doneData, backgroundColor: '#00a88f' }
            ]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top', labels: { font: { size: 10 } } } } }
    });

    new Chart(ctxStatus, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                { label: 'In Progress', data: progData, backgroundColor: '#ffc107' },
                { label: 'Done', data: doneData, backgroundColor: '#28a745' }
            ]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top', labels: { font: { size: 10 } } } } }
    });
}

function initFilters() {
    const filterIds = ['filter-activity', 'filter-assignee', 'filter-status', 'filter-created', 'filter-updated'];
    filterIds.forEach(id => {
        document.getElementById(id).addEventListener('input', filterTimeline);
    });

    document.getElementById('clear-filters-btn').addEventListener('click', () => {
        filterIds.forEach(id => document.getElementById(id).value = '');
        filterTimeline();
    });
    
    filterTimeline(); // Initial render
}

function filterTimeline() {
    const act = document.getElementById('filter-activity').value.toLowerCase();
    const ass = document.getElementById('filter-assignee').value.toLowerCase();
    const stat = document.getElementById('filter-status').value.toLowerCase();
    const cre = document.getElementById('filter-created').value;
    const upd = document.getElementById('filter-updated').value;

    const filtered = allIssues.filter(issue => {
        const iAct = (issue.key + " " + issue.fields.summary).toLowerCase();
        const iAss = issue.fields.assignee.displayName.toLowerCase();
        const iStat = issue.fields.status.name.toLowerCase();
        
        const iCre = new Date(issue.fields.created).toISOString().split('T')[0];
        const iUpd = new Date(issue.fields.updated).toISOString().split('T')[0];

        if (act && !iAct.includes(act)) return false;
        if (ass && !iAss.includes(ass)) return false;
        if (stat && iStat !== stat) return false;
        if (cre && iCre !== cre) return false;
        if (upd && iUpd !== upd) return false;
        
        return true;
    });

    renderTimelineTable(filtered);
}

window.addEventListener('DOMContentLoaded', loadData);
