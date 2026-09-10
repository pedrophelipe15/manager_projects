/**
 * Timeline — Árvore hierárquica visual collapsible.
 * Carrega dados do /api/hierarchy/tree e renderiza como árvore com filtros.
 */

let treeData = null;
let epicHealthData = null;

async function init() {
    const container = document.getElementById("tree-container");

    try {
        const [configRes, healthRes] = await Promise.all([
            fetch("/api/hierarchy/config"),
            fetch("/api/hierarchy/epic-health"),
        ]);

        const config = await configRes.json();
        epicHealthData = await healthRes.json();

        if (!config || config.length === 0) {
            container.innerHTML = `<p class="empty-state">Nenhuma hierarquia configurada. Acesse Configuracoes para adicionar.</p>`;
            return;
        }

        // Carrega árvores para cada entrada do config
        const trees = [];
        for (const entry of config) {
            const res = await fetch(`/api/hierarchy/tree?key=${entry.key}`);
            if (res.ok) {
                const data = await res.json();
                trees.push(data);
            }
        }

        treeData = trees;
        populateTeamFilter(trees);
        renderTree(trees);

    } catch (err) {
        container.innerHTML = `<p class="empty-state">Erro ao carregar: ${err.message}</p>`;
        console.error(err);
    }
}

function populateTeamFilter(trees) {
    const teams = new Set();
    for (const tree of trees) {
        const epics = tree.epics || (tree.epic ? [tree.epic] : []);
        for (const epic of epics) {
            for (const story of (epic.stories || [])) {
                if (story.project_key) teams.add(story.project_key);
            }
        }
    }

    const select = document.getElementById("filter-team");
    for (const t of [...teams].sort()) {
        const opt = document.createElement("option");
        opt.value = t;
        opt.textContent = t;
        select.appendChild(opt);
    }
}

function getEpicRisk(epicKey) {
    if (!epicHealthData || !epicHealthData.epics) return "";
    const e = epicHealthData.epics.find(x => x.epic.key === epicKey);
    return e ? e.risk : "";
}

function applyFilters() {
    if (treeData) renderTree(treeData);
}

function renderTree(trees) {
    const container = document.getElementById("tree-container");
    const filterTeam = document.getElementById("filter-team").value;
    const filterStatus = document.getElementById("filter-status").value;
    const filterRisk = document.getElementById("filter-risk").value;

    let html = `<ul class="tree">`;

    for (const tree of trees) {
        if (tree.type === "initiative") {
            html += renderInitiativeNode(tree, filterTeam, filterStatus, filterRisk);
        } else if (tree.type === "epic") {
            html += renderEpicNode(tree.epic, filterTeam, filterStatus, filterRisk);
        }
    }

    html += `</ul>`;
    container.innerHTML = html;
}

function renderInitiativeNode(tree, filterTeam, filterStatus, filterRisk) {
    const ini = tree.initiative;
    const epics = tree.epics || [];

    // Filtra épicos por risco
    let filteredEpics = epics;
    if (filterRisk) {
        filteredEpics = epics.filter(e => getEpicRisk(e.key) === filterRisk);
    }

    if (filteredEpics.length === 0 && filterRisk) return "";

    let childrenHtml = "";
    for (const epic of filteredEpics) {
        childrenHtml += renderEpicNode(epic, filterTeam, filterStatus, filterRisk);
    }

    const count = filteredEpics.length;
    return `
        <li class="tree-item level-initiative">
            <div class="tree-node" onclick="toggleNode(this)">
                <span class="tree-toggle expanded">&#9654;</span>
                <span class="tree-key">${jiraLink(ini.key)}</span>
                <span class="tree-summary">${escapeHTML(ini.summary)}</span>
                <span class="tree-status">${ini.status}</span>
                <span class="tree-count">${count} epicos</span>
            </div>
            <ul class="tree-children open">${childrenHtml}</ul>
        </li>
    `;
}

function renderEpicNode(epic, filterTeam, filterStatus, filterRisk) {
    const stories = epic.stories || [];
    const risk = getEpicRisk(epic.key);

    if (filterRisk && risk !== filterRisk) return "";

    // Filtra stories
    let filteredStories = stories;
    if (filterTeam) {
        filteredStories = filteredStories.filter(s => s.project_key === filterTeam);
    }
    if (filterStatus) {
        filteredStories = filteredStories.filter(s => s.status === filterStatus);
    }

    if (filteredStories.length === 0 && (filterTeam || filterStatus)) return "";

    let childrenHtml = "";
    for (const story of filteredStories) {
        childrenHtml += renderStoryNode(story, filterStatus);
    }

    const riskHtml = risk ? `<span class="risk-badge risk-${risk}" style="font-size:0.6rem">${risk}</span>` : "";
    const count = filteredStories.length;

    return `
        <li class="tree-item level-epic">
            <div class="tree-node" onclick="toggleNode(this)">
                <span class="tree-toggle">&#9654;</span>
                <span class="tree-key">${jiraLink(epic.key)}</span>
                <span class="tree-summary">${escapeHTML(epic.summary)}</span>
                <span class="tree-status">${epic.status}</span>
                ${riskHtml}
                <span class="tree-count">${count} stories</span>
            </div>
            <ul class="tree-children">${childrenHtml}</ul>
        </li>
    `;
}

function renderStoryNode(story, filterStatus) {
    const subtasks = story.subtasks || [];

    let filteredSubs = subtasks;
    if (filterStatus) {
        filteredSubs = subtasks.filter(s => s.status === filterStatus);
    }

    const hasChildren = filteredSubs.length > 0;
    let childrenHtml = "";
    for (const sub of filteredSubs) {
        childrenHtml += renderSubtaskNode(sub);
    }

    const toggleClass = hasChildren ? "" : " leaf";
    const meta = story.assignee_name ? `<span class="tree-meta">${escapeHTML(story.assignee_name)}</span>` : "";
    const teamBadge = story.project_key ? `<span class="tree-meta">${story.project_key}</span>` : "";

    return `
        <li class="tree-item level-story">
            <div class="tree-node" onclick="toggleNode(this)">
                <span class="tree-toggle${toggleClass}">&#9654;</span>
                <span class="tree-key">${jiraLink(story.key)}</span>
                <span class="tree-summary">${escapeHTML(story.summary)}</span>
                <span class="tree-status">${story.status}</span>
                ${teamBadge}
                ${meta}
            </div>
            ${hasChildren ? `<ul class="tree-children">${childrenHtml}</ul>` : ""}
        </li>
    `;
}

function renderSubtaskNode(sub) {
    const meta = sub.assignee_name ? `<span class="tree-meta">${escapeHTML(sub.assignee_name)}</span>` : "";
    return `
        <li class="tree-item level-subtask">
            <div class="tree-node">
                <span class="tree-toggle leaf">&#9654;</span>
                <span class="tree-key">${jiraLink(sub.key)}</span>
                <span class="tree-summary">${escapeHTML(sub.summary)}</span>
                <span class="tree-status">${sub.status}</span>
                ${meta}
            </div>
        </li>
    `;
}

function toggleNode(nodeEl) {
    const item = nodeEl.closest(".tree-item");
    const children = item.querySelector(".tree-children");
    const toggle = nodeEl.querySelector(".tree-toggle");
    if (!children || toggle.classList.contains("leaf")) return;

    children.classList.toggle("open");
    toggle.classList.toggle("expanded");
}

function expandAll() {
    document.querySelectorAll(".tree-children").forEach(el => el.classList.add("open"));
    document.querySelectorAll(".tree-toggle:not(.leaf)").forEach(el => el.classList.add("expanded"));
}

function collapseAll() {
    document.querySelectorAll(".tree-children").forEach(el => el.classList.remove("open"));
    document.querySelectorAll(".tree-toggle").forEach(el => el.classList.remove("expanded"));
}

function escapeHTML(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function jiraLink(key) {
    return `<a href="https://jiraps.atlassian.net/browse/${key}" target="_blank" rel="noopener" style="color:inherit;text-decoration:none">${key}</a>`;
}

init();
