/**
 * Roadmap — Visualização timeline de stories hierárquicas.
 * Busca dados de /api/hierarchy/roadmap e renderiza Gantt simplificado.
 * Filtros segregados: um set para Iniciativas, outro para Órfãos.
 */

let dataInitiatives = [];
let dataOrphans = [];
let filtersIni = { initiative: [], epic: [], project: [], status: [], assignee: [] };
let filtersOrphan = { epic: [], project: [], status: [], assignee: [] };

// ==================== HELPERS ====================

function getMonthsRange() {
    const now = new Date();
    const months = [];
    for (let i = -1; i <= 4; i++) {
        const d = new Date(now.getFullYear(), now.getMonth() + i, 1);
        months.push({
            key: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`,
            label: d.toLocaleDateString("pt-BR", { month: "short" }).toUpperCase().replace(".", ""),
            year: d.getFullYear(),
        });
    }
    return months;
}

function getBarClass(status) {
    if (status === "Blocked") return "blocked";
    if (status === "In Progress") return "in-progress";
    if (status === "Done" || status === "Canceled") return "done";
    return "default";
}

function getStatusBadgeClass(status) {
    if (status === "Blocked") return "status-blocked";
    if (status === "In Progress") return "status-in-progress";
    if (status === "Done" || status === "Canceled") return "status-done";
    return "status-default";
}

function getTimelineDate(story) {
    if ((story.status === "Done" || story.status === "Canceled") && story.resolved_at) return story.resolved_at;
    return story.due_date;
}

function getMonthKey(dateStr) {
    if (!dateStr) return null;
    const d = new Date(dateStr);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function formatShortDate(dateStr) {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function jiraLink(key) {
    return `<a href="https://jiraps.atlassian.net/browse/${key}" target="_blank" rel="noopener" class="story-key">${key}</a>`;
}

function countDone(stories) {
    const total = stories.length;
    const done = stories.filter(s => s.status === "Done" || s.status === "Canceled").length;
    const pct = total > 0 ? Math.round(done / total * 100) : 0;
    return { total, done, pct };
}

// ==================== FILTROS ====================

function buildDropdown(id, label, options, selected) {
    const cbs = options.map(o => {
        const checked = selected.includes(o) ? " checked" : "";
        return `<label class="dd-option"><input type="checkbox" value="${o}"${checked} onchange="onFilterChange('${id.split('-')[0]}')"><span>${o}</span></label>`;
    }).join("");
    const count = selected.length;
    const countHtml = count > 0 ? `(${count})` : "";
    return `<div class="dd-wrapper" id="${id}"><button class="dd-toggle" onclick="toggleDropdown('${id}')"><span class="dd-label">${label}</span><span class="dd-count" id="${id}-count">${countHtml}</span><span class="dd-arrow">&#9662;</span></button><div class="dd-menu">${cbs}</div></div>`;
}

function getFilteredInitiativeContext() {
    // Dados filtrados pela iniciativa selecionada (para calcular opções dos outros filtros)
    let inits = dataInitiatives;
    if (filtersIni.initiative.length > 0) inits = inits.filter(i => filtersIni.initiative.includes(i.key));
    let epics = inits.flatMap(i => i.epics);
    if (filtersIni.epic.length > 0) epics = epics.filter(e => filtersIni.epic.includes(e.key));
    const stories = epics.flatMap(e => e.stories);
    return { inits, epics, stories };
}

function buildInitiativeFilters() {
    const ctx = getFilteredInitiativeContext();
    // Opções: Iniciativa sempre mostra todas, demais são contextuais
    const allInitiatives = dataInitiatives.map(i => i.key);
    const epicOptions = ctx.inits.flatMap(i => i.epics.map(e => e.key)).sort();
    const projectOptions = [...new Set(ctx.stories.map(s => s.project_key).filter(Boolean))].sort();
    const statusOptions = [...new Set(ctx.stories.map(s => s.status).filter(Boolean))].sort();
    const assigneeOptions = [...new Set(ctx.stories.map(s => s.assignee_name).filter(Boolean))].sort();

    // Remove seleções inválidas (épico que não pertence mais ao contexto)
    filtersIni.epic = filtersIni.epic.filter(e => epicOptions.includes(e));
    filtersIni.project = filtersIni.project.filter(p => projectOptions.includes(p));
    filtersIni.status = filtersIni.status.filter(s => statusOptions.includes(s));
    filtersIni.assignee = filtersIni.assignee.filter(a => assigneeOptions.includes(a));

    return `<div class="filters-row">
        ${buildDropdown("ini-initiative", "Iniciativa", allInitiatives, filtersIni.initiative)}
        ${buildDropdown("ini-epic", "Epico", epicOptions, filtersIni.epic)}
        ${buildDropdown("ini-project", "Projeto", projectOptions, filtersIni.project)}
        ${buildDropdown("ini-status", "Status", statusOptions, filtersIni.status)}
        ${buildDropdown("ini-assignee", "Assignee", assigneeOptions, filtersIni.assignee)}
        <button class="btn-clear-filters" onclick="clearFiltersIni()">Limpar</button>
        <span class="legend-inline"><span class="legend-item"><span class="legend-dot" style="background:#dc3545"></span> Blocked</span><span class="legend-item"><span class="legend-dot" style="background:#0d6efd"></span> In Progress</span><span class="legend-item"><span class="legend-dot" style="background:#10b981"></span> Done/Canceled</span><span class="legend-item"><span class="legend-dot" style="background:#6c757d"></span> Outros</span></span>
    </div>`;
}

function getFilteredOrphanContext() {
    let epics = dataOrphans;
    if (filtersOrphan.epic.length > 0) epics = epics.filter(e => filtersOrphan.epic.includes(e.key));
    const stories = epics.flatMap(e => e.stories);
    return { epics, stories };
}

function buildOrphanFilters() {
    const ctx = getFilteredOrphanContext();
    const epicOptions = dataOrphans.map(e => e.key).sort();
    const projectOptions = [...new Set(ctx.stories.map(s => s.project_key).filter(Boolean))].sort();
    const statusOptions = [...new Set(ctx.stories.map(s => s.status).filter(Boolean))].sort();
    const assigneeOptions = [...new Set(ctx.stories.map(s => s.assignee_name).filter(Boolean))].sort();

    filtersOrphan.project = filtersOrphan.project.filter(p => projectOptions.includes(p));
    filtersOrphan.status = filtersOrphan.status.filter(s => statusOptions.includes(s));
    filtersOrphan.assignee = filtersOrphan.assignee.filter(a => assigneeOptions.includes(a));

    return `<div class="filters-row">
        ${buildDropdown("orp-epic", "Epico", epicOptions, filtersOrphan.epic)}
        ${buildDropdown("orp-project", "Projeto", projectOptions, filtersOrphan.project)}
        ${buildDropdown("orp-status", "Status", statusOptions, filtersOrphan.status)}
        ${buildDropdown("orp-assignee", "Assignee", assigneeOptions, filtersOrphan.assignee)}
        <button class="btn-clear-filters" onclick="clearFiltersOrphan()">Limpar</button>
        <span class="legend-inline"><span class="legend-item"><span class="legend-dot" style="background:#dc3545"></span> Blocked</span><span class="legend-item"><span class="legend-dot" style="background:#0d6efd"></span> In Progress</span><span class="legend-item"><span class="legend-dot" style="background:#10b981"></span> Done/Canceled</span><span class="legend-item"><span class="legend-dot" style="background:#6c757d"></span> Outros</span></span>
    </div>`;
}

function toggleDropdown(id) {
    const menu = document.getElementById(id).querySelector(".dd-menu");
    const isOpen = menu.classList.contains("open");
    document.querySelectorAll(".dd-menu.open").forEach(m => m.classList.remove("open"));
    if (!isOpen) menu.classList.add("open");
}

document.addEventListener("click", (e) => {
    if (!e.target.closest(".dd-wrapper")) document.querySelectorAll(".dd-menu.open").forEach(m => m.classList.remove("open"));
});

function onFilterChange(section) {
    if (section === "ini") {
        filtersIni.initiative = getChecked("ini-initiative");
        filtersIni.epic = getChecked("ini-epic");
        filtersIni.project = getChecked("ini-project");
        filtersIni.status = getChecked("ini-status");
        filtersIni.assignee = getChecked("ini-assignee");
        // Rebuild filtros (dinâmico) + roadmap
        const filtersContainer = document.querySelector("#section-initiatives .filters-row");
        if (filtersContainer) filtersContainer.outerHTML = buildInitiativeFilters();
        renderInitiativesSection();
    } else {
        filtersOrphan.epic = getChecked("orp-epic");
        filtersOrphan.project = getChecked("orp-project");
        filtersOrphan.status = getChecked("orp-status");
        filtersOrphan.assignee = getChecked("orp-assignee");
        const filtersContainer = document.querySelector("#section-orphans .filters-row");
        if (filtersContainer) filtersContainer.outerHTML = buildOrphanFilters();
        renderOrphansSection();
    }
}

function getChecked(id) {
    const el = document.getElementById(id);
    return el ? [...el.querySelectorAll("input:checked")].map(cb => cb.value) : [];
}

function updateBadgesFor(prefix) {
    document.querySelectorAll(`[id^="${prefix}-"]`).forEach(wrapper => {
        const countEl = document.getElementById(wrapper.id + "-count");
        if (countEl) {
            const c = getChecked(wrapper.id).length;
            countEl.textContent = c > 0 ? `(${c})` : "";
        }
    });
}

function clearFiltersIni() {
    filtersIni = { initiative: [], epic: [], project: [], status: [], assignee: [] };
    const filtersContainer = document.querySelector("#section-initiatives .filters-row");
    if (filtersContainer) filtersContainer.outerHTML = buildInitiativeFilters();
    renderInitiativesSection();
}

function clearFiltersOrphan() {
    filtersOrphan = { epic: [], project: [], status: [], assignee: [] };
    const filtersContainer = document.querySelector("#section-orphans .filters-row");
    if (filtersContainer) filtersContainer.outerHTML = buildOrphanFilters();
    renderOrphansSection();
}

// ==================== FILTER LOGIC ====================

function filterStoriesBy(stories, f) {
    let result = stories;
    if (f.project && f.project.length > 0) result = result.filter(s => f.project.includes(s.project_key));
    if (f.status && f.status.length > 0) result = result.filter(s => f.status.includes(s.status));
    if (f.assignee && f.assignee.length > 0) result = result.filter(s => f.assignee.includes(s.assignee_name));
    return result;
}

function filterInitiatives() {
    let result = dataInitiatives;
    if (filtersIni.initiative.length > 0) result = result.filter(i => filtersIni.initiative.includes(i.key));
    return result.map(i => {
        let epics = i.epics;
        if (filtersIni.epic.length > 0) epics = epics.filter(e => filtersIni.epic.includes(e.key));
        // Aplica filtros de stories apenas se algum filtro de story-level está ativo
        const hasStoryFilter = (filtersIni.project.length > 0 || filtersIni.status.length > 0 || filtersIni.assignee.length > 0);
        if (hasStoryFilter) {
            epics = epics.map(e => ({ ...e, stories: filterStoriesBy(e.stories, filtersIni) })).filter(e => e.stories.length > 0);
        }
        return { ...i, epics };
    }).filter(i => i.epics.length > 0);
}

function filterOrphans() {
    let result = dataOrphans;
    if (filtersOrphan.epic.length > 0) result = result.filter(e => filtersOrphan.epic.includes(e.key));
    const hasStoryFilter = (filtersOrphan.project.length > 0 || filtersOrphan.status.length > 0 || filtersOrphan.assignee.length > 0);
    if (hasStoryFilter) {
        result = result.map(e => ({ ...e, stories: filterStoriesBy(e.stories, filtersOrphan) })).filter(e => e.stories.length > 0);
    }
    return result;
}

// ==================== RENDER ====================

function renderAll() {
    let html = "";

    if (dataInitiatives.length > 0) {
        html += `<div class="roadmap-section" id="section-initiatives">`;
        html += `<div class="section-title">Iniciativas e Epicos <span class="section-badge">${dataInitiatives.length} iniciativa(s)</span></div>`;
        html += buildInitiativeFilters();
        html += `<div id="ini-roadmap"></div>`;
        html += `</div>`;
    }

    if (dataOrphans.length > 0) {
        html += `<div class="roadmap-section orphan-separator" id="section-orphans">`;
        html += `<div class="section-title">Epicos Orfaos <span class="section-badge">${dataOrphans.length} epico(s) sem iniciativa</span></div>`;
        html += buildOrphanFilters();
        html += `<div id="orp-roadmap"></div>`;
        html += `</div>`;
    }

    if (!dataInitiatives.length && !dataOrphans.length) {
        html = `<p class="empty-state">Nenhum dado encontrado. Execute uma sincronizacao primeiro.</p>`;
    }

    document.getElementById("roadmap-content").innerHTML = html;
    renderInitiativesSection();
    renderOrphansSection();
}

function renderInitiativesSection() {
    const container = document.getElementById("ini-roadmap");
    if (!container) return;
    const months = getMonthsRange();
    const currentMonthKey = getCurrentMonthKey();
    const initiatives = filterInitiatives();

    if (initiatives.length === 0) {
        container.innerHTML = `<p style="padding:1.5rem;text-align:center;color:#94a3b8;">Nenhuma story encontrada.</p>`;
        return;
    }

    let html = `<div class="roadmap-container" style="--month-count:${months.length}">`;
    html += renderTimelineHeader(months, currentMonthKey);
    for (const ini of initiatives) {
        // Stats FIXAS: usa dados originais (não filtrados)
        const origIni = dataInitiatives.find(i => i.key === ini.key);
        const iniStats = countDone(origIni ? origIni.epics.flatMap(e => e.stories) : []);
        html += `<div class="initiative-header"><div class="initiative-name">${ini.key} — ${ini.summary}</div><div class="header-stats">${iniStats.done} de ${iniStats.total} Atividades — ${iniStats.pct}%</div></div>`;
        for (const epic of ini.epics) {
            const origEpic = origIni ? origIni.epics.find(e => e.key === epic.key) : null;
            const epicStats = countDone(origEpic ? origEpic.stories : []);
            html += `<div class="epic-header"><div class="epic-name"><span class="epic-key">${epic.key}</span> ${epic.summary}</div><div class="header-stats">${epicStats.done} de ${epicStats.total} Atividades — ${epicStats.pct}%</div></div>`;
            for (const story of epic.stories.sort((a, b) => (getTimelineDate(a) || "").localeCompare(getTimelineDate(b) || ""))) {
                html += renderStoryRow(story, months);
            }
        }
    }
    html += `</div>`;
    container.innerHTML = html;
}

function renderOrphansSection() {
    const container = document.getElementById("orp-roadmap");
    if (!container) return;
    const months = getMonthsRange();
    const currentMonthKey = getCurrentMonthKey();
    const orphans = filterOrphans();

    if (orphans.length === 0) {
        container.innerHTML = `<p style="padding:1.5rem;text-align:center;color:#94a3b8;">Nenhuma story encontrada.</p>`;
        return;
    }

    let html = `<div class="roadmap-container" style="--month-count:${months.length}">`;
    html += renderTimelineHeader(months, currentMonthKey);
    for (const epic of orphans) {
        // Stats FIXAS: usa dados originais
        const origEpic = dataOrphans.find(e => e.key === epic.key);
        const epicStats = countDone(origEpic ? origEpic.stories : []);
        html += `<div class="epic-header"><div class="epic-name"><span class="epic-key">${epic.key}</span> ${epic.summary}</div><div class="header-stats">${epicStats.done} de ${epicStats.total} Atividades — ${epicStats.pct}%</div></div>`;
        for (const story of epic.stories.sort((a, b) => (getTimelineDate(a) || "").localeCompare(getTimelineDate(b) || ""))) {
            html += renderStoryRow(story, months);
        }
    }
    html += `</div>`;
    container.innerHTML = html;
}

function getCurrentMonthKey() {
    const n = new Date();
    return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}`;
}

function renderTimelineHeader(months, currentMonthKey) {
    let html = `<div class="timeline-header"><div class="timeline-header-label">Listagem de Atividades</div><div class="timeline-months">`;
    for (const m of months) {
        const cls = m.key === currentMonthKey ? " current" : "";
        html += `<div class="timeline-month${cls}">${m.label} ${m.year}</div>`;
    }
    return html + `</div></div>`;
}

function renderStoryRow(story, months) {
    const timelineDate = getTimelineDate(story);
    const monthKey = getMonthKey(timelineDate);
    const barClass = getBarClass(story.status);
    const badgeClass = getStatusBadgeClass(story.status);
    const shortDate = formatShortDate(timelineDate);
    const fullDate = timelineDate ? new Date(timelineDate).toLocaleDateString("pt-BR") : "—";

    let html = `<div class="story-row"><div class="story-info">`;
    html += jiraLink(story.key);
    html += `<span class="story-assignee" title="${story.assignee_name || ''}">${story.assignee_name || "—"}</span>`;
    html += `<span class="story-name" title="${story.summary}">${story.summary}</span>`;
    html += `<span class="story-status-badge ${badgeClass}">${story.status}</span>`;
    html += `</div><div class="story-timeline">`;

    for (const m of months) {
        html += `<div class="timeline-cell">`;
        if (m.key === monthKey) {
            html += `<div class="gantt-bar ${barClass}"
                data-story="${story.summary}" data-key="${story.key}"
                data-project="${story.project_key}" data-status="${story.status}"
                data-date="${fullDate}" data-assignee="${story.assignee_name || '—'}"
                onmouseenter="showTooltip(event,this)" onmouseleave="hideTooltip()">${shortDate}</div>`;
        }
        html += `</div>`;
    }

    return html + `</div></div>`;
}

// ==================== TOOLTIP ====================

function showTooltip(event, el) {
    const tip = document.getElementById("tooltip");
    const dl = (el.dataset.status === "Done" || el.dataset.status === "Canceled") ? "Resolved" : "Due Date";
    tip.innerHTML = `
        <div class="tooltip-title">${el.dataset.key} — ${el.dataset.story}</div>
        <div class="tooltip-row">Projeto: <span>${el.dataset.project}</span></div>
        <div class="tooltip-row">Assignee: <span>${el.dataset.assignee}</span></div>
        <div class="tooltip-row">Status: <span>${el.dataset.status}</span></div>
        <div class="tooltip-row">${dl}: <span>${el.dataset.date}</span></div>
    `;
    tip.classList.add("visible");
    positionTooltip(event);
}

function hideTooltip() { document.getElementById("tooltip").classList.remove("visible"); }

document.addEventListener("mousemove", (e) => {
    const t = document.getElementById("tooltip");
    if (t.classList.contains("visible")) positionTooltip(e);
});

function positionTooltip(e) {
    const t = document.getElementById("tooltip");
    t.style.left = (e.clientX + 12) + "px";
    t.style.top = (e.clientY + 12) + "px";
}

// ==================== INIT ====================

async function init() {
    try {
        const res = await fetch("/api/hierarchy/roadmap");
        const data = await res.json();
        dataInitiatives = data.initiatives || [];
        dataOrphans = data.orphan_epics || [];
        renderAll();
    } catch (err) {
        document.getElementById("roadmap-content").innerHTML = `<p class="empty-state">Erro ao carregar: ${err.message}</p>`;
    }
}

init();
