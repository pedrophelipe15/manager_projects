/**
 * Hierarchy Settings — CRUD de hierarquias + Sync + Histórico.
 */

let pollInterval = null;

async function init() {
    await Promise.all([loadConfig(), loadExcluded(), loadHistory(), checkSyncStatus()]);
}

// ==================== PROJETOS EXCLUIDOS ====================

async function loadExcluded() {
    try {
        const res = await fetch("/api/settings/excluded-projects");
        const data = await res.json();
        renderExcluded(data.excluded_projects || []);
    } catch (err) {
        document.getElementById("excluded-body").innerHTML = `<tr><td colspan="2" class="empty-state">Erro: ${err.message}</td></tr>`;
    }
}

function renderExcluded(keys) {
    const tbody = document.getElementById("excluded-body");
    if (!keys || keys.length === 0) {
        tbody.innerHTML = `<tr><td colspan="2" class="empty-state">Nenhum projeto excluido.</td></tr>`;
        return;
    }

    tbody.innerHTML = keys.map(k => `
        <tr>
            <td><strong>${escapeHTML(k)}</strong></td>
            <td><button class="btn-delete" onclick="deleteExcluded('${escapeHTML(k)}')">Remover</button></td>
        </tr>
    `).join("");
}

async function addExcluded() {
    const input = document.getElementById("input-excluded-key");
    const key = input.value.trim();
    if (!key) return alert("Informe o project key (ex: PSDC).");

    try {
        const res = await fetch("/api/settings/excluded-projects", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ key }),
        });

        if (res.status === 409) {
            alert("Esse projeto ja esta excluido.");
            return;
        }
        if (!res.ok) {
            const err = await res.json();
            alert(err.detail || "Erro ao excluir projeto.");
            return;
        }

        input.value = "";
        await loadExcluded();
    } catch (err) {
        alert("Erro: " + err.message);
    }
}

async function deleteExcluded(key) {
    if (!confirm(`Reativar o projeto "${key}"? Ele voltara a ser consolidado e exibido.`)) return;

    try {
        const res = await fetch(`/api/settings/excluded-projects/${encodeURIComponent(key)}`, { method: "DELETE" });
        if (!res.ok) {
            const err = await res.json();
            alert(err.detail || "Erro ao remover.");
            return;
        }
        await loadExcluded();
    } catch (err) {
        alert("Erro: " + err.message);
    }
}

// ==================== CONFIG CRUD ====================

async function loadConfig() {
    try {
        const res = await fetch("/api/hierarchy/config");
        const entries = await res.json();
        renderConfig(entries);
    } catch (err) {
        document.getElementById("config-body").innerHTML = `<tr><td colspan="4" class="empty-state">Erro: ${err.message}</td></tr>`;
    }
}

function renderConfig(entries) {
    const tbody = document.getElementById("config-body");
    if (!entries || entries.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="empty-state">Nenhuma hierarquia configurada.</td></tr>`;
        return;
    }

    tbody.innerHTML = entries.map(e => `
        <tr>
            <td><strong>${escapeHTML(e.key)}</strong></td>
            <td>${escapeHTML(e.name)}</td>
            <td>${e.type === "initiative" ? "Iniciativa" : "Epico"}</td>
            <td><button class="btn-delete" onclick="deleteEntry('${escapeHTML(e.key)}')">Remover</button></td>
        </tr>
    `).join("");
}

async function addEntry() {
    const key = document.getElementById("input-key").value.trim();
    const name = document.getElementById("input-name").value.trim();
    const type = document.getElementById("input-type").value;

    if (!key) return alert("Informe a key da issue.");
    if (!name) return alert("Informe um nome descritivo.");

    try {
        const res = await fetch("/api/hierarchy/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ key, name, type }),
        });

        if (res.status === 409) {
            alert("Essa key ja esta configurada.");
            return;
        }
        if (!res.ok) {
            const err = await res.json();
            alert(err.detail || "Erro ao adicionar.");
            return;
        }

        document.getElementById("input-key").value = "";
        document.getElementById("input-name").value = "";
        await loadConfig();
    } catch (err) {
        alert("Erro: " + err.message);
    }
}

async function deleteEntry(key) {
    if (!confirm(`Remover "${key}" da configuracao?`)) return;

    try {
        const res = await fetch(`/api/hierarchy/config/${key}`, { method: "DELETE" });
        if (!res.ok) {
            const err = await res.json();
            alert(err.detail || "Erro ao remover.");
            return;
        }
        await loadConfig();
    } catch (err) {
        alert("Erro: " + err.message);
    }
}

// ==================== SYNC ====================

async function triggerSync() {
    const btn = document.getElementById("btn-sync");
    btn.disabled = true;
    btn.textContent = "Sincronizando...";

    try {
        const res = await fetch("/api/hierarchy/sync", { method: "POST" });
        if (!res.ok) {
            const err = await res.json();
            alert(err.detail || "Erro ao iniciar sync.");
            btn.disabled = false;
            btn.textContent = "Sincronizar Hierarquia";
            return;
        }

        showSyncLog(true);
        startPolling();
    } catch (err) {
        alert("Erro: " + err.message);
        btn.disabled = false;
        btn.textContent = "Sincronizar Hierarquia";
    }
}

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(pollSyncStatus, 2000);
}

function stopPolling() {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null; }
}

async function checkSyncStatus() {
    try {
        const res = await fetch("/api/hierarchy/sync/status");
        const status = await res.json();
        if (status.running) {
            document.getElementById("btn-sync").disabled = true;
            document.getElementById("btn-sync").textContent = "Sincronizando...";
            showSyncLog(true);
            renderSyncLog(status.progress);
            startPolling();
        }
    } catch (err) { /* ignore */ }
}

async function pollSyncStatus() {
    try {
        const res = await fetch("/api/hierarchy/sync/status");
        const status = await res.json();
        renderSyncLog(status.progress);

        if (!status.running) {
            stopPolling();
            document.getElementById("btn-sync").disabled = false;
            document.getElementById("btn-sync").textContent = "Sincronizar Hierarquia";
            document.getElementById("sync-status-text").textContent = "Concluido!";
            await loadHistory();
        }
    } catch (err) {
        stopPolling();
        document.getElementById("btn-sync").disabled = false;
        document.getElementById("btn-sync").textContent = "Sincronizar Hierarquia";
    }
}

function showSyncLog(visible) {
    const log = document.getElementById("sync-log");
    log.classList.toggle("visible", visible);
}

function renderSyncLog(lines) {
    const log = document.getElementById("sync-log");
    log.innerHTML = (lines || []).map(line => {
        let cls = "line-info";
        if (line.includes("\u2713") || line.includes("conclu")) cls = "line-ok";
        else if (line.includes("ERRO") || line.includes("falhou")) cls = "line-err";
        return `<div class="${cls}">${escapeHTML(line)}</div>`;
    }).join("");
    log.scrollTop = log.scrollHeight;
}

// ==================== HISTORY ====================

async function loadHistory() {
    try {
        const res = await fetch("/api/hierarchy/sync/history");
        const rows = await res.json();
        renderHistory(rows);
    } catch (err) {
        document.getElementById("history-body").innerHTML = `<tr><td colspan="8" class="empty-state">Erro: ${err.message}</td></tr>`;
    }
}

function renderHistory(rows) {
    const tbody = document.getElementById("history-body");
    if (!rows || rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" class="empty-state">Nenhuma sincronizacao realizada.</td></tr>`;
        return;
    }

    tbody.innerHTML = rows.map(r => {
        const dt = r.started_at ? new Date(r.started_at).toLocaleString("pt-BR") : "—";
        const dur = r.duration_seconds ? `${r.duration_seconds}s` : "—";
        const statusCls = r.status === "success" ? "status-success" : "status-error";
        return `
            <tr>
                <td>${dt}</td>
                <td>${dur}</td>
                <td style="text-align:center">${r.initiatives_count || 0}</td>
                <td style="text-align:center">${r.epics_count || 0}</td>
                <td style="text-align:center">${r.stories_count || 0}</td>
                <td style="text-align:center">${r.subtasks_count || 0}</td>
                <td style="text-align:center">${r.changelogs_count || 0}</td>
                <td class="${statusCls}">${r.status}</td>
            </tr>
        `;
    }).join("");
}

// ==================== UTILS ====================

function escapeHTML(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

init();
