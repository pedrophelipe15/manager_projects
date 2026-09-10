/**
 * Dashboard V2 — Visão consolidada.
 * Big numbers + Initiatives (com drill-down) + Épicos Órfãos.
 */

const MS_TO_DAYS = 1 / 86400000;

function formatDays(ms) {
    if (!ms || ms <= 0) return "—";
    const days = ms * MS_TO_DAYS;
    return days < 1 ? `${Math.round(days * 24)}h` : `${Math.round(days)}d`;
}

function riskBadge(risk) {
    const labels = { done: "Done", low: "Low", medium: "Medium", high: "High", critical: "Critical" };
    return `<span class="risk-badge risk-${risk}">${labels[risk] || risk}</span>`;
}

function progressBar(pct, width = 80) {
    let color = "blue";
    if (pct >= 80) color = "green";
    else if (pct >= 50) color = "blue";
    else if (pct >= 25) color = "amber";
    else color = "red";
    return `<div class="progress-bar" style="width:${width}px"><div class="progress-fill ${color}" style="width:${Math.min(pct, 100)}%"></div></div><span class="progress-label">${pct}%</span>`;
}

async function init() {
    const container = document.getElementById("content-container");
    const kpiContainer = document.getElementById("kpi-container");

    try {
        const res = await fetch("/api/hierarchy/dashboard-v2");
        const data = await res.json();

        // === Big Numbers ===
        const bn = data.big_numbers;
        kpiContainer.innerHTML = `
            <div class="kpi-card">
                <div class="kpi-value accent">${bn.total_epics}</div>
                <div class="kpi-label">Epicos Total</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">${bn.total_initiatives}</div>
                <div class="kpi-label">Iniciativas</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value success">${bn.initiatives_with_epics}</div>
                <div class="kpi-label">Iniciativas c/ Epicos</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value warning">${bn.orphan_epics}</div>
                <div class="kpi-label">Epicos Orfaos</div>
            </div>
        `;

        let html = "";

        // === Seção: Initiatives ===
        const iniData = data.initiatives;
        if (iniData.initiatives && iniData.initiatives.length > 0) {
            html += renderInitiativesSection(iniData.initiatives);
        }

        // === Seção: Épicos Órfãos ===
        const orphans = data.orphan_epics;
        if (orphans.epics && orphans.epics.length > 0) {
            html += `<hr class="section-divider">`;
            html += renderOrphanEpicsSection(orphans);
        }

        if (!html) {
            html = `<p class="empty-state">Nenhum dado encontrado. Execute uma sincronizacao primeiro.</p>`;
        }

        container.innerHTML = html;

    } catch (err) {
        container.innerHTML = `<p class="empty-state">Erro ao carregar: ${err.message}</p>`;
        console.error(err);
    }
}

// === Initiatives Section (mesma estrutura do initiative-health) ===

function renderInitiativesSection(initiatives) {
    let rows = "";
    for (const ini of initiatives) {
        const i = ini.initiative;
        const pr = ini.progress;
        const fc = ini.forecast;

        rows += `
            <tr class="clickable" onclick="window.location.href='/hierarchy/initiative-health.html?key=${i.key}'">
                <td><strong>${jiraLink(i.key)}</strong></td>
                <td style="max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHTML(i.summary)}</td>
                <td>${progressBar(pr.weighted_progress_pct)}</td>
                <td style="text-align:center">${pr.done_stories}/${pr.total_stories}</td>
                <td style="text-align:center">${pr.total_epics}</td>
                <td style="text-align:center">${ini.teams.length}</td>
                <td style="text-align:center">${fc.p85 > 0 ? fc.p85 + "w" : "—"}</td>
                <td>${riskBadge(ini.risk)}</td>
            </tr>
        `;
    }

    return `
        <div class="metric-section glass">
            <h2 class="section-title">Iniciativas</h2>
            <p class="section-subtitle">Visao corporativa. Clique para detalhes dos epicos da iniciativa.</p>
            <table class="metric-table">
                <thead>
                    <tr>
                        <th>Key</th>
                        <th>Iniciativa</th>
                        <th>Progresso</th>
                        <th>Stories</th>
                        <th>Epicos</th>
                        <th>Times</th>
                        <th>Forecast P85</th>
                        <th>Risco</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
    `;
}

// === Orphan Epics Section (mesma estrutura do epic-health) ===

function renderOrphanEpicsSection(orphanData) {
    const epics = orphanData.epics;
    let rows = "";
    for (const e of epics) {
        const ep = e.epic;
        const pr = e.progress;
        const fc = e.forecast;

        rows += `
            <tr class="clickable" onclick="window.location.href='/hierarchy/epic-health.html?key=${ep.key}'">
                <td><strong>${jiraLink(ep.key)}</strong></td>
                <td style="max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHTML(ep.summary)}</td>
                <td>${progressBar(pr.progress_pct)}</td>
                <td style="text-align:center">${pr.done}/${pr.total}</td>
                <td style="text-align:center">${fc.p85 > 0 ? fc.p85 + "w" : "—"}</td>
                <td style="text-align:center">${formatDays(e.metrics.avg_cycle_time_ms)}</td>
                <td style="text-align:center">${formatDays(e.metrics.avg_lead_time_ms)}</td>
                <td>${riskBadge(e.risk)}</td>
            </tr>
        `;
    }

    return `
        <div class="metric-section glass">
            <h2 class="section-title">Epicos Orfaos</h2>
            <p class="section-subtitle">Epicos sem iniciativa vinculada. Clique para detalhes.</p>
            <table class="metric-table">
                <thead>
                    <tr>
                        <th>Key</th>
                        <th>Epic</th>
                        <th>Progresso</th>
                        <th>Done/Total</th>
                        <th>Forecast P85</th>
                        <th>Cycle Time</th>
                        <th>Lead Time</th>
                        <th>Risco</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
    `;
}

function escapeHTML(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function jiraLink(key) {
    return `<a href="https://jiraps.atlassian.net/browse/${key}" target="_blank" rel="noopener" style="color:var(--accent);text-decoration:none">${key}</a>`;
}

init();
