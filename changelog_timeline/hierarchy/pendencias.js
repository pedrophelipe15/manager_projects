/**
 * Pendencias — atividades pendentes da hierarquia.
 * Replica o padrao de tabela/filtros do dashboard.html (multiselect dropdown,
 * busca por chave, filtro por epico/parent, paginacao) + ordenacao por coluna.
 * Fonte: GET /api/hierarchy/pending (ja exclui Done/Resolved/Canceled/Reject).
 */

const state = {
    all: [],
    filtered: [],
    page: 1,
    pageSize: 15,
    sort: { col: null, dir: "asc" },
};

const JIRA = "https://jiraps.atlassian.net/browse/";

// ---- Formatacao (mesmo padrao do dashboard) ----
function formatDuration(ms) {
    if (!ms || ms === 0) return "--";
    const days = Math.floor(ms / 86400000);
    const hours = Math.floor((ms % 86400000) / 3600000);
    if (days > 0) return `${days}d ${hours}h`;
    return `${hours}h`;
}
function formatDate(s) {
    if (!s) return "--";
    const p = String(s).split("T")[0].split("-");
    return p.length === 3 ? `${p[2]}/${p[1]}/${p[0]}` : s;
}
function escapeHtml(s) {
    return String(s == null ? "" : s)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

document.addEventListener("DOMContentLoaded", async () => {
    try {
        const r = await fetch("/api/hierarchy/pending");
        const data = await r.json();
        state.all = data.issues || [];
    } catch (e) {
        console.error("Erro ao buscar pendencias:", e);
        state.all = [];
    }
    document.getElementById("total-count").textContent = state.all.length.toLocaleString("pt-BR");
    buildDropdowns();
    bindEvents();
    applyFilters();
});

function bindEvents() {
    document.getElementById("btn-prev").addEventListener("click", () => {
        if (state.page > 1) { state.page--; renderTable(); }
    });
    document.getElementById("btn-next").addEventListener("click", () => {
        const maxP = Math.ceil(state.filtered.length / state.pageSize);
        if (state.page < maxP) { state.page++; renderTable(); }
    });
    document.getElementById("searchInput").addEventListener("input", applyFilters);
    document.getElementById("filterParentKey").addEventListener("input", applyFilters);

    // Ordenacao por coluna
    document.querySelectorAll("#pending-table th.sortable").forEach(th => {
        th.addEventListener("click", () => {
            const k = th.dataset.k;
            if (state.sort.col === k) { state.sort.dir = state.sort.dir === "asc" ? "desc" : "asc"; }
            else { state.sort.col = k; state.sort.dir = "asc"; }
            renderTable();
        });
    });
}

// ---- Dropdowns multiselect (Projeto, Status, Assignee) ----
function uniq(vals) { return [...new Set(vals.filter(v => v !== "" && v != null))].sort(); }

function buildDropdowns() {
    fillDropdown("project", uniq(state.all.map(i => i.project_key)));
    fillDropdown("status", uniq(state.all.map(i => i.status)));
    fillDropdown("assignee", uniq(state.all.map(i => i.assignee)));
}

function fillDropdown(type, options) {
    const div = document.getElementById(`${type}-dropdown`);
    div.innerHTML = "";
    options.forEach(v => {
        const label = document.createElement("label");
        label.innerHTML = `<input type="checkbox" value="${escapeHtml(v)}" class="${type}-check" onchange="updateHeader('${type}'); applyFilters();"> ${escapeHtml(v)}`;
        div.appendChild(label);
    });
}

function toggleDropdown(id) {
    document.getElementById(id).classList.toggle("open");
}
window.toggleDropdown = toggleDropdown;

function updateHeader(type) {
    const checked = document.querySelectorAll(`#${type}-dropdown input:checked`);
    const header = document.querySelector(`#${type}-multiselect .multiselect-header`);
    const labels = { project: "Projeto", status: "Status", assignee: "Assignee" };
    header.innerHTML = "";
    if (checked.length === 0) {
        header.innerHTML = `<span class="placeholder-text">${labels[type]}: Todos</span>`;
    } else {
        checked.forEach(cb => {
            const tag = document.createElement("span");
            tag.className = "multiselect-tag";
            tag.innerHTML = `${escapeHtml(cb.value)} <span class="tag-remove" onclick="removeTag(event,'${type}','${escapeHtml(cb.value)}')">×</span>`;
            header.appendChild(tag);
        });
    }
}
window.updateHeader = updateHeader;

window.removeTag = function (event, type, value) {
    event.stopPropagation();
    const cb = document.querySelector(`#${type}-dropdown input[value="${value}"]`);
    if (cb) { cb.checked = false; updateHeader(type); applyFilters(); }
};

// Fecha dropdowns ao clicar fora
window.addEventListener("click", (e) => {
    if (!e.target.closest(".custom-multiselect")) {
        document.querySelectorAll(".multiselect-options").forEach(el => el.classList.remove("open"));
    }
});

window.clearFilters = function () {
    document.getElementById("searchInput").value = "";
    document.getElementById("filterParentKey").value = "";
    document.querySelectorAll(".project-check, .status-check, .assignee-check").forEach(cb => cb.checked = false);
    updateHeader("project"); updateHeader("status"); updateHeader("assignee");
    applyFilters();
};

function applyFilters() {
    const search = document.getElementById("searchInput").value.toLowerCase();
    const parent = document.getElementById("filterParentKey").value.toLowerCase();
    const sel = (type) => Array.from(document.querySelectorAll(`.${type}-check:checked`)).map(cb => cb.value);
    const projects = sel("project"), statuses = sel("status"), assignees = sel("assignee");

    state.filtered = state.all.filter(i => {
        if (search && !i.key.toLowerCase().includes(search)) return false;
        if (parent && !(i.parent_key || "").toLowerCase().includes(parent)) return false;
        if (projects.length && !projects.includes(i.project_key)) return false;
        if (statuses.length && !statuses.includes(i.status)) return false;
        if (assignees.length && !assignees.includes(i.assignee)) return false;
        return true;
    });

    state.page = 1;
    renderTable();
}
window.applyFilters = applyFilters;

function sortedRows() {
    const { col, dir } = state.sort;
    if (!col) return state.filtered;
    const numeric = col === "lead_time_ms" || col === "cycle_time_ms";
    return state.filtered.slice().sort((a, b) => {
        let va = a[col], vb = b[col];
        if (numeric) { va = va || 0; vb = vb || 0; return dir === "asc" ? va - vb : vb - va; }
        const c = String(va == null ? "" : va).localeCompare(String(vb == null ? "" : vb), "pt-BR", { numeric: true });
        return dir === "asc" ? c : -c;
    });
}

function statusClass(status) {
    switch (status) {
        case "In Progress": return "status-progress";
        case "Blocked": return "status-blocked";
        case "Test": return "status-test";
        case "Waiting for Delivery": return "status-waiting";
        default: return "status-open";
    }
}

function renderTable() {
    const tbody = document.getElementById("table-body");
    const rows = sortedRows();
    const total = rows.length;
    const maxP = Math.max(1, Math.ceil(total / state.pageSize));
    if (state.page > maxP) state.page = maxP;
    const start = (state.page - 1) * state.pageSize;
    const pageRows = rows.slice(start, start + state.pageSize);

    // Indicadores de ordenacao
    document.querySelectorAll("#pending-table th.sortable").forEach(th => {
        const ind = th.querySelector(".sort-ind");
        ind.textContent = th.dataset.k === state.sort.col ? (state.sort.dir === "asc" ? "↑" : "↓") : "↕";
    });

    if (!pageRows.length) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:2rem">Nenhuma pendencia no filtro atual.</td></tr>`;
    } else {
        tbody.innerHTML = pageRows.map(i => `<tr>
            <td><strong><a href="${JIRA}${encodeURIComponent(i.key)}" target="_blank" rel="noopener" class="jira-link">${escapeHtml(i.key)}</a></strong></td>
            <td>${i.parent_key ? `<a href="${JIRA}${encodeURIComponent(i.parent_key)}" target="_blank" rel="noopener" class="jira-link">${escapeHtml(i.parent_key)}</a>` : "--"}</td>
            <td class="cell-assignee">${escapeHtml(i.assignee || "--")}</td>
            <td class="cell-summary" title="${escapeHtml(i.summary)}">${escapeHtml(i.summary)}</td>
            <td><span class="status-badge ${statusClass(i.status)}">${escapeHtml(i.status)}</span></td>
            <td>${formatDate(i.created_at)}</td>
            <td>${formatDate(i.due_date)}</td>
            <td>${formatDate(i.updated_at)}</td>
        </tr>`).join("");
    }

    document.getElementById("page-info").textContent = `Pagina ${state.page} de ${maxP}`;
    document.getElementById("btn-prev").disabled = state.page <= 1;
    document.getElementById("btn-next").disabled = state.page >= maxP;
}
